import subprocess
from pathlib import Path

import pytest

from src.core import PipelineContext
from src.pipeline_stages.screenshot_grouping import ScreenshotGroupingStage


def make_context(tmp_path, enabled=True, python=None, project=None, targets=None):
    camera_uploads = tmp_path / "Camera Uploads"
    camera_uploads.mkdir(parents=True, exist_ok=True)
    return PipelineContext(
        config={
            "paths": {
                "camera_uploads": str(camera_uploads),
                "ingest": {"camera_uploads": str(camera_uploads)},
            },
            "screenshot_grouping": {
                "enabled": enabled,
                "python": str(python) if python else "",
                "project_path": str(project) if project else "",
                "target_folders": targets if targets is not None else [
                    "_Other images/_POTENTIAL_TEXT_SCREENSHOTS",
                    "_Other images/_POTENTIAL_INFOGRAPHICS",
                ],
            },
        },
    )


@pytest.fixture
def grouper_install(tmp_path):
    python = tmp_path / "venv" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    project = tmp_path / "grouper-project"
    project.mkdir()
    return python, project


def completed(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args, returncode, stdout, stderr)


def test_disabled_skips_without_invoking_tool(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called when disabled")

    monkeypatch.setattr(subprocess, "run", explode)
    context = make_context(tmp_path, enabled=False)

    ScreenshotGroupingStage().execute(context)

    assert context.stage_stats["screenshot-grouping"] == {"inputs": 0, "outputs": 0, "errors": 0}
    assert any("disabled" in line for line in context.logs)


def test_missing_tool_skips_gracefully(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called when tool is missing")

    monkeypatch.setattr(subprocess, "run", explode)
    context = make_context(tmp_path, python=tmp_path / "nope" / "python.exe")

    ScreenshotGroupingStage().execute(context)

    assert any("not available" in line for line in context.logs)


def test_groups_each_existing_target_folder(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    camera_uploads = tmp_path / "Camera Uploads"
    screenshots = camera_uploads / "_Other images" / "_POTENTIAL_TEXT_SCREENSHOTS"
    screenshots.mkdir(parents=True)
    # _POTENTIAL_INFOGRAPHICS deliberately absent

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return completed(command, stdout="All-days batch done: moved 7 file(s) across 3 day(s)")

    monkeypatch.setattr(subprocess, "run", fake_run)
    context = make_context(tmp_path, python=python, project=project)

    ScreenshotGroupingStage().execute(context)

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == [
        str(python), "-m", "screenshot_grouper.daily_batch", "--all", str(screenshots)]
    assert kwargs["cwd"] == str(project)
    assert context.counters["screenshots_grouped"] == 7
    assert context.stage_stats["screenshot-grouping"] == {"inputs": 7, "outputs": 7, "errors": 0}
    assert any("skipping" in line and "_POTENTIAL_INFOGRAPHICS" in line for line in context.logs)


def test_tool_failure_recorded_not_raised(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    camera_uploads = tmp_path / "Camera Uploads"
    (camera_uploads / "_Other images" / "_POTENTIAL_TEXT_SCREENSHOTS").mkdir(parents=True)
    (camera_uploads / "_Other images" / "_POTENTIAL_INFOGRAPHICS").mkdir(parents=True)

    responses = iter([
        completed([], returncode=1, stderr="Traceback: boom"),
        completed([], stdout="All-days batch done: moved 2 file(s) across 1 day(s)"),
    ])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: next(responses))
    context = make_context(tmp_path, python=python, project=project)

    ScreenshotGroupingStage().execute(context)

    assert context.stage_stats["screenshot-grouping"]["errors"] == 1
    assert context.counters["screenshots_grouped"] == 2
    assert any("failed" in line for line in context.logs)


def test_absolute_target_folder_kept_as_is(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    external = tmp_path / "external-screenshots"
    external.mkdir()

    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return completed(command, stdout="All-days batch done: moved 1 file(s) across 1 day(s)")

    monkeypatch.setattr(subprocess, "run", fake_run)
    context = make_context(
        tmp_path, python=python, project=project, targets=[str(external)])

    ScreenshotGroupingStage().execute(context)

    assert calls[0][-1] == str(external)


def test_stage_in_default_pipeline_after_folder_sorting():
    from src.pipeline_stages import build_default_stages

    stages = build_default_stages()
    ids = [stage.stage_id for stage in stages]
    assert "screenshot-grouping" in ids
    stage = stages[ids.index("screenshot-grouping")]
    assert stage.dependencies == ("folder-sorting",)
