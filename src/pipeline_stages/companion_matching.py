"""Matching companions to their subjects — the engine, with no pipeline in it.

Two jobs, and they are not the same job.

``reconcile_folder`` — **follow the representative.** When the grouper splits a
sorted event folder into named sub-events, only the top-level representative
images move; each shot's RAW original, sidecar and preview stay behind in the
event folder's taxonomy subdirs. This walks one event folder and sends each
companion after the representative that left, matched on **capture time**,
because the representative has been renamed since and its name no longer
resembles the companion's.

``place_companions`` — **put each companion where the standard says.** A sidecar
belongs in the ``__EXIF`` directly inside the folder holding its subject (X10),
a preview in that folder's ``__PREVIEWS`` (X13). This works on a whole tree and
matches on **name**, because a companion carries its subject's full name (X1),
which makes it exact where the other can only be careful. It gathers the whole
index before moving anything: a sidecar stranded in the wrong event folder is
only findable once every subject in the tree is known, and an ambiguous name is
only visible once you can count how many folders claim it.

Two callers, one implementation
-------------------------------
``companion_reconciliation.py`` wraps the first as a pipeline stage, running it
on the folders a live run just grouped. ``tools/restructure_archive.py`` runs
both over an existing archive, twice: once to heal what earlier passes stranded
and once to follow the representatives the GUI has just moved.

They need different things from it — the tool must be able to report without
writing (T3), must not prune during a dry run, and needs the project's retry
and chunk-size conventions on a share — so the writes and the reads this module
performs are parameters rather than imports: ``move``, ``checksum``, ``prune``.
That is the whole reason this module exists apart from the stage. A second
implementation of the matching, living in the tools directory and drifting away
from the one the pipeline uses, is exactly what T8 forbids.

This is a **leaf module** in the sense the standard means (T8): it imports
nothing from the project but other dependency-free modules — ``stamps``,
``grouping_names``, ``taxonomy`` and ``parking`` (which reads ``months``) — and
in particular nothing from ``src.core``. A maintenance tool can therefore load
it without dragging exiftool, the dashboard and the converters in behind it.

Every file lands in exactly one bucket of the returned report, and every file
that is *not* moved is named in the log, so a partial run can never look like a
clean one.
"""

import hashlib
import os
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from src.pipeline_stages.parking import \
    free_versioned_name, \
    parking_area_for
from src.pipeline_stages.grouping_names import \
    EMPTY_SUBFOLDERS_FOLDER, \
    extension_sets, \
    preview_extensions, \
    sidecar_extensions, \
    sidecar_subject_name
from src.pipeline_stages.stamps import \
    day_prefix, \
    leading_stamp_key, \
    stamp_keys
from src.pipeline_stages.taxonomy import \
    differing_name, \
    duplicate_name, \
    legacy_container_names, \
    legacy_container_targets, \
    taxonomy_subdir, \
    sidecar_dir_names, \
    sidecar_subdir, \
    strip_representative_suffixes, \
    taxonomy_dir_names

# Per-folder, per-kind cap on individual filenames written to the log, so one
# pathological folder cannot bury the rest of the run. Errors are never capped.
_MAX_REPORTED_PER_KIND = 20


def default_move(source: Path, target: Path) -> Path:
    """Move one file, creating the destination folder. The plain version.

    ``src.core.safe_move`` is this plus the project's retry convention, and the
    pipeline passes that in. This exists so the module has a working default
    and no caller is *obliged* to supply one.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    return Path(shutil.move(str(source), str(target)))


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
        strip_representative_suffixes(part)
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
                     log=lambda _msg: None, move=None,
                     prune: bool = True) -> ReconcileReport:
    """Move a folder's taxonomy companions to follow their representative images.

    ``move(source, target)`` performs each move and is the one thing this
    module does not decide for itself. The pipeline passes ``src.core.safe_move``
    so a dropped SMB handle is retried; a maintenance tool doing a dry run
    passes a recorder that writes nothing, which is what makes T3 ("report
    before writing") reachable without a second implementation of the matching.

    ``prune`` empties out the taxonomy folders left behind. A dry run turns it
    off, since removing a directory is still a write.
    """
    report = ReconcileReport()
    reporter = _Reporter(log)
    move = default_move if move is None else move

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

    # Index every companion by its shot key: key -> [(relative_dir, path)].
    # The relative dir is what the companion is re-created under at the
    # destination, so a sidecar in "__RAW/__EXIF" arrives in the sub-event's
    # "__RAW/__EXIF" rather than being flattened into its "__EXIF" (X10).
    sidecar_names = sidecar_dir_names(config)
    companions: dict[str, list[tuple[str, Path]]] = {}

    def collect(directory: Path, relative: str, descend: bool) -> None:
        for entry in _list_dir(directory, reporter):
            path = Path(entry.path)
            if not _is_file(entry, reporter):
                if not _is_dir(entry, reporter):
                    continue
                # A sidecar folder inside a media folder is the one legal nest
                # (X11): "__RAW/__EXIF" holds the RAWs' sidecars. Anything else
                # nested here is unexpected and is left alone, as before.
                if descend and entry.name in sidecar_names:
                    collect(path, f"{relative}/{entry.name}", descend=False)
                else:
                    reporter.note(
                        "nested",
                        f"- skipping nested folder {relative}/{entry.name} "
                        "(companions are expected to be files)",
                    )
                continue
            key = shot_key(entry.name)
            if key is None:
                report.unkeyed += 1
                reporter.note(
                    "unkeyed",
                    f"- left {relative}/{entry.name}: no date+time in the filename",
                )
                continue
            companions.setdefault(key, []).append((relative, path))

    for tax_dir in tax_dirs:
        # Only a media folder can hold a sidecar folder; __EXIF holds nothing
        # but sidecars (X12), so there is never a second level to descend into.
        collect(tax_dir, tax_dir.name, descend=tax_dir.name not in sidecar_names)
    if not companions:
        if prune:
            _prune_empty_taxonomy_dirs(tax_dirs, reporter)
        report.errors = reporter.error_count
        return report

    dest_by_key = _representative_index(event_folder, tax_names, reporter)

    for key, items in sorted(companions.items()):
        candidates = dest_by_key.get(key)
        if not candidates:
            report.unmatched += len(items)
            for relative, path in items:
                reporter.note(
                    "unmatched",
                    f"- left {relative}/{path.name}: no representative image "
                    "found in this or any sibling folder",
                )
            continue

        for relative, path in items:
            dest = _pick_destination(path.name, candidates, reporter)
            if dest == event_folder:
                # The representative never left (the user kept this group here),
                # so the companion is already where it belongs.
                report.in_place += 1
                continue
            target = dest.joinpath(*relative.split("/")) / path.name
            if target.exists():
                # Idempotent re-run or genuine clash: leave the original in place
                # rather than risk overwriting, but never silently.
                report.already_present += 1
                reporter.note(
                    "already-present",
                    f"- left {relative}/{path.name}: already present in "
                    f"{dest.name}/{relative}",
                )
                continue
            try:
                move(path, target)
            except Exception as error:
                # Broad on purpose: one unmovable file (locked by Dropbox, path
                # too long, shutil.Error) must not strand the rest of the folder.
                reporter.error(
                    f"could not move {relative}/{path.name} to {dest.name}/{relative}: {error}")
                continue
            report.moved += 1

    if prune:
        _prune_empty_taxonomy_dirs(tax_dirs, reporter)
    report.errors = reporter.error_count
    return report


def _prune_empty_taxonomy_dirs(tax_dirs: list[Path], reporter: _Reporter) -> None:
    # Deepest first, so emptying "__RAW/__EXIF" lets "__RAW" go in the same pass
    # rather than leaving a folder that is empty but for an empty child.
    for tax_dir in tax_dirs:
        nested = []
        try:
            nested = [child for child in tax_dir.iterdir() if child.is_dir()] \
                if tax_dir.is_dir() else []
        except OSError as error:
            reporter.error(f"could not read {tax_dir.name}: {error}")
        for child in nested + [tax_dir]:
            try:
                if child.is_dir() and not any(child.iterdir()):
                    child.rmdir()
            except OSError as error:
                reporter.error(f"could not remove empty {child.name}: {error}")


# --------------------------------------------------------------------------
# X10 -- a sidecar belongs beside its subject
# --------------------------------------------------------------------------



# --------------------------------------------------------------------------
# X10/X13 -- placing every companion beside its subject
# --------------------------------------------------------------------------
#
# Gather, then distribute. Two full passes over the tree rather than one
# folder-at-a-time walk:
#
#   1. index every subject (and, separately, every medium that ought to have a
#      sidecar at all), by full name and by stem, with the folder it lives in;
#   2. index every companion;
#   3. work out where each companion belongs and move it there.
#
# The reason for the shape is that step 3 needs the *whole* index to answer two
# questions a per-folder walk cannot: "is this subject somewhere else in the
# archive?" and "is this name ambiguous?". A sidecar stranded in the wrong event
# folder entirely is only findable once every subject in the tree is known.

# The two kinds of companion that live one level below their subject, each with
# the taxonomy key naming the folder it goes in. Both follow X10-X13; they are
# separated only because they land in different folders.
COMPANION_KINDS = (("exif", sidecar_extensions), ("previews", preview_extensions))


def default_checksum(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """MD5 of a file, read in chunks. The plain version.

    Injected the way ``move`` is, for the same reason: ``src.core.file_md5`` is
    this plus the project's config-driven chunk size, and the caller that has a
    config passes it in.
    """
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class PlacementReport:
    """What became of every companion, and of every medium that wants one.

    The companion buckets are exhaustive and mutually exclusive. ``renamed`` and
    ``across_folders`` describe moves that already counted in ``moved``, and are
    reported separately because they are the two kinds worth reading twice.
    """

    moved: int = 0
    renamed: int = 0
    across_folders: int = 0
    in_place: int = 0
    parked_duplicate: int = 0
    parked_differing: int = 0
    orphaned: int = 0
    ambiguous: int = 0
    errors: int = 0

    # The audit half: media indexed, and how many of them have no sidecar (X4).
    media: int = 0
    media_without_sidecar: int = 0
    missing_sidecars: list = None       # media Paths, resolved after tolerant matching

    # What the walk saw on its way past and did not act on: folders that fit
    # none of the shapes the standard allows, and legacy containers still to be
    # migrated. Lists, not counts, because the point is to name them.
    non_compliant: list = None           # [(path, reason)]
    legacy_containers: list = None       # [(path, taxonomy_key or None)]

    def __post_init__(self):
        self.non_compliant = [] if self.non_compliant is None else self.non_compliant
        self.legacy_containers = (
            [] if self.legacy_containers is None else self.legacy_containers)
        self.missing_sidecars = (
            [] if self.missing_sidecars is None else self.missing_sidecars)

    @property
    def seen(self) -> int:
        return (self.moved + self.in_place + self.parked_duplicate
                + self.parked_differing + self.orphaned + self.ambiguous
                + self.errors)

    @property
    def needs_attention(self) -> int:
        """Everything a person may want to look at afterwards."""
        return (self.parked_differing + self.orphaned + self.ambiguous
                + self.media_without_sidecar + self.errors)

    def summary(self) -> str:
        parts = [f"moved {self.moved}"]
        for label, value in (
            ("renamed onto X1", self.renamed),
            ("across folders", self.across_folders),
            ("already in place", self.in_place),
            ("parked as duplicates", self.parked_duplicate),
            ("parked as DIFFERING", self.parked_differing),
            ("no subject found", self.orphaned),
            ("subject ambiguous", self.ambiguous),
            ("media with no sidecar", self.media_without_sidecar),
            ("errors", self.errors),
        ):
            if value:
                parts.append(f"{value} {label}")
        return ", ".join(parts)

    def merge(self, other: "PlacementReport") -> None:
        for field in ("moved", "renamed", "across_folders", "in_place",
                      "parked_duplicate", "parked_differing", "orphaned",
                      "ambiguous", "errors", "media", "media_without_sidecar"):
            setattr(self, field, getattr(self, field) + getattr(other, field))
        self.non_compliant.extend(other.non_compliant)
        self.legacy_containers.extend(other.legacy_containers)
        self.missing_sidecars.extend(other.missing_sidecars)


def companion_kinds(config: dict) -> list[tuple[str, set[str]]]:
    """``[(taxonomy_key, extensions)]`` for every companion kind, from config."""
    return [(key, reader(config)) for key, reader in COMPANION_KINDS]


def _companion_kind(name: str, kinds: list[tuple[str, set[str]]]):
    """``(taxonomy_key, subject_name, extension)`` for a companion, else None."""
    for key, extensions in kinds:
        subject = sidecar_subject_name(name, extensions)
        if subject is not None:
            return key, subject, name[len(subject):]
    return None


@dataclass
class _Index:
    """Everything one pass over the trees found."""

    # A subject is any file that is not itself a companion: media, but also the
    # ".psd" in __EDITED and the ".xmp" beside it, which have sidecars too.
    # Only files inside a dated folder are indexed -- see ``index_trees``.
    subjects_by_name: dict = None        # name.lower() -> [(actual name, folder), ...]
    subjects_by_stem: dict = None        # stem.lower() -> [(name, folder), ...]
    # The media half, for the X4 audit: the files that *ought* to have a sidecar.
    media: list = None                   # [(name, folder), ...]
    companions: list = None              # [(path, folder, key, subject, ext)]
    # Folders that fit none of the shapes the standard allows, and the legacy
    # containers still waiting to be migrated. Reported, never acted on here.
    non_compliant: list = None           # [(path, reason)]
    legacy_containers: list = None       # [(path, taxonomy_key or None)]

    def __post_init__(self):
        for field in ("subjects_by_name", "subjects_by_stem"):
            if getattr(self, field) is None:
                setattr(self, field, {})
        for field in ("media", "companions", "non_compliant", "legacy_containers"):
            if getattr(self, field) is None:
                setattr(self, field, [])


def _folder_problem(name: str, inside_dated: bool, depth: int,
                    tax_names: set[str], sidecar_names: set[str],
                    legacy_names: set[str]) -> str | None:
    """Why ``name`` does not belong where it is, or None if it does.

    Deliberately shallow and forgiving. It answers "does this folder have one
    of the shapes the standard allows here", not "is this archive correct" --
    that is the fixing tool's job (section 7), and this is what a placement run
    happens to see on its way past.
    """
    if day_prefix(name):
        return None                       # a dated folder is legal at any level
    if name == EMPTY_SUBFOLDERS_FOLDER:
        return None                       # a holding area (H2)
    folded = name.casefold()
    if folded in legacy_names:
        return None                       # reported separately, as a migration
    if inside_dated:
        if folded in tax_names or folded in sidecar_names:
            return None                   # S2/X11 allow the nesting
        return "not a dated folder and not one of the allowed subfolders (S1)"
    if depth <= 0:
        # A child of the tree root: month folders live here, and so does the
        # year-level __DUPLICATES a run parks collision losers in. ``depth`` is
        # the *parent's* depth, so 0 means "directly under the root" -- one
        # deeper and we are under a month folder, where a name with no date is
        # the thing worth reporting.
        return None
    return "below a month folder but carries no date (N1) and is not a subfolder"


def index_trees(roots, config: dict, reporter: "_Reporter",
                skip_keys=()) -> _Index:
    """One walk over every root, sorting what it finds.

    **Only a dated folder holds source images.** A media file outside one is
    not indexed as a subject, however plausible its name: the archive's shape
    is what says which files are the archive's, and a stray JPG in a working
    folder must not become the answer to some sidecar's search. Such a folder
    is reported instead (see ``_folder_problem``).

    The format is read loosely, as the standard does: a leading `YYYY-MM-DD` is
    enough, with or without the weekday and the time. A day folder that never
    gained a time is still a day folder.

    ``skip_keys`` are left out of the walk entirely -- the parking folders,
    whose contents have already been dealt with. Without this the run after a
    parking run would find those files, fail to match the ``_DUPE_``-suffixed
    names against any subject, and report every one of them as orphaned.

    Reparse points are refused rather than followed (T4): this walk covers
    whole year trees, so a junction planted anywhere under one would otherwise
    take the index -- and then the moves -- somewhere else entirely.
    """
    kinds = [(key, extensions) for key, extensions in companion_kinds(config)
             if extensions]
    image_exts, video_exts = extension_sets(config)
    media_exts = image_exts | video_exts
    tax_names = {name.casefold() for name in taxonomy_dir_names(config)}
    sidecar_names = {name.casefold() for name in sidecar_dir_names(config)}
    legacy_names = {name.casefold() for name in legacy_container_names(config)}
    legacy_targets = legacy_container_targets(config)
    legacy_targets_folded = {
        name.casefold(): key for name, key in legacy_targets.items()
    }
    index = _Index()

    def walk(folder: Path, inside_dated: bool, depth: int) -> None:
        for entry in _list_dir(folder, reporter):
            path = Path(entry.path)
            try:
                if entry.is_symlink() or getattr(
                        entry.stat(follow_symlinks=False), "st_reparse_tag", 0):
                    reporter.note("reparse",
                                  f"? skipped {path}: reparse point not followed")
                    continue
            except OSError as error:
                reporter.error(f"could not stat {path}: {error}")
                continue
            try:
                is_directory = entry.is_dir(follow_symlinks=False)
            except OSError as error:
                reporter.error(f"could not stat {path}: {error}")
                continue

            if is_directory:
                if os.path.normcase(os.path.abspath(str(path))) in skip_keys:
                    continue
                problem = _folder_problem(entry.name, inside_dated, depth,
                                          tax_names, sidecar_names, legacy_names)
                if problem is not None:
                    index.non_compliant.append((path, problem))
                if entry.name.casefold() in legacy_names:
                    index.legacy_containers.append(
                        (path, legacy_targets_folded.get(entry.name.casefold())))
                if entry.name == EMPTY_SUBFOLDERS_FOLDER:
                    # H1/H5: a parking area is an archive of hollow folders,
                    # not a source tree, wherever it sits. Parked days must
                    # not re-enter companion reconciliation just because they
                    # still carry dated names.
                    continue
                walk(path, inside_dated or bool(day_prefix(entry.name)), depth + 1)
                continue

            if not _is_file(entry, reporter):
                continue

            found = _companion_kind(entry.name, kinds)
            if found is not None:
                # A sidecar is indexed wherever it lies. Being in the wrong
                # place is the condition this pass exists to repair, so
                # refusing to look outside a dated folder would hide exactly
                # the files it is looking for.
                key, subject, extension = found
                index.companions.append((path, folder, key, subject, extension))
                continue

            if not inside_dated:
                continue                  # only a dated folder holds subjects

            index.subjects_by_name.setdefault(
                entry.name.lower(), []).append((entry.name, folder))
            index.subjects_by_stem.setdefault(
                Path(entry.name).stem.lower(), []).append((entry.name, folder))
            if Path(entry.name).suffix.lower() in media_exts:
                index.media.append((entry.name, folder))

    for root in roots:
        root = Path(root)
        walk(root, bool(day_prefix(root.name)), 0)
    return index


def survey_trees(roots, config: dict, log=lambda _msg: None) -> _Index:
    """Walk the trees and report what is there, moving nothing.

    The public face of ``index_trees``, for a caller that wants the survey
    before it decides anything -- which legacy containers are waiting, which
    folders fit no allowed shape. Reads only.
    """
    return index_trees(roots, config, _Reporter(log))


def _free_parking_name(folder: Path, stem: str, extension: str,
                       digest: str, differs: bool) -> Path:
    """A name in ``folder`` nothing else holds, following F4.

    Numbered rather than overwritten: two events can each strand a sidecar of
    the same name, and both belong in the report.
    """
    namer = differing_name if differs else duplicate_name
    index = 1
    while True:
        candidate = folder / namer(stem, digest, index, extension)
        if not candidate.exists():
            return candidate
        index += 1


def _path_key(path: Path) -> str:
    """Case-insensitive absolute key, matching Windows archive semantics."""
    return os.path.normcase(os.path.abspath(str(path)))


def _distinct_subjects(candidates) -> list[tuple[str, Path]]:
    """De-duplicate ``(actual name, folder)`` candidates without losing case."""
    distinct = {}
    for name, folder in candidates:
        distinct[(name.lower(), _path_key(folder))] = (name, Path(folder))
    return list(distinct.values())


def _subject_candidates(index: _Index, subject_name: str, sidecar_folder: Path,
                        key: str, config: dict) -> tuple[list[tuple[str, Path]], bool]:
    """Resolve canonical and historical companion names to possible subjects.

    The historical ``._exif`` writer omitted the media extension, so a sidecar
    named ``shot._exif`` has to fall back to the subject stem. When both a JPEG
    and its RAW share that stem, position resolves the otherwise ambiguous
    pair: ``<event>/__EXIF`` belongs to the top-level JPEG, while
    ``<event>/__RAW/__EXIF`` belongs to the RAW (X10).

    Returns ``(candidates, used_stem_form)``. A caller still refuses more than
    one candidate; location narrows a match but never guesses between peers.
    """
    direct = _distinct_subjects(
        index.subjects_by_name.get(subject_name.lower(), []))
    if direct:
        return direct, False

    stem = _distinct_subjects(index.subjects_by_stem.get(subject_name.lower(), []))
    if not stem:
        return [], True
    local = [
        candidate for candidate in stem
        if _path_key(sidecar_subdir(candidate[1], config, key))
        == _path_key(sidecar_folder)
    ]
    return (local or stem), True


def place_companions(roots, config: dict, duplicates_for,
                     log=lambda _msg: None, move=None, checksum=None,
                     prune: bool = True) -> PlacementReport:
    r"""Put every sidecar and preview under ``roots`` in the folder that belongs to it.

    Standard X10 for sidecars, X13 for previews, and they say the same thing: a
    companion sits in ``__EXIF`` (or ``__PREVIEWS``) *directly inside* the
    folder holding its subject -- never two levels up, never in one further
    along the tree. A RAW in ``__RAW`` keeps its sidecar in ``__RAW\__EXIF``; a
    still at the top level keeps its own in the dated folder's ``__EXIF``.

    **Gather, then distribute.** ``roots`` is every tree of the run at once,
    not one event folder, and the index is built before anything moves. A
    sidecar is looked for **anywhere in the target, at any depth** -- that is
    what lets one stranded in a different event folder, or a different year,
    find its subject, and what makes an ambiguous name visible instead of
    guessed at. Neither is answerable while walking one folder at a time.

    **Only a dated folder holds subjects.** A media file outside one is not a
    candidate however plausible its name -- see ``index_trees``.

    ``duplicates_for(folder)`` returns where a collision loser from that folder
    should be parked, so a run over several year trees parks each year's losers
    under that year rather than pooling them.

    Two ways a companion names its subject, tried in that order:

    1. **X1** -- the subject's full name with an extension appended,
       "clip.mp4._exif", "clip.mp4.thm". A direct lookup, and unambiguous.
    2. **Historical stem form** -- the subject's *stem* with the companion's own
       extension, "shot._exif" or "GX010042.LRV" beside "GX010042.MP4". Older
       EXIF extraction omitted the media extension, and previews arrive this
       way from cameras. Both are resolved by stem and renamed onto X1. If a
       JPEG and RAW share the stem, their X10 location selects the one the
       sidecar can describe; otherwise a non-unique stem is refused.

    **When something already holds the destination name**, the two files are
    compared by MD5 rather than one being picked:

      * identical -- the incoming copy is redundant, and goes to
        ``duplicates_root`` as ``<name>_DUPE_<md5>_<n>`` (F4);
      * different -- one of them is wrong and which is not knowable here, so the
        incoming copy goes to the same place as
        ``<name>_DIFFERS_<md5>_<n>`` and is counted separately. Nothing is
        overwritten and nothing is deleted (T1, T2); the file at the destination
        is left exactly as it was.

    A companion whose subject is nowhere in the tree is **left exactly where it
    is** and counted as orphaned. It is the only surviving record that the
    subject ever existed (X3), and moving it on a guess would lose the one thing
    it still says. That is what ``e`` reports (X4).

    The report also carries the other half of the audit: how many media files
    the tree holds and how many of them have no sidecar at all.

    ``move``, ``checksum`` and ``prune`` are the writes and the reads this
    module does not decide for itself -- see the module docstring.
    """
    report = PlacementReport()
    reporter = _Reporter(log)
    move = default_move if move is None else move
    checksum = default_checksum if checksum is None else checksum

    roots = [Path(one) for one in roots]
    missing = [one for one in roots if not one.is_dir()]
    for one in missing:
        reporter.error(f"{one} is gone, no companions placed")
    roots = [one for one in roots if one not in missing]
    if not roots:
        report.errors = reporter.error_count
        return report

    if not any(extensions for _key, extensions in companion_kinds(config)):
        return report          # an archive configured to keep neither

    skip_keys = {os.path.normcase(os.path.abspath(str(duplicates_for(one))))
                 for one in roots}
    index = index_trees(roots, config, reporter, skip_keys)
    report.media = len(index.media)
    report.non_compliant = list(index.non_compliant)
    report.legacy_containers = list(index.legacy_containers)

    keeps_exif_sidecars = bool(sidecar_extensions(config))
    covered = set()
    emptied: list[Path] = []

    for path, folder, key, subject_name, extension in index.companions:
        candidates, used_stem = _subject_candidates(
            index, subject_name, folder, key, config)
        if not candidates:
            report.orphaned += 1
            reporter.note("orphaned",
                          f"- left {path}: {subject_name} is nowhere in the tree")
            continue
        if len(candidates) > 1:
            report.ambiguous += 1
            reporter.note(
                "ambiguous",
                f"? left {path}: {len(candidates)} files "
                f"{'share the stem' if used_stem else 'claim the name'} "
                f"{subject_name}, so its subject is not knowable",
            )
            continue

        media_name, subject_folder = candidates[0]
        wanted_name = media_name + extension.lower()
        if key == "exif":
            covered.add((media_name.lower(), _path_key(subject_folder)))
        wanted = Path(sidecar_subdir(subject_folder, config, key))
        destination = wanted / wanted_name
        same_folder = _path_key(wanted) == _path_key(folder)
        if same_folder and wanted_name == path.name:
            report.in_place += 1
            continue

        # A case-only normalization names the same directory entry on Windows;
        # it is a rename, not a collision with a second file.
        if _path_key(destination) == _path_key(path):
            try:
                move(path, destination)
            except Exception as error:
                reporter.error(f"could not rename {path} to {wanted_name}: {error}")
                continue
            report.moved += 1
            report.renamed += 1
            continue

        if destination.exists():
            try:
                digest = checksum(path)
                same = digest == checksum(destination)
            except OSError as error:
                reporter.error(
                    f"could not checksum {path} against {destination}: {error}")
                continue
            parked = _free_parking_name(
                duplicates_for(subject_folder), subject_name, extension,
                digest[:8], not same)
            try:
                move(path, parked)
            except Exception as error:
                reporter.error(f"could not park {path}: {error}")
                continue
            if same:
                report.parked_duplicate += 1
                reporter.note(
                    "duplicate",
                    f"= {path.name}: identical to the one already in "
                    f"{wanted.name}, parked as {parked.name}",
                )
            else:
                report.parked_differing += 1
                reporter.note(
                    "differing",
                    f"! {path.name}: DIFFERENT bytes from the one already in "
                    f"{wanted.name}, parked as {parked.name} -- both kept, "
                    "neither is knowably right",
                )
            if folder not in emptied:
                emptied.append(folder)
            continue

        try:
            move(path, destination)
        except Exception as error:
            # Broad on purpose: one unmovable file must not strand the rest.
            reporter.error(f"could not move {path} to {wanted}: {error}")
            continue
        report.moved += 1
        if wanted_name != path.name:
            report.renamed += 1
        if _dated_ancestor(folder) != _dated_ancestor(subject_folder):
            report.across_folders += 1
            reporter.note(
                "across",
                f"> {path.name}: moved out of {_dated_ancestor(folder)} into "
                f"{_dated_ancestor(subject_folder)}",
            )
        if folder not in emptied:
            emptied.append(folder)

    # Audit only after tolerant matching. A stem-form or case-variant sidecar
    # covers the real media just as fully as an already-canonical X1 name; the
    # move above normalizes its spelling for the next run.
    if keeps_exif_sidecars:
        for name, folder in index.media:
            if (name.lower(), _path_key(folder)) not in covered:
                report.missing_sidecars.append(Path(folder) / name)
    report.media_without_sidecar = len(report.missing_sidecars)

    if prune and emptied:
        # Only the folders this pass took files out of: one that was already
        # empty is somebody else's business.
        _prune_empty_taxonomy_dirs(emptied, reporter)
    report.errors = reporter.error_count
    return report


def _dated_ancestor(folder: Path) -> str:
    """The name of the dated folder ``folder`` sits in, for reporting.

    A companion in "<day>/__RAW/__EXIF" and its subject in "<day>/__RAW" are in
    the same event; only a move that leaves the day is worth calling out.
    """
    for candidate in [folder, *folder.parents]:
        if day_prefix(candidate.name):
            return candidate.name
    return folder.name


# --------------------------------------------------------------------------
# Migrating the legacy containers
# --------------------------------------------------------------------------

@dataclass
class MigrationReport:
    """What became of the pre-"__" containers the legacy CLI wrote."""

    renamed: int = 0
    merged: int = 0
    files_moved: int = 0
    parked: int = 0
    left: int = 0
    errors: int = 0

    @property
    def seen(self) -> int:
        return self.renamed + self.merged + self.left + self.errors

    def summary(self) -> str:
        parts = [f"renamed {self.renamed}"]
        for label, value in (("merged", self.merged),
                             ("files moved", self.files_moved),
                             ("parked empty", self.parked),
                             ("left alone", self.left),
                             ("errors", self.errors)):
            if value:
                parts.append(f"{value} {label}")
        return ", ".join(parts)

    def merge(self, other: "MigrationReport") -> None:
        for field in ("renamed", "merged", "files_moved", "parked", "left",
                      "errors"):
            setattr(self, field, getattr(self, field) + getattr(other, field))


def _folder_is_empty(folder: Path) -> bool:
    """True when ``folder`` holds no file anywhere beneath it."""
    try:
        for _directory, _subdirs, names in os.walk(folder):
            if names:
                return False
    except OSError:
        return False
    return True


def migrate_legacy_containers(containers, config: dict, duplicates_for,
                              log=lambda _msg: None, move=None,
                              checksum=None) -> MigrationReport:
    r"""Move what the legacy CLI wrote into the folders it is called now.

    ``##   EXIFs   ##`` becomes ``__EXIF`` and ``##   RAWs   ##`` becomes
    ``__RAW``. Two ways, whichever is safe:

      * the modern folder does not exist yet -- the container is **renamed**,
        one atomic operation that cannot half-finish and cannot lose a file;
      * it does exist -- each file is **moved across** individually, and a name
        already taken is settled by checksum exactly as companion placement
        settles one: identical is parked as ``_DUPE_``, different as
        ``_DIFFERS_``. Nothing is overwritten (T2) and nothing is deleted (T1).

    A container left **absolutely empty** -- no file anywhere beneath it, which
    is checked rather than assumed -- is then parked in the
    ``__EMPTY_SUBFOLDERS`` **under its month folder** (H2), numbered ``_2``,
    ``_3`` … when that name is taken. One still holding anything is left
    exactly where it is and reported: a folder that would not empty is a
    question, not a job.

    Containers with no modern equivalent -- ``old_EXIF`` and the three "FILES"
    holders -- are counted as left alone. Where their contents belong is a
    decision for a person, and this makes none of it.

    ``containers`` is ``[(path, taxonomy_key or None)]``, as ``index_trees``
    collects them. ``duplicates_for(folder)`` says where a collision loser is
    parked -- the same place companion placement parks one, so the two passes
    do not scatter losers into two different holding areas.
    """
    report = MigrationReport()
    reporter = _Reporter(log)
    move = default_move if move is None else move
    checksum = default_checksum if checksum is None else checksum
    reserved_parking_names = set()

    for container, key in containers:
        container = Path(container)
        if key is None:
            report.left += 1
            reporter.note(
                "unmapped",
                f"- left {container}: no modern folder corresponds to it")
            continue
        if not container.is_dir():
            continue                      # an earlier pass already took it

        destination = Path(taxonomy_subdir(container.parent, config, key))
        if not destination.exists():
            try:
                move(container, destination)
            except Exception as error:
                reporter.error(f"could not rename {container}: {error}")
                continue
            report.renamed += 1
            reporter.note("renamed",
                          f"* {container.name} -> {destination.name}")
            continue

        moved_here = _merge_container(container, destination,
                                      duplicates_for(container.parent),
                                      move, checksum, report, reporter)
        if moved_here:
            report.merged += 1
        _park_if_empty(container, report, reporter, move, reserved_parking_names)

    report.errors = reporter.error_count
    return report


def _merge_container(container: Path, destination: Path, parking: Path,
                     move, checksum, report: "MigrationReport",
                     reporter: "_Reporter") -> bool:
    """Move every file out of ``container`` into ``destination``. Returns moved-any."""
    moved_any = False
    for directory, _subdirs, names in os.walk(container):
        relative = Path(directory).relative_to(container)
        for name in sorted(names):
            source = Path(directory) / name
            target = destination / relative / name
            if target.exists():
                try:
                    digest = checksum(source)
                    same = digest == checksum(target)
                except OSError as error:
                    reporter.error(f"could not checksum {source}: {error}")
                    continue
                stem, extension = os.path.splitext(name)
                parked = _free_parking_name(
                    parking, stem, extension, digest[:8], not same)
                try:
                    move(source, parked)
                except Exception as error:
                    reporter.error(f"could not park {source}: {error}")
                    continue
                report.files_moved += 1
                moved_any = True
                reporter.note(
                    "collision",
                    ("= " if same else "! ")
                    + f"{name}: {'identical to' if same else 'DIFFERENT from'} "
                      f"the one already in {destination.name}, "
                      f"parked as {parked.name}")
                continue
            try:
                move(source, target)
            except Exception as error:
                reporter.error(f"could not move {source}: {error}")
                continue
            report.files_moved += 1
            moved_any = True
    return moved_any


def _park_if_empty(container: Path, report: "MigrationReport",
                   reporter: "_Reporter", move, reserved=None) -> None:
    """Park an emptied container in its month folder's ``__EMPTY_SUBFOLDERS``."""
    if not container.is_dir():
        return
    if not _folder_is_empty(container):
        report.left += 1
        reporter.note(
            "not-empty",
            f"- left {container}: still holds files after the migration")
        return
    parking = parking_area_for(container)
    if parking is None:
        report.left += 1
        reporter.error(
            f"could not park empty {container}: no conforming month folder above it (H2)")
        return
    target = free_versioned_name(parking, container.name, reserved)
    try:
        move(container, target)
    except Exception as error:
        reporter.error(f"could not park empty {container}: {error}")
        return
    report.parked += 1
    reporter.note("parked",
                  f"* {container.name} was left empty, parked as "
                  f"{EMPTY_SUBFOLDERS_FOLDER}/{target.name}")
