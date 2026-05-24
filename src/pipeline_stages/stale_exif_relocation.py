from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.pipeline_stages.legacy import old_exif_folder


class StaleExifRelocationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="stale-exif-relocation",
            display_name="Stale EXIF Relocation",
            dependencies=("upload-harvest",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        inbox = Path(context.config["paths"]["inbox_folder"])
        destination = old_exif_folder(context.config)
        destination.mkdir(parents=True, exist_ok=True)
        moved = 0

        if inbox.exists():
            for sidecar in inbox.glob("*._exif"):
                target = destination / sidecar.name
                if target.exists():
                    target = destination / f"{sidecar.stem}_old{sidecar.suffix}"
                safe_move(sidecar, target)
                moved += 1

        context.counters["moved_old_exifs"] += moved
        context.log(f"Relocated {moved} stale EXIF sidecars")
        return context
