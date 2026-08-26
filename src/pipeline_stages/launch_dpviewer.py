from src.core import \
    PipelineContext, \
    PipelineStage


class LaunchDpviewerStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="launch-dpviewer",
            display_name="Launch DPViewer",
            dependencies=("convert-crws",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        cr2_assets = [
            asset
            for asset in context.assets
            if asset.primary_path.suffix.lower() == ".cr2" and asset.primary_path.exists()
        ]
        if cr2_assets:
            prompt = context.create_prompt(
                "dpviewer_conversion",
                {
                    "asset_count": len(cr2_assets),
                    "paths": [str(asset.primary_path) for asset in cr2_assets[:20]],
                },
                self.stage_id,
            )
            # Hold the pipeline here until DPViewer has finished; later stages
            # move these files out from under it.
            context.await_prompt(prompt, auto_answer={"done": True})
        context.counters["dpviewer_candidates"] = len(cr2_assets)
        context.log(f"Prepared {len(cr2_assets)} CR2 assets for DPViewer")
        return context
