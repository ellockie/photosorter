from pathlib import Path

from src.core import \
    MediaAsset, \
    PipelineContext, \
    StagedWorkspaceStage


class RawStagedConversionStage(StagedWorkspaceStage):
    def __init__(self):
        super().__init__(
            stage_id="raw-staged-conversion",
            display_name="RAW Staged Conversion",
            dependencies=("launch-dpviewer",),
            target_extensions=(".cr2", ".crw", ".arw"),
            sidecar_extension_map={"converted_jpg": ".jpg"},
            headless=True,
        )

    def run_workspace(self, context: PipelineContext, workspace: Path,
                      staged_assets: list[MediaAsset]) -> None:
        context.log(
            f"Prepared RAW workspace {workspace} with {len(staged_assets)} assets"
        )
        if staged_assets:
            context.create_prompt(
                "raw_conversion",
                {
                    "workspace": str(workspace),
                    "asset_count": len(staged_assets),
                },
                self.stage_id,
            )
