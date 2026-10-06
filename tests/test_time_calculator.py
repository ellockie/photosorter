"""The calculator page's JS gives the engine's answers (camera-time-correction, T8 by test)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from src.pipeline_stages.timezone_engine import calculate, country_zones

ROOT = Path(__file__).resolve().parents[1]
VECTORS = json.loads((ROOT / "tests" / "fixtures" / "time_vectors.json").read_text(encoding="utf-8"))
ENGINE_JS = ROOT / "tools" / "time_calculator_engine.js"

RUNNER = r"""
const calc = require(process.argv[1]);
const cases = JSON.parse(require("fs").readFileSync(0, "utf8"));
console.log(JSON.stringify(cases.map(c => { const r = calc.calculate(c); return {state: r.state, error: r.error, stamp: r.stamp}; })));
"""


def _zone(place):
    return place if "/" in place else country_zones(place)[0]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_js_engine_matches_the_python_engine():
    cases = []
    for case in VECTORS["calculator"]:
        cases.append({"home": _zone("GB"), "location": _zone(case["location"]), "reading": case["reading"],
                      "reference": case.get("reference"), "state": case.get("state"), "error": case.get("error", 0)})
    output = subprocess.run(["node", "-e", RUNNER, str(ENGINE_JS)], input=json.dumps(cases),
                            capture_output=True, text=True, check=True).stdout
    results = json.loads(output)
    for case, js in zip(VECTORS["calculator"], results):
        python = calculate("GB", case["location"], case["reading"], case.get("reference"),
                           case.get("state"), case.get("error", 0))
        assert js == python, case["name"]
        for key, value in case["expect"].items():
            assert js[key] == value, (case["name"], key)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_js_accepts_a_bare_clock_time():
    """A clock in a photo shows a time, not a date: the nearest day is taken."""
    case = {"home": "Europe/London", "location": "Europe/London",
            "reading": "2026-09-27_(Sun)__19.08.31.774", "reference": "20:09:52.208"}
    output = subprocess.run(["node", "-e", RUNNER, str(ENGINE_JS)], input=json.dumps([case]),
                            capture_output=True, text=True, check=True).stdout
    assert json.loads(output) == [{"state": "home-winter", "error": -80, "stamp": "2026-09-27_(Sun)__20.09.51"}]


def test_page_is_self_contained(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_time_calculator", ROOT / "tools" / "build_time_calculator.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    page = module.build()
    assert "/*ENGINE*/" not in page and "/*COUNTRIES*/" not in page
    assert '"JP":["Japan",["Asia/Tokyo"]]' in page
    assert "http://" not in page and "https://" not in page and "<link" not in page
