from pathlib import Path

from src.core import \
    CollisionDecision, \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineStage, \
    file_md5, \
    safe_delete, \
    safe_rename
from src.pipeline_stages.legacy import \
    legacy_filename
from src.pipeline_stages.provenance import \
    renamed_sidecar_path, \
    resolve_sidecar_target


def unique_duplicate_path(path: Path, suffix: str, md5: str) -> Path:
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}{suffix}_{md5}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


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
        skipped = 0

        for asset in context.assets:
            source_path = asset.primary_path
            if not source_path.exists():
                skipped += 1
                continue
            if "image_datetime" not in asset.metadata:
                context.log(f"Rename skipped, EXIF metadata missing: {source_path.name}")
                skipped += 1
                continue
            new_name = legacy_filename(asset.metadata, source_path.suffix, context.config)
            target_path = source_path.with_name(new_name)
            if target_path.exists() and target_path != source_path:
                result = resolver.resolve(target_path, source_path, context, self.stage_id)
                if result.decision == CollisionDecision.DISCARD_DUPLICATE:
                    # The image is a redundant duplicate: drop it AND its
                    # sidecars so they cannot be orphaned into __EXIF later.
                    for sidecar_path in list(asset.sidecars.values()):
                        if sidecar_path.exists():
                            safe_delete(sidecar_path)
                    safe_delete(source_path)
                    skipped += 1
                    continue
                if result.decision == CollisionDecision.PROMPT:
                    context.log(f"Rename paused for collision prompt: {source_path.name}")
                    skipped += 1
                    continue
                duplicate_suffix = (
                    resolver.low_res_suffix
                    if result.reason == "significantly-smaller"
                    else resolver.duplicate_suffix
                )
                if result.decision == CollisionDecision.KEEP_CANDIDATE:
                    # The incoming file wins the base name; the existing target
                    # is renamed away using the legacy _DUPE_<md5>_<n> grammar.
                    existing_md5 = file_md5(target_path)
                    safe_rename(
                        target_path,
                        target_path.with_name(
                            f"{target_path.stem}{duplicate_suffix}_{existing_md5}_0{target_path.suffix}"
                        ),
                    )
                else:
                    source_md5 = file_md5(source_path)
                    target_path = unique_duplicate_path(target_path, duplicate_suffix, source_md5)

            old_primary_name = source_path.name
            if target_path != source_path:
                safe_rename(source_path, target_path)
                asset.primary_path = target_path

            for name, sidecar_path in list(asset.sidecars.items()):
                if not sidecar_path.exists():
                    continue
                desired = renamed_sidecar_path(sidecar_path, old_primary_name, target_path.name)
                sidecar_target = resolve_sidecar_target(sidecar_path, desired)
                if sidecar_target is None:
                    safe_delete(sidecar_path)
                    del asset.sidecars[name]
                    continue
                if sidecar_target != sidecar_path:
                    safe_rename(sidecar_path, sidecar_target)
                    asset.sidecars[name] = sidecar_target
            renamed += 1

        context.counters["renamed_assets"] = renamed
        context.counters["rename_skipped_assets"] = skipped
        context.log(f"Renamed {renamed} media assets and EXIF sidecars")
        return context
