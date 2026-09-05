"""The event-folder subfolder taxonomy — defined here and nowhere else.

``ARCHIVE_STANDARD.md`` section 4 is the specification; this module is its one
implementation (rule T8/S4). Nothing else in the project may spell a taxonomy
folder name as a string literal: ``default_config()`` deliberately writes no
``taxonomy`` block, so ``taxonomy_folder`` falls through to ``DEFAULT_TAXONOMY``
here unless a config file overrides a key on purpose.

Like ``stamps.py`` and ``grouping_names.py`` this is a **leaf module** — it
imports nothing from the project, so a maintenance tool can load it by file path
without dragging exiftool, the dashboard and the converters in behind it.

Videos are not in the taxonomy. A video that can be dated from its own metadata
is a representative and sits at the top level of the event folder beside the
stills (standard V1); only videos still awaiting a name are parked in a subfolder.
``__VIDEOS`` and ``__EXTRACTED_VIDEOS`` were the earlier arrangement and survive
in ``LEGACY_TAXONOMY`` — read, never written, so an existing archive keeps
working and companion reconciliation can still drain the old folders.
"""

import re
from pathlib import Path

DEFAULT_TAXONOMY = {
    "to_share": "__TO_SHARE",
    "stereo_3d": "__3D",
    "other": "___OTHER",
    "duplicates": "__DUPLICATES",
    "edited": "__EDITED",
    "exif": "__EXIF",
    "exported": "__EXPORTED",
    "raw_extracted_jpgs": "__RAW_EXTRACTED_JPGS",
    "geolocations": "__GEOLOCATIONS",
    "hashes": "__HASHES",
    "ocr": "__OCR",
    "panoramas": "__PANORAMAS",
    "people": "__PEOPLE",
    "previews": "__PREVIEWS",
    "processed": "__PROCESSED",
    "raw": "__RAW",
    "resized": "__RESIZED",
    "shared": "__SHARED",
    "videos_extracted": "__VIDEOS_EXTRACTED",
    "videos_to_rename": "__VIDEOS_TO_RENAME",
}

# Written by an earlier version of the pipeline. Recognised wherever the
# question is "is this a taxonomy folder?" -- so an existing archive is not
# reported as malformed and its companions can still be reunited -- but never
# produced by anything new. The mirror of the historical name forms in
# stamps.py: read the old shapes, write only the current one.
LEGACY_TAXONOMY = {
    "videos": "__VIDEOS",
    "extracted_videos": "__EXTRACTED_VIDEOS",
    "extracted": "__EXTRACTED",
    "to_share_old": "__2_SHARE",
}

# The containers the legacy CLI wrote, before every subfolder gained its "__"
# prefix, and the taxonomy key each one's contents belong under now. Mirrors
# config.json "legacy.subfolders"; that block may rename them, so read through
# ``legacy_container_targets`` rather than using this directly.
#
# Only these two carry a mapping. The rest are recognised so a walk does not
# report them as unknown folders, but nothing moves their contents: an
# "old_EXIF" holds sidecars already judged stale, and the three "FILES"
# containers hold whatever the legacy run could not classify. Where those
# belong is a decision for a person.
DEFAULT_LEGACY_CONTAINERS = {
    "raw": "##   RAWs   ##",
    "exif": "##   EXIFs   ##",
}

DEFAULT_LEGACY_CONTAINERS_UNMAPPED = (
    "old_EXIF",
    "##   UNSUPPORTED EXTENSIONS   ##",
    "##   EMPTY FILES   ##",
    "##   NOT_ENOUGH_INFO FILES   ##",
    "##   DUPLICATE_FILE_NAMES FILES   ##",
)


def legacy_container_targets(config: dict) -> dict[str, str]:
    """``{folder name on disk: taxonomy key its contents belong under}``.

    The migration map: what a legacy container is called, and where what is
    inside it goes. Config may rename either side, so both halves are read.
    """
    names = (config.get("legacy") or {}).get("subfolders") or {}
    return {
        names.get(key, default): key
        for key, default in DEFAULT_LEGACY_CONTAINERS.items()
    }


def legacy_container_names(config: dict) -> set[str]:
    """Every legacy container name, mapped or not.

    A walk uses this to tell "an old folder still to migrate" from "a folder
    nobody recognises" -- the first is expected in an archive this old, the
    second is worth reporting.
    """
    names = (config.get("legacy") or {}).get("subfolders") or {}
    found = set(legacy_container_targets(config))
    for default in DEFAULT_LEGACY_CONTAINERS_UNMAPPED:
        found.add(default)
    found.update(str(value) for value in names.values())
    return found


# The subfolders that hold a *subject's* companions rather than media of their
# own. A sidecar lives in one of these directly inside the folder holding its
# subject (standard X10), so unlike every other taxonomy folder these may nest
# one level inside another -- "__RAW\__EXIF\" is the RAW's sidecar, and is legal
# where "__RAW\__EDITED\" is not (S2, X11, X12).
SIDECAR_KEYS = ("exif", "previews", "ocr")

# These folders are only ever created/recognized by the pipeline; their
# contents are curated by hand and must never be populated automatically.
MANUALLY_CURATED_KEYS = ("to_share", "shared", "people", "panoramas", "stereo_3d",
                         "other", "processed")

# Defined in the taxonomy but intentionally not generated yet.
FUTURE_KEYS = ("hashes", "videos_extracted", "videos_to_rename")


def taxonomy_folder(config: dict, key: str) -> str:
    return config.get("taxonomy", {}).get(key, DEFAULT_TAXONOMY[key])


def taxonomy_subdir(event_folder: str | Path, config: dict, key: str) -> Path:
    return Path(event_folder) / taxonomy_folder(config, key)


def taxonomy_dir_names(config: dict) -> set[str]:
    """Every directory name that counts as a taxonomy subfolder.

    Current names, whatever a config overrides them to, and the legacy names --
    a stage asking this is asking "may I skip/drain this directory?", and the
    answer for ``__VIDEOS`` in an archive written last year is yes.
    """
    names = set(DEFAULT_TAXONOMY.values())
    names.update(LEGACY_TAXONOMY.values())
    names.update((config.get("taxonomy") or {}).values())
    return names


def sidecar_dir_names(config: dict) -> set[str]:
    """The subfolder names that hold companions rather than media (X10)."""
    return {taxonomy_folder(config, key) for key in SIDECAR_KEYS}


def sidecar_subdir(subject_folder: str | Path, config: dict, key: str = "exif") -> Path:
    """Where a file living in ``subject_folder`` keeps its sidecars.

    X10: directly inside the folder that holds the subject, never in an
    ``__EXIF`` further up. A still at the top level of an event folder uses that
    folder's ``__EXIF``; a RAW in ``__RAW`` uses ``__RAW\\__EXIF``. Locality is
    what makes moving a folder carry its sidecars instead of stranding them.
    """
    return taxonomy_subdir(subject_folder, config, key)


# Suffixes a representative carries to announce what its subfolders hold, so
# the top level alone tells you how a shot was taken and what else exists.
#
#   (none)      a JPG-only shot: what the camera wrote is all there is
#   _HAS_RAW    straight from the camera, and a RAW original sits in __RAW
#   _FROM_RAW   extracted from a RAW because the shot had no camera JPG
#   _HAS_EDIT   a better version sits in __EDITED
#
# "HAS" names a sibling that exists elsewhere; "FROM" names this file's own
# provenance. The pair is what the old vocabulary got wrong: "_RAW" on a
# camera JPG read as "this is a raw" -- the sense "RAW__" carries inside a
# filename -- when it meant "a raw exists". _HAS_RAW and _FROM_RAW cannot be
# misread for each other, and they are mutually exclusive by construction:
# _FROM_RAW already says a RAW exists.
# Collision suffixes (standard F4). A file that lost a name collision keeps its
# own name and says so, carrying the checksum that identified it so the pair can
# be matched up again by eye.
#
#   _DUPE_<md5>_<n>     byte-identical to the file already holding the name
#   _DIFFERS_<md5>_<n>  same name, different bytes -- the case that needs a human
#
# "_DIFFERS" is the newer of the two: F4 names only "_DUPE" and "_LOWRES",
# because until companion placement went archive-wide there was nowhere for two
# sidecars of one subject to meet.
DUPLICATE_SUFFIX = "_DUPE"
DIFFERING_SUFFIX = "_DIFFERS"


def duplicate_name(stem: str, md5: str, index: int, extension: str) -> str:
    """``photo_DUPE_abcd_2.jpg`` -- F4's name for a byte-identical loser."""
    return f"{stem}{DUPLICATE_SUFFIX}_{md5}_{index}{extension}"


def differing_name(stem: str, md5: str, index: int, extension: str) -> str:
    """``photo_DIFFERS_abcd_2.jpg`` -- same name, different bytes."""
    return f"{stem}{DIFFERING_SUFFIX}_{md5}_{index}{extension}"


SUFFIX_HAS_RAW = "_HAS_RAW"
SUFFIX_FROM_RAW = "_FROM_RAW"
SUFFIX_HAS_EDIT = "_HAS_EDIT"

# Written by an earlier version: "_RAW" (has raw), "_EXT" (extracted),
# "_EDT" (has edit). Read so an existing archive keeps matching -- the same
# read-old/write-new rule as the timestamp forms (N5) and LEGACY_TAXONOMY.
LEGACY_SUFFIXES = ("_RAW", "_EXT", "_EDT")

# Every suffix, current and legacy, at the end of a stem. Longest alternatives
# first so "_HAS_RAW" is not clipped to "_RAW". One definition: matching these
# was previously a second regex inside companion_reconciliation.py.
REPRESENTATIVE_SUFFIX_RE = re.compile(
    r"(?:_(?:HAS_RAW|FROM_RAW|HAS_EDIT|RAW|EXT|EDT))+$"
)


def representative_suffixes(has_raw: bool = False, extracted_from_raw: bool = False,
                            has_edited: bool = False) -> str:
    suffixes = ""
    if extracted_from_raw:
        # Implies the RAW it came from, so never both.
        suffixes += SUFFIX_FROM_RAW
    elif has_raw:
        suffixes += SUFFIX_HAS_RAW
    if has_edited:
        suffixes += SUFFIX_HAS_EDIT
    return suffixes


def apply_representative_suffixes(file_name: str, has_raw: bool = False,
                                  extracted_from_raw: bool = False,
                                  has_edited: bool = False) -> str:
    path = Path(file_name)
    return path.stem + representative_suffixes(has_raw, extracted_from_raw, has_edited) + path.suffix


def strip_representative_suffixes(stem: str) -> str:
    """A stem with any trailing representative suffixes removed."""
    return REPRESENTATIVE_SUFFIX_RE.sub("", stem)
