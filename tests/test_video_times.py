"""A video's capture time: QuickTime UTC plus the offset its device recorded (K11)."""

import datetime

from src.pipeline_stages.clock_readings import folder_readings, parse_clock_fields, reading_from_fields
from src.pipeline_stages.legacy import intrinsic_capture_datetime_from_exif_text, parse_legacy_exif_text
from src.pipeline_stages.retime_plan import apply_plan, plan_folder
from src.pipeline_stages.timezone_engine import TimeModel
from tests.test_clock_evidence import write_shot

CONFIG = {"camera_symbols": {"": "NOID"}}
D = datetime.datetime

# The S23 Ultra video from "Droga do Andory": 15:31:28 UTC, recorded at +0200.
SAMSUNG = """File Modification Date/Time     : 2026:09:15 16:31:28+01:00
---- QuickTime ----
Create Date                     : 2026:09:15 15:31:28
Author                          : Galaxy S23 Ultra
Samsung Model                   : SM-S918B
Android Time Zone               : +0200
Track Create Date               : 2026:09:15 15:31:28
Media Create Date               : 2026:09:15 15:31:28
"""
# The a7R V video from "W drodze na Tuca d'Aneto": camera zone setting +00:00.
SONY = """File Modification Date/Time     : 2026:09:17 13:25:57+01:00
Create Date                     : 2026:09:17 13:25:53
Time Zone                       : +00:00
Media Create Date               : 2026:09:17 13:25:53
Creation Date Value             : 2026:09:17 13:25:53Z
Device Manufacturer             : Sony
Device Model Name               : ILCE-7RM5
"""
APPLE = """Create Date                     : 2026:09:15 15:31:28
Camera Model Name               : iPhone 6
Creation Date                   : 2026:09:15 17:31:28+02:00
"""
NO_OFFSET_PHONE = """Create Date                     : 2026:09:15 15:31:28
Author                          : Galaxy S23 Ultra
"""
TRIP = {"home": "GB", "mobiles": ["SG23U", "iP6"],
        "trips": [{"country": "Europe/Madrid", "from": "2026-09-15_(Tue)__12.08.14",
                   "to": "2026-09-23_(Wed)__20.34.47"}],
        "camera_clocks": [{"camera": "ILC7R5", "clock": "home-winter"}],
        "calibrations": [{"camera": "ILC7R5", "reading": "2026-09-27_(Sun)__19.08.31.774",
                          "true": "2026-09-27_(Sun)__20.09.52.208"}]}


def reading(text):
    return reading_from_fields(parse_clock_fields(text), CONFIG)


def test_samsung_video_reading_is_utc_plus_android_time_zone():
    shot = reading(SAMSUNG)
    assert shot["camera"] == "SG23U"
    assert shot["reading"] == D(2026, 9, 15, 17, 31, 28) and shot["declared_offset"] == "+02:00"


def test_sony_video_reading_is_the_cameras_own_clock():
    shot = reading(SONY)
    assert shot["camera"] == "ILC7R5" and shot["reading"] == D(2026, 9, 17, 13, 25, 53)
    # Through the clock model like any of its stills: GMT clock, 80 s slow, in Spain.
    assert TimeModel(TRIP).correct_shot("ILC7R5", shot["reading"]).stamp == D(2026, 9, 17, 15, 27, 13)


def test_apple_creation_date_carries_its_own_offset():
    shot = reading(APPLE)
    assert shot["reading"] == D(2026, 9, 15, 17, 31, 28) and shot["declared_offset"] == "+02:00"


def test_no_offset_phone_video_is_utc_placed_by_the_trip():
    shot = reading(NO_OFFSET_PHONE)
    assert shot["reading"] is None and shot["utc"] == D(2026, 9, 15, 15, 31, 28)
    correction = TimeModel(TRIP).correct_shot("SG23U", None, None, shot["utc"])
    assert correction.stamp == D(2026, 9, 15, 17, 31, 28)


def test_no_offset_camera_video_is_taken_as_its_local_clock():
    correction = TimeModel({"home": "GB"}).correct_shot("C6D", None, None, D(2026, 7, 1, 12, 0, 0))
    assert correction.stamp == D(2026, 7, 1, 12, 0, 0)


def test_a_file_time_never_names_a_video():
    metadata = parse_legacy_exif_text(SAMSUNG, CONFIG)
    assert metadata["captured_at"] == D(2026, 9, 15, 17, 31, 28)
    assert metadata["camera_symbol"] == "SG23U"
    assert intrinsic_capture_datetime_from_exif_text(SAMSUNG) == D(2026, 9, 15, 17, 31, 28)


def test_author_that_is_a_person_is_not_a_camera():
    shot = reading("Create Date : 2026:09:15 15:31:28\nAuthor : Jan Kowalski\n")
    assert shot["camera"] == "NOID"


def test_step_zero_renames_the_mis_named_video(tmp_path):
    folder = tmp_path / "2026" / "09. September" / "2026-09-15_(Tue)__16.08.33 - Droga do Andory"
    name = "2026-09-15_(Tue)__16.31.28__fNA__T---__LNA__I---s__NOID.mp4"
    write_shot(folder, name, SAMSUNG)
    plan = plan_folder(folder, CONFIG, TimeModel(TRIP))
    assert plan.shots[0].new_name == "2026-09-15_(Tue)__17.31.28__fNA__T---__LNA__I---s__NOID.mp4"
    assert any("file time" in flag for flag in plan.shots[0].flags)
    apply_plan(plan, log=lambda _: None)
    assert (folder / "__EXIF" / "2026-09-15_(Tue)__17.31.28__fNA__T---__LNA__I---s__NOID.mp4._exif").exists()
    assert folder_readings(folder, CONFIG)[0].camera == "SG23U"
