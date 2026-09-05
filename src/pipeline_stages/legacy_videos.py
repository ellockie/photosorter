"""Drain the legacy ``__VIDEOS`` container into the current video layout.

Datable videos are representatives and move one level up beside the images
(V1). An unkeyed name is checked against intrinsic ExifTool metadata only;
filesystem dates never qualify (V4). A still-undatable video is tagged and
moved into ``__VIDEOS_TO_RENAME`` with its sidecars and previews (V8/V8c).

This module owns the migration mechanics while the restructure front door
supplies ExifTool, archive-safe moves, checksums, dry-run behaviour and logs.
"""

import os
import stat
from dataclasses import dataclass
from pathlib import Path

from src.pipeline_stages.grouping_names import \
    extension_sets, \
    preview_extensions, \
    sidecar_extensions
from src.pipeline_stages.legacy import \
    intrinsic_capture_datetime_from_exif_text, \
    legacy_filename, \
    parse_legacy_exif_text
from src.pipeline_stages.parking import \
    free_versioned_name, \
    parking_area_for
from src.pipeline_stages.stamps import \
    format_stamp, \
    leading_stamp_key
from src.pipeline_stages.taxonomy import \
    LEGACY_TAXONOMY, \
    differing_name, \
    duplicate_name, \
    sidecar_subdir, \
    taxonomy_subdir
from src.utils.checksums import file_md5


TO_RENAME_PREFIX = "__TO_RENAME__"


# The one implementation, under this module's own name (T8). A caller with a
# config in hand passes its own chunked checksum in instead.
_default_checksum = file_md5


@dataclass
class VideoMigrationReport:
    folders: int = 0
    moved_up: int = 0
    named_from_metadata: int = 0
    unresolved: int = 0
    companions_moved: int = 0
    sidecars_created: int = 0
    parked_duplicate: int = 0
    parked_differing: int = 0
    empty_folders_parked: int = 0
    left: int = 0
    errors: int = 0
    blocked_folders: set = None
    drainable_folders: set = None

    def __post_init__(self):
        self.blocked_folders = (set() if self.blocked_folders is None
                                else self.blocked_folders)
        self.drainable_folders = (set() if self.drainable_folders is None
                                  else self.drainable_folders)

    @property
    def seen(self):
        return self.folders

    @property
    def needs_attention(self):
        return bool(self.unresolved or self.left or self.errors)

    def summary(self):
        return (f"{self.folders} folder(s), {self.moved_up} video(s) moved up, "
                f"{self.named_from_metadata} named from metadata, "
                f"{self.unresolved} awaiting a name, "
                f"{self.companions_moved} companion(s) carried, "
                f"{self.empty_folders_parked} empty folder(s) parked, "
                f"{self.left} left, {self.errors} error(s)")


def legacy_video_folders(dated_folders, config: dict):
    """Find immediate ``__VIDEOS`` children, accepting historical case."""
    wanted = LEGACY_TAXONOMY["videos"].casefold()
    found = []
    for dated in dated_folders:
        try:
            children = list(Path(dated).iterdir())
        except OSError:
            continue
        for child in children:
            if child.name.casefold() != wanted:
                continue
            try:
                status = os.lstat(child)
            except OSError:
                continue
            # Include a matching reparse point so the migration can refuse it
            # explicitly and report an error, without following it here (T4).
            if (stat.S_ISDIR(status.st_mode)
                    or getattr(status, "st_reparse_tag", 0)
                    or os.path.islink(child)):
                found.append(child)
    return sorted(set(found), key=lambda path: str(path).casefold())


def _files_below(folder: Path):
    found = []
    for directory, _subdirs, names in os.walk(folder):
        found.extend(Path(directory) / name for name in sorted(names))
    return found


def _first_reparse_below(folder: Path):
    """A reparse point at or below ``folder``, without traversing into one."""
    try:
        status = os.lstat(folder)
    except OSError:
        return folder
    if getattr(status, "st_reparse_tag", 0) or os.path.islink(folder):
        return folder
    for directory, subdirs, names in os.walk(folder, topdown=True):
        safe_subdirs = []
        for name in subdirs:
            child = Path(directory) / name
            try:
                status = os.lstat(child)
            except OSError:
                return child
            if getattr(status, "st_reparse_tag", 0) or os.path.islink(child):
                return child
            safe_subdirs.append(name)
        subdirs[:] = safe_subdirs
        for name in names:
            child = Path(directory) / name
            try:
                status = os.lstat(child)
            except OSError:
                return child
            if getattr(status, "st_reparse_tag", 0) or os.path.islink(child):
                return child
    return None


def _companions_for(video: Path, files, videos, config: dict):
    kinds = (("exif", sidecar_extensions(config)),
             ("previews", preview_extensions(config)))
    same_stem = [candidate for candidate in videos
                 if candidate.stem.casefold() == video.stem.casefold()]
    answers = []
    for candidate in files:
        lower = candidate.name.casefold()
        for key, extensions in kinds:
            extension = next((ext for ext in extensions
                              if lower.endswith(ext.casefold())), None)
            if extension is None:
                continue
            subject = candidate.name[:-len(extension)]
            exact = subject.casefold() == video.name.casefold()
            historical = (subject.casefold() == video.stem.casefold()
                          and len(same_stem) == 1)
            if exact or historical:
                answers.append((candidate, key, extension.lower()))
            break
    return answers


def _same_path(left: Path, right: Path):
    return (os.path.normcase(os.path.abspath(left))
            == os.path.normcase(os.path.abspath(right)))


def _plain_directory(path: Path):
    """True only for an ordinary directory, without following a reparse point."""
    try:
        status = os.lstat(path)
    except OSError:
        return False
    return (stat.S_ISDIR(status.st_mode)
            and not getattr(status, "st_reparse_tag", 0)
            and not os.path.islink(path))


def _plain_file(path: Path):
    """True only for an ordinary file, without following a reparse point."""
    try:
        status = os.lstat(path)
    except OSError:
        return False
    return (stat.S_ISREG(status.st_mode)
            and not getattr(status, "st_reparse_tag", 0)
            and not os.path.islink(path))


def _collision_target(source: Path, target: Path, parking: Path,
                      checksum, reserved, report: VideoMigrationReport):
    key = str(target).casefold()
    if not target.exists() and key not in reserved:
        reserved.add(key)
        return target
    try:
        digest = checksum(source)
        same = target.exists() and digest == checksum(target)
    except OSError:
        report.errors += 1
        return None
    stem, extension = os.path.splitext(target.name)
    namer = duplicate_name if same else differing_name
    index = 1
    while True:
        candidate = parking / namer(stem, digest[:8], index, extension)
        if not candidate.exists() and str(candidate).casefold() not in reserved:
            reserved.add(str(candidate).casefold())
            if same:
                report.parked_duplicate += 1
            else:
                report.parked_differing += 1
            return candidate
        index += 1


def migrate_legacy_videos(folders, config: dict, duplicates_for,
                          inspect_metadata, log=lambda _message: None,
                          move=None, checksum=None, write_sidecar=None):
    """Move videos out of each legacy folder without guessing a timestamp."""
    report = VideoMigrationReport(folders=len(folders))
    image_exts, video_exts = extension_sets(config)
    media_exts = image_exts | video_exts
    move = (lambda source, target: os.rename(source, target)) if move is None else move
    checksum = _default_checksum if checksum is None else checksum
    reserved = set()

    for folder in folders:
        folder = Path(folder)
        folder_key = os.path.normcase(os.path.abspath(folder))
        refused = _first_reparse_below(folder)
        if refused is not None:
            report.errors += 1
            report.left += 1
            report.blocked_folders.add(folder_key)
            log(f"! left {folder}: reparse point not followed: {refused} (T4)")
            continue
        files = _files_below(folder)
        videos = [path for path in files if path.suffix.lower() in video_exts]
        # Historical runs commonly put a video's companions in the dated
        # folder's sibling __EXIF/__PREVIEWS even while keeping the video in
        # __VIDEOS. Include those two canonical locations in the pairing scope.
        scope_files = list(files)
        for key in ("exif", "previews"):
            sibling = sidecar_subdir(folder.parent, config, key)
            if not _plain_directory(sibling):
                continue
            refused = _first_reparse_below(sibling)
            if refused is not None:
                log(f"! did not search {sibling}: reparse point not followed: "
                    f"{refused} (T4)")
                continue
            scope_files.extend(_files_below(sibling))
        try:
            top_level_media = [
                path for path in folder.parent.iterdir()
                if _plain_file(path) and path.suffix.lower() in media_exts
            ]
        except OSError:
            top_level_media = []
        media_scope = videos + top_level_media
        handled = set()
        for video in videos:
            companions = _companions_for(video, scope_files, media_scope, config)
            destination_folder = folder.parent
            destination_name = video.name
            metadata_text = None
            captured = None

            if leading_stamp_key(video.name) is None:
                exif_candidates = [path for path, key, _ext in companions
                                   if key == "exif"]
                if len(exif_candidates) == 1:
                    try:
                        metadata_text = exif_candidates[0].read_text(
                            encoding="iso-8859-1")
                    except OSError as error:
                        log(f"! could not read {exif_candidates[0]}: {error}")
                if metadata_text:
                    captured = intrinsic_capture_datetime_from_exif_text(metadata_text)
                if captured is None:
                    try:
                        metadata_text = inspect_metadata(video)
                    except Exception as error:
                        log(f"! could not inspect {video}: {error}")
                        report.errors += 1
                        report.left += 1
                        # Failure to read metadata is not evidence that no
                        # timestamp exists. Leave the video untouched rather
                        # than misclassifying it as intrinsically undatable.
                        continue
                    if metadata_text:
                        captured = intrinsic_capture_datetime_from_exif_text(metadata_text)

                if captured is not None:
                    metadata = parse_legacy_exif_text(metadata_text, config)
                    metadata["captured_at"] = captured
                    metadata["image_datetime"] = format_stamp(captured)
                    destination_name = legacy_filename(metadata, video.suffix, config)
                    report.named_from_metadata += 1
                else:
                    destination_folder = taxonomy_subdir(
                        folder.parent, config, "videos_to_rename")
                    if not video.name.startswith(TO_RENAME_PREFIX):
                        destination_name = TO_RENAME_PREFIX + video.name
                    report.unresolved += 1
                    log(f"! {video} has no intrinsic capture time; tagged and moved "
                        "to the video-review folder (V8)")

            destination = destination_folder / destination_name
            target = _collision_target(
                video, destination, Path(duplicates_for(folder.parent)),
                checksum, reserved, report)
            if target is None:
                report.left += 1
                continue
            try:
                move(video, target)
            except Exception as error:
                log(f"! could not move {video} to {target}: {error}")
                report.errors += 1
                report.left += 1
                continue
            if destination_folder == folder.parent:
                report.moved_up += 1
            handled.add(video)
            log(f"* {video} -> {target}")

            # Carry companions in the same migration even when the video's
            # name is unchanged. Besides satisfying X5, this lets the emptied
            # legacy container be parked before generic pruning can erase it.
            for companion, key, extension in companions:
                companion_target = (sidecar_subdir(target.parent, config, key)
                                    / (target.name + extension))
                if _same_path(companion, companion_target):
                    continue
                companion_target = _collision_target(
                    companion, companion_target,
                    Path(duplicates_for(folder.parent)), checksum,
                    reserved, report)
                if companion_target is None:
                    report.left += 1
                    continue
                try:
                    move(companion, companion_target)
                except Exception as error:
                    log(f"! could not carry {companion}: {error}")
                    report.errors += 1
                    report.left += 1
                    continue
                report.companions_moved += 1
                handled.add(companion)

            has_exif = any(key == "exif" for _path, key, _ext in companions)
            if metadata_text and not has_exif and write_sidecar is not None:
                sidecar_target = (sidecar_subdir(target.parent, config, "exif")
                                  / (target.name + "._exif"))
                try:
                    write_sidecar(sidecar_target, metadata_text, video)
                except Exception as error:
                    log(f"! could not write {sidecar_target}: {error}")
                    report.errors += 1
                else:
                    report.sidecars_created += 1

        if set(files) <= handled:
            report.drainable_folders.add(folder_key)

    return report


def park_empty_legacy_video_folders(folders, report: VideoMigrationReport,
                                    log=lambda _message: None, move=None,
                                    dry_run=False):
    """Park a drained ``__VIDEOS`` only after verifying no file remains."""
    move = (lambda source, target: os.rename(source, target)) if move is None else move
    reserved = set()
    for folder in folders:
        folder = Path(folder)
        folder_key = os.path.normcase(os.path.abspath(folder))
        if folder_key in report.blocked_folders:
            continue
        if not folder.is_dir():
            continue
        refused = _first_reparse_below(folder)
        if refused is not None:
            report.errors += 1
            report.left += 1
            log(f"! left {folder}: reparse point not followed: {refused} (T4)")
            continue
        remaining = _files_below(folder)
        if not dry_run and remaining:
            report.left += 1
            log(f"- left {folder}: files remain after video migration")
            continue
        if dry_run and folder_key not in report.drainable_folders:
            report.left += 1
            log(f"- left {folder}: files would remain after video migration")
            continue
        parking = parking_area_for(folder)
        if parking is None:
            report.errors += 1
            report.left += 1
            log(f"! could not park empty {folder}: no month folder above it")
            continue
        target = free_versioned_name(parking, folder.name, reserved)
        try:
            move(folder, target)
        except Exception as error:
            report.errors += 1
            report.left += 1
            log(f"! could not park empty {folder}: {error}")
            continue
        report.empty_folders_parked += 1
        log(f"* parked empty {folder} as {target}")
