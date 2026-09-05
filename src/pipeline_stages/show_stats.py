from src.core import \
    PipelineContext, \
    PipelineStage


class ShowStatsStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="show-stats",
            display_name="Show Stats",
            dependencies=("folder-sorting",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        assets = context.counters.get("assets", 0)
        renamed = context.counters.get("renamed_assets", 0)
        sorted_assets = context.counters.get("sorted_assets", 0)
        prompts = len(context.prompt_queue)
        context.log(
            f"Stats: assets={assets}, renamed={renamed}, sorted={sorted_assets}, prompts={prompts}"
        )
        return context
