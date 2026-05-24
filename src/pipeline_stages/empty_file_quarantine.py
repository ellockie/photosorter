from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.pipeline_stages.legacy import problematic_folder


class EmptyFileQuarantineStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="empty-file-quarantine",
            display_name="Empty File Quarantine",
            dependencies=("stale-exif-relocation",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        inbox = Path(context.config["paths"]["inbox_folder"])
        destination = problematic_folder(context.config, "empty")
        destination.mkdir(parents=True, exist_ok=True)
        moved = 0

        if inbox.exists():
            for path in inbox.iterdir():
                if not path.is_file() or path.stat().st_size != 0:
                    continue
                safe_move(path, destination / path.name)
                moved += 1

        context.counters["empty_files_quarantined"] += moved
        context.log(f"Quarantined {moved} zero-byte files")
        return context
