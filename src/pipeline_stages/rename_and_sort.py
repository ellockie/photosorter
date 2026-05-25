from src.core import \
    PipelineContext, \
    PipelineStage, \
    file_md5, \
    safe_delete, \
    safe_rename
from src.pipeline_stages.legacy import \
    legacy_filename


class RenameAndSortStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="rename-and-sort",
            display_name="Rename and Sort",
            dependencies=("timezone-and-travel",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
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
                source_md5 = file_md5(source_path)
                existing_md5 = file_md5(target_path)
                if source_md5 == existing_md5:
                    safe_delete(source_path)
                    context.register_safety_exception(source_md5, "Exact duplicate renamed image")
                    skipped += 1
                    continue
                target_path = source_path.with_name(
                    f"{target_path.stem}_DUPE_{source_md5}_1{target_path.suffix}"
                )

            if target_path != source_path:
                safe_rename(source_path, target_path)
                asset.primary_path = target_path

            for name, sidecar_path in list(asset.sidecars.items()):
                if not sidecar_path.exists():
                    continue
                sidecar_target = target_path.with_name(target_path.stem + sidecar_path.suffix)
                if sidecar_target.exists() and sidecar_target != sidecar_path:
                    sidecar_target = target_path.with_name(
                        f"{target_path.stem}_DUPE_EXIF{sidecar_path.suffix}"
                    )
                if sidecar_target != sidecar_path:
                    safe_rename(sidecar_path, sidecar_target)
                    asset.sidecars[name] = sidecar_target
            renamed += 1

        context.counters["renamed_assets"] = renamed
        context.counters["rename_skipped_assets"] = skipped
        context.log(f"Renamed {renamed} media assets and EXIF sidecars")
        return context
