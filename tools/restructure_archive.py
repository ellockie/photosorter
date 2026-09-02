r"""Bring an existing archive onto the current conventions, in one pass.

This is the front door for restructuring work: the seven steps that turn a tree
written by an older Photosorter, an older grouper or a third-party tool into
the shape ``ARCHIVE_STANDARD.md`` describes, run in the one order that makes
sense, over one target, with one set of safety rules.

    1. Canonicalise names          tools/canonicalise_timestamp_names.py
    2. Reunite companions and sidecars     companion_matching.py
    3. Group the "__TO_SPLIT__" folders, one at a time, in the grouper GUI
    4. Reunite companions and sidecars     companion_matching.py
    5. Canonicalise names again    tools/canonicalise_timestamp_names.py
    6. Check compliance with the archive standard      [not implemented]
    7. Fix compliance with the archive standard        [not implemented]

Only the folders worth opening
------------------------------
Step 3 opens a marked folder only when it has an image or a video **at its top
level**, which is the whole of what the grouper's thumbnail grid shows. A
folder can carry the marker and still have nothing for it to do: an earlier
pass already split the day into sub-events, the day's files all sit in
"__RAW" or a legacy "__VIDEOS", or it is one of the hollow folders parked in
"__EMPTY_SUBFOLDERS" that the canonicaliser marks "(EMPTY)". Opening one of
those puts an empty grid in front of the reviewer and waits for them to close
it, and on a batch of ninety that is the difference between a job and an
afternoon. They are listed, with the reason, rather than dropped silently;
"--open-all" opens them anyway.

The count is taken off the disk, never off the folder's own name: the
canonicaliser counts the whole subtree when a top level is bare, so a day
whose every file sits in a subfolder is still named "__TO_SPLIT__(v=3)"
while having nothing to show.

Why everything happens twice
---------------------------
Step 1 is what makes step 3 possible: the grouper is opened on folders
carrying the "__TO_SPLIT__" marker, and a legacy "- 1. ######" day does not
carry it until the canonicaliser has rewritten the tail. Step 1 also gives
every folder the time of its earliest file, so two days that would otherwise
collide on a bare date are separated before anything else runs.

Step 2 is reconciliation over an archive nobody has touched yet: the point of
this tool is already-archived material, where earlier passes and third-party
tools have left companions stranded and sidecars a level too high. Healing
that **before** the GUI opens is what puts a whole shot in front of the
reviewer instead of half of one.

Step 4 is the same engine over what step 3 has just done, and is the reason
the pipeline has the stage at all: splitting a day moves only the top-level
representatives, leaving every RAW, sidecar and preview behind in the event
folder's taxonomy subdirs. Without this pass they stay behind for good.

Step 5 is what makes steps 3 and 4 durable: the grouper writes its own names,
on its own convention, and rebuilds a count bracket from scratch every time it
touches a folder -- dropping the "e"/"s" audit markers, and leaving the
sub-event folders it creates stamped in whatever shape it favours. Step 4 then
moves files between folders, which changes those counts again. Running the
canonicaliser last folds all of it back onto the canonical form and re-derives
the audit markers from what is finally on disk.

What reconciliation does
------------------------
Three passes, in this order and no other:

  * ``migrate_legacy_containers`` -- "##   EXIFs   ##" becomes "__EXIF" and
    "##   RAWs   ##" becomes "__RAW". Renamed outright where nothing of that
    name is there yet; where one is, each file moves across and a collision is
    settled by checksum. An emptied container is parked in the
    "__EMPTY_SUBFOLDERS" beside it, numbered when that name is taken. A
    container with no modern equivalent -- "old_EXIF", the three "FILES"
    holders -- is reported and never touched.
  * ``reconcile_folder`` -- a companion left in an event folder's taxonomy
    subdir follows the representative the grouper moved into a sibling
    sub-event. Matched on capture time, because the representative has been
    renamed since.
  * ``place_companions`` -- X10 and X13: a companion goes into the folder
    directly inside the one that holds its subject -- an "._exif" sidecar into
    "__EXIF", a ".thm" or ".lrv" preview into "__PREVIEWS". Matched on name,
    because a companion carries its subject's full name (X1).

The order is the dependency order. Migration first, so everything after it
reads one set of folder names instead of two. Reconciliation next, because it
moves *subjects*: a RAW still in the wrong event folder has no business having
its sidecar placed beside it yet. Placement last, once every file is in the
folder it belongs to.

**A sidecar is looked for anywhere in the target**, at any depth and across
year trees -- placement indexes every tree of the run at once before it moves
anything. That is what lets one stranded in a different event folder, or a
different year, find its subject.

**Only a dated folder holds subjects.** A media file outside one is not a
candidate however plausible its name: the archive's shape is what says which
files are the archive's, and a stray JPG in a working folder must not become
the answer to some sidecar's search. The date format is read loosely, as N1
allows -- a leading "YYYY-MM-DD" is enough, with or without the weekday and
the time. A day folder that never gained a time is still a day folder.

For sidecars, placement is the migration section 6 asks for: everything that
writes the archive already honours X10, so what is left over is the ones
written before it. For previews it is the first routing they have ever had --
nothing has moved a ".thm" anywhere -- so they are still lying where the camera
wrote them, named after the subject's *stem* rather than its full name. Those
are matched by stem and renamed onto X1 as they move: "GX010042.LRV" becomes
"GX010042.MP4.lrv" in "__PREVIEWS". A stem shared by two subjects is not
knowable, so that preview is left where it is.

A companion whose subject cannot be found is **left exactly where it is** and
reported. It is the only surviving record that the subject existed (X3), and
moving it on a guess would lose the one thing it still says.

None of the three is implemented here. All are ``companion_matching.py``, the
same module the pipeline's companion-reconciliation stage runs -- see its
docstring for why it is a module rather than part of the stage. This tool
supplies only what a maintenance run needs and a pipeline run does not: a mover
that records instead of writing so a dry run can report (T3), the project's
chunked checksum, and pruning turned off while it reports.

Folders that fit no shape
-------------------------
Anything the walk meets that is neither a dated folder, nor an allowed
subfolder, nor a holding area, nor a recognised legacy container is collected
and printed **at the end of the run, in red**. A structural problem noticed
halfway through a rename report scrolls past; these are the one part of the
output somebody has to act on by hand. Reported, never fixed -- what to do with
a folder the standard does not describe is a decision, and steps 6 and 7 are
where that will live once the standard leaves draft.

A dry run does each thing once
------------------------------
Steps 4 and 5 repeat 2 and 1 to clean up after the grouper. In a dry run the
grouper never opens, so nothing has changed between the passes and the second
would print the first's report word for word. Those are skipped, with a line
saying why. Asked for on their own (``--steps 5``) they still run: nothing came
before them to repeat.

Steps 6 and 7 are placeholders
------------------------------
``ARCHIVE_STANDARD.md`` is **v0.8, a draft, enforced by nothing** -- its S4
subfolder set and its T8 "defined more than once" list still carry open
questions whose answers change what "compliant" means. Enforcing it now would
migrate a live archive of hundreds of thousands of files to a shape that is
still being argued about. So both steps announce themselves and do nothing;
the plumbing -- ordering, prompting, journalling, exit codes -- is here so
that implementing them is a change to one function each, against the
specification in that document's section 7.

TARGETS
-------
The default target is the canonicaliser's: the year folder under the
configured archive root (``paths.root_folder`` in config.json), chosen with
``--year``. Beyond that, anything can be named explicitly::

    (no target)                       <root_folder>\<year>
    "d:\__PHOTOS_BACKUP" --year 2024  a year tree on another local disk
    "d:\__PHOTOS_BACKUP"              a whole archive root: every year tree
    "\\NAS\PhotoBackup" --year 2024   the same, on a network device
    "z:\Photos\2024\07. July\..."     any folder inside an archive

Naming an **archive root** -- a folder holding year folders -- restricts the
run to those year trees, because rule P1 of the standard, and its section 0,
put everything else at a root ("____INGEST_PIPELINE", "____TO_SORT") out of
scope. A tool that walked into the ingest pipeline would be renaming files
still in flight.

SAFETY
------
The archive is the only copy of some of these photographs, and a network
target multiplies every way a run can go wrong. This tool therefore:

  * **reports; it changes nothing** without ``--apply``. A dry run lists the
    renames the canonicaliser would make and the folders the GUI would be
    opened on, and touches neither;
  * **refuses a target that does not look like an archive** -- one that is
    neither a year folder, nor inside one, nor holds any -- so a mistyped path
    or a bare drive letter stops here rather than at the first rename
    (``--force-target`` overrides, deliberately awkwardly);
  * **resolves a mapped drive letter to its UNC once, up front**, and hands
    every step the resolved path, so a letter remapped mid-run cannot
    re-point the rest of it at a different server (``--keep-drive-letter``
    opts out);
  * **never follows a reparse point** -- junction, symlink, mount point --
    when scanning for folders to group, and reports each one it refused, so a
    junction planted on a share cannot walk the run out of the target tree;
  * **re-checks every folder immediately before opening the GUI on it**: still
    inside the resolved root, still not a reparse point, still a directory. A
    folder can be renamed or split away by the previous window in the batch;
  * **moves a companion with ``os.rename``**, never ``os.replace`` and never a
    copy-and-delete, so an unexpected collision fails loudly instead of
    destroying the file it lands on (T2), and never over an existing file: a
    companion already at its destination is left where it is and reported;
  * **will not run an interpreter off the network.** The grouper is launched
    from the paths in config.json, and if either sits on a share or a mapped
    drive the run stops: an executable on a share is an executable somebody
    else can replace between one folder and the next
    (``--allow-network-tool`` overrides);
  * **passes folder names as an argument vector**, never through a shell, so
    an event somebody labelled with an ampersand reaches the GUI as a name;
  * **asks before it writes** to a network target, and refuses to apply at all
    with no terminal to ask at unless ``--yes`` says the run is unattended;
  * **handles no credentials of any kind.** Authenticating a share is the
    operating system's job, and this tool will not accept a password.

Every applied run appends to a journal recording what each step did and which
folders were opened. The canonicaliser writes its own rename journal per year
tree, and ``--undo`` on that tool replays those renames backwards; step 3 is
not undoable, because what the GUI does inside a folder is the user's own
work.

Nothing here redefines a convention. The steps, the path-safety primitives and
the config reader are loaded from ``tools/canonicalise_timestamp_names.py``,
the "__TO_SPLIT__" marker from ``src/pipeline_stages/grouping_names.py``, the
grouper's location and command line from
``src/pipeline_stages/grouper_launch.py``, and the whole of reconciliation
from ``src/pipeline_stages/companion_matching.py`` -- without going through
``import src.pipeline_stages...``, because that package's ``__init__`` imports
every pipeline stage (exiftool, dashboard, converters) and a maintenance tool
must run on a bare interpreter with none of that installed. See
``load_leaf_package`` for how the last of those is reached.

Usage:
    python tools/restructure_archive.py [TARGET] [--year YYYY] [--apply]
    python tools/restructure_archive.py [TARGET] --steps 2,4 --apply
    python tools/restructure_archive.py [TARGET] --list-to-split

Exit codes: 0 = nothing left to do, 1 = changes pending or failures, 2 = error.
"""

import argparse
import datetime
import importlib
import importlib.machinery
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICALISE_TOOL_PATH = REPO_ROOT / "tools" / "canonicalise_timestamp_names.py"
PIPELINE_STAGES_DIR = REPO_ROOT / "src" / "pipeline_stages"
GROUPER_LAUNCH_MODULE_PATH = PIPELINE_STAGES_DIR / "grouper_launch.py"
STANDARD_PATH = REPO_ROOT / "ARCHIVE_STANDARD.md"

# A year folder: exactly four digits and nothing else (ARCHIVE_STANDARD P2).
YEAR_FOLDER_RE = re.compile(r"^\d{4}$")

# What a confirmation wants typed. A word, not "y": the point of the prompt is
# that the path printed above it has been read.
CONFIRM_WORD = "APPLY"

OK, SKIPPED, FAILED, PENDING = "OK", "SKIPPED", "FAILED", "PENDING"


def load_leaf_package():
    """Make ``src.pipeline_stages``' leaf modules importable, without its ``__init__``.

    ``companion_matching`` is the reconciliation engine, and unlike the other
    leaf modules it is not self-contained: it imports ``stamps``, ``taxonomy``
    and ``grouping_names`` the ordinary way. Loading it by bare file path would
    execute those imports, and ``src.pipeline_stages.__init__`` imports every
    pipeline stage -- exiftool, the dashboard, the converters -- which a
    maintenance tool must run without.

    So instead of loading the module out of its package, this puts a stub of
    the package in ``sys.modules`` first. The import machinery finds the parent
    already present, never runs either ``__init__``, and resolves
    ``from src.pipeline_stages.stamps import ...`` normally against the real
    file. The engine stays a plain readable module with plain imports, and this
    tool still starts on a bare interpreter.
    """
    for name, folder in (("src", REPO_ROOT / "src"),
                         ("src.pipeline_stages", PIPELINE_STAGES_DIR)):
        if name in sys.modules:
            continue
        spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
        module = importlib.util.module_from_spec(spec)
        module.__path__ = [str(folder)]
        sys.modules[name] = module
    return importlib.import_module("src.pipeline_stages.companion_matching")


def load_module(name, path):
    """Load a module by file path, without importing its package."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("Cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The canonicaliser is both step 1/3 and this tool's library of path-safety
# primitives -- extended_path, drive_is_network, resolve_target,
# walk_bottom_up, path_key, inside, is_reparse_point, colourise, and the config
# readers. One definition of each, in the tool that already had to get them
# right for the same targets.
canonicalise = load_module("canonicalise_timestamp_names", CANONICALISE_TOOL_PATH)
grouper = load_module("photosorter_grouper_launch", GROUPER_LAUNCH_MODULE_PATH)

# The companion-matching engine the pipeline stage runs, used here unchanged --
# see its module docstring, and T8. Steps 2 and 4 are this module; nothing
# about which file follows which representative is decided in this tool.
matching = load_leaf_package()
# The taxonomy folder names, read rather than spelled here (S4).
taxonomy = importlib.import_module("src.pipeline_stages.taxonomy")

# The grouping marker's grammar, already loaded by the canonicaliser from
# src/pipeline_stages/grouping_names.py.
TO_SPLIT_MARKER = canonicalise.grouping.TO_SPLIT_MARKER

colourise = canonicalise.colourise
extended_path = canonicalise.extended_path
path_key = canonicalise.path_key
inside = canonicalise.inside


# --------------------------------------------------------------------------
# Target resolution
# --------------------------------------------------------------------------

def path_is_reparse_point(path):
    """True for a junction, symlink or mount point at ``path``.

    The canonicaliser's check takes a ``DirEntry`` from its own walk; this is
    the same test for a path handed in from outside it. It reads the reparse
    tag rather than asking ``is_symlink()``, because on Windows a **junction**
    is not a symlink: ``Path.is_symlink()`` and ``os.path.islink()`` both say
    False for one, and a junction is exactly what would be planted on a share
    to walk a run out of the tree it was pointed at.
    """
    try:
        status = os.lstat(extended_path(path))
    except OSError:
        return True                            # unreadable: treat as untrusted
    tag = getattr(status, "st_reparse_tag", 0)
    if tag:
        return True
    return os.path.islink(str(path))           # non-Windows


def year_children(folder):
    """The year folders directly inside ``folder``, oldest first.

    A reparse point is never among them: a junction named "2019" is exactly
    the trick this tool must not fall for.
    """
    found = []
    try:
        with os.scandir(extended_path(folder)) as scan:
            for entry in scan:
                if not YEAR_FOLDER_RE.fullmatch(entry.name):
                    continue
                if canonicalise.is_reparse_point(entry):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        found.append(Path(folder) / entry.name)
                except OSError:
                    continue
    except OSError:
        return []
    return sorted(found, key=lambda path: path.name)


def looks_like_an_archive(folder):
    """True when ``folder`` is a year tree, sits inside one, or holds some.

    The guard against a mistyped or simply wrong path. Deliberately shallow --
    it asks where the folder sits, not what is in it -- because the point is
    to stop before the walk, not to validate the archive.
    """
    resolved = Path(os.path.abspath(str(folder)))
    if any(YEAR_FOLDER_RE.fullmatch(part) for part in resolved.parts):
        return True
    return bool(year_children(resolved))


def scan_roots(target, report):
    """The trees to work on: the target, or its year folders if it is a root.

    ARCHIVE_STANDARD P1 and its section 0: at an archive root only the year
    trees are governed, and a tool must not descend into "____INGEST_PIPELINE"
    or "____TO_SORT", which hold files still in flight.
    """
    if YEAR_FOLDER_RE.fullmatch(target.name):
        return [target]
    years = year_children(target)
    if not years:
        return [target]
    report("dim", "Archive root: restricted to its %d year tree(s) -- %s"
                  % (len(years), ", ".join(path.name for path in years)))
    return years


def resolve_run_target(args, report):
    """``(target, error_message)``: the folder to work on, fully checked.

    Every check that can refuse a run happens here, before any step is
    entered, so a bad target costs nothing and a good one is resolved once.
    """
    if args.target:
        target = Path(args.target)
        # An explicit --year alongside an explicitly named root is how a
        # backup archive gets addressed: "\\NAS\PhotoBackup --year 2024".
        if args.year_given and (target / str(args.year)).is_dir():
            target = target / str(args.year)
    else:
        target = Path(canonicalise.configured_root_folder()) / str(args.year)

    if not target.is_dir():
        return None, "Target is not a folder: %s" % target

    if path_is_reparse_point(target):
        return None, "Target is a reparse point (junction/symlink): %s" % target

    if not looks_like_an_archive(target) and not args.force_target:
        return None, (
            "%s does not look like an archive: it is not a year folder, it is "
            "not inside one, and it holds none.\nNothing was touched. Check "
            "the path, or pass --force-target if this really is the tree you "
            "mean." % target)

    if canonicalise.drive_is_network(target):
        report("dim", "Target is on a network location.")
    return canonicalise.resolve_target(target, args.keep_drive_letter, report), None


# --------------------------------------------------------------------------
# Journal
# --------------------------------------------------------------------------

class Journal:
    """An append-only record of what an applied run did.

    Opened and closed around each write rather than held open, because it
    normally sits inside the target, where step 3's walk will meet it: a file
    this tool still had a handle on could not be renamed, and the canonicaliser
    would report that as a failure. Its own name is already canonical, so in
    practice nothing tries to.
    """

    def __init__(self, path):
        self.path = path

    def write(self, event, **fields):
        if self.path is None:
            return
        record = {"at": canonicalise.stamps.format_stamp(datetime.datetime.now()),
                  "event": event}
        record.update(fields)
        try:
            with open(extended_path(self.path), "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            # A journal that cannot be written must not end a run that is
            # otherwise fine; the console output is the primary record.
            self.path = None


# --------------------------------------------------------------------------
# Steps 1 and 3 -- canonicalise names
# --------------------------------------------------------------------------

def step_canonicalise(run, label):
    """Run the canonicaliser over each tree; return the worst exit code."""
    worst = 0
    for tree in run.trees:
        run.report("bold", "\n%s  %s" % (label, tree))
        # The target is already resolved -- resolving it a second time inside
        # the canonicaliser could only re-point it -- so whatever letter is
        # left is deliberately kept.
        argv = [str(tree), "--keep-drive-letter"]
        if run.apply:
            argv.append("--apply")
        if run.quiet:
            argv.append("--quiet")
        if not run.colour:
            argv.append("--no-colour")
        try:
            code = canonicalise.main(argv)
        except SystemExit as stop:              # argparse inside the tool
            code = stop.code if isinstance(stop.code, int) else 2
        except OSError as error:
            run.report(FAILED, "Canonicalise failed on %s: %s" % (tree, error))
            code = 2
        run.journal.write("canonicalise", tree=str(tree), exit_code=code)
        worst = max(worst, code)
    return worst


# --------------------------------------------------------------------------
# Step 2 -- group the __TO_SPLIT__ folders
# --------------------------------------------------------------------------

def find_to_split_folders(run):
    """Every folder still carrying the marker, oldest day first.

    The walk is the canonicaliser's: bottom-up, never leaving the tree it
    started in, never following a reparse point, reporting each one refused.
    """
    found, refused = [], []
    for tree in run.trees:
        root_key = path_key(tree)
        for directory, _files in canonicalise.walk_bottom_up(tree, root_key, refused):
            if TO_SPLIT_MARKER in directory.name:
                found.append(directory)
    for path, reason in refused:
        run.report("warn", "REFUSED %s: %s" % (path, reason))
    # Alphabetical is oldest-day-first, because every name opens with
    # "YYYY-MM-DD", and it is the order Explorer shows -- so it is always
    # obvious which folder the GUI is on and which are still to come.
    # Case-insensitive, to match Windows' own collation.
    found.sort(key=lambda path: str(path).lower())
    return found


def top_level_media(folder, settings):
    """``(images, videos)`` sitting directly in ``folder``; None if unreadable.

    Read off the top level and nowhere else, because that is exactly what the
    grouper GUI puts in front of the reviewer -- a thumbnail grid of the
    folder's own images and videos. It deliberately does **not** trust the
    ``i``/``v`` in the folder's name: the canonicaliser's ``folder_media``
    falls back to counting the whole subtree when the top level is bare, so a
    day whose every file sits in a subfolder is named
    ``__TO_SPLIT__(v=3)`` while having nothing to show at all.

    Subfolders are skipped rather than descended for the same reason, and a
    reparse point is skipped rather than followed.
    """
    names = []
    try:
        with os.scandir(extended_path(folder)) as scan:
            for entry in scan:
                if canonicalise.is_reparse_point(entry):
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                names.append(entry.name)
    except OSError:
        return None
    return canonicalise.grouping.count_media(
        names, settings.image_exts, settings.video_exts)


def partition_groupable(folders, run):
    """Split marked folders into the ones worth opening and the ones that are not.

    Returns ``(groupable, passed_over)`` -- ``[(folder, images, videos)]`` and
    ``[(folder, reason)]``.

    A folder can carry the marker and still have nothing for the GUI to do.
    The grouper was emptied into sub-events on an earlier pass; the day's
    files all sit in "__RAW" or a legacy "__VIDEOS"; the folder is one of the hollow
    ones parked in "__EMPTY_SUBFOLDERS" that the canonicaliser marks
    ``(EMPTY)``. Opening any of those puts an empty grid in front of the
    reviewer and waits for them to close it, which on a batch of ninety is the
    difference between a job and an afternoon.

    **Images and videos both count.** The grouper's own README describes its
    grid as "every image and video as a thumbnail", and the ``v`` half of the
    count bracket exists because videos are part of the review job -- so a
    video-only day at the top level is real work, not an empty window.
    """
    groupable, passed_over = [], []
    for folder in folders:
        counts = top_level_media(folder, run.grouping_settings)
        if counts is None:
            passed_over.append((folder, "cannot be listed"))
            continue
        images, videos = counts
        if images == 0 and videos == 0 and not run.open_all:
            passed_over.append((folder, "no image or video at its top level"))
            continue
        groupable.append((folder, images, videos))
    return groupable, passed_over


def report_passed_over(run, passed_over):
    """Say what was left unopened, and why, rather than dropping it silently."""
    if not passed_over:
        return
    run.report("warn", "%d marked folder(s) have nothing for the grouper to show:"
               % len(passed_over))
    for folder, reason in passed_over:
        run.report("dim", "    %s  (%s)" % (folder.name, reason))
    run.report("dim", "    The GUI shows a folder's top level only. "
                      "Pass --open-all to open these anyway.")


def grouper_paths(run):
    """``(python_exe, project_path)``, or None with the reason reported."""
    settings = canonicalise._config().get("screenshot_grouping", {})
    install = grouper.grouper_install(settings)
    if install is None:
        run.report("warn",
                   "The grouper is not installed on this machine "
                   "(screenshot_grouping.python = %r, .project_path = %r in "
                   "config.json)." % (settings.get("python", ""),
                                      settings.get("project_path", "")))
        return None
    python_exe, project_path = install
    if not run.allow_network_tool:
        for path in (python_exe, project_path):
            if canonicalise.drive_is_network(path):
                run.report(FAILED,
                           "The grouper lives on a network location (%s). An "
                           "executable on a share can be replaced between one "
                           "folder and the next, so it is not run from there."
                           "\nPass --allow-network-tool if that share is yours "
                           "and you trust it." % path)
                return None
    return python_exe, project_path


def still_safe_to_open(folder, run):
    """``None`` when the folder may be opened, otherwise why it may not.

    Re-checked immediately before each launch: the previous window in this
    same batch may have renamed the folder or split it away entirely, and a
    tree that was clean when it was scanned may not still be by the time the
    hundredth window closes.
    """
    if not any(inside(path_key(tree), folder) for tree in run.trees):
        return "no longer inside the target tree"
    if not folder.is_dir():
        return "no longer under that name (renamed or split by an earlier window)"
    if path_is_reparse_point(folder):
        return "reparse point (junction/symlink) not followed"
    # Asked again here, not just when the batch was planned: splitting a day
    # moves its files down into the sub-event folders, so a folder that had a
    # gridful when it was counted can have an empty top level by the time the
    # batch reaches it.
    if not run.open_all and top_level_media(folder, run.grouping_settings) == (0, 0):
        return "nothing left at its top level for the grouper to show"
    return None


def step_group(run):
    """Open the grouper on each marked folder, one at a time.

    A folder the GUI failed on is counted and the batch carries on: one bad
    folder must not cost the reviewer the other ninety.
    """
    marked = find_to_split_folders(run)
    if not marked:
        run.report("ok", "No folder carries the %s marker; nothing to group."
                   % TO_SPLIT_MARKER)
        return 0

    counted, passed_over = partition_groupable(marked, run)
    report_passed_over(run, passed_over)
    for folder, reason in passed_over:
        run.journal.write("group_passed_over", folder=str(folder), reason=reason)

    if not counted:
        run.report("ok", "\nNothing to group: all %d marked folder(s) have an "
                         "empty top level." % len(marked))
        return 0

    folders = [folder for folder, _images, _videos in counted]
    top_level = {path_key(folder): (images, videos)
                 for folder, images, videos in counted}

    if run.max_folders and len(folders) > run.max_folders:
        run.report("warn", "%d folder(s) carry the marker; limiting this run "
                           "to the first %d (--max-folders / "
                           "screenshot_grouping.max_folders). The rest stay "
                           "marked and come up on the next run."
                   % (len(folders), run.max_folders))
        folders = folders[:run.max_folders]

    run.report("bold", "\n%d folder(s) to group:" % len(folders))
    for folder in folders:
        images, videos = top_level[path_key(folder)]
        run.report("dim", "    %s  [%d image(s), %d video(s) at the top level]"
                   % (folder, images, videos))

    if not run.apply:
        run.report("ok", "\nDry run: the grouper was not opened. "
                         "Re-run with --apply.")
        return 1

    install = grouper_paths(run)
    if install is None:
        return 2
    python_exe, project_path = install

    if not run.confirm("Open the grouper on %d folder(s) under\n    %s"
                       % (len(folders), run.target)):
        run.report("warn", "Not confirmed; nothing was opened.")
        return 2

    opened = failures = skipped = 0
    for number, folder in enumerate(folders, start=1):
        reason = still_safe_to_open(folder, run)
        if reason is not None:
            run.report("dim", "[%d/%d] skipping %s: %s"
                       % (number, len(folders), folder.name, reason))
            run.journal.write("group_skipped", folder=str(folder), reason=reason)
            skipped += 1
            continue

        run.report("bold", "[%d/%d] %s" % (number, len(folders), folder.name))
        run.journal.write("group_opened", folder=str(folder))
        try:
            result = grouper.run_grouper(python_exe, project_path, folder)
        except OSError as error:
            run.report(FAILED, "    ! could not launch the grouper: %s" % error)
            run.journal.write("group_failed", folder=str(folder), error=str(error))
            failures += 1
            continue
        if result.returncode != 0:
            # The bare exit code says nothing about what went wrong -- the
            # grouper's own message only reaches its stderr.
            run.report(FAILED, "    ! grouper exited with code %d"
                       % result.returncode)
            run.report("dim", "      command: %s" % subprocess.list2cmdline(
                grouper.grouper_command(python_exe, project_path, folder)))
            for line in grouper.stderr_tail(result.stderr):
                run.report("dim", "      %s" % line)
            run.journal.write("group_failed", folder=str(folder),
                              exit_code=result.returncode)
            failures += 1
            continue
        run.journal.write("group_closed", folder=str(folder))
        opened += 1

    run.report("bold", "\n%d folder(s) grouped, %d skipped, %d failure(s)."
               % (opened, skipped, failures))
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Steps 2 and 4 -- reunite companions with their subjects
# --------------------------------------------------------------------------

def dated_folders(run):
    """Every dated folder under the target, parents before children.

    A dated name is what marks an event folder (N1); a month folder
    ("07. July") and a taxonomy subfolder are not dated and are skipped. The
    walk is the canonicaliser's, so a reparse point is refused here exactly as
    it is everywhere else (T4).
    """
    found, refused = [], []
    for tree in run.trees:
        root_key = path_key(tree)
        for directory, _files in canonicalise.walk_bottom_up(tree, root_key, refused):
            if path_key(directory) == root_key:
                continue
            if canonicalise.stamps.day_prefix(directory.name):
                found.append(directory)
    for path, reason in refused:
        run.report("warn", "REFUSED %s: %s" % (path, reason))
    # Sorting the paths puts a parent before its children, which is the order
    # the two passes want: companions are distributed out of the event folder
    # the grouper was opened on, and sidecars are placed from the top down.
    found.sort(key=lambda path: str(path).lower())
    return found


def archive_mover(run):
    """The move the engine performs, or a recorder when this is a dry run.

    Applying goes through the canonicaliser's ``rename_path``: ``os.rename``,
    never ``os.replace``, so an unexpected collision fails loudly instead of
    destroying the file it lands on (T2), retried so a dropped SMB handle does
    not strand a folder half-reconciled.
    """
    if not run.apply:
        def record(source, target):
            run.planned.append((Path(source), Path(target)))
            return Path(target)
        return record

    attempts, delay_seconds = canonicalise.configured_retry()

    def move(source, target):
        target = Path(target)
        os.makedirs(extended_path(target.parent), exist_ok=True)
        return canonicalise.rename_path(source, target, attempts, delay_seconds)
    return move


def archive_checksum(run):
    """The MD5 the placement pass compares two same-named companions with.

    Chunked, at the size ``safety.hash_chunk_size`` configures, because a
    sidecar is small but a ".lrv" proxy is not and this runs over a share.
    """
    chunk_size = canonicalise._config().get("safety", {}).get(
        "hash_chunk_size", 1024 * 1024)

    def checksum(path):
        return matching.default_checksum(Path(path), chunk_size)
    return checksum


def tree_of(folder, run):
    """The run tree ``folder`` sits in, or the first tree as a fallback."""
    key = path_key(folder)
    for tree in run.trees:
        if inside(path_key(tree), folder):
            return tree
    return run.trees[0]


def duplicates_folder(folder, run, config):
    r"""Where a companion that lost a name collision is parked.

    One per year tree -- ``<year>\__DUPLICATES`` -- so a whole year's collision
    losers land in a single place to review, rather than being scattered one
    per event folder. Chosen from the *subject's* tree, so a run over several
    years parks each year's losers under that year instead of pooling them.

    This is a deliberate extension of section 4, which puts ``__DUPLICATES``
    inside a dated folder; see the tool's module docstring.

    The name itself is read from the taxonomy, never spelled here (S4).
    """
    return Path(tree_of(folder, run)) / taxonomy.taxonomy_folder(config, "duplicates")


def step_reconcile(run, label):
    """Migrate the legacy containers, reunite companions, place every one of them.

    Three passes, in this order and no other:

    1. ``migrate_legacy_containers`` -- ``##   EXIFs   ##`` becomes ``__EXIF``
       and ``##   RAWs   ##`` becomes ``__RAW``, so everything after this reads
       one set of folder names instead of two.
    2. ``reconcile_folder``, per dated folder -- the engine the pipeline stage
       runs. A companion left behind in an event folder's taxonomy subdir
       follows the representative the grouper moved into a sibling sub-event,
       matched on capture time because the representative has been renamed
       since.
    3. ``place_companions``, over the **whole target at once** -- gather every
       subject and every companion, then distribute. A sidecar goes into the
       ``__EXIF`` directly inside the folder holding its subject (X10), a
       preview into that folder's ``__PREVIEWS`` (X13), matched on name because
       a companion carries its subject's full name (X1).

    The order is the dependency order. Migration first, because a companion
    still sitting in ``##   EXIFs   ##`` is in a folder the later passes would
    have to know two names for. Reconciliation next, because it moves
    *subjects*: a RAW still in the wrong event folder has no business having
    its sidecar placed beside it yet. Placement last, once every file is in the
    folder it belongs to, to say where in that folder each companion goes.
    """
    folders = dated_folders(run)
    if not folders:
        run.report("ok", "No dated folder found; nothing to reconcile.")
        return 0

    config = canonicalise._config()
    move = archive_mover(run)
    checksum = archive_checksum(run)
    run.planned = []
    migration = matching.MigrationReport()
    companions = matching.ReconcileReport()
    placement = matching.PlacementReport()

    run.report("bold", "%s %d dated folder(s) in %d tree(s)"
               % (label, len(folders), len(run.trees)))

    def log(message):
        run.report("dim", "  %s" % message.strip())

    # 1 -- the legacy containers. Found by the same walk that indexes the tree,
    # so this asks for an index first and then acts on what it named.
    survey = matching.survey_trees(run.trees, config, log)
    if survey.legacy_containers:
        try:
            migration.merge(matching.migrate_legacy_containers(
                survey.legacy_containers, config,
                lambda folder: duplicates_folder(folder, run, config), log,
                move=move, checksum=checksum))
        except Exception as error:
            run.report(FAILED, "  ! migrating legacy containers failed: %r" % error)
            migration.errors += 1

    # 2 -- companions after their representative, per event folder.
    for folder in folders:
        def folder_log(message, folder=folder):
            run.report("dim", "  %s: %s" % (folder.name, message.strip()))
        try:
            companions.merge(matching.reconcile_folder(
                folder, config, folder_log, move=move, prune=run.apply))
        except Exception as error:        # never abandon the rest of the tree
            run.report(FAILED, "  ! reconciling %s failed: %r" % (folder.name, error))
            companions.errors += 1

    # 3 -- placement, over every tree at once so a sidecar stranded anywhere in
    # the target can still find its subject.
    try:
        placement.merge(matching.place_companions(
            run.trees, config, lambda folder: duplicates_folder(folder, run, config),
            log, move=move, checksum=checksum, prune=run.apply))
    except Exception as error:
        run.report(FAILED, "  ! placing companions failed: %r" % error)
        placement.errors += 1

    if not run.apply:
        for source, target in run.planned:
            run.report("dim", "    %s\n    ->  %s" % (source, target))

    if migration.seen:
        run.report("bold", "\nLegacy containers: %s" % migration.summary())
    run.report("bold", "\nCompanions following their representative: %s"
               % companions.summary())
    run.report("bold", "Companion placement (X10/X13): %s" % placement.summary())
    run.report("dim", "%d media file(s) indexed" % placement.media)

    # Everything the run saw and did not settle, gathered where it can be read
    # rather than scrolled back to.
    run.non_compliant.extend(placement.non_compliant)
    for path, key in survey.legacy_containers:
        if key is None:
            run.non_compliant.append(
                (path, "legacy container with no modern equivalent; "
                       "its contents are a decision for a person"))

    if placement.needs_attention:
        run.report("warn", "\n%d thing(s) want a look: %s" % (
            placement.needs_attention,
            ", ".join(
                "%d %s" % (value, text) for text, value in (
                    ("with DIFFERENT bytes at the destination",
                     placement.parked_differing),
                    ("with no subject anywhere", placement.orphaned),
                    ("whose subject is ambiguous", placement.ambiguous),
                    ("media with no sidecar", placement.media_without_sidecar),
                    ("errors", placement.errors),
                ) if value)))

    if not run.apply and run.planned:
        run.report("ok", "\n%d file(s) to move. Nothing was changed. Re-run "
                         "with --apply." % len(run.planned))

    run.journal.write("reconcile", folders=len(folders),
                      legacy_renamed=migration.renamed,
                      legacy_merged=migration.merged,
                      legacy_files_moved=migration.files_moved,
                      legacy_parked=migration.parked,
                      companions_moved=companions.moved,
                      companions_left=companions.left_behind,
                      placed=placement.moved,
                      placed_across_folders=placement.across_folders,
                      parked_duplicate=placement.parked_duplicate,
                      parked_differing=placement.parked_differing,
                      orphaned=placement.orphaned,
                      ambiguous=placement.ambiguous,
                      media=placement.media,
                      media_without_sidecar=placement.media_without_sidecar,
                      non_compliant=len(placement.non_compliant),
                      errors=(companions.errors + placement.errors
                              + migration.errors))

    if companions.errors or placement.errors or migration.errors:
        return 1
    if not run.apply and run.planned:
        return 1
    return 0


# --------------------------------------------------------------------------
# Steps 6 and 7 -- compliance with the archive standard
# --------------------------------------------------------------------------

_STANDARD_NOTICE = (
    "%s is v0.1, a DRAFT, enforced by nothing: its S4 subfolder set and its T8 "
    "'defined more than once' list still carry open questions, and the answers "
    "change what counts as compliant. Enforcing it now would migrate a live "
    "archive to a shape that is still being argued about.\nThis step is a "
    "placeholder and does nothing. 'The fixing tool' under section 7 of that "
    "document is the specification it will be built to, and section 8 is the "
    "machine-readable form it will parse." % STANDARD_PATH.name)


def step_standard_check(run):
    run.report("warn", "NOT IMPLEMENTED -- " + _STANDARD_NOTICE)
    run.journal.write("standard_check", status="not_implemented")
    return 0


def step_standard_fix(run):
    run.report("warn", "NOT IMPLEMENTED -- " + _STANDARD_NOTICE)
    run.report("dim", "When it exists it will prompt before changing anything, "
                      "the way step 2 does.")
    run.journal.write("standard_fix", status="not_implemented")
    return 0


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

# number, title, action, and the step this one repeats (None for a first pass).
#
# A repeat exists to clean up after the step between the two -- the grouper. In
# a dry run the grouper never opens, so nothing has changed between the passes
# and the second would print the first's report word for word. Those are
# skipped, with a line saying why, unless asked for on their own.
STEPS = (
    (1, "Canonicalise names",
     lambda run: step_canonicalise(run, "Canonicalising"), None),
    (2, "Reunite companions and sidecars",
     lambda run: step_reconcile(run, "Reconciling"), None),
    (3, "Group the %s folders" % TO_SPLIT_MARKER, step_group, None),
    (4, "Reunite companions and sidecars again",
     lambda run: step_reconcile(run, "Reconciling (again)"), 2),
    (5, "Canonicalise names again",
     lambda run: step_canonicalise(run, "Canonicalising (again)"), 1),
    (6, "Check compliance with the archive standard", step_standard_check, None),
    (7, "Fix compliance with the archive standard", step_standard_fix, None),
)


def report_non_compliant(run, colour):
    """The last thing the run prints: folders that fit no allowed shape.

    In red, at the end, and nowhere else. A structural problem noticed halfway
    through a rename report scrolls past; the point of gathering them is that
    they are the one part of the output somebody has to act on by hand.

    Reported, never fixed. What to do with a folder the standard does not
    describe is a decision, and steps 6 and 7 are where that will live once the
    standard leaves draft.
    """
    if not run.non_compliant:
        return
    print()
    print(colourise("NON-COMPLIANT FOLDERS  (%d) -- reported, not touched"
                    % len(run.non_compliant), FAILED, colour))
    seen = set()
    for path, reason in sorted(run.non_compliant, key=lambda item: str(item[0]).lower()):
        if path_key(path) in seen:
            continue
        seen.add(path_key(path))
        print(colourise("  %s" % path, FAILED, colour))
        print(colourise("      %s" % reason, "dim", colour))


class Run:
    """Everything the steps share: the target, the switches, the reporting."""

    def __init__(self, args, target, trees, colour):
        self.target = target
        self.trees = trees
        self.apply = args.apply
        self.quiet = args.quiet
        self.colour = colour
        self.assume_yes = args.yes
        self.allow_network_tool = args.allow_network_tool
        self.max_folders = args.max_folders
        self.open_all = args.open_all
        # The extension sets that say what counts as an image or a video, read
        # once from the same config the pipeline uses.
        self.grouping_settings = canonicalise.GroupingSettings(canonicalise._config())
        # Where a dry run's reconcile step collects the moves it would make.
        self.planned = []
        # Folders that fit none of the shapes the standard allows, gathered as
        # the run goes and printed together at the end (in red) rather than
        # scrolling past in the middle of a rename report.
        self.non_compliant = []
        self.journal = Journal(None)

    def report(self, key, message):
        if self.quiet and key not in ("warn", "bold", FAILED):
            return
        print(colourise(message, key, self.colour))

    def confirm(self, question):
        """Ask, and mean it: only the confirmation word is a yes.

        ``--yes`` is for an unattended run and is the only way past this with
        no terminal attached -- a script that piped its way through a
        confirmation would make the confirmation decorative.
        """
        if self.assume_yes:
            return True
        if not (sys.stdin and sys.stdin.isatty()):
            self.report(FAILED, "No terminal to confirm at. Re-run from a "
                                "console, or pass --yes for an unattended run.")
            return False
        print(colourise("\n" + question, "bold", self.colour))
        try:
            answer = input("Type %s to continue: " % CONFIRM_WORD)
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        return answer.strip() == CONFIRM_WORD


def selected_steps(text):
    """``--steps 1,3`` -> the step numbers to run, in their fixed order."""
    numbers = [number for number, _, _, _ in STEPS]
    if not text:
        return numbers
    wanted = set()
    for piece in text.replace(" ", "").split(","):
        if not piece:
            continue
        if not piece.isdigit() or int(piece) not in numbers:
            raise argparse.ArgumentTypeError(
                "%r is not a step number (1-%d)" % (piece, len(STEPS)))
        wanted.add(int(piece))
    # Fixed order regardless of how they were typed: "3,1" still canonicalises
    # before it canonicalises again.
    return [number for number in numbers if number in wanted]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="restructure_archive",
        description="Bring an existing photo archive onto the current naming "
                    "and structure conventions.",
        epilog="Nothing is changed without --apply.")
    parser.add_argument("target", nargs="?", default=None,
                        help="year tree, archive root, or any folder inside "
                             r"one; local or UNC (default: <root_folder>\<year>)")
    parser.add_argument("--year", type=int, default=canonicalise.DEFAULT_YEAR,
                        help="year tree to work on, under the configured root "
                             "or under an explicitly named root "
                             "(default: %(default)s)")
    parser.add_argument("--apply", action="store_true",
                        help="make the changes; without it this only reports")
    parser.add_argument("--steps", default=None, metavar="N[,N...]",
                        help="run only these steps (default: all of 1-%d)"
                             % len(STEPS))
    parser.add_argument("--list-to-split", action="store_true",
                        help="list the folders step 2 would open, and stop")
    parser.add_argument("--open-all", action="store_true",
                        help="open every marked folder, including those with "
                             "no image or video at their top level for the "
                             "grouper to show")
    parser.add_argument("--max-folders", type=int, default=None,
                        help="open the grouper on at most this many folders "
                             "(default: screenshot_grouping.max_folders, "
                             "0 for no limit)")
    parser.add_argument("--yes", action="store_true",
                        help="answer every confirmation; for unattended runs")
    parser.add_argument("--force-target", action="store_true",
                        help="work on a target that does not look like an archive")
    parser.add_argument("--allow-network-tool", action="store_true",
                        help="run the grouper even though its interpreter or "
                             "project sits on a network location")
    parser.add_argument("--keep-drive-letter", action="store_true",
                        help="do not pin a mapped network drive to its UNC")
    parser.add_argument("--journal", default=None,
                        help="where to record what an applied run did "
                             "(default: a dated file inside the target)")
    parser.add_argument("--quiet", action="store_true",
                        help="only print each step's headline and summary")
    parser.add_argument("--no-colour", action="store_true")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    # Which of the two ways the year arrived matters: an explicit --year
    # alongside an explicitly named root means "that year of that archive",
    # while the default year must not silently redirect a named target.
    args.year_given = any(item == "--year" or item.startswith("--year=")
                          for item in argv)
    colour = not args.no_colour and sys.stdout.isatty()

    def report(key, message):
        if args.quiet and key not in ("warn", "bold", FAILED):
            return
        print(colourise(message, key, colour))

    try:
        steps = selected_steps(args.steps)
    except argparse.ArgumentTypeError as error:
        print(colourise("Bad --steps: %s" % error, FAILED, colour))
        return 2

    target, error = resolve_run_target(args, report)
    if error:
        print(colourise(error, FAILED, colour))
        return 2

    trees = scan_roots(target, report)
    if args.max_folders is None:
        args.max_folders = canonicalise._config().get(
            "screenshot_grouping", {}).get("max_folders", 0) or 0

    run = Run(args, target, trees, colour)

    if args.list_to_split:
        marked = find_to_split_folders(run)
        counted, passed_over = partition_groupable(marked, run)
        for folder, images, videos in counted:
            print("%s  [i=%d v=%d]" % (folder, images, videos))
        print(colourise("\n%d folder(s) carry the %s marker; %d worth opening."
                        % (len(marked), TO_SPLIT_MARKER, len(counted)),
                        "bold", colour))
        report_passed_over(run, passed_over)
        return 1 if counted else 0

    report("bold", "%s %s" % ("Restructuring" if args.apply else "Dry run over",
                              target))
    report("dim", "Steps: %s" % ", ".join(str(number) for number in steps))

    if args.apply:
        if canonicalise.drive_is_network(target) and not run.confirm(
                "This will rename files on a NETWORK location:\n    %s" % target):
            print(colourise("Not confirmed; nothing was changed.", "warn", colour))
            return 2
        stamp = canonicalise.stamps.format_stamp(datetime.datetime.now())
        run.journal = Journal(Path(args.journal) if args.journal else
                              target / ("_restructure_journal_%s.jsonl" % stamp))
        run.journal.write("run_started", target=str(target),
                          trees=[str(tree) for tree in trees], steps=steps)

    outcomes = []
    worst = 0
    ran = set()
    for number, title, action, repeats in STEPS:
        if number not in steps:
            outcomes.append((number, title, SKIPPED))
            continue
        if not args.apply and repeats is not None and repeats in ran:
            # Nothing between the two passes changed anything, so the second
            # would report exactly what the first did.
            report("dim", "\nSTEP %d -- %s: skipped, a dry run leaves nothing "
                          "for a second pass to find (step %d already reported "
                          "it)." % (number, title, repeats))
            outcomes.append((number, title, SKIPPED))
            continue
        report("bold", "\n" + "=" * 60)
        report("bold", "STEP %d -- %s" % (number, title))
        report("bold", "=" * 60)
        code = action(run)
        ran.add(number)
        worst = max(worst, code)
        outcomes.append((number, title, {0: OK, 1: PENDING}.get(code, FAILED)))
        if code == 2:
            # An error is a stopped run: step 3 has nothing to tidy up after a
            # step 2 that never opened anything, and step 1 failing at all
            # means the target itself is wrong.
            report(FAILED, "\nStep %d could not run; stopping here." % number)
            break

    print()
    report("bold", "SUMMARY  (%s)" % ("applied" if args.apply else "dry run"))
    for number, title, outcome in outcomes:
        key = {OK: "ok", PENDING: "warn", SKIPPED: "dim"}.get(outcome, FAILED)
        print("  %s  %s" % (colourise("%-7s" % outcome, key, colour),
                            "%d. %s" % (number, title)))
    report_non_compliant(run, colour)

    if run.journal.path is not None:
        run.journal.write("run_finished", exit_code=worst,
                          non_compliant=len(run.non_compliant))
        print(colourise("\nJournal: %s" % run.journal.path, "dim", colour))
    if not args.apply and worst == 1:
        print(colourise("\nNothing was changed. Re-run with --apply.", "ok", colour))
    return worst


if __name__ == "__main__":
    sys.exit(main())
