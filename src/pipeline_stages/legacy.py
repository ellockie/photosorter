import datetime
from pathlib import Path


MONTH_FOLDERS = {
    "01": "01. January",
    "02": "02. February",
    "03": "03. March",
    "04": "04. April",
    "05": "05. May",
    "06": "06. June",
    "07": "07. July",
    "08": "08. August",
    "09": "09. September",
    "10": "10. October",
    "11": "11. November",
    "12": "12. December",
}


def legacy_settings(config: dict) -> dict:
    return config.get("legacy", {})


def raw_marker(config: dict) -> str:
    return legacy_settings(config).get("raw_marker", "RAW__")


def day_boundary(config: dict) -> datetime.time:
    value = legacy_settings(config).get("day_boundary_time", "04.44.44")
    hour, minute, second = [int(part) for part in value.split(".")]
    return datetime.time(hour, minute, second)


def date_folder_suffix(config: dict) -> str:
    return legacy_settings(config).get("date_folder_suffix", " - 1. ######")


def subfolder_name(config: dict, key: str) -> str:
    defaults = {
        "raw": "##   RAWs   ##",
        "exif": "##   EXIFs   ##",
        "unsupported": "##   UNSUPPORTED EXTENSIONS   ##",
        "empty": "##   EMPTY FILES   ##",
        "not_enough_info": "##   NOT_ENOUGH_INFO FILES   ##",
        "duplicate_file_names": "##   DUPLICATE_FILE_NAMES FILES   ##",
        "old_exif": "old_EXIF",
    }
    return legacy_settings(config).get("subfolders", {}).get(key, defaults[key])


def is_raw_extension(extension: str, config: dict) -> bool:
    raw_extensions = {
        value.lower()
        for value in config.get("extensions", {}).get("raw_images", [])
    }
    return extension.lower() in raw_extensions


def format_extension(extension: str, config: dict) -> str:
    return extension.upper() if is_raw_extension(extension, config) else extension.lower()


def legacy_filename(metadata: dict, extension: str, config: dict) -> str:
    is_raw = is_raw_extension(extension, config)
    marker = raw_marker(config) if is_raw else ""
    stem = (
        metadata["image_datetime"]
        + "__"
        + marker
        + metadata.get("aperture", "fNA")
        + "__"
        + metadata.get("exposure_time", "T---")
        + "__"
        + metadata.get("focal_length", "LNA")
        + "__"
        + metadata.get("iso", "INA")
        + "__"
        + metadata.get("camera_symbol", "NOID")
    )
    return stem + format_extension(extension, config)


def date_folder_datetime(captured_at: datetime.datetime, config: dict) -> datetime.datetime:
    if captured_at.time() <= day_boundary(config):
        return captured_at - datetime.timedelta(days=1)
    return captured_at


def legacy_date_folder_name(captured_at: datetime.datetime, config: dict) -> str:
    folder_date = date_folder_datetime(captured_at, config)
    return folder_date.strftime("%Y-%m-%d_(%a)") + date_folder_suffix(config)


def month_folder_name(captured_at: datetime.datetime, config: dict) -> str:
    folder_date = date_folder_datetime(captured_at, config)
    return MONTH_FOLDERS[folder_date.strftime("%m")]


def final_event_folder(captured_at: datetime.datetime, config: dict) -> Path:
    root = Path(config["paths"]["root_folder"])
    folder_date = date_folder_datetime(captured_at, config)
    return root / folder_date.strftime("%Y") / month_folder_name(captured_at, config) / legacy_date_folder_name(captured_at, config)


def duplicate_name(stem: str, md5: str, index: int, extension: str) -> str:
    return f"{stem}_DUPE_{md5}_{index}{extension}"


def problematic_folder(config: dict, key: str) -> Path:
    return Path(config["paths"]["working_folder"]) / "__PROBLEMATIC" / subfolder_name(config, key)


def old_exif_folder(config: dict) -> Path:
    return Path(config["paths"]["working_folder"]) / "__PROBLEMATIC" / subfolder_name(config, "old_exif")


def apply_camera_clock_corrections(captured_at: datetime.datetime, camera_symbol: str, config: dict) -> datetime.datetime:
    corrected = captured_at
    for correction in config.get("camera_clock_corrections", []):
        if correction.get("camera_symbol") != camera_symbol:
            continue
        start = datetime.datetime.fromisoformat(correction["from_date"])
        end = datetime.datetime.fromisoformat(correction["to_date"])
        if start <= corrected <= end:
            corrected += datetime.timedelta(seconds=int(correction.get("offset_seconds", 0)))
    return corrected


def apply_trip_timezone(captured_at: datetime.datetime, config: dict) -> tuple[datetime.datetime, str | None]:
    for trip in config.get("trips", []):
        start = datetime.datetime.fromisoformat(trip["start"])
        end = datetime.datetime.fromisoformat(trip["end"])
        if start <= captured_at <= end:
            offset = datetime.timedelta(hours=float(trip.get("timezone_offset_hours", 0)))
            return captured_at + offset, trip.get("location_suffix")
    return captured_at, None
