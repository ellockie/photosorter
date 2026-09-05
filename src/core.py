import hashlib
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


def file_md5(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.md5()
    with Path(path).open("rb") as handler:
        while True:
            chunk = handler.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


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


def safe_move(source: str | Path, destination: str | Path, attempts=DEFAULT_RETRY_ATTEMPTS,
              delay_seconds=DEFAULT_RETRY_DELAY_SECONDS) -> Path:
    source = Path(source)
    destination = Path(destination)

    def operation():
        destination.parent.mkdir(parents=True, exist_ok=True)
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
    input_snapshot: dict[str, SafetySnapshotEntry] = field(default_factory=dict)
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
                        outputs: int | None = None, errors: int | None = None) -> None:
        with self.lock:
            stats = self.stage_stats.setdefault(stage_id, {})
            if inputs is not None:
                stats["inputs"] = inputs
            if outputs is not None:
                stats["outputs"] = outputs
            if errors is not None:
                stats["errors"] = errors

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

    def snapshot_inputs(self, roots: list[str | Path] | None = None) -> None:
        roots = roots or [self.config["paths"]["unsorted_folder"]]
        media_extensions = self.media_extensions()
        chunk_size = self.config.get("safety", {}).get("hash_chunk_size", 1024 * 1024)
        snapshot = {}

        for root in roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            for path in root_path.rglob("*"):
                if not path.is_file() or normalize_suffix(path.suffix) not in media_extensions:
                    continue
                md5 = file_md5(path, chunk_size)
                stat = path.stat()
                snapshot[md5] = SafetySnapshotEntry(
                    original_path=path,
                    size=stat.st_size,
                    modified_at=stat.st_mtime,
                    md5=md5,
                )

        with self.lock:
            self.input_snapshot = snapshot

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
                    "dependencies": list(stage.dependencies),
                    "headless": stage.headless,
                }
                for stage in self.ordered_stages()
            ]
        }

    def run(self, context: PipelineContext) -> PipelineContext:
        context.mode = self.mode
        ordered = self.ordered_stages()
        total = len(ordered)
        for index, stage in enumerate(ordered, start=1):
            context = self._run_stage(context, stage, index, total)
        return context

    def _run_stage(self, context: PipelineContext, stage: PipelineStage,
                   index: int, total: int) -> PipelineContext:
        """Run one stage between its two banners.

        The exit banner is emitted from a `finally`, so every path out of a
        stage — success, failure, pause, or an interrupt that no `except` here
        catches — is announced exactly once. A stage can never leave the
        transcript with an opening line and no closing one.
        """
        self.announce(format_start(index, total, stage.stage_id, stage.display_name))
        context.log(f"Stage: {stage.stage_id}")
        context.set_stage_state(stage.stage_id, PipelineState.ACTIVE)
        started = time.monotonic()
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
            self.announce(format_end(
                index, total, stage.stage_id, stage.display_name,
                outcome, time.monotonic() - started, detail,
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
    def __init__(self):
        super().__init__(
            stage_id="safety-validation",
            display_name="Safety Validation",
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not context.config.get("safety", {}).get("enabled", True):
            return context

        output_roots = self._output_roots(context)
        media_extensions = context.media_extensions()
        chunk_size = context.config.get("safety", {}).get("hash_chunk_size", 1024 * 1024)
        found = {}
        zero_byte_files = []

        for root in output_roots:
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if not path.is_file() or normalize_suffix(path.suffix) not in media_extensions:
                    continue
                if path.stat().st_size == 0:
                    zero_byte_files.append(path)
                    continue
                found.setdefault(file_md5(path, chunk_size), []).append(path)

        missing = []
        for md5, entry in context.input_snapshot.items():
            if md5 in context.safety_exceptions:
                continue
            if md5 not in found:
                missing.append(entry.original_path)

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

        return context

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
    def __init__(self, threshold: float = DEFAULT_COLLISION_THRESHOLD,
                 duplicate_suffix: str = "_DUPE",
                 low_res_suffix: str = "_LOWRES"):
        self.threshold = threshold
        self.duplicate_suffix = duplicate_suffix
        self.low_res_suffix = low_res_suffix

    @classmethod
    def from_context(cls, context: PipelineContext) -> "NameCollisionResolver":
        collision = context.config.get("collision", {})
        return cls(
            threshold=collision.get("significantly_smaller_ratio", DEFAULT_COLLISION_THRESHOLD),
            duplicate_suffix=collision.get("duplicate_suffix", "_DUPE"),
            low_res_suffix=collision.get("low_res_suffix", "_LOWRES"),
        )

    def resolve(self, existing: str | Path, candidate: str | Path,
                context: PipelineContext | None = None, stage_id: str | None = None) -> CollisionResult:
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

        smaller, larger = (
            (existing, candidate)
            if existing_stat.st_size < candidate_stat.st_size
            else (candidate, existing)
        )
        smaller_size = min(existing_stat.st_size, candidate_stat.st_size)
        larger_size = max(existing_stat.st_size, candidate_stat.st_size)
        if larger_size and smaller_size / larger_size < self.threshold:
            return CollisionResult(
                decision=CollisionDecision.RENAME_CANDIDATE,
                original=larger,
                duplicate=smaller,
                target_path=self._duplicate_path(smaller, self.low_res_suffix),
                reason="significantly-smaller",
            )

        if existing_stat.st_mtime <= candidate_stat.st_mtime and existing_stat.st_size >= candidate_stat.st_size:
            return CollisionResult(
                decision=CollisionDecision.RENAME_CANDIDATE,
                original=existing,
                duplicate=candidate,
                target_path=self._duplicate_path(candidate, self.duplicate_suffix),
                reason="existing-older-larger",
            )

        if candidate_stat.st_mtime <= existing_stat.st_mtime and candidate_stat.st_size >= existing_stat.st_size:
            return CollisionResult(
                decision=CollisionDecision.KEEP_CANDIDATE,
                original=candidate,
                duplicate=existing,
                target_path=self._duplicate_path(existing, self.duplicate_suffix),
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
