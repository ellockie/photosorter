"""Where the external grouper lives, and how it is invoked.

The GUI that splits a day into named sub-events is a separate project
(``screenshot_grouping.project_path`` in config.json), run out of its own
virtualenv (``screenshot_grouping.python``). Three callers open it:

* ``ScreenshotGroupingStage`` -- during a pipeline run, on the folders that
  run sorted into;
* ``src/server.py`` -- from the dashboard's grouping-review prompt;
* ``tools/restructure_archive.py`` -- over an existing archive, on every
  folder still carrying the ``__TO_SPLIT__`` marker.

What counts as "installed", the exact command line, and **the count taken
around each window** therefore have to be one definition rather than three,
the same way the name grammars are (``ARCHIVE_STANDARD.md``, rule T8).

The count is the safety rule. The grouper is another project and does not obey
T1/T2: it has been seen to rename two same-second files onto one name and lose
the one underneath. So no caller opens a window bare -- ``folder_census``
before, ``folder_census`` after, ``guard_grouper_window`` between them, and any
of the four totals coming back lower stops the batch instead of being carried
past. See the section at the foot of this module for the four totals, and for
why the count is over the folder's parent.

This is a **leaf module**: it imports nothing from the project, so the
maintenance tool can load it by file path without dragging the whole pipeline
-- exiftool, the dashboard, the converters -- in behind it. Importing
``src.pipeline_stages.screenshot_grouping`` instead would run that package's
``__init__``, which imports every stage.
"""

import collections
import os
import subprocess
from pathlib import Path
from typing import NamedTuple

# The entry point inside the grouper project. Its presence is also what says
# the project path points at the grouper and not at some other folder.
GROUPER_ENTRY_POINT = "main.py"


def grouper_install(settings: dict) -> tuple[Path, Path] | None:
    """``(python_exe, project_path)`` of the external grouper, or None.

    ``settings`` is the ``screenshot_grouping`` block of the config. Both
    halves have to be on disk: a virtualenv without the project, or a project
    path with no ``main.py`` in it, is not an installation.
    """
    python_exe = Path(settings.get("python", ""))
    project_path = Path(settings.get("project_path", ""))
    if not python_exe.is_file() or not (project_path / GROUPER_ENTRY_POINT).is_file():
        return None
    return python_exe, project_path


def grouper_command(python_exe: Path, project_path: Path, folder: Path) -> list[str]:
    """The argument vector that opens the grouper on one folder.

    A list, never a string, and every caller runs it with ``shell=False``: a
    folder name is archive data, and an event somebody labelled with an
    ampersand must reach the GUI as a name rather than as a shell operator.
    """
    return [str(python_exe), str(project_path / GROUPER_ENTRY_POINT), str(folder)]


def stderr_tail(stderr: str | None, limit: int = 5) -> list[str]:
    """The last few non-empty stderr lines, for the failure log.

    The bare exit code says nothing about what went wrong -- the grouper's own
    message (an argparse usage error, a traceback) only reaches its stderr.
    """
    if not stderr:
        return []
    lines = [line.rstrip() for line in stderr.splitlines() if line.strip()]
    return lines[-limit:]


def run_grouper(python_exe: Path, project_path: Path, folder: Path):
    """Open the GUI on one folder, blocking until its window closes.

    Returns the ``CompletedProcess``. Raises ``OSError`` if the interpreter
    could not be started at all; every caller decides for itself whether that
    ends the batch.
    """
    return subprocess.run(
        grouper_command(python_exe, project_path, folder),
        cwd=str(project_path),
        stderr=subprocess.PIPE,
        text=True,
    )


# --------------------------------------------------------------------------
# Counting what was handed over, and counting it again when it comes back
# --------------------------------------------------------------------------
#
# The grouper is a separate project. It is not bound by T1 ("no file is
# deleted") or T2 ("rename, never replace"), and it has been found not to be
# keeping them: handed two files captured in the same second, it renamed both
# onto one name and the second landed on the first. One shot, gone, with
# nothing in any log to say it had ever been there.
#
# Nothing this project writes inside itself would have stopped that -- the
# overwrite happens in another process, in another virtualenv. What it can do
# is refuse to be the tool that did not notice. So every window is bracketed
# by a count, and a count that comes back lower ends the batch where it
# stands: before the next window can do the same thing again, and before any
# later step rewrites the names that are the last record of what was there.
#
# Four totals are taken, not one -- files, media, sidecars, bytes -- because
# each catches a loss the others do not. A sidecar lost while a state file
# arrives leaves the file count level; a file overwritten in place leaves every
# count level and moves only the byte total. See census_loss.
#
# The count is taken over the folder's PARENT, not the folder. Splitting a day
# is allowed to consume the folder it was opened on -- the grouper writes the
# sub-events as siblings and takes the original away -- so a count scoped to
# the folder would read zero after every successful split and cry wolf on all
# of them. Everything a window is expected to do (create folders, rename
# files, move them down into sub-events) happens inside that parent and leaves
# its total alone. Anything that lowers the total left the parent, and there is
# no reading of that which is safe to carry on past.


# What a file is, for counting. Three kinds and not one, because a total that
# merged them would let a loss hide behind an arrival: a window that took a
# sidecar away and wrote a state file of its own leaves the file count exactly
# where it was, and only a separate sidecar count says what happened.
#
# A sidecar here is X6's sense of the word -- the "._exif" and every other
# companion, the camera thumbnail and the GoPro proxy included. They are not
# lesser files. A shot's sidecar is the only record of what the camera said
# about it, and X3 makes a stranded companion the only surviving evidence that
# its subject ever existed; losing one is losing the thing that could have
# identified what else was lost.
MEDIA, SIDECAR, OTHER = "media", "sidecar", "other"


class Census(NamedTuple):
    """What lay below a folder at one moment, in the terms a loss shows up in.

    Four totals, and a window must lower none of them: ``files`` (every file
    at any depth), ``media`` (the images and videos among them), ``sidecars``
    (the companions -- X6, so previews and OCR text count), and ``bytes``.
    They are what ``census_loss`` decides on.

    Bytes are a total in their own right because a file can be destroyed
    without disappearing: overwritten in place, or truncated, it is still one
    file with one name, and only its size says it is not the same file any
    more.

    ``sizes`` is the same files as a sorted ``(size, name)`` multiset, which
    renaming and moving within the subtree leave untouched -- so what fails to
    cancel between two of them names the file that did not come back.
    ``unreadable`` is every path the walk could not read: a census carrying one
    has undercounted, and says so rather than being quietly trusted.
    """

    files: int
    media: int
    sidecars: int
    bytes: int
    sizes: tuple
    unreadable: tuple


def _plain_extended_path(path):
    """No long-path prefix. The fallback for a caller with no path library."""
    return str(path)


def _plain_is_reparse_point(entry):
    """True for a junction, symlink or mount point (T4).

    The fallback used when no path-safety library is injected. The pipeline
    runs on short archive paths and has no such library; the restructuring
    tool has one and passes it, which is what ``paths`` below is for.
    """
    try:
        return bool(entry.stat(follow_symlinks=False).st_reparse_tag)
    except AttributeError:
        return entry.is_symlink()          # non-Windows
    except OSError:
        return True                        # unreadable: treat as untrusted


def folder_census(folder, classify=None, paths=None) -> Census:
    """Count every file below ``folder``, however deep.

    ``classify`` reads one filename and answers ``MEDIA``, ``SIDECAR`` or
    ``OTHER``; without it those two totals stay 0 and the file and byte counts
    are the only evidence. ``paths`` is an optional path-safety
    library supplying ``extended_path`` (the long-path prefix a deep tree
    needs, T6) and ``is_reparse_point`` (T4);
    ``tools/canonicalise_timestamp_names`` is one, and is what the
    restructuring tool passes. Without it the standard library is used
    directly, which is what the pipeline already does everywhere else.

    A reparse point is refused rather than followed, and recorded: a census
    that skipped a junction has not counted what is behind it either time, and
    two such readings only mean something together with what they missed.

    Nothing here opens, moves, renames or writes a file. It reads directory
    entries and their sizes, and that is deliberately all it can do.
    """
    extended_path = getattr(paths, "extended_path", _plain_extended_path)
    is_reparse_point = getattr(paths, "is_reparse_point", _plain_is_reparse_point)
    kind_of = classify or (lambda name: OTHER)

    files = media = sidecars = total_bytes = 0
    sizes, unreadable = [], []
    pending = [Path(folder)]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(extended_path(directory)) as scan:
                entries = list(scan)
        except OSError as error:
            unreadable.append("%s (%s)" % (directory, error))
            continue
        for entry in entries:
            try:
                if is_reparse_point(entry):
                    unreadable.append(
                        "%s (reparse point, not followed)" % entry.path)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                    continue
                size = entry.stat(follow_symlinks=False).st_size
            except OSError as error:
                unreadable.append("%s (%s)" % (entry.path, error))
                continue
            files += 1
            total_bytes += size
            sizes.append((size, entry.name))
            kind = kind_of(entry.name)
            if kind == MEDIA:
                media += 1
            elif kind == SIDECAR:
                sidecars += 1
    return Census(files, media, sidecars, total_bytes,
                  tuple(sorted(sizes)), tuple(sorted(unreadable)))


def census_record(census: Census) -> dict:
    """The census as journal fields: the counts, never the file list.

    One journal line per window, and a month folder holds thousands of files
    -- the list would bury every other event in a file somebody reads to find
    out what a run did. What the counts do not say, the alarm says in full.
    """
    return {
        "files": census.files,
        "media": census.media,
        "sidecars": census.sidecars,
        "bytes": census.bytes,
        "unreadable": list(census.unreadable),
    }


def census_loss(before: Census, after: Census) -> list:
    """Every total ``after`` came back lower on, or ``[]`` when none did.

    All four are checked, and any one of them is enough. They catch different
    losses and none of them subsumes another:

    * **files** -- the plain disappearance;
    * **media** -- a shot lost while something else arrived, which the file
      count alone would show as no change at all;
    * **sidecars** -- the same for a companion, and companions are where the
      overwrites land, since two shots in one second are named apart long
      before their "._exif" files are;
    * **bytes** -- a file destroyed without disappearing. Overwritten in place
      or truncated, it is still one file under one name: every count above is
      unchanged and the only thing that moved is the size.

    Only a drop counts. A window is expected to create folders, rename every
    file it touches and move files down into the sub-events it makes; none of
    that lowers any of the four. A rise is not a loss -- a grouper that writes
    a state file of its own has taken nothing away.
    """
    losses = []
    if after.files < before.files:
        losses.append(
            "%d file(s) went missing: %d before, %d after"
            % (before.files - after.files, before.files, after.files))
    if after.media < before.media:
        losses.append(
            "%d image(s)/video(s) went missing: %d before, %d after"
            % (before.media - after.media, before.media, after.media))
    if after.sidecars < before.sidecars:
        losses.append(
            "%d sidecar(s)/companion(s) went missing: %d before, %d after"
            % (before.sidecars - after.sidecars, before.sidecars, after.sidecars))
    if after.bytes < before.bytes:
        losses.append(
            "%s byte(s) of content went missing: %s before, %s after"
            % (format(before.bytes - after.bytes, ","),
               format(before.bytes, ","), format(after.bytes, ",")))
    return losses


def census_vanished(before: Census, after: Census) -> list:
    """``[(size, name)]`` whose size is no longer accounted for -- evidence.

    Compared as a multiset of sizes because the grouper renames everything it
    touches: a file that came back under another name still occupies a slot of
    its own size, so what is left over once the two are cancelled against each
    other is what did not come back at all.

    This decides nothing -- ``census_loss`` does, off the counts. A file the
    grouper rewrote rather than moved would surface here too. It is here to
    answer the question that follows the alarm: which one, and how big was it.
    """
    remaining = collections.Counter(size for size, _name in after.sizes)
    vanished = []
    for size, name in before.sizes:
        if remaining[size]:
            remaining[size] -= 1
        else:
            vanished.append((size, name))
    return vanished


class GrouperLostFiles(Exception):
    """A grouper window left fewer files below the folder than it found.

    Raised rather than returned because there is nothing sensible for a caller
    to do with it except stop: a second window would be opened on an archive
    that has already lost something, and every step after this one rewrites
    names -- which are the last record of what the missing file was called.
    """

    def __init__(self, folder, scope, before, after, losses, vanished):
        self.folder = Path(folder)
        self.scope = Path(scope)
        self.before = before
        self.after = after
        self.losses = list(losses)
        self.vanished = list(vanished)
        super().__init__("%s: %s" % (self.folder.name, "; ".join(self.losses)))


def census_scope(folder) -> Path:
    """The folder a window's before/after counts are taken over: its parent.

    One definition, because the two counts being over the same thing is the
    whole of what makes them comparable, and because a caller that computed
    the scope itself could compute it differently after the window than
    before -- exactly when the folder has been renamed away and the answer
    matters most.
    """
    return Path(folder).parent


def guard_grouper_window(folder, before, after):
    """Raise ``GrouperLostFiles`` when a window took files away; else return.

    The one place the two censuses are compared, so no caller can bracket a
    window with counts and then forget to act on them.
    """
    losses = census_loss(before, after)
    if not losses:
        return
    raise GrouperLostFiles(
        folder, census_scope(folder), before, after,
        losses, census_vanished(before, after))
