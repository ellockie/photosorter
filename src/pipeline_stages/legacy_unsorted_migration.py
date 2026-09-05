from pathlib import Path

from src.core import \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.pipeline_stages.provenance import \
    dont_move_folder


class LegacyUnsortedMigrationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="legacy-unsorted-migration",
            display_name="Legacy Unsorted Migration",
            dependencies=("initialization",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        legacy = Path(context.config["paths"]["legacy_unsorted_folder"])
        inbox = Path(context.config["paths"]["inbox_folder"])
        if not legacy.exists() or legacy.resolve() == inbox.resolve():
            context.log("Legacy unsorted migration skipped")
            return context

        inbox.mkdir(parents=True, exist_ok=True)
        excluded = dont_move_folder(context.config)
        moved = 0
        for path in legacy.iterdir():
            if path.is_dir():
                # Whole folders migrate as-is (except __DONT_MOVE); the
                # folder-intake stage flattens them and records origin labels.
                if path.name == excluded:
                    continue
                folder_target = inbox / path.name
                index = 1
                while folder_target.exists():
                    folder_target = inbox / f"{path.name}_{index}"
                    index += 1
                safe_move(path, folder_target)
                moved += 1
                continue
            target = inbox / path.name
            if target.exists():
                result = NameCollisionResolver.from_context(context).resolve(
                    target,
                    path,
                    context,
                    self.stage_id,
                )
                if result.target_path:
                    target = result.target_path
                elif result.prompt:
                    context.log("Legacy migration paused for collision prompt")
                    break
            safe_move(path, target)
            moved += 1

        context.counters["legacy_unsorted_migrated"] += moved
        context.log(f"Migrated {moved} files from legacy unsorted folder")
        return context
