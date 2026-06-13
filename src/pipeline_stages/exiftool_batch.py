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
        context.log(f"Removed {removed} stale EXIF sidecars")

        media_exts = context.media_extensions()
        targets = [
            p for p in unsorted.iterdir()
            if p.is_file() and p.suffix.lower() in media_exts
        ]
        if not targets:
            context.log("ExifTool batch skipped: no media files found")
            return context

        command = [
            exiftool,
            "-a",
            "-u",
            "-g1",
            "-w!",
            "%d%f.%e._exif",
            *[str(p) for p in targets],
        ]
        try:
            subprocess.check_call(command)
        except FileNotFoundError:
            context.log("ExifTool executable not found; batch generation skipped")
        return context
