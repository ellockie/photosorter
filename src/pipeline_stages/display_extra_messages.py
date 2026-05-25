from src.core import \
    PipelineContext, \
    PipelineStage


class DisplayExtraMessagesStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="display-extra-messages",
            display_name="Display Extra Messages",
            dependencies=("show-stats",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        if context.prompt_queue:
            context.log(f"Extra messages: {len(context.prompt_queue)} item(s) need attention")
        else:
            context.log("Extra messages: none")
        return context
