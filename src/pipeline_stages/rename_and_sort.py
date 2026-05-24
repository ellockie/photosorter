from src.core import \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineStage


class RenameAndSortStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="rename-and-sort",
            display_name="Rename and Sort",
            dependencies=("timezone-and-travel",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        resolver = NameCollisionResolver.from_context(context)
        renamed = 0

        for asset in context.assets:
            target = asset.primary_path
            if not target.exists():
                continue
            if target.exists() and target != asset.primary_path:
                resolver.resolve(target, asset.primary_path, context, self.stage_id)
            renamed += 1

        context.counters["rename_candidates"] = renamed
        context.log(f"Prepared {renamed} assets for rename/sort handling")
        return context
