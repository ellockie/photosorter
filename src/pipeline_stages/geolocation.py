"""Derived geolocation projection (design.md Decision 9).

The location timeline is the single source of truth; an event folder cannot own
the trip definition because a trip spans many folders. Each event folder instead
receives a *projection* — a small ``_location.json`` stamp in its
``__GEOLOCATIONS`` subfolder — giving every photo a coarse zone/place even with
no GPS hardware. Real GPX tracks (routed separately) enrich it where present.
"""

import json
from pathlib import Path

from src.pipeline_stages.taxonomy import taxonomy_subdir

LOCATION_STAMP_NAME = "_location.json"


def location_info(metadata: dict) -> dict | None:
    """Extract the derived-geolocation fields an asset carries, or None.

    The event-folder label and the geolocation label are the same value
    (``location_suffix``); a zone with no trip label still stamps the folder.
    """
    info = {}
    if metadata.get("location_zone"):
        info["zone"] = metadata["location_zone"]
    if metadata.get("location_suffix"):
        info["label"] = metadata["location_suffix"]
    if metadata.get("location_coords"):
        info["coords"] = metadata["location_coords"]
    return info or None


def write_location_stamp(event_folder: str | Path, config: dict, info: dict) -> Path | None:
    """Write/refresh the derived ``_location.json`` for an event folder."""
    if not info:
        return None
    geo_folder = taxonomy_subdir(event_folder, config, "geolocations")
    geo_folder.mkdir(parents=True, exist_ok=True)
    stamp = {
        "zone": info.get("zone"),
        "label": info.get("label"),
        "coords": info.get("coords"),
        "derived_from": "locations timeline",
    }
    target = geo_folder / LOCATION_STAMP_NAME
    target.write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    return target
