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
    sidecar_subdir, \
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


def _place_extracted_sidecar(asset, sidecar: Path | None, subject: Path, config: dict) -> None:
    """Move an extracted JPEG's own ``._exif`` to sit beside it (X10, X4).

    The extracted image is a media file like any other, so it gets a sidecar of
    its own rather than borrowing the RAW's — a sidecar describes exactly one
    file, and the RAW's carries the RAW's dimensions and type. Without this a
    RAW-only shot leaves a bare representative at the top level and trips the
    ``e`` audit marker on every such folder.
    """
    if sidecar is None or not sidecar.exists():
        return
    exif_folder = sidecar_subdir(subject.parent, config)
    exif_folder.mkdir(parents=True, exist_ok=True)
    target = exif_folder / f"{subject.name}._exif"
    if target.exists():
        safe_delete(sidecar)
        return
    safe_move(sidecar, target)
    asset.sidecars["converted_jpg_exif"] = target
    rewrite_sidecar_path_fields(target, subject.name, str(subject.parent))


def _demote_existing_occupant(context: PipelineContext, folder: Path, file_name: str, current_path: Path) -> None:
    # A different file already sits at the destination name (a stale leftover
    # or a genuine same-name collision). Flag it as a duplicate using its own
    # hash instead of silently leaving it there unmarked, and drag its
    # sidecars along so they don't end up orphaned under a stale name.
    existing = folder / file_name
    if not existing.exists() or existing == current_path:
        return
    demoted = _unique_target(folder, file_name, existing)
    old_name = existing.name
    safe_move(existing, demoted)
    for asset in context.assets:
        if asset.primary_path != existing:
            continue
        asset.primary_path = demoted
        for name, sidecar_path in list(asset.sidecars.items()):
            if not sidecar_path.exists():
                continue
            desired = renamed_sidecar_path(sidecar_path, old_name, demoted.name)
            sidecar_target = resolve_sidecar_target(sidecar_path, desired)
            if sidecar_target is None:
                safe_delete(sidecar_path)
                del asset.sidecars[name]
                continue
            if sidecar_target != sidecar_path:
                safe_move(sidecar_path, sidecar_target)
                asset.sidecars[name] = sidecar_target
        break


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
        # RAW-only shots: a RAW arrived with no straight-from-camera JPEG, so an
        # extraction stands in as the representative. Counted and reported —
        # it is the mode where the archive holds no picture the camera itself
        # produced, and that is worth knowing without auditing the tree.
        raw_only_promoted = 0
        raw_only_unconverted = sorted(
            key for key in raw_shot_keys if key not in camera_image_shot_keys
        )
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
                context.affected_event_folders.add(event_folder)

            is_raw = is_raw_extension(asset.primary_path.suffix, config)
            is_video = asset.primary_path.suffix.lower() in video_extensions
            shot_key = _shot_key(asset)

            if is_raw:
                primary_folder = taxonomy_subdir(event_folder, config, "raw")
                primary_name = asset.primary_path.name
            elif is_video:
                # A video that reached this point carries a capture time, so it
                # is a representative and sits at the top level beside the
                # stills (ARCHIVE_STANDARD.md V1). It takes no representative
                # suffix: _RAW/_EXT/_EDT describe a still's relationship to its
                # own subfolders, and a video has none of those.
                primary_folder = event_folder
                primary_name = asset.primary_path.name
            else:
                primary_folder = event_folder
                primary_name = apply_representative_suffixes(
                    asset.primary_path.name,
                    has_raw=shot_key in raw_shot_keys,
                )

            primary_folder.mkdir(parents=True, exist_ok=True)
            old_primary_name = asset.primary_path.name
            _demote_existing_occupant(context, primary_folder, primary_name, asset.primary_path)
            primary_target = _unique_target(primary_folder, primary_name, asset.primary_path)
            safe_move(asset.primary_path, primary_target)
            asset.primary_path = primary_target

            # Handled with the extracted JPEG itself: it is named after that
            # file, not after this asset's RAW primary, so the generic renaming
            # below would give it the wrong name.
            extracted_exif = asset.sidecars.pop("converted_jpg_exif", None)

            for name, sidecar_path in list(asset.sidecars.items()):
                if not sidecar_path.exists():
                    continue
                if name == "converted_jpg" and is_raw:
                    # Extracted image from RAW: promote to representative when
                    # the shot has no straight-from-camera image, otherwise keep
                    # it as an alternate under __RAW_EXTRACTED_JPGS.
                    if shot_key is not None and shot_key not in camera_image_shot_keys:
                        extracted_folder = event_folder
                        extracted_name = apply_representative_suffixes(
                            sidecar_path.name, extracted_from_raw=True)
                        raw_only_promoted += 1
                    else:
                        extracted_folder = taxonomy_subdir(
                            event_folder, config, "raw_extracted_jpgs")
                        extracted_name = sidecar_path.name
                    extracted_folder.mkdir(parents=True, exist_ok=True)
                    sidecar_target = _unique_target(extracted_folder, extracted_name, sidecar_path)
                    safe_move(sidecar_path, sidecar_target)
                    asset.sidecars[name] = sidecar_target
                    _place_extracted_sidecar(
                        asset, extracted_exif, sidecar_target, config)
                    continue
                else:
                    # X10: the sidecar goes in the __EXIF of the folder holding
                    # its subject, not the event folder's. A still or video at
                    # the top level therefore lands in the event folder's own
                    # __EXIF; a RAW that was routed into __RAW lands in
                    # __RAW\__EXIF, so moving __RAW carries its sidecars along.
                    exif_folder = sidecar_subdir(primary_target.parent, config)
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
        context.counters["raw_only_shots"] = len(raw_only_unconverted)
        context.counters["raw_only_promoted"] = raw_only_promoted
        context.set_stage_stats(self.stage_id, inputs=moved, outputs=moved, errors=undated)
        context.log(f"Sorted {moved} assets into event folders")
        if undated:
            context.log(f"Routed {undated} assets without a capture date to READY")
        if raw_only_unconverted:
            # Every RAW-only shot is named, not just counted: a shot with no
            # extraction has no representative at all, so the folder shows a
            # RAW and nothing to look at.
            context.log(
                f"{len(raw_only_unconverted)} RAW-only shot(s) (no straight-from-camera JPEG); "
                f"{raw_only_promoted} had an extraction promoted to representative"
            )
            missing = len(raw_only_unconverted) - raw_only_promoted
            if missing > 0:
                context.log(
                    f"  {missing} of them have no extracted JPEG — no representative image"
                )
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
