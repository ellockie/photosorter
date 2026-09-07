import subprocess
from pathlib import Path

from src.core import     PipelineContext,     PipelineStage
from src.pipeline_stages.legacy import date_folder_suffix
from src.pipeline_stages.grouper_launch import     MEDIA as _MEDIA,     OTHER as _OTHER,     SIDECAR as _SIDECAR,     GrouperLostFiles,     census_scope as _census_scope,     folder_census as _folder_census,     grouper_command as _grouper_command,     grouper_install,     guard_grouper_window as _guard_grouper_window,     run_grouper as _run_grouper,     stderr_tail as _stderr_tail
from src.pipeline_stages.parking import parking_area_for as _parking_area_for
from src.pipeline_stages.grouping_names import preview_extensions as _preview_extensions
from src.pipeline_stages.grouping_names import     companion_extension_spellings as _companion_extension_spellings,     companion_subject_name as _companion_subject_name
from src.pipeline_stages.grouping_names import     EMPTY_SUBFOLDERS_FOLDER as _EMPTY_SUBFOLDERS_FOLDER,     TO_SPLIT_MARKER as _TO_SPLIT_MARKER,     count_media as _count_media,     extension_sets as _extension_sets,     select_media as _select_media,     to_split_name as _to_split_name,     with_earliest_time as _with_earliest_time

# grouper_install is re-exported: the dashboard (src/server.py) imports it
# from here. Its definition, and the command line, moved to the leaf module
# grouper_launch.py so tools/restructure_archive.py can load them by file path
# without importing this package -- see that module's docstring.
__all__ = ["GrouperLostFiles", "ScreenshotGroupingStage", "grouper_install", "launch_grouper", "report_lost_files"]


def holds_no_files(folder: Path) -> bool:
    """True when nothing anywhere below ``folder`` is a file.

    Empty means empty all the way down. A day whose media was routed into
    a legacy "__VIDEOS" is not empty -- it is a day the GUI happens not to show,
    which
    is a different thing and handled separately.
    """
    try:
        return not any(path.is_file() for path in folder.rglob("*"))
    except OSError:
        return False                  # unreadable: leave it exactly where it is


# How many of the files a window took away are named in the log before the
# list is cut off. Enough to recognise the shot; short enough that the alarm
# still fits on a screen, with the count of the rest after it.
VANISHED_TO_NAME = 12


def census_classifier(config: dict):
    """``kind(name)`` for the census: media, sidecar, or anything else.

    Both readings come off the project's own definitions rather than a list
    spelled here (T8): ``count_media`` for what an image or a video is, and
    ``companion_subject_name`` over every companion extension there is --
    "._exif", the ".THM.jpg"/".lrv" previews, the ".OCR.txt" -- for what is a
    companion of something. X6 makes all of those sidecars; the census counts
    them as one number because they are lost the same way.

    Media is asked first only because it is the cheaper question. The two
    cannot both be true: ``count_media`` already excludes previews (X7), and no
    companion extension is in the image or video sets.
    """
    image_exts, video_exts = _extension_sets(config)
    preview_exts = _preview_extensions(config)
    companion_exts = set(_companion_extension_spellings(config))

    def kind(name: str) -> str:
        images, videos = _count_media([name], image_exts, video_exts, preview_exts)
        if images or videos:
            return _MEDIA
        if _companion_subject_name(name, companion_exts) is not None:
            return _SIDECAR
        return _OTHER

    return kind


def census_line(which: str, census, scope: Path) -> str:
    """One reading, in the four totals a window must not lower.

    All four every time, rather than only the one that later breaks: the line
    written before the window opens is the only record of what was there to
    lose, and it is written before anybody knows whether anything will be.
    """
    return ("  %-8s %d file(s), %d media, %d sidecar(s), %s byte(s) below %s"
            % (which + ":", census.files, census.media, census.sidecars,
               format(census.bytes, ","), scope.name))


def report_lost_files(context: PipelineContext, error: GrouperLostFiles) -> None:
    """Say in full what a window took away.

    The loudest thing this stage says, and the only place the evidence exists
    at all: the file is already gone, and the names it went missing under are
    about to be rewritten by the passes that follow. Written to the log the
    dashboard shows, so it reaches a reviewer who never sees a console.
    """
    context.log("")
    context.log("!!! FILES WENT MISSING WHILE THE GROUPER WAS OPEN !!!")
    context.log(f"    folder opened:  {error.folder}")
    context.log(f"    counted below:  {error.scope}")
    for loss in error.losses:
        context.log(f"    {loss}")
    if error.vanished:
        context.log("    no longer accounted for "
                    "(size, and the name it had BEFORE the window opened):")
        for size, name in error.vanished[:VANISHED_TO_NAME]:
            context.log(f"      {size:>12,} B  {name}")
        if len(error.vanished) > VANISHED_TO_NAME:
            context.log(f"      ... and {len(error.vanished) - VANISHED_TO_NAME} more")
    for path in error.before.unreadable + error.after.unreadable:
        context.log(f"    ! not counted either time: {path}")
    context.log("    Nothing further is opened. Recover the file(s) from a "
                "backup or from Dropbox version history, and check the "
                "grouper before running this again.")


def launch_grouper(context: PipelineContext, folder: Path,
                   python_exe: Path, project_path: Path) -> bool:
    """Open the grouper GUI on one folder, blocking until its window closes.

    Bracketed by a file count, taken over the folder's parent and logged both
    times. The grouper is a separate project bound by neither T1 nor T2, and
    handed two files captured in the same second it has been seen to rename
    both onto one name and lose the one underneath -- so the one thing this
    project can still do is count what it handed over and count it again.

    Returns True when the window exited cleanly. Every failure is logged
    rather than raised, so one bad folder cannot take the rest of a batch down
    with it -- except a count that came back lower, which raises
    ``GrouperLostFiles`` and is meant to. Carrying on would open the next
    window on an archive that has already lost something, and let the passes
    after this one rewrite the names that are the last record of what it was.
    """
    scope = _census_scope(folder)
    classify = census_classifier(context.config)
    before = _folder_census(scope, classify, paths=None)
    context.log(f"Launching grouper GUI on {folder.name}")
    context.log(census_line("before", before, scope))
    for path in before.unreadable:
        context.log(f"  ! not counted: {path}")
    try:
        result = _run_grouper(python_exe, project_path, folder)
    except OSError as error:
        # The window never opened, so nothing below the scope can have moved
        # and there is nothing to count a second time.
        context.log(f"  ! could not launch grouper for {folder.name}: {error}")
        return False
    after = _folder_census(scope, classify, paths=None)
    context.log(census_line("after", after, scope))
    for path in after.unreadable:
        context.log(f"  ! not counted: {path}")
    # Before the exit code is even looked at: a window that crashed after
    # destroying a file has still destroyed it, and that is the finding that
    # decides what happens next.
    _guard_grouper_window(folder, before, after)
    if result.returncode != 0:
        # The bare exit code says nothing about what went wrong -- the
        # grouper's own message (an argparse usage error, a traceback) only
        # reaches its stderr, so echo the tail of it here.
        context.log(
            f"  ! grouper exited with code {result.returncode} for {folder.name}"
        )
        context.log("    command: %s" % subprocess.list2cmdline(
            _grouper_command(python_exe, project_path, folder)))
        for line in _stderr_tail(result.stderr):
            context.log(f"    {line}")
        return False
    return True


class ScreenshotGroupingStage(PipelineStage):
    """Launch the grouper GUI on each freshly sorted, ungrouped event folder.

    After folder-sorting drops photos into event folders like
    "2026-07-18_(Sat) - 1. ######", this stage renames the placeholder
    suffix to the grouper's "__TO_SPLIT__(i=N_v=M)" convention and opens the
    external screenshot-grouper GUI (the Image Grouper thumbnail view) on each
    folder, one at a time, so the day can be reviewed and split into named
    sub-event folders. Only the sorted photo tree under root_folder is
    touched — never the Dropbox intake folders.
    """

    def __init__(self):
        super().__init__(
            stage_id="screenshot-grouping",
            display_name="Screenshot Grouping",
            dependencies=("folder-sorting",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        settings = context.config.get("screenshot_grouping", {})
        context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)

        if not settings.get("enabled", False):
            context.log("Screenshot grouping disabled, skipping")
            return context

        install = grouper_install(settings)
        if install is None:
            context.log(
                "Screenshot grouper not available "
                f"(python: {settings.get('python', '')}, "
                f"project: {settings.get('project_path', '')}), skipping"
            )
            return context
        python_exe, project_path = install

        candidates = self._candidate_folders(context)
        max_folders = settings.get("max_folders", 0)
        if max_folders and len(candidates) > max_folders:
            context.log(
                f"Found {len(candidates)} folders to group, limiting to the first "
                f"{max_folders} in alphabetical order (screenshot_grouping.max_folders)"
            )
            candidates = candidates[:max_folders]

        if not candidates:
            context.log("No ungrouped event folders found, nothing to group")
            context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)
            return context

        image_exts, video_exts = _extension_sets(context.config)
        launched = 0
        errors = 0

        context.log(f"Grouping {len(candidates)} event folder(s), one at a time")
        for folder in candidates:
            target = self._prepare_folder(context, folder, image_exts, video_exts)
            if target is None:
                continue
            context.screenshot_grouped_folders.append(target)
            try:
                opened = launch_grouper(context, target, python_exe, project_path)
            except GrouperLostFiles as loss:
                # The one failure that ends the run rather than the folder.
                # Counted, said in full, and re-raised: the orchestrator marks
                # the stage FAILED and no later stage renames anything, which
                # is what keeps the missing file's last known name readable.
                report_lost_files(context, loss)
                errors += 1
                context.counters["screenshot_folders_grouped"] += launched
                context.set_stage_stats(
                    self.stage_id, inputs=len(candidates), outputs=launched,
                    errors=errors)
                raise
            if opened:
                launched += 1
            else:
                errors += 1

        context.counters["screenshot_folders_grouped"] += launched
        context.set_stage_stats(
            self.stage_id, inputs=len(candidates), outputs=launched, errors=errors)
        context.log(f"Grouped {launched} event folder(s) via the grouper GUI")
        return context

    def _candidate_folders(self, context: PipelineContext) -> list[Path]:
        """The event folders this run sorted assets into that still need grouping.

        Uses the list folder-sorting recorded (context.affected_event_folders)
        rather than scanning the archive, so only folders actually touched this
        run are opened — and never the Dropbox intake or ingest/READY trees.
        Keeps unlabelled days (the " - 1. ######" placeholder) and existing
        "__TO_SPLIT__" folders; labelled folders (trips) are already named and
        left alone. Alphabetical order.
        """
        placeholder = date_folder_suffix(context.config)
        found: list[Path] = []
        for folder in context.affected_event_folders:
            if not folder.is_dir():
                continue
            if folder.name.endswith(placeholder) or _TO_SPLIT_MARKER in folder.name:
                found.append(folder)

        # Alphabetical — the order Explorer shows, so it is always obvious
        # which folder the GUI is on and which are still to come. Because the
        # names open with "YYYY-MM-DD", that is also oldest day first.
        # Case-insensitive to match Windows' own collation.
        found.sort(key=lambda p: str(p).lower())
        return found

    def _park_empty_folder(self, context: PipelineContext, folder: Path) -> None:
        """Move an empty day folder into its month's ``__EMPTY_SUBFOLDERS``.

        Opening the grouper on a folder with nothing in it costs the reviewer a
        window to read and close, and teaches them to click through the GUI
        without looking -- the one habit this stage cannot afford. Parking it
        keeps the month folder down to the days that still want work, while
        keeping the folder itself: its name still records which day it was and
        what it held before it was emptied.

        The parking folder is a sibling of the folder being moved -- it sits
        where dated folders sit, so a day emptied out of a month folder is
        parked in that month folder and a sub-event emptied out of a group is
        parked in that group (H2). Neither leaves the level it was on, so what
        a folder was near is still what it is near. Created on first use.

        Nothing is overwritten. A folder of that name already parked means an
        earlier run put one there, and which of the two is which is not this
        stage's guess to make -- it says so and leaves the folder alone.
        """
        parking = _parking_area_for(folder)
        if parking is None:
            context.log(f"  ! {folder.name} is empty, but no conforming month "
                        "folder stands above it (H2); left where it is")
            return False
        destination = parking / folder.name
        if destination.exists():
            context.log(f"  ! {folder.name} is empty, but {_EMPTY_SUBFOLDERS_FOLDER}"
                        f" already holds that name; left in place")
            return
        try:
            parking.mkdir(exist_ok=True)
            folder.rename(destination)
        except OSError as error:
            context.log(f"  ! could not park empty {folder.name}: {error}")
            return
        context.counters["screenshot_folders_parked_empty"] += 1
        context.log(f"Parked empty {folder.name} in {_EMPTY_SUBFOLDERS_FOLDER}")

    def _prepare_folder(self, context: PipelineContext, folder: Path,
                        image_exts: set[str], video_exts: set[str]) -> Path | None:
        """Rename a placeholder folder to the __TO_SPLIT__ convention.

        Returns the folder to open in the GUI, or None when there is nothing to
        group: an empty folder, which is parked out of the way first, or one
        holding no top-level media. Folders already carrying the __TO_SPLIT__
        marker are opened as-is.
        """
        if holds_no_files(folder):
            self._park_empty_folder(context, folder)
            return None

        top_level_files = [path for path in folder.iterdir() if path.is_file()]
        preview_exts = _preview_extensions(context.config)
        media = _select_media(top_level_files, image_exts, video_exts, preview_exts)
        images, videos = _count_media(media, image_exts, video_exts, preview_exts)
        if images == 0 and videos == 0:
            context.log(f"Skipping {folder.name}: no top-level media to group")
            return None

        if _TO_SPLIT_MARKER in folder.name:
            return folder

        placeholder = date_folder_suffix(context.config)
        base = folder.name[: -len(placeholder)] if folder.name.endswith(placeholder) else folder.name
        new_name = _to_split_name(_with_earliest_time(base, media), images, videos)
        target = folder.with_name(new_name)
        if target == folder:
            return folder
        if target.exists():
            context.log(f"Cannot rename {folder.name}: {new_name} already exists, opening as-is")
            return folder
        try:
            folder.rename(target)
        except OSError as error:
            context.log(f"Could not rename {folder.name}: {error}, opening as-is")
            return folder
        return target
