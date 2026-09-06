import subprocess
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    project_root, \
    safe_delete
from src.pipeline_stages.exiftool_sidecars import \
    MAX_COMMAND_CHARS, \
    WRITE_FORMAT, \
    chunk_targets, \
    exiftool_command


class ExiftoolBatchStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="exiftool-batch",
            display_name="ExifTool Batch",
            dependencies=("empty-file-quarantine",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        unsorted = Path(context.config["paths"]["unsorted_folder"])
        exiftool = exiftool_command(context.config, project_root())
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

        base_command = [
            exiftool,
            "-a",
            "-u",
            "-g1",
            "-w!",
            WRITE_FORMAT,
        ]
        for chunk in chunk_targets(targets):
            try:
                subprocess.check_call(base_command + chunk)
            except FileNotFoundError as error:
                # WinError 206 ("filename or extension is too long") also maps
                # to FileNotFoundError; do not mistake it for a missing binary.
                if getattr(error, "winerror", None) == 206:
                    context.log(f"ExifTool batch failed: command line too long ({error})")
                else:
                    context.log(f"ExifTool executable not found: {exiftool}")
                break
            except subprocess.CalledProcessError as error:
                # Exit code 1 means some files could not be read; the sidecars
                # for the remaining files were still written, so keep going.
                context.log(f"ExifTool reported errors (exit code {error.returncode})")
            except OSError as error:
                context.log(f"ExifTool batch failed: {error}")
                break

        created = len(list(unsorted.glob("*._exif")))
        failed = max(0, len(targets) - created)
        context.set_stage_stats(self.stage_id, inputs=len(targets), outputs=created, errors=failed)
        context.log(f"Generated {created} EXIF sidecars for {len(targets)} media files")
        if failed:
            context.log(f"Missing EXIF sidecars for {failed} media files")
        return context
