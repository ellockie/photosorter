"""Sort related files after screenshot grouping.

When the grouper GUI splits a sorted event folder (e.g.
"2026-07-18_(Sat) - __TO_SPLIT__(…)") into named sub-event folders, only the
top-level representative images move; each shot's RAW original, EXIF sidecar,
video, etc. stay behind in the event folder's taxonomy subdirs (__RAW, __EXIF,
__VIDEOS, …). This stage reunites them: for every companion file it finds the
sub-event folder that received the matching representative image (matched by the
leading date+time in the filename) and moves the companion into the same-named
taxonomy subdir there. Nothing is ever deleted; companions with no located
representative (e.g. videos that never appeared in the grouper) are left in
place and reported.

Every companion file lands in exactly one bucket of the returned report — moved,
already_present, in_place, unmatched, unkeyed or errors — and every file that is
*not* moved is named in the log, so a partial run can never look like a clean
one.
"""

import os
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.pipeline_stages.stamps import \
    leading_stamp_key, \
    stamp_keys
from src.pipeline_stages.taxonomy import DEFAULT_TAXONOMY
from src.pipeline_stages.grouping_names import TO_SPLIT_MARKER as _TO_SPLIT_MARKER

# Per-folder, per-kind cap on individual filenames written to the log, so one
# pathological folder cannot bury the rest of the run. Errors are never capped.
_MAX_REPORTED_PER_KIND = 20


def shot_key(name: str) -> str | None:
    """The normalized YYYYMMDDHHMMSS key a companion filename opens with.

    Companions are named by this pipeline, so their own stamp always leads.
    """
    return leading_stamp_key(name)


def representative_keys(name: str) -> list[str]:
    """Every shot key a representative image can legitimately answer to.

    Normally just the leading stamp. But the grouper may *prefix* a file with a
    timestamp of its own and push the Photosorter name into trailing text
    ("2026-07-19__21.29.04__SCR__2026-07-19_(Sun)_15.37.10__f1.7…"). The sidecar
    in __EXIF still carries only the original stamp, so indexing a
    representative under every stamp in its name is what keeps the two
    matchable — without it exactly those companions are stranded.
    """
    return stamp_keys(name)


def taxonomy_dir_names(config: dict) -> set[str]:
    names = set(DEFAULT_TAXONOMY.values())
    names.update((config.get("taxonomy") or {}).values())
    return names


@dataclass
class ReconcileReport:
    """Disposition of every companion file examined in one event folder.

    The buckets are exhaustive and mutually exclusive: a companion is either
    moved, found already present at the destination, deliberately left because
    its representative never left this folder, left because no representative
    could be located, or left because its name carries no date+time key.
    `errors` counts every failure logged during the pass — a failed move, an
    unreadable folder, a vanished event folder — so a run that could not do all
    of its work never reports a clean total.
    """

    moved: int = 0
    already_present: int = 0
    in_place: int = 0
    unmatched: int = 0
    unkeyed: int = 0
    errors: int = 0

    @property
    def seen(self) -> int:
        return (self.moved + self.already_present + self.in_place
                + self.unmatched + self.unkeyed + self.errors)

    @property
    def left_behind(self) -> int:
        """Companions that stayed put for a reason the user may want to act on."""
        return self.already_present + self.unmatched + self.unkeyed

    def summary(self) -> str:
        parts = [f"moved {self.moved}"]
        for label, value in (
            ("already at destination", self.already_present),
            ("representative still here", self.in_place),
            ("no representative found", self.unmatched),
            ("no date in name", self.unkeyed),
            ("errors", self.errors),
        ):
            if value:
                parts.append(f"{value} {label}")
        return ", ".join(parts)

    def merge(self, other: "ReconcileReport") -> None:
        self.moved += other.moved
        self.already_present += other.already_present
        self.in_place += other.in_place
        self.unmatched += other.unmatched
        self.unkeyed += other.unkeyed
        self.errors += other.errors


class _Reporter:
    """Logs individual problem files, capped per kind (errors uncapped)."""

    def __init__(self, log):
        self._log = log
        self._counts: dict[str, int] = defaultdict(int)

    def note(self, kind: str, message: str, capped: bool = True) -> None:
        self._counts[kind] += 1
        count = self._counts[kind]
        if not capped or count <= _MAX_REPORTED_PER_KIND:
            self._log(f"  {message}")
        elif count == _MAX_REPORTED_PER_KIND + 1:
            self._log(f"  … more '{kind}' messages for this folder suppressed")

    def error(self, message: str) -> None:
        self.note("error", f"! {message}", capped=False)

    @property
    def error_count(self) -> int:
        """Every failure logged, including unreadable folders and failed stats —
        the stage's error total is taken from here so nothing goes uncounted."""
        return self._counts["error"]


def _list_dir(directory: Path, reporter: _Reporter) -> list[os.DirEntry]:
    """Immediate entries of a directory; an unreadable directory is reported."""
    try:
        with os.scandir(directory) as entries:
            return list(entries)
    except OSError as error:
        reporter.error(f"could not read {directory}: {error}")
        return []


def _is_file(entry: os.DirEntry, reporter: _Reporter) -> bool:
    try:
        return entry.is_file()
    except OSError as error:
        reporter.error(f"could not stat {entry.path}: {error}")
        return False


def _is_dir(entry: os.DirEntry, reporter: _Reporter) -> bool:
    try:
        return entry.is_dir()
    except OSError as error:
        reporter.error(f"could not stat {entry.path}: {error}")
        return False


def _common_prefix_len(left: str, right: str) -> int:
    limit = min(len(left), len(right))
    index = 0
    while index < limit and left[index] == right[index]:
        index += 1
    return index


# The "_RAW"/"_EXT"/"_EDT" markers apply_representative_suffixes() appends to a
# representative's stem; stripped so a representative and its RAW original
# tokenize alike.
_REPRESENTATIVE_SUFFIXES = re.compile(r"(?:_(?:RAW|EXT|EDT))+$")


def _name_tokens(name: str) -> set[str]:
    """The "__"-separated parts of a filename, normalized for comparison.

    Photosorter names one shot's files from the same parts — datetime, aperture,
    exposure, camera symbol — but in a different order and with different
    markers per taxonomy kind ("…__RAW__f8.0__6D.CR2" against the
    representative "…__f8.0__6D_RAW.JPG"). Comparing the parts as a set matches
    them where a plain prefix comparison cannot.
    """
    stem = Path(name).stem
    return {
        _REPRESENTATIVE_SUFFIXES.sub("", part)
        for part in stem.split("__")
        if part
    }


def _representative_index(event_folder: Path, tax_names: set[str],
                          reporter: _Reporter) -> dict[str, list[tuple[Path, str]]]:
    """Map each shot key to the folders holding a matching representative image.

    Returns key -> [(folder, representative filename), …] covering the event
    folder itself (a group the user chose to keep in place) and every sibling of
    it. Siblings are NOT filtered by name: the grouper names a sub-event after
    its *earliest* file, so a group running past the day boundary lands under
    the next day's date, and a group the user leaves unsplit lands in a fresh
    "__TO_SPLIT__" sibling. Filtering on either would strand exactly those
    companions. The shot key carries a full date+time, so cross-folder false
    matches are not a concern.
    """
    candidates: dict[str, list[tuple[Path, str]]] = {}

    def index_folder(folder: Path) -> None:
        for entry in _list_dir(folder, reporter):
            if not _is_file(entry, reporter):
                continue
            for key in representative_keys(entry.name):
                entries = candidates.setdefault(key, [])
                if (folder, entry.name) not in entries:
                    entries.append((folder, entry.name))

    index_folder(event_folder)
    for entry in _list_dir(event_folder.parent, reporter):
        if not _is_dir(entry, reporter):
            continue
        sibling = Path(entry.path)
        if sibling == event_folder or entry.name in tax_names:
            continue
        index_folder(sibling)

    return candidates


def _pick_destination(companion_name: str, candidates: list[tuple[Path, str]],
                      reporter: _Reporter) -> Path:
    """Choose which sub-event folder a companion belongs to.

    Normally there is one candidate. Burst shots can share a date+time key down
    to the second and end up in different sub-events, so ties are broken by how
    many filename parts the companion shares with each representative (the
    aperture/exposure/camera symbols), then by common prefix, then
    deterministically by folder name. A genuine tie across folders is logged
    rather than silently guessed at.
    """
    if len(candidates) == 1:
        return candidates[0][0]

    tokens = _name_tokens(companion_name)

    def score(rep_name: str) -> tuple[int, int]:
        return (len(tokens & _name_tokens(rep_name)),
                _common_prefix_len(companion_name, rep_name))

    ranked = sorted(
        candidates,
        key=lambda item: (tuple(-value for value in score(item[1])), str(item[0]), item[1]),
    )
    best_folder, best_name = ranked[0]
    best_score = score(best_name)
    tied = {folder for folder, name in ranked if score(name) == best_score}
    if len(tied) > 1:
        reporter.note(
            "ambiguous",
            f"? {companion_name} matches {len(tied)} sub-events equally, "
            f"using {best_folder.name}",
        )
    return best_folder


def reconcile_folder(event_folder: Path, config: dict,
                     log=lambda _msg: None) -> ReconcileReport:
    """Move a folder's taxonomy companions to follow their representative images."""
    report = ReconcileReport()
    reporter = _Reporter(log)

    if not event_folder.is_dir():
        reporter.error(
            f"{event_folder} is gone — renamed or removed after grouping, nothing reconciled")
        report.errors = reporter.error_count
        return report

    tax_names = taxonomy_dir_names(config)
    tax_dirs = [
        Path(entry.path)
        for entry in _list_dir(event_folder, reporter)
        if entry.name in tax_names and _is_dir(entry, reporter)
    ]
    if not tax_dirs:
        report.errors = reporter.error_count
        return report

    # Index every companion by its shot key: key -> [(taxonomy_dir_name, path)].
    companions: dict[str, list[tuple[str, Path]]] = {}
    for tax_dir in tax_dirs:
        for entry in _list_dir(tax_dir, reporter):
            path = Path(entry.path)
            if not _is_file(entry, reporter):
                if _is_dir(entry, reporter):
                    reporter.note(
                        "nested",
                        f"- skipping nested folder {tax_dir.name}/{entry.name} "
                        "(companions are expected to be files)",
                    )
                continue
            key = shot_key(entry.name)
            if key is None:
                report.unkeyed += 1
                reporter.note(
                    "unkeyed",
                    f"- left {tax_dir.name}/{entry.name}: no date+time in the filename",
                )
                continue
            companions.setdefault(key, []).append((tax_dir.name, path))
    if not companions:
        _prune_empty_taxonomy_dirs(tax_dirs, reporter)
        report.errors = reporter.error_count
        return report

    dest_by_key = _representative_index(event_folder, tax_names, reporter)

    for key, items in sorted(companions.items()):
        candidates = dest_by_key.get(key)
        if not candidates:
            report.unmatched += len(items)
            for tax_name, path in items:
                reporter.note(
                    "unmatched",
                    f"- left {tax_name}/{path.name}: no representative image "
                    "found in this or any sibling folder",
                )
            continue

        for tax_name, path in items:
            dest = _pick_destination(path.name, candidates, reporter)
            if dest == event_folder:
                # The representative never left (the user kept this group here),
                # so the companion is already where it belongs.
                report.in_place += 1
                continue
            target = dest / tax_name / path.name
            if target.exists():
                # Idempotent re-run or genuine clash: leave the original in place
                # rather than risk overwriting, but never silently.
                report.already_present += 1
                reporter.note(
                    "already-present",
                    f"- left {tax_name}/{path.name}: already present in "
                    f"{dest.name}/{tax_name}",
                )
                continue
            try:
                safe_move(path, target)
            except Exception as error:
                # Broad on purpose: one unmovable file (locked by Dropbox, path
                # too long, shutil.Error) must not strand the rest of the folder.
                reporter.error(
                    f"could not move {tax_name}/{path.name} to {dest.name}/{tax_name}: {error}")
                continue
            report.moved += 1

    _prune_empty_taxonomy_dirs(tax_dirs, reporter)
    report.errors = reporter.error_count
    return report


def _prune_empty_taxonomy_dirs(tax_dirs: list[Path], reporter: _Reporter) -> None:
    for tax_dir in tax_dirs:
        try:
            if tax_dir.is_dir() and not any(tax_dir.iterdir()):
                tax_dir.rmdir()
        except OSError as error:
            reporter.error(f"could not remove empty {tax_dir.name}: {error}")


class CompanionReconciliationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="companion-reconciliation",
            display_name="Companion Reconciliation",
            dependencies=("grouping-review",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        settings = context.config.get("companion_reconciliation", {})
        context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)

        if not settings.get("enabled", False):
            context.log("Companion reconciliation disabled, skipping")
            return context

        folders = list(context.screenshot_grouped_folders)
        if not folders:
            context.log("No grouped folders to reconcile")
            return context

        totals = ReconcileReport()
        for folder in folders:
            try:
                report = reconcile_folder(folder, context.config, context.log)
            except Exception as error:  # never abandon the remaining folders
                totals.errors += 1
                context.log(f"  ! reconciling {folder.name} failed: {error!r}")
                continue
            if report.seen:
                context.log(f"Reconciled {folder.name}: {report.summary()}")
            totals.merge(report)

        context.counters["companions_reconciled"] += totals.moved
        context.counters["companions_unmatched"] += totals.unmatched
        context.counters["companions_left_behind"] += totals.left_behind
        context.counters["companions_reconcile_errors"] += totals.errors
        context.set_stage_stats(
            self.stage_id,
            inputs=totals.seen,
            outputs=totals.moved,
            errors=totals.errors,
        )
        context.log(
            f"Reconciled {totals.moved} companion file(s) across {len(folders)} folder(s)"
            + (f"; {totals.left_behind} left behind" if totals.left_behind else "")
            + (f"; {totals.errors} error(s)" if totals.errors else "")
        )
        return context
