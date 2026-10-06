"""Clock evidence: read from sidecars, reported only (camera-time-correction)."""

import datetime
from pathlib import Path

from src.pipeline_stages.clock_evidence import \
    CERTAIN, \
    POSSIBLE, \
    TRIP_END, \
    TRIP_START, \
    find_evidence, \
    format_findings
from src.pipeline_stages.clock_readings import \
    folder_readings, \
    parse_clock_fields, \
    walk_dated_folders
from src.pipeline_stages.timezone_engine import TimeModel

CONFIG = {"camera_symbols": {"ILCE-7RM5": "ILC7R5", "Galaxy S23 Ultra": "SG23U", "": "NOID"}}


def sidecar_text(model, reading, offset=None, counter=None, subsec=None, tail=""):
    lines = [f"Camera Model Name               : {model}",
             f"Date/Time Original              : {reading}"]
    if subsec:
        lines.append(f"Sub Sec Time Original           : {subsec}")
    if offset:
        lines.append(f"Offset Time Original            : {offset}")
    if counter is not None:
        lines.append(f"Shutter Count                   : {counter}")
    return "\n".join(lines) + "\n" + tail


def write_shot(folder: Path, name, text, subdir=""):
    place = folder / subdir if subdir else folder
    (place / "__EXIF").mkdir(parents=True, exist_ok=True)
    (place / name).write_bytes(b"x")
    (place / "__EXIF" / f"{name}._exif").write_text(text, encoding="iso-8859-1")


def calibration_folder(tmp_path):
    folder = tmp_path / "2026" / "09. September" / "2026-09-27_(Sun)__19.08.31 - calibration"
    write_shot(folder, "2026-09-27_(Sun)__19.08.31__ILC7R5_HAS_RAW.jpg",
               sidecar_text("ILCE-7RM5", "2026:09:27 19:08:31", "+00:00", 16878, "774"))
    write_shot(folder, "2026-09-27_(Sun)__20.20.58__ILC7R5_HAS_RAW.jpg",
               sidecar_text("ILCE-7RM5", "2026:09:27 20:20:58", "+01:00", 16879, "925"))
    # The RAW of the same exposure: its sidecar repeats Date/Time Original
    # further down for the embedded preview, with an offset welded on.
    write_shot(folder, "2026-09-27_(Sun)__20.20.58__RAW__ILC7R5.ARW",
               sidecar_text("ILCE-7RM5", "2026:09:27 20:20:58", "+01:00", 16879, "925",
                            tail="Date/Time Original              : 2026:09:27 20:20:58.925+01:00\n"),
               subdir="__RAW")
    return folder


def test_first_occurrence_wins():
    fields = parse_clock_fields("Date/Time Original : 2026:09:27 20:20:58\n"
                                "Sequence Image Number : 1\n"
                                "Date/Time Original : 2026:09:27 20:20:58.925+01:00\n")
    assert fields == {"Date/Time Original": "2026:09:27 20:20:58"}


def test_folder_readings_cover_raw_subfolder(tmp_path):
    readings = folder_readings(calibration_folder(tmp_path), CONFIG)
    assert sorted((shot.subdir, shot.counter) for shot in readings) == [("", 16878), ("", 16879), ("__RAW", 16879)]
    raw = next(shot for shot in readings if shot.subdir == "__RAW")
    assert raw.reading == datetime.datetime(2026, 9, 27, 20, 20, 58)
    assert raw.camera == "ILC7R5" and raw.declared_offset == "+01:00"


def test_walk_finds_nested_dated_folders_and_skips_taxonomy(tmp_path):
    month = tmp_path / "2026" / "09. September"
    group = month / "2026-09-15_(Tue)__04.44.37___GROUP___[ Hiszpania ]___2026-09-24_(Thu)__02.01.41"
    (group / "2026-09-15_(Tue)__11.08.17 - Barcelona" / "__EXIF").mkdir(parents=True)
    (tmp_path / "2026" / "__LOGS").mkdir()
    found = [(depth, folder.name) for depth, folder in walk_dated_folders(tmp_path, CONFIG)]
    assert found == [(1, group.name), (2, "2026-09-15_(Tue)__11.08.17 - Barcelona")]


def test_declared_offset_change_is_a_possible_adjustment_with_a_paste_line(tmp_path):
    readings = folder_readings(calibration_folder(tmp_path), CONFIG)
    findings = find_evidence(readings, TimeModel({"home": "GB"}))
    assert [finding.kind for finding in findings] == [POSSIBLE]
    assert findings[0].paste == \
        '{ "camera": "ILC7R5", "from": "2026-09-27_(Sun)__20.20.58", "counter": 16879, "clock": "??" },'
    assert not findings[0].recorded


def test_recorded_finding_is_marked(tmp_path):
    readings = folder_readings(calibration_folder(tmp_path), CONFIG)
    model = TimeModel({"home": "GB", "camera_clocks": [
        {"camera": "ILC7R5", "from": "2026-09-27_(Sun)__20.20.58", "counter": 16879, "clock": "local"}]})
    findings = find_evidence(readings, model)
    assert findings[0].recorded
    assert "paste" not in "\n".join(format_findings(findings))


def test_backward_reading_with_advancing_counter_is_certain(tmp_path):
    folder = tmp_path / "2019" / "08. August" / "2019-08-03_(Sat)__20.00.00 - x"
    write_shot(folder, "a.jpg", sidecar_text("ILCE-7RM5", "2019:08:03 23:58:10", counter=4211))
    write_shot(folder, "b.jpg", sidecar_text("ILCE-7RM5", "2019:08:03 23:02:44", counter=4212))
    findings = find_evidence(folder_readings(folder, CONFIG), TimeModel({"home": "GB"}))
    assert [finding.kind for finding in findings] == [CERTAIN]
    assert "-55m 26s" in findings[0].detail


def test_phone_offset_changes_are_trip_boundaries(tmp_path):
    folder = tmp_path / "2026" / "09. September" / "2026-09-15_(Tue)__11.08.17 - trip"
    write_shot(folder, "p1.jpg", sidecar_text("Galaxy S23 Ultra", "2026:09:15 11:08:17", "+01:00"))
    write_shot(folder, "p2.jpg", sidecar_text("Galaxy S23 Ultra", "2026:09:15 12:08:14", "+02:00"))
    write_shot(folder, "p3.jpg", sidecar_text("Galaxy S23 Ultra", "2026:09:23 20:34:47", "+02:00"))
    write_shot(folder, "p4.jpg", sidecar_text("Galaxy S23 Ultra", "2026:09:24 01:02:44", "+01:00"))
    model = TimeModel({"home": "GB", "mobiles": ["SG23U"]})
    findings = find_evidence(folder_readings(folder, CONFIG), model)
    assert [finding.kind for finding in findings] == [TRIP_START, TRIP_END]
    assert '"from": "2026-09-15_(Tue)__12.08.14"' in findings[0].paste
    assert '"to": "2026-09-23_(Wed)__20.34.47"' in findings[1].paste


def test_report_changes_nothing(tmp_path):
    folder = calibration_folder(tmp_path)
    before = sorted((path, path.stat().st_mtime) for path in tmp_path.rglob("*"))
    find_evidence(folder_readings(folder, CONFIG), TimeModel({"home": "GB"}))
    assert sorted((path, path.stat().st_mtime) for path in tmp_path.rglob("*")) == before
