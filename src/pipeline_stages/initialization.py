from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage
from src.utils.progress import \
    format_bytes, \
    format_count


class InitializationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="initialization",
            display_name="Initialization",
            description=(
                "Creates the pipeline folders if missing, then checksums every file "
                "waiting in the inbox so the run can prove at the end that none of them "
                "was lost. Reads every incoming byte, so it scales with intake size."
            ),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        paths = context.config.get("paths", {})
        created = []
        for key in ("root_folder", "unsorted_folder", "ready_folder", "temp_root"):
            value = paths.get(key)
            if not value:
                continue
            folder = Path(value)
            if not folder.exists():
                created.append(f"{key}={folder}")
            folder.mkdir(parents=True, exist_ok=True)
        context.log(
            f"Created {len(created)} missing folder(s): {', '.join(created)}"
            if created else "All pipeline folders already exist"
        )

        inbox = paths.get("unsorted_folder")
        context.log(f"Checksumming everything waiting in {inbox}")
        tally = context.snapshot_inputs([inbox], stage_id=self.stage_id)

        # Files, not snapshot entries: byte-identical inputs share one entry,
        # so counting the snapshot reported 251 for a 600-file intake and made
        # the dashboard look like 349 files had already gone missing.
        context.counters["input_files"] = tally["files"]
        context.counters["input_checksums"] = tally["unique"]
        context.counters["input_bytes"] = tally["bytes"]
        context.set_stage_stats(
            self.stage_id,
            inputs=tally["files"],
            outputs=tally["unique"],
            errors=0,
            bytes=tally["bytes"],
            folders_created=len(created),
        )
        context.log(
            f"Intake: {format_count(tally['files'])} file(s), {format_bytes(tally['bytes'])}, "
            f"{format_count(tally['unique'])} distinct checksum(s)"
        )
        if tally["duplicates"]:
            # Not a fault -- byte-identical inputs share one snapshot entry --
            # but it explains why "files in" and "checksums to find" differ,
            # which otherwise reads like files went missing before the run began.
            note = (
                f"{format_count(tally['duplicates'])} incoming file(s) are byte-identical "
                "to another and share one checksum"
            )
            context.counters["input_duplicate_files"] = tally["duplicates"]
            context.log(note)
            context.add_stage_note(self.stage_id, note)
        if not tally["files"]:
            context.add_stage_note(self.stage_id, "inbox is empty, nothing to ingest")
        return context
