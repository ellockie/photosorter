"""Plan, and apply, re-dating the shots of an already-sorted dated folder.

The one planner (T8) behind restructure step 0. For every shot in a dated
folder it asks the engine for the local stamp the shot should carry -- always
from the untouched EXIF reading in its sidecar, so a second run plans nothing
(idempotent) and removing a ``timezone.json`` entry plans the way back
(reversible). What it plans obeys the archive standard:

* the stamp opening the name is replaced; everything after it -- a sub-second
  (F9), the exposure fields, the camera, the suffixes -- is kept as it is;
* a shot moves **with its unit** (X10): each companion in a sidecar folder
  directly beside it (``__EXIF``, ``__PREVIEWS``, ``__OCR``,
  ``__VIDEOS_EXTRACTED``) whose name is the subject's name plus a suffix (X1),
  and any file with no sidecar of its own carrying the same old stamp (an edit)
  when exactly one shot claims that stamp;
* a shot whose **day** changes (N7 on the new stamp) moves to the sibling dated
  folder with the same description, created in the month folder its date
  belongs to (P5) when it does not exist. A folder's own date is never
  rewritten (N6); restructure steps 1 and 5 recompute its time (N3) and step 6
  the group spans (C11);
* a stray already filed on a day other than its folder's is renamed in place,
  never moved by this -- where it belongs is a question this does not answer;
* a name that is taken goes through F9: two different exposures of one second
  (both record a sub-second, and they differ) are told apart by it. Anything
  else is an F4 question for a person: reported, and the shot left alone.

Groups (a dated folder holding dated folders) are not planned: C4 says a group
holds no media, and step 8 is where loose media in one is dealt with.

Leaf module: engine, readings, stamps, taxonomy, siblings, legacy (N7, months).
"""

import dataclasses
import datetime
import os
from pathlib import Path

from src.constants.months import MONTH_FOLDERS
from src.pipeline_stages.clock_readings import \
    YEAR_RE, \
    folder_readings, \
    subject_dirs
from src.pipeline_stages.legacy import \
    date_folder_datetime
from src.pipeline_stages.siblings import \
    sibling_name, \
    subsecond_of_sidecar
from src.pipeline_stages.stamps import \
    LEADING_STAMP_RE, \
    format_day_prefix, \
    format_stamp, \
    parse_stamp, \
    split_dated_folder
from src.pipeline_stages.taxonomy import \
    sidecar_dir_names, \
    taxonomy_folder
from src.pipeline_stages.timezone_engine import \
    TimeModel, \
    format_duration, \
    order_inversions

TEMPORARY_PREFIX = "__RETIME_IN_PROGRESS__"


@dataclasses.dataclass
class FileMove:
    source: Path
    target: Path
    role: str          # subject | companion | follower


@dataclasses.dataclass
class ShotPlan:
    subject: Path
    camera: str
    reading: datetime.datetime
    correction: object
    current: datetime.datetime
    new_name: str
    target_folder: Path
    moves: list
    flags: list

    @property
    def target(self) -> Path:
        return self.moves[0].target


@dataclasses.dataclass
class FolderPlan:
    folder: Path
    shots: list
    skipped: list            # (path, reason)
    new_folders: list
    inversions: list
    notes: list
    folder_time_before: str | None = None
    folder_time_after: str | None = None

    @property
    def changes(self) -> bool:
        return bool(self.shots)

    @property
    def moves(self) -> list:
        return [move for shot in self.shots for move in shot.moves]

    def cameras(self) -> list[dict]:
        """Per camera: clock, error, shift(s), count -- what the prompt shows."""
        found: dict = {}
        for shot in self.shots:
            entry = found.setdefault(shot.camera, {"camera": shot.camera, "clocks": set(), "errors": set(),
                                                   "shifts": set(), "sources": set(), "count": 0, "examples": []})
            entry["clocks"].add(shot.correction.clock)
            entry["errors"].add(shot.correction.error_seconds)
            entry["shifts"].add(int(shot.correction.shift.total_seconds()))
            entry["sources"].add(shot.correction.source)
            entry["count"] += 1
            if len(entry["examples"]) < 3 and not shot.subject.parent.name.startswith("__"):
                entry["examples"].append((format_stamp(shot.current), format_stamp(shot.correction.stamp)))
        return list(found.values())


def _stamp_tail(name: str):
    match = LEADING_STAMP_RE.match(name)
    if not match:
        return None, None
    return parse_stamp(name[:match.end()]), name[match.end():]


def _folder_day(folder: Path) -> datetime.date | None:
    split = split_dated_folder(folder.name)
    if split is None:
        return None
    try:
        return datetime.date.fromisoformat(split.date)
    except ValueError:
        return None


def is_group(folder: Path) -> bool:
    try:
        return any(child.is_dir() and split_dated_folder(child.name) is not None
                   and not child.name.startswith("__") for child in folder.iterdir())
    except OSError:
        return False


def _target_day_folder(folder: Path, day: datetime.date) -> tuple[Path | None, str | None]:
    """The folder a shot moving to ``day`` goes to, or (None, why not)."""
    split = split_dated_folder(folder.name)
    tail = split.tail
    parent = folder.parent
    in_month = parent.name in MONTH_FOLDERS.values() and YEAR_RE.match(parent.parent.name or "")
    if in_month:
        parent = parent.parent.parent / f"{day:%Y}" / MONTH_FOLDERS[f"{day:%m}"]
    prefix = format_day_prefix(day)
    matches = []
    if parent.is_dir():
        for sibling in parent.iterdir():
            other = split_dated_folder(sibling.name)
            if sibling.is_dir() and other is not None and other.date == f"{day:%Y-%m-%d}" and other.tail == tail:
                matches.append(sibling)
    if len(matches) > 1:
        return None, f"{len(matches)} folders for {prefix}{tail} -- which one is a person's call"
    if matches:
        return matches[0], None
    return parent / f"{prefix}{tail}", None


def _companions(subject: Path, config: dict) -> list[Path]:
    found = []
    for name in sidecar_dir_names(config):
        directory = subject.parent / name
        if not directory.is_dir():
            continue
        for candidate in directory.iterdir():
            if candidate.is_file() and candidate.name.startswith(subject.name + "."):
                found.append(candidate)
    return sorted(found)


def plan_folder(folder: Path, config: dict, model: TimeModel, cache=None,
                start: datetime.datetime | None = None, end: datetime.datetime | None = None) -> FolderPlan:
    """What re-dating ``folder``'s shots would do. Reads only; changes nothing."""
    plan = FolderPlan(folder, [], [], [], [], [])
    split = split_dated_folder(folder.name)
    if split is None:
        plan.notes.append("not a dated folder")
        return plan
    plan.folder_time_before = split.time
    if is_group(folder):
        plan.notes.append("a group: its own media is step 8's (C4), not retimed here")
        return plan
    folder_day = _folder_day(folder)
    readings = folder_readings(folder, config, cache)
    by_subject = {shot.subject: shot for shot in readings}
    targets_taken: set[str] = set()
    vacated: set[str] = set()
    stamp_claims: dict = {}
    order_items = []
    top_level_after = []

    planned = []
    for shot in sorted(readings, key=lambda s: str(s.subject)):
        if shot.reading is None or not shot.subject.is_file():
            continue
        current, tail = _stamp_tail(shot.subject.name)
        if current is None:
            continue
        correction = model.correct(shot.camera, shot.reading, shot.counter)
        if shot.subdir == "":
            order_items.append((correction.stamp_text + tail, correction.true_utc, shot.subject.name))
        stamp_claims.setdefault((shot.subject.parent, format_stamp(current)), set()).add(correction.stamp)
        in_range = (start is None or shot.reading >= start) and (end is None or shot.reading < end)
        if correction.stamp == current or not in_range:
            if shot.subdir == "":
                top_level_after.append(current)
            continue
        flags = []
        if current not in (shot.reading, correction.stamp):
            flags.append(f"named {format_stamp(current)}, reading {format_stamp(shot.reading)}: renamed by hand?")
        if correction.ambiguous:
            flags.append("reading falls in a repeated hour; taken as after the clock change")
        new_day = date_folder_datetime(correction.stamp, config).date()
        current_day = date_folder_datetime(current, config).date()
        target_folder = folder
        if folder_day is not None and new_day != folder_day:
            if current_day != folder_day:
                flags.append(f"already filed away from its day ({current_day}); renamed in place, not moved")
            else:
                target_folder, why = _target_day_folder(folder, new_day)
                if target_folder is None:
                    plan.skipped.append((shot.subject, why))
                    continue
        if shot.subdir == "" and target_folder == folder:
            top_level_after.append(correction.stamp)
        planned.append((shot, current, tail, correction, target_folder, flags))

    # Every file planned to move frees its name for the others (rename chains).
    for shot, *_ in planned:
        vacated.add(str(shot.subject).casefold())
        for companion in _companions(shot.subject, config):
            vacated.add(str(companion).casefold())

    for shot, current, tail, correction, target_folder, flags in planned:
        new_name = format_stamp(correction.stamp) + tail
        place = target_folder / shot.subdir if shot.subdir else target_folder
        target = place / new_name
        key = str(target).casefold()
        occupied = key in targets_taken or (target.exists() and key not in vacated)
        if occupied:
            occupant = target
            occupant_sidecar = occupant.parent / taxonomy_folder(config, "exif") / (occupant.name + "._exif")
            mine, theirs = shot.subsecond, subsecond_of_sidecar(occupant_sidecar)
            candidate = sibling_name(new_name, mine)
            if mine and theirs and mine != theirs and candidate != new_name:
                new_name, target = candidate, place / candidate
                key = str(target).casefold()
                if key in targets_taken or (target.exists() and key not in vacated):
                    plan.skipped.append((shot.subject, f"{new_name} is taken too (F4: needs a person)"))
                    continue
                flags.append("same second as another shot: sub-second added (F9)")
            else:
                plan.skipped.append((shot.subject, f"{new_name} is already taken (F4: needs a person)"))
                continue
        targets_taken.add(key)
        moves = [FileMove(shot.subject, target, "subject")]
        for companion in _companions(shot.subject, config):
            suffix = companion.name[len(shot.subject.name):]
            moves.append(FileMove(companion, place / companion.parent.name / (new_name + suffix), "companion"))
            targets_taken.add(str(moves[-1].target).casefold())
        if target_folder != folder and not target_folder.exists() and target_folder not in plan.new_folders:
            plan.new_folders.append(target_folder)
        plan.shots.append(ShotPlan(shot.subject, shot.camera, shot.reading, correction, current,
                                   new_name, target_folder, moves, flags))

    _plan_followers(plan, folder, config, by_subject, stamp_claims)
    plan.inversions = order_inversions(order_items)
    if top_level_after:
        plan.folder_time_after = min(top_level_after).strftime("%H.%M.%S")
    return plan


def _plan_followers(plan, folder, config, by_subject, stamp_claims) -> None:
    """Files with no sidecar of their own follow the one shot sharing their old stamp."""
    planned = {(shot.subject.parent, format_stamp(shot.current)): shot for shot in plan.shots}
    moving = {move.source for move in plan.moves}
    for _subdir, place in subject_dirs(folder, config):
        try:
            files = sorted(path for path in place.iterdir() if path.is_file())
        except OSError:
            continue
        for path in files:
            if path in by_subject or path in moving:
                continue
            current, tail = _stamp_tail(path.name)
            if current is None:
                continue
            key = (place, format_stamp(current))
            shot = planned.get(key)
            if shot is None:
                continue
            if len(stamp_claims.get(key, ())) != 1:
                plan.skipped.append((path, "shares its stamp with shots going to different times"))
                continue
            target_place = shot.target.parent
            target = target_place / (format_stamp(shot.correction.stamp) + tail)
            if target.exists():
                plan.skipped.append((path, f"{target.name} is already taken (F4: needs a person)"))
                continue
            shot.moves.append(FileMove(path, target, "follower"))


def describe(plan: FolderPlan) -> list[str]:
    """The lines a person reads before answering yes / all / no."""
    lines = [str(plan.folder)]
    for camera in plan.cameras():
        clocks = ", ".join(sorted(camera["clocks"]))
        errors = ", ".join(f"{error:+d} s" for error in sorted(camera["errors"]))
        shifts = sorted(camera["shifts"])
        shift = format_duration(shifts[0]) if len(shifts) == 1 else \
            f"{format_duration(shifts[0])} .. {format_duration(shifts[-1])}"
        sources = "/".join(sorted(camera["sources"]))
        lines.append(f"  {camera['camera']:<8} {camera['count']} file(s)  clock {clocks}, error {errors} "
                     f"-> {shift}  ({sources})")
        for before, after in camera["examples"]:
            lines.append(f"      {before[-8:]} -> {after if after[:10] != before[:10] else after[-8:]}")
    companions = sum(1 for move in plan.moves if move.role != "subject")
    if companions:
        lines.append(f"  with {companions} companion/sidecar file(s) moving alongside (X10)")
    if plan.folder_time_after and plan.folder_time_after != plan.folder_time_before:
        lines.append(f"  folder time {plan.folder_time_before or '--'} -> {plan.folder_time_after} "
                     "(written by the canonicalise step, N3)")
    moved = sorted({shot.target_folder for shot in plan.shots if shot.target_folder != plan.folder}, key=str)
    for target in moved:
        count = sum(1 for shot in plan.shots if shot.target_folder == target)
        new = " (new folder)" if target in plan.new_folders else ""
        lines.append(f"  {count} file(s) change day -> {target.name}{new}")
    if not moved:
        lines.append("  day folder unchanged")
    if plan.inversions:
        lines.append(f"  name order: {len(plan.inversions)} shot(s) would sort out of time order, "
                     f"e.g. {plan.inversions[0][0]} (reported only)")
    else:
        lines.append("  name order: chronological")
    for shot in plan.shots:
        for flag in shot.flags:
            lines.append(f"  ! {shot.subject.name}: {flag}")
    for path, reason in plan.skipped:
        lines.append(f"  SKIPPED {path.name}: {reason}")
    return lines


def apply_plan(plan: FolderPlan, log=print) -> list[tuple[Path, Path]]:
    """Carry a plan out. Never overwrites; returns the ``(source, target)`` pairs done.

    Two phases when a target is a name another planned file is leaving (a rename
    chain): everything first steps aside to a temporary name in its own folder.
    """
    moves = plan.moves
    sources = {str(move.source).casefold() for move in moves}
    chained = any(str(move.target).casefold() in sources for move in moves)
    staged = []
    for move in moves:
        if chained:
            temporary = move.source.with_name(TEMPORARY_PREFIX + move.source.name)
            os.rename(move.source, temporary)
            staged.append((temporary, move))
        else:
            staged.append((move.source, move))
    done = []
    for current, move in staged:
        move.target.parent.mkdir(parents=True, exist_ok=True)
        if move.target.exists():
            raise FileExistsError(f"refusing to overwrite {move.target}")
        os.rename(current, move.target)
        done.append((move.source, move.target))
        log(f"    {move.source.name}  ->  {move.target.relative_to(plan.folder.parent) if move.target.is_relative_to(plan.folder.parent) else move.target}")
    return done
