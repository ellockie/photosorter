import datetime
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.legacy import \
    final_event_folder, \
    is_raw_extension, \
    subfolder_name


class FolderSortingStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="folder-sorting",
            display_name="Folder Sorting",
            dependencies=("move-results",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        moved = 0

        for asset in context.assets:
            if not asset.primary_path.exists():
                continue
            captured_at = asset.metadata.get("captured_at_corrected") or asset.metadata.get("captured_at")
            if isinstance(captured_at, str):
                captured_at = datetime.datetime.fromisoformat(captured_at)
            if captured_at is None:
                target_folder = Path(context.config["paths"]["ready_folder"])
            else:
                target_folder = final_event_folder(captured_at, context.config)

            if is_raw_extension(asset.primary_path.suffix, context.config):
                asset.move_all(target_folder / subfolder_name(context.config, "raw"))
            else:
                asset.move_all(target_folder)

            for name, sidecar_path in list(asset.sidecars.items()):
                if sidecar_path.exists() and sidecar_path.suffix.lower() == "._exif":
                    exif_folder = target_folder / subfolder_name(context.config, "exif")
                    exif_folder.mkdir(parents=True, exist_ok=True)
                    moved_sidecar = exif_folder / sidecar_path.name
                    sidecar_path.rename(moved_sidecar)
                    asset.sidecars[name] = moved_sidecar
            moved += 1

        context.counters["sorted_assets"] = moved
        context.log(f"Moved {moved} assets to the ready folder")
        return context
