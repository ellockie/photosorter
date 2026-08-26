import datetime
import json
from pathlib import Path

from src.pipeline_stages.timezone_engine import (
    correct,
    has_timezone_config,
    is_ambiguous_reading,
    parse_stamp,
    validate_timezone_config,
)
from src.pipeline_stages.geolocation import location_info, write_location_stamp
from src.retime_archive import retime_archive


ZONES = {"UK": "Europe/London", "JP": "Asia/Tokyo"}


def japan_config():
    return {
        "zones": ZONES,
        "locations": [
            {"since": "2000-01-01_(Sat)_00.00.00", "zone": "UK"},
            {
                "since": "2026-04-10_(Fri)_00.00.00",
                "zone": "JP",
                "label": "Japan",
                "until": "2026-04-20_(Mon)_23.59.59",
            },
        ],
        "camera_clock_sets": [],
    }


def test_parse_stamp_photo_grammar_and_iso():
    assert parse_stamp("2026-04-12_(Sun)_18.00.00") == datetime.datetime(2026, 4, 12, 18, 0, 0)
    # Weekday is decorative: a wrong day name still parses.
    assert parse_stamp("2026-04-12_(Xxx)_18.00.00") == datetime.datetime(2026, 4, 12, 18, 0, 0)
    assert parse_stamp("2026-04-12T18:00:00") == datetime.datetime(2026, 4, 12, 18, 0, 0)


def test_location_timeline_shifts_into_trip_zone():
    # Camera on home (London, BST +1) never re-set: 10:00 London -> 09:00 UTC
    # -> Tokyo 18:00, labelled Japan.
    result = correct(japan_config(), datetime.datetime(2026, 4, 12, 10, 0, 0), "NE71")
    assert result["display"] == datetime.datetime(2026, 4, 12, 18, 0, 0)
    assert result["label"] == "Japan"
    assert result["zone"] == "JP"


def test_until_sugar_resumes_home_era():
    # 2026-05-01 is past the trip's `until`, so the home era resumes: identity.
    result = correct(japan_config(), datetime.datetime(2026, 5, 1, 14, 30, 0), "C6D")
    assert result["display"] == datetime.datetime(2026, 5, 1, 14, 30, 0)
    assert result["label"] is None


def test_camera_holds_fixed_offset_and_does_not_auto_dst():
    # Camera set to UK in winter (GMT/+0) and never touched. A June reading must
    # NOT auto-gain BST on the camera side; the world did, so the photo is +1h.
    config = {
        "zones": {"UK": "Europe/London"},
        "locations": [{"since": "2000-01-01_(Sat)_00.00.00", "zone": "UK"}],
        "camera_clock_sets": [
            {"camera": "C6D", "at_reading": "2026-01-01_(Thu)_12.00.00", "set_to": "UK"}
        ],
    }
    result = correct(config, datetime.datetime(2026, 6, 1, 12, 0, 0), "C6D")
    assert result["display"] == datetime.datetime(2026, 6, 1, 13, 0, 0)


def test_frame_check_warns_on_backward_true_time():
    bad = {
        "zones": ZONES,
        "locations": [{"since": "2000-01-01_(Sat)_00.00.00", "zone": "UK"}],
        "camera_clock_sets": [
            {"camera": "C6D", "at_reading": "2026-04-12_(Sun)_10.00.00", "set_to": "UK"},
            {"camera": "C6D", "at_reading": "2026-04-12_(Sun)_14.00.00", "set_to": "JP"},
        ],
    }
    warnings = validate_timezone_config(bad)
    assert any("OLD clock frame" in message for message in warnings)
    # A correctly recorded forward adjustment never false-positives.
    assert validate_timezone_config(japan_config()) == []


def test_westward_overlap_flagged_and_defaults_to_post_adjustment():
    config = {
        "zones": ZONES,
        "locations": [{"since": "2000-01-01_(Sat)_00.00.00", "zone": "UK"}],
        "camera_clock_sets": [
            {"camera": "X", "at_reading": "2026-04-11_(Sat)_18.00.00", "set_to": "JP"},
            {"camera": "X", "at_reading": "2026-04-21_(Tue)_09.00.00", "set_to": "UK"},
        ],
    }
    overlapping = datetime.datetime(2026, 4, 21, 12, 0, 0)  # repeated-hour window
    assert is_ambiguous_reading(config, "X", overlapping) is True
    # Default resolution is the post-adjustment (UK) interval: 12:00 stays 12:00.
    assert correct(config, overlapping, "X")["display"] == overlapping
    # A reading before the second set is unambiguous.
    assert is_ambiguous_reading(config, "X", datetime.datetime(2026, 4, 21, 8, 0, 0)) is False


def test_has_timezone_config_gates_identity():
    assert has_timezone_config(japan_config()) is True
    assert has_timezone_config({"locations": [], "camera_clock_sets": []}) is False


def test_geolocation_stamp_projection(tmp_path):
    metadata = {"location_zone": "JP", "location_suffix": "Japan", "location_coords": [35.68, 139.69]}
    info = location_info(metadata)
    assert info == {"zone": "JP", "label": "Japan", "coords": [35.68, 139.69]}
    event_folder = tmp_path / "2026-04-12_(Sun) - Japan"
    stamp = write_location_stamp(event_folder, {}, info)
    assert stamp == event_folder / "__GEOLOCATIONS" / "_location.json"
    data = json.loads(stamp.read_text(encoding="utf-8"))
    assert data["zone"] == "JP" and data["label"] == "Japan"


def test_timezone_data_lives_in_dedicated_file(tmp_path):
    from src.core import load_config, save_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"paths": {"root_folder": str(tmp_path / "P")}}), encoding="utf-8")
    (tmp_path / "timezone.json").write_text(json.dumps({
        "zones": {"JP": "Asia/Tokyo"},
        "locations": [{"since": "2026-04-10_(Fri)_00.00.00", "zone": "JP", "label": "Japan"}],
        "camera_clock_sets": [],
    }), encoding="utf-8")

    # The dedicated file is overlaid onto the loaded config.
    config = load_config(str(cfg_path))
    assert config["zones"]["JP"] == "Asia/Tokyo"
    assert config["locations"][0]["label"] == "Japan"

    # Saving keeps the timezone keys out of config.json and in timezone.json.
    config.setdefault("camera_symbols", {})["X"] = "Y"
    save_config(config, str(cfg_path))
    saved_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert not any(key in saved_cfg for key in ("zones", "locations", "camera_clock_sets"))
    saved_tz = json.loads((tmp_path / "timezone.json").read_text(encoding="utf-8"))
    assert saved_tz["zones"]["JP"] == "Asia/Tokyo"
    assert saved_tz["locations"][0]["label"] == "Japan"


def _retime_config():
    return {
        "zones": {"UK": "Europe/London"},
        "locations": [{"since": "2000-01-01_(Sat)_00.00.00", "zone": "UK"}],
        # Camera frozen on GMT all year, so summer readings need +1h (BST).
        "camera_clock_sets": [
            {"camera": "C6D", "at_reading": "2026-01-01_(Thu)_12.00.00", "set_to": "UK"}
        ],
        "extensions": {"lossy_images": [".jpg"], "raw_images": [], "videos": [], "other_images": []},
        "camera_symbols": {"Canon EOS 6D": "C6D", "": "NOID"},
        "legacy": {"day_boundary_time": "04.44.44", "date_folder_suffix": " - 1. ######"},
    }


def _write_event_file(event_folder: Path, image_name: str, taken_at: str):
    event_folder.mkdir(parents=True, exist_ok=True)
    (event_folder / image_name).write_text("photo-bytes", encoding="utf-8")
    exif_dir = event_folder / "__EXIF"
    exif_dir.mkdir(parents=True, exist_ok=True)
    (exif_dir / f"{image_name}._exif").write_text(
        "\n".join([
            "Camera Model Name               : Canon EOS 6D",
            f"Date/Time Original              : {taken_at}",
        ]),
        encoding="iso-8859-1",
    )


def test_retime_archive_refolds_across_day_boundary_and_is_idempotent(tmp_path):
    config = _retime_config()
    parent = tmp_path / "2026"
    # Original reading 04:30 (before 04:44 boundary) was filed under 05-31; the
    # +1h BST correction pushes it to 05:30 -> day flips to 06-01.
    old_folder = parent / "2026-05-31_(Sun) - Holiday"
    image = "2026-06-01_(Mon)_04.30.00__Holiday__f2.8__T1_250__I200__C6D.jpg"
    _write_event_file(old_folder, image, "2026:06:01 04:30:00")

    summary = retime_archive(parent, "2026-06-01", "2026-06-02", config)
    assert summary["retimed"] == 1
    assert summary["refolded"] == 1

    new_folder = parent / "2026-06-01_(Mon) - Holiday"
    # Retiming also upgrades the legacy single-underscore stamp it read to the
    # canonical "_(Ddd)__HH.MM.SS" form.
    new_image = "2026-06-01_(Mon)__05.30.00__Holiday__f2.8__T1_250__I200__C6D.jpg"
    assert (new_folder / new_image).exists()
    assert (new_folder / "__EXIF" / f"{new_image}._exif").exists()
    assert not (old_folder / image).exists()

    # Idempotent: a second run recomputes from EXIF and is a no-op.
    summary2 = retime_archive(parent, "2026-06-01", "2026-06-02", config)
    assert summary2["retimed"] == 0
    assert summary2["unchanged"] == 1
    assert (new_folder / new_image).exists()
