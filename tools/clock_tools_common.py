"""Shared start-up for the read-only clock tools (evidence report, visualiser).

Loads ``src``'s leaf modules without running ``src.pipeline_stages.__init__``
(which imports every pipeline stage), reads ``config.json`` with
``timezone.json`` overlaid, and scans the photo roots -- merging folders that
appear under more than one root into one entry, as the visualiser shows them.
"""

import datetime
import importlib
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_src():
    """Make ``src`` importable as stub packages, leaving their ``__init__`` unrun."""
    for name, folder in (
        ("src", REPO_ROOT / "src"),
        ("src.pipeline_stages", REPO_ROOT / "src" / "pipeline_stages"),
    ):
        if name in sys.modules:
            continue
        spec = importlib.machinery.ModuleSpec(name, None, is_package=True)
        module = importlib.util.module_from_spec(spec)
        module.__path__ = [str(folder)]
        sys.modules[name] = module


load_src()
core = importlib.import_module("src.core")
engine = importlib.import_module("src.pipeline_stages.timezone_engine")
clock_readings = importlib.import_module("src.pipeline_stages.clock_readings")


def load_config(config_path=None, timezone_path=None) -> dict:
    """``config.json`` with ``timezone.json`` overlaid -- or another timezone file, to try one out."""
    config = core.load_config(config_path)
    if timezone_path:
        import json
        data = json.loads(Path(timezone_path).read_text(encoding="utf-8"))
        for key in (*engine.TIMEZONE_KEYS, *engine.SUPERSEDED_KEYS):
            config.pop(key, None)
            if key in data:
                config[key] = data[key]
    return config


def roots_from(config: dict, given) -> list[Path]:
    """The roots to scan: those given, else every configured photo root."""
    if given:
        return [Path(root) for root in given]
    roots = core.photo_roots(config)
    return roots or [Path(config["paths"]["root_folder"])]


def parse_day(text):
    if not text:
        return None
    return datetime.datetime.fromisoformat(str(text))


MergedFolder = clock_readings.MergedFolder
scan_roots = clock_readings.scan_roots
in_range = clock_readings.in_range


def report_path(roots, years, name: str) -> Path:
    """Where a report goes: the year's ``__LOGS`` for a single year (J1), else per user."""
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    if years and len(years) == 1 and roots and roots[0].exists():
        return roots[0] / str(years[0]) / clock_readings.LOGS_FOLDER / f"{name}_{stamp}.txt"
    return clock_readings.cache_path_for(Path("reports")).parent.parent / "reports" / f"{name}_{stamp}.txt"
