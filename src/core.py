import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from src.utils.checksums import file_md5  # noqa: F401  (re-export)
from src.utils.dimensions import is_downscaled
from src.utils.progress import \
    StageProgress, \
    format_bytes, \
    format_count, \
    format_duration
from src.utils.stage_banner import \
    announce_to_console, \
    format_end, \
    format_start


CONFIG_FILE_NAME = "config.json"
# The travel/clock data is hand-edited and conceptually separate from the app
# config, so it lives in its own sibling file (Decision 9). The loader overlays
# it onto the config dict so the rest of the code keeps reading config["..."].
TIMEZONE_FILE_NAME = "timezone.json"
TIMEZONE_KEYS = ("zones", "locations", "camera_clock_sets")
DEFAULT_COLLISION_THRESHOLD = 0.5
DEFAULT_DASHBOARD_PORT = 8888
DEFAULT_RETRY_ATTEMPTS = 5
DEFAULT_RETRY_DELAY_SECONDS = 0.2
# How often a stage blocked on a prompt re-checks for an abort. NOT a timeout:
# the wait itself is unbounded (see PipelineContext.await_prompt).
PROMPT_POLL_SECONDS = 0.25


class PipelineState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    FAILED = "failed"
    SKIPPED = "skipped"


class CollisionDecision(str, Enum):
    KEEP_EXISTING = "keep_existing"
    KEEP_CANDIDATE = "keep_candidate"
    RENAME_CANDIDATE = "rename_candidate"
    PROMPT = "prompt"
    DISCARD_DUPLICATE = "discard_duplicate"
    # Not a collision after all: two exposures inside one second (F9). Never
    # reached by NameCollisionResolver on its own -- pipeline_stages.siblings
    # settles the provable case before the resolver is asked, and a person
    # answering the collision prompt settles the case EXIF cannot prove.
    SIBLINGS = "siblings"


class PipelineMode(str, Enum):
    CLI = "cli"
    UI = "ui"


class PipelineError(Exception):
    pass


class PipelinePaused(PipelineError):
    pass


class CatastrophicSafetyError(PipelineError):
    pass


class PipelineConfigError(PipelineError):
    pass


@dataclass(frozen=True)
class SafetySnapshotEntry:
    original_path: Path
    size: int
    modified_at: float
    md5: str


@dataclass
class PromptRequest:
    prompt_id: str
    prompt_type: str
    payload: dict
    stage_id: str | None = None
    answered: bool = False
    answer: dict | None = None
    # Set the moment an answer arrives, so a stage blocked in
    # PipelineContext.await_prompt() wakes immediately instead of polling.
    answered_event: threading.Event = field(
        default_factory=threading.Event, repr=False, compare=False)


@dataclass
class CollisionResult:
    decision: CollisionDecision
    original: Path | None = None
    duplicate: Path | None = None
    target_path: Path | None = None
    prompt: PromptRequest | None = None
    reason: str = ""


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_config() -> dict:
    photo_base_folder = os.environ.get("PHOTO_BASE_FOLDER", r"c:\__PHOTOS")
    root_folder = str(Path(photo_base_folder)) if photo_base_folder else r"c:\__PHOTOS"
    working_folder = Path(root_folder) / "____INGEST_PIPELINE"

    return {
        "dashboard": {
            "host": "127.0.0.1",
            "port": DEFAULT_DASHBOARD_PORT,
            "open_browser": True,
        },
        "paths": {
            "root_folder": root_folder,
            "working_folder": str(working_folder),
            "inbox_folder": str(working_folder / "INBOX"),
            "ready_folder": str(working_folder / "READY"),
            "temp_folder": str(working_folder / ".TMP"),
            "legacy_unsorted_folder": str(Path(root_folder) / "____TO_SORT" / "____UNSORTED"),
            "legacy_ready_folder": str(Path(root_folder) / "____TO_SORT" / "__READY"),
            "camera_uploads": "c:/Users/luxxa/Dropbox/Camera Uploads",
            "ingest": {
                "camera_uploads": "c:/Users/luxxa/Dropbox/Camera Uploads",
            },
            "unsorted_folder": str(working_folder / "INBOX"),
            "temp_root": str(working_folder / ".TMP"),
        },
        "extensions": {
            "lossy_images": [".jpg", ".jpeg"],
            "other_images": [".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"],
            "raw_images": [".arw", ".cr2", ".crw", ".dng", ".mpo", ".rw2"],
            "videos": [".mp4", ".mov", ".avi"],
            "sidecars": ["._exif"],
            # Camera thumbnails and low-res proxies. Sidecars, not media
            # (ARCHIVE_STANDARD.md X6): a ".thm" counted as a lossy image
            # inflates a folder's image count and can be picked as a shot's
            # representative in place of the picture it is a thumbnail of.
            "previews": [".thm", ".lrv"],
        },
        "external_tools": {
            "exiftool": "exiftool",
            "irfanview": r"c:\_[SOFT] - Grafika\__Browsers, Viewers\IrfanView\i_view32.exe",
            "dpviewer": r"c:\Program Files (x86)\Canon\Digital Photo Professional\DPPViewer.exe",
            "sony_converter": r"c:\Program Files\Sony\Imaging Edge Desktop\ied.exe",
        },
        "camera_symbols": {
            "": "NOID",
        },
        # Who took the shot, as opposed to what took it. Same shape as
        # camera_symbols: name -> short symbol. The empty key is the
        # archive owner and maps to no symbol, so the owner's own media
        # carries no marker and nothing already in the archive is renamed.
        # There is no built-in table -- camera models are universal, the
        # people in one person's archive are not.
        "author_symbols": {
            "": "",
        },
        "collision": {
            "significantly_smaller_ratio": DEFAULT_COLLISION_THRESHOLD,
            "duplicate_suffix": "_DUPE",
            "low_res_suffix": "_LOWRES",
            "differing_suffix": "_DIFFERS",
        },
        # A capture at or before this time belongs to the previous day's folder
        # (ARCHIVE_STANDARD.md N7) -- a night that runs past midnight is one
        # event. Top level, not in "legacy": every stage depends on it, and the
        # legacy block is for compatibility shims. day_boundary() still reads
        # the old location so an existing config.json keeps working.
        "day_boundary_time": "04.44.44",
        "legacy": {
            "date_folder_suffix": " - 1. ######",
            "raw_marker": "RAW__",
            "subfolders": {
                "raw": "##   RAWs   ##",
                "exif": "##   EXIFs   ##",
                "unsupported": "##   UNSUPPORTED EXTENSIONS   ##",
                "empty": "##   EMPTY FILES   ##",
                "not_enough_info": "##   NOT_ENOUGH_INFO FILES   ##",
                "duplicate_file_names": "##   DUPLICATE_FILE_NAMES FILES   ##",
                "old_exif": "old_EXIF"
            }
        },
        # No "taxonomy" block on purpose. The subfolder names live in exactly
        # one place -- src/pipeline_stages/taxonomy.py, per ARCHIVE_STANDARD.md
        # rule T8 -- and taxonomy_folder() falls through to DEFAULT_TAXONOMY
        # there. Restating them here would be a second list to keep in step, and
        # save_config() would then bake a stale copy into every config.json.
        # A config file may still override an individual key.
        "provenance": {
            "dont_move_folder": "__DONT_MOVE",
            "journal_folder": ".JOURNAL",
            "geodata_extensions": [".gpx"],
        },
        # Final review step: open the external screenshot-grouper GUI (shared
        # with the Mac workflow) on each freshly sorted, ungrouped event folder
        # so the day can be split into named sub-events. Off until its
        # python/project paths are configured. max_folders caps how many GUIs
        # a single run will open (0 = no limit).
        "screenshot_grouping": {
            "enabled": False,
            "python": "",
            "project_path": "",
            "max_folders": 0,
        },
        # Hold the run until this batch's event folders have really been named,
        # and re-resolve their paths afterwards. `null` follows
        # screenshot_grouping.enabled: a run that opened the grouper is a run
        # where naming was expected, and one that did not is not worth blocking.
        "grouping_review": {
            "enabled": None,
        },
        # After grouping, move each shot's RAW/EXIF/video companions to follow
        # its representative image into the new sub-event folder.
        "companion_reconciliation": {
            "enabled": False,
        },
        # Archive restructuring repairs genuinely missing RAW metadata after
        # tolerant historical-name matching (ARCHIVE_STANDARD.md X14).
        "raw_sidecar_generation": {
            "enabled": True,
        },
        # Two-timeline timezone & travel model (design.md Decision 9). Zones are
        # a small alias map over IANA names; offsets are derived, never typed.
        "zones": {},
        "locations": [],
        "camera_clock_sets": [],
        "safety": {
            "enabled": True,
            "hash_chunk_size": 1024 * 1024,
        },
        "retry": {
            "attempts": DEFAULT_RETRY_ATTEMPTS,
            "delay_seconds": DEFAULT_RETRY_DELAY_SECONDS,
        },
    }


def merge_dicts(defaults: dict, overrides: dict) -> dict:
    merged = dict(defaults)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _confine_ingest_paths(paths: dict, root_path: Path, declared_paths: dict) -> None:
    # Ingest sources are read-and-emptied: the pipeline harvests files out of
    # them and into the run's own tree. An absolute one pointing outside the
    # tree this run was told to operate on would therefore drain the real
    # Dropbox folder into a scratch tree — the --base-folder override and the
    # partial-scratch-config cases both hit this, because default_config()
    # hardcodes the real Camera Uploads path and _reroot() cannot map a path
    # that was never under the old root.
    #
    # So an external ingest path is trusted only when the config file declared
    # it *and* declared the very root this run resolved to. Anything else is
    # confined to the root, which for a scratch run means a folder that simply
    # does not exist and the harvest stages skip.
    logger = logging.getLogger(__name__)
    declared_root = declared_paths.get("root_folder") or declared_paths.get("photo_base_folder")
    root_is_declared = declared_root is not None and Path(declared_root) == root_path

    def confine(value: str, key: str, declared: bool) -> str:
        path = Path(value)
        if not path.is_absolute():
            return str(root_path / path)
        # Pass the original string back rather than str(Path(...)): rewriting
        # separators here would churn the user's config.json on every save.
        if path.is_relative_to(root_path):
            return value
        if declared and root_is_declared:
            return value
        confined = root_path / path.name
        logger.warning(
            "Ingest path %s=%s lies outside the run root %s and was not configured "
            "for it; using %s instead so this run cannot harvest from it.",
            key, path, root_path, confined,
        )
        return str(confined)

    camera_uploads = paths.get("camera_uploads")
    if isinstance(camera_uploads, str) and camera_uploads:
        paths["camera_uploads"] = confine(
            camera_uploads, "camera_uploads", "camera_uploads" in declared_paths
        )

    ingest = paths.get("ingest")
    if isinstance(ingest, dict):
        declared_ingest = declared_paths.get("ingest")
        declared_ingest = declared_ingest if isinstance(declared_ingest, dict) else {}
        for key, value in list(ingest.items()):
            if isinstance(value, str) and value:
                ingest[key] = confine(value, f"ingest.{key}", key in declared_ingest)


def normalize_config_paths(config: dict, base_folder: str | Path | None = None,
                           declared_config: dict | None = None) -> dict:
    paths = config.setdefault("paths", {})
    persisted_root = paths.get("root_folder") or paths.get("photo_base_folder")
    root_folder = base_folder or persisted_root or os.environ.get("PHOTO_BASE_FOLDER") or r"c:\__PHOTOS"
    root_path = Path(root_folder)
    if root_path.name == "____TO_SORT":
        root_path = root_path.parent
    if not root_path.is_absolute():
        root_path = Path(os.environ.get("PHOTO_BASE_FOLDER", r"c:\__PHOTOS")) / root_path

    # Absolute working paths persisted under the old root must follow a root
    # override; otherwise a --base-folder run reads from the real tree while
    # writing into the override tree. Paths outside the old root are deliberate
    # external locations and stay untouched.
    old_root = Path(persisted_root) if persisted_root else None

    def _reroot(path: Path) -> Path:
        if old_root is None or not path.is_absolute():
            return path
        try:
            return root_path / path.relative_to(old_root)
        except ValueError:
            return path

    working_folder = paths.get("working_folder") or "____INGEST_PIPELINE"
    working_path = _reroot(Path(working_folder))
    if not working_path.is_absolute():
        working_path = root_path / working_path

    inbox_folder = paths.get("inbox_folder") or paths.get("unsorted_folder") or "INBOX"
    inbox_path = _reroot(Path(inbox_folder))
    if not inbox_path.is_absolute():
        inbox_path = working_path / inbox_path.name

    ready_folder = paths.get("ready_folder") or "READY"
    ready_path = _reroot(Path(ready_folder))
    if not ready_path.is_absolute() or ready_path.name == "__READY":
        ready_path = working_path / "READY"

    temp_folder = paths.get("temp_folder") or paths.get("temp_root") or ".TMP"
    temp_path = _reroot(Path(temp_folder))
    if not temp_path.is_absolute():
        temp_path = working_path / temp_path

    legacy_unsorted = _reroot(Path(paths.get("legacy_unsorted_folder") or (root_path / "____TO_SORT" / "____UNSORTED")))
    if not legacy_unsorted.is_absolute():
        legacy_unsorted = root_path / legacy_unsorted
    legacy_ready = _reroot(Path(paths.get("legacy_ready_folder") or (root_path / "____TO_SORT" / "__READY")))
    if not legacy_ready.is_absolute():
        legacy_ready = root_path / legacy_ready

    paths["root_folder"] = str(root_path)
    paths["working_folder"] = str(working_path)
    paths["inbox_folder"] = str(inbox_path)
    paths["ready_folder"] = str(ready_path)
    paths["temp_folder"] = str(temp_path)
    paths["legacy_unsorted_folder"] = str(Path(legacy_unsorted))
    paths["legacy_ready_folder"] = str(Path(legacy_ready))
    paths["unsorted_folder"] = str(inbox_path)
    paths["temp_root"] = str(temp_path)
    paths.pop("photo_base_folder", None)

    declared_paths = (declared_config or {}).get("paths")
    _confine_ingest_paths(paths, root_path, declared_paths if isinstance(declared_paths, dict) else {})
    return config


def timezone_file_path(config_path: str | Path | None = None, config: dict | None = None) -> Path:
    base = Path(config_path).parent if config_path else project_root()
    override = (config or {}).get("timezone_file")
    if override:
        candidate = Path(override)
        return candidate if candidate.is_absolute() else base / candidate
    return base / TIMEZONE_FILE_NAME


def _load_timezone_file(config: dict, config_path: str | Path | None) -> None:
    # Overlay the dedicated timezone file over whatever is (or isn't) inline in
    # config.json. The file wins, so it is the source of truth once present.
    tz_path = timezone_file_path(config_path, config)
    if not tz_path.exists():
        return
    try:
        with tz_path.open("r", encoding="utf-8") as handler:
            data = json.load(handler)
    except (json.JSONDecodeError, OSError):
        logging.getLogger(__name__).warning("Could not read timezone file %s", tz_path)
        return
    if isinstance(data, dict):
        for key in TIMEZONE_KEYS:
            if key in data:
                config[key] = data[key]


def load_config(config_path: str | Path | None = None, base_folder: str | Path | None = None) -> dict:
    path = Path(config_path) if config_path else project_root() / CONFIG_FILE_NAME
    defaults = default_config()
    if not path.exists():
        # Nothing was declared for this tree, so the hardcoded default ingest
        # paths are not trusted for it.
        config = normalize_config_paths(defaults, base_folder, declared_config={})
    else:
        with path.open("r", encoding="utf-8") as handler:
            loaded = json.load(handler)
        if not isinstance(loaded, dict):
            raise PipelineConfigError(f"Config file must contain an object: {path}")
        config = normalize_config_paths(merge_dicts(defaults, loaded), base_folder, declared_config=loaded)
    _load_timezone_file(config, config_path)
    _warn_timezone_config(config)
    return config


def _warn_timezone_config(config: dict) -> None:
    # Enforce the at_reading "first corrected reading" convention at load time;
    # this is the one timezone field that otherwise fails silently (Decision 9).
    from src.pipeline_stages.timezone_engine import validate_timezone_config

    for message in validate_timezone_config(config):
        logging.getLogger(__name__).warning("timezone config: %s", message)


def relativize_config_paths(config: dict) -> dict:
    # Stored configs keep only root_folder absolute; every working path under
    # it is persisted relative so the base folder can be swapped via CLI.
    relativized = json.loads(json.dumps(config))
    paths = relativized.get("paths", {})
    root = paths.get("root_folder")
    if not root:
        return relativized
    root_path = Path(root)
    for key, value in paths.items():
        if key in ("root_folder", "ingest") or not isinstance(value, str):
            continue
        try:
            paths[key] = str(Path(value).relative_to(root_path))
        except ValueError:
            continue
    return relativized


def save_config(config: dict, config_path: str | Path | None = None) -> None:
    path = Path(config_path) if config_path else project_root() / CONFIG_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = relativize_config_paths(config)

    # Split the timezone/travel data into its own file; keep it out of config.json.
    tz_data = {key: serializable.pop(key) for key in TIMEZONE_KEYS if key in serializable}
    with path.open("w", encoding="utf-8") as handler:
        json.dump(serializable, handler, indent=2, sort_keys=True)
        handler.write("\n")

    if tz_data:
        tz_path = timezone_file_path(config_path, config)
        tz_path.parent.mkdir(parents=True, exist_ok=True)
        with tz_path.open("w", encoding="utf-8") as handler:
            json.dump(tz_data, handler, indent=2, sort_keys=True)
            handler.write("\n")


def normalize_suffix(suffix: str) -> str:
    return suffix.lower()


def dont_move_folder_name(config: dict) -> str:
    """The name of the folder the pipeline must never touch.

    One definition (T8); ``pipeline_stages.provenance.dont_move_folder``
    delegates here. It lives in core because core is what has to honour it
    first -- the safety snapshot runs before any stage does.
    """
    return config.get("provenance", {}).get("dont_move_folder", "__DONT_MOVE")


def protected_intake_folders(config: dict) -> list[Path]:
    """The `__DONT_MOVE` folders, one per intake root.

    The spec is explicit: the pipeline never reads, moves, renames or deletes
    anything inside these, and the exclusion applies at the **top level of the
    intake folder only** -- a `__DONT_MOVE` nested deeper is an ordinary
    folder and is processed like any other.
    """
    name = dont_move_folder_name(config)
    paths = config.get("paths", {})
    folders: list[Path] = []
    for key in ("unsorted_folder", "inbox_folder", "legacy_unsorted_folder"):
        root = paths.get(key)
        if not root:
            continue
        candidate = Path(root) / name
        if candidate not in folders:
            folders.append(candidate)
    return folders


def is_protected(path: Path, protected: list[Path]) -> bool:
    """Is ``path`` inside one of the protected folders?

    A pure path comparison -- no filesystem access, and case-insensitive on
    Windows, where `is_relative_to` follows the platform's own rules.
    """
    return any(path.is_relative_to(folder) for folder in protected)


def measure_folder(folder: Path) -> dict:
    """File count and total bytes for a folder tree, without reading content.

    The cheap half of a safety check. Checksumming a protected folder would
    mean reading files the pipeline is forbidden to read, and would cost the
    same as hashing the archive; a stat-only tally still catches the failure
    that matters -- the pipeline having deleted or truncated something in
    there -- for a rounding error's worth of time.
    """
    files, total = 0, 0
    if not folder.exists():
        return {"files": 0, "bytes": 0, "exists": False}
    for path in folder.rglob("*"):
        try:
            if not path.is_file():
                continue
            total += path.stat().st_size
        except OSError:
            continue
        files += 1
    return {"files": files, "bytes": total, "exists": True}


# Re-exported, not defined: ``src.utils.checksums`` is the one implementation
# (T8), and every ``from src.core import file_md5`` in the pipeline keeps
# reading it from here.


def with_retry(operation, attempts=DEFAULT_RETRY_ATTEMPTS, delay_seconds=DEFAULT_RETRY_DELAY_SECONDS):
    last_error = None
    for attempt in range(attempts):
        try:
            return operation()
        except OSError as error:
            last_error = error
            if attempt == attempts - 1:
                break
            time.sleep(delay_seconds * (attempt + 1))
    raise last_error


def same_file(source, target) -> bool:
    """True when two names are one file -- which is what a case-only rename is.

    Windows' filesystem is case-insensitive, so ``target.exists()`` is true for
    a rename that changes only the case of a name ("._EXIF" onto "._exif").
    That is not a collision to refuse; it is the file itself.
    """
    try:
        return os.path.samefile(str(source), str(target))
    except OSError:
        return False


def safe_move(source: str | Path, destination: str | Path, attempts=DEFAULT_RETRY_ATTEMPTS,
              delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> Path:
    source = Path(source)
    destination = Path(destination)

    def operation():
        destination.parent.mkdir(parents=True, exist_ok=True)
        # T2, rename never replace. shutil.move keeps that promise only within
        # one volume, where it delegates to os.rename and Windows raises on a
        # collision. Across volumes -- the Dropbox intake on one disk, the
        # archive on another -- it falls back to copy2 plus unlink, which
        # overwrites whatever is already sitting on that name, silently. So
        # the collision is refused here instead, on every path.
        if destination.exists() and not same_file(source, destination):
            raise FileExistsError(
                "%s already exists; not moved onto (T2)" % destination)
        return Path(shutil.move(str(source), str(destination)))

    return with_retry(operation, attempts, delay_seconds)


def safe_rename(source: str | Path, destination: str | Path, attempts=DEFAULT_RETRY_ATTEMPTS,
                delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> Path:
    source = Path(source)
    destination = Path(destination)

    def operation():
        destination.parent.mkdir(parents=True, exist_ok=True)
        source.rename(destination)
        return destination

    return with_retry(operation, attempts, delay_seconds)


def safe_delete(path: str | Path, attempts=DEFAULT_RETRY_ATTEMPTS,
                delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> None:
    path = Path(path)

    def operation():
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    return with_retry(operation, attempts, delay_seconds)


@dataclass
class MediaAsset:
    primary_path: Path
    sidecars: dict[str, Path] = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    asset_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self):
        self.primary_path = Path(self.primary_path)
        self.sidecars = {
            name: Path(path)
            for name, path in self.sidecars.items()
        }

    @property
    def all_paths(self) -> list[Path]:
        return [self.primary_path] + list(self.sidecars.values())

    def existing_paths(self) -> list[Path]:
        return [
            path
            for path in self.all_paths
            if path.exists()
        ]

    def register_sidecar(self, name: str, path: str | Path) -> None:
        self.sidecars[name] = Path(path)

    def rename_all(self, new_stem: str, attempts=DEFAULT_RETRY_ATTEMPTS,
                   delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> "MediaAsset":
        original_primary = self.primary_path
        original_sidecars = dict(self.sidecars)
        moved: list[tuple[Path, Path]] = []

        try:
            new_primary = self.primary_path.with_name(new_stem + self.primary_path.suffix)
            if self.primary_path.exists() and new_primary != self.primary_path:
                safe_rename(self.primary_path, new_primary, attempts, delay_seconds)
                moved.append((new_primary, self.primary_path))
            self.primary_path = new_primary

            for name, sidecar_path in list(self.sidecars.items()):
                new_sidecar = sidecar_path.with_name(new_stem + sidecar_path.suffix)
                if sidecar_path.exists() and new_sidecar != sidecar_path:
                    safe_rename(sidecar_path, new_sidecar, attempts, delay_seconds)
                    moved.append((new_sidecar, sidecar_path))
                self.sidecars[name] = new_sidecar
        except Exception:
            for current, previous in reversed(moved):
                if current.exists() and not previous.exists():
                    safe_rename(current, previous, attempts, delay_seconds)
            self.primary_path = original_primary
            self.sidecars = original_sidecars
            raise

        return self

    def move_all(self, destination_dir: str | Path, attempts=DEFAULT_RETRY_ATTEMPTS,
                 delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> "MediaAsset":
        destination_dir = Path(destination_dir)
        original_primary = self.primary_path
        original_sidecars = dict(self.sidecars)
        moved: list[tuple[Path, Path]] = []

        try:
            new_primary = destination_dir / self.primary_path.name
            if self.primary_path.exists() and new_primary != self.primary_path:
                safe_move(self.primary_path, new_primary, attempts, delay_seconds)
                moved.append((new_primary, self.primary_path))
            self.primary_path = new_primary

            for name, sidecar_path in list(self.sidecars.items()):
                new_sidecar = destination_dir / sidecar_path.name
                if sidecar_path.exists() and new_sidecar != sidecar_path:
                    safe_move(sidecar_path, new_sidecar, attempts, delay_seconds)
                    moved.append((new_sidecar, sidecar_path))
                self.sidecars[name] = new_sidecar
        except Exception:
            for current, previous in reversed(moved):
                if current.exists() and not previous.exists():
                    safe_move(current, previous, attempts, delay_seconds)
            self.primary_path = original_primary
            self.sidecars = original_sidecars
            raise

        return self

    def delete_all(self, attempts=DEFAULT_RETRY_ATTEMPTS,
                   delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> None:
        for path in self.existing_paths():
            safe_delete(path, attempts, delay_seconds)


@dataclass
class PipelineContext:
    assets: list[MediaAsset] = field(default_factory=list)
    config: dict = field(default_factory=default_config)
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stage_states: dict[str, PipelineState] = field(default_factory=dict)
    stage_stats: dict[str, dict[str, int]] = field(default_factory=dict)
    # Three per-stage records, each with exactly one writer, so nothing has to
    # guess who owns a key:
    #   stage_stats     -- the stage: how much went in, out, and wrong.
    #   stage_timings   -- the orchestrator: when it ran and for how long.
    #   stage_progress  -- StageProgress: where a long stage is right now.
    stage_timings: dict[str, dict] = field(default_factory=dict)
    stage_progress: dict[str, dict] = field(default_factory=dict)
    # Free-form findings a stage wants a reader to see next to its node --
    # "3 files had no capture date", "42 GB rehashed". Distinct from the log,
    # which is a chronological transcript nobody scrolls back through.
    stage_notes: dict[str, list[str]] = field(default_factory=dict)
    input_snapshot: dict[str, SafetySnapshotEntry] = field(default_factory=dict)
    # File count and total bytes of each `__DONT_MOVE` folder, taken before
    # any stage runs. Not checksums: the pipeline is forbidden to read what is
    # in there, so its integrity is watched by size and count alone -- enough
    # to catch the pipeline having deleted or truncated something, for none of
    # the cost of hashing it.
    protected_snapshot: dict[str, dict] = field(default_factory=dict)
    safety_exceptions: dict[str, str] = field(default_factory=dict)
    prompt_queue: deque[PromptRequest] = field(default_factory=deque)
    prompt_answers: dict[str, dict] = field(default_factory=dict)
    # The prompt a stage is currently blocked on, so the dashboard can say so
    # instead of looking idle, and an abort request so it can let go.
    waiting_prompt_id: str | None = None
    abort_event: threading.Event = field(default_factory=threading.Event, repr=False)
    logs: list[str] = field(default_factory=list)
    mode: PipelineMode = PipelineMode.CLI
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    provenance: dict[str, dict] = field(default_factory=dict)
    geodata: list[dict] = field(default_factory=list)
    # Event folders that folder-sorting moved assets into this run, and the
    # subset the screenshot-grouping stage actually opened in the grouper (as
    # their renamed __TO_SPLIT__ paths) — consumed by companion-reconciliation.
    affected_event_folders: set[Path] = field(default_factory=set)
    screenshot_grouped_folders: list[Path] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)

    @classmethod
    def from_config_file(cls, config_path: str | Path | None = None,
                         mode: PipelineMode = PipelineMode.CLI) -> "PipelineContext":
        return cls(config=load_config(config_path), mode=mode)

    def add_asset(self, asset: MediaAsset) -> None:
        with self.lock:
            self.assets.append(asset)

    def log(self, message: str) -> None:
        with self.lock:
            self.logs.append(message)

    def set_stage_state(self, stage_id: str, state: PipelineState) -> None:
        with self.lock:
            self.stage_states[stage_id] = state

    def set_stage_stats(self, stage_id: str, inputs: int | None = None,
                        outputs: int | None = None, errors: int | None = None,
                        **extra) -> None:
        """In / out / errors for a stage, plus any stage-specific numbers.

        ``extra`` is how a stage reports the counts only it knows about --
        ``skipped``, ``bytes``, ``folders`` -- without every such number having
        to become a parameter here. The dashboard renders them generically.
        """
        with self.lock:
            stats = self.stage_stats.setdefault(stage_id, {})
            if inputs is not None:
                stats["inputs"] = inputs
            if outputs is not None:
                stats["outputs"] = outputs
            if errors is not None:
                stats["errors"] = errors
            for key, value in extra.items():
                if value is not None:
                    stats[key] = value

    def set_stage_progress(self, stage_id: str, record: dict | None) -> None:
        """Where a long-running stage currently is. Written by StageProgress."""
        with self.lock:
            if record is None:
                self.stage_progress.pop(stage_id, None)
            else:
                self.stage_progress[stage_id] = record

    def add_stage_note(self, stage_id: str, note: str) -> None:
        """A finding worth showing next to the stage after it has finished."""
        with self.lock:
            notes = self.stage_notes.setdefault(stage_id, [])
            if note not in notes:
                notes.append(note)

    def progress(self, stage_id: str, activity: str, **kwargs) -> StageProgress:
        """A progress reporter bound to this context and stage."""
        return StageProgress(self, stage_id, activity, **kwargs)

    def media_extensions(self) -> set[str]:
        extensions = self.config.get("extensions", {})
        values = []
        values.extend(extensions.get("lossy_images", []))
        values.extend(extensions.get("raw_images", []))
        values.extend(extensions.get("videos", []))
        return {
            normalize_suffix(value)
            for value in values
        }

    def snapshot_inputs(self, roots: list[str | Path] | None = None,
                        stage_id: str | None = None) -> dict:
        """MD5 every media file about to be processed, so the run can prove
        later that none of them vanished.

        Reports progress: this reads every input byte, so on a big intake it is
        minutes of apparently doing nothing. ``stage_id`` is what binds the
        report to a dashboard node; without it the hashing is silent as before.

        Returns the tally the caller needs for its own log line.
        """
        roots = roots or [self.config["paths"]["unsorted_folder"]]
        media_extensions = self.media_extensions()
        chunk_size = self.config.get("safety", {}).get("hash_chunk_size", 1024 * 1024)
        snapshot = {}
        # `__DONT_MOVE` is not intake. The pipeline is forbidden to read it, it
        # never becomes an asset, and hashing it would both violate that and
        # let a file parked in there stand in for a genuinely lost input --
        # the two would collide on MD5 and the safety check would pass. It is
        # watched separately and much more cheaply; see `measure_folder`.
        protected = protected_intake_folders(self.config)

        # Walk first, hash second. Two passes over the tree costs one cheap
        # directory listing and buys a real total, so the progress bar is a
        # percentage from its first tick instead of an open-ended count.
        candidates: list[tuple[Path, os.stat_result]] = []
        # Where the intake actually came from, one entry per containing folder.
        # A count alone says how much arrived; this says from where, which is
        # what tells a stray import apart from the one you meant to run — and
        # these same folder names become origin labels in folder-intake.
        folders: dict[Path, dict] = {}
        protected_skipped = 0
        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            for path in root_path.rglob("*"):
                if not path.is_file() or normalize_suffix(path.suffix) not in media_extensions:
                    continue
                if is_protected(path, protected):
                    protected_skipped += 1
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                candidates.append((path, stat))
                folder = folders.setdefault(
                    path.parent, {"files": 0, "bytes": 0, "root": root_path})
                folder["files"] += 1
                folder["bytes"] += stat.st_size

        total_bytes = sum(stat.st_size for _path, stat in candidates)
        reporter = None
        if stage_id:
            reporter = self.progress(
                stage_id,
                "Checksumming inputs",
                total=len(candidates),
                total_bytes=total_bytes,
            )

        duplicates = 0
        for path, stat in candidates:
            md5 = file_md5(path, chunk_size)
            if md5 in snapshot:
                # Two byte-identical inputs collapse to one snapshot entry, so
                # the "N files in" and "N hashes to find" numbers legitimately
                # differ. Counted rather than hidden: it is the difference
                # between a shrinking count and a lost file.
                duplicates += 1
            snapshot[md5] = SafetySnapshotEntry(
                original_path=path,
                size=stat.st_size,
                modified_at=stat.st_mtime,
                md5=md5,
            )
            if reporter:
                reporter.advance(size_bytes=stat.st_size)

        with self.lock:
            self.input_snapshot = snapshot

        tally = {
            "files": len(candidates),
            "bytes": total_bytes,
            "unique": len(snapshot),
            "duplicates": duplicates,
            "protected_skipped": protected_skipped,
            # Path order rather than count order: siblings stay together, so
            # the list reads as the tree it describes.
            "folders": [
                {
                    "path": path,
                    "root": info["root"],
                    "files": info["files"],
                    "bytes": info["bytes"],
                }
                for path, info in sorted(folders.items(), key=lambda item: str(item[0]).lower())
            ],
        }
        if reporter:
            reporter.finish()
        return tally

    def extend_snapshot(self, paths, stage_id: str | None = None) -> dict:
        """Bring media that arrived after the opening snapshot under the safety net.

        The opening snapshot is taken against the INBOX before any stage runs,
        so anything a later stage carries in — harvested from Camera Uploads,
        migrated from the legacy unsorted folder — was invisible to it, and a
        loss of those files went undetected. This is how such a stage says
        "these are mine now, watch them too".

        ``paths`` may name files or whole directories; a directory is walked,
        because the legacy migration moves entire folders in one go.

        Merges rather than replaces — `snapshot_inputs` overwrites the whole
        snapshot, so calling it a second time would discard the first.

        Files are hashed where they now sit, which means the single move that
        brought them here is not itself covered; every later move is, exactly
        as for files that started in the INBOX. Call this *after* the move has
        succeeded: registering a file that never actually arrived would have
        the safety check hunt at the end for something that was never taken.
        """
        media_extensions = self.media_extensions()
        chunk_size = self.config.get("safety", {}).get("hash_chunk_size", 1024 * 1024)
        protected = protected_intake_folders(self.config)

        candidates: list[tuple[Path, os.stat_result]] = []
        seen: set[Path] = set()
        for entry in paths:
            path = Path(entry)
            found = sorted(path.rglob("*")) if path.is_dir() else [path]
            for item in found:
                if not item.is_file() or normalize_suffix(item.suffix) not in media_extensions:
                    continue
                if is_protected(item, protected):
                    continue
                try:
                    resolved = item.resolve()
                    stat = item.stat()
                except OSError:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append((item, stat))

        if not candidates:
            return {"files": 0, "bytes": 0, "new_checksums": 0, "already_known": 0}

        total_bytes = sum(stat.st_size for _path, stat in candidates)
        reporter = None
        if stage_id:
            reporter = self.progress(
                stage_id,
                "Checksumming arrivals",
                total=len(candidates),
                total_bytes=total_bytes,
            )

        new_checksums, already_known = 0, 0
        for path, stat in candidates:
            md5 = file_md5(path, chunk_size)
            with self.lock:
                if md5 in self.input_snapshot:
                    already_known += 1
                else:
                    new_checksums += 1
                self.input_snapshot[md5] = SafetySnapshotEntry(
                    original_path=path,
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                    md5=md5,
                )
            if reporter:
                reporter.advance(size_bytes=stat.st_size)

        # Kept here rather than in each caller so the two numbers cannot drift
        # apart: every arrival is counted once, by the code that records it.
        self.counters["input_files_added_later"] += len(candidates)
        self.counters["input_bytes"] += total_bytes
        self.counters["input_checksums"] = len(self.input_snapshot)
        if reporter:
            reporter.finish()
        return {
            "files": len(candidates),
            "bytes": total_bytes,
            "new_checksums": new_checksums,
            "already_known": already_known,
        }

    def snapshot_protected_folders(self) -> dict[str, dict]:
        """Measure the `__DONT_MOVE` folders so a later pass can prove the
        pipeline left them alone. Stat only -- never their content."""
        measured = {
            str(folder): measure_folder(folder)
            for folder in protected_intake_folders(self.config)
        }
        with self.lock:
            self.protected_snapshot = measured
        return measured

    def verify_protected_folders(self) -> list[dict]:
        """Re-measure and return one entry per folder that changed.

        A change is reported, never repaired and never guessed at: the two
        explanations -- a pipeline bug, or the user editing their own staging
        folder mid-run -- look identical from here.
        """
        changed = []
        for folder_name, before in self.protected_snapshot.items():
            after = measure_folder(Path(folder_name))
            if after["files"] != before["files"] or after["bytes"] != before["bytes"]:
                changed.append({"folder": folder_name, "before": before, "after": after})
        return changed

    def register_safety_exception(self, md5: str, reason: str) -> None:
        with self.lock:
            self.safety_exceptions[md5] = reason

    def create_prompt(self, prompt_type: str, payload: dict, stage_id: str | None = None) -> PromptRequest:
        prompt = PromptRequest(
            prompt_id=uuid.uuid4().hex,
            prompt_type=prompt_type,
            payload=payload,
            stage_id=stage_id,
        )
        with self.lock:
            self.prompt_queue.append(prompt)
        return prompt

    def answer_prompt(self, prompt_id: str, answer: dict) -> None:
        with self.lock:
            self.prompt_answers[prompt_id] = answer
            for prompt in self.prompt_queue:
                if prompt.prompt_id == prompt_id:
                    prompt.answered = True
                    prompt.answer = answer
                    prompt.answered_event.set()
                    break

    def await_prompt(self, prompt: PromptRequest, auto_answer: dict | None = None) -> dict:
        """Block until the user answers `prompt`. There is no timeout.

        A prompt exists because the pipeline cannot proceed without a human
        decision — resolving a name collision, converting RAWs by hand, naming
        the folders the grouper just created. Guessing after N seconds is
        always wrong: it either discards the user's work or writes a decision
        they never made. So this waits as long as it takes, and the only ways
        out are an answer or an explicit abort (the dashboard's Pause button,
        via `request_abort`).

        Waking is event-driven; the short poll interval exists only so an abort
        raised on another thread is noticed promptly.

        Outside UI mode nobody can answer. Rather than hang a headless run
        forever, `auto_answer` supplies the documented fallback and the choice
        is logged; without one, the run pauses as it always has.
        """
        if prompt.answered:
            return prompt.answer or {}

        if self.mode != PipelineMode.UI:
            if auto_answer is None:
                raise PipelinePaused(
                    f"Prompt {prompt.prompt_type} needs the dashboard to answer it"
                )
            self.log(
                f"No UI to answer {prompt.prompt_type}, continuing with {auto_answer}"
            )
            self.answer_prompt(prompt.prompt_id, auto_answer)
            return auto_answer

        with self.lock:
            self.waiting_prompt_id = prompt.prompt_id
        self.log(f"Waiting for you: {prompt.prompt_type} (the pipeline will not time out)")
        try:
            while not prompt.answered_event.wait(PROMPT_POLL_SECONDS):
                if self.abort_event.is_set():
                    raise PipelinePaused(
                        f"Run aborted while waiting for {prompt.prompt_type}"
                    )
        finally:
            with self.lock:
                self.waiting_prompt_id = None
        self.log(f"Answered {prompt.prompt_type}: {prompt.answer}")
        return prompt.answer or {}

    def request_abort(self) -> None:
        """Release any stage blocked in `await_prompt`, ending the run."""
        self.abort_event.set()

    def clear_abort(self) -> None:
        self.abort_event.clear()


@dataclass
class PipelineStage(ABC):
    stage_id: str
    display_name: str
    # One sentence saying what this stage does to the archive, in the terms a
    # person thinks in ("Moves every file out of inbox subfolders..."), not in
    # the terms the code thinks in. The dashboard shows it under the stage
    # name, so a reader never has to open the source to know what is running.
    # Where a stage is slow or destructive, say so here -- this is the only
    # place the UI has to explain a stage before it starts.
    description: str = ""
    dependencies: tuple[str, ...] = ()
    input_contract: tuple[str, ...] = ()
    output_contract: tuple[str, ...] = ()
    headless: bool = True

    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        raise NotImplementedError

    def cleanup(self, context: PipelineContext) -> None:
        pass


class PipelineOrchestrator:
    def __init__(self, stages: list[PipelineStage], mode: PipelineMode = PipelineMode.CLI,
                 announce=None):
        self.stages = {
            stage.stage_id: stage
            for stage in stages
        }
        self.mode = mode
        # Where stage banners go. Injectable so tests can capture them; the
        # default writes to the console the run was launched from.
        self.announce = announce_to_console if announce is None else announce
        self._validate_graph()

    def _validate_graph(self) -> None:
        for stage in self.stages.values():
            for dependency in stage.dependencies:
                if dependency not in self.stages:
                    raise PipelineError(
                        f"Stage {stage.stage_id} depends on unknown stage {dependency}"
                    )

    def ordered_stages(self) -> list[PipelineStage]:
        pending = set(self.stages)
        complete = set()
        ordered = []

        while pending:
            ready = sorted(
                stage_id
                for stage_id in pending
                if all(dependency in complete for dependency in self.stages[stage_id].dependencies)
            )
            if not ready:
                raise PipelineError("Pipeline graph contains a cycle or unsatisfied dependency")
            for stage_id in ready:
                pending.remove(stage_id)
                complete.add(stage_id)
                ordered.append(self.stages[stage_id])

        return ordered

    def graph(self) -> dict:
        return {
            "nodes": [
                {
                    "id": stage.stage_id,
                    "label": stage.display_name,
                    # What the stage does, in words, so the dashboard can say
                    # it without the reader opening the source.
                    "description": stage.description,
                    "position": index,
                    "dependencies": list(stage.dependencies),
                    "headless": stage.headless,
                }
                for index, stage in enumerate(self.ordered_stages(), start=1)
            ],
            "total": len(self.stages),
        }

    def run(self, context: PipelineContext) -> PipelineContext:
        context.mode = self.mode
        ordered = self.ordered_stages()
        total = len(ordered)
        run_started = time.time()
        context.stage_timings["__run__"] = {
            "started_at": run_started,
            "stage_count": total,
        }
        try:
            for index, stage in enumerate(ordered, start=1):
                context = self._run_stage(context, stage, index, total)
        finally:
            # From a finally so an aborted run still gets its wall-clock and
            # its slowest-stage list -- which is exactly when you want them.
            self._close_run(context, run_started, total)
        return context

    def _close_run(self, context: PipelineContext, run_started: float, total: int) -> None:
        elapsed = time.time() - run_started
        finished = [
            (stage_id, timing.get("duration_seconds") or 0.0)
            for stage_id, timing in context.stage_timings.items()
            if stage_id != "__run__"
        ]
        ranked = sorted(finished, key=lambda item: item[1], reverse=True)
        context.stage_timings["__run__"] = {
            "started_at": run_started,
            "finished_at": time.time(),
            "duration_seconds": elapsed,
            "stage_count": total,
            "stages_run": len(finished),
            # Where the time actually went. Without this, "the run took 22
            # minutes" is a fact nobody can act on.
            "slowest": [
                {"stage_id": stage_id, "duration_seconds": seconds}
                for stage_id, seconds in ranked[:5]
            ],
        }
        if not finished:
            return
        context.log(
            f"Run finished in {format_duration(elapsed)} "
            f"({len(finished)}/{total} stages)"
        )
        for stage_id, seconds in ranked[:5]:
            if seconds < 1:
                continue
            share = (seconds / elapsed * 100) if elapsed else 0
            context.log(f"  time: {stage_id} {format_duration(seconds)} ({share:.0f}%)")

    def _run_stage(self, context: PipelineContext, stage: PipelineStage,
                   index: int, total: int) -> PipelineContext:
        """Run one stage between its two banners.

        The exit banner is emitted from a `finally`, so every path out of a
        stage — success, failure, pause, or an interrupt that no `except` here
        catches — is announced exactly once. A stage can never leave the
        transcript with an opening line and no closing one.

        Timing is recorded here rather than by the stages for the same reason
        the banners are: a stage cannot forget to do it, and a failing stage
        cannot skip it. The duration of a stage that died is the most useful
        one there is.
        """
        self.announce(format_start(index, total, stage.stage_id, stage.display_name))
        context.log(f"Stage: {stage.stage_id}")
        if stage.description:
            context.log(f"  {stage.description}")
        context.set_stage_state(stage.stage_id, PipelineState.ACTIVE)
        started = time.monotonic()
        context.stage_timings[stage.stage_id] = {
            "started_at": time.time(),
            "position": index,
            "outcome": None,
        }
        # Nothing below catches BaseException, so an interrupt lands here.
        outcome, detail = "ABORTED", ""
        try:
            if self.mode == PipelineMode.CLI and not stage.headless:
                raise PipelinePaused(f"Stage requires UI prompt: {stage.stage_id}")
            context = stage.execute(context)
            context.set_stage_state(stage.stage_id, PipelineState.COMPLETE)
            context.log("Completed.")
            outcome = "COMPLETE"
            return context
        except PipelinePaused as error:
            context.set_stage_state(stage.stage_id, PipelineState.PAUSED)
            context.log("Paused.")
            outcome, detail = "PAUSED", str(error)
            raise
        except Exception as error:
            context.set_stage_state(stage.stage_id, PipelineState.FAILED)
            context.log("Failed.")
            outcome, detail = "FAILED", repr(error)
            stage.cleanup(context)
            raise
        finally:
            duration = time.monotonic() - started
            context.stage_timings[stage.stage_id].update({
                "finished_at": time.time(),
                "duration_seconds": duration,
                "outcome": outcome,
                "detail": detail,
            })
            # A finished stage's progress bar is stale the moment it exits;
            # leaving it up makes a completed stage look mid-flight.
            context.set_stage_progress(stage.stage_id, None)
            self.announce(format_end(
                index, total, stage.stage_id, stage.display_name,
                outcome, duration, detail,
                stats=context.stage_stats.get(stage.stage_id),
            ))


@dataclass
class StagedWorkspaceStage(PipelineStage):
    target_extensions: tuple[str, ...] = ()
    sidecar_extension_map: dict[str, str] = field(default_factory=dict)

    def execute(self, context: PipelineContext) -> PipelineContext:
        temp_root = Path(context.config["paths"]["temp_root"])
        temp_root.mkdir(parents=True, exist_ok=True)
        workspace = Path(tempfile.mkdtemp(prefix=f"{self.stage_id}_", dir=temp_root))
        try:
            staged_assets = self.stage_assets(context, workspace)
            self.run_workspace(context, workspace, staged_assets)
            self.sweep_sidecars(staged_assets, workspace)
            return context
        finally:
            safe_delete(workspace)

    def stage_assets(self, context: PipelineContext, workspace: Path) -> list[MediaAsset]:
        workspace.mkdir(parents=True, exist_ok=True)
        wanted = {
            normalize_suffix(value)
            for value in self.target_extensions
        }
        staged_assets = []

        for asset in context.assets:
            if normalize_suffix(asset.primary_path.suffix) not in wanted:
                continue
            staged_path = workspace / asset.primary_path.name
            if asset.primary_path.exists():
                shutil.copy2(asset.primary_path, staged_path)
                staged_assets.append(MediaAsset(staged_path, dict(asset.sidecars), dict(asset.metadata), asset.asset_id))

        return staged_assets

    def run_workspace(self, context: PipelineContext, workspace: Path,
                      staged_assets: list[MediaAsset]) -> None:
        pass

    def sweep_sidecars(self, staged_assets: list[MediaAsset], workspace: Path) -> None:
        for staged_asset in staged_assets:
            for name, extension in self.sidecar_extension_map.items():
                candidate = workspace / (staged_asset.primary_path.stem + extension)
                if candidate.exists():
                    staged_asset.register_sidecar(name, candidate)


class SafetyValidationStage(PipelineStage):
    """Proves no input file was lost, by finding every input MD5 in the output.

    This is the stage that takes the longest, and the reason is worth stating
    plainly because it is not obvious from the outside: there is no index of
    the archive's checksums, so the only way to prove a file is still there is
    to read it. It therefore walks *the whole archive root* -- not just this
    run's output -- and MD5s every media file in it. On a multi-terabyte
    archive that is minutes to hours of pure disk read, every run, and it
    scales with the size of the archive rather than the size of the intake.

    So it says so: how many files and bytes it is about to read, then a live
    count with a throughput and an ETA, then what it proved.
    """

    def __init__(self):
        super().__init__(
            stage_id="safety-validation",
            display_name="Safety Validation",
            description=(
                "Proves nothing was lost: re-reads and checksums every media "
                "file in the archive and confirms each input file's MD5 is "
                "among them. Slowest stage by far -- its cost is the size of "
                "the whole archive, not of this run's intake."
            ),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.config.get("safety", {}).get("enabled", True):
            context.log("Safety validation disabled in config, skipping")
            context.add_stage_note(self.stage_id, "disabled in config")
            return context

        expected = {
            md5: entry
            for md5, entry in context.input_snapshot.items()
            if md5 not in context.safety_exceptions
        }
        output_roots = self._output_roots(context)
        chunk_size = context.config.get("safety", {}).get("hash_chunk_size", 1024 * 1024)

        if expected:
            context.log(
                f"Verifying {format_count(len(expected))} ingested file(s) survived the run."
            )
            context.log(
                "  Every media file under the output roots has to be re-read and "
                "checksummed -- there is no stored index to consult, so this stage "
                "costs the size of the archive, not the size of the intake:"
            )
        else:
            context.log(
                "Nothing was ingested this run, so no checksums have to be matched; "
                "the output roots are still walked for zero-byte files."
            )

        candidates, zero_byte_files, per_root = self._scan(context, output_roots)
        for root, count, size in per_root:
            context.log(f"  - {root}: {format_count(count)} files, {format_bytes(size)}")

        total_bytes = sum(size for _path, size in candidates)

        if expected:
            context.log(
                f"  Reading {format_count(len(candidates))} files "
                f"({format_bytes(total_bytes)}) to match {format_count(len(expected))} checksum(s)."
            )
            found = self._hash_all(context, candidates, chunk_size, expected, total_bytes)
        else:
            # Hashing exists only to locate this run's inputs. With none to
            # locate, reading every byte of the archive proves nothing, so the
            # walk alone is the whole stage.
            found = set()
            total_bytes = 0
            context.log(
                f"  Skipped checksumming {format_count(len(candidates))} archive "
                "file(s): with no inputs to account for, there is nothing to match."
            )
            context.add_stage_note(self.stage_id, "no intake this run, checksumming skipped")

        missing = [
            entry.original_path
            for md5, entry in expected.items()
            if md5 not in found
        ]
        matched = len(expected) - len(missing)
        context.set_stage_stats(
            self.stage_id,
            inputs=len(expected),
            outputs=matched,
            errors=len(missing) + len(zero_byte_files),
            scanned=len(candidates),
            bytes_read=total_bytes,
        )
        context.counters["safety_files_scanned"] = len(candidates)
        context.counters["safety_bytes_read"] = total_bytes
        context.counters["safety_inputs_matched"] = matched

        # Before the raise, not after: a run that is already failing is
        # exactly when it matters whether the protected folder was disturbed
        # too, and a raise here would take that answer with it.
        self._verify_protected(context)

        if zero_byte_files or missing:
            # Log the specific offenders so the dashboard shows what actually
            # failed, not just a count. Cap the lists to avoid flooding the UI.
            for path in missing[:50]:
                context.log(f"  ! missing from output: {path}")
            for path in zero_byte_files[:50]:
                context.log(f"  ! zero-byte output: {path}")
            truncated = " (list truncated, see logs)" if len(missing) > 50 or len(zero_byte_files) > 50 else ""
            raise CatastrophicSafetyError(
                "Safety validation failed: "
                f"{len(missing)} input file(s) not found in output by MD5, "
                f"{len(zero_byte_files)} zero-byte output file(s).{truncated}"
            )

        if expected:
            context.add_stage_note(
                self.stage_id,
                f"all {format_count(matched)} ingested file(s) accounted for in "
                f"{format_count(len(candidates))} archive files ({format_bytes(total_bytes)} read)",
            )
            context.log(
                f"All {format_count(matched)} ingested file(s) accounted for; "
                "no zero-byte outputs."
            )
        else:
            context.log(
                f"Walked {format_count(len(candidates))} archive file(s); no zero-byte outputs."
            )
        return context

    def _verify_protected(self, context: PipelineContext) -> None:
        """Confirm the pipeline left the `__DONT_MOVE` folders exactly as it
        found them.

        Reported, not raised. The pipeline never touches these folders, so a
        change is far more likely to be the user editing their own staging
        area while a long run was going than a pipeline bug -- and ending a
        twenty-minute run over files the pipeline was not handling would be
        the wrong trade. It is loud in the log and on the stage's node, and
        the counter is there for anything that wants to escalate it.
        """
        if not context.protected_snapshot:
            return
        changed = context.verify_protected_folders()
        if not changed:
            watched = sum(
                entry["files"] for entry in context.protected_snapshot.values()
            )
            if watched:
                context.log(
                    f"{format_count(watched)} file(s) in "
                    f"{dont_move_folder_name(context.config)} are as they were, untouched."
                )
            return

        context.counters["protected_folders_changed"] = len(changed)
        for entry in changed:
            before, after = entry["before"], entry["after"]
            context.log(
                f"  ! {entry['folder']} CHANGED during the run: "
                f"{format_count(before['files'])} -> {format_count(after['files'])} file(s), "
                f"{format_bytes(before['bytes'])} -> {format_bytes(after['bytes'])}"
            )
        lost = sum(
            max(0, entry["before"]["files"] - entry["after"]["files"])
            for entry in changed
        )
        note = (
            f"{dont_move_folder_name(context.config)} changed during the run"
            + (f" -- {format_count(lost)} file(s) fewer than at the start"
               if lost else " (nothing lost; files were added or grew)")
        )
        context.log(f"  ! {note}. The pipeline is not supposed to touch it.")
        context.add_stage_note(self.stage_id, note)

    def _scan(self, context: PipelineContext, output_roots: list[Path]):
        """List what has to be hashed, per root, before hashing any of it.

        The walk is cheap next to the hashing and it is what turns the bar into
        a percentage. The per-root breakdown is the answer to "why is this
        slow" -- it names the root holding the millions of files.
        """
        media_extensions = context.media_extensions()
        walk = context.progress(self.stage_id, "Scanning output roots", unit="files")
        candidates: list[tuple[Path, int]] = []
        zero_byte_files: list[Path] = []
        per_root = []
        # Excluded on both sides or on neither. Scanning `__DONT_MOVE` for
        # output would let a file parked there satisfy a lost input's checksum
        # -- a false pass, which is worse than the false failure it looks like
        # it is avoiding -- and would fail the run over a zero-byte file the
        # user deliberately keeps there. Its integrity is checked separately.
        protected = protected_intake_folders(context.config)
        # The output roots nest: READY and INBOX live *inside* root_folder in
        # the default layout, so walking all three visits those files two or
        # three times. Hashing them twice reads the same bytes twice and
        # proves nothing new, so each resolved path counts once, for the first
        # root that reaches it.
        seen: set[Path] = set()

        for root in output_roots:
            if not root.exists():
                context.log(f"  - {root}: does not exist, skipped")
                continue
            walk.set_activity("Scanning output roots", note=str(root))
            root_count, root_bytes = 0, 0
            for path in root.rglob("*"):
                if not path.is_file() or normalize_suffix(path.suffix) not in media_extensions:
                    continue
                if is_protected(path, protected):
                    continue
                try:
                    resolved = path.resolve()
                    size = path.stat().st_size
                except OSError:
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                if size == 0:
                    zero_byte_files.append(path)
                    continue
                candidates.append((path, size))
                root_count += 1
                root_bytes += size
                walk.advance()
            per_root.append((root, root_count, root_bytes))
        walk.finish()
        return candidates, zero_byte_files, per_root

    def _hash_all(self, context: PipelineContext, candidates, chunk_size: int,
                  expected: dict, total_bytes: int) -> set[str]:
        """Checksum everything, reporting throughput and what is still owed.

        The note carries the count still unaccounted for, so a run watching
        this stage can see the number fall to zero rather than only learning
        the verdict at the end.
        """
        reporter = context.progress(
            self.stage_id,
            "Checksumming archive",
            total=len(candidates),
            total_bytes=total_bytes,
        )
        found: set[str] = set()
        outstanding = len(expected)
        for path, size in candidates:
            md5 = file_md5(path, chunk_size)
            if md5 in expected and md5 not in found:
                outstanding -= 1
            found.add(md5)
            reporter.advance(
                size_bytes=size,
                note=f"{format_count(outstanding)} of this run's files still to find",
            )
        context.log(reporter.finish())
        return found

    def _output_roots(self, context: PipelineContext) -> list[Path]:
        paths = context.config.get("paths", {})
        configured = paths.get("output_roots")
        if configured:
            return [Path(path) for path in configured]
        return [
            Path(paths.get("root_folder", "")),
            Path(paths.get("ready_folder", "")),
            Path(paths.get("unsorted_folder", "")),
        ]


class NameCollisionResolver:
    """Which of two files claiming one name keeps it, and what the other is called.

    The three F4 suffixes are not interchangeable and this class is where the
    difference is decided. ``_DUPE`` is a claim of **byte-identity** — the loser
    adds nothing, and the checksum in its name is the proof. A file whose bytes
    differ is never a duplicate however alike the two look, so it takes
    ``_DIFFERS`` (a question for a person) or ``_LOWRES`` (a smaller rendering
    of the same shot).

    Naming a byte-different loser ``_DUPE`` was PS-10: two exposures a second
    apart were filed as copies of each other, and the hash on one of them said
    nothing about the other. Whether such a pair is two exposures at all is not
    decided here — ``pipeline_stages.siblings`` answers that (F9), before a
    collision that turns out to be no collision ever reaches this class.
    """

    def __init__(self, threshold: float = DEFAULT_COLLISION_THRESHOLD,
                 duplicate_suffix: str = "_DUPE",
                 low_res_suffix: str = "_LOWRES",
                 differing_suffix: str = "_DIFFERS"):
        self.threshold = threshold
        self.duplicate_suffix = duplicate_suffix
        self.low_res_suffix = low_res_suffix
        self.differing_suffix = differing_suffix

    @classmethod
    def from_context(cls, context: PipelineContext) -> "NameCollisionResolver":
        collision = context.config.get("collision", {})
        return cls(
            threshold=collision.get("significantly_smaller_ratio", DEFAULT_COLLISION_THRESHOLD),
            duplicate_suffix=collision.get("duplicate_suffix", "_DUPE"),
            low_res_suffix=collision.get("low_res_suffix", "_LOWRES"),
            differing_suffix=collision.get("differing_suffix", "_DIFFERS"),
        )

    def resolve(self, existing: str | Path, candidate: str | Path,
                context: PipelineContext | None = None, stage_id: str | None = None,
                existing_dimensions: tuple[int, int] | None = None,
                candidate_dimensions: tuple[int, int] | None = None) -> CollisionResult:
        existing = Path(existing)
        candidate = Path(candidate)
        existing_md5 = file_md5(existing) if existing.exists() else None
        candidate_md5 = file_md5(candidate) if candidate.exists() else None

        if existing_md5 and existing_md5 == candidate_md5:
            if context:
                context.register_safety_exception(candidate_md5, "Exact duplicate collision")
            return CollisionResult(
                decision=CollisionDecision.DISCARD_DUPLICATE,
                original=existing,
                duplicate=candidate,
                reason="identical-md5",
            )

        existing_stat = existing.stat()
        candidate_stat = candidate.stat()

        # "_LOWRES" is a claim about **resolution**, and only the pixel count
        # can support it. The byte ratio is kept as a first filter -- a
        # downscale is always much lighter -- but it decides nothing on its
        # own: two exposures of one scene can differ by more than half on
        # compressibility alone at identical dimensions, which is exactly how a
        # 4000x3000 photograph came to be filed as a low-resolution copy of a
        # different 4000x3000 photograph (PS-10). Equal or unknown dimensions
        # are never a downscale, so such a pair falls through to the rules
        # below and ends up a question rather than a false answer.
        smaller, larger = (
            (existing, candidate)
            if existing_stat.st_size < candidate_stat.st_size
            else (candidate, existing)
        )
        smaller_dimensions, larger_dimensions = (
            (existing_dimensions, candidate_dimensions)
            if smaller == existing
            else (candidate_dimensions, existing_dimensions)
        )
        smaller_size = min(existing_stat.st_size, candidate_stat.st_size)
        larger_size = max(existing_stat.st_size, candidate_stat.st_size)
        if (larger_size and smaller_size / larger_size < self.threshold
                and is_downscaled(larger_dimensions, smaller_dimensions)):
            # The **smaller** file is the one that carries _LOWRES, whichever
            # side of the collision it arrived on. Returning RENAME_CANDIDATE
            # unconditionally put the suffix on the incoming file even when the
            # incoming file was the full-resolution one, so the archive ended
            # up with a 7.4 MB original labelled a low-resolution copy of a
            # 2.0 MB file.
            return CollisionResult(
                decision=(CollisionDecision.RENAME_CANDIDATE if smaller == candidate
                          else CollisionDecision.KEEP_CANDIDATE),
                original=larger,
                duplicate=smaller,
                target_path=self._duplicate_path(smaller, self.low_res_suffix),
                reason="significantly-smaller",
            )

        # Past the identical-MD5 branch above, the two files provably differ.
        # Whichever loses the name is therefore a ``_DIFFERS``, never a
        # ``_DUPE``: it holds bytes the winner does not, and only a person can
        # say which was wanted (F4).
        if existing_stat.st_mtime <= candidate_stat.st_mtime and existing_stat.st_size >= candidate_stat.st_size:
            return CollisionResult(
                decision=CollisionDecision.RENAME_CANDIDATE,
                original=existing,
                duplicate=candidate,
                target_path=self._duplicate_path(candidate, self.differing_suffix),
                reason="existing-older-larger",
            )

        if candidate_stat.st_mtime <= existing_stat.st_mtime and candidate_stat.st_size >= existing_stat.st_size:
            return CollisionResult(
                decision=CollisionDecision.KEEP_CANDIDATE,
                original=candidate,
                duplicate=existing,
                target_path=self._duplicate_path(existing, self.differing_suffix),
                reason="candidate-older-larger",
            )

        prompt = None
        if context:
            prompt = context.create_prompt(
                "name_collision",
                {
                    "existing": self._path_payload(existing),
                    "candidate": self._path_payload(candidate),
                },
                stage_id=stage_id,
            )

        return CollisionResult(
            decision=CollisionDecision.PROMPT,
            prompt=prompt,
            reason="ambiguous",
        )

    def _duplicate_path(self, path: Path, suffix: str) -> Path:
        return path.with_name(f"{path.stem}{suffix}{path.suffix}")

    def _path_payload(self, path: Path) -> dict:
        stat = path.stat()
        return {
            "path": str(path),
            "size": stat.st_size,
            "modified_at": stat.st_mtime,
            "md5": file_md5(path),
        }
