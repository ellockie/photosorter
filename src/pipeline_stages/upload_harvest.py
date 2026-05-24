from pathlib import Path

from src.core import \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineStage, \
    safe_move


class UploadHarvestStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="upload-harvest",
            display_name="Upload Harvest",
            dependencies=("move-other-images",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        paths = context.config.get("paths", {})
        source = Path(paths.get("ingest", {}).get("camera_uploads") or paths.get("camera_uploads", ""))
        destination = Path(paths.get("unsorted_folder", ""))
        extensions = context.media_extensions()

        if not source.exists() or not destination.exists():
            context.log("Upload harvest skipped: source or destination does not exist")
            return context

        moved = 0
        for path in source.iterdir():
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            target = destination / path.name
            if target.exists():
                result = NameCollisionResolver.from_context(context).resolve(
                    target,
                    path,
                    context,
                    self.stage_id,
                )
                if result.target_path:
                    target = result.target_path
                elif result.prompt:
                    context.log("Upload harvest paused for collision prompt")
                    break
            safe_move(path, target)
            moved += 1

        context.counters["uploaded_files_moved"] += moved
        context.log(f"Moved {moved} uploaded files into the unsorted folder")
        return context
