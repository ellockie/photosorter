from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage


class InitializationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="initialization",
            display_name="Initialization",
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        paths = context.config.get("paths", {})
        for key in ("root_folder", "unsorted_folder", "ready_folder", "temp_root"):
            value = paths.get(key)
            if not value:
                continue
            Path(value).mkdir(parents=True, exist_ok=True)

        context.snapshot_inputs([paths.get("unsorted_folder")])
        context.counters["input_files"] = len(context.input_snapshot)
        context.log(f"Captured input safety snapshot: {len(context.input_snapshot)} files")
        return context
