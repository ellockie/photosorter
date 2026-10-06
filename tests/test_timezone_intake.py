"""Intake: re-dating asks once per proposed folder (camera-time-correction)."""

import datetime
import json
from pathlib import Path
from types import SimpleNamespace

from src.core import PipelineContext, PipelineMode
from src.pipeline_stages.timezone_and_travel import RETIME_PROMPT, TimezoneAndTravelStage

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "time_vectors.json").read_text(encoding="utf-8"))


def asset(name, camera, reading):
    return SimpleNamespace(primary_path=Path(name), metadata={
        "camera_symbol": camera, "captured_at": reading,
        "image_datetime": reading.strftime("%Y-%m-%d_(xxx)__%H.%M.%S")})


def context(tmp_path, answers, mode=PipelineMode.UI):
    config = {**VECTORS["corrections"][0]["config"], "paths": {"root_folder": str(tmp_path / "root")},
              "day_boundary_time": "04.44.44"}
    ctx = PipelineContext(config=config, mode=mode)
    ctx.assets = [
        asset("a.jpg", "ILC7R5", datetime.datetime(2026, 9, 27, 19, 8, 31)),
        asset("b.jpg", "ILC7R5", datetime.datetime(2026, 9, 27, 20, 20, 58)),
        asset("c.jpg", "ILC7R5", datetime.datetime(2026, 9, 26, 10, 0, 0)),
        asset("p.jpg", "SG23U", datetime.datetime(2026, 9, 27, 20, 0, 0)),
    ]
    asked = []
    if answers is not None:
        queue = list(answers)

        def await_prompt(prompt, auto_answer=None):
            assert prompt.prompt_type == RETIME_PROMPT
            asked.append(prompt.payload)
            return {"action": queue.pop(0)}
        ctx.await_prompt = await_prompt
    return ctx, asked


def stamps(ctx):
    return {a.primary_path.name: a.metadata["image_datetime"] for a in ctx.assets}


def test_yes_per_folder(tmp_path):
    ctx, asked = context(tmp_path, ["yes", "yes"])
    TimezoneAndTravelStage().execute(ctx)
    assert [payload["folder"] for payload in asked] == ["2026-09-26_(Sat)", "2026-09-27_(Sun)"]
    assert stamps(ctx)["a.jpg"] == "2026-09-27_(Sun)__20.09.51"
    assert stamps(ctx)["b.jpg"] == "2026-09-27_(Sun)__20.20.59"
    assert stamps(ctx)["c.jpg"] == "2026-09-26_(Sat)__11.01.20"
    assert stamps(ctx)["p.jpg"] == "2026-09-27_(xxx)__20.00.00"   # a mobile is never touched
    lines = "\n".join(asked[1]["lines"])
    assert "19.08.31 -> 2026-09-27_(Sun)__20.09.51" in lines and "Name order: chronological" in lines


def test_yes_to_all_asks_once(tmp_path):
    ctx, asked = context(tmp_path, ["all"])
    TimezoneAndTravelStage().execute(ctx)
    assert len(asked) == 1
    assert stamps(ctx)["a.jpg"] == "2026-09-27_(Sun)__20.09.51"


def test_no_keeps_camera_time_and_lists_it_for_later(tmp_path):
    ctx, _ = context(tmp_path, ["no", "yes"])
    TimezoneAndTravelStage().execute(ctx)
    assert stamps(ctx)["c.jpg"] == "2026-09-26_(xxx)__10.00.00"
    assert stamps(ctx)["a.jpg"] == "2026-09-27_(Sun)__20.09.51"
    pending = next((tmp_path / "root" / "2026" / "__LOGS").glob("retime_pending_*.txt")).read_text(encoding="utf-8")
    assert "2026-09-26_(Sat)__10.00.00 -> 2026-09-26_(Sat)__11.01.20" in pending and "c.jpg" in pending


def test_headless_run_declines(tmp_path):
    ctx, _ = context(tmp_path, None, mode=PipelineMode.CLI)
    TimezoneAndTravelStage().execute(ctx)
    assert stamps(ctx)["a.jpg"] == "2026-09-27_(xxx)__19.08.31"
    assert ctx.counters["timezone_declined_assets"] == 3
