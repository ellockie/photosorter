"""Camera clocks, trips and calibrations (openspec change camera-time-correction).

Most cases live in ``tests/fixtures/time_vectors.json``: the calculator page is
held to the same file, so the two implementations cannot drift apart (T8).
"""

import datetime
import json
from pathlib import Path

import pytest

from src.pipeline_stages.geolocation import location_info, write_location_stamp
from src.pipeline_stages.stamps import parse_stamp
from src.pipeline_stages.timezone_engine import (
    TimeModel,
    TimezoneConfigError,
    calculate,
    country_zones,
    has_timezone_config,
    resolve_place,
    validate_timezone_config,
)

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "time_vectors.json").read_text(encoding="utf-8"))


def _config(case, cases):
    config = case["config"]
    while isinstance(config, str) and config.startswith("@"):
        config = cases[int(config[1:])]["config"]
    return config


@pytest.mark.parametrize("case", VECTORS["corrections"], ids=lambda case: case["name"])
def test_correction_vectors(case):
    model = TimeModel(_config(case, VECTORS["corrections"]))
    assert model.errors == []
    result = model.correct(case["camera"], parse_stamp(case["reading"]), case.get("counter"))
    expect = case["expect"]
    assert result.stamp_text == expect["stamp"]
    if "error" in expect:
        assert result.error_seconds == expect["error"]
    if "source" in expect:
        assert result.source == expect["source"]
    if "ambiguous" in expect:
        assert result.ambiguous is expect["ambiguous"]


@pytest.mark.parametrize("case", VECTORS["config_errors"], ids=lambda case: case["name"])
def test_config_error_vectors(case):
    model = TimeModel(case["config"])
    assert any(case["contains"] in message for message in model.errors), model.errors


@pytest.mark.parametrize("case", VECTORS["config_warnings"], ids=lambda case: case["name"])
def test_config_warning_vectors(case):
    model = TimeModel(case["config"])
    assert model.errors == []
    assert any(case["contains"] in message for message in model.warnings), model.warnings


@pytest.mark.parametrize("case", VECTORS["calculator"], ids=lambda case: case["name"])
def test_calculator_vectors(case):
    result = calculate("GB", case["location"], case["reading"], case.get("reference"),
                       case.get("state"), case.get("error", 0))
    for key, value in case["expect"].items():
        assert result[key] == value


def test_country_resolution():
    assert resolve_place("JP").key == "Asia/Tokyo"
    assert resolve_place("gb").key == "Europe/London"
    assert resolve_place("Europe/Warsaw").key == "Europe/Warsaw"
    # Zones that have kept identical time collapse into the principal one.
    assert country_zones("DE") == ["Europe/Berlin"]
    # Genuinely different ones do not: the Canaries are an hour behind Madrid.
    assert "Atlantic/Canary" in country_zones("ES")
    with pytest.raises(TimezoneConfigError, match="America/Los_Angeles"):
        resolve_place("US")
    with pytest.raises(TimezoneConfigError):
        resolve_place("XX")


def test_home_dst_is_the_zones_own():
    model = TimeModel({"home": "GB"})
    changes = model.dst_changes(datetime.datetime(2026, 1, 1), datetime.datetime(2027, 1, 1))
    assert [(change[0], change[3]) for change in changes] == [
        (datetime.datetime(2026, 3, 29, 1, tzinfo=datetime.timezone.utc), datetime.timedelta(hours=1)),
        (datetime.datetime(2026, 10, 25, 1, tzinfo=datetime.timezone.utc), datetime.timedelta(0)),
    ]


def test_declared_offset_is_never_an_input():
    """The engine has no parameter through which a declared offset could enter."""
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "X", "clock": "home-winter"}]})
    import inspect
    assert list(inspect.signature(model.correct).parameters) == ["camera", "reading", "counter"]


def test_has_timezone_config_gates_identity():
    assert has_timezone_config({"trips": [{"country": "JP"}]}) is True
    assert has_timezone_config({"home": "GB", "mobiles": ["SG23U"]}) is False


def test_validate_reports_errors_first():
    messages = validate_timezone_config({"camera_clock_sets": [], "home": "GB"})
    assert messages and messages[0].startswith("ERROR:")


def test_geolocation_stamp_projection(tmp_path):
    metadata = {"location_zone": "Asia/Tokyo"}
    info = location_info(metadata)
    assert info == {"zone": "Asia/Tokyo"}
    event_folder = tmp_path / "2026-04-12_(Sun)"
    stamp = write_location_stamp(event_folder, {}, info)
    assert json.loads(stamp.read_text(encoding="utf-8"))["zone"] == "Asia/Tokyo"


def test_timezone_data_lives_in_dedicated_file(tmp_path):
    from src.core import load_config, save_config

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"paths": {"root_folder": str(tmp_path / "P")}}), encoding="utf-8")
    (tmp_path / "timezone.json").write_text(json.dumps({
        "home": "GB",
        "trips": [{"country": "JP", "from": "2026-04-11_(Sat)__07.12.40", "to": "2026-04-20_(Mon)__21.03.11"}],
    }), encoding="utf-8")

    config = load_config(str(cfg_path))
    assert config["trips"][0]["country"] == "JP"

    config.setdefault("camera_symbols", {})["X"] = "Y"
    save_config(config, str(cfg_path))
    saved_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert not any(key in saved_cfg for key in ("home", "trips", "camera_clocks", "calibrations", "mobiles"))
    saved_tz = json.loads((tmp_path / "timezone.json").read_text(encoding="utf-8"))
    assert saved_tz["trips"][0]["country"] == "JP"


def test_repo_timezone_file_is_valid():
    data = json.loads((Path(__file__).parents[1] / "timezone.json").read_text(encoding="utf-8"))
    assert TimeModel(data).errors == []
