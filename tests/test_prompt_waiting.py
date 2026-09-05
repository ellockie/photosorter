"""The pipeline waits for user decisions instead of guessing past them.

Every prompt this pipeline raises exists because a human has to decide
something. These tests pin the two properties that matter: the wait is
unbounded, and the answer is actually acted on.
"""

import threading
import time
from pathlib import Path

import pytest

from src.core import \
    MediaAsset, \
    PipelineContext, \
    PipelineMode, \
    PipelinePaused, \
    default_config
from src.pipeline_stages.grouping_review import \
    GroupingReviewStage, \
    is_unnamed, \
    pending_folders, \
    reconcilable_folders, \
    review_scope
from src.pipeline_stages.rename_and_sort import RenameAndSortStage


def build_config(tmp_path: Path) -> dict:
    config = default_config()
    root = tmp_path / "archive"
    working = tmp_path / "pipeline"
    config["paths"].update({
        "root_folder": str(root),
        "working_folder": str(working),
        "inbox_folder": str(working / "INBOX"),
        "unsorted_folder": str(working / "INBOX"),
        "ready_folder": str(working / "READY"),
        "temp_folder": str(working / ".TMP"),
        "temp_root": str(working / ".TMP"),
    })
    return config


def answer_after(context: PipelineContext, prompt_id_holder, answer: dict, delay: float):
    """Answer whichever prompt the pipeline is blocked on, once it blocks."""
    def run():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            waiting = context.waiting_prompt_id
            if waiting is not None:
                prompt_id_holder.append(waiting)
                context.answer_prompt(waiting, answer)
                return
            time.sleep(0.02)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


# --------------------------------------------------------------------------
# The wait itself
# --------------------------------------------------------------------------

def test_await_prompt_blocks_until_answered_and_never_times_out():
    context = PipelineContext(config=default_config(), mode=PipelineMode.UI)
    prompt = context.create_prompt("demo", {})

    # Comfortably longer than any poll interval: a timeout would fire here.
    threading.Timer(1.2, lambda: context.answer_prompt(prompt.prompt_id, {"action": "go"})).start()

    started = time.monotonic()
    answer = context.await_prompt(prompt)
    waited = time.monotonic() - started

    assert answer == {"action": "go"}
    assert waited >= 1.1
    assert context.waiting_prompt_id is None


def test_await_prompt_reports_which_prompt_it_is_blocked_on():
    context = PipelineContext(config=default_config(), mode=PipelineMode.UI)
    prompt = context.create_prompt("demo", {})
    seen = []

    def watcher():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if context.waiting_prompt_id is not None:
                seen.append(context.waiting_prompt_id)
                context.answer_prompt(prompt.prompt_id, {})
                return
            time.sleep(0.02)

    thread = threading.Thread(target=watcher)
    thread.start()
    context.await_prompt(prompt)
    thread.join()

    assert seen == [prompt.prompt_id]


def test_abort_releases_a_waiting_stage():
    context = PipelineContext(config=default_config(), mode=PipelineMode.UI)
    prompt = context.create_prompt("demo", {})
    threading.Timer(0.3, context.request_abort).start()

    with pytest.raises(PipelinePaused):
        context.await_prompt(prompt)
    assert context.waiting_prompt_id is None


def test_headless_run_uses_the_declared_fallback_rather_than_hanging():
    context = PipelineContext(config=default_config(), mode=PipelineMode.CLI)
    prompt = context.create_prompt("demo", {})

    assert context.await_prompt(prompt, auto_answer={"action": "continue"}) == {"action": "continue"}
    assert prompt.answered
    assert any("continuing with" in line.lower() for line in context.logs)


def test_headless_run_without_a_fallback_pauses():
    context = PipelineContext(config=default_config(), mode=PipelineMode.CLI)
    prompt = context.create_prompt("demo", {})

    with pytest.raises(PipelinePaused):
        context.await_prompt(prompt)


# --------------------------------------------------------------------------
# Name collisions: the answer must actually be applied
# --------------------------------------------------------------------------

def _collision_context(tmp_path: Path) -> PipelineContext:
    """Two same-named-on-rename files whose age/size make the call ambiguous."""
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    metadata = {
        "image_datetime": "2026-05-14_(Thu)__10.30.00",
        "aperture": "f2.8",
        "exposure_time": "T1_250",
        "focal_length": "L50.0",
        "iso": "I100",
        "camera_symbol": "6D",
    }
    from src.pipeline_stages.legacy import legacy_filename
    target_name = legacy_filename(metadata, ".jpg", config)

    # Ambiguous: the newcomer is newer AND larger, so neither age nor size
    # rules, and the sizes stay within significantly_smaller_ratio.
    existing = inbox / target_name
    existing.write_text("x" * 900, encoding="utf-8")
    import os
    os.utime(existing, (1_000_000, 1_000_000))

    candidate = inbox / "IMG_0002.jpg"
    candidate.write_text("y" * 1200, encoding="utf-8")
    os.utime(candidate, (2_000_000, 2_000_000))

    context = PipelineContext(config=config, mode=PipelineMode.UI)
    asset = MediaAsset(candidate)
    asset.metadata.update(metadata)
    context.assets = [asset]
    return context


def test_collision_prompt_answer_renames_the_file_instead_of_skipping_it(tmp_path):
    context = _collision_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    answered = []
    thread = answer_after(context, answered, {"action": "keep_candidate"}, 0)

    RenameAndSortStage().execute(context)
    thread.join()

    assert answered, "the stage never blocked on the collision prompt"
    # keep_candidate: the newcomer takes the contested name, the sitting file
    # is demoted with the _DUPE grammar.
    assert context.counters["renamed_assets"] == 1
    assert context.assets[0].primary_path.parent == inbox
    assert "_DUPE_" not in context.assets[0].primary_path.name
    assert any("_DUPE_" in path.name for path in inbox.iterdir())


def test_collision_prompt_answer_can_leave_the_file_alone(tmp_path):
    context = _collision_context(tmp_path)
    original = context.assets[0].primary_path
    answered = []
    thread = answer_after(context, answered, {"action": "skip"}, 0)

    RenameAndSortStage().execute(context)
    thread.join()

    assert answered
    assert context.counters["rename_skipped_assets"] == 1
    assert original.exists(), "skipping must leave the file exactly where it was"


def test_cancelling_at_a_collision_stops_the_run(tmp_path):
    context = _collision_context(tmp_path)
    answered = []
    thread = answer_after(context, answered, {"action": "cancel"}, 0)

    with pytest.raises(PipelinePaused):
        RenameAndSortStage().execute(context)
    thread.join()


# --------------------------------------------------------------------------
# Grouping review
# --------------------------------------------------------------------------

def _event_tree(tmp_path: Path) -> tuple[dict, Path]:
    config = build_config(tmp_path)
    config["grouping_review"] = {"enabled": True}
    month = Path(config["paths"]["root_folder"]) / "2026" / "08. August"
    month.mkdir(parents=True)
    return config, month


def test_unnamed_folders_are_recognised(tmp_path):
    config, month = _event_tree(tmp_path)
    for name in (
        "2026-08-14_(Fri) - __TO_SPLIT__(i=7)",
        "2026-08-14_(Fri)__15.32.01 - __TO_LABEL__",
        "2026-08-14_(Fri) - 1. ######",
    ):
        assert is_unnamed(month / name, config), name
    assert not is_unnamed(month / "2026-08-14_(Fri)__15.32.01 - Kajaki", config)


def test_review_blocks_until_the_folders_are_named(tmp_path):
    config, month = _event_tree(tmp_path)
    unnamed = month / "2026-08-14_(Fri) - __TO_SPLIT__(i=2)"
    (unnamed / "__EXIF").mkdir(parents=True)
    named = month / "2026-08-14_(Fri)__15.32.01 - Kajaki"
    named.mkdir()

    context = PipelineContext(config=config, mode=PipelineMode.UI)
    context.screenshot_grouped_folders = [unnamed]

    def rename_then_rescan():
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            waiting = context.waiting_prompt_id
            if waiting is None:
                time.sleep(0.02)
                continue
            # Exactly what the user does in Explorer, then presses Re-scan.
            unnamed.rename(month / "2026-08-14_(Fri)__15.00.00 - Kajaki start")
            context.answer_prompt(waiting, {"action": "rescan"})
            return
    thread = threading.Thread(target=rename_then_rescan)
    thread.start()

    GroupingReviewStage().execute(context)
    thread.join()

    assert not pending_folders(context, review_scope(context))
    # The renamed folder still carries __EXIF, so it is queued for reconciliation
    # even though the path recorded before the GUI ran no longer exists.
    queued = {folder.name for folder in context.screenshot_grouped_folders}
    assert "2026-08-14_(Fri)__15.00.00 - Kajaki start" in queued


def test_review_can_be_fast_forwarded(tmp_path):
    config, month = _event_tree(tmp_path)
    unnamed = month / "2026-08-14_(Fri) - __TO_SPLIT__(i=2)"
    (unnamed / "__EXIF").mkdir(parents=True)

    context = PipelineContext(config=config, mode=PipelineMode.UI)
    context.screenshot_grouped_folders = [unnamed]
    answered = []
    thread = answer_after(context, answered, {"action": "continue"}, 0)

    GroupingReviewStage().execute(context)
    thread.join()

    assert answered
    assert unnamed.exists(), "fast-forward must not touch the folders"
    assert context.counters["grouping_review_pending"] == 1
    assert unnamed in context.screenshot_grouped_folders


def test_review_scope_never_leaves_the_days_this_run_touched(tmp_path):
    config, month = _event_tree(tmp_path)
    mine = month / "2026-08-14_(Fri) - __TO_SPLIT__(i=2)"
    (mine / "__EXIF").mkdir(parents=True)
    # An unnamed folder from some earlier session, months away.
    stale = month / "2026-03-02_(Mon) - __TO_SPLIT__(i=9)"
    (stale / "__EXIF").mkdir(parents=True)

    context = PipelineContext(config=config, mode=PipelineMode.CLI)
    context.affected_event_folders = {mine}

    scope = review_scope(context)
    assert pending_folders(context, scope) == [mine]
    assert stale not in reconcilable_folders(context, scope)


def test_review_is_a_no_op_when_nothing_was_grouped(tmp_path):
    config, _ = _event_tree(tmp_path)
    context = PipelineContext(config=config, mode=PipelineMode.UI)

    GroupingReviewStage().execute(context)

    assert context.screenshot_grouped_folders == []
    assert not context.prompt_queue


def test_day_boundary_neighbour_is_in_scope(tmp_path):
    config, month = _event_tree(tmp_path)
    grouped = month / "2026-08-14_(Fri) - __TO_SPLIT__(i=2)"
    grouped.mkdir(parents=True)
    # A group split off just after midnight lands on the next date.
    neighbour = month / "2026-08-15_(Sat)__00.10.00 - Late night"
    (neighbour / "__EXIF").mkdir(parents=True)

    context = PipelineContext(config=config, mode=PipelineMode.CLI)
    context.screenshot_grouped_folders = [grouped]

    assert neighbour in reconcilable_folders(context, review_scope(context))
