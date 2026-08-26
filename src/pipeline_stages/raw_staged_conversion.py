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
        if not staged_assets:
            return
        prompt = context.create_prompt(
            "raw_conversion",
            {
                "workspace": str(workspace),
                "asset_count": len(staged_assets),
                "instructions": (
                    "Convert the RAWs in this workspace, then press Done — "
                    "the folder is swept as soon as you do."
                ),
            },
            self.stage_id,
        )
        # Blocking here is the whole point. StagedWorkspaceStage.execute deletes
        # the workspace in its finally-block, so without a wait the folder the
        # prompt is pointing at is gone before the user can even read the path.
        context.await_prompt(prompt, auto_answer={"done": True})
