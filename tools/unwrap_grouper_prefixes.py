r"""Strip the timestamp prefix an older screenshot grouper put on already-dated media.

Between 2026-07-18 and 2026-07-20 the screenshot grouper re-standardised files
this pipeline had already named, producing a name carrying two timestamps::

    2026-07-18_(Sat)__15.18.44__SCR__2026-07-18_(Sat)__15.18.20__f1.7__...__SG23U.jpg
    |<--------- added ---------->|  |<------ the name Photosorter wrote ------>|

**What went wrong.** The grouper's ``StandardizedFormatExtractor`` matched
``YYYY-MM-DD__HH.MM.SS`` -- double underscore, no weekday -- while this pipeline
was writing ``YYYY-MM-DD_(Ddd)_HH.MM.SS``. None of its four date extractors
matched, so ``_resolve_date`` fell through to ``file_birthtime()`` and the
prefix it wrote is the file's **creation time on disk**: when the phone finished
writing the frame, or when the batch was copied to this machine. Not a capture
time, and no information EXIF does not already hold. ``extract_extra_text``
recognised nothing to strip either, so the whole original name survived as
trailing text -- which is the one piece of luck here, and what makes this
repairable byte for byte.

Two consequences, and this tool exists to undo both:

  * **every sidecar was orphaned.** ``__EXIF`` still holds
    ``<original>.jpg._exif``, named for a file that no longer answers to that
    name. ``place_companions`` resolves a companion by full name or by stem;
    neither survives a *prepended* prefix, so the sidecar reports as "nowhere in
    the tree" and its image as "has no sidecar" -- one pair, counted twice. The
    grouper gained sidecar-following only later, so nothing carried them across.
  * **event folders were mistimed.** ``earliest_capture_time`` reads a name's
    *leading* stamp (N3), which on a wrapped file is the creation time. Folders
    took their prefix from it, which is why four distinct events can all be
    stamped ``21.29.04`` -- one copy batch, not one moment.

Fixed upstream in the grouper by ``_ALREADY_DATED`` (commit 6751a81,
2026-07-20 21:39), which leaves any name opening with a date and a time alone.
Nothing new is being wrapped; what is left is the files already on disk.

**What this tool will and will not touch.** The signature it acts on is a
timestamp prefix, the grouper's ``SCR``/``VIDEO`` marker, and *a second
timestamp immediately after it*. That second stamp is the whole tell: it is
exactly the condition ``_ALREADY_DATED`` now refuses, so a name carrying it was
never one the grouper should have rewritten. A genuine screenshot --
``2026-07-18_(Sat)__14.30.00__SCR__Chrome.png`` -- carries one stamp and is left
alone. A wrapper whose inner stamp is *later* than the outer one is not this
bug, and is reported rather than unwrapped.

Companions are not special-cased: a sidecar or preview that carries a wrapped
name matches the same pattern wherever it sits and is unwrapped with everything
else, so a folder cannot come out half-repaired.

Nothing is renamed without ``--apply``. With it, every rename is appended to a
journal that ``--undo`` replays backwards.

Usage:
    python tools/unwrap_grouper_prefixes.py [TARGET] [--year YYYY] [--apply]
    python tools/unwrap_grouper_prefixes.py --undo JOURNAL [--apply]

Exit codes: 0 = nothing left to do, 1 = changes pending or failures, 2 = error.
"""

import argparse
import datetime
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICALISE_TOOL_PATH = REPO_ROOT / "tools" / "canonicalise_timestamp_names.py"


def load_module(name, path):
    """Load a module by file path, without importing its package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("Cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The canonicaliser is this tool's library of path-safety primitives --
# extended_path, resolve_target, walk_bottom_up, path_key, is_reparse_point,
# rename_path, the retry convention, the report colours and the journal format.
# One definition of each, in the tool that already had to get them right for
# the same targets (T8).
canonicalise = load_module("canonicalise_timestamp_names", CANONICALISE_TOOL_PATH)
stamps = canonicalise.stamps
grouping = canonicalise.grouping

CHANGED = canonicalise.CHANGED
CONFLICT = canonicalise.CONFLICT
FAILED = canonicalise.FAILED
REFUSED = canonicalise.REFUSED

# The two media-type markers the grouper writes between its prefix and whatever
# text it kept. Spelled here rather than imported: the grouper is a separate
# project with its own release cycle, and this tool has to keep reading names it
# wrote in 2026 whether or not that project still exists.
GROUPER_MARKERS = ("SCR", "VIDEO")

# A grouper prefix in front of a name that already carried its own timestamp.
# The lookahead is the whole safety argument: without a second stamp behind the
# marker this is an ordinary screenshot name and none of this applies. The
# optional "__<n>" is the collision counter the grouper writes when two files
# in a folder land on one second.
WRAPPED_RE = re.compile(
    r"^(?P<outer>%s)(?:__\d+)?__(?P<marker>%s)__(?=%s)"
    % (stamps.STAMP_PATTERN, "|".join(GROUPER_MARKERS), stamps.STAMP_PATTERN))


class Wrapped:
    """One wrapped name, split into the prefix to drop and the name to restore."""

    def __init__(self, name, outer, marker, inner_name, inner):
        self.name = name
        self.outer = outer              # datetime the grouper wrote (a ctime)
        self.marker = marker            # "SCR" or "VIDEO"
        self.inner_name = inner_name    # the name Photosorter had written
        self.inner = inner              # datetime that name opens with

    @property
    def gap_seconds(self):
        """How far the grouper's stamp sits after the capture it displaced."""
        return int((self.outer - self.inner).total_seconds())


def read_wrapped(name):
    """Split ``name`` into prefix and payload, or None if it is not wrapped.

    Both stamps have to be real instants: ``STAMP_PATTERN`` matches the shape of
    a timestamp, not a date that exists, and a name saying ``2026-02-30`` is an
    anomaly to report rather than a rename to plan.
    """
    match = WRAPPED_RE.match(name)
    if match is None:
        return None
    inner_name = name[match.end():]
    outer = stamps.parse_stamp(match.group("outer"))
    inner = stamps.parse_stamp(inner_name)
    if outer is None or inner is None:
        return None
    return Wrapped(name, outer, match.group("marker"), inner_name, inner)


def reason_to_refuse(wrapped):
    """Why this wrapper is not the 2026-07 bug, or None when it is.

    The grouper wrote a file *creation* time, which cannot precede the capture
    the file records. One that does came from somewhere else, and guessing which
    half of the name to keep is exactly the judgement this tool must not make.
    """
    if wrapped.gap_seconds < 0:
        return ("its %s prefix %s is EARLIER than the capture time %s it wraps, "
                "so it is not a creation-time prefix; left alone"
                % (wrapped.marker,
                   stamps.format_stamp(wrapped.outer),
                   stamps.format_stamp(wrapped.inner)))
    return None


def scan(target, refused, skip_keys=()):
    """Every wrapped file under ``target``, deepest first.

    The walk is the canonicaliser's: it never follows a reparse point, never
    leaves the resolved root, and reports what it could not read instead of
    assuming it was a file.
    """
    root_key = canonicalise.path_key(target)
    found = []
    for _directory, files in canonicalise.walk_bottom_up(
            target, root_key, refused, skip_keys):
        for path in files:
            wrapped = read_wrapped(path.name)
            if wrapped is not None:
                found.append((path, wrapped))
    return found


def plan(found, refused):
    """Pair each wrapped file with the name it is to get back.

    A target something else already holds is a conflict, not a choice: two files
    claiming one name is the anomaly, and ``os.rename`` would fail on it anyway.
    ``claimed`` carries the names handed out earlier in this run, so a dry run
    predicts exactly what an ``--apply`` run would do.
    """
    renames, conflicts = [], []
    claimed = set()
    for path, wrapped in found:
        refusal = reason_to_refuse(wrapped)
        if refusal is not None:
            refused.append((path, refusal))
            continue
        target = path.with_name(wrapped.inner_name)
        key = canonicalise.path_key(target)
        if key in claimed:
            conflicts.append((path, target,
                              "another wrapped file here unwraps to the same "
                              "name; left alone"))
            continue
        if os.path.lexists(canonicalise.extended_path(target)):
            conflicts.append((path, target, "already exists; left alone"))
            continue
        claimed.add(key)
        renames.append((path, target, wrapped))
    return renames, conflicts


def folder_retiming(renames):
    """Per folder, the earliest leading capture time before and after the unwrap.

    Read exactly as ``canonicalise_timestamp_names`` reads it -- the earliest
    *leading* stamp among the folder's files (N3) -- so this previews what a
    following run of that tool will write, rather than offering a second opinion
    about it. A folder whose earliest capture does not move is not listed.
    """
    by_folder = {}
    for path, target, _wrapped in renames:
        by_folder.setdefault(path.parent, {})[path.name] = target.name

    moved = []
    for folder, replaced in sorted(by_folder.items(), key=lambda pair: str(pair[0])):
        try:
            with os.scandir(canonicalise.extended_path(folder)) as scan_folder:
                names = [entry.name for entry in scan_folder if entry.is_file()]
        except OSError:
            continue
        before = grouping.earliest_capture_time(names)
        after = grouping.earliest_capture_time(
            [replaced.get(name, name) for name in names])
        if before and after and before != after:
            moved.append((folder, before, after))
    return moved


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description="Remove the screenshot grouper's timestamp prefix from "
                    "media it re-standardised that was already dated.",
        epilog="Nothing is renamed without --apply.")
    parser.add_argument("target", nargs="?", default=None,
                        help="folder to process, recursively "
                             r"(default: <root_folder>\<year>)")
    parser.add_argument("--year", type=int, default=canonicalise.DEFAULT_YEAR,
                        help="year folder under the configured photo root "
                             "(default: %(default)s)")
    parser.add_argument("--apply", action="store_true",
                        help="perform the renames; without it this only reports")
    parser.add_argument("--journal", default=None,
                        help="where to record applied renames "
                             "(default: a dated file inside the target)")
    parser.add_argument("--undo", default=None, metavar="JOURNAL",
                        help="revert the renames recorded in a journal")
    parser.add_argument("--keep-drive-letter", action="store_true",
                        help="do not pin a mapped network drive to its UNC")
    parser.add_argument("--quiet", action="store_true",
                        help="only print the summary")
    parser.add_argument("--no-colour", action="store_true")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    colour = not args.no_colour and sys.stdout.isatty()
    attempts, delay_seconds = canonicalise.configured_retry()

    def report(key, message, target=None, note=""):
        """One report line, or -- when ``target`` is given -- one rename pair."""
        if args.quiet and key not in ("warn", "bold"):
            return
        if target is None:
            print(canonicalise.colourise(message, key, colour))
        else:
            print(canonicalise.rename_report(message, target, key, note, colour))

    if args.undo:
        # The same journal shape the canonicaliser writes, so the same replay
        # reverts it -- one undo, not a second one that could drift.
        return canonicalise.run_undo(args.undo, args.apply, attempts,
                                     delay_seconds, report)

    if args.target:
        target = Path(args.target)
    else:
        target = Path(canonicalise.configured_root_folder()) / str(args.year)

    if not target.is_dir():
        print(canonicalise.colourise("Target is not a folder: %s" % target,
                                     FAILED, colour))
        return 2

    if canonicalise.drive_is_network(target):
        report("dim", "Target is on a network location.")
    target = canonicalise.resolve_target(target, args.keep_drive_letter, report)

    report("bold", "%s %s"
           % ("Unwrapping in" if args.apply else "Dry run over", target))

    journal_handle = None
    journal_path = None
    skip_keys = set()
    if args.apply:
        # Named canonically, so the tool's own bookkeeping obeys the convention
        # it is repairing.
        journal_path = Path(args.journal) if args.journal else (
            target / ("_unwrap_journal_%s.jsonl"
                      % stamps.format_stamp(datetime.datetime.now())))
        skip_keys.add(canonicalise.path_key(journal_path))
        try:
            journal_handle = open(canonicalise.extended_path(journal_path),
                                  "a", encoding="utf-8")
        except OSError as error:
            print(canonicalise.colourise("Cannot open journal %s: %s"
                                         % (journal_path, error), FAILED, colour))
            return 2

    refused = []
    found = scan(target, refused, skip_keys)
    renames, conflicts = plan(found, refused)

    changed = failures = 0
    try:
        for path, destination, wrapped in renames:
            note = "drops %s__%s__ (+%ds on the capture)" % (
                stamps.format_stamp(wrapped.outer), wrapped.marker,
                wrapped.gap_seconds)
            if not args.apply:
                changed += 1
                report(CHANGED, path, destination, note)
                continue
            try:
                canonicalise.rename_path(path, destination, attempts, delay_seconds)
            except OSError as error:
                failures += 1
                report(FAILED, path, destination, "failed: %s" % error)
                continue
            changed += 1
            report(CHANGED, path, destination, note)
            if journal_handle is not None:
                journal_handle.write(
                    json.dumps({"from": str(path), "to": str(destination)}) + "\n")
                journal_handle.flush()   # an interrupted run must stay undoable
    finally:
        if journal_handle is not None:
            journal_handle.close()

    for path, destination, why in conflicts:
        report(CONFLICT, path, destination, why)
    for path, why in refused:
        report(REFUSED, "REFUSED %s: %s" % (path, why))

    retimed = folder_retiming(renames)
    if retimed and not args.quiet:
        print()
        print(canonicalise.colourise(
            "%d event folder(s) whose earliest capture time changes as a result:"
            % len(retimed), "bold", colour))
        for folder, before, after in retimed:
            print(canonicalise.colourise(
                "  %s\n      %s  ->  %s"
                % (folder.name, "%02d.%02d.%02d" % (before.hour, before.minute,
                                                    before.second),
                   "%02d.%02d.%02d" % (after.hour, after.minute, after.second)),
                "dim", colour))
        print(canonicalise.colourise(
            "  Their prefixes are not this tool's to write. Run\n"
            "  tools/canonicalise_timestamp_names.py over them afterwards to "
            "correct the folder times (N3).", "dim", colour))

    print()
    verb = "unwrapped" if args.apply else "to unwrap"
    print(canonicalise.colourise(
        "%d %s, %d conflict(s), %d failure(s), %d refused."
        % (changed, verb, len(conflicts), failures, len(refused)),
        "bold", colour))

    if args.apply and changed:
        print(canonicalise.colourise(
            "Journal: %s  (revert with --undo)" % journal_path, "dim", colour))
    if not args.apply and changed:
        print(canonicalise.colourise(
            "Nothing was changed. Re-run with --apply.", "ok", colour))

    if failures or conflicts:
        return 1
    if not args.apply and changed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
