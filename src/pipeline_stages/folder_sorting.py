import datetime
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    file_md5, \
    safe_delete, \
    safe_move
from src.pipeline_stages.legacy import \
    final_event_folder, \
    is_raw_extension
from src.pipeline_stages.geolocation import \
    location_info, \
    write_location_stamp
from src.pipeline_stages.provenance import \
    renamed_sidecar_path, \
    resolve_sidecar_target, \
    rewrite_sidecar_path_fields
from src.pipeline_stages.taxonomy import \
    apply_representative_suffixes, \
    taxonomy_subdir


def _captured_at(asset) -> datetime.datetime | None:
    captured_at = asset.metadata.get("captured_at_corrected") or asset.metadata.get("captured_at")
    if isinstance(captured_at, str):
        captured_at = datetime.datetime.fromisoformat(captured_at)
    return captured_at


def _shot_key(asset) -> tuple | None:
    image_datetime = asset.metadata.get("image_datetime")
    if not image_datetime:
        return None
    return (image_datetime, asset.metadata.get("camera_symbol"))


def _unique_target(folder: Path, file_name: str, source: Path) -> Path:
    target = folder / file_name
    index = 1
    while target.exists():
        md5 = file_md5(source)
        target = folder / f"{Path(file_name).stem}_DUPE_{md5}_{index}{Path(file_name).suffix}"
        index += 1
    return target


class FolderSortingStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="folder-sorting",
            display_name="Folder Sorting",
            dependencies=("move-results",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        config = context.config
        video_extensions = {
            value.lower()
            for value in config.get("extensions", {}).get("videos", [])
        }
        # Shots where a camera image exists alongside a RAW original get the
        # _RAW representative suffix; RAW-only shots promote an extracted JPEG.
        raw_shot_keys = {
            _shot_key(asset)
            for asset in context.assets
            if asset.primary_path.exists() and is_raw_extension(asset.primary_path.suffix, config)
        }
        raw_shot_keys.discard(None)
        camera_image_shot_keys = {
            _shot_key(asset)
            for asset in context.assets
            if asset.primary_path.exists()
            and not is_raw_extension(asset.primary_path.suffix, config)
            and asset.primary_path.suffix.lower() not in video_extensions
        }
        camera_image_shot_keys.discard(None)

        moved = 0
        undated = 0
        sorted_by_label: dict[str, list] = {}
        located_folders: dict[Path, dict] = {}

        for asset in context.assets:
            if not asset.primary_path.exists():
                continue
            captured_at = _captured_at(asset)
            # An explicit origin folder wins; otherwise a trip location names
            # the event folder (e.g. "2026-04-12_(Sun) - Japan").
            label = asset.metadata.get("origin_label") or asset.metadata.get("location_suffix")
            if captured_at is None:
                undated += 1
                event_folder = Path(config["paths"]["ready_folder"])
            else:
                event_folder = final_event_folder(captured_at, config, label)

            is_raw = is_raw_extension(asset.primary_path.suffix, config)
            is_video = asset.primary_path.suffix.lower() in video_extensions
            shot_key = _shot_key(asset)

            if is_raw:
                primary_folder = taxonomy_subdir(event_folder, config, "raw")
                primary_name = asset.primary_path.name
            elif is_video:
                primary_folder = taxonomy_subdir(event_folder, config, "videos")
                primary_name = asset.primary_path.name
            else:
                primary_folder = event_folder
                primary_name = apply_representative_suffixes(
                    asset.primary_path.name,
                    has_raw=shot_key in raw_shot_keys,
                )

            primary_folder.mkdir(parents=True, exist_ok=True)
            old_primary_name = asset.primary_path.name
            primary_target = _unique_target(primary_folder, primary_name, asset.primary_path)
            safe_move(asset.primary_path, primary_target)
            asset.primary_path = primary_target

            for name, sidecar_path in list(asset.sidecars.items()):
                if not sidecar_path.exists():
                    continue
                if name == "converted_jpg" and is_raw:
                    # Extracted image from RAW: promote to representative when
                    # the shot has no straight-from-camera image, otherwise
                    # keep it as an alternate under __EXTRACTED.
                    if shot_key is not None and shot_key not in camera_image_shot_keys:
                        extracted_folder = event_folder
                        extracted_name = apply_representative_suffixes(
                            sidecar_path.name, has_raw=True, extracted_from_raw=True)
                    else:
                        extracted_folder = taxonomy_subdir(event_folder, config, "extracted")
                        extracted_name = sidecar_path.name
                    extracted_folder.mkdir(parents=True, exist_ok=True)
                    sidecar_target = _unique_target(extracted_folder, extracted_name, sidecar_path)
                else:
                    exif_folder = taxonomy_subdir(event_folder, config, "exif")
                    exif_folder.mkdir(parents=True, exist_ok=True)
                    sidecar_name = renamed_sidecar_path(
                        sidecar_path, old_primary_name, primary_target.name).name
                    sidecar_target = resolve_sidecar_target(
                        sidecar_path, exif_folder / sidecar_name)
                    if sidecar_target is None:
                        # An identical sidecar already sits in __EXIF (e.g. a
                        # re-run): drop the redundant copy instead of orphaning it.
                        safe_delete(sidecar_path)
                        del asset.sidecars[name]
                        continue
                safe_move(sidecar_path, sidecar_target)
                asset.sidecars[name] = sidecar_target
                # Correct File Name / Directory now that the image has reached
                # its final name and location (the metadata pass ran pre-rename).
                if sidecar_target.name.endswith("._exif"):
                    rewrite_sidecar_path_fields(
                        sidecar_target, primary_target.name, str(primary_target.parent))

            if label:
                sorted_by_label.setdefault(label, []).append((captured_at, event_folder))
            info = location_info(asset.metadata)
            if info and captured_at is not None:
                located_folders[event_folder] = info
            moved += 1

        for event_folder, info in located_folders.items():
            write_location_stamp(event_folder, config, info)

        self._route_geodata(context, sorted_by_label)

        context.counters["sorted_assets"] = moved
        context.set_stage_stats(self.stage_id, inputs=moved, outputs=moved, errors=undated)
        context.log(f"Sorted {moved} assets into event folders")
        if undated:
            context.log(f"Routed {undated} assets without a capture date to READY")
        return context

    def _route_geodata(self, context: PipelineContext, sorted_by_label: dict[str, list]) -> None:
        inbox = Path(context.config["paths"]["unsorted_folder"])
        for record in context.geodata:
            label = record.get("origin_label")
            file_name = record.get("file_name")
            if not file_name:
                continue
            source = inbox / file_name
            if not source.exists():
                continue
            destinations = sorted_by_label.get(label)
            if not destinations:
                context.log(f"Geodata left in inbox, no sorted assets for label {label!r}: {file_name}")
                continue
            _, event_folder = min(
                destinations,
                key=lambda item: item[0] or datetime.datetime.max,
            )
            geo_folder = taxonomy_subdir(event_folder, context.config, "geolocations")
            geo_folder.mkdir(parents=True, exist_ok=True)
            target = resolve_sidecar_target(source, geo_folder / file_name)
            if target is None:
                safe_delete(source)
                continue
            safe_move(source, target)
            context.counters["geodata_routed"] += 1
