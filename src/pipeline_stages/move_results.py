import datetime
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.legacy import \
    final_event_folder


def _captured_at(asset) -> datetime.datetime | None:
    value = asset.metadata.get("captured_at_corrected") or asset.metadata.get("captured_at")
    if isinstance(value, str):
        value = datetime.datetime.fromisoformat(value)
    return value if isinstance(value, datetime.datetime) else None


class MoveResultsStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="move-results",
            display_name="Move Results",
            dependencies=("raw-staged-conversion",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        ready = [
            asset
            for asset in context.assets
            if asset.primary_path.exists()
        ]
        context.counters["result_assets_ready"] = len(ready)
        context.set_stage_stats(self.stage_id, inputs=len(context.assets), outputs=len(ready))
        context.log(f"Prepared {len(ready)} result assets for final sorting")

        # Preview the destination event folders. This uses the same captured-at
        # and label logic as FolderSortingStage, so the list matches where the
        # files will actually land.
        root = Path(context.config["paths"]["root_folder"])
        folders = set()
        for asset in ready:
            captured_at = _captured_at(asset)
            if captured_at is None:
                continue
            label = asset.metadata.get("origin_label") or asset.metadata.get("location_suffix")
            folders.add(final_event_folder(captured_at, context.config, label))

        if folders:
            context.log(f"Final folders ({len(folders)}):")
            for folder in sorted(folders, key=str):
                try:
                    shown = folder.relative_to(root)
                except ValueError:
                    shown = folder
                context.log(f"  - {shown}")

        return context
