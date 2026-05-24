import datetime

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.legacy import \
    apply_camera_clock_corrections, \
    apply_trip_timezone


class TimezoneAndTravelStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="timezone-and-travel",
            display_name="Timezone and Travel",
            dependencies=("metadata-extraction",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        corrected = 0
        for asset in context.assets:
            captured_at = asset.metadata.get("captured_at")
            if isinstance(captured_at, str):
                captured_at = datetime.datetime.fromisoformat(captured_at)
            if not isinstance(captured_at, datetime.datetime):
                continue

            camera_symbol = asset.metadata.get("camera_symbol", "")
            adjusted = apply_camera_clock_corrections(captured_at, camera_symbol, context.config)
            adjusted, location_suffix = apply_trip_timezone(adjusted, context.config)
            asset.metadata["captured_at_corrected"] = adjusted
            if location_suffix:
                asset.metadata["location_suffix"] = location_suffix
            corrected += 1

        context.counters["timezone_corrected_assets"] += corrected
        context.log(f"Applied timezone/travel corrections to {corrected} assets")
        return context
