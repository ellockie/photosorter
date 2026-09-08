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
            description=(
                "Runs ExifTool once over the whole INBOX to write one ._exif sidecar per "
                "media file. One external process per chunk, so cost tracks the number of "
                "files, not their size."
            ),
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
            context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)
            return context

        base_command = [
            exiftool,
            "-a",
            "-u",
            "-g1",
            "-w!",
            WRITE_FORMAT,
        ]
        # Chunked because a Windows command line has a length limit, and a
        # chunk is the only unit of progress there is: ExifTool says nothing
        # until the whole batch it was given returns. Counting them is the
        # difference between "running" and "3 of 14 batches done".
        chunks = list(chunk_targets(targets))
        context.log(
            f"Running {exiftool} over {len(targets)} file(s) "
            f"in {len(chunks)} batch(es) of up to {MAX_COMMAND_CHARS} command characters"
        )
        reporter = context.progress(
            self.stage_id,
            "Running ExifTool",
            total=len(targets),
            unit="files",
        )
        for index, chunk in enumerate(chunks, start=1):
            reporter.set_activity(
                "Running ExifTool", note=f"batch {index}/{len(chunks)} ({len(chunk)} files)")
            try:
                subprocess.check_call(base_command + chunk)
                reporter.advance(len(chunk))
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
                context.log(
                    f"ExifTool reported errors in batch {index}/{len(chunks)} "
                    f"(exit code {error.returncode}); the readable files in it still "
                    "got sidecars"
                )
                reporter.advance(len(chunk), errors=1)
            except OSError as error:
                context.log(f"ExifTool batch failed: {error}")
                break

        context.log(reporter.finish())
        created = len(list(unsorted.glob("*._exif")))
        failed = max(0, len(targets) - created)
        context.set_stage_stats(
            self.stage_id,
            inputs=len(targets),
            outputs=created,
            errors=failed,
            batches=len(chunks),
        )
        context.log(f"Generated {created} EXIF sidecars for {len(targets)} media files")
        if failed:
            note = (
                f"{failed} file(s) got no EXIF sidecar -- ExifTool could not read them; "
                "they will have no capture time downstream"
            )
            context.log(note)
            context.add_stage_note(self.stage_id, note)
        return context
