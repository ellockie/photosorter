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
nothing from the project but the other leaf modules — ``stamps``,
``grouping_names`` and ``taxonomy`` — and in particular nothing from
``src.core``. A maintenance tool can therefore load it without dragging
exiftool, the dashboard and the converters in behind it.

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

from src.pipeline_stages.grouping_names import \
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
    """Everything one pass over the tree found."""

    # A subject is any file that is not itself a companion: media, but also the
    # ".psd" in __EDITED and the ".xmp" beside it, which have sidecars too.
    subjects_by_name: dict = None        # name.lower() -> [folder, ...]
    subjects_by_stem: dict = None        # stem.lower() -> [(name, folder), ...]
    # The media half, for the X4 audit: the files that *ought* to have a sidecar.
    media: list = None                   # [(name, folder), ...]
    companions: list = None              # [(path, folder, key, subject, ext)]

    def __post_init__(self):
        self.subjects_by_name = {} if self.subjects_by_name is None else self.subjects_by_name
        self.subjects_by_stem = {} if self.subjects_by_stem is None else self.subjects_by_stem
        self.media = [] if self.media is None else self.media
        self.companions = [] if self.companions is None else self.companions


def index_tree(root: Path, config: dict, reporter: "_Reporter",
               skip: Path | None = None) -> _Index:
    """One walk over ``root``, sorting every file into subject or companion.

    ``skip`` is left out of the walk entirely -- it is the parking folder, and
    what is in there has already been dealt with. Without this the run after a
    parking run would find those files, fail to match the ``_DUPE_``-suffixed
    names against any subject, and report every one of them as orphaned.

    Reparse points are refused rather than followed (T4): this walk covers a
    whole year tree, so a junction planted anywhere under it would otherwise
    take the index -- and then the moves -- somewhere else entirely.
    """
    skip_key = os.path.normcase(os.path.abspath(str(skip))) if skip else None
    kinds = [(key, extensions) for key, extensions in companion_kinds(config)
             if extensions]
    image_exts, video_exts = extension_sets(config)
    media_exts = image_exts | video_exts
    index = _Index()

    def walk(folder: Path) -> None:
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
                if entry.is_dir(follow_symlinks=False):
                    if skip_key is None or os.path.normcase(
                            os.path.abspath(str(path))) != skip_key:
                        walk(path)
                    continue
            except OSError as error:
                reporter.error(f"could not stat {path}: {error}")
                continue
            if not _is_file(entry, reporter):
                continue

            found = _companion_kind(entry.name, kinds)
            if found is not None:
                key, subject, extension = found
                index.companions.append((path, folder, key, subject, extension))
                continue

            index.subjects_by_name.setdefault(entry.name.lower(), []).append(folder)
            index.subjects_by_stem.setdefault(
                Path(entry.name).stem.lower(), []).append((entry.name, folder))
            if Path(entry.name).suffix.lower() in media_exts:
                index.media.append((entry.name, folder))

    walk(root)
    return index


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


def place_companions(root: Path, config: dict, duplicates_root: Path,
                     log=lambda _msg: None, move=None, checksum=None,
                     prune: bool = True) -> PlacementReport:
    r"""Put every sidecar and preview under ``root`` in the folder that belongs to it.

    Standard X10 for sidecars, X13 for previews, and they say the same thing: a
    companion sits in ``__EXIF`` (or ``__PREVIEWS``) *directly inside* the
    folder holding its subject -- never two levels up, never in one further
    along the tree. A RAW in ``__RAW`` keeps its sidecar in ``__RAW\__EXIF``; a
    still at the top level keeps its own in the dated folder's ``__EXIF``.

    **Gather, then distribute.** ``root`` is a whole tree, not one event folder,
    and the index is built before anything moves. That is what lets a sidecar
    stranded in a different event folder entirely find its subject, and what
    makes an ambiguous name visible instead of guessed at -- neither is
    answerable while walking one folder at a time.

    Two ways a companion names its subject, tried in that order:

    1. **X1** -- the subject's full name with an extension appended,
       "clip.mp4._exif", "clip.mp4.thm". A direct lookup, and unambiguous.
    2. **Camera form** -- the subject's *stem* with the companion's own
       extension, "GX010042.LRV" beside "GX010042.MP4". Nothing in the pipeline
       writes this and nothing has ever renamed it, so it is what a preview
       actually looks like on disk. Resolved by stem, and renamed onto X1 as it
       moves, because once it is in ``__PREVIEWS`` the stem is all that would be
       left to pair it by. Accepted for previews only: an ``._exif`` is written
       by this pipeline and is always in X1 form already, so allowing a stem
       match there would add a way to get it wrong and no way to get it right.

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

    if not root.is_dir():
        reporter.error(f"{root} is gone, no companions placed")
        report.errors = reporter.error_count
        return report

    if not any(extensions for _key, extensions in companion_kinds(config)):
        return report          # an archive configured to keep neither

    index = index_tree(root, config, reporter, skip=duplicates_root)
    report.media = len(index.media)

    # Which subjects a sidecar was found for, so the X4 audit can name the media
    # that have none. Only "._exif" counts here: a preview is not counted in e
    # (X8), so a video with a .thm and no ._exif still wants one.
    sidecar_exts = sidecar_extensions(config)
    have_sidecar = {
        subject.lower()
        for _path, _folder, key, subject, _ext in index.companions
        if key == "exif"
    }
    for name, folder in index.media:
        if name.lower() not in have_sidecar:
            report.media_without_sidecar += 1
            reporter.note(
                "no-sidecar",
                f"- {folder.name}/{name} has no sidecar",
            )

    emptied: list[Path] = []

    for path, folder, key, subject_name, extension in index.companions:
        wanted_name = path.name
        folders = index.subjects_by_name.get(subject_name.lower(), [])

        if not folders and key == "previews":
            # Camera form: the stem of the subject rather than its name.
            candidates = index.subjects_by_stem.get(subject_name.lower(), [])
            distinct = {(name, str(where)) for name, where in candidates}
            if len(distinct) > 1:
                report.ambiguous += 1
                reporter.note(
                    "ambiguous",
                    f"? left {path}: {len(distinct)} files share the stem "
                    f"{subject_name}, so its subject is not knowable",
                )
                continue
            if candidates:
                media_name, subject_folder = candidates[0]
                wanted_name = media_name + extension.lower()
                folders = [subject_folder]

        if not folders:
            report.orphaned += 1
            reporter.note("orphaned",
                          f"- left {path}: {subject_name} is nowhere in the tree")
            continue
        if len({str(where) for where in folders}) > 1:
            report.ambiguous += 1
            reporter.note(
                "ambiguous",
                f"? left {path}: {subject_name} exists in "
                f"{len(set(str(w) for w in folders))} folders, so which one "
                "this describes is not knowable",
            )
            continue

        subject_folder = folders[0]
        wanted = Path(sidecar_subdir(subject_folder, config, key))
        if wanted == folder and wanted_name == path.name:
            report.in_place += 1
            continue

        destination = wanted / wanted_name
        if destination.exists():
            try:
                digest = checksum(path)
                same = digest == checksum(destination)
            except OSError as error:
                reporter.error(
                    f"could not checksum {path} against {destination}: {error}")
                continue
            parked = _free_parking_name(
                duplicates_root, subject_name, extension, digest[:8], not same)
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
