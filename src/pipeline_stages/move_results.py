from src.core import \
    PipelineContext, \
    PipelineStage


class MoveResultsStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="move-results",
            display_name="Move Results",
            dependencies=("raw-staged-conversion",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        context.counters["result_assets_ready"] = len([
            asset
            for asset in context.assets
            if asset.primary_path.exists()
        ])
        context.log(f"Prepared {context.counters['result_assets_ready']} result assets for final sorting")
        return context
