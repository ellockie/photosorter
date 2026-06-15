import datetime
from pathlib import Path

from src.constants.constants import \
    KNOWN_CAMERAS_SYMBOLS


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
    location = metadata.get("location_suffix")
    location_part = f"{location}__" if location else ""
    stem = (
        metadata["image_datetime"]
        + "__"
        + location_part
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


def reformat_exposure_time(value: str) -> str:
    return value.replace("/", "_")


def reformat_focal_length(value: str) -> str:
    if "equivalent" in value:
        parts = value.split("equivalent: ")
        value = parts[-1].replace(")", ".eq")
    return value.replace(" ", "").replace("mm", "")


def parse_exif_datetime(value: str) -> datetime.datetime:
    clean = value.split("+")[0].split("-")[0].strip()
    return datetime.datetime(
        int(clean[0:4]),
        int(clean[5:7]),
        int(clean[8:10]),
        int(clean[11:13]),
        int(clean[14:16]),
        int(clean[17:19]),
    )


def legacy_image_datetime(value: str) -> str:
    captured = parse_exif_datetime(value)
    return captured.strftime("%Y-%m-%d_(%a)_%H.%M.%S")


def camera_symbol_for_model(camera_name: str, config: dict) -> str:
    configured = config.get("camera_symbols", {})
    if camera_name in configured:
        return configured[camera_name]
    for known_name, symbol in KNOWN_CAMERAS_SYMBOLS:
        if known_name == camera_name:
            return symbol
    return configured.get("", "NOID")


def parse_legacy_exif_sidecar(path: Path, config: dict) -> dict:
    metadata = {}
    unformatted_datetime = None

    with Path(path).open(encoding="iso-8859-1") as exif_file:
        for line in exif_file:
            if ": " not in line:
                continue
            key, value = line.split(": ", 1)
            value = value.strip()
            if key.startswith("Camera Model Name"):
                metadata["camera_model"] = value
                metadata["camera_symbol"] = camera_symbol_for_model(value, config)
            elif key.startswith("File Modification Date/Time"):
                unformatted_datetime = value
            elif key.startswith("Date/Time Original"):
                unformatted_datetime = value
            elif key.startswith("Aperture"):
                metadata["aperture"] = "f" + value
            elif key.startswith("Exposure Time"):
                metadata["exposure_time"] = "T" + reformat_exposure_time(value)
            elif key.startswith("ISO  "):
                metadata["iso"] = "I" + value
            elif key.startswith("Focal Length"):
                metadata["focal_length"] = "L" + reformat_focal_length(value)

    if unformatted_datetime:
        metadata["captured_at"] = parse_exif_datetime(unformatted_datetime)
        metadata["image_datetime"] = legacy_image_datetime(unformatted_datetime)
    metadata.setdefault("aperture", "fNA")
    metadata.setdefault("exposure_time", "T---")
    metadata.setdefault("focal_length", "LNA")
    metadata.setdefault("iso", "I---s")
    metadata.setdefault("camera_symbol", "NOID")
    return metadata


def date_folder_datetime(captured_at: datetime.datetime, config: dict) -> datetime.datetime:
    if captured_at.time() <= day_boundary(config):
        return captured_at - datetime.timedelta(days=1)
    return captured_at


def legacy_date_folder_name(captured_at: datetime.datetime, config: dict,
                            label: str | None = None) -> str:
    folder_date = date_folder_datetime(captured_at, config)
    suffix = f" - {label}" if label else date_folder_suffix(config)
    return folder_date.strftime("%Y-%m-%d_(%a)") + suffix


def month_folder_name(captured_at: datetime.datetime, config: dict) -> str:
    folder_date = date_folder_datetime(captured_at, config)
    return MONTH_FOLDERS[folder_date.strftime("%m")]


def final_event_folder(captured_at: datetime.datetime, config: dict,
                       label: str | None = None) -> Path:
    root = Path(config["paths"]["root_folder"])
    folder_date = date_folder_datetime(captured_at, config)
    return root / folder_date.strftime("%Y") / month_folder_name(captured_at, config) / legacy_date_folder_name(captured_at, config, label)


def duplicate_name(stem: str, md5: str, index: int, extension: str) -> str:
    return f"{stem}_DUPE_{md5}_{index}{extension}"


def problematic_folder(config: dict, key: str) -> Path:
    return Path(config["paths"]["working_folder"]) / "__PROBLEMATIC" / subfolder_name(config, key)


def old_exif_folder(config: dict) -> Path:
    return Path(config["paths"]["working_folder"]) / "__PROBLEMATIC" / subfolder_name(config, "old_exif")
