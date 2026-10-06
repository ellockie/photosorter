"""Camera clocks, trips and calibrations -> the local time a shot was taken.

The one definition (T8) of how a camera's raw reading becomes the stamp a file
is named by. Used by intake (``timezone-and-travel``), restructure step 0, the
clock evidence report and the visualiser. The calculator page re-implements it
in JavaScript and is held to the same results by shared test vectors
(``tests/data/time_vectors.json``).

    reading + camera --(clock segment: state + error)--> TRUE INSTANT (UTC)
    TRUE INSTANT --(where was I: trip zone, else home)--> local wall time
    local wall time --> stamp (whole seconds)

Configuration (``timezone.json``; openspec change ``camera-time-correction``):

* ``home``          country or IANA zone. DST is the zone's, never typed.
* ``mobiles``       camera symbols whose clock is always right (phones).
* ``trips``         ``{country, from, to}``. ``from``/``to`` are local wall
                    times in the trip's zone -- the stamps of the first and last
                    phone photo there.
* ``camera_clocks`` ``{camera, from?, counter?, clock}``. ``from`` is the first
                    reading the camera showed *after* the adjustment; no
                    ``from`` means "since the camera's first shot".
* ``calibrations``  ``{camera, reading, true}``: what the camera read, and what
                    the time really was (local wall time), at one moment.

Clock states:

    home                  the home zone, keeping up with its DST
    local                 the zone the user was in at ``from``, fixed then, with
                          that zone's DST (a camera set to Tokyo stays on Tokyo)
    home-winter / -summer home's standard / daylight offset, fixed
    <country or zone>     that zone, with its DST
    +HH:MM / -HH:MM       that fixed offset

Defaults: before a camera's first entry its clock is ``home`` with no error.
Outside trips that is no shift at all; inside a trip it is the "camera never
updated" shift, reported as *assumed*. Mobiles are never shifted.

A calibration's remainder -- what the state does not explain -- is the
segment's **error**, rounded to whole seconds so a shot's second still pairs
with its untouched ``SubSecTimeOriginal`` (F9). An in-camera declared offset
(``OffsetTimeOriginal``) never influences anything here.

Leaf module: standard library and ``stamps`` only, so the restructure tool can
load it on a bare interpreter. Zone data comes from ``tzdata`` (Windows has no
system zone database); when it is missing, ``ZoneDataUnavailable`` is raised.
"""

import dataclasses
import datetime
import functools
import math
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.pipeline_stages.stamps import \
    format_stamp, \
    parse_stamp, \
    parse_stamp_with_fraction

UTC = datetime.timezone.utc

TIMEZONE_KEYS = ("home", "mobiles", "trips", "camera_clocks", "calibrations")
# Decision 9's schema. Rejected, never read: its "set_to, frozen at the moment
# of setting" could not say "on GMT, 80 s slow", and reading it would quietly
# mean something different from what it meant when it was written.
SUPERSEDED_KEYS = {
    "zones": "home / trips (countries resolve to zones themselves)",
    "locations": "trips",
    "camera_clock_sets": "camera_clocks",
}

DEFAULT_HOME = "GB"
HOME, LOCAL, HOME_WINTER, HOME_SUMMER = "home", "local", "home-winter", "home-summer"
FIXED_OFFSET_RE = re.compile(r"^([+-])(\d{1,2}):(\d{2})$")
COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")

# Calibrations of one segment further apart than this are reported (D5).
CALIBRATION_AGREEMENT = datetime.timedelta(seconds=2)
# An error this large is a wrong state, not drift (D5).
SUSPICIOUS_ERROR = datetime.timedelta(minutes=15)

# How a camera's clock came to be what it is, for reports and the visualiser.
SOURCE_MOBILE = "mobile"
SOURCE_DEFAULT = "default"        # no entry, outside every trip: nothing to do
SOURCE_ASSUMED = "assumed"        # no entry, inside a trip: on home time, assumed
SOURCE_CONFIGURED = "configured"  # a camera_clocks entry
SOURCE_CALIBRATED = "calibrated"  # an entry (or the default) plus a calibration


class TimezoneConfigError(ValueError):
    """``timezone.json`` cannot be used as written."""


class ZoneDataUnavailable(RuntimeError):
    """No IANA zone database: ``tzdata`` is not installed for this interpreter."""


# --------------------------------------------------------------------------
# Zone data: countries -> zones, from the tzdata package's own tables
# --------------------------------------------------------------------------

def _tzdata_text(name: str) -> str:
    try:
        import importlib.resources
        return importlib.resources.files("tzdata").joinpath("zoneinfo", name).read_text(encoding="utf-8")
    except (ImportError, FileNotFoundError, OSError, ModuleNotFoundError) as error:
        raise ZoneDataUnavailable(
            "zone data unavailable: install 'tzdata' for this interpreter "
            "(it is in the project's Poetry environment)") from error


@functools.lru_cache(maxsize=1)
def country_tables() -> tuple[dict, dict]:
    """``({code: country name}, {code: [IANA zones, principal first]})``.

    ``iso3166.tab`` names the countries and ``zone.tab`` lists each country's
    zones, one per line, the most populous first.
    """
    names = {}
    for line in _tzdata_text("iso3166.tab").splitlines():
        if line and not line.startswith("#"):
            code, _, name = line.partition("\t")
            names[code.strip()] = name.strip()
    zones: dict[str, list[str]] = {}
    for line in _tzdata_text("zone.tab").splitlines():
        if line and not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) >= 3:
                zones.setdefault(parts[0].strip(), []).append(parts[2].strip())
    return names, zones


def _offsets_signature(zone: ZoneInfo) -> tuple:
    """The zone's offsets in January and July of every year 1990-2040."""
    signature = []
    for year in range(1990, 2041):
        for month in (1, 7):
            moment = datetime.datetime(year, month, 15, 12, tzinfo=UTC)
            signature.append(moment.astimezone(zone).utcoffset())
    return tuple(signature)


@functools.lru_cache(maxsize=None)
def country_zones(code: str) -> list[str]:
    """The *distinct* zones of a country, principal first.

    ``zone.tab`` lists zones that have kept identical time for decades
    (Germany's Busingen beside Berlin). Asking which of two identical clocks
    you were in is a question with no answer, so those collapse into the first.
    """
    _, zones = country_tables()
    distinct: list[str] = []
    signatures: list[tuple] = []
    for name in zones.get(code.upper(), []):
        try:
            signature = _offsets_signature(ZoneInfo(name))
        except (ZoneInfoNotFoundError, ValueError):
            continue
        if signature not in signatures:
            signatures.append(signature)
            distinct.append(name)
    return distinct


def resolve_place(text: str) -> ZoneInfo:
    """A country code or IANA zone name, as a zone. Raises ``TimezoneConfigError``.

    A country with several genuinely different zones is refused, and the
    refusal lists them: "US" is not a time.
    """
    value = str(text or "").strip()
    if COUNTRY_RE.match(value):
        names, _ = country_tables()
        code = value.upper()
        if code not in names:
            raise TimezoneConfigError(f"unknown country code {value!r}")
        candidates = country_zones(code)
        if not candidates:
            raise TimezoneConfigError(f"no time zone known for {code} ({names[code]})")
        if len(candidates) > 1:
            raise TimezoneConfigError(
                f"{code} ({names[code]}) has several time zones; name the region instead: "
                + ", ".join(candidates))
        return ZoneInfo(candidates[0])
    if "/" in value or value == "UTC":
        _tzdata_text("zone.tab")  # a clear error when the database is missing
        try:
            return ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise TimezoneConfigError(f"unknown time zone {value!r}") from None
    raise TimezoneConfigError(
        f"{value!r} is neither a two-letter country code nor an IANA zone such as 'Europe/London'")


def _fixed_offset(text: str) -> datetime.timedelta | None:
    match = FIXED_OFFSET_RE.match(str(text).strip())
    if not match:
        return None
    sign, hours, minutes = match.groups()
    delta = datetime.timedelta(hours=int(hours), minutes=int(minutes))
    return -delta if sign == "-" else delta


def standard_and_daylight(zone: ZoneInfo, year: int) -> tuple[datetime.timedelta, datetime.timedelta]:
    """A zone's (standard, daylight) offsets in a year; equal when it has no DST.

    Winter is the smaller of the January and July offsets, summer the larger --
    in either hemisphere. Not ``dst()``: tzdata gives Ireland a *negative* DST
    in winter, which would swap the two for a home in Dublin.
    """
    offsets = [datetime.datetime(year, month, 15, 12, tzinfo=UTC).astimezone(zone).utcoffset()
               for month in (1, 7)]
    return min(offsets), max(offsets)


def zone_label(zone: ZoneInfo | None) -> str:
    return getattr(zone, "key", None) or "?"


# --------------------------------------------------------------------------
# Stamps in the config
# --------------------------------------------------------------------------

def parse_config_stamp(value, *, fraction: bool = False) -> datetime.datetime:
    """A config stamp: the photo grammar, or ISO-8601. Naive (a wall reading)."""
    if isinstance(value, datetime.datetime):
        return value.replace(tzinfo=None)
    text = str(value).strip()
    parsed = parse_stamp_with_fraction(text) if fraction else None
    if parsed is None:
        parsed = parse_stamp(text) if not fraction else None
    if parsed is None:
        try:
            parsed = datetime.datetime.fromisoformat(text).replace(tzinfo=None)
        except ValueError:
            raise TimezoneConfigError(f"unreadable stamp {value!r}") from None
        if not fraction:
            parsed = parsed.replace(microsecond=0)
    return parsed


def round_seconds(delta: datetime.timedelta) -> int:
    """Whole seconds, half away from zero (calibration errors, D5)."""
    seconds = delta.total_seconds()
    return int(math.copysign(math.floor(abs(seconds) + 0.5), seconds))


def format_duration(seconds: int) -> str:
    """``+1h 01m 20s`` style, signed."""
    sign = "-" if seconds < 0 else "+"
    seconds = abs(int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{sign}{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{sign}{minutes}m {secs:02d}s"
    return f"{sign}{secs}s"


def format_error(seconds: int) -> str:
    """An error as the config writes one: ``-00:01:20``."""
    sign = "-" if seconds < 0 else "+"
    seconds = abs(int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{secs:02d}"


# --------------------------------------------------------------------------
# The model
# --------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Clock:
    """A resolved clock state: a zone (with its DST) or a fixed offset."""

    label: str
    zone: ZoneInfo | None = None
    offset: datetime.timedelta | None = None   # fixed offset
    fixed_kind: str | None = None              # home-winter / home-summer: per year

    def utc(self, reading: datetime.datetime, home: ZoneInfo) -> datetime.datetime:
        if self.zone is not None:
            return reading.replace(tzinfo=self.zone).astimezone(UTC)
        offset = self.offset
        if self.fixed_kind is not None:
            standard, daylight = standard_and_daylight(home, reading.year)
            offset = standard if self.fixed_kind == HOME_WINTER else daylight
        return (reading - offset).replace(tzinfo=UTC)

    def offset_at(self, reading: datetime.datetime, home: ZoneInfo) -> datetime.timedelta:
        return reading - self.utc(reading, home).replace(tzinfo=None)


@dataclasses.dataclass(frozen=True)
class Trip:
    zone: ZoneInfo
    place: str
    start_wall: datetime.datetime
    end_wall: datetime.datetime
    start_utc: datetime.datetime
    end_utc: datetime.datetime

    def contains_wall(self, wall: datetime.datetime) -> bool:
        return self.start_wall <= wall <= self.end_wall


@dataclasses.dataclass(frozen=True)
class Segment:
    camera: str
    start: datetime.datetime | None     # first reading after the adjustment; None = from the first shot
    counter: int | None
    clock: Clock
    entry_index: int | None             # None = the implicit default segment


@dataclasses.dataclass(frozen=True)
class Calibration:
    camera: str
    reading: datetime.datetime
    true_local: datetime.datetime
    error_seconds: int                  # camera minus truth: negative = camera slow
    raw_error: datetime.timedelta
    segment_index: int | None


@dataclasses.dataclass(frozen=True)
class Correction:
    camera: str
    reading: datetime.datetime
    stamp: datetime.datetime            # local wall time the file is named by
    true_utc: datetime.datetime
    zone: str                           # the zone ``stamp`` is in
    trip: str | None                    # the trip's place, when inside one
    clock: str                          # the clock state's label
    clock_offset: datetime.timedelta    # what the camera clock was ahead of UTC (error included)
    error_seconds: int
    source: str
    ambiguous: bool = False

    @property
    def shift(self) -> datetime.timedelta:
        return self.stamp - self.reading

    @property
    def local_offset(self) -> datetime.timedelta:
        return self.stamp - self.true_utc.replace(tzinfo=None)

    @property
    def stamp_text(self) -> str:
        return format_stamp(self.stamp)


class TimeModel:
    """``timezone.json``, resolved. ``errors`` make it unusable; ``warnings`` do not."""

    def __init__(self, data: dict | None):
        data = data or {}
        self.errors: list[str] = []
        self.warnings: list[str] = []
        for key, replacement in SUPERSEDED_KEYS.items():
            if key in data:
                self.errors.append(
                    f"'{key}' belongs to the superseded schema; use {replacement} instead "
                    "(see timezone.json and openspec change camera-time-correction)")
        self.home_name = str(data.get("home") or DEFAULT_HOME)
        self.home = self._place(self.home_name, "home") or ZoneInfo("UTC")
        self.mobiles = {str(symbol) for symbol in data.get("mobiles") or []}
        self.trips = self._trips(data.get("trips") or [])
        self.segments: dict[str, list[Segment]] = {}
        self._segments(data.get("camera_clocks") or [])
        self.calibrations: dict[str, list[Calibration]] = {}
        self._calibrations(data.get("calibrations") or [])
        self._check_frames()

    # -- loading ---------------------------------------------------------

    def _place(self, text, where) -> ZoneInfo | None:
        try:
            return resolve_place(text)
        except TimezoneConfigError as error:
            self.errors.append(f"{where}: {error}")
            return None

    def _trips(self, entries) -> list[Trip]:
        trips = []
        for index, entry in enumerate(entries):
            where = f"trips[{index}]"
            if not isinstance(entry, dict):
                self.errors.append(f"{where}: not an object")
                continue
            zone = self._place(entry.get("country"), where)
            try:
                start = parse_config_stamp(entry["from"])
                end = parse_config_stamp(entry["to"])
            except KeyError as missing:
                self.errors.append(f"{where}: missing {missing}")
                continue
            except TimezoneConfigError as error:
                self.errors.append(f"{where}: {error}")
                continue
            if zone is None:
                continue
            if end < start:
                self.errors.append(f"{where}: 'to' is before 'from'")
                continue
            trips.append(Trip(zone, str(entry.get("country")), start, end,
                              start.replace(tzinfo=zone).astimezone(UTC),
                              end.replace(tzinfo=zone).astimezone(UTC)))
        trips.sort(key=lambda trip: trip.start_utc)
        return trips

    def _clock(self, text, start, where) -> Clock | None:
        value = str(text or "").strip()
        if value == HOME:
            return Clock(HOME, zone=self.home)
        if value in (HOME_WINTER, HOME_SUMMER):
            return Clock(value, fixed_kind=value)
        if value == LOCAL:
            if start is None:
                self.errors.append(f"{where}: 'local' needs a 'from' -- local to where, when?")
                return None
            zone = self.zone_at_wall(start)
            return Clock(f"local ({zone_label(zone)})", zone=zone)
        offset = _fixed_offset(value)
        if offset is not None:
            return Clock(value, offset=offset)
        zone = self._place(value, where)
        return Clock(zone_label(zone), zone=zone) if zone is not None else None

    def _segments(self, entries) -> None:
        for index, entry in enumerate(entries):
            where = f"camera_clocks[{index}]"
            if not isinstance(entry, dict) or not entry.get("camera"):
                self.errors.append(f"{where}: needs 'camera' and 'clock'")
                continue
            camera = str(entry["camera"])
            if camera in self.mobiles:
                self.errors.append(f"{where}: {camera} is a mobile; a mobile's clock is never corrected")
                continue
            start = None
            if entry.get("from"):
                try:
                    start = parse_config_stamp(entry["from"])
                except TimezoneConfigError as error:
                    self.errors.append(f"{where}: {error}")
                    continue
            counter = entry.get("counter")
            if counter is not None:
                try:
                    counter = int(counter)
                except (TypeError, ValueError):
                    self.errors.append(f"{where}: counter must be a number")
                    counter = None
            clock = self._clock(entry.get("clock"), start, where)
            if clock is None:
                continue
            self.segments.setdefault(camera, []).append(Segment(camera, start, counter, clock, index))
        for camera, segments in self.segments.items():
            if sum(1 for segment in segments if segment.start is None) > 1:
                self.errors.append(f"camera_clocks: {camera} has more than one entry without 'from'")
            segments.sort(key=lambda segment: (segment.start is not None, segment.start or datetime.datetime.min))

    def _calibrations(self, entries) -> None:
        for index, entry in enumerate(entries):
            where = f"calibrations[{index}]"
            if not isinstance(entry, dict) or not entry.get("camera"):
                self.errors.append(f"{where}: needs 'camera', 'reading' and 'true'")
                continue
            camera = str(entry["camera"])
            if camera in self.mobiles:
                self.errors.append(f"{where}: {camera} is a mobile; a mobile's clock is never corrected")
                continue
            try:
                reading = parse_config_stamp(entry["reading"], fraction=True)
                true_local = parse_config_stamp(entry["true"], fraction=True)
            except KeyError as missing:
                self.errors.append(f"{where}: missing {missing}")
                continue
            except TimezoneConfigError as error:
                self.errors.append(f"{where}: {error}")
                continue
            segment_index, segment = self._segment_for(camera, reading, None)
            clock = segment.clock if segment else Clock(HOME, zone=self.home)
            true_utc = true_local.replace(tzinfo=self.zone_at_wall(true_local)).astimezone(UTC)
            raw_error = clock.utc(reading, self.home) - true_utc
            calibration = Calibration(camera, reading, true_local, round_seconds(raw_error), raw_error, segment_index)
            if abs(raw_error) >= SUSPICIOUS_ERROR:
                self.warnings.append(
                    f"{where}: {camera} is {format_duration(calibration.error_seconds)} off on clock "
                    f"'{clock.label}' -- that is a clock setting, not drift. "
                    f"{self.suggest_state(camera, reading, true_local)}")
            self.calibrations.setdefault(camera, []).append(calibration)
        for camera, calibrations in self.calibrations.items():
            by_segment: dict = {}
            for calibration in calibrations:
                by_segment.setdefault(calibration.segment_index, []).append(calibration)
            for group in by_segment.values():
                errors = [calibration.error_seconds for calibration in group]
                if max(errors) - min(errors) > CALIBRATION_AGREEMENT.total_seconds():
                    self.warnings.append(
                        f"calibrations: {camera} has calibrations {', '.join(format_duration(e) for e in errors)} "
                        "in one clock segment -- they disagree by more than 2 s")

    def _check_frames(self) -> None:
        """Consecutive adjustments must advance in true time (Decision 9's frame rule).

        ``from`` is the first reading *after* an adjustment. A ``from`` copied
        from the old frame -- "when I noticed" rather than "the first right
        photo" -- puts the adjustment before the previous one in real time.
        """
        for camera, segments in self.segments.items():
            previous = None
            for segment in segments:
                if segment.start is None:
                    continue
                instant = segment.clock.utc(segment.start, self.home)
                if previous is not None and instant < previous:
                    self.warnings.append(
                        f"camera_clocks: {camera} from {format_stamp(segment.start)} lies before the previous "
                        "adjustment in real time -- 'from' must be the first reading AFTER the adjustment")
                previous = instant

    # -- lookups ---------------------------------------------------------

    @property
    def is_identity(self) -> bool:
        return not (self.trips or self.segments or self.calibrations)

    def trip_at_wall(self, wall: datetime.datetime) -> Trip | None:
        found = None
        for trip in self.trips:
            if trip.contains_wall(wall):
                found = trip
        return found

    def zone_at_wall(self, wall: datetime.datetime) -> ZoneInfo:
        trip = self.trip_at_wall(wall)
        return trip.zone if trip else self.home

    def trip_at(self, instant: datetime.datetime) -> Trip | None:
        found = None
        for trip in self.trips:
            if trip.start_utc <= instant <= trip.end_utc:
                found = trip
        return found

    def zone_at(self, instant: datetime.datetime) -> ZoneInfo:
        trip = self.trip_at(instant)
        return trip.zone if trip else self.home

    def _segment_for(self, camera, reading, counter) -> tuple[int | None, Segment | None]:
        """The segment a reading falls in, and whether a backward overlap made it a guess."""
        index, segment, _ = self._resolve_segment(camera, reading, counter)
        return index, segment

    def _resolve_segment(self, camera, reading, counter):
        segments = self.segments.get(camera, [])
        chosen_index, chosen, ambiguous = None, None, False
        for index, segment in enumerate(segments):
            if segment.start is None:
                chosen_index, chosen = index, segment
                continue
            if reading < segment.start:
                break
            previous = chosen.clock if chosen is not None else Clock(HOME, zone=self.home)
            # A backward adjustment repeats readings: the old clock had reached
            # start + overlap by the moment it was set back to start (D7).
            overlap = segment.clock.utc(segment.start, self.home) - previous.utc(segment.start, self.home)
            repeated = overlap > datetime.timedelta(0) and reading < segment.start + overlap
            if repeated and segment.counter is not None and counter is not None:
                if counter < segment.counter:
                    continue
                ambiguous = False
            else:
                ambiguous = repeated
            chosen_index, chosen = index, segment
        return chosen_index, chosen, ambiguous

    def _error_for(self, camera, segment_index, reading) -> tuple[int, bool]:
        calibrations = [c for c in self.calibrations.get(camera, []) if c.segment_index == segment_index]
        if not calibrations:
            return 0, False
        nearest = min(calibrations, key=lambda c: abs(c.reading - reading))
        return nearest.error_seconds, True

    def correct(self, camera: str, reading: datetime.datetime, counter: int | None = None) -> Correction:
        """The local stamp a shot read ``reading`` on camera ``camera`` is named by."""
        reading = reading.replace(tzinfo=None, microsecond=0)
        camera = camera or ""
        if camera in self.mobiles or self.is_identity:
            zone = self.home if camera not in self.mobiles else self.zone_at_wall(reading)
            true_utc = reading.replace(tzinfo=zone).astimezone(UTC)
            trip = self.trip_at(true_utc)
            return Correction(camera, reading, reading, true_utc, zone_label(zone), trip.place if trip else None,
                              LOCAL if camera in self.mobiles else HOME, reading - true_utc.replace(tzinfo=None),
                              0, SOURCE_MOBILE if camera in self.mobiles else SOURCE_DEFAULT)
        index, segment, ambiguous = self._resolve_segment(camera, reading, counter)
        clock = segment.clock if segment is not None else Clock(HOME, zone=self.home)
        error, calibrated = self._error_for(camera, index, reading)
        true_utc = clock.utc(reading, self.home) - datetime.timedelta(seconds=error)
        zone = self.zone_at(true_utc)
        trip = self.trip_at(true_utc)
        if clock.zone is not None and clock.zone.key == zone.key:
            # Same clock as the place: the reading already is the local time, bar
            # the error. Not round-tripped through UTC, which would move a reading
            # inside a DST gap or repeated hour by the hour it does not have.
            stamp = reading - datetime.timedelta(seconds=error)
        else:
            stamp = true_utc.astimezone(zone).replace(tzinfo=None)
        if segment is None:
            source = SOURCE_ASSUMED if trip is not None else SOURCE_DEFAULT
        else:
            source = SOURCE_CONFIGURED
        if calibrated:
            source = SOURCE_CALIBRATED
        return Correction(camera, reading, stamp.replace(microsecond=0), true_utc, zone_label(zone),
                          trip.place if trip else None, clock.label,
                          reading - true_utc.replace(tzinfo=None), error, source, ambiguous)

    # -- helpers for people ----------------------------------------------

    def candidate_clocks(self, at_wall: datetime.datetime) -> list[Clock]:
        zone = self.zone_at_wall(at_wall)
        candidates = [Clock(HOME, zone=self.home), Clock(HOME_WINTER, fixed_kind=HOME_WINTER),
                      Clock(HOME_SUMMER, fixed_kind=HOME_SUMMER)]
        if zone.key != self.home.key:
            candidates.append(Clock(f"local ({zone.key})", zone=zone))
        return candidates

    def suggest_state(self, camera, reading, true_local) -> str:
        true_utc = true_local.replace(tzinfo=self.zone_at_wall(true_local)).astimezone(UTC)
        best = min(self.candidate_clocks(reading),
                   key=lambda clock: abs(clock.utc(reading, self.home) - true_utc))
        remainder = round_seconds(best.utc(reading, self.home) - true_utc)
        name = best.label.split(" ")[0]
        return f"Did you mean clock '{name}' (leaving an error of {format_duration(remainder)})?"

    def dst_changes(self, start: datetime.datetime, end: datetime.datetime) -> list[tuple]:
        """``(utc instant, zone, offset before, offset after)`` for home and trip zones.

        Scanned hour by hour, which no DST rule in use is finer than.
        """
        zones = {self.home.key: self.home}
        for trip in self.trips:
            zones[trip.zone.key] = trip.zone
        changes = []
        start_utc = start.replace(tzinfo=UTC) if start.tzinfo is None else start
        end_utc = end.replace(tzinfo=UTC) if end.tzinfo is None else end
        for name, zone in zones.items():
            moment = start_utc.replace(minute=0, second=0, microsecond=0)
            previous = moment.astimezone(zone).utcoffset()
            step = datetime.timedelta(hours=1)
            # Coarse day steps, refined to the hour around a change.
            day = datetime.timedelta(days=1)
            while moment < end_utc:
                following = moment + day
                offset = following.astimezone(zone).utcoffset()
                if offset != previous:
                    probe = moment
                    while probe.astimezone(zone).utcoffset() == previous:
                        probe += step
                    changes.append((probe, name, previous, offset))
                    previous = offset
                moment = following
        changes.sort(key=lambda change: change[0])
        return changes


def order_inversions(items) -> list[tuple]:
    """Where sorting by name would not be chronological (option c: reported, never fixed).

    ``items`` are ``(name, true_utc, payload)``. Returns ``(payload, payload)``
    pairs: the first sorts *after* the second by name but was taken *before*
    it. At a westward seam or in a DST fall-back hour local time repeats, and
    that is exactly where this happens.
    """
    by_name = sorted(items, key=lambda item: item[0])
    found = []
    latest = None
    for item in by_name:
        if latest is not None and item[1] < latest[1]:
            found.append((item[2], latest[2]))
        if latest is None or item[1] > latest[1]:
            latest = item
    return found


# The states the calculator tries, in the order a tie is settled: a person's
# camera is far more often "on home time" than on a fixed half of it.
CALCULATOR_STATES = (HOME, HOME_WINTER, HOME_SUMMER, LOCAL)


def _calculator_clock(state: str, home: ZoneInfo, location: ZoneInfo) -> Clock:
    if state == HOME:
        return Clock(HOME, zone=home)
    if state in (HOME_WINTER, HOME_SUMMER):
        return Clock(state, fixed_kind=state)
    if state == LOCAL:
        return Clock(LOCAL, zone=location)
    offset = _fixed_offset(state)
    if offset is not None:
        return Clock(state, offset=offset)
    zone = resolve_place(state)
    return Clock(zone_label(zone), zone=zone)


def calculate(home: str, location: str, reading, reference=None, state: str | None = None,
              error: int = 0) -> dict:
    """What the calculator page computes, for its test vectors (T8 by test).

    With a ``reference`` (the true local time at ``location`` -- a clock in the
    photo, or a phone shot of the same moment) the state that leaves the
    smallest remainder is inferred and the remainder becomes the error. Without
    one, ``state`` and ``error`` are taken as given and only translated.
    """
    home_zone, location_zone = resolve_place(home), resolve_place(location)
    reading = parse_config_stamp(reading, fraction=True)
    if reference is not None:
        true_utc = parse_config_stamp(reference, fraction=True).replace(tzinfo=location_zone).astimezone(UTC)
        best = None
        for candidate in CALCULATOR_STATES:
            clock = _calculator_clock(candidate, home_zone, location_zone)
            remainder = clock.utc(reading, home_zone) - true_utc
            if best is None or abs(remainder) < abs(best[1]):
                best = (candidate, remainder)
        state, error = best[0], round_seconds(best[1])
    clock = _calculator_clock(state or HOME, home_zone, location_zone)
    whole = reading.replace(microsecond=0)
    if clock.zone is not None and clock.zone.key == location_zone.key:
        stamp = whole - datetime.timedelta(seconds=error)
    else:
        true_utc = clock.utc(whole, home_zone) - datetime.timedelta(seconds=error)
        stamp = true_utc.astimezone(location_zone).replace(tzinfo=None)
    return {"state": state or HOME, "error": error, "stamp": format_stamp(stamp)}


def model_from_config(config: dict) -> TimeModel:
    """The model for a loaded config (``timezone.json`` overlaid onto it)."""
    data = {key: config[key] for key in TIMEZONE_KEYS if key in config}
    data.update({key: config[key] for key in SUPERSEDED_KEYS if key in config})
    return TimeModel(data)


def validate_timezone_config(config: dict) -> list[str]:
    """Every problem with the timezone data, errors first; empty when it is usable."""
    try:
        model = model_from_config(config)
    except ZoneDataUnavailable as error:
        return [str(error)]
    return [f"ERROR: {message}" for message in model.errors] + model.warnings


def has_timezone_config(config: dict) -> bool:
    """Whether anything would ever be shifted."""
    return any(config.get(key) for key in ("trips", "camera_clocks", "calibrations"))
