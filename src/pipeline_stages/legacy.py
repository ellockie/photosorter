import datetime
from pathlib import Path

from src.constants.constants import \
    KNOWN_CAMERAS_SYMBOLS
from src.constants.months import MONTH_FOLDERS
from src.pipeline_stages.taxonomy import duplicate_name  # noqa: F401  (re-exported: F4 lives in taxonomy)
from src.pipeline_stages.siblings import \
    DIMENSIONS_METADATA_KEY, \
    SUBSECOND_EXIF_FIELD, \
    SUBSECOND_METADATA_KEY
from src.utils.dimensions import parse_exif_dimensions
from src.pipeline_stages.stamps import \
    format_day_prefix, \
    format_stamp, \
    normalise_subsecond




def legacy_settings(config: dict) -> dict:
    return config.get("legacy", {})


def raw_marker(config: dict) -> str:
    return legacy_settings(config).get("raw_marker", "RAW__")


DEFAULT_DAY_BOUNDARY_TIME = "04.44.44"


def day_boundary(config: dict) -> datetime.time:
    """The time before which a capture belongs to the previous day (N7).

    Top level first: this is a live rule the whole pipeline depends on, not a
    compatibility shim, so it does not belong in the "legacy" block beside the
    "##   RAWs   ##" folder names. That block is still read, so a config file
    written before the key moved keeps working.
    """
    value = config.get("day_boundary_time")
    if value is None:
        value = legacy_settings(config).get("day_boundary_time", DEFAULT_DAY_BOUNDARY_TIME)
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


AUTHOR_MARKER_PREFIX = "@"


def author_part(metadata: dict) -> str:
    """The trailing ``__@<AUTHOR>`` token, or "" for the archive owner.

    Written last, after the camera symbol, because the two together are the
    file's provenance and reading them side by side is the point. The "@" sigil
    makes the token self-identifying: a tool can tell an author from a camera
    symbol without consulting a table, which matters for a convention other
    people's tools have to implement.
    """
    symbol = metadata.get("author_symbol") or ""
    return f"__{AUTHOR_MARKER_PREFIX}{symbol}" if symbol else ""


def legacy_filename(metadata: dict, extension: str, config: dict) -> str:
    is_raw = is_raw_extension(extension, config)
    marker = raw_marker(config) if is_raw else ""
    location = metadata.get("location_suffix")
    location_part = f"{location}__" if location else ""
    # No sub-second here. The fraction is not part of a shot's name -- it is
    # what tells two shots in one second apart, so it is written only where
    # there are two (F9c), by the stage that can see the whole second's worth
    # of files. A lone shot keeps the plain second form.
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
        + author_part(metadata)
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
    return format_stamp(captured)


def camera_symbol_for_model(camera_name: str, config: dict) -> str:
    configured = config.get("camera_symbols", {})
    if camera_name in configured:
        return configured[camera_name]
    for known_name, symbol in KNOWN_CAMERAS_SYMBOLS:
        if known_name == camera_name:
            return symbol
    return configured.get("", "NOID")


# The archive owner's own media carries no author marker: absent means "mine".
# Anything else would rename every file already in the archive to say what its
# absence already said.
OWNER_AUTHOR_SYMBOL = ""


def author_symbol_for_name(author_name: str | None, config: dict) -> str | None:
    """The short symbol for a person, or None when the name is unknown.

    The mirror of ``camera_symbol_for_model``, and deliberately shaped the same
    way -- a small table in config, short symbols, one lookup -- because it
    answers the neighbouring question. The camera symbol says which *device*
    took a shot; two people shooting the same model are indistinguishable by it,
    which is exactly the case an author symbol exists for (standard G4/F8).

    There is no built-in table to match ``KNOWN_CAMERAS_SYMBOLS``: camera models
    are universal, the people in one person's archive are not.

    ``None`` for an unknown name rather than a silent fallback -- dropping the
    attribution would file someone else's photo as the owner's, which is the one
    outcome the marker exists to prevent.
    """
    configured = config.get("author_symbols", {})
    if not author_name:
        return configured.get("", OWNER_AUTHOR_SYMBOL)
    if author_name in configured:
        return configured[author_name]
    return None


def parse_legacy_exif_text(text: str, config: dict) -> dict:
    """Parse the human-readable ExifTool output used by legacy sidecars."""
    metadata = {}
    unformatted_datetime = None
    # Read whole rather than line by line: the dimension tags appear under
    # several group headings, and which heading a pair sits under is what
    # separates the picture's size from its embedded thumbnail's (F10).
    dimensions = parse_exif_dimensions(text)
    if dimensions is not None:
        metadata[DIMENSIONS_METADATA_KEY] = dimensions

    for line in text.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        value = value.strip()
        if key.startswith("Camera Model Name"):
            metadata["camera_model"] = value
            metadata["camera_symbol"] = camera_symbol_for_model(value, config)
        elif key.startswith("Artist"):
            # Some cameras carry the photographer's name. It is the one
            # source of authorship a file can supply about itself; anything
            # else has to come from where the batch was ingested from.
            # An unmapped name resolves to None and is left for a person
            # rather than silently filed as the owner's (G4/F8).
            metadata["author_name"] = value
            metadata["author_symbol"] = author_symbol_for_name(value, config)
        elif key.startswith("File Modification Date/Time"):
            unformatted_datetime = value
        elif key.startswith("Date/Time Original"):
            unformatted_datetime = value
        elif key.startswith(SUBSECOND_EXIF_FIELD):
            # The fraction of the second the shutter opened in. It is not part
            # of the name a shot is given -- F9 writes it only to separate two
            # exposures that landed in the same second -- but it is carried on
            # every asset, so the collision that needs it does not have to go
            # back to the sidecar to ask.
            metadata[SUBSECOND_METADATA_KEY] = normalise_subsecond(value)
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


def parse_legacy_exif_sidecar(path: Path, config: dict) -> dict:
    with Path(path).open(encoding="iso-8859-1") as exif_file:
        return parse_legacy_exif_text(exif_file.read(), config)


INTRINSIC_CAPTURE_TIME_FIELDS = (
    "Date/Time Original",
    "Media Create Date",
    "Track Create Date",
    "Create Date",
)


def intrinsic_capture_datetime_from_exif_text(text: str) -> datetime.datetime | None:
    """Return a camera/container capture time, never a filesystem timestamp.

    ExifTool's text output also contains ``File Modification Date/Time`` and
    similar system fields. Those are deliberately excluded: standard V4 says
    an undatable video must be routed for review, not assigned a plausible
    time from the filesystem.
    """
    values = {}
    for line in text.splitlines():
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        key = key.strip()
        if key in INTRINSIC_CAPTURE_TIME_FIELDS and key not in values:
            values[key] = value.strip()
    for key in INTRINSIC_CAPTURE_TIME_FIELDS:
        value = values.get(key)
        if not value or value.startswith("0000:00:00"):
            continue
        try:
            return parse_exif_datetime(value)
        except (ValueError, IndexError):
            continue
    return None


def date_folder_datetime(captured_at: datetime.datetime, config: dict) -> datetime.datetime:
    if captured_at.time() <= day_boundary(config):
        return captured_at - datetime.timedelta(days=1)
    return captured_at


def legacy_date_folder_name(captured_at: datetime.datetime, config: dict,
                            label: str | None = None) -> str:
    folder_date = date_folder_datetime(captured_at, config)
    suffix = f" - {label}" if label else date_folder_suffix(config)
    return format_day_prefix(folder_date) + suffix


def month_folder_name(captured_at: datetime.datetime, config: dict) -> str:
    folder_date = date_folder_datetime(captured_at, config)
    return MONTH_FOLDERS[folder_date.strftime("%m")]


def final_event_folder(captured_at: datetime.datetime, config: dict,
                       label: str | None = None) -> Path:
    root = Path(config["paths"]["root_folder"])
    folder_date = date_folder_datetime(captured_at, config)
    return root / folder_date.strftime("%Y") / month_folder_name(captured_at, config) / legacy_date_folder_name(captured_at, config, label)





def problematic_folder(config: dict, key: str) -> Path:
    return Path(config["paths"]["working_folder"]) / "__PROBLEMATIC" / subfolder_name(config, key)


def old_exif_folder(config: dict) -> Path:
    return Path(config["paths"]["working_folder"]) / "__PROBLEMATIC" / subfolder_name(config, "old_exif")
