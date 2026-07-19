import re
import subprocess
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage

# Summary line logged by screenshot_grouper.daily_batch --all
_BATCH_SUMMARY = re.compile(r"moved (\d+) file\(s\) across (\d+) day\(s\)")


class ScreenshotGroupingStage(PipelineStage):
    """Sort classified screenshots into dated group folders.

    Delegates to the external screenshot-grouper project (shared with the
    Mac workflow): its all-days batch mode standardizes filenames and moves
    each completed day's files into a "YYYY-MM-DD__HH.MM.SS - __TO_SPLIT__"
    folder, ready for naming/splitting in the grouper GUI.
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
        if not python_exe.is_file() or not project_path.is_dir():
            context.log(
                "Screenshot grouper not available "
                f"(python: {python_exe}, project: {project_path}), skipping"
            )
            return context

        target_folders = self._target_folders(context.config, settings)
        moved_total = 0
        days_total = 0
        errors = 0

        for folder in target_folders:
            if not folder.is_dir():
                context.log(f"Screenshot grouping target missing, skipping: {folder}")
                continue
            result = subprocess.run(
                [str(python_exe), "-m", "screenshot_grouper.daily_batch", "--all", str(folder)],
                cwd=str(project_path),
                capture_output=True,
                text=True,
            )
            output = (result.stdout or "") + (result.stderr or "")
            if result.returncode != 0:
                errors += 1
                tail = output.strip().splitlines()[-5:]
                context.log(f"Screenshot grouper failed for {folder.name}:")
                for line in tail:
                    context.log(f"  ! {line}")
                continue
            match = _BATCH_SUMMARY.search(output)
            moved = int(match.group(1)) if match else 0
            days = int(match.group(2)) if match else 0
            moved_total += moved
            days_total += days
            context.log(
                f"Screenshot grouping {folder.name}: {moved} files into {days} day folder(s)"
            )

        context.counters["screenshots_grouped"] += moved_total
        context.set_stage_stats(
            self.stage_id, inputs=moved_total, outputs=moved_total, errors=errors)
        context.log(
            f"Grouped {moved_total} screenshots into {days_total} dated folder(s)"
        )
        return context

    def _target_folders(self, config: dict, settings: dict) -> list[Path]:
        paths = config.get("paths", {})
        base = Path(
            paths.get("ingest", {}).get("camera_uploads")
            or paths.get("camera_uploads")
            or ""
        )
        folders = []
        for value in settings.get("target_folders", []):
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = base / candidate
            folders.append(candidate)
        return folders
