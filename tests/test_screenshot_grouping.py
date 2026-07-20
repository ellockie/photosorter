import subprocess
from pathlib import Path

import pytest

from src.core import PipelineContext
from src.pipeline_stages.screenshot_grouping import ScreenshotGroupingStage

PLACEHOLDER = " - 1. ######"


def make_context(tmp_path, enabled=True, python=None, project=None, max_folders=0):
    root = tmp_path / "__PHOTOS"
    root.mkdir(parents=True, exist_ok=True)
    return PipelineContext(
        config={
            "paths": {"root_folder": str(root)},
            "extensions": {
                "lossy_images": [".jpg", ".jpeg"],
                "other_images": [".png"],
                "raw_images": [".cr2"],
                "videos": [".mp4", ".mov"],
            },
            "legacy": {"date_folder_suffix": PLACEHOLDER},
            "screenshot_grouping": {
                "enabled": enabled,
                "python": str(python) if python else "",
                "project_path": str(project) if project else "",
                "max_folders": max_folders,
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
    (project / "main.py").write_text("", encoding="utf-8")
    return python, project


def make_event_folder(tmp_path, name, images=0, videos=0, with_raw_subdir=False):
    folder = tmp_path / "__PHOTOS" / "2026" / "07. July" / name
    folder.mkdir(parents=True)
    for i in range(images):
        (folder / f"img_{i}.jpg").write_bytes(b"x")
    for i in range(videos):
        (folder / f"vid_{i}.mp4").write_bytes(b"x")
    if with_raw_subdir:
        raw = folder / "__RAW"
        raw.mkdir()
        (raw / "orig.cr2").write_bytes(b"x")
    return folder


def affect(context, *folders):
    """Register folders as the ones folder-sorting touched this run."""
    context.affected_event_folders.update(folders)


def ok(cmd, **kwargs):
    return subprocess.CompletedProcess(cmd, 0)


def test_disabled_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("should not run"))
    context = make_context(tmp_path, enabled=False)
    ScreenshotGroupingStage().execute(context)
    assert any("disabled" in line for line in context.logs)


def test_missing_tool_skips(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("should not run"))
    context = make_context(tmp_path, python=tmp_path / "nope.exe", project=tmp_path / "nope")
    ScreenshotGroupingStage().execute(context)
    assert any("not available" in line for line in context.logs)


def test_renames_placeholder_and_launches_gui(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    folder = make_event_folder(tmp_path, f"2026-07-18_(Sat){PLACEHOLDER}", images=3, videos=1,
                               with_raw_subdir=True)

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append((cmd, k)) or ok(cmd))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, folder)

    ScreenshotGroupingStage().execute(context)

    renamed = tmp_path / "__PHOTOS" / "2026" / "07. July" / "2026-07-18_(Sat) - __TO_SPLIT__(i=3_v=1)"
    assert renamed.is_dir()
    assert not folder.exists()

    assert len(calls) == 1
    cmd, kwargs = calls[0]
    assert cmd == [str(python), str(project / "main.py"), "--alternative", str(renamed)]
    assert kwargs["cwd"] == str(project)
    assert context.counters["screenshot_folders_grouped"] == 1
    assert context.stage_stats["screenshot-grouping"] == {"inputs": 1, "outputs": 1, "errors": 0}
    # The renamed folder is recorded for the reconciliation stage.
    assert context.screenshot_grouped_folders == [renamed]


def test_only_affected_folders_are_touched(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    affected = make_event_folder(tmp_path, f"2026-07-18_(Sat){PLACEHOLDER}", images=1)
    # A second placeholder folder on disk that this run did NOT sort into
    make_event_folder(tmp_path, f"2026-07-01_(Wed){PLACEHOLDER}", images=1)

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd) or ok(cmd))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, affected)  # only the first is registered

    ScreenshotGroupingStage().execute(context)

    assert len(calls) == 1
    assert Path(calls[0][-1]).name.startswith("2026-07-18")
    assert (tmp_path / "__PHOTOS" / "2026" / "07. July" / f"2026-07-01_(Wed){PLACEHOLDER}").is_dir()


def test_labelled_folder_left_alone(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    trip = make_event_folder(tmp_path, "2026-07-18_(Sat) - Japan trip", images=2)

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("should not launch"))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, trip)

    ScreenshotGroupingStage().execute(context)

    assert context.counters["screenshot_folders_grouped"] == 0
    assert trip.is_dir()


def test_processes_folders_one_by_one_most_recent_first(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    a = make_event_folder(tmp_path, f"2026-07-18_(Sat){PLACEHOLDER}", images=1)
    b = make_event_folder(tmp_path, f"2026-07-19_(Sun){PLACEHOLDER}", images=1)

    order = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **k: order.append(Path(cmd[-1]).name) or ok(cmd))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, a, b)

    ScreenshotGroupingStage().execute(context)

    assert order == [
        "2026-07-19_(Sun) - __TO_SPLIT__(i=1)",
        "2026-07-18_(Sat) - __TO_SPLIT__(i=1)",
    ]
    assert context.counters["screenshot_folders_grouped"] == 2


def test_existing_to_split_folder_opened_without_rename(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    folder = make_event_folder(tmp_path, "2026-07-18_(Sat) - __TO_SPLIT__(i=2)", images=2)

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd) or ok(cmd))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, folder)

    ScreenshotGroupingStage().execute(context)

    assert calls[0][-1] == str(folder)
    assert folder.is_dir()


def test_folder_without_media_is_skipped(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    folder = make_event_folder(tmp_path, f"2026-07-18_(Sat){PLACEHOLDER}", with_raw_subdir=True)

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("should not launch"))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, folder)

    ScreenshotGroupingStage().execute(context)

    assert context.counters["screenshot_folders_grouped"] == 0
    assert any("no top-level media" in line for line in context.logs)


def test_launch_failure_isolated_and_recorded(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    a = make_event_folder(tmp_path, f"2026-07-18_(Sat){PLACEHOLDER}", images=1)
    b = make_event_folder(tmp_path, f"2026-07-19_(Sun){PLACEHOLDER}", images=1)

    results = iter([
        subprocess.CompletedProcess([], 1),  # first (most recent) fails
        subprocess.CompletedProcess([], 0),
    ])
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: next(results))
    context = make_context(tmp_path, python=python, project=project)
    affect(context, a, b)

    ScreenshotGroupingStage().execute(context)

    stats = context.stage_stats["screenshot-grouping"]
    assert stats["errors"] == 1
    assert context.counters["screenshot_folders_grouped"] == 1


def test_max_folders_caps_launches(tmp_path, monkeypatch, grouper_install):
    python, project = grouper_install
    a = make_event_folder(tmp_path, f"2026-07-18_(Sat){PLACEHOLDER}", images=1)
    b = make_event_folder(tmp_path, f"2026-07-19_(Sun){PLACEHOLDER}", images=1)
    c = make_event_folder(tmp_path, f"2026-07-20_(Mon){PLACEHOLDER}", images=1)

    calls = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **k: calls.append(cmd) or ok(cmd))
    context = make_context(tmp_path, python=python, project=project, max_folders=2)
    affect(context, a, b, c)

    ScreenshotGroupingStage().execute(context)

    assert len(calls) == 2  # most recent two only
    assert Path(calls[0][-1]).name.startswith("2026-07-20")
    assert Path(calls[1][-1]).name.startswith("2026-07-19")


def test_stage_in_default_pipeline_after_folder_sorting():
    from src.pipeline_stages import build_default_stages

    stages = build_default_stages()
    ids = [stage.stage_id for stage in stages]
    assert "screenshot-grouping" in ids
    stage = stages[ids.index("screenshot-grouping")]
    assert stage.dependencies == ("folder-sorting",)
