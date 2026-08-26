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

Only the *time* is taken from the earliest file; the date stays as
folder-sorting wrote it, since a shot after midnight but before the day
boundary belongs to the previous day's folder and rewriting the date would
move the day out from under its month folder too. A folder already carrying
the marker keeps its counts verbatim -- the grouper may be mid-review on it --
and only gains the time. Labelled folders ("... - Lens tests") are already
named by a human and are never touched. ``--skip-placeholders`` turns this
half off and rewrites timestamps only.

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
           "bold": "\033[1m", "off": "\033[0m"}


def colourise(text, key, enabled):
    if not enabled:
        return text
    return "%s%s%s" % (COLOURS.get(key, ""), text, COLOURS["off"])


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


def folder_media(folder, media_files, settings):
    """The media a day folder holds, preferring its top level.

    Top level first, because that is what the grouper GUI shows and therefore
    what the grouping stage counts -- so wherever that stage would write a
    name, this tool writes the same one.

    A day whose every file was routed into a subfolder (a video-only day: all
    of "__VIDEOS", sidecars in "__EXIF") has nothing at the top level at all.
    Those are real days with real media, so fall back to the whole subtree
    rather than pretend the day is empty.
    """
    media = grouping.select_media(media_files or (), settings.image_exts, settings.video_exts)
    if media:
        return media
    try:
        nested = [path for path in Path(folder).rglob("*") if path.is_file()]
    except OSError:
        return []
    return grouping.select_media(nested, settings.image_exts, settings.video_exts)


def earliest_time_text(media):
    """``HH.MM.SS`` of the earliest stamped file, or None if none is stamped."""
    moments = []
    for path in media:
        match = stamps.LEADING_STAMP_RE.match(Path(path).name)
        if not match:
            continue
        try:
            moments.append(datetime.datetime(*(int(part) for part in match.groups())))
        except ValueError:
            continue
    return f"{min(moments):%H.%M.%S}" if moments else None


def with_earliest_time(base, media):
    """Give a day prefix the time of its earliest file: ``2026-07-03_(Fri)__09.12.53``.

    Only the time is taken. The date stays as folder-sorting wrote it, because
    that is a decision this tool must not silently revisit: a shot after
    midnight but before the day-boundary time belongs to the previous day's
    folder, and rewriting the date would move the day out from under its month
    folder as well.
    """
    if stamps.LEADING_STAMP_RE.match(base):
        return base                    # already carries a time
    text = earliest_time_text(media)
    return f"{base}__{text}" if text else base


def canonical_placeholder_name(folder, name, media_files, settings):
    """Put a day folder onto the grouper's ``__TO_SPLIT__`` convention.

    Both halves of the name are brought up to date: the dated prefix gains the
    time of the day's earliest file, and the legacy placeholder becomes the
    marker with its media counts.
    """
    base = grouping.strip_placeholder(name, settings.placeholder)
    if base is not None:
        media = folder_media(folder, media_files, settings)
        images, videos = grouping.count_media(
            media, settings.image_exts, settings.video_exts)
        return grouping.to_split_name(with_earliest_time(base, media), images, videos)

    existing = grouping.split_to_split_name(name)
    if existing is not None:
        # Already marked: give it the time, but leave the counts exactly as
        # they are -- the grouper may be part-way through that folder.
        base, tail = existing
        media = folder_media(folder, media_files, settings)
        return with_earliest_time(base, media) + tail

    return name


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
                report(CONFLICT, "%s\n        -> %s already exists; left alone"
                       % (path, target.name))
                continue

        if not apply_changes:
            counters[CHANGED] += 1
            report(CHANGED, "%s\n        -> %s" % (path, target.name))
            continue

        try:
            rename_path(path, target, attempts, delay_seconds)
        except OSError as error:
            counters[FAILED] += 1
            report(FAILED, "%s\n        -> %s failed: %s" % (path, target.name, error))
            continue

        counters[CHANGED] += 1
        report(CHANGED, "%s\n        -> %s" % (path, target.name))
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
            report(CHANGED, "%s\n        -> %s" % (source, Path(target).name))
            continue
        try:
            rename_path(source, target, attempts, delay_seconds)
        except OSError as error:
            failures += 1
            report(FAILED, "%s\n        -> %s failed: %s" % (source, target, error))
        else:
            report(CHANGED, "%s\n        -> %s" % (source, Path(target).name))

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

    def report(key, message):
        if args.quiet and key not in ("warn", "bold"):
            return
        print(colourise(message, key, colour))

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
