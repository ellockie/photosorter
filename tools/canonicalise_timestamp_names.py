"""Rewrite dated folder and file names into the canonical timestamp form.

Names written by earlier versions of the pipeline, or by the screenshot
grouper, carry the same instant in several different shapes::

    2015-11-23_(Mon)_09.26.27__RAW__f4.0.JPG    single underscore before time
    2026-07-19__21.29.04__SCR__shot.png         no weekday at all
    2026-08-25_(tue)__10.23.12__f2.8.JPG        stale or lower-case weekday
    2014-05-08 - 1. ######                      day folder without a weekday

All of them become the canonical form::

    2026-08-25_(Tue)__10.23.12__<rest of the name kept verbatim>

Only the timestamp is rewritten. Every other character -- markers, camera
symbols, exposure suffixes, extension, capitalisation -- survives byte for
byte, because the substitution is applied to the timestamp span alone.

Event folders are additionally brought onto the grouper's convention, gaining
both the time of their earliest file and the media counts::

    2026-07-15_(Wed) - 1. ######        ->  ..._(Wed)__09.12.53 - __TO_SPLIT__(i=111)
    2026-07-18_(Sat) - __TO_SPLIT__(i=6)  ->  ..._(Sat)__11.04.02 - __TO_SPLIT__(i=6)

The time comes from the folder's earliest file, or -- when the grouper has
moved the images out and left their "._exif" files behind -- from the earliest
of those, since a sidecar is named after the image it described and carries its
capture time.

Only the *time* is taken from the earliest file; the date stays as
folder-sorting wrote it, since a shot after midnight but before the day
boundary belongs to the previous day's folder and rewriting the date would
move the day out from under its month folder too. Labelled folders
("... - Lens tests") are already named by a human and are never touched.
``--skip-placeholders`` turns this half off and rewrites timestamps only.

The counts of a folder already carrying the marker are rebuilt from what is on
disk now, and gain two audit markers that say what the ``i``/``v`` counts do
not account for::

    ..._(Wed)__13.07.11 - __TO_SPLIT__(i=129)  ->  ..._(i=129_s=6)
    2026-07-25_(Sat) - __TO_SPLIT__(i=7)       ->  ..._(Sat) - __TO_SPLIT__(e=7)

``s`` counts the non-sidecar files below the top level -- videos routed into
"__VIDEOS", RAWs, an already-split sub-event -- because the grouper GUI shows
the top level only, so nothing down there is in front of the reviewer. ``e``
counts the sidecars in the whole tree and is written only when that number
does not match the media in the tree: one "._exif" per media file is the norm,
and 7 sidecars beside 0 images means the day's photos left without them.

Rebuilding a count means rewriting the whole tail, so it is done only for a
tail of nothing but the marker and its bracket, and only for a folder that
still holds something. Anything a human wrote after the marker, and the count
on an emptied folder -- the last thing an "__EMPTY_SUBFOLDERS" record has to
say about itself -- are left exactly as found, and those folders only gain the
time.

Neither grammar is redefined here. Both are loaded from the leaf modules that
own them -- ``src/pipeline_stages/stamps.py`` and
``src/pipeline_stages/grouping_names.py`` -- by file path rather than by
``import src.pipeline_stages...``, because that package's ``__init__`` imports
every pipeline stage (exiftool, dashboard, converters); a maintenance tool must
run on a bare interpreter with none of that installed.

NETWORK TARGETS
---------------
A mapped drive letter is a per-session, mutable alias: it can be remapped
between the moment the target is checked and the moment a file is renamed, and
anything that walks it can be redirected by a junction planted on the share.
This tool therefore:

  * resolves a mapped letter to its UNC once, up front, and works on the UNC,
    so the run cannot be re-pointed underneath it (``--keep-drive-letter``
    opts out);
  * never follows reparse points (junctions, symlinks, mount points) and
    reports each one it refused, so the walk cannot leave the target tree;
  * re-checks that every directory it is about to scan is still inside the
    resolved root;
  * renames with ``os.rename``, never ``os.replace``, so an unexpected name
    collision fails loudly instead of destroying the file it lands on;
  * retries transient SMB failures instead of aborting a tree half-renamed;
  * handles no credentials of any kind -- authenticating the share is the
    operating system's job, and this tool will not accept a password.

Nothing is renamed without ``--apply``: the default run is a dry report. With
``--apply`` every rename is appended to a journal that ``--undo`` replays
backwards.

Usage:
    python tools/canonicalise_timestamp_names.py [TARGET] [--year YYYY] [--apply]
    python tools/canonicalise_timestamp_names.py --undo JOURNAL [--apply]

Exit codes: 0 = nothing left to do, 1 = changes pending or failures, 2 = error.
"""

import argparse
import ctypes
import datetime
import importlib.util
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
STAMPS_MODULE_PATH = REPO_ROOT / "src" / "pipeline_stages" / "stamps.py"
GROUPING_MODULE_PATH = REPO_ROOT / "src" / "pipeline_stages" / "grouping_names.py"
CONFIG_PATH = REPO_ROOT / "config.json"

DEFAULT_ROOT_FOLDER = r"c:\__PHOTOS"
DEFAULT_YEAR = 2026

DEFAULT_RETRY_ATTEMPTS = 5
DEFAULT_RETRY_DELAY_SECONDS = 0.2

# Below this length Windows needs no extended-path prefix; above it, a plain
# path silently fails on any tree deep enough, which network photo archives are.
MAX_COMFORTABLE_PATH = 240

# Interim name for a rename that only changes letter case.
CASE_CHANGE_SUFFIX = ".__casefix__"

CHANGED, CONFLICT, FAILED, REFUSED, UNPARSEABLE = (
    "CHANGED", "CONFLICT", "FAILED", "REFUSED", "UNPARSEABLE")

COLOURS = {CHANGED: "\033[96m", CONFLICT: "\033[93m", FAILED: "\033[91m",
           REFUSED: "\033[93m", UNPARSEABLE: "\033[93m",
           "ok": "\033[92m", "warn": "\033[93m", "dim": "\033[90m",
           # The halves of a rename that differ: what the name says now, and
           # what will replace it.
           "old": "\033[97m", "new": "\033[91m",
           # Faint *and* grey: the rule between two renames has to be visible
           # enough to group them and quiet enough to read straight past.
           "rule": "\033[2;90m",
           "bold": "\033[1m", "off": "\033[0m"}

# A rename prints as two lines carrying prefixes of equal width, so the old and
# the new path land in one column and the eye can run straight down to the
# character where they part.
RENAME_FROM_PREFIX = "        "
RENAME_TO_PREFIX = "    ->  "

# Closing each pair with a rule is what keeps a long report legible: without
# it, four adjacent paths are one block and the eye has to count to find which
# two belong together. ASCII, because this prints to whatever console and code
# page the machine happens to have.
#
# One width for every rule, rather than one that hugs each pair: a ragged right
# edge down the report reads as content, and this is meant to read as nothing.
# Resolved once, since the command is short-lived, and kept a column clear of
# the edge so the rule cannot wrap into a line of its own.
RENAME_RULE_CHAR = "-"
RENAME_RULE_WIDTH = max(
    20, shutil.get_terminal_size((100, 24)).columns - len(RENAME_FROM_PREFIX) - 1)


def colourise(text, key, enabled):
    if not enabled or not text:
        return text
    return "%s%s%s" % (COLOURS.get(key, ""), text, COLOURS["off"])


def rename_report(source, target, key, note, enabled):
    """The two aligned lines of one rename, coloured at the point they part.

    Everything the two paths share -- the whole folder above them, and however
    much of the name survives -- keeps the outcome's own colour, so a wall of
    renames still reads as CHANGED or CONFLICT at a glance. Past that point the
    two lines disagree, and that is the only part worth reading: the text going
    away is plain white, the text replacing it is red.

    A faint rule closes the pair, so a long report reads as a list of renames
    rather than a block of paths.
    """
    source, target = str(source), str(target)
    shared = len(os.path.commonprefix([source, target]))

    lines = [
        RENAME_FROM_PREFIX + colourise(source[:shared], key, enabled)
        + colourise(source[shared:], "old", enabled),
        RENAME_TO_PREFIX + colourise(target[:shared], key, enabled)
        + colourise(target[shared:], "new", enabled),
    ]
    if note:
        lines[1] += "  " + colourise(note, key, enabled)

    lines.append(RENAME_FROM_PREFIX + colourise(
        RENAME_RULE_CHAR * RENAME_RULE_WIDTH, "rule", enabled))
    return "\n".join(lines)


def load_leaf_module(name, path):
    """Load a name-grammar module without importing the stage package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("Cannot load the name grammar from %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stamps = load_leaf_module("photosorter_stamps", STAMPS_MODULE_PATH)
grouping = load_leaf_module("photosorter_grouping_names", GROUPING_MODULE_PATH)


# --------------------------------------------------------------------------
# Name transformation
# --------------------------------------------------------------------------

def _canonical_stamp(match):
    """Rewrite one matched timestamp; leave an impossible date verbatim."""
    try:
        moment = datetime.datetime(*(int(part) for part in match.groups()))
    except ValueError:
        # e.g. "2026-02-31__10.00.00" or "...__25.99.99" -- the regex accepts
        # the shape, the calendar does not. Renaming it would invent a date.
        return match.group(0)
    return stamps.format_stamp(moment)


def _canonical_day_prefix(name):
    """Give a date-only leading prefix its weekday: ``2014-05-08_(Thu)``."""
    match = stamps.DAY_PREFIX_RE.match(name)
    if not match:
        return name
    try:
        day = datetime.date(*(int(part) for part in match.group(1).split("-")))
    except ValueError:
        return name
    return stamps.format_day_prefix(day) + name[match.end():]


def canonical_name(name):
    """The canonical form of ``name``; identical when nothing needs changing."""
    rewritten = stamps.STAMP_RE.sub(_canonical_stamp, name)
    # A day prefix is only meaningful when the name does not already open with
    # a full timestamp -- otherwise the substitution above has handled it.
    if not stamps.LEADING_STAMP_RE.match(rewritten):
        rewritten = _canonical_day_prefix(rewritten)
    return rewritten


def carries_impossible_stamp(name):
    """True when a name looks stamped but names a date that cannot exist."""
    return bool(stamps.STAMP_RE.search(name)) and stamps.parse_stamp(name) is None


class GroupingSettings:
    """What the placeholder rewrite needs from config, resolved once."""

    def __init__(self, config):
        self.placeholder = grouping.date_folder_suffix(config)
        self.image_exts, self.video_exts = grouping.extension_sets(config)
        self.sidecar_exts = grouping.sidecar_extensions(config)


def nested_files(folder):
    """Every file below ``folder``'s top level, however deep.

    ``os.walk`` rather than ``Path.rglob``, for the two reasons the rest of
    this tool cares about: it takes the extended path, so a deep archive tree
    does not silently come back short, and with ``followlinks=False`` it will
    not descend a junction planted inside a day folder.
    """
    found = []
    try:
        walk = os.walk(extended_path(folder), followlinks=False)
        next(walk, None)                      # the top level is the caller's
        for directory, _subdirectories, names in walk:
            found.extend(Path(directory) / name for name in names)
    except OSError:
        return []
    return found


def folder_media(top_level_files, nested, settings):
    """The media a day folder holds, preferring its top level.

    Top level first, because that is what the grouper GUI shows and therefore
    what the grouping stage counts -- so wherever that stage would write a
    name, this tool writes the same one.

    A day whose every file was routed into a subfolder (a video-only day: all
    of "__VIDEOS", sidecars in "__EXIF") has nothing at the top level at all.
    Those are real days with real media, so fall back to the whole subtree
    rather than pretend the day is empty.
    """
    media = grouping.select_media(
        top_level_files or (), settings.image_exts, settings.video_exts)
    if media:
        return media
    return grouping.select_media(nested, settings.image_exts, settings.video_exts)


def folder_audit(everything, nested, settings):
    """``(sidecars, subfolder_files)`` for a day folder; ``None`` where silent.

    Each is something the ``i``/``v`` counts do not account for, and each is
    reported only when it has something to say:

      * ``sidecars`` -- every "._exif" in the tree, but only when the count
        does not match the media in that tree. One sidecar per media file is
        the norm; any other number means a sidecar was orphaned when its image
        moved, or an image arrived without one. ``e=0`` beside a folder full of
        images is the loudest form of that, so zero is reported, not dropped.
      * ``subfolder_files`` -- everything below the top level that is not a
        sidecar, whenever there is any. The grouper GUI shows the top level
        only, so nothing down there is in front of the reviewer.

    An archive configured to keep no sidecars silences ``e`` outright: with no
    extension to look for, a count of zero would be saying nothing.
    """
    media = grouping.select_media(everything, settings.image_exts, settings.video_exts)
    sidecars = grouping.count_sidecars(everything, settings.sidecar_exts)
    if not settings.sidecar_exts or sidecars == len(media):
        sidecars = None

    subfolder_files = sum(
        1 for path in nested
        if Path(path).suffix.lower() not in settings.sidecar_exts)

    return sidecars, subfolder_files or None


def _counts_may_be_rebuilt(tail, top_level_files, nested):
    """Whether an existing ``__TO_SPLIT__`` tail may be recomputed.

    It may not in two cases, and in both the folder keeps its tail verbatim
    and only gains its time:

      * the tail carries something besides the counts. Rebuilding rewrites the
        whole tail, and would take a note somebody left there with it.
      * the folder is empty. Then there is nothing to count and the rebuild
        could only erase: the emptied day folders parked in
        "__EMPTY_SUBFOLDERS" have their old count as the last thing they say
        about themselves, and several of them share a date, so blanking the
        counts would also collide four folders onto one name.
    """
    if not grouping.to_split_tail_is_only_counts(tail):
        return False
    return bool(top_level_files) or bool(nested)


def canonical_placeholder_name(folder, name, media_files, settings):
    """Put a day folder onto the grouper's ``__TO_SPLIT__`` convention.

    Both halves of the name are brought up to date: the dated prefix gains the
    time of the day's earliest file -- or, for a folder whose media has gone,
    of the earliest sidecar left behind -- and the placeholder (or the marker
    an earlier run left) becomes the marker with counts rebuilt from what is on
    disk now, carrying whatever audit markers ``folder_audit`` found. The time
    itself comes from ``grouping.with_earliest_time`` -- the same function the
    live screenshot-grouping stage uses -- so this tool cannot drift from it.
    """
    base = grouping.strip_placeholder(name, settings.placeholder)
    tail = None
    if base is None:
        existing = grouping.split_to_split_name(name)
        if existing is None:
            return name                # labelled by a human, or not a day folder
        base, tail = existing

    nested = nested_files(folder)
    everything = list(media_files or ()) + nested
    media = folder_media(media_files, nested, settings)

    # Falling back to the sidecars is what dates a day the grouper has emptied
    # of images: the "._exif" files stay behind, and each is named after the
    # image it described, so it carries that image's capture time. Without
    # this such a folder keeps a bare date, and two of them on one day collide
    # on a single name -- which is the whole reason the time is there.
    dated = grouping.with_earliest_time(
        base, media or grouping.select_sidecars(everything, settings.sidecar_exts))

    if tail is not None and not _counts_may_be_rebuilt(tail, media_files, nested):
        return dated + tail

    images, videos = grouping.count_media(
        media, settings.image_exts, settings.video_exts)
    sidecars, subfolder_files = folder_audit(everything, nested, settings)
    return grouping.to_split_name(dated, images, videos, sidecars, subfolder_files)


# --------------------------------------------------------------------------
# Windows / network path handling
# --------------------------------------------------------------------------

def extended_path(path):
    """Prefix a long Windows path so the syscall is not capped at MAX_PATH."""
    text = str(path)
    if os.name != "nt" or len(text) < MAX_COMFORTABLE_PATH or text.startswith("\\\\?\\"):
        return text
    absolute = os.path.abspath(text)
    if absolute.startswith("\\\\"):
        return "\\\\?\\UNC\\" + absolute[2:]
    return "\\\\?\\" + absolute


def drive_is_network(path):
    """True when ``path`` lives on a mapped drive or a UNC share."""
    text = str(path)
    if text.startswith("\\\\"):
        return True
    if os.name != "nt":
        return False
    drive = os.path.splitdrive(os.path.abspath(text))[0]
    if not drive:
        return False
    DRIVE_REMOTE = 4
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(drive + "\\") == DRIVE_REMOTE
    except (AttributeError, OSError):
        return False


def unc_for_drive(path):
    """The UNC a mapped letter points at right now, or None.

    Pinning this once removes the window in which a remapped letter would send
    the rest of the run at a different server.
    """
    if os.name != "nt":
        return None
    drive = os.path.splitdrive(os.path.abspath(str(path)))[0]
    if not drive or not drive.endswith(":"):
        return None
    buffer_length = ctypes.c_ulong(1024)
    buffer = ctypes.create_unicode_buffer(buffer_length.value)
    try:
        result = ctypes.windll.mpr.WNetGetConnectionW(
            drive, buffer, ctypes.byref(buffer_length))
    except (AttributeError, OSError):
        return None
    if result != 0:
        return None
    return buffer.value or None


def resolve_target(target, keep_drive_letter, report):
    """Return the path to operate on, pinned to a UNC where that is safer."""
    if keep_drive_letter or not drive_is_network(target):
        return target
    unc = unc_for_drive(target)
    if not unc:
        return target
    remainder = os.path.splitdrive(os.path.abspath(str(target)))[1].lstrip("\\/")
    pinned = Path(unc) / remainder if remainder else Path(unc)
    if not pinned.is_dir():
        # Alternate credentials on the mapping, or a share that refuses a direct
        # connection. The letter still works, so continue -- but say so.
        report("warn", "Mapped drive resolves to %s, which is not reachable "
                       "directly; staying on the drive letter." % unc)
        return target
    report("dim", "Mapped drive pinned to its UNC: %s" % pinned)
    return pinned


def is_reparse_point(entry):
    """True for a junction, symlink or mount point."""
    try:
        return bool(entry.stat(follow_symlinks=False).st_reparse_tag)
    except AttributeError:
        return entry.is_symlink()          # non-Windows
    except OSError:
        return True                        # unreadable: treat as untrusted


def path_key(path):
    return os.path.normcase(os.path.abspath(str(path)))


def inside(root_key, candidate):
    key = path_key(candidate)
    return key == root_key or key.startswith(root_key.rstrip("\\/") + os.sep)


def walk_bottom_up(root, root_key, refused, skip_keys=()):
    """Yield ``(directory, files)`` deepest-first, never leaving the root.

    Deepest-first is what makes the run safe to interrupt: a directory is
    renamed only after everything inside it has been, so no recorded path is
    ever stale when it is used.
    """
    if not inside(root_key, root):
        refused.append((str(root), "resolves outside the target root"))
        return
    try:
        with os.scandir(extended_path(root)) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except OSError as error:
        refused.append((str(root), "cannot be listed: %s" % error))
        return

    directories, files = [], []
    for entry in entries:
        if path_key(entry.path) in skip_keys:
            continue
        if is_reparse_point(entry):
            refused.append((entry.path, "reparse point (junction/symlink) not followed"))
            continue
        try:
            is_directory = entry.is_dir(follow_symlinks=False)
        except OSError as error:
            refused.append((entry.path, "cannot be inspected: %s" % error))
            continue
        (directories if is_directory else files).append(Path(root) / entry.name)

    for directory in directories:
        yield from walk_bottom_up(directory, root_key, refused, skip_keys)
    yield Path(root), files


# --------------------------------------------------------------------------
# Renaming
# --------------------------------------------------------------------------

def with_retry(operation, attempts, delay_seconds):
    """Project retry convention: a dropped SMB handle must not end the run."""
    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except FileExistsError:
            raise                     # a collision will not heal by waiting
        except OSError as error:
            last_error = error
            if attempt == attempts - 1:
                break
            time.sleep(delay_seconds * (attempt + 1))
    raise last_error


def differs_only_by_case(left, right):
    return left != right and os.path.normcase(left) == os.path.normcase(right)


def rename_path(source, target, attempts, delay_seconds):
    """Rename, never overwrite, and survive a case-only change on a share."""
    source, target = Path(source), Path(target)

    def operation():
        if differs_only_by_case(source.name, target.name):
            # Windows and SMB compare names case-insensitively, so renaming
            # "(tue)" to "(Tue)" can be treated as a no-op or refused outright.
            # Going through a distinct interim name forces it through.
            interim = source.with_name(source.name + CASE_CHANGE_SUFFIX)
            os.rename(extended_path(source), extended_path(interim))
            try:
                os.rename(extended_path(interim), extended_path(target))
            except OSError:
                os.rename(extended_path(interim), extended_path(source))
                raise
        else:
            # os.rename, never os.replace: on Windows this raises rather than
            # silently destroying an existing file of the target name.
            os.rename(extended_path(source), extended_path(target))

    return with_retry(operation, attempts, delay_seconds)


def plan_for(path, media_files=None, grouping_settings=None):
    """The canonical target path for one entry, or None when already correct."""
    name = Path(path).name
    wanted = canonical_name(name)
    if grouping_settings is not None and media_files is not None:
        wanted = canonical_placeholder_name(path, wanted, media_files, grouping_settings)
    if wanted == name:
        return None
    return Path(path).with_name(wanted)


def apply_plan(entries, apply_changes, attempts, delay_seconds, journal, report,
               grouping_settings=None):
    """Walk the planned renames, reporting each outcome. Returns counters.

    ``entries`` pairs each path with the top-level files of the folder it *is*
    (None for a file), which is what the placeholder rewrite counts.
    """
    counters = {CHANGED: 0, CONFLICT: 0, FAILED: 0, UNPARSEABLE: 0}

    for path, media_files in entries:
        if carries_impossible_stamp(path.name):
            counters[UNPARSEABLE] += 1
            report(UNPARSEABLE, "%s  (names a date that does not exist)" % path)
            continue

        target = plan_for(path, media_files, grouping_settings)
        if target is None:
            continue

        # A case-only change targets the same file, so lexists() is meaningless.
        if not differs_only_by_case(path.name, target.name):
            if os.path.lexists(extended_path(target)):
                counters[CONFLICT] += 1
                report(CONFLICT, path, target, "already exists; left alone")
                continue

        if not apply_changes:
            counters[CHANGED] += 1
            report(CHANGED, path, target)
            continue

        try:
            rename_path(path, target, attempts, delay_seconds)
        except OSError as error:
            counters[FAILED] += 1
            report(FAILED, path, target, "failed: %s" % error)
            continue

        counters[CHANGED] += 1
        report(CHANGED, path, target)
        if journal is not None:
            journal.write(json.dumps({"from": str(path), "to": str(target)}) + "\n")
            journal.flush()          # an interrupted network run must stay undoable

    return counters


# --------------------------------------------------------------------------
# Undo
# --------------------------------------------------------------------------

def run_undo(journal_path, apply_changes, attempts, delay_seconds, report):
    """Replay a journal backwards, so the deepest rename is reverted first."""
    try:
        lines = Path(journal_path).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        report("warn", "Cannot read journal: %s" % error)
        return 2

    moves = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            record = json.loads(line)
            moves.append((record["to"], record["from"]))
        except (ValueError, KeyError):
            report("warn", "Skipping unreadable journal line: %s" % line)

    failures = 0
    for source, target in reversed(moves):
        if not os.path.lexists(extended_path(source)):
            report(CONFLICT, "%s is already gone; skipped" % source)
            failures += 1
            continue
        if not apply_changes:
            report(CHANGED, source, target)
            continue
        try:
            rename_path(source, target, attempts, delay_seconds)
        except OSError as error:
            failures += 1
            report(FAILED, source, target, "failed: %s" % error)
        else:
            report(CHANGED, source, target)

    report("bold", "%d rename(s) in journal, %d could not be reverted."
           % (len(moves), failures))
    return 1 if failures else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def configured_root_folder():
    return _config().get("paths", {}).get("root_folder") or DEFAULT_ROOT_FOLDER


def configured_retry():
    retry = _config().get("retry", {})
    try:
        return (int(retry.get("attempts", DEFAULT_RETRY_ATTEMPTS)),
                float(retry.get("delay_seconds", DEFAULT_RETRY_DELAY_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_ATTEMPTS, DEFAULT_RETRY_DELAY_SECONDS


def build_parser():
    parser = argparse.ArgumentParser(
        description="Rewrite dated folder and file names into the canonical "
                    "%s form." % stamps.STAMP_FORMAT_DESCRIPTOR,
        epilog="Nothing is renamed without --apply.")
    parser.add_argument("target", nargs="?", default=None,
                        help="folder to process, recursively "
                             r"(default: <root_folder>\<year>)")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR,
                        help="year folder under the configured photo root "
                             "(default: %(default)s)")
    parser.add_argument("--apply", action="store_true",
                        help="perform the renames; without it this only reports")
    parser.add_argument("--journal", default=None,
                        help="where to record applied renames "
                             "(default: a dated file inside the target)")
    parser.add_argument("--undo", default=None, metavar="JOURNAL",
                        help="revert the renames recorded in a journal")
    parser.add_argument("--skip-placeholders", action="store_true",
                        help='rewrite timestamps only; leave " - 1. ######" '
                             "event folders alone")
    parser.add_argument("--keep-drive-letter", action="store_true",
                        help="do not pin a mapped network drive to its UNC")
    parser.add_argument("--quiet", action="store_true",
                        help="only print the summary")
    parser.add_argument("--no-colour", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    colour = not args.no_colour and sys.stdout.isatty()
    attempts, delay_seconds = configured_retry()

    def report(key, message, target=None, note=""):
        """One report line, or -- when ``target`` is given -- one rename pair."""
        if args.quiet and key not in ("warn", "bold"):
            return
        if target is None:
            print(colourise(message, key, colour))
        else:
            print(rename_report(message, target, key, note, colour))

    if args.undo:
        return run_undo(args.undo, args.apply, attempts, delay_seconds, report)

    if args.target:
        target = Path(args.target)
    else:
        target = Path(configured_root_folder()) / str(args.year)

    if not target.is_dir():
        print(colourise("Target is not a folder: %s" % target, FAILED, colour))
        return 2

    # The year check looks at the folder actually being processed, so it also
    # catches "--target c:\__PHOTOS\2019" and not just a stale default.
    current_year = datetime.date.today().year
    if re.fullmatch(r"\d{4}", target.name):
        if int(target.name) != current_year:
            report("warn", colourise(
                "WARNING: %s is not the current year (%d)."
                % (target.name, current_year), "warn", colour))
    else:
        report("warn", colourise(
            "WARNING: %s is not a year folder; processing it anyway." % target.name,
            "warn", colour))

    if drive_is_network(target):
        report("dim", "Target is on a network location.")
    target = resolve_target(target, args.keep_drive_letter, report)

    root_key = path_key(target)
    refused = []
    grouping_settings = None if args.skip_placeholders else GroupingSettings(_config())

    report("bold", "%s %s" % ("Renaming in" if args.apply else "Dry run over", target))

    journal_handle = None
    journal_path = None
    skip_keys = set()
    if args.apply:
        # Named canonically, so the tool's own bookkeeping obeys the convention
        # it enforces.
        journal_path = Path(args.journal) if args.journal else (
            target / ("_rename_journal_%s.jsonl"
                      % stamps.format_stamp(datetime.datetime.now())))
        # The journal usually sits inside the target, where the walk would find
        # it, try to rename it, and fail because it is still open. Whatever the
        # caller chose, it is never a rename candidate.
        skip_keys.add(path_key(journal_path))
        try:
            journal_handle = open(extended_path(journal_path), "a", encoding="utf-8")
        except OSError as error:
            print(colourise("Cannot open journal %s: %s" % (journal_path, error),
                            FAILED, colour))
            return 2

    totals = {CHANGED: 0, CONFLICT: 0, FAILED: 0, UNPARSEABLE: 0}
    try:
        for directory, files in walk_bottom_up(target, root_key, refused, skip_keys):
            # Files first, then the directory itself: renaming the directory
            # last keeps every path collected above valid while it is used.
            entries = [(path, None) for path in files]
            if path_key(directory) != root_key:
                entries.append((directory, files))
            counters = apply_plan(entries, args.apply, attempts, delay_seconds,
                                  journal_handle, report, grouping_settings)
            for key, value in counters.items():
                totals[key] += value
    finally:
        if journal_handle is not None:
            journal_handle.close()

    for path, reason in refused:
        report(REFUSED, "REFUSED %s: %s" % (path, reason))

    print()
    verb = "renamed" if args.apply else "to rename"
    print(colourise(
        "%d %s, %d conflict(s), %d failure(s), %d unparseable, %d refused."
        % (totals[CHANGED], verb, totals[CONFLICT], totals[FAILED],
           totals[UNPARSEABLE], len(refused)), "bold", colour))

    if args.apply and totals[CHANGED]:
        print(colourise("Journal: %s  (revert with --undo)" % journal_path,
                        "dim", colour))
    if not args.apply and totals[CHANGED]:
        print(colourise("Nothing was changed. Re-run with --apply.", "ok", colour))

    if totals[FAILED] or totals[CONFLICT]:
        return 1
    if not args.apply and totals[CHANGED]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
