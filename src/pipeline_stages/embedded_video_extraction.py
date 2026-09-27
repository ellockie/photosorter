"""Extract the video every motion photo carries, as it is filed (X16).

The pipeline half of ``embedded_videos.py``; that module holds all of the
finding and the ExifTool invocation, shared with the restructure tool (T8).

It runs **after** ``folder-sorting``, over the stills that stage has just put
in the archive: the extraction is named after the still's final name (X1) and
written into the ``__VIDEOS_EXTRACTED`` beside it (X10), so extracting any
earlier would name it after a file that is about to be renamed. And it runs
**before** the grouper, so when the grouper moves a still into a sub-event,
``companion-reconciliation`` carries the extraction after it like any other
companion.
"""

from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    project_root
from src.pipeline_stages.embedded_videos import \
    extract, \
    extraction_enabled, \
    find_pending
from src.pipeline_stages.exiftool_sidecars import exiftool_command


class EmbeddedVideoExtractionStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="embedded-video-extraction",
            display_name="Embedded Video Extraction",
            description=(
                "Extracts the video a motion photo carries into the __VIDEOS_EXTRACTED "
                "beside it, named after the still so it travels with it; the still is "
                "never rewritten."
            ),
            dependencies=("folder-sorting",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        config = context.config
        context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)
        if not extraction_enabled(config):
            context.log("Embedded video extraction disabled, skipping")
            return context

        stills = [asset.primary_path for asset in context.assets
                  if Path(asset.primary_path).exists()]
        exiftool = exiftool_command(config, project_root())
        pending = find_pending(stills, config, exiftool)
        context.set_stage_stats(self.stage_id, inputs=len(pending.pending))
        if not pending.pending:
            context.log(
                f"No motion photos awaiting extraction "
                f"({pending.examined} still(s) checked, {pending.probed} read by ExifTool)")
            return context

        result = extract(pending.pending, config, exiftool, log=context.log)
        failed = len(result.missing) + len(result.not_video)
        context.counters["embedded_videos_extracted"] += len(result.created)
        context.counters["embedded_video_errors"] += failed + result.errors
        context.set_stage_stats(self.stage_id, outputs=len(result.created),
                                errors=failed + result.errors)
        context.log(f"Extracted {len(result.created)} video(s) from "
                    f"{len(pending.pending)} motion photo(s)")
        # Named, not counted: a still whose video could not be lifted out is
        # what restructure step 7 will report as X16, so say which ones now.
        for subject in result.missing:
            context.log(f"  ! no video extracted from {subject.name}")
        for subject, target in result.not_video:
            context.log(f"  ! {target.name} from {subject.name} does not open as a video")
        return context
