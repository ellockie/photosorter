from pathlib import Path

from src.core import \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.utils.progress import \
    format_bytes, \
    format_count


class UploadHarvestStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="upload-harvest",
            display_name="Upload Harvest",
            description=(
                "Moves the camera photos and videos left in Camera Uploads into the "
                "INBOX, asking what to do whenever a name is already taken."
            ),
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

        candidates = [
            path for path in source.iterdir()
            if path.is_file() and path.suffix.lower() in extensions
        ]
        moved = 0
        # Only what actually landed. A file left behind by a collision prompt
        # is still in Camera Uploads, which is not an output root, so watching
        # it would have the safety check report it lost at the end of a run
        # that never took it.
        arrived = []
        for path in candidates:
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
            arrived.append(target)
            moved += 1

        context.counters["uploaded_files_moved"] += moved
        context.log(f"Moved {moved} uploaded files into the unsorted folder")

        # These arrived after the opening snapshot, so nothing was watching
        # them until now (see PipelineContext.extend_snapshot).
        watched = context.extend_snapshot(arrived, stage_id=self.stage_id)
        context.set_stage_stats(
            self.stage_id,
            inputs=len(candidates),
            outputs=moved,
            watched=watched["files"],
            bytes=watched["bytes"],
        )
        if watched["files"]:
            context.log(
                f"Now under the safety check: {format_count(watched['files'])} harvested "
                f"file(s), {format_bytes(watched['bytes'])}"
            )
            if watched["already_known"]:
                # Byte-identical to something already watched -- one checksum
                # covers both, which is why the two counts differ.
                context.log(
                    f"  {format_count(watched['already_known'])} of them are byte-identical "
                    "to a file already in the snapshot"
                )
        return context
