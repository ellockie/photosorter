import re
import subprocess
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.legacy import date_folder_suffix

_YEAR_DIR = re.compile(r"\d{4}")
_TO_SPLIT_MARKER = "__TO_SPLIT__"


def _extension_sets(config: dict) -> tuple[set[str], set[str]]:
    extensions = config.get("extensions", {})
    video_exts = {value.lower() for value in extensions.get("videos", [])}
    image_exts = {
        value.lower()
        for group in ("lossy_images", "other_images", "raw_images")
        for value in extensions.get(group, [])
    }
    return image_exts, video_exts


def _count_top_level_media(folder: Path, image_exts: set[str], video_exts: set[str]) -> tuple[int, int]:
    """Count top-level image and video files (what the grouper GUI will show)."""
    images = 0
    videos = 0
    for path in folder.iterdir():
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in video_exts:
            videos += 1
        elif suffix in image_exts:
            images += 1
    return images, videos


def _to_split_suffix(images: int, videos: int) -> str:
    # "=" not ":" — the grouper uses ":" on macOS but Photosorter is Windows,
    # where ":" is illegal in filenames (matches COUNT_SEPARATOR in the grouper).
    parts = []
    if images:
        parts.append(f"i={images}")
    if videos:
        parts.append(f"v={videos}")
    return "(" + "_".join(parts) + ")" if parts else ""


class ScreenshotGroupingStage(PipelineStage):
    """Launch the grouper GUI on each freshly sorted, ungrouped event folder.

    After folder-sorting drops photos into event folders like
    "2026-07-18_(Sat) - 1. ######", this stage renames the placeholder
    suffix to the grouper's "__TO_SPLIT__(i=N_v=M)" convention and opens the
    external screenshot-grouper GUI (alternative thumbnail grouper) on each
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

        python_exe = Path(settings.get("python", ""))
        project_path = Path(settings.get("project_path", ""))
        main_script = project_path / "main.py"
        if not python_exe.is_file() or not main_script.is_file():
            context.log(
                "Screenshot grouper not available "
                f"(python: {python_exe}, project: {project_path}), skipping"
            )
            return context

        candidates = self._candidate_folders(context.config)
        max_folders = settings.get("max_folders", 0)
        if max_folders and len(candidates) > max_folders:
            context.log(
                f"Found {len(candidates)} folders to group, limiting to {max_folders} "
                "(screenshot_grouping.max_folders)"
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
            context.log(f"Launching grouper GUI on {target.name}")
            try:
                result = subprocess.run(
                    [str(python_exe), str(main_script), "--alternative", str(target)],
                    cwd=str(project_path),
                )
            except OSError as error:
                errors += 1
                context.log(f"  ! could not launch grouper for {target.name}: {error}")
                continue
            if result.returncode != 0:
                errors += 1
                context.log(
                    f"  ! grouper exited with code {result.returncode} for {target.name}"
                )
                continue
            launched += 1

        context.counters["screenshot_folders_grouped"] += launched
        context.set_stage_stats(
            self.stage_id, inputs=len(candidates), outputs=launched, errors=errors)
        context.log(f"Grouped {launched} event folder(s) via the grouper GUI")
        return context

    def _candidate_folders(self, config: dict) -> list[Path]:
        """Event folders under root that still need grouping (most recent first).

        Matches folders whose name carries the placeholder date suffix
        (" - 1. ######") or already the "__TO_SPLIT__" marker, at the
        root/YYYY/<Month>/<event> level only — so the ingest pipeline, READY,
        and legacy trees are never scanned.
        """
        root = Path(config["paths"]["root_folder"])
        if not root.is_dir():
            return []

        placeholder = date_folder_suffix(config)
        found: list[Path] = []
        for year_dir in root.iterdir():
            if not year_dir.is_dir() or not _YEAR_DIR.fullmatch(year_dir.name):
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir():
                    continue
                for event_dir in month_dir.iterdir():
                    if not event_dir.is_dir():
                        continue
                    if event_dir.name.endswith(placeholder) or _TO_SPLIT_MARKER in event_dir.name:
                        found.append(event_dir)

        # Most recent day first: the YYYY-MM-DD prefix sorts lexically.
        found.sort(key=lambda p: str(p), reverse=True)
        return found

    def _prepare_folder(self, context: PipelineContext, folder: Path,
                        image_exts: set[str], video_exts: set[str]) -> Path | None:
        """Rename a placeholder folder to the __TO_SPLIT__ convention.

        Returns the folder to open in the GUI, or None if it holds no
        top-level media to group. Folders already carrying the __TO_SPLIT__
        marker are opened as-is.
        """
        images, videos = _count_top_level_media(folder, image_exts, video_exts)
        if images == 0 and videos == 0:
            context.log(f"Skipping {folder.name}: no top-level media to group")
            return None

        if _TO_SPLIT_MARKER in folder.name:
            return folder

        placeholder = date_folder_suffix(context.config)
        base = folder.name[: -len(placeholder)] if folder.name.endswith(placeholder) else folder.name
        new_name = f"{base} - {_TO_SPLIT_MARKER}{_to_split_suffix(images, videos)}"
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
