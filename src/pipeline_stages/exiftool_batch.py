import subprocess
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    safe_delete


class ExiftoolBatchStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="exiftool-batch",
            display_name="ExifTool Batch",
            dependencies=("empty-file-quarantine",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        unsorted = Path(context.config["paths"]["unsorted_folder"])
        exiftool = context.config.get("external_tools", {}).get("exiftool", "exiftool")
        if not unsorted.exists():
            context.log("ExifTool batch skipped: unsorted folder does not exist")
            return context

        removed = 0
        for sidecar in unsorted.glob("*._exif"):
            safe_delete(sidecar)
            removed += 1

        command = [
            exiftool,
            "-a",
            "-u",
            "-g1",
            "-w!",
            "%f.%e._exif",
            str(unsorted),
        ]
        context.log(f"Removed {removed} stale EXIF sidecars")
        try:
            subprocess.check_call(command)
        except FileNotFoundError:
            context.log("ExifTool executable not found; batch generation skipped")
        return context
