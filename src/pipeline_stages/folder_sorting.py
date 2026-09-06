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
    rewrite_sidecar_path_fields, \
    sidecar_candidates
from src.pipeline_stages.siblings import \
    SUBSECOND_METADATA_KEY, \
    are_siblings, \
    occupant_names, \
    sibling_name, \
    subsecond_of_sidecar
from src.pipeline_stages.taxonomy import \
    DIFFERING_SUFFIX, \
    DUPLICATE_SUFFIX, \
    LOW_RES_SUFFIX, \
    split_collision_suffix, \
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


def _unique_target(folder: Path, file_name: str, source: Path,
                   winner: Path | None = None) -> Path:
    """A free name for ``source`` in ``folder``, marked for why it is not the wanted one.

    ``_DUPE`` only where the bytes match the file that keeps the name;
    otherwise ``_DIFFERS``, which is what F4 calls a loser that is not a copy.
    The distinction is the point: a checksum on a file called a duplicate is a
    claim about the *other* file, and it is only true when the two match.

    ``winner`` names that other file where it is not simply whatever holds
    ``file_name`` right now — which is the case when the loser being renamed is
    itself the file sitting there, and comparing it against the name it already
    holds would be comparing it with itself.
    """
    target = folder / file_name
    index = 1
    while target.exists():
        md5 = file_md5(source)
        rival_md5 = file_md5(winner if winner is not None else target)
        suffix = DUPLICATE_SUFFIX if rival_md5 == md5 else DIFFERING_SUFFIX
        target = folder / f"{Path(file_name).stem}{suffix}_{md5}_{index}{Path(file_name).suffix}"
        index += 1
    return target


def is_low_res(file_name: str) -> bool:
    """Does this name carry F4's ``_LOWRES``? (F10)

    Read through the taxonomy's own parser rather than by substring: the
    suffix is part of a grammar, and "_LOWRES" appearing anywhere in a
    description a person typed is not the same as a file that lost a collision.
    """
    parsed = split_collision_suffix(file_name)
    return parsed is not None and parsed.suffix == LOW_RES_SUFFIX


def _sidecar_subsecond(media_path: Path, config: dict) -> str | None:
    """The fraction recorded for a file already on disk, from its sidecar."""
    for sidecar in sidecar_candidates(media_path, config):
        if sidecar.exists():
            found = subsecond_of_sidecar(sidecar)
            if found:
                return found
    # A file already filed keeps its sidecar in the __EXIF beside it (X10),
    # not next to itself, so that is the second place to look.
    for sidecar in sidecar_candidates(
            sidecar_subdir(media_path.parent, config) / media_path.name, config):
        if sidecar.exists():
            found = subsecond_of_sidecar(sidecar)
            if found:
                return found
    return None


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


def _settle_existing_occupant(context: PipelineContext, folder: Path, file_name: str,
                              current_path: Path, asset=None) -> str:
    """Clear ``file_name`` in ``folder`` for ``current_path``, and say what it is called.

    Two files can want one name here for two unrelated reasons, and they are
    not settled the same way:

      * **two exposures inside one second** (F9) — no collision at all. Neither
        file is a loser: both are representatives, and each takes the fraction
        its own camera recorded, so the pair sorts in the order it was shot.
        The file already filed is renamed too, for the reason set out in
        ``rename_and_sort._settle_as_siblings``.
      * **anything else** — a stale leftover, or a genuine same-name collision.
        The occupant is flagged with its own hash rather than left standing
        unmarked, and its sidecars are dragged along so none is orphaned under
        a stale name (X5).
    """
    # The generated name carries the camera's sub-second (F9c); a shot filed
    # before it did is under the fraction-less form of the same name, and that
    # is the same collision. Looking only for the exact name would file a copy
    # of an already-archived photo a second time.
    existing = None
    for candidate in occupant_names(file_name):
        if (folder / candidate).exists():
            existing = folder / candidate
            break
    if existing is None or existing == current_path:
        return file_name

    sibling = _sibling_names(context, existing, current_path, asset)
    if sibling is not None:
        occupant_name, arrival_name = sibling
        if occupant_name == existing.name:
            return arrival_name         # only the arrival needs a new name
        demoted = folder / occupant_name
    else:
        # Built from the occupant's **own** name, which is not always the
        # arrival's: an older file is under the fraction-less form of it
        # (F9c), and naming the demotion off `file_name` would rename the
        # occupant onto the very name the arrival is about to take.
        #
        # The comparison is against `current_path` -- not against the name the
        # occupant already holds, which is the occupant itself.
        demoted = _unique_target(folder, existing.name, existing, winner=current_path)
        arrival_name = file_name
    old_name = existing.name
    safe_move(existing, demoted)
    for tracked in context.assets:
        if tracked.primary_path != existing:
            continue
        tracked.primary_path = demoted
        for name, sidecar_path in list(tracked.sidecars.items()):
            if not sidecar_path.exists():
                continue
            desired = renamed_sidecar_path(sidecar_path, old_name, demoted.name)
            sidecar_target = resolve_sidecar_target(sidecar_path, desired)
            if sidecar_target is None:
                safe_delete(sidecar_path)
                del tracked.sidecars[name]
                continue
            if sidecar_target != sidecar_path:
                safe_move(sidecar_path, sidecar_target)
                tracked.sidecars[name] = sidecar_target
        return arrival_name
    # The occupant belongs to no asset in this run — it was already in the
    # archive. Its sidecar is in the __EXIF beside it (X10) and still has to
    # follow the rename, or it is orphaned under a name nothing answers to.
    _move_untracked_sidecars(existing, demoted, context.config)
    return arrival_name


def _move_untracked_sidecars(old_path: Path, new_path: Path, config: dict) -> None:
    exif_folder = sidecar_subdir(old_path.parent, config)
    for holder in (old_path, exif_folder / old_path.name):
        for sidecar in sidecar_candidates(holder, config):
            if not sidecar.exists():
                continue
            desired = renamed_sidecar_path(sidecar, old_path.name, new_path.name)
            target = resolve_sidecar_target(sidecar, desired)
            if target is not None and target != sidecar:
                safe_move(sidecar, target)


def _sibling_names(context: PipelineContext, existing: Path, arriving: Path,
                   asset) -> tuple[str, str] | None:
    """``(occupant name, arrival name)`` if these are two exposures, else None (F9).

    None is every case F9a cannot vouch for, and the caller then settles the
    pair as F4 says. Nothing is renamed on a guess.
    """
    if file_md5(existing) == file_md5(arriving):
        return None                    # a real duplicate; F4 owns it
    config = context.config
    arriving_subsecond = (asset.metadata.get(SUBSECOND_METADATA_KEY)
                          if asset is not None else None)
    if not arriving_subsecond:
        arriving_subsecond = _sidecar_subsecond(arriving, config)
    existing_subsecond = _sidecar_subsecond(existing, config)
    if not are_siblings(existing_subsecond, arriving_subsecond):
        return None
    return (sibling_name(existing.name, existing_subsecond),
            sibling_name(existing.name, arriving_subsecond))


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
            elif is_low_res(asset.primary_path.name):
                # A proven downscale is a derivative, not a representative, so
                # it goes in __RESIZED rather than beside the shot it is a
                # smaller copy of (F7/F10). It takes no representative suffix
                # for the same reason a RAW does not: those describe a
                # representative's relationship to its own subfolders.
                primary_folder = taxonomy_subdir(event_folder, config, "resized")
                primary_name = asset.primary_path.name
            else:
                primary_folder = event_folder
                primary_name = apply_representative_suffixes(
                    asset.primary_path.name,
                    has_raw=shot_key in raw_shot_keys,
                )

            primary_folder.mkdir(parents=True, exist_ok=True)
            old_primary_name = asset.primary_path.name
            primary_name = _settle_existing_occupant(
                context, primary_folder, primary_name, asset.primary_path, asset)
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
