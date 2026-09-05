"""Where an emptied folder is parked — decided here and nowhere else.

``ARCHIVE_STANDARD.md`` section 4.1. A **parking area** is ``__EMPTY_SUBFOLDERS``,
and it sits **where dated folders sit** (H2): directly under a month folder, or
inside a group beside that group's dated children. A day folder emptied of every
file goes into the one on its own level, and so does a legacy taxonomy container
the migration emptied — once it has been checked to hold no file anywhere, never
because it was assumed to.

It is a sibling of what it takes, and that is the whole of the rule. A day
emptied out of a month folder is parked in that month folder; a sub-event
emptied out of a group is parked in that group; neither leaves the level it was
on, so what a folder was near is still what it is near.

What that leaves illegal, and what H6 hoists, is a parking area **inside a leaf
dated folder** — where the legacy-container migration used to put one, three
levels down, holding an emptied ``##   EXIFs   ##`` in a shell nobody would ever
open. A leaf dated folder holds one event's files; a parked folder is not one of
them, so the area belongs one level up, beside the day itself.

This is the one rule that needs both halves — the parking folder's *name*, which
belongs to ``grouping_names``, and the *level* it lives at, which needs
``months`` — so it cannot live in either of them: both are strict leaf modules
importing nothing from the project. It gets its own module rather than being
spelled out in each of the callers, which is what T8 is for.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from src.constants.months import is_month_folder, month_folder_of
from src.pipeline_stages.grouping_names import EMPTY_SUBFOLDERS_FOLDER
from src.pipeline_stages.stamps import day_prefix


def holds_dated_child(folder: Path) -> bool:
    """True when ``folder`` directly holds at least one dated folder.

    Which is the definition of a group (C1) read off the disk rather than off
    the name. The marker is what a *name* claims; this is what is *there*, and
    the two disagree for exactly as long as it takes the marker pass to run --
    the live pipeline creates and empties sub-events without touching a marker.
    Parking has to be right in that window too, so it asks the disk.

    A parking area is not a dated folder and so never counts, which is what
    keeps a leaf day holding only a parked shell from looking like a group.
    """
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if is_parking_area(entry.name):
                    continue
                if not day_prefix(entry.name):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        return True
                except OSError:
                    continue
    except OSError:
        return False
    return False


def is_parking_level(folder: Path) -> bool:
    """True when a parking area may sit directly inside ``folder`` (H2).

    A month folder, or a group. Those are the two places a dated folder may
    sit, and a parking area goes wherever the folders it parks came from.
    """
    if is_month_folder(folder.name):
        return True
    return bool(day_prefix(folder.name)) and holds_dated_child(folder)


def parking_level_for(folder: Path) -> Path | None:
    """The nearest level at or above ``folder.parent`` that may hold a parking area.

    ``folder`` is the thing being parked, not its parent. For a dated folder
    this is its own parent and the walk stops immediately -- whatever holds a
    dated folder is a month folder or a group by definition. The walk is for
    everything else: an emptied ``##   EXIFs   ##`` inside a leaf day, a
    misplaced parking area being hoisted out of one.

    ``None`` means there is no such level anywhere above -- a tree out of
    shape, or a run pointed below a month folder. A caller reports and leaves
    the folder alone rather than inventing somewhere to put it.
    """
    current = folder.parent
    while True:
        if is_parking_level(current):
            return current
        parent = current.parent
        if parent == current:               # the filesystem root: nothing above
            return None
        current = parent


def parking_area_for(folder: Path) -> Path | None:
    """The ``__EMPTY_SUBFOLDERS`` that ``folder`` belongs in when it is emptied.

    ``None`` when there is no level above it allowed to hold one (H2). A caller
    must report and leave that folder alone: falling back to "beside it
    wherever it is" would create the malformed nested parking area H6 removes.
    """
    level = parking_level_for(folder)
    return level / EMPTY_SUBFOLDERS_FOLDER if level is not None else None


def is_parking_area(name: str) -> bool:
    """True when ``name`` is the parking folder's name."""
    return name == EMPTY_SUBFOLDERS_FOLDER


def parking_area_is_misplaced(folder: Path) -> bool:
    """True when ``folder`` is a parking area somewhere H2 does not allow one.

    The case H6 hoists: its parent is neither a month folder nor a group -- a
    leaf dated folder, or a taxonomy subfolder inside one.

    One sitting *above* its level -- directly under a year folder, say -- is
    not this and is not hoisted (H7): moving it down would mean deciding which
    month each folder in it belongs to, a different question that nobody has
    asked. That is why the test is "no month folder above it" rather than "not
    directly under one".
    """
    if not is_parking_area(folder.name):
        return False
    if month_folder_of(folder.parent) is None:
        return False                        # H7: above its level, or outside a tree
    return not is_parking_level(folder.parent)


def is_inside_parking_area(path: Path) -> bool:
    """True when an ancestor of ``path`` is the parking area.

    Parked dated folders are records, not live events. Restructuring passes
    must therefore stop at a parking area, wherever it sits, rather than
    offering what it holds to the grouper or treating those files as
    reconciliation subjects (H1/H5).
    """
    return any(is_parking_area(parent.name) for parent in Path(path).parents)


def free_versioned_name(folder: Path, name: str, reserved=None) -> Path:
    """Return a collision-free ``folder/name``, then ``name_2``, ``name_3``.

    ``reserved`` carries dry-run destinations which do not exist on disk yet,
    so several planned hoists cannot accidentally claim the same target.
    """
    reserved = set() if reserved is None else reserved
    candidate = folder / name
    index = 1
    while candidate.exists() or str(candidate).lower() in reserved:
        index += 1
        candidate = folder / f"{name}_{index}"
    reserved.add(str(candidate).lower())
    return candidate


@dataclass
class ParkingReport:
    """What an archive-wide parking-area normalization found and changed."""

    misplaced: int = 0
    entries_moved: int = 0
    shells_removed: int = 0
    left: int = 0
    errors: int = 0

    @property
    def needs_attention(self) -> bool:
        return bool(self.misplaced or self.errors)

    def summary(self) -> str:
        return (f"{self.misplaced} nested area(s), "
                f"{self.entries_moved} entr{'y' if self.entries_moved == 1 else 'ies'} moved, "
                f"{self.shells_removed} empty shell(s) removed, "
                f"{self.left} left, {self.errors} error(s)")


def _is_reparse_point(path: Path) -> bool:
    """The T4 refusal for a direct child about to be moved."""
    try:
        status = os.lstat(path)
    except OSError:
        return True
    return bool(getattr(status, "st_reparse_tag", 0) or os.path.islink(path))


def hoist_parking_areas(areas, log=lambda _message: None, move=None,
                        remove_empty=None, dry_run=False) -> ParkingReport:
    """Merge every misplaced parking area into the nearest allowed one (H2/H6).

    ``areas`` must be a safely discovered list of directories; deepest-first
    processing makes this recursive. Every direct entry is renamed into the
    parking area of the nearest month folder or group above it, collision names
    are versioned, and the source shell is removed only after it is verified
    (or, in a dry run, planned) empty.

    No recursive deletion is used. A reparse point, unreadable entry, failed
    move, or missing level leaves the source shell in place and is reported.
    """
    move = (lambda source, target: os.rename(source, target)) if move is None else move
    remove_empty = (lambda folder: folder.rmdir()) if remove_empty is None else remove_empty
    report = ParkingReport()
    reserved = set()

    sources = sorted(
        (Path(area) for area in areas if parking_area_is_misplaced(Path(area))),
        key=lambda path: (len(path.parts), str(path).lower()),
        reverse=True,
    )
    report.misplaced = len(sources)

    for source in sources:
        destination = parking_area_for(source)
        if destination is None:
            report.left += 1
            report.errors += 1
            log(f"! left {source}: no month folder or group above it (H2)")
            continue
        try:
            entries = sorted(source.iterdir(), key=lambda path: path.name.lower())
        except OSError as error:
            report.left += 1
            report.errors += 1
            log(f"! left {source}: cannot list it: {error}")
            continue

        failed = False
        for entry in entries:
            if _is_reparse_point(entry):
                failed = True
                report.left += 1
                report.errors += 1
                log(f"! left {entry}: reparse point not followed (T4)")
                continue
            target = free_versioned_name(destination, entry.name, reserved)
            try:
                move(entry, target)
            except Exception as error:
                failed = True
                report.left += 1
                report.errors += 1
                log(f"! could not hoist {entry} to {target}: {error}")
                continue
            report.entries_moved += 1
            log(f"* {entry} -> {target}")

        if failed:
            continue
        if not dry_run:
            try:
                if any(source.iterdir()):
                    report.left += 1
                    report.errors += 1
                    log(f"! left {source}: not empty after its entries moved")
                    continue
            except OSError as error:
                report.left += 1
                report.errors += 1
                log(f"! left {source}: cannot verify it is empty: {error}")
                continue
        try:
            remove_empty(source)
        except Exception as error:
            report.left += 1
            report.errors += 1
            log(f"! could not remove empty parking shell {source}: {error}")
            continue
        report.shells_removed += 1
        log(f"* removed empty parking shell {source}")

    return report
