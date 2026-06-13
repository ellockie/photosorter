from pathlib import Path

DEFAULT_TAXONOMY = {
    "to_share": "__2_SHARE",
    "stereo_3d": "__3D",
    "other": "___OTHER",
    "duplicates": "__DUPLICATES",
    "edited": "__EDITED",
    "exif": "__EXIF",
    "exported": "__EXPORTED",
    "extracted": "__EXTRACTED",
    "extracted_videos": "__EXTRACTED_VIDEOS",
    "geolocations": "__GEOLOCATIONS",
    "hashes": "__HASHES",
    "panoramas": "__PANORAMAS",
    "people": "__PEOPLE",
    "raw": "__RAW",
    "resized": "__RESIZED",
    "shared": "__SHARED",
    "videos": "__VIDEOS",
}

# These folders are only ever created/recognized by the pipeline; their
# contents are curated by hand and must never be populated automatically.
MANUALLY_CURATED_KEYS = ("to_share", "shared", "people", "panoramas", "stereo_3d", "other")

# Defined in the taxonomy but intentionally not generated yet.
FUTURE_KEYS = ("hashes", "extracted_videos")


def taxonomy_folder(config: dict, key: str) -> str:
    return config.get("taxonomy", {}).get(key, DEFAULT_TAXONOMY[key])


def taxonomy_subdir(event_folder: str | Path, config: dict, key: str) -> Path:
    return Path(event_folder) / taxonomy_folder(config, key)


def representative_suffixes(has_raw: bool = False, extracted_from_raw: bool = False,
                            has_edited: bool = False) -> str:
    suffixes = ""
    if has_raw:
        suffixes += "_RAW"
    if extracted_from_raw:
        suffixes += "_EXT"
    if has_edited:
        suffixes += "_EDT"
    return suffixes


def apply_representative_suffixes(file_name: str, has_raw: bool = False,
                                  extracted_from_raw: bool = False,
                                  has_edited: bool = False) -> str:
    path = Path(file_name)
    return path.stem + representative_suffixes(has_raw, extracted_from_raw, has_edited) + path.suffix
