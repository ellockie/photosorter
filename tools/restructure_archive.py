r"""Bring an existing archive onto the current conventions, in one pass.

This is the front door for restructuring work: the eight steps that turn a tree
written by an older Photosorter, an older grouper or a third-party tool into
the shape ``ARCHIVE_STANDARD.md`` describes, run in the one order that makes
sense, over one target, with one set of safety rules.

    1. Canonicalise names and park the empty
                                   tools/canonicalise_timestamp_names.py
    2. Reunite companions and sidecars     companion_matching.py
    3. Group the "__TO_SPLIT__" folders, one at a time, in the grouper GUI
    4. Reunite companions and sidecars     companion_matching.py
    5. Canonicalise names and park again
                                   tools/canonicalise_timestamp_names.py
    6. Mark and time the groups    ARCHIVE_STANDARD.md section 3
    7. Check compliance with the archive standard      [not implemented]
    8. Fix compliance with the archive standard        [not implemented]

What steps 1 and 5 settle about a folder
----------------------------------------
Its **time**, and whether it still belongs in the month at all. Both come off
the same reading of what the folder holds, so they happen together.

N3 makes a folder's time an equality -- it *is* the capture time of the
folder's earliest file -- rather than a default, so a prefix that disagrees is
corrected and not merely filled in when blank. A day stamped before an earlier
pass moved its early shots into a sibling goes on naming a photograph that is
no longer in it. A group is not retimed here (C11 maintains both ends of its
span together), and neither is a folder whose earliest file is not a capture
that day may hold (N7) -- that one is reported MISTIMED, because one stray from
another year must not rewrite the name of a day that was right.

A folder that turns out to hold **no file anywhere** is parked in the
"__EMPTY_SUBFOLDERS" on its own level, which is where H4 says it belongs:
"parked rather than offered to a grouper", rather than left in the month for
every later run to notice again and pass over again. Empty means no files;
subfolders below it are not files, do not keep it out, and travel with it. What
the folder is called decides nothing -- marked, placeholdered or named by a
person, H3 parks it under its own name, so nothing a name recorded is lost.

The name is never the evidence for either. It records what some earlier run
found, so the folder is read off the disk before anything moves, over the same
walk that refuses a reparse point everywhere else (T4); a folder that cannot be
read in full is not called empty. Reading the disk is also what makes the park
visible in a dry run, before any "(EMPTY)" has been written: "--apply" is still
what moves anything.

Only the folders worth opening
------------------------------
Step 3 opens a marked folder only when it has an image or a video **at its top
level**, which is the whole of what the grouper's thumbnail grid shows. A
folder can carry the marker and still have nothing for it to do: an earlier
pass already split the day into sub-events, or the day's files all sit in
"__RAW" or a legacy "__VIDEOS". Opening one of those puts an empty grid in
front of the reviewer and waits for them to close it, and on a batch of ninety
that is the difference between a job and an afternoon. They are listed, with
the reason, rather than dropped silently; "--open-all" opens them anyway.

A folder holding nothing at all reaches step 3 only when step 1 was skipped or
could not park it -- a run of "--steps 3" alone, a folder with no level above
it allowed to hold a parking area (H2). It is passed over on the same grounds.

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

What step 6 does
----------------
Section 3 of the standard: a dated folder holding dated child folders is a
*group*, it says so in its tail -- "____GROUP____" -- and its prefix states
both ends of the span it covers, start stamp and "#end", each read off the
subtree. A folder that stopped holding dated children loses the marker and the
span again. It runs after step 5 because the grouper (step 3) creates and
destroys exactly those parent/child relationships, and after the second
canonicalise pass because that is what settles the child names the span is
computed from.

It rewrites only the marker and the two stamps. The date a group starts on is
never derived from its contents (N6), media is never moved out of a group (C4)
and no group is ever moved between month folders (C12): those are open
questions 4-6 in the standard, and a folder that runs into one is reported with
the rule number rather than changed.

What reconciliation does
------------------------
Six passes, in this order and no other:

  * ``hoist_parking_areas`` -- every nested ``__EMPTY_SUBFOLDERS`` is merged
    into the single parking area directly below its month folder. It runs
    first so parked days cannot re-enter any of the active-archive passes.
  * ``migrate_legacy_videos`` -- every video in a case-variant ``__VIDEOS``
    moves up beside the images when its filename or intrinsic metadata dates
    it. A genuinely undatable video is tagged and routed to
    ``__VIDEOS_TO_RENAME``; a metadata-reader failure leaves it untouched.
    Sidecars/previews travel with the subject, and the recursively verified
    empty legacy folder is parked below the month (V12/L4).
  * ``migrate_legacy_containers`` -- "##   EXIFs   ##" becomes "__EXIF" and
    "##   RAWs   ##" becomes "__RAW". Renamed outright where nothing of that
    name is there yet; where one is, each file moves across and a collision is
    settled by checksum. An emptied container is parked in the
    "__EMPTY_SUBFOLDERS" beside the dated folder it sat in -- one level up,
    since a leaf day is not a level a parking area may sit on (H2) --
    numbered when that name is taken. A
    container with no modern equivalent -- "old_EXIF", the three "FILES"
    holders -- is reported and never touched.
  * ``reconcile_folder`` -- a companion left in an event folder's taxonomy
    subdir follows the representative the grouper moved into a sibling
    sub-event. Matched on capture time, because the representative has been
    renamed since.
  * ``place_companions`` -- X10 and X13: a companion goes into the folder
    directly inside the one that holds its subject -- an "._exif" sidecar into
    "__EXIF", a ".thm" or ".lrv" preview into "__PREVIEWS". Canonical X1
    names match directly; historical EXIF names without the media extension
    match by stem and X10 location, then are renamed onto X1 (X1a).
  * ``generate_missing_raw_sidecars`` -- after tolerant matching has removed
    the false positives, every genuinely uncovered RAW is passed to ExifTool.
    Its canonical X1 sidecar is placed in the RAW folder's ``__EXIF`` (X14).

The order is the dependency order. Parking and legacy names are normalized
first. Reconciliation moves subjects; placement then settles every sidecar it
can read, including historical names. Only then is a RAW called genuinely
missing and given a newly extracted sidecar.

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

For sidecars, placement is the migration section 6 asks for. Older ``._exif``
files may omit the media extension or differ in extension case; those are read
case-insensitively, resolved by stem plus X10 location, and renamed onto X1.
Previews use the same stem fallback. A stem still shared by multiple candidates
at the same location is not knowable and is left for review.

A companion whose subject cannot be found is **left exactly where it is** and
reported. It is the only surviving record that the subject existed (X3), and
moving it on a guess would lose the one thing it still says.

The parking migration is ``parking.py``; matching is
``companion_matching.py``; legacy-video migration is ``legacy_videos.py``;
ExifTool invocation is the shared leaf ``exiftool_sidecars.py``. This tool
supplies only the archive-level ordering, dry-run/journal behavior and safe
moves.

Folders that fit no shape
-------------------------
Anything the walk meets that is neither a dated folder, nor an allowed
subfolder, nor a holding area, nor a recognised legacy container is collected
and printed **at the end of the run, in red**. A structural problem noticed
halfway through a rename report scrolls past; these are the one part of the
output somebody has to act on by hand. Reported, never fixed -- what to do with
a folder the standard does not describe is a decision, and steps 7 and 8 are
where that will live once the standard leaves draft.

What the output is shaped around
--------------------------------
A run prints thousands of lines, and two questions decide what happens next:
did this step leave anything for a person, and did the run as a whole succeed.
Neither survives being read out of a wall of renames, so neither is left in
one.

**Every step closes with a framed verdict** -- green when it left nothing, red
when it did, naming what it flagged. **The run closes with two frames and
nothing after them**: every issue it gathered, in full, grouped by kind; and
then the summary, with the verdict in a heavy box of its own. The summary is
last deliberately: whichever block is printed last is the one still on the
screen when the run ends.

An issue is anything the tool deliberately declined to settle -- a folder that
fits no shape, a reparse point it would not follow, a companion with no
subject, a group nobody has named, a step that did not finish. None of them is
fixed for you, and each is listed with the reason it was left.

**Every line this tool says itself is tagged " [restructure] " and cyan**, and
every line it relays from a tool it called -- the canonicaliser's rename
report, the grouper's stderr, the matching engine's log, ExifTool's -- is
neither. Run together they are a wall; told apart, "which of these was the
restructurer complaining about?" stops being a question. The tag is always the
same colour whoever is speaking about whatever: the colour says who, and the
message keeps whatever colour its own meaning earned, so an ``ok`` stays
green, a ``warn`` yellow and a failure red inside a cyan-tagged line.

The frames are box-drawing characters where the console can encode them and
ASCII where it cannot: this prints to whatever code page the machine happens
to have, and a ``UnicodeEncodeError`` raised while drawing the summary would
lose the very lines the frame exists to make unmissable. Colour goes to a
terminal only, and ``--no-colour`` turns it off; the frames stay either way,
because a redirected log needs the shape as much as a console does.

The verdict answers "is there anything left for me?"; the **exit code** answers
"did the tool do its work?" -- and they are not the same question. A run that
finds twenty folders the standard cannot describe did its work perfectly and
exits 0, with a red banner saying twenty things are waiting.

A dry run does each thing once
------------------------------
Steps 4 and 5 repeat 2 and 1 to clean up after the grouper. In a dry run the
grouper never opens, so nothing has changed between the passes and the second
would print the first's report word for word. Those are skipped, with a line
saying why. Asked for on their own (``--steps 5``) they still run: nothing came
before them to repeat.

Steps 6 and 7 are placeholders
------------------------------
``ARCHIVE_STANDARD.md`` is **v0.12, a draft, only partly enforced** -- its S4
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
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import NamedTuple

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
    for name, folder in (
        ("src", REPO_ROOT / "src"),
        ("src.pipeline_stages", PIPELINE_STAGES_DIR),
    ):
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
# Where an emptied folder is parked, and the hoist for one sitting somewhere
# H2 does not allow (H2/H6).
parking = importlib.import_module("src.pipeline_stages.parking")
# Dependency-free ExifTool command helpers used for missing RAW sidecars (X14).
exif_sidecars = importlib.import_module("src.pipeline_stages.exiftool_sidecars")
# The read-old/write-new migration for the legacy video container (S5/V1/V8).
legacy_videos = importlib.import_module("src.pipeline_stages.legacy_videos")

# The grouping marker's grammar, already loaded by the canonicaliser from
# src/pipeline_stages/grouping_names.py.
TO_SPLIT_MARKER = canonicalise.grouping.TO_SPLIT_MARKER

colourise = canonicalise.colourise
extended_path = canonicalise.extended_path
path_key = canonicalise.path_key
inside = canonicalise.inside


# --------------------------------------------------------------------------
# Frames -- the two lines of a run that somebody has to read
# --------------------------------------------------------------------------
#
# A run prints thousands of lines and two of them decide what happens next:
# did this step leave anything for a person, and did the run as a whole
# succeed. In a wall of renames both scroll past. So each step closes with a
# framed verdict, and the run closes with the issues it gathered and then the
# summary -- framed, coloured, and the last thing on the screen.
#
# Box-drawing characters where the console can encode them, ASCII where it
# cannot. This prints to whatever code page the machine happens to have, and a
# UnicodeEncodeError raised while drawing the summary would lose the very
# lines the frame exists to make unmissable.

FRAME_LIGHT = {
    "tl": "\u250c",
    "tr": "\u2510",
    "bl": "\u2514",
    "br": "\u2518",
    "h": "\u2500",
    "v": "\u2502",
}
FRAME_HEAVY = {
    "tl": "\u2554",
    "tr": "\u2557",
    "bl": "\u255a",
    "br": "\u255d",
    "h": "\u2550",
    "v": "\u2551",
}
FRAME_LIGHT_ASCII = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "-", "v": "|"}
FRAME_HEAVY_ASCII = {"tl": "+", "tr": "+", "bl": "+", "br": "+", "h": "=", "v": "|"}

GLYPHS = {"tick": "\u2714", "cross": "\u2716", "warn": "\u25b6", "dot": "\u2022"}
# Bracketed rather than spelled out: the summary already says OK or FAILED in
# the column beside the mark, and a glyph that repeats the word reads as a
# stutter ("OK OK  6. ...").
GLYPHS_ASCII = {"tick": "[+]", "cross": "[!]", "warn": "[~]", "dot": "*"}

# One column for the mark whichever set is in use, so the outcome words below
# each other line up: a box-drawing tick is one character wide and its ASCII
# stand-in is three.
GLYPH_WIDTH = 3

# Wide enough to hold a step title, narrow enough that the eye takes the box
# in as one shape rather than reading along it.
FRAME_MAX_WIDTH = 100
FRAME_MIN_WIDTH = 44

# Every frame stands two columns in from the left edge. A box flush against
# the edge of the window reads as part of the window; two columns of nothing
# are what make it read as a thing placed on the page, and they give the eye
# the vertical line to run down when several frames follow each other. Taken
# off the width rather than added to it, so a frame still fits the terminal it
# is indented inside.
FRAME_MARGIN = "  "

# How many items of one kind a step's own verdict lists before it stops. The
# end-of-run block lists every one of them; a step that flagged four hundred
# folders must not push its own headline off the screen.
STEP_VERDICT_ITEMS = 8


def console_can_print(text):
    """True when stdout's encoding can carry ``text``.

    Asked of the box characters and the glyphs before either is used, so a
    console on a legacy code page gets the ASCII frame instead of a traceback.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeError):
        return False
    return True


def frame_chars(heavy=False):
    if console_can_print(FRAME_LIGHT["h"] + FRAME_HEAVY["h"]):
        return FRAME_HEAVY if heavy else FRAME_LIGHT
    return FRAME_HEAVY_ASCII if heavy else FRAME_LIGHT_ASCII


def glyph(name):
    """The mark that goes with the frame -- and it goes with the frame.

    Asked against the box characters as well as the glyph itself, so a console
    that gets the ASCII frame gets the ASCII marks with it. A bullet is
    encodable on code pages that no box character survives, and one Unicode
    mark inside a box made of plus signs reads as a mistake.
    """
    if console_can_print(FRAME_LIGHT["h"] + FRAME_HEAVY["h"] + GLYPHS[name]):
        return GLYPHS[name]
    return GLYPHS_ASCII[name]


def frame_width():
    return max(
        FRAME_MIN_WIDTH,
        min(
            shutil.get_terminal_size((100, 24)).columns - 1 - len(FRAME_MARGIN),
            FRAME_MAX_WIDTH,
        ),
    )


def line(key, text, rendered=None):
    """One line of a frame: its colour, its text, and how to print it.

    ``text`` is what the box is measured against and ``rendered`` is what goes
    on the screen, so a line that colours only part of itself -- the outcome
    word of a summary row -- still pads to the right edge.
    """
    return (key, text, rendered)


def frame(title, lines, key, colour, heavy=False, closed=True):
    """Print ``lines`` inside a titled box drawn in ``key``'s colour.

    Each line keeps its own colour, so an OK and a FAILED read apart inside
    one box.

    ``closed=False`` leaves the right edge open, which is what a list of paths
    wants: the full path is the actionable half of an issue, and padding or
    truncating it to fit a box would make it uncopyable. A line too long for a
    closed box loses its right edge for the same reason, rather than the box
    losing its shape.
    """
    box = frame_chars(heavy)
    width = frame_width()
    head = box["tl"] + box["h"]
    if title:
        head += " %s " % title
    head += box["h"] * max(1, width - len(head) - 1) + box["tr"]
    print(FRAME_MARGIN + colourise(head, key, colour))

    edge = colourise(box["v"], key, colour)
    inner = width - 4  # "| " ... " |"
    for line_key, text, rendered in lines:
        body = rendered if rendered is not None else colourise(text, line_key, colour)
        if closed and len(text) <= inner:
            print(
                "%s%s %s%s %s"
                % (FRAME_MARGIN, edge, body, " " * (inner - len(text)), edge)
            )
        else:
            print("%s%s %s" % (FRAME_MARGIN, edge, body))
    print(
        FRAME_MARGIN
        + colourise(box["bl"] + box["h"] * (width - 2) + box["br"], key, colour)
    )


def banner(headline, detail, key, colour):
    """The verdict: one heavy box, centred, and nothing else near it.

    This is the last thing a run prints and the one line somebody reading over
    a shoulder should be able to act on -- so it says the outcome in words, in
    colour, inside a frame of its own, rather than leaving it to be inferred
    from an exit code.
    """
    box = frame_chars(heavy=True)
    width = frame_width()
    inner = width - 4
    edge = colourise(box["v"], key, colour)
    print(
        FRAME_MARGIN
        + colourise(box["tl"] + box["h"] * (width - 2) + box["tr"], key, colour)
    )
    for text, emphasis in (("", False), (headline, True), (detail, False), ("", False)):
        text = text[:inner]
        pad = inner - len(text)
        left = pad // 2
        body = colourise(text, key, colour)
        if emphasis and colour and text:
            body = "\033[1m" + body
        print(
            "%s%s %s%s%s %s"
            % (FRAME_MARGIN, edge, " " * left, body, " " * (pad - left), edge)
        )
    print(
        FRAME_MARGIN
        + colourise(box["bl"] + box["h"] * (width - 2) + box["br"], key, colour)
    )


# --------------------------------------------------------------------------
# Whose voice a line is in
# --------------------------------------------------------------------------
#
# This tool prints two kinds of line: the ones it says itself, and the ones it
# relays from a tool it called -- the canonicaliser, the grouper, the
# companion-matching engine, ExifTool. Told apart they are a run; run together
# they are a wall, and "which of these was the restructurer complaining about?"
# is a question somebody ends up asking at the wrong moment.
#
# So everything this tool says itself is tagged and cyan, and everything it
# relays is neither. The tag is the whole of the distinction and it is always
# the same colour, whatever the line means: the colour says who is speaking,
# the message keeps whatever colour its meaning already earned.
#
# ok / warn / FAILED mean something -- something finished, something wants a
# look, something broke -- and keep their green, yellow and red. "bold" and
# "dim" are emphasis rather than meaning, so those are the ones that become
# cyan: this tool speaking normally, loudly or quietly.
#
# The frames are exempt. A frame is already unmistakably this tool's, it is
# already coloured by what it is saying, and a tag inside a box would only
# take width away from the paths in it.

SPEAKER_TAG = " [restructure] "
SPEAKER_GUTTER = " " * len(SPEAKER_TAG)
SPEAKER_COLOUR = "\033[96m"  # bright cyan
SPEAKER_EMPHASIS = {"bold": "\033[1;96m", "dim": "\033[2;96m"}
COLOUR_OFF = "\033[0m"

# The keys whose colour is a statement about the message, not about the
# speaker, and which therefore survive being spoken by this tool.
MEANS_SOMETHING = ("ok", "warn", FAILED)


def speak(message, key, colour):
    """Render one of this tool's own lines: tagged, and cyan unless it means
    something else.

    A message that spans lines is tagged once and gutter-aligned after that,
    so a two-line rename report reads as one thing said rather than two. Blank
    lines stay blank: a spacer with a tag on it is not a spacer.
    """
    lines, tagged = [], False
    for text in message.split("\n"):
        if not text.strip():
            lines.append("")
            continue
        if key in MEANS_SOMETHING:
            body = colourise(text, key, colour)
        elif colour:
            body = SPEAKER_EMPHASIS.get(key, SPEAKER_COLOUR) + text + COLOUR_OFF
        else:
            body = text
        lines.append(
            "%s %s"
            % (
                (
                    (
                        SPEAKER_COLOUR + SPEAKER_TAG + COLOUR_OFF
                        if colour
                        else SPEAKER_TAG
                    )
                    if not tagged
                    else SPEAKER_GUTTER
                ),
                body,
            )
        )
        tagged = True
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Issues -- what a run leaves for a person
# --------------------------------------------------------------------------
#
# Every step reports as it goes, and every step's report scrolls. Flagging is
# what keeps a finding for the two places it will be read: the step's own
# closing frame, and the block at the end of the run. The step still reports
# it in place; the flag is what stops it being missed.
#
# A heading is a kind of problem, and its note says what the tool did about it
# -- which for all of these is "nothing", deliberately. None of them is a
# thing a tool can decide.

NON_COMPLIANT = "NON-COMPLIANT FOLDERS"
STEPS_FAILED = "STEPS THAT DID NOT FINISH"
REFUSED_PATHS = "PATHS REFUSED"
GROUPER_FAILURES = "FOLDERS THE GROUPER COULD NOT OPEN"
PASSED_OVER = "MARKED FOLDERS WITH NOTHING TO SHOW"
PARK_FAILURES = "EMPTY FOLDERS THAT COULD NOT BE PARKED"
RECONCILE_ERRORS = "RECONCILIATION ERRORS"
WANTS_A_LOOK = "COMPANIONS AND SIDECARS THAT WANT A LOOK"
AWAITING_A_NAME = "GROUPS NOBODY HAS NAMED"
RENAME_FAILURES = "FOLDERS THAT COULD NOT BE RENAMED"

ISSUE_NOTES = {
    NON_COMPLIANT: "reported, never fixed -- what to do with a folder the "
    "standard does not describe is a decision for a person",
    STEPS_FAILED: "the run stopped here; whatever follows a stopped step " "never ran",
    REFUSED_PATHS: "not followed and not read, so nothing below them was "
    "seen by this run at all",
    GROUPER_FAILURES: "the folder still carries its marker -- re-run step 3 "
    "once the grouper starts",
    PASSED_OVER: "the grouper shows a folder's top level only; --open-all "
    "opens these anyway",
    PARK_FAILURES: "the folder holds no file anywhere and is still sitting "
    "in the month",
    RECONCILE_ERRORS: "a companion or a sidecar was left exactly where it was",
    WANTS_A_LOOK: "nothing was moved on a guess -- every one of these is a "
    "judgement call",
    AWAITING_A_NAME: "their children disagree or are themselves unnamed, and "
    "a name is not this tool's to invent",
    RENAME_FAILURES: "the name on the disk still says what it said before",
}

# Failures first, because they change what the rest of the run means; the
# folders the standard cannot describe last, because they are the only group
# no future step will ever settle on its own.
ISSUE_ORDER = [
    STEPS_FAILED,
    GROUPER_FAILURES,
    RENAME_FAILURES,
    PARK_FAILURES,
    RECONCILE_ERRORS,
    REFUSED_PATHS,
    PASSED_OVER,
    WANTS_A_LOOK,
    AWAITING_A_NAME,
    NON_COMPLIANT,
]


def group_issues(flags, limit=None):
    """``[(step, heading, item, note)]`` -> ``[(heading, items, hidden)]``.

    Deduplicated on heading and item, so a reparse point four separate walks
    all refused is one line, and ordered by ``ISSUE_ORDER``. ``limit`` caps
    each heading's list and reports how many it held back.
    """
    seen, index, headings = set(), {}, []
    for _step, heading, item, note in flags:
        key = (heading, item.casefold())
        if key in seen:
            continue
        seen.add(key)
        if heading not in index:
            index[heading] = []
            headings.append(heading)
        index[heading].append((item, note))
    headings.sort(
        key=lambda heading: (
            ISSUE_ORDER.index(heading) if heading in ISSUE_ORDER else len(ISSUE_ORDER)
        )
    )
    groups = []
    for heading in headings:
        items = index[heading]
        shown = items if limit is None else items[:limit]
        groups.append((heading, shown, len(items) - len(shown)))
    return groups


def issue_body(groups, notes=True):
    """The lines inside an issues frame: a counted heading, then its items."""
    lines = []
    for heading, items, hidden in groups:
        if lines:
            lines.append(line("dim", ""))
        lines.append(line(FAILED, "%s  (%d)" % (heading, len(items) + hidden)))
        note = ISSUE_NOTES.get(heading) if notes else None
        for index, piece in enumerate(
            textwrap.wrap(note, max(30, frame_width() - 12)) if note else []
        ):
            lines.append(
                line("dim", "    %s %s" % ("--" if index == 0 else "  ", piece))
            )
        for item, item_note in items:
            lines.append(line("warn", "    %s %s" % (glyph("dot"), item)))
            if item_note:
                lines.append(line("dim", "        %s" % item_note))
        if hidden:
            lines.append(
                line(
                    "dim",
                    "    ... and %d more, listed in full at "
                    "the end of the run" % hidden,
                )
            )
    return lines


# --------------------------------------------------------------------------
# Target resolution
# --------------------------------------------------------------------------


def report_refused(run, refused, indent=""):
    """Say what a walk would not follow, and keep it for the end of the run.

    A refused reparse point is not a failure -- refusing it is the point (T4)
    -- but it does mean a part of the target went unread, and that is
    something only a person can decide about.
    """
    for path, reason in refused:
        run.report("warn", "%sREFUSED %s: %s" % (indent, path, reason))
        run.flag(REFUSED_PATHS, path, reason)


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
        return True  # unreadable: treat as untrusted
    tag = getattr(status, "st_reparse_tag", 0)
    if tag:
        return True
    return os.path.islink(str(path))  # non-Windows


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
    report(
        "dim",
        "Archive root: restricted to its %d year tree(s) -- %s"
        % (len(years), ", ".join(path.name for path in years)),
    )
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
            "mean." % target
        )

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
        record = {
            "at": canonicalise.stamps.format_stamp(datetime.datetime.now()),
            "event": event,
        }
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
    """Canonicalise each tree, then park what that marked EMPTY (H4).

    The park is part of the step rather than a step of its own because it is
    the other half of the same finding: the canonicaliser is what establishes
    that a folder holds nothing anywhere, and a folder that holds nothing is
    not one to leave in the month for the next run to notice again.

    Returns the worst exit code of the two.
    """
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
        except SystemExit as stop:  # argparse inside the tool
            code = stop.code if isinstance(stop.code, int) else 2
        except OSError as error:
            run.report(FAILED, "Canonicalise failed on %s: %s" % (tree, error))
            run.flag(STEPS_FAILED, tree, "canonicalise failed: %s" % error)
            code = 2
        run.journal.write("canonicalise", tree=str(tree), exit_code=code)
        worst = max(worst, code)
    if worst < 2:
        # A canonicalise that could not run has not established anything about
        # what these folders hold, so nothing is moved on the strength of it.
        run.report("bold", "\nParking empty folders")
        worst = max(worst, park_empty_dated_folders(run))
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
            if (
                TO_SPLIT_MARKER in directory.name
                and not parking.is_inside_parking_area(directory)
            ):
                found.append(directory)
    report_refused(run, refused)
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
        names, settings.image_exts, settings.video_exts, settings.preview_exts
    )


def partition_groupable(folders, run):
    """Split marked folders into the ones worth opening and the ones that are not.

    Returns ``(groupable, passed_over)`` -- ``[(folder, images, videos)]`` and
    ``[(folder, reason)]``.

    A folder can carry the marker and still have nothing for the GUI to do.
    The grouper was emptied into sub-events on an earlier pass; the day's files
    all sit in "__RAW" or a legacy "__VIDEOS"; the folder holds nothing at all
    and step 1 has not parked it, because it was skipped or because there is no
    level above it allowed to hold a parking area (H2). Opening any of those
    puts an empty grid in front of the reviewer and waits for them to close it,
    which on a batch of ninety is the difference between a job and an
    afternoon.

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
    run.report(
        "warn",
        "%d marked folder(s) have nothing for the grouper to show:" % len(passed_over),
    )
    for folder, reason in passed_over:
        run.report("dim", "    %s  (%s)" % (folder.name, reason))
        run.flag(PASSED_OVER, folder, reason)
    run.report(
        "dim",
        "    The GUI shows a folder's top level only. "
        "Pass --open-all to open these anyway.",
    )


def grouper_paths(run):
    """``(python_exe, project_path)``, or None with the reason reported."""
    settings = canonicalise._config().get("screenshot_grouping", {})
    install = grouper.grouper_install(settings)
    if install is None:
        run.report(
            "warn",
            "The grouper is not installed on this machine "
            "(screenshot_grouping.python = %r, .project_path = %r in "
            "config.json)."
            % (settings.get("python", ""), settings.get("project_path", "")),
        )
        return None
    python_exe, project_path = install
    if not run.allow_network_tool:
        for path in (python_exe, project_path):
            if canonicalise.drive_is_network(path):
                run.report(
                    FAILED,
                    "The grouper lives on a network location (%s). An "
                    "executable on a share can be replaced between one "
                    "folder and the next, so it is not run from there."
                    "\nPass --allow-network-tool if that share is yours "
                    "and you trust it." % path,
                )
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
        run.report(
            "ok", "No folder carries the %s marker; nothing to group." % TO_SPLIT_MARKER
        )
        return 0

    counted, passed_over = partition_groupable(marked, run)
    report_passed_over(run, passed_over)
    for folder, reason in passed_over:
        run.journal.write("group_passed_over", folder=str(folder), reason=reason)

    if not counted:
        run.report(
            "ok",
            "\nNothing to group: all %d marked folder(s) have an "
            "empty top level." % len(marked),
        )
        return 0

    folders = [folder for folder, _images, _videos in counted]
    top_level = {
        path_key(folder): (images, videos) for folder, images, videos in counted
    }

    if run.max_folders and len(folders) > run.max_folders:
        run.report(
            "warn",
            "%d folder(s) carry the marker; limiting this run "
            "to the first %d (--max-folders / "
            "screenshot_grouping.max_folders). The rest stay "
            "marked and come up on the next run." % (len(folders), run.max_folders),
        )
        folders = folders[: run.max_folders]

    run.report("bold", "\n%d folder(s) to group:" % len(folders))
    for folder in folders:
        images, videos = top_level[path_key(folder)]
        run.report(
            "dim",
            "    %s  [%d image(s), %d video(s) at the top level]"
            % (folder, images, videos),
        )

    if not run.apply:
        run.report(
            "ok", "\nDry run: the grouper was not opened. " "Re-run with --apply."
        )
        return 1

    install = grouper_paths(run)
    if install is None:
        return 2
    python_exe, project_path = install

    if not run.confirm(
        "Open the grouper on %d folder(s) under\n    %s" % (len(folders), run.target)
    ):
        run.report("warn", "Not confirmed; nothing was opened.")
        return 2

    opened = failures = skipped = 0
    for number, folder in enumerate(folders, start=1):
        reason = still_safe_to_open(folder, run)
        if reason is not None:
            run.report(
                "dim",
                "[%d/%d] skipping %s: %s" % (number, len(folders), folder.name, reason),
            )
            run.journal.write("group_skipped", folder=str(folder), reason=reason)
            skipped += 1
            continue

        run.report("bold", "[%d/%d] %s" % (number, len(folders), folder.name))
        run.journal.write("group_opened", folder=str(folder))
        try:
            result = grouper.run_grouper(python_exe, project_path, folder)
        except OSError as error:
            run.report(FAILED, "    ! could not launch the grouper: %s" % error)
            run.flag(GROUPER_FAILURES, folder, "could not launch: %s" % error)
            run.journal.write("group_failed", folder=str(folder), error=str(error))
            failures += 1
            continue
        if result.returncode != 0:
            # The bare exit code says nothing about what went wrong -- the
            # grouper's own message only reaches its stderr.
            run.report(FAILED, "    ! grouper exited with code %d" % result.returncode)
            run.flag(
                GROUPER_FAILURES,
                folder,
                "the grouper exited with code %d" % result.returncode,
            )
            run.report(
                "dim",
                "      command: %s"
                % subprocess.list2cmdline(
                    grouper.grouper_command(python_exe, project_path, folder)
                ),
            )
            for line in grouper.stderr_tail(result.stderr):
                run.report("dim", "      %s" % line, speaker=False)
            run.journal.write(
                "group_failed", folder=str(folder), exit_code=result.returncode
            )
            failures += 1
            continue
        run.journal.write("group_closed", folder=str(folder))
        opened += 1

    run.report(
        "bold",
        "\n%d folder(s) grouped, %d skipped, %d failure(s)."
        % (opened, skipped, failures),
    )
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
            if canonicalise.stamps.day_prefix(
                directory.name
            ) and not parking.is_inside_parking_area(directory):
                found.append(directory)
    report_refused(run, refused)
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
    chunk_size = (
        canonicalise._config().get("safety", {}).get("hash_chunk_size", 1024 * 1024)
    )

    def checksum(path):
        return matching.default_checksum(Path(path), chunk_size)

    return checksum


def archive_sidecar_writer(run):
    """Write ExifTool text once, exclusively, or record the dry-run action."""
    if not run.apply:

        def record(target, _text, source):
            run.planned_video_sidecars.append((Path(source), Path(target)))

        return record

    def write(target, text, source):
        target = Path(target)
        os.makedirs(extended_path(target.parent), exist_ok=True)
        # Exclusive creation is the sidecar-writing equivalent of T2's
        # os.rename rule: an unexpected destination is never replaced.
        with open(extended_path(target), "x", encoding="iso-8859-1") as output:
            output.write(text)
        run.journal.write(
            "video_sidecar_generated", video=str(source), sidecar=str(target)
        )

    return write


def generate_missing_raw_sidecars(run, placement, config, move):
    """Generate canonical X1/X10 sidecars for RAW media still uncovered (X14)."""
    if exif_sidecars.SIDECAR_SUFFIX not in matching.sidecar_extensions(config):
        return 0, 0
    raw_exts = {
        extension.lower()
        for extension in config.get("extensions", {}).get("raw_images", [])
    }
    raw_missing = [
        path for path in placement.missing_sidecars if path.suffix.lower() in raw_exts
    ]
    other_missing = [
        path
        for path in placement.missing_sidecars
        if path.suffix.lower() not in raw_exts
    ]
    settings = config.get("raw_sidecar_generation", {})
    if not raw_missing or settings.get("enabled", True) is False:
        return 0, 0

    run.report(
        "bold", "\nRAW sidecars: %d missing after tolerant matching" % len(raw_missing)
    )
    for raw in raw_missing:
        run.report("dim", "  %s" % raw)

    if not run.apply:
        run.planned_generations.extend(raw_missing)
        placement.missing_sidecars = other_missing
        placement.media_without_sidecar = len(other_missing)
        run.report(
            "ok",
            "  %d RAW sidecar(s) to generate with ExifTool "
            "under --apply." % len(raw_missing),
        )
        return len(raw_missing), 0

    def log(message):  # ExifTool's own words
        run.report("warn", "  %s" % message, speaker=False)

    generated = exif_sidecars.generate_adjacent_sidecars(
        raw_missing,
        config.get("external_tools", {}).get("exiftool", "exiftool"),
        log=log,
    )
    completed = set()
    move_errors = 0
    for temporary in generated.created:
        raw = Path(str(temporary)[: -len(exif_sidecars.SIDECAR_SUFFIX)])
        destination = (
            Path(taxonomy.sidecar_subdir(raw.parent, config, "exif")) / temporary.name
        )
        try:
            move(temporary, destination)
        except Exception as error:
            run.flag(
                RECONCILE_ERRORS,
                destination,
                "generated sidecar could not be placed: %s" % error,
            )
            run.report(
                FAILED,
                "  ! could not place generated sidecar %s: %s" % (temporary, error),
            )
            move_errors += 1
            continue
        completed.add(os.path.normcase(os.path.abspath(str(raw))))
        run.journal.write(
            "raw_sidecar_generated", raw=str(raw), sidecar=str(destination)
        )
        run.report("dim", "  + %s" % destination)

    failed_raws = [
        raw
        for raw in raw_missing
        if os.path.normcase(os.path.abspath(str(raw))) not in completed
    ]
    placement.missing_sidecars = other_missing + failed_raws
    placement.media_without_sidecar = len(placement.missing_sidecars)
    errors = generated.errors + move_errors
    run.report(
        "bold",
        "Generated and placed %d/%d RAW sidecar(s)%s."
        % (
            len(completed),
            len(raw_missing),
            " with %d error(s)" % errors if errors else "",
        ),
    )
    return len(completed), errors


def find_parking_areas(run):
    """Every ``__EMPTY_SUBFOLDERS`` in the target, safely and deepest first."""
    found, refused = [], []
    for tree in run.trees:
        root_key = path_key(tree)
        for directory, _files in canonicalise.walk_bottom_up(tree, root_key, refused):
            if parking.is_parking_area(directory.name):
                found.append(directory)
    report_refused(run, refused)
    found.sort(key=lambda path: (len(path.parts), str(path).lower()), reverse=True)
    return found


def archive_empty_dir_remover(run):
    """Remove one verified-empty parking shell, or record that dry-run action."""
    if not run.apply:

        def record(folder):
            run.planned_removals.append(Path(folder))

        return record

    attempts, delay_seconds = canonicalise.configured_retry()

    def remove(folder):
        folder = Path(folder)
        canonicalise.with_retry(
            lambda: os.rmdir(extended_path(folder)), attempts, delay_seconds
        )
        run.journal.write("parking_shell_removed", folder=str(folder))

    return remove


def hoist_nested_parking(run, move):
    """Apply H2/H6 before any reconciliation pass descends into the tree."""
    areas = find_parking_areas(run)

    def log(message):  # the parking engine's own
        run.report("dim", "  %s" % message.strip(), speaker=False)

    def journalled_move(source, target):
        result = move(source, target)
        if run.apply:
            run.journal.write(
                "parking_entry_hoisted", source=str(source), target=str(target)
            )
        return result

    report = parking.hoist_parking_areas(
        areas,
        log=log,
        move=journalled_move,
        remove_empty=archive_empty_dir_remover(run),
        dry_run=not run.apply,
    )
    if report.misplaced:
        run.report("bold", "Nested parking areas: %s" % report.summary())
    return report


# --------------------------------------------------------------------------
# Steps 1 and 5 -- park every dated folder that holds no file
# --------------------------------------------------------------------------
#
# H4: an "__EMPTY_SUBFOLDERS" is where a day folder emptied of every file goes,
# "parked rather than offered to a grouper". The canonicaliser is what notices
# a folder holds nothing -- it writes the "(EMPTY)" bracket on it -- and until
# now that was the whole of what happened: the folder kept its place in the
# month, was counted among the day's work, and was passed over by step 3 one
# folder at a time, every run, for good.
#
# So the park happens where the notice does, in the same step.
#
# Empty means NO FILES, anywhere below it. Folders below it are not files and
# do not keep it out: a day drained down to a hollow "__RAW" and "__EXIF" is a
# day with nothing in it, which is why the canonicaliser writes "(f=2_EMPTY)"
# on that one rather than a count. The shells travel with it, so what it still
# says about itself survives the move.
#
# What the folder is CALLED decides nothing. Every dated folder is a candidate
# -- marked, placeholdered, or named by a person -- because H4 is about what a
# folder holds, and a name that no longer describes anything is not a reason to
# leave it in the month. Nothing is lost either way: H3 parks a folder under
# its own name, so the record of the day and what it was called goes with it.
#
# The disk is the evidence, never the name: a bracket says what some earlier
# run found, and re-reading is also what lets a dry run show the parks before
# any "(EMPTY)" has been written.


def folder_holds_no_files(folder, run):
    """True when nothing anywhere below ``folder`` is a file; None if unsure.

    The canonicaliser's walk, so a reparse point is refused here exactly as it
    is everywhere else (T4) -- and a folder hiding one is ``None`` rather than
    empty, because what a junction leads to is not something this may look at
    and so not something it may call nothing.

    Every dated folder in the archive is asked this, so the top level is read
    first and on its own: a day with photographs in it answers in one
    ``scandir``, and only a folder that might really be empty is walked to the
    bottom. Over a share that is the difference between one pass and two.
    """
    try:
        with os.scandir(extended_path(folder)) as entries:
            for entry in entries:
                if not entry.is_dir(follow_symlinks=False):
                    return False
    except OSError as error:
        run.report("warn", "  ! %s cannot be listed: %s" % (folder, error))
        return None

    refused = []
    for _directory, files in canonicalise.walk_bottom_up(
        folder, path_key(folder), refused
    ):
        if files:
            return False
    if refused:
        report_refused(run, refused, indent="  ")
        return None
    return True


def park_empty_dated_folders(run):
    """Move every dated folder holding no file into its level's parking area (H2/H4).

    Deepest first, and a folder still holding a dated child is left alone this
    run: parking its children is what makes it a leaf, and a leaf is what the
    next pass may park (H8 settles the two in that order). The guard is read
    before anything moves, so one run never both empties a group and parks it.
    """
    candidates = [
        folder for folder in dated_folders(run) if not parking.holds_dated_child(folder)
    ]
    candidates.sort(key=lambda path: (len(path.parts), str(path).lower()), reverse=True)

    # Only the applying half of ``archive_mover``: a park a dry run planned is
    # collected on its own below rather than in ``run.planned``, so the
    # reconcile step's "N file(s) to move" goes on counting files.
    move = archive_mover(run) if run.apply else None
    reserved = set()
    parked = errors = 0
    planned = []
    for folder in candidates:
        empty = folder_holds_no_files(folder, run)
        if empty is None:
            errors += 1
            run.report(
                FAILED,
                "  ! left %s: cannot read all of it, so it "
                "cannot be called empty" % folder,
            )
            continue
        if not empty:
            continue
        area = parking.parking_area_for(folder)
        if area is None:
            errors += 1
            run.report(
                "warn",
                "  ! left %s: no month folder or group above it "
                "to park it in (H2)" % folder,
            )
            run.non_compliant.append(
                (folder, "empty, but nothing above it may hold a parking area (H2)")
            )
            continue
        # A name already parked gains "_2", "_3" ... which is exactly the
        # discriminator N10a allows on an EMPTY name: two days emptied out of
        # one month keep both records rather than one overwriting the other.
        target = parking.free_versioned_name(area, folder.name, reserved)
        if not run.apply:
            planned.append((folder, target))
            run.report("dim", "  %s -> %s" % (folder, target))
            continue
        try:
            move(folder, target)
        except Exception as error:
            errors += 1
            run.report(FAILED, "  ! could not park empty %s: %s" % (folder, error))
            run.flag(PARK_FAILURES, folder, str(error))
            continue
        parked += 1
        run.journal.write("empty_folder_parked", folder=str(folder), target=str(target))
        run.report(
            "ok",
            "  * parked empty %s in %s"
            % (folder.name, parking.EMPTY_SUBFOLDERS_FOLDER),
        )

    if planned:
        run.planned_parkings.extend(planned)
        run.report(
            "bold",
            "\n%d empty folder(s) to park in %s. Nothing was "
            "changed. Re-run with --apply."
            % (len(planned), parking.EMPTY_SUBFOLDERS_FOLDER),
        )
    elif parked or errors:
        run.report(
            "bold",
            "\nParked %d empty folder(s)%s."
            % (parked, " with %d error(s)" % errors if errors else ""),
        )
    if parked or errors:
        run.journal.write("park_empty", parked=parked, errors=errors)
    if errors:
        return 1
    return 1 if planned else 0


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

    Six passes, in this order and no other:

    1. Nested ``__EMPTY_SUBFOLDERS`` areas are hoisted and merged into the one
       directly below their month folder (H2/H6). Parked folders are excluded
       from every pass that follows.
    2. Legacy ``__VIDEOS`` is drained: datable videos move up beside images;
       undatable ones are tagged and routed for review (V1/V4/V8).
    3. ``migrate_legacy_containers`` -- ``##   EXIFs   ##`` becomes ``__EXIF``
       and ``##   RAWs   ##`` becomes ``__RAW``, so everything after this reads
       one set of folder names instead of two.
    4. ``reconcile_folder``, per dated folder -- the engine the pipeline stage
       runs. A companion left behind in an event folder's taxonomy subdir
       follows the representative the grouper moved into a sibling sub-event,
       matched on capture time because the representative has been renamed
       since.
    5. ``place_companions``, over the **whole target at once** -- gather every
       subject and every companion, then distribute. A sidecar goes into the
       ``__EXIF`` directly inside the folder holding its subject (X10), a
       preview into that folder's ``__PREVIEWS`` (X13), matched on name because
       a companion carries its subject's full name (X1).
    6. Generate a canonical sidecar from every RAW genuinely still uncovered
       after historical stem/case matching, using ExifTool (X14).

    The order is the dependency order. Parking is normalized first, then
    legacy migration gives every later pass one set of folder names.
    Reconciliation next moves *subjects*: a RAW still in the wrong event folder
    has no business having its sidecar placed beside it yet. Placement is last,
    once every file is in the folder it belongs to.
    """
    config = canonicalise._config()
    move = archive_mover(run)
    checksum = archive_checksum(run)
    run.planned = []
    run.planned_removals = []
    run.planned_generations = []
    run.planned_video_sidecars = []
    parking_report = hoist_nested_parking(run, move)
    folders = dated_folders(run)
    if not folders and not parking_report.misplaced:
        run.report("ok", "No dated folder found; nothing to reconcile.")
        return 0

    migration = matching.MigrationReport()
    video_migration = legacy_videos.VideoMigrationReport()
    companions = matching.ReconcileReport()
    placement = matching.PlacementReport()

    run.report(
        "bold",
        "%s %d live dated folder(s) in %d tree(s)"
        % (label, len(folders), len(run.trees)),
    )

    def log(message):  # the matching engine's own
        run.report("dim", "  %s" % message.strip(), speaker=False)

    # 2 -- drain legacy videos before companion placement indexes subjects.
    video_folders = legacy_videos.legacy_video_folders(folders, config)
    if video_folders:
        exiftool = config.get("external_tools", {}).get("exiftool", "exiftool")

        def inspect_video(video):
            return exif_sidecars.read_metadata_text(video, exiftool)

        try:
            video_migration = legacy_videos.migrate_legacy_videos(
                video_folders,
                config,
                lambda folder: duplicates_folder(folder, run, config),
                inspect_video,
                log,
                move=move,
                checksum=checksum,
                write_sidecar=archive_sidecar_writer(run),
            )
        except Exception as error:
            run.report(FAILED, "  ! migrating legacy videos failed: %r" % error)
            run.flag(
                RECONCILE_ERRORS,
                run.target,
                "migrating legacy videos failed: %r" % error,
            )
            video_migration.errors += 1

        # All recognized companions travel in the same operation. Park the
        # shell now, before generic reconciliation prunes empty taxonomy dirs.
        legacy_videos.park_empty_legacy_video_folders(
            video_folders, video_migration, log, move=move, dry_run=not run.apply
        )

    # 3 -- the legacy containers. Found by the same walk that indexes the tree,
    # so this asks for an index first and then acts on what it named.
    survey = matching.survey_trees(run.trees, config, log)
    if survey.legacy_containers:
        try:
            migration.merge(
                matching.migrate_legacy_containers(
                    survey.legacy_containers,
                    config,
                    lambda folder: duplicates_folder(folder, run, config),
                    log,
                    move=move,
                    checksum=checksum,
                )
            )
        except Exception as error:
            run.report(FAILED, "  ! migrating legacy containers failed: %r" % error)
            run.flag(
                RECONCILE_ERRORS,
                run.target,
                "migrating legacy containers failed: %r" % error,
            )
            migration.errors += 1

    # 4 -- companions after their representative, per event folder.
    for folder in folders:

        def folder_log(message, folder=folder):  # the matching engine's own
            run.report(
                "dim", "  %s: %s" % (folder.name, message.strip()), speaker=False
            )

        try:
            companions.merge(
                matching.reconcile_folder(
                    folder, config, folder_log, move=move, prune=run.apply
                )
            )
        except Exception as error:  # never abandon the rest of the tree
            run.report(FAILED, "  ! reconciling %s failed: %r" % (folder.name, error))
            run.flag(RECONCILE_ERRORS, folder, "reconciling failed: %r" % error)
            companions.errors += 1

    # 5 -- placement, over every tree at once so a sidecar stranded anywhere in
    # the target can still find its subject.
    try:
        placement.merge(
            matching.place_companions(
                run.trees,
                config,
                lambda folder: duplicates_folder(folder, run, config),
                log,
                move=move,
                checksum=checksum,
                prune=run.apply,
            )
        )
    except Exception as error:
        run.report(FAILED, "  ! placing companions failed: %r" % error)
        run.flag(RECONCILE_ERRORS, run.target, "placing companions failed: %r" % error)
        placement.errors += 1

    # 6 -- only genuinely uncovered RAW media reach generation.
    generated_raw_sidecars, generation_errors = generate_missing_raw_sidecars(
        run, placement, config, move
    )

    # Only genuinely uncovered media remain here. Historical stem-form and
    # case-variant sidecars were resolved above; RAWs successfully generated
    # here have also been removed from the audit.
    for media in placement.missing_sidecars:
        run.report("dim", "  - %s has no sidecar" % media)

    if not run.apply:
        for source, target in run.planned:
            run.report("dim", "    %s\n    ->  %s" % (source, target))

    if migration.seen:
        run.report("bold", "\nLegacy containers: %s" % migration.summary())
    if video_migration.seen:
        run.report("bold", "\nLegacy videos: %s" % video_migration.summary())
    run.report(
        "bold", "\nCompanions following their representative: %s" % companions.summary()
    )
    run.report("bold", "Companion placement (X10/X13): %s" % placement.summary())
    run.report("dim", "%d media file(s) indexed" % placement.media)

    # Everything the run saw and did not settle, gathered where it can be read
    # rather than scrolled back to.
    run.non_compliant.extend(placement.non_compliant)
    for path, key in survey.legacy_containers:
        if key is None:
            run.non_compliant.append(
                (
                    path,
                    "legacy container with no modern equivalent; "
                    "its contents are a decision for a person",
                )
            )

    wants_a_look = [
        (text, value)
        for text, value in (
            ("with DIFFERENT bytes at the destination", placement.parked_differing),
            ("with no subject anywhere", placement.orphaned),
            ("whose subject is ambiguous", placement.ambiguous),
            ("media with no sidecar", placement.media_without_sidecar),
            ("errors", placement.errors),
        )
        if value
    ]
    if placement.needs_attention:
        run.report(
            "warn",
            "\n%d thing(s) want a look: %s"
            % (
                placement.needs_attention,
                ", ".join("%d %s" % (value, text) for text, value in wants_a_look),
            ),
        )
        # Counts, not paths: what the engine knows about each of these is in
        # its own per-file report, and repeating that here would bury the one
        # thing the end of the run is for -- that something is waiting.
        #
        # A media file with no sidecar is not flagged. It is reported, dim,
        # where it is found, and it is the ordinary state of most of an
        # archive that predates sidecars -- flagging it would put a red count
        # on every run for something nobody is going to act on folder by
        # folder. The four that are flagged are the ones where this tool
        # deliberately declined to guess.
        for text, value in wants_a_look:
            if text == "media with no sidecar":
                continue
            run.flag(WANTS_A_LOOK, "%d %s" % (value, text), "under %s" % run.target)

    if not run.apply and (
        run.planned
        or run.planned_removals
        or run.planned_generations
        or run.planned_video_sidecars
    ):
        if run.planned_removals:
            pending = "%d path(s) to move and %d empty parking shell(s) to remove" % (
                len(run.planned),
                len(run.planned_removals),
            )
        else:
            pending = "%d file(s) to move" % len(run.planned)
        if run.planned_generations:
            pending += "; %d RAW sidecar(s) to generate" % len(run.planned_generations)
        if run.planned_video_sidecars:
            pending += "; %d video sidecar(s) to generate" % len(
                run.planned_video_sidecars
            )
        run.report("ok", "\n%s. Nothing was changed. Re-run with --apply." % pending)

    run.journal.write(
        "reconcile",
        folders=len(folders),
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
        raw_sidecars_generated=generated_raw_sidecars,
        legacy_video_folders=video_migration.folders,
        legacy_videos_moved_up=video_migration.moved_up,
        legacy_videos_named_from_metadata=(video_migration.named_from_metadata),
        legacy_videos_unresolved=video_migration.unresolved,
        legacy_video_companions_moved=(video_migration.companions_moved),
        legacy_video_sidecars_created=(video_migration.sidecars_created),
        legacy_video_empty_folders_parked=(video_migration.empty_folders_parked),
        nested_parking_areas=parking_report.misplaced,
        parking_entries_hoisted=parking_report.entries_moved,
        parking_shells_removed=parking_report.shells_removed,
        non_compliant=len(placement.non_compliant),
        errors=(
            companions.errors
            + placement.errors
            + migration.errors
            + parking_report.errors
            + video_migration.errors
            + generation_errors
        ),
    )

    if (
        companions.errors
        or placement.errors
        or migration.errors
        or parking_report.errors
        or video_migration.errors
        or video_migration.left
    ):
        return 1
    if generation_errors:
        return 1
    if not run.apply and (
        run.planned
        or run.planned_removals
        or run.planned_generations
        or run.planned_video_sidecars
    ):
        return 1
    return 0


# --------------------------------------------------------------------------
# Step 6 -- mark and time the groups
# --------------------------------------------------------------------------
#
# Section 3: a dated folder holding dated children carries "____GROUP____" as
# the first element of its tail (C1), one that holds none carries no marker
# (C2), and a group states both ends of its span in its prefix (C6), both read
# off the subtree and rewritten whenever it changes (C11).
#
# What this step will NOT do, and why:
#
#   * It never rewrites the start **date**. N6 forbids deriving a date from
#     contents -- rewriting it would move the folder out from under its month
#     folder -- and C12's consequence, a group crossing into another month when
#     its earliest child leaves, is open question 6 in the standard. A folder
#     whose earliest file falls before its own date is reported instead.
#   * It never moves media out of a group (C4, open question 5), and never
#     moves a group between month folders (C12, open question 6).
#
# So this is the settled half of section 3: the marker and the two stamps.


def dated_children(folder, refused):
    """The direct dated child folders of ``folder``, or None if unreadable.

    The same two refusals every walk here makes (T4): a reparse point is never
    followed, and anything that cannot be inspected is reported rather than
    assumed to be a file.
    """
    try:
        with os.scandir(extended_path(folder)) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except OSError as error:
        refused.append((str(folder), "cannot be listed: %s" % error))
        return None
    children = []
    for entry in entries:
        if canonicalise.is_reparse_point(entry):
            refused.append(
                (entry.path, "reparse point (junction/symlink) not followed")
            )
            continue
        try:
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError as error:
            refused.append((entry.path, "cannot be inspected: %s" % error))
            continue
        if canonicalise.stamps.day_prefix(entry.name):
            children.append(Path(folder) / entry.name)
    return children


class Subtree(NamedTuple):
    """What a group's name is computed from: the two capture ends and the last day."""

    earliest: object  # datetime, or None when nothing under it is stamped
    latest: object  # datetime, likewise
    last_day: str | None  # "YYYY-MM-DD" of the last dated folder beneath it


def read_subtree(folder, refused):
    """Walk ``folder`` once for everything its name depends on.

    The capture ends come off **filenames**, never off the filesystem's own
    timestamps: every file in the archive carries its capture time in its name
    (F1), where a copy's mtime says only when it was copied. An unstamped file
    is ignored rather than guessed at, which is why either end can be None.

    The last day comes off the **dated folders** beneath it, at any depth,
    rather than off the last capture time. Two reasons, and they are the same
    reason twice: a day folder's date already has the day boundary applied
    (N7), so a night running past midnight is one day and not two, and a nested
    group's own span may be stale on the way in -- the run that fixes it is
    this one. Reading the days themselves is immune to both.
    """
    stamps = canonicalise.stamps
    grouping = canonicalise.grouping
    root_key = path_key(folder)
    names, days = [], []
    for directory, files in canonicalise.walk_bottom_up(folder, root_key, refused):
        if parking.is_parking_area(directory.name) or parking.is_inside_parking_area(
            directory
        ):
            continue
        names.extend(path.name for path in files)
        if path_key(directory) == root_key:
            continue
        day = stamps.day_prefix(directory.name)
        if day:
            days.append(day)
    return Subtree(
        grouping.earliest_capture_time(names),
        grouping.latest_capture_time(names),
        max(days) if days else None,
    )


def placeholder_tail(name, config):
    """The marker a tool left on ``name`` saying the day is unfinished, or None.

    ``__TO_SPLIT__`` means the day still has to be split, ``__TO_LABEL__`` that
    it still has to be named, and " - 1. ######" is what folder-sorting wrote
    before either existed. None of the three is a description, and the first of
    them is load-bearing: step 3 opens the grouper on exactly those folders.
    """
    grouping = canonicalise.grouping
    for marker in (grouping.TO_SPLIT_MARKER, grouping.TO_LABEL_MARKER):
        if grouping.LABEL_SEPARATOR + marker in name:
            return marker
    suffix = grouping.date_folder_suffix(config)
    return suffix if name.endswith(suffix) else None


def description_to_keep(name, config):
    """What a folder about to be renamed should still be called, or None.

    A person's claim on the name and nothing else: a group's existing
    description, which survives every rewrite of the stamps (C11, T7), or the
    label on a folder somebody named before it ever held children, which is the
    same claim written before the marker existed. A tool's placeholder is not a
    name -- ``__TO_SPLIT__(i=79)`` is a count and ``__TO_LABEL__`` is a request
    -- and comes back as None.

    Which of those shapes a name is, and what each one means, is
    ``grouping_names``' question, not this tool's (T8).
    """
    return canonicalise.grouping.folder_description(
        name, canonicalise.grouping.date_folder_suffix(config)
    )


def description_for_group(folder, children, config):
    """What a group is to be called, and where that name came from.

    Returns ``(description, source)`` with ``source`` one of ``"kept"``,
    ``"agreed"`` or ``"unnamed"``, so the step can say what it did rather than
    only what it wrote.

    Three sources, in order of authority:

      1. **a person.** The group's own description, or the label it carried
         before it had children. Never overwritten, never re-derived (T7).
      2. **agreement among its children.** When every dated child carries the
         same description, the group is about that thing and saying so invents
         nothing -- see ``grouping_names.shared_child_description``.
      3. **nobody.** ``__TO_LABEL__`` (N11), which is a question addressed to a
         person, not an answer. It is deliberately not sticky: a group marked
         this way is re-asked on every run, so it picks up a name the moment
         its children agree on one or somebody types one in.

    The alternative to (3) is the bare marker this step used to leave --
    ``- ____GROUP____(d=3)`` and nothing after it -- which says the same thing
    by saying nothing, and reads in Explorer as a folder that is simply named
    that way. A group waiting for a name should look like it is waiting.
    """
    kept = description_to_keep(folder.name, config)
    if kept is not None:
        return kept, "kept"
    agreed = canonicalise.grouping.shared_child_description(
        [child.name for child in children],
        canonicalise.grouping.date_folder_suffix(config),
    )
    if agreed is not None:
        return agreed, "agreed"
    return canonicalise.grouping.TO_LABEL_MARKER, "unnamed"


def date_of(text):
    """``YYYY-MM-DD`` as a date, so a prefix can be rebuilt with its weekday (N1)."""
    return datetime.date(int(text[:4]), int(text[5:7]), int(text[8:10]))


def span_end_moment(end_day, latest):
    """The instant a span end states: the last day, at the last capture time.

    The two halves come from different places on purpose -- the day from the
    children's names, which have the day boundary already applied (N7), the
    time from the latest file anywhere in the subtree. A night that runs past
    midnight is one event, so its last shot is timed 01.20.44 inside a folder
    dated the evening before, and the span has to be able to say exactly that.
    """
    day = date_of(end_day)
    return datetime.datetime(
        day.year, day.month, day.day, latest.hour, latest.minute, latest.second
    )


def group_target_name(folder, children, run, config, refused):
    """The name section 3 wants on ``folder``, as ``(name, reason, source)``.

    ``name`` is None when the folder cannot be named, and ``reason`` says why;
    otherwise ``reason`` is None and ``source`` says where the description came
    from -- see ``description_for_group``.

    No ``children`` means the marker has to come off (C2): the folder is a leaf
    again, and a leaf carries neither marker nor span. It also loses a
    ``__TO_LABEL__`` the group carried, which was a question about a group and
    is not one this tool asks of a leaf -- N11 is read on a day folder, never
    written onto one.
    """
    stamps = canonicalise.stamps
    grouping = canonicalise.grouping
    parsed = stamps.split_dated_folder(folder.name)
    if parsed is None:
        return None, "not a dated folder", None
    base = stamps.format_day_prefix(date_of(parsed.date))

    if not children:
        description = description_to_keep(folder.name, config)
        if parsed.time:
            base += "__" + parsed.time
        return (
            base + (grouping.LABEL_SEPARATOR + description if description else ""),
            None,
            "kept",
        )

    placeholder = placeholder_tail(folder.name, config)
    if placeholder:
        # A day that has been split but still has shots of its own at the top
        # level is half-done, and the marker is how step 3 finds it again.
        # Taking it off would strand that media for good -- and gathering it
        # into a child of its own is C4, open question 5. Reported, not touched.
        counts = top_level_media(folder, run.grouping_settings)
        if counts is None or sum(counts) > 0:
            return (
                None,
                (
                    "still carries %s with %s at its top level: it is a "
                    "group by C1 and a day awaiting the grouper at once "
                    "-- C4, open question 5"
                    % (
                        placeholder,
                        (
                            "media"
                            if counts is None
                            else "%d image(s) and %d video(s)" % counts
                        ),
                    )
                ),
                None,
            )

    subtree = read_subtree(folder, refused)
    if subtree.earliest is None or subtree.latest is None:
        return None, "no file under it carries a capture stamp (C5, C8)", None
    if subtree.last_day is None:
        return None, "no folder under it carries a readable date", None
    if subtree.last_day < parsed.date:
        return (
            None,
            (
                "a folder under it is dated %s, before its own %s (C13)"
                % (subtree.last_day, parsed.date)
            ),
            None,
        )

    earliest, latest = subtree.earliest, subtree.latest
    if "%04d-%02d-%02d" % (earliest.year, earliest.month, earliest.day) < parsed.date:
        # C12 / open question 6: the start belongs under an earlier month
        # folder. Reported, never moved -- and the name is left alone, because
        # a start time from a day the folder does not claim would be a lie.
        return (
            None,
            (
                "its earliest file is dated %04d-%02d-%02d, before the "
                "folder's own %s -- moving it is open question 6 (C12)"
                % (earliest.year, earliest.month, earliest.day, parsed.date)
            ),
            None,
        )

    base += "__%02d.%02d.%02d" % (earliest.hour, earliest.minute, earliest.second)
    base += stamps.format_range_end(
        parsed.date, span_end_moment(subtree.last_day, latest)
    )
    # Last, so a folder this step refuses to name is never asked what it should
    # be called -- the children are read only for a group that is getting a name.
    description, source = description_for_group(folder, children, config)
    return grouping.group_name(base, len(children), description), None, source


def group_violations(folder, config):
    """What ``folder`` holds that C3 does not allow. Reported, never fixed.

    Media, loose files of any kind and taxonomy subfolders are all outside the
    closed set. None of it is touched: gathering loose media into a dated child
    is C4, which is open question 5, and where a whole trip's ".gpx" belongs is
    open question 4.
    """
    stamps = canonicalise.stamps
    grouping = canonicalise.grouping
    try:
        with os.scandir(extended_path(folder)) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
    except OSError as error:
        return ["cannot be listed: %s" % error]

    files, folders_inside = [], []
    for entry in entries:
        if canonicalise.is_reparse_point(entry):
            continue
        try:
            is_directory = entry.is_dir(follow_symlinks=False)
        except OSError:
            continue
        (folders_inside if is_directory else files).append(entry.name)

    reasons = []
    if files:
        images, videos = grouping.count_media(
            files, *grouping.extension_sets(config), grouping.preview_extensions(config)
        )
        if images or videos:
            reasons.append(
                "holds %d image(s) and %d video(s) of its own -- C3; "
                "moving them down is C4, open question 5" % (images, videos)
            )
        other = len(files) - images - videos
        if other:
            reasons.append("holds %d loose file(s) that are not media (C3)" % other)

    parking_areas = 0
    for name in folders_inside:
        if stamps.day_prefix(name):
            continue
        if name == grouping.EMPTY_SUBFOLDERS_FOLDER:
            # H2: a group is a level dated folders sit on, so it is a level a
            # parking area may sit on -- it holds the children this group has
            # emptied. C3 allows exactly one.
            parking_areas += 1
            if parking_areas > 1:
                reasons.append("holds more than one %r (C3, H2)" % name)
            continue
        reasons.append(
            "holds %r, which is neither a dated folder nor %s (C3)"
            % (name, grouping.EMPTY_SUBFOLDERS_FOLDER)
        )
    return reasons


def step_group_markers(run):
    """Mark, time and span every group; report what section 3 leaves open."""
    grouping = canonicalise.grouping
    config = canonicalise._config()
    refused = []

    folders = dated_folders(run)
    # Deepest first, so renaming a child never invalidates a parent's recorded
    # path -- the same reason every walk here is bottom-up.
    folders.sort(key=lambda path: (len(path.parts), str(path).lower()), reverse=True)

    renames, groups, unmarked = [], 0, 0
    # Where each group's description came from, so the step can say whether it
    # carried a name across, read one off the children, or is asking for one.
    agreed, awaiting = [], []
    for folder in folders:
        children = dated_children(folder, refused)
        if children is None:
            continue
        carries = grouping.carries_group_marker(folder.name)
        if not children and not carries:
            continue  # an ordinary leaf: nothing to say
        if children:
            groups += 1
            for reason in group_violations(folder, config):
                run.non_compliant.append((folder, reason))
        else:
            unmarked += 1

        target, reason, source = group_target_name(
            folder, children, run, config, refused
        )
        if target is None:
            run.non_compliant.append((folder, reason))
            continue
        if children and source == "agreed":
            agreed.append((folder, grouping.group_description(target)))
        elif children and source == "unnamed":
            awaiting.append(folder)
        if target != folder.name:
            renames.append((folder, folder.with_name(target)))

    report_refused(run, refused)

    run.report(
        "ok",
        "\n%d group(s); %d folder(s) carrying the marker with no "
        "dated children left; %d name(s) to correct."
        % (groups, unmarked, len(renames)),
    )
    for source, target in renames:
        run.report("dim", "  %s\n      -> %s" % (source, target.name))

    if agreed:
        run.report(
            "ok", "\n%d group(s) named from what their children agree on:" % len(agreed)
        )
        for folder, description in agreed:
            run.report("dim", "  %s\n      -> %s" % (folder.name, description))
    if awaiting:
        # Not a violation and not in ``non_compliant``: a group with no name is
        # a conforming group. This is the one thing in the step addressed to a
        # person rather than to the archive, so it is stated plainly and left.
        run.report(
            "warn",
            "\n%d group(s) nobody has named, marked %s -- their "
            "children disagree or are themselves unnamed, and a "
            "name for them is not this tool's to invent:"
            % (len(awaiting), grouping.TO_LABEL_MARKER),
        )
        for folder in awaiting:
            run.report("dim", "  %s" % folder)
            run.flag(AWAITING_A_NAME, folder, "marked %s" % grouping.TO_LABEL_MARKER)

    failures = 0
    if run.apply:
        # Deepest first, as they were gathered: a child is renamed before the
        # parent whose path was recorded when the child still had its old name.
        attempts, delay_seconds = canonicalise.configured_retry()
        for source, target in renames:
            try:
                canonicalise.rename_path(source, target, attempts, delay_seconds)
            except OSError as error:
                run.report(FAILED, "FAILED %s: %s" % (source, error))
                run.flag(RENAME_FAILURES, source, str(error))
                failures += 1

    run.journal.write(
        "group_markers",
        groups=groups,
        unmarked=unmarked,
        renamed=len(renames),
        named_from_children=len(agreed),
        awaiting_a_name=len(awaiting),
        failures=failures,
        applied=bool(run.apply),
    )

    if failures:
        return 2
    if not run.apply and renames:
        run.report(
            "ok",
            "\n%d folder(s) to rename. Nothing was changed. "
            "Re-run with --apply." % len(renames),
        )
        return 1
    return 0


# --------------------------------------------------------------------------
# Steps 7 and 8 -- compliance with the archive standard
# --------------------------------------------------------------------------

_STANDARD_NOTICE = (
    "%s is a DRAFT: its S4 subfolder set and its T8 "
    "'defined more than once' list still carry open questions, and the answers "
    "change what counts as compliant. Enforcing it now would migrate a live "
    "archive to a shape that is still being argued about.\nThis step is a "
    "placeholder and does nothing. 'The fixing tool' under section 7 of that "
    "document is the specification it will be built to, and section 8 is the "
    "machine-readable form it will parse.\nSection 3 is the one part already "
    "settled and already enforced -- by step 6, which marks, times and spans "
    "the groups." % STANDARD_PATH.name
)


def step_standard_check(run):
    run.report("warn", "NOT IMPLEMENTED -- " + _STANDARD_NOTICE)
    run.journal.write("standard_check", status="not_implemented")
    return 0


def step_standard_fix(run):
    run.report("warn", "NOT IMPLEMENTED -- " + _STANDARD_NOTICE)
    run.report(
        "dim",
        "When it exists it will prompt before changing anything, "
        "the way step 2 does.",
    )
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
    (
        1,
        "Canonicalise names and park the empty",
        lambda run: step_canonicalise(run, "Canonicalising"),
        None,
    ),
    (
        2,
        "Reunite companions and sidecars",
        lambda run: step_reconcile(run, "Reconciling"),
        None,
    ),
    (3, "Group the %s folders" % TO_SPLIT_MARKER, step_group, None),
    (
        4,
        "Reunite companions and sidecars again",
        lambda run: step_reconcile(run, "Reconciling (again)"),
        2,
    ),
    (
        5,
        "Canonicalise names and park again",
        lambda run: step_canonicalise(run, "Canonicalising (again)"),
        1,
    ),
    (6, "Mark and time the groups", step_group_markers, None),
    (7, "Check compliance with the archive standard", step_standard_check, None),
    (8, "Fix compliance with the archive standard", step_standard_fix, None),
)


def step_header(number, title, colour):
    """Open each step with a frame, so the run reads as a run of steps."""
    print()
    frame(None, [line("bold", "STEP %d -- %s" % (number, title))], "bold", colour)


def report_step_verdict(run, number, title, outcome, colour):
    """Close each step with the one thing that decides what happens next.

    A step prints hundreds of lines and whether it left anything for a person
    is not one of them -- it is spread through them. So every step ends in a
    frame of its own: green when it left nothing, red when it did, naming what
    it flagged rather than making anybody scroll back through the report to
    find out.

    Only the step's own flags, and only the first ``STEP_VERDICT_ITEMS`` of
    each kind: the end-of-run block is where the full list lives, and a step
    that flagged four hundred folders must not push its own headline off the
    screen.
    """
    flags = [entry for entry in run.issues if entry[0] == number]
    if not flags:
        if outcome == OK:
            key, headline = "ok", "%s STEP %d OK -- nothing to address." % (
                glyph("tick"),
                number,
            )
        elif outcome == PENDING:
            key, headline = "warn", (
                "%s STEP %d -- changes pending, nothing to address."
                % (glyph("warn"), number)
            )
        else:
            key, headline = FAILED, (
                "%s STEP %d FAILED -- see its report "
                "above." % (glyph("cross"), number)
            )
        print()
        frame(None, [line(key, headline)], key, colour)
        return

    groups = group_issues(flags, limit=STEP_VERDICT_ITEMS)
    total = sum(len(items) + hidden for _heading, items, hidden in groups)
    lines = [
        line(
            FAILED,
            "%s STEP %d LEFT %d THING(S) TO ADDRESS" % (glyph("cross"), number, total),
        ),
        line("dim", ""),
    ] + issue_body(groups, notes=False)
    print()
    frame("STEP %d -- %s" % (number, title), lines, FAILED, colour, closed=False)


def report_run_issues(run, outcomes, colour):
    """Everything the whole run left for a person, in one framed block.

    Two sources: what the steps flagged as they went, and the steps that did
    not finish. Printed once, in full, in red, immediately before the summary
    -- because a finding that has to be scrolled back to has not been
    reported.

    Returns how many there were, which is what the summary's verdict turns on.
    """
    flags = list(run.issues)
    flags += [
        (None, STEPS_FAILED, "Step %d -- %s" % (number, title), None)
        for number, title, outcome in outcomes
        if outcome == FAILED
    ]
    groups = group_issues(flags)
    if not groups:
        return 0
    total = sum(len(items) for _heading, items, _hidden in groups)
    print()
    frame(
        "ISSUES TO ADDRESS  (%d)" % total,
        issue_body(groups),
        FAILED,
        colour,
        closed=False,
    )
    return total


def report_summary(run, outcomes, worst, issues, colour):
    """The last thing printed: what each step did, then the verdict.

    Deliberately after the issues rather than before them. The summary is the
    shape of the run and the issues are the work still to do, and whichever is
    printed last is the one that is still on the screen when the run ends.
    """
    lines = []
    for number, title, outcome in outcomes:
        key = {OK: "ok", PENDING: "warn", SKIPPED: "dim"}.get(outcome, FAILED)
        mark = {OK: glyph("tick"), PENDING: glyph("warn"), SKIPPED: ""}.get(
            outcome, glyph("cross")
        )
        mark = mark.ljust(GLYPH_WIDTH)
        text = "%s %-8s %d. %s" % (mark, outcome, number, title)
        lines.append(
            line(
                key,
                text,
                colourise("%s %-8s " % (mark, outcome), key, colour)
                + colourise(
                    "%d. %s" % (number, title),
                    "dim" if outcome == SKIPPED else "bold",
                    colour,
                ),
            )
        )
    if run.journal.path is not None:
        lines.append(line("dim", ""))
        lines.append(line("dim", "Journal: %s" % run.journal.path))

    print()
    frame(
        "SUMMARY  (%s)" % ("applied" if run.apply else "dry run"), lines, "bold", colour
    )

    if issues:
        banner(
            "%s  %d ISSUE(S) TO ADDRESS  %s" % (glyph("cross"), issues, glyph("cross")),
            "Listed in the block above. None of them was fixed for you.",
            FAILED,
            colour,
        )
    elif worst >= 2:
        banner(
            "%s  RUN STOPPED  %s" % (glyph("cross"), glyph("cross")),
            "A step could not run; the steps after it never started.",
            FAILED,
            colour,
        )
    elif worst == 1 and not run.apply:
        banner(
            "%s  DRY RUN -- CHANGES PENDING  %s" % (glyph("warn"), glyph("warn")),
            "Nothing was changed. Re-run with --apply.",
            "warn",
            colour,
        )
    elif worst == 1:
        banner(
            "%s  CHANGES PENDING  %s" % (glyph("warn"), glyph("warn")),
            "Re-run to carry on where this one stopped.",
            "warn",
            colour,
        )
    else:
        banner(
            "%s  ALL CLEAR  %s" % (glyph("tick"), glyph("tick")),
            "Every step finished and nothing is left to address.",
            "ok",
            colour,
        )


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
        self.planned_removals = []
        self.planned_generations = []
        # And where a dry run's canonicalise step collects the empty folders it
        # would park -- kept apart from ``planned`` so the reconcile step's
        # "N file(s) to move" still counts only files (H4).
        self.planned_parkings = []
        # Folders that fit none of the shapes the standard allows, gathered as
        # the run goes and printed together at the end (in red) rather than
        # scrolling past in the middle of a rename report.
        self.non_compliant = []
        # Everything a person has to act on, tagged with the step that found
        # it: ``(step, heading, item, note)``. Each step closes with its own
        # share of these and the run closes with all of them.
        self.issues = []
        # Set by the run loop around each step's action, so a flag raised deep
        # inside a step knows which step's verdict it belongs in.
        self.current_step = None
        self.journal = Journal(None)

    def report(self, key, message, speaker=True):
        """Print one line of the run's report.

        ``speaker=False`` for a line relayed from a tool this one called: it
        keeps that tool's own words and colours and takes no tag, which is
        what makes the tagged lines mean anything.
        """
        if self.quiet and key not in ("warn", "bold", FAILED):
            return
        print(
            speak(message, key, self.colour)
            if speaker
            else colourise(message, key, self.colour)
        )

    def flag(self, heading, item, note=None):
        """Keep something for the step's verdict and the end-of-run block.

        The step has already reported it in place, where it will scroll past.
        This is the copy that does not: see ``group_issues``, which is what
        both frames are built from. Deduplicated per step, so one walk that
        meets the same refused junction twice states it once.
        """
        entry = (self.current_step, heading, str(item), note)
        if entry not in self.issues:
            self.issues.append(entry)

    def confirm(self, question):
        """Ask, and mean it: only the confirmation word is a yes.

        ``--yes`` is for an unattended run and is the only way past this with
        no terminal attached -- a script that piped its way through a
        confirmation would make the confirmation decorative.
        """
        if self.assume_yes:
            return True
        if not (sys.stdin and sys.stdin.isatty()):
            self.report(
                FAILED,
                "No terminal to confirm at. Re-run from a "
                "console, or pass --yes for an unattended run.",
            )
            return False
        print(speak("\n" + question, "bold", self.colour))
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
                "%r is not a step number (1-%d)" % (piece, len(STEPS))
            )
        wanted.add(int(piece))
    # Fixed order regardless of how they were typed: "3,1" still canonicalises
    # before it canonicalises again.
    return [number for number in numbers if number in wanted]


def build_parser():
    parser = argparse.ArgumentParser(
        prog="restructure_archive",
        description="Bring an existing photo archive onto the current naming "
        "and structure conventions.",
        epilog="Nothing is changed without --apply.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="year tree, archive root, or any folder inside "
        r"one; local or UNC (default: <root_folder>\<year>)",
    )
    parser.add_argument(
        "--year",
        type=int,
        default=canonicalise.DEFAULT_YEAR,
        help="year tree to work on, under the configured root "
        "or under an explicitly named root "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="make the changes; without it this only reports",
    )
    parser.add_argument(
        "--steps",
        default=None,
        metavar="N[,N...]",
        help="run only these steps (default: all of 1-%d)" % len(STEPS),
    )
    parser.add_argument(
        "--list-to-split",
        action="store_true",
        help="list the folders step 2 would open, and stop",
    )
    parser.add_argument(
        "--open-all",
        action="store_true",
        help="open every marked folder, including those with "
        "no image or video at their top level for the "
        "grouper to show",
    )
    parser.add_argument(
        "--max-folders",
        type=int,
        default=None,
        help="open the grouper on at most this many folders "
        "(default: screenshot_grouping.max_folders, "
        "0 for no limit)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="answer every confirmation; for unattended runs",
    )
    parser.add_argument(
        "--force-target",
        action="store_true",
        help="work on a target that does not look like an archive",
    )
    parser.add_argument(
        "--allow-network-tool",
        action="store_true",
        help="run the grouper even though its interpreter or "
        "project sits on a network location",
    )
    parser.add_argument(
        "--keep-drive-letter",
        action="store_true",
        help="do not pin a mapped network drive to its UNC",
    )
    parser.add_argument(
        "--journal",
        default=None,
        help="where to record what an applied run did "
        "(default: a dated file inside the target)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="only print each step's headline and summary",
    )
    parser.add_argument("--no-colour", action="store_true")
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    # Which of the two ways the year arrived matters: an explicit --year
    # alongside an explicitly named root means "that year of that archive",
    # while the default year must not silently redirect a named target.
    args.year_given = any(
        item == "--year" or item.startswith("--year=") for item in argv
    )
    colour = not args.no_colour and sys.stdout.isatty()

    def report(key, message):
        if args.quiet and key not in ("warn", "bold", FAILED):
            return
        print(speak(message, key, colour))

    try:
        steps = selected_steps(args.steps)
    except argparse.ArgumentTypeError as error:
        print(speak("Bad --steps: %s" % error, FAILED, colour))
        banner(
            "%s  NOTHING RAN  %s" % (glyph("cross"), glyph("cross")),
            "Bad --steps. Nothing was changed.",
            FAILED,
            colour,
        )
        return 2

    target, error = resolve_run_target(args, report)
    if error:
        print(speak(error, FAILED, colour))
        banner(
            "%s  NOTHING RAN  %s" % (glyph("cross"), glyph("cross")),
            "The target was refused. Nothing was changed.",
            FAILED,
            colour,
        )
        return 2

    trees = scan_roots(target, report)
    if args.max_folders is None:
        args.max_folders = (
            canonicalise._config().get("screenshot_grouping", {}).get("max_folders", 0)
            or 0
        )

    run = Run(args, target, trees, colour)

    if args.list_to_split:
        marked = find_to_split_folders(run)
        counted, passed_over = partition_groupable(marked, run)
        for folder, images, videos in counted:
            print("%s  [i=%d v=%d]" % (folder, images, videos))
        report_passed_over(run, passed_over)
        # A listing stops before the first step, so it never reaches the
        # summary -- but "how many, and is any of it a problem" is the same
        # question the end of a run answers, and it gets the same frame.
        print()
        frame(
            None,
            [
                line(
                    "bold",
                    "%d folder(s) carry the %s marker; "
                    "%d worth opening." % (len(marked), TO_SPLIT_MARKER, len(counted)),
                )
            ],
            "bold",
            colour,
        )
        if passed_over:
            frame(
                None, issue_body(group_issues(run.issues)), FAILED, colour, closed=False
            )
        return 1 if counted else 0

    report(
        "bold", "%s %s" % ("Restructuring" if args.apply else "Dry run over", target)
    )
    report("dim", "Steps: %s" % ", ".join(str(number) for number in steps))

    if args.apply:
        if canonicalise.drive_is_network(target) and not run.confirm(
            "This will rename files on a NETWORK location:\n    %s" % target
        ):
            print(speak("Not confirmed; nothing was changed.", "warn", colour))
            banner(
                "%s  NOTHING RAN  %s" % (glyph("warn"), glyph("warn")),
                "Not confirmed. Nothing was changed.",
                "warn",
                colour,
            )
            return 2
        stamp = canonicalise.stamps.format_stamp(datetime.datetime.now())
        run.journal = Journal(
            Path(args.journal)
            if args.journal
            else target / ("_restructure_journal_%s.jsonl" % stamp)
        )
        run.journal.write(
            "run_started",
            target=str(target),
            trees=[str(tree) for tree in trees],
            steps=steps,
        )

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
            report(
                "dim",
                "\nSTEP %d -- %s: skipped, a dry run leaves nothing "
                "for a second pass to find (step %d already reported "
                "it)." % (number, title, repeats),
            )
            outcomes.append((number, title, SKIPPED))
            continue
        step_header(number, title, colour)
        run.current_step = number
        seen_non_compliant = len(run.non_compliant)
        code = action(run)
        # The folders the step found no shape for become flags like every
        # other finding, so one gathering serves both frames. They are still
        # kept in ``run.non_compliant`` for the journal's count.
        for path, reason in run.non_compliant[seen_non_compliant:]:
            run.flag(NON_COMPLIANT, path, reason)
        ran.add(number)
        worst = max(worst, code)
        outcome = {0: OK, 1: PENDING}.get(code, FAILED)
        outcomes.append((number, title, outcome))
        report_step_verdict(run, number, title, outcome, colour)
        run.current_step = None
        if code == 2:
            # An error is a stopped run: step 3 has nothing to tidy up after a
            # step 2 that never opened anything, and step 1 failing at all
            # means the target itself is wrong.
            report(FAILED, "\nStep %d could not run; stopping here." % number)
            break

    issues = report_run_issues(run, outcomes, colour)
    if run.journal.path is not None:
        run.journal.write(
            "run_finished",
            exit_code=worst,
            non_compliant=len(run.non_compliant),
            issues=issues,
        )
    report_summary(run, outcomes, worst, issues, colour)
    return worst


if __name__ == "__main__":
    sys.exit(main())
