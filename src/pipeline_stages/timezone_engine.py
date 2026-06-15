"""Two-timeline timezone & travel engine (design.md Decision 9).

Two independent timelines drive every correction:

* LOCATION timeline (`config["locations"]`) — where the photographer physically
  was. Determines the DISPLAY zone, the event-folder label suffix, and
  geolocation. A breakpoint is the moment a new zone was entered.
* CAMERA-CLOCK timeline (`config["camera_clock_sets"]`, per camera) — what each
  camera's clock was set to. Determines how a raw reading becomes a true
  instant. A breakpoint is the moment that camera was physically adjusted.

They meet at the TRUE INSTANT:

    reading + camera-clock timeline -> true instant -> location timeline -> display

Zones are named IANA zones resolved through stdlib ``zoneinfo`` (no third-party
dependency); offsets are always *derived*, never typed. DST is therefore an
ordinary camera-clock breakpoint, not a special case.
"""

import datetime
import logging
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Photo-grammar timestamp, e.g. ``2026-04-12_(Sun)_18.00.00``. The weekday is
# decorative; only the numeric fields are parsed so a wrong day name never
# rejects an otherwise valid stamp.
_PHOTO_STAMP = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})_\([A-Za-z]{3}\)_(\d{2})\.(\d{2})\.(\d{2})"
)

UTC = datetime.timezone.utc


def parse_stamp(value) -> datetime.datetime:
    """Parse a timestamp in the photo grammar, with ISO-8601 as a fallback.

    Returns a naive ``datetime`` (wall-clock reading, no zone attached).
    """
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    match = _PHOTO_STAMP.search(text)
    if match:
        year, month, day, hour, minute, second = (int(part) for part in match.groups())
        return datetime.datetime(year, month, day, hour, minute, second)
    return datetime.datetime.fromisoformat(text).replace(tzinfo=None)


def format_stamp(value: datetime.datetime) -> str:
    """Render a naive datetime back into the photo grammar."""
    return value.strftime("%Y-%m-%d_(%a)_%H.%M.%S")


def resolve_zone(config: dict, name: str | None) -> ZoneInfo | None:
    """Resolve a zone alias or raw IANA name to a ``ZoneInfo``.

    ``config["zones"]`` is a small user-curated alias map (e.g. ``"JP" ->
    "Asia/Tokyo"``) so timezones can be picked without typing long strings; an
    unmapped name is treated as a raw IANA name.
    """
    if not name:
        return None
    iana = config.get("zones", {}).get(name, name)
    try:
        return ZoneInfo(iana)
    except (ZoneInfoNotFoundError, ValueError, ModuleNotFoundError):
        logger.warning("Unknown timezone %r (resolved to %r)", name, iana)
        return None


def home_zone_name(config: dict) -> str | None:
    """The baseline zone cameras sit on by default — the earliest location era.

    There is deliberately no ``home`` constant; "home" is simply the first entry
    on the location timeline (which may itself differ across eras).
    """
    locations = config.get("locations", [])
    if not locations:
        return None
    earliest = min(locations, key=lambda entry: parse_stamp(entry["since"]))
    return earliest.get("zone")


def _offset_at(zone: ZoneInfo, naive_wall: datetime.datetime) -> datetime.timedelta:
    return naive_wall.replace(tzinfo=zone).utcoffset() or datetime.timedelta(0)


def camera_zone_name_at(config: dict, camera: str, reading: datetime.datetime) -> str | None:
    """Which zone camera ``camera`` was set to at the given raw ``reading``.

    Sets are indexed in *reading space* (the values the camera displays), so the
    naive reading is compared directly against each ``at_reading``. A camera with
    no set in scope falls back to the home zone — i.e. it was never adjusted, so
    the whole window is one lag gap.
    """
    candidates = [
        entry for entry in config.get("camera_clock_sets", [])
        if entry.get("camera") == camera and parse_stamp(entry["at_reading"]) <= reading
    ]
    if not candidates:
        return home_zone_name(config)
    latest = max(candidates, key=lambda entry: parse_stamp(entry["at_reading"]))
    return latest.get("set_to")


def is_ambiguous_reading(config: dict, camera: str, reading: datetime.datetime) -> bool:
    """Whether a reading falls in a backward-jump overlap (repeated hour).

    When a camera is adjusted *backward* (flying west, or autumn fall-back) the
    clock jumps back, so the same wall-clock value exists on both sides of the
    adjustment. Such readings are resolved to the post-adjustment interval by
    default (see ``camera_zone_name_at``); this flags them so the straggler set
    can be surfaced for optional hand-nudging rather than guessed silently.
    """
    sets = sorted(
        (e for e in config.get("camera_clock_sets", []) if e.get("camera") == camera),
        key=lambda item: parse_stamp(item["at_reading"]),
    )
    home = resolve_zone(config, home_zone_name(config))
    for index, entry in enumerate(sets):
        at_reading = parse_stamp(entry["at_reading"])
        zone = resolve_zone(config, entry.get("set_to"))
        if zone is None:
            continue
        new_offset = _offset_at(zone, at_reading)
        if index == 0:
            prev_offset = _offset_at(home, at_reading) if home else datetime.timedelta(0)
        else:
            prev_zone = resolve_zone(config, sets[index - 1].get("set_to"))
            prev_offset = _offset_at(prev_zone, parse_stamp(sets[index - 1]["at_reading"])) if prev_zone else datetime.timedelta(0)
        jump = new_offset - prev_offset
        if jump < datetime.timedelta(0) and at_reading <= reading < at_reading - jump:
            return True
    return False


def camera_offset_at(config: dict, camera: str, reading: datetime.datetime) -> datetime.timedelta:
    """The *fixed* UTC offset the camera's clock holds at the given reading.

    A camera holds whatever offset its set zone had at the moment it was last
    adjusted, and does NOT track that zone's later DST — which is exactly why a
    lag gap exists. So the offset is frozen at the set's ``at_reading``. With no
    set in scope the camera is assumed to track the home zone (DST included),
    which is the sensible default when no adjustment was recorded.
    """
    candidates = [
        entry for entry in config.get("camera_clock_sets", [])
        if entry.get("camera") == camera and parse_stamp(entry["at_reading"]) <= reading
    ]
    if not candidates:
        home = resolve_zone(config, home_zone_name(config))
        return _offset_at(home, reading) if home else datetime.timedelta(0)
    latest = max(candidates, key=lambda entry: parse_stamp(entry["at_reading"]))
    zone = resolve_zone(config, latest.get("set_to"))
    return _offset_at(zone, parse_stamp(latest["at_reading"])) if zone else datetime.timedelta(0)


def to_true_instant(reading: datetime.datetime, offset: datetime.timedelta) -> datetime.datetime:
    """Turn a naive camera reading + its fixed offset into an aware UTC instant."""
    return (reading - offset).replace(tzinfo=UTC)


def _location_breakpoints(config: dict) -> list[tuple[datetime.datetime, dict]]:
    """Expand the location timeline into sorted (start_utc, entry) breakpoints.

    Each entry's ``since`` is a wall-clock moment in that entry's own zone (the
    local time where you arrived), converted to UTC for comparison. An optional
    ``until`` is sugar that auto-inserts a "resume the previous era" breakpoint
    so a trip does not need its return leg spelled out separately.
    """
    raw = sorted(config.get("locations", []), key=lambda entry: parse_stamp(entry["since"]))
    breakpoints: list[tuple[datetime.datetime, dict]] = []
    for index, entry in enumerate(raw):
        zone = resolve_zone(config, entry.get("zone"))
        since = parse_stamp(entry["since"]).replace(tzinfo=zone or UTC).astimezone(UTC)
        breakpoints.append((since, entry))
        if entry.get("until"):
            until = parse_stamp(entry["until"]).replace(tzinfo=zone or UTC).astimezone(UTC)
            previous = raw[index - 1] if index > 0 else {"zone": home_zone_name(config)}
            breakpoints.append((until, {**previous, "_resumed": True}))
    breakpoints.sort(key=lambda item: item[0])
    return breakpoints


def location_at(config: dict, true_instant: datetime.datetime) -> tuple[str | None, str | None, list | None]:
    """(zone, label, coords) for the location active at a true (UTC) instant."""
    active = None
    for start_utc, entry in _location_breakpoints(config):
        if start_utc <= true_instant:
            active = entry
        else:
            break
    if active is None:
        return home_zone_name(config), None, None
    return active.get("zone"), active.get("label"), active.get("coords")


def correct(config: dict, reading: datetime.datetime, camera: str) -> dict:
    """Full per-photo correction.

    Returns a dict with the corrected display ``datetime`` plus the resolved
    location ``label``/``zone``/``coords`` for naming and geolocation.
    """
    offset = camera_offset_at(config, camera, reading)
    true_instant = to_true_instant(reading, offset)
    zone_name, label, coords = location_at(config, true_instant)
    display_zone = resolve_zone(config, zone_name)
    if display_zone is None:
        display = true_instant.replace(tzinfo=None) if true_instant.tzinfo else true_instant
    else:
        display = true_instant.astimezone(display_zone).replace(tzinfo=None)
    return {
        "display": display,
        "true_instant": true_instant,
        "label": label,
        "zone": zone_name,
        "coords": coords,
    }


def has_timezone_config(config: dict) -> bool:
    """Whether any timeline is configured; empty config means identity (no-op)."""
    return bool(config.get("locations") or config.get("camera_clock_sets"))


def validate_timezone_config(config: dict) -> list[str]:
    """Validate timelines and enforce the ``at_reading`` frame convention.

    ``at_reading`` MUST be the *first corrected reading* (the value the camera
    showed right AFTER it was adjusted; see Decision 9). A bare timestamp is
    ambiguous about which clock frame it was measured in, and a wrong frame
    silently files photos into the wrong day. This is the one field that fails
    invisibly, so the loader checks it: consecutive sets (in reading order) must
    advance in *true* time. A set whose true instant precedes the previous set's
    is physically impossible and is the signature of an at_reading recorded in
    the old (pre-adjustment) frame. Only real consecutive sets are compared, so a
    correctly recorded forward adjustment never false-positives.
    """
    warnings: list[str] = []

    for entry in config.get("locations", []):
        for key in ("since", "until"):
            if key in entry:
                try:
                    parse_stamp(entry[key])
                except (ValueError, KeyError):
                    warnings.append(f"location {entry!r}: unparseable {key} {entry.get(key)!r}")
        if entry.get("zone") and resolve_zone(config, entry["zone"]) is None:
            warnings.append(f"location {entry!r}: unknown zone {entry['zone']!r}")

    by_camera: dict[str, list[dict]] = {}
    for entry in config.get("camera_clock_sets", []):
        try:
            parse_stamp(entry["at_reading"])
        except (ValueError, KeyError):
            warnings.append(f"clock set {entry!r}: unparseable at_reading")
            continue
        if entry.get("set_to") and resolve_zone(config, entry["set_to"]) is None:
            warnings.append(f"clock set {entry!r}: unknown zone {entry['set_to']!r}")
        by_camera.setdefault(entry.get("camera", ""), []).append(entry)

    for camera, sets in by_camera.items():
        ordered = sorted(sets, key=lambda item: parse_stamp(item["at_reading"]))
        previous_true = None
        for entry in ordered:
            zone = resolve_zone(config, entry.get("set_to"))
            reading = parse_stamp(entry["at_reading"])
            offset = _offset_at(zone, reading) if zone is not None else datetime.timedelta(0)
            true_instant = to_true_instant(reading, offset)
            if previous_true is not None and true_instant < previous_true:
                warnings.append(
                    f"camera-clock set for {camera} at {entry['at_reading']} appears to be "
                    f"in the OLD clock frame: its true instant precedes the previous "
                    f"adjustment. at_reading must be the first corrected reading "
                    f"(the value shown right after adjusting)."
                )
            previous_true = true_instant

    return warnings
