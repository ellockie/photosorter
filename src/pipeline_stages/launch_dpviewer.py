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
            context.create_prompt(
                "dpviewer_conversion",
                {"asset_count": len(cr2_assets)},
                self.stage_id,
            )
        context.counters["dpviewer_candidates"] = len(cr2_assets)
        context.log(f"Prepared {len(cr2_assets)} CR2 assets for DPViewer")
        return context
