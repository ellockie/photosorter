"""Where the archive suggests a clock was changed, or a trip began -- reported only.

Nothing here changes a file, the configuration, or a stamp. Every finding is an
*indication*, printed with a ready-to-paste ``timezone.json`` line built from
the real stamps, for a person to confirm or ignore:

* **certain adjustment** -- a camera's reading goes backwards while its shutter
  counter goes forwards. Clocks do not run backwards on their own.
* **possible adjustment** -- the offset a camera *declares* changes between two
  consecutive shots. Possible, not certain: the zone setting and the clock are
  set independently, so neither proves anything about the other.
* **trip boundary** -- a phone's declared offset changes. Phones keep their own
  time right, so a change there is where the user went.

Findings already covered by ``timezone.json`` are marked *recorded*.

Leaf module (engine, readings, stamps only), shared by the report tool.
"""

import dataclasses
import datetime

from src.pipeline_stages.clock_readings import exposures
from src.pipeline_stages.stamps import format_stamp
from src.pipeline_stages.timezone_engine import \
    TimeModel, \
    format_duration

CERTAIN, POSSIBLE, TRIP_START, TRIP_END = "certain adjustment", "possible adjustment", "trip start", "trip end"
# How close a recorded trip boundary must be to a phone's offset change to cover it.
TRIP_MATCH = datetime.timedelta(hours=36)


@dataclasses.dataclass(frozen=True)
class Finding:
    kind: str
    camera: str
    before: object          # ShotReading
    after: object           # ShotReading
    detail: str
    paste: str
    recorded: bool

    @property
    def when(self) -> datetime.datetime:
        return self.after.reading


def _ordered(shots) -> list:
    with_counter = [shot for shot in shots if shot.counter is not None]
    if shots and len(with_counter) >= 0.8 * len(shots):
        return sorted(with_counter, key=lambda shot: (shot.counter, shot.reading))
    return sorted(shots, key=lambda shot: (shot.reading, shot.subsecond or ""))


def _offset(text: str | None) -> datetime.timedelta | None:
    if not text:
        return None
    text = text.strip()
    try:
        sign = -1 if text[0] == "-" else 1
        hours, minutes = text.lstrip("+-").split(":")[:2]
        return sign * datetime.timedelta(hours=int(hours), minutes=int(minutes))
    except (ValueError, IndexError):
        return None


def _camera_recorded(model: TimeModel, camera: str, after) -> bool:
    return any(segment.start is not None and abs(segment.start - after.reading) <= datetime.timedelta(minutes=2)
               for segment in model.segments.get(camera, []))


def _camera_line(after) -> str:
    counter = f', "counter": {after.counter}' if after.counter is not None else ""
    return f'{{ "camera": "{after.camera}", "from": "{format_stamp(after.reading)}"{counter}, "clock": "??" }},'


def find_evidence(readings, model: TimeModel) -> list[Finding]:
    """Every indication in ``readings`` (any number of folders), oldest first."""
    by_camera: dict[str, list] = {}
    for shot in exposures(readings):
        if shot.reading is None:
            continue
        by_camera.setdefault(shot.camera, []).append(shot)
    findings = []
    for camera, shots in sorted(by_camera.items()):
        ordered = _ordered(shots)
        mobile = camera in model.mobiles
        for before, after in zip(ordered, ordered[1:]):
            gap = after.reading - before.reading
            offset_before, offset_after = _offset(before.declared_offset), _offset(after.declared_offset)
            offset_changed = offset_before is not None and offset_after is not None and offset_before != offset_after
            if mobile:
                if not offset_changed:
                    continue
                home_offset = after.reading.replace(tzinfo=model.home).utcoffset()
                kind = TRIP_END if offset_after == home_offset else TRIP_START
                if kind == TRIP_START:
                    paste = f'{{ "country": "??", "from": "{format_stamp(after.reading)}", "to": "??" }},'
                    recorded = any(abs(trip.start_wall - after.reading) <= TRIP_MATCH for trip in model.trips)
                else:
                    paste = f'... "to": "{format_stamp(before.reading)}" }}  (last shot before returning)'
                    recorded = any(abs(trip.end_wall - before.reading) <= TRIP_MATCH for trip in model.trips)
                findings.append(Finding(kind, camera, before, after,
                                        f"phone offset {before.declared_offset} -> {after.declared_offset}",
                                        paste, recorded))
                continue
            counters_advance = before.counter is not None and after.counter is not None and after.counter > before.counter
            if counters_advance and gap < datetime.timedelta(seconds=-1):
                findings.append(Finding(CERTAIN, camera, before, after,
                                        f"reading went back {format_duration(int(gap.total_seconds()))} "
                                        f"while the counter went {before.counter} -> {after.counter}",
                                        _camera_line(after), _camera_recorded(model, camera, after)))
            elif offset_changed:
                findings.append(Finding(POSSIBLE, camera, before, after,
                                        f"declared offset {before.declared_offset} -> {after.declared_offset}, "
                                        f"reading gap {format_duration(int(gap.total_seconds()))}",
                                        _camera_line(after), _camera_recorded(model, camera, after)))
    findings.sort(key=lambda finding: (finding.when, finding.camera))
    return findings


def format_findings(findings: list[Finding]) -> list[str]:
    """The report body: one block per finding, the paste line last."""
    lines = []
    for finding in findings:
        mark = "recorded" if finding.recorded else "NEW"
        counters = ""
        if finding.before.counter is not None and finding.after.counter is not None:
            counters = f"  counter {finding.before.counter} -> {finding.after.counter}"
        lines.append(f"[{mark}] {finding.kind:<19} {finding.camera:<8} {finding.detail}")
        lines.append(f"      last before : {format_stamp(finding.before.reading)}  {finding.before.subject.name}")
        lines.append(f"      first after : {format_stamp(finding.after.reading)}  {finding.after.subject.name}{counters}")
        lines.append(f"      in          : {finding.after.folder}")
        if not finding.recorded:
            lines.append(f"      paste       : {finding.paste}")
        lines.append("")
    return lines
