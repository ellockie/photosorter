import datetime

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.timezone_engine import \
    correct, \
    format_stamp, \
    has_timezone_config, \
    is_ambiguous_reading


class TimezoneAndTravelStage(PipelineStage):
    """Apply the two-timeline correction (design.md Decision 9) before naming.

    Reads each asset's raw ``captured_at`` reading, runs it through the camera
    and location timelines, and writes back the corrected display time so the
    filename and event folder reflect the lived local time and place.
    """

    def __init__(self):
        super().__init__(
            stage_id="timezone-and-travel",
            display_name="Timezone and Travel",
            dependencies=("metadata-extraction",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not has_timezone_config(context.config):
            context.log("Timezone/travel: no timelines configured, leaving readings unchanged")
            return context

        corrected = 0
        ambiguous: list[str] = []
        for asset in context.assets:
            captured_at = asset.metadata.get("captured_at")
            if isinstance(captured_at, str):
                captured_at = datetime.datetime.fromisoformat(captured_at)
            if not isinstance(captured_at, datetime.datetime):
                continue

            camera_symbol = asset.metadata.get("camera_symbol", "")
            result = correct(context.config, captured_at, camera_symbol)
            display = result["display"]
            asset.metadata["captured_at_corrected"] = display
            if "image_datetime" in asset.metadata:
                # The corrected time must drive the final filename and folder.
                asset.metadata["image_datetime"] = format_stamp(display)
            if result["label"]:
                asset.metadata["location_suffix"] = result["label"]
            if result["zone"]:
                asset.metadata["location_zone"] = result["zone"]
            if result["coords"]:
                asset.metadata["location_coords"] = result["coords"]
            if is_ambiguous_reading(context.config, camera_symbol, captured_at):
                asset.metadata["clock_ambiguous"] = True
                ambiguous.append(asset.primary_path.name)
            corrected += 1

        context.counters["timezone_corrected_assets"] += corrected
        context.log(f"Applied timezone/travel corrections to {corrected} assets")
        if ambiguous:
            # Backward-jump (repeated-hour) readings defaulted to the corrected
            # interval; surface them for optional hand-nudging.
            context.counters["timezone_ambiguous_assets"] += len(ambiguous)
            context.log(
                f"{len(ambiguous)} reading(s) fell in a repeated-hour window and were "
                f"resolved to the corrected zone: {', '.join(ambiguous)}"
            )
        return context
