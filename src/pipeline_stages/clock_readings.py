"""What each shot's sidecar says about its camera's clock -- read, never trusted.

The retime planner, the clock evidence report and the timezone visualiser all
need the same handful of facts about every shot in a dated folder, from its
``._exif`` sidecar (X1/X10): the raw reading, the camera, the shutter counter,
and what the camera *declared* its offset to be. One reader for all three (T8).

The declared offset is carried for reports only. Nothing that names a file may
use it: a camera's zone setting and its clock are set independently, and
nothing ties the one to the other.

Leaf module: standard library, ``stamps``, ``taxonomy`` and the camera-symbol
table only, so the maintenance tools load it on a bare interpreter.
"""

import dataclasses
import datetime
import json
import os
import re
from pathlib import Path

from src.constants.camera_symbols import \
    camera_symbol_for_model
from src.pipeline_stages.stamps import \
    split_dated_folder
from src.pipeline_stages.taxonomy import \
    sidecar_dir_names, \
    taxonomy_dir_names, \
    taxonomy_folder

SIDECAR_SUFFIX = "._exif"
SIDECAR_ENCODING = "iso-8859-1"
LOGS_FOLDER = "__LOGS"
YEAR_RE = re.compile(r"^\d{4}$")
# Counters in the order they are trusted: a body's own shutter count first,
# then what the file numbering says (Canon writes "100-1234": folder-number).
COUNTER_KEYS = ("Shutter Count", "Image Number", "File Number")
# Where a file names the device that made it. A still says it in "Camera Model
# Name"; a Sony video in "Device Model Name"; a Samsung phone video in "Author"
# (which on other files can be a person, so it counts only when it is a camera
# the symbol table knows).
CAMERA_MODEL_KEYS = ("Camera Model Name", "Device Model Name", "Author", "Android Model")
# A video's capture time (K11). QuickTime "Create Date" is UTC by the format's
# own definition; the device's wall-clock reading is that UTC plus the offset
# the device recorded with it -- Samsung's "Android Time Zone", Sony's "Time
# Zone" -- or a wall time carrying its own offset (Apple's "Creation Date",
# Sony's "Creation Date Value"). File times never are one (V4).
VIDEO_UTC_KEYS = ("Create Date", "Media Create Date", "Track Create Date")
VIDEO_OFFSET_KEYS = ("Android Time Zone", "Time Zone")
VIDEO_WALL_KEYS = ("Creation Date", "Creation Date Value")
FIELD_KEYS = ("Date/Time Original", "Sub Sec Time Original", "Offset Time Original",
              *CAMERA_MODEL_KEYS, *COUNTER_KEYS, *VIDEO_UTC_KEYS, *VIDEO_OFFSET_KEYS, *VIDEO_WALL_KEYS)
# Bumped whenever FIELD_KEYS changes, so a cache written for fewer fields is not trusted.
FIELDS_VERSION = 2
EXIF_DATETIME_RE = re.compile(r"^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})")
OFFSET_RE = re.compile(r"^([+-])(\d{2}):?(\d{2})$")
WALL_WITH_OFFSET_RE = re.compile(r"^(\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?(Z|[+-]\d{2}:?\d{2})$")


@dataclasses.dataclass(frozen=True)
class ShotReading:
    """One media file's clock facts, from its sidecar."""

    subject: Path                     # the media file the sidecar describes (may be gone)
    sidecar: Path
    folder: Path                      # the dated folder the subject belongs to
    subdir: str                       # "" at the folder's top level, else e.g. "__RAW"
    model: str | None
    camera: str
    reading: datetime.datetime | None
    subsecond: str | None
    declared_offset: str | None
    counter: int | None
    # A video whose device recorded no offset: its QuickTime time, in UTC, and
    # no wall reading. The engine decides what that means (a phone: the true
    # instant; a camera: most write their local time there).
    utc: datetime.datetime | None = None


def exposures(readings) -> list[ShotReading]:
    """One reading per exposure: a JPEG and its RAW share a counter and a second.

    The top-level file is kept over one in a subfolder, so a report names the
    representative a person would look for.
    """
    seen: dict = {}
    for shot in readings:
        if shot.reading is None and shot.utc is None:
            continue
        key = (shot.camera, shot.counter, shot.reading or shot.utc, shot.subsecond)
        if key not in seen or (seen[key].subdir and not shot.subdir):
            seen[key] = shot
    return list(seen.values())


def parse_clock_fields(text: str) -> dict:
    """The first value of each clock field in an ExifTool text sidecar.

    First, not last: a RAW sidecar repeats ``Date/Time Original`` for its
    embedded preview further down, with a fraction and an offset welded on.
    """
    found: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        key = key.strip()
        if key in FIELD_KEYS and key not in found:
            found[key] = value.strip()
    return found


def parse_exif_reading(value: str | None) -> datetime.datetime | None:
    match = EXIF_DATETIME_RE.match(value or "")
    if not match:
        return None
    try:
        return datetime.datetime(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def normalise_offset(value: str | None) -> str | None:
    """``+0200`` / ``+02:00`` -> ``+02:00``; anything else -> None."""
    match = OFFSET_RE.match((value or "").strip())
    return f"{match.group(1)}{match.group(2)}:{match.group(3)}" if match else None


def _offset_delta(text: str) -> datetime.timedelta:
    sign = -1 if text[0] == "-" else 1
    return sign * datetime.timedelta(hours=int(text[1:3]), minutes=int(text[4:6]))


def video_reading(fields: dict):
    """``(wall reading, declared offset, utc)`` of a video, from QuickTime fields (K11).

    The wall reading is what the device's own clock showed, the same thing a
    still's ``Date/Time Original`` is, so the clock model treats both alike.
    With no offset recorded there is no wall reading, only the UTC time.
    """
    utc = next((value for value in (parse_exif_reading(fields.get(key)) for key in VIDEO_UTC_KEYS)
                if value is not None), None)
    for key in VIDEO_WALL_KEYS:
        match = WALL_WITH_OFFSET_RE.match((fields.get(key) or "").strip())
        if match and match.group(2) != "Z":
            return parse_exif_reading(match.group(1)), normalise_offset(match.group(2)), utc
    for key in VIDEO_OFFSET_KEYS:
        offset = normalise_offset(fields.get(key))
        if offset is not None and utc is not None:
            return utc + _offset_delta(offset), offset, utc
    return None, None, utc


def camera_from_fields(fields: dict, config: dict) -> tuple[str | None, str]:
    """``(model, symbol)``: the first model field naming a camera the table knows."""
    unknown = camera_symbol_for_model("", config)
    first = None
    for key in CAMERA_MODEL_KEYS:
        value = (fields.get(key) or "").strip()
        if not value:
            continue
        symbol = camera_symbol_for_model(value, config)
        if symbol != unknown or key == "Camera Model Name":
            return value, symbol
        first = first or value
    return first, unknown


def parse_counter(value: str | None) -> int | None:
    digits = re.sub(r"\D", "", value or "")
    return int(digits) if digits else None


def reading_from_fields(fields: dict, config: dict) -> dict:
    counter = None
    for key in COUNTER_KEYS:
        counter = parse_counter(fields.get(key))
        if counter is not None:
            break
    model, camera = camera_from_fields(fields, config)
    subsecond = (fields.get("Sub Sec Time Original") or "").strip()
    reading = parse_exif_reading(fields.get("Date/Time Original"))
    declared = fields.get("Offset Time Original") or None
    utc = None
    if reading is None:
        reading, declared, utc = video_reading(fields)
        if reading is not None:
            utc = None
    return {
        "model": model,
        "camera": camera,
        "reading": reading,
        "subsecond": subsecond if subsecond.isdigit() else None,
        "declared_offset": declared,
        "counter": counter,
        "utc": utc,
    }


class SidecarCache:
    """Parsed sidecar fields keyed by path, size and mtime, kept outside the archive.

    A NAS holds tens of thousands of sidecars; re-reading every one over the
    network for each view is what makes a view of the whole archive unusable.
    A sidecar that changes size or mtime is simply read again.
    """

    def __init__(self, path: Path | None):
        self.path = path
        self.entries: dict[str, list] = {}
        self.dirty = False
        if path is not None and path.exists():
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                stored = {}
            if isinstance(stored, dict) and stored.get("version") == FIELDS_VERSION:
                self.entries = stored.get("entries", {})

    def fields(self, sidecar: Path) -> dict | None:
        try:
            stat = sidecar.stat()
        except OSError:
            return None
        key = str(sidecar)
        cached = self.entries.get(key)
        if cached and cached[0] == stat.st_size and cached[1] == stat.st_mtime:
            return cached[2]
        try:
            text = sidecar.read_text(encoding=SIDECAR_ENCODING, errors="replace")
        except OSError:
            return None
        fields = parse_clock_fields(text)
        self.entries[key] = [stat.st_size, stat.st_mtime, fields]
        self.dirty = True
        return fields

    def save(self) -> None:
        if self.path is None or not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"version": FIELDS_VERSION, "entries": self.entries}), encoding="utf-8")
        os.replace(temporary, self.path)
        self.dirty = False


def cache_path_for(root: Path, cache_dir: Path | None = None) -> Path:
    """Where a root's sidecar cache lives: per user, never inside the archive."""
    base = cache_dir or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "photosorter" / "clock_cache"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", str(root)).strip("_") or "root"
    return base / f"{safe}.json"


def subject_dirs(folder: Path, config: dict) -> list[tuple[str, Path]]:
    """``(subdir, path)`` of every place in a dated folder that holds subjects.

    The folder itself and its non-sidecar taxonomy subfolders (``__RAW``,
    ``__EDITED`` ...); a subject's sidecar sits in ``__EXIF`` directly inside
    whichever of these holds it (X10).
    """
    found = [("", folder)]
    sidecars = sidecar_dir_names(config)
    taxonomy = taxonomy_dir_names(config)
    try:
        children = sorted(folder.iterdir())
    except OSError:
        return found
    for child in children:
        if child.is_dir() and child.name in taxonomy and child.name not in sidecars:
            found.append((child.name, child))
    return found


def folder_readings(folder: Path, config: dict, cache: SidecarCache | None = None) -> list[ShotReading]:
    """Every shot in one dated folder (its dated children not included)."""
    readings = []
    exif = taxonomy_folder(config, "exif")
    cache = cache or SidecarCache(None)
    for subdir, place in subject_dirs(folder, config):
        sidecar_dir = place / exif
        if not sidecar_dir.is_dir():
            continue
        for sidecar in sorted(sidecar_dir.iterdir()):
            if not sidecar.name.endswith(SIDECAR_SUFFIX) or not sidecar.is_file():
                continue
            fields = cache.fields(sidecar)
            if fields is None:
                continue
            subject = place / sidecar.name[:-len(SIDECAR_SUFFIX)]
            readings.append(ShotReading(subject, sidecar, folder, subdir, **reading_from_fields(fields, config)))
    return readings


def walk_dated_folders(root: Path, config: dict, years=None):
    """``(depth, folder)`` for every dated folder under ``root``'s year trees.

    Depth 1 is a folder directly in a month folder; a group's children are 2,
    theirs 3, and so on. Taxonomy folders, ``__LOGS`` and anything a dated
    folder does not open with are not descended into.
    """
    taxonomy = taxonomy_dir_names(config)
    try:
        year_folders = sorted(p for p in root.iterdir() if p.is_dir() and YEAR_RE.match(p.name))
    except OSError:
        return
    for year in year_folders:
        if years and year.name not in {str(value) for value in years}:
            continue
        for month in sorted(p for p in year.iterdir() if p.is_dir() and p.name != LOGS_FOLDER):
            yield from _walk_level(month, 1, taxonomy)


def _walk_level(parent: Path, depth: int, taxonomy: set):
    try:
        children = sorted(p for p in parent.iterdir() if p.is_dir())
    except OSError:
        return
    for child in children:
        if child.name in taxonomy or child.name.startswith("__"):
            continue
        if split_dated_folder(child.name) is None:
            continue
        yield depth, child
        yield from _walk_level(child, depth + 1, taxonomy)


class MergedFolder:
    """One dated folder, possibly present under several roots."""

    def __init__(self, relative: Path, depth: int):
        self.relative = relative
        self.depth = depth
        self.copies: dict[int, Path] = {}   # root index -> folder
        self.readings = []                  # merged: first root holding a subject wins

    @property
    def name(self) -> str:
        return self.relative.name

    def root_tags(self, letters) -> str:
        return "+".join(letters[index] for index in sorted(self.copies))


def scan_roots(roots, config, years=None, use_cache=True, progress=None, cache_dir=None) -> list["MergedFolder"]:
    """Every dated folder under every root, merged by path relative to its root."""
    merged: dict[Path, MergedFolder] = {}
    for index, root in enumerate(roots):
        if not root.exists():
            if progress:
                progress(f"root not reachable, skipped: {root}")
            continue
        cache = SidecarCache(cache_path_for(root, cache_dir) if use_cache else None)
        count = 0
        for depth, folder in walk_dated_folders(root, config, years):
            relative = folder.relative_to(root)
            entry = merged.setdefault(relative, MergedFolder(relative, depth))
            entry.copies[index] = folder
            known = {(shot.subdir, shot.subject.name) for shot in entry.readings}
            for shot in folder_readings(folder, config, cache):
                if (shot.subdir, shot.subject.name) not in known:
                    entry.readings.append(shot)
            count += 1
            if progress and count % 200 == 0:
                progress(f"{root}: {count} folders read")
                cache.save()
        cache.save()
    return sorted(merged.values(), key=lambda entry: [part.casefold() for part in entry.relative.parts])


def in_range(shot, start, end) -> bool:
    moment = shot.reading or shot.utc
    if moment is None:
        return False
    if start is not None and moment < start:
        return False
    if end is not None and moment >= end + datetime.timedelta(days=1):
        return False
    return True
