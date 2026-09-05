from src.core import \
    PipelineContext, \
    PipelineStage


class ConvertCrwsStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="convert-crws",
            display_name="Convert CRWs",
            dependencies=("rename-and-sort",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        crw_assets = [
            asset
            for asset in context.assets
            if asset.primary_path.suffix.lower() == ".crw" and asset.primary_path.exists()
        ]
        if crw_assets:
            prompt = context.create_prompt(
                "crw_conversion",
                {
                    "asset_count": len(crw_assets),
                    "paths": [str(asset.primary_path) for asset in crw_assets[:20]],
                },
                self.stage_id,
            )
            # Hold the pipeline here until the conversion is actually done;
            # later stages move these files out from under the converter.
            context.await_prompt(prompt, auto_answer={"done": True})
        context.counters["crw_conversion_candidates"] = len(crw_assets)
        context.log(f"Prepared {len(crw_assets)} CRW assets for conversion")
        return context
