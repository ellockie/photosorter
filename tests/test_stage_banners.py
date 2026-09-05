"""Every stage announces itself on the way in and on the way out.

The rule is enforced by the orchestrator, not by the stages, so these tests
work against the orchestrator directly: a new stage cannot opt out, and a
failing one cannot skip its exit line.
"""

import pytest

from src.core import \
    PipelineContext, \
    PipelineMode, \
    PipelineOrchestrator, \
    PipelinePaused, \
    PipelineStage, \
    default_config
from src.pipeline_stages import build_default_stages
from src.utils.stage_banner import format_end, format_start


class _Recorded(PipelineStage):
    """A stage whose body is supplied by the test."""

    def __init__(self, stage_id, display_name, body=None, dependencies=()):
        super().__init__(
            stage_id=stage_id,
            display_name=display_name,
            dependencies=dependencies,
        )
        self._body = body

    def execute(self, context):
        if self._body is not None:
            self._body(context)
        return context


def run_with_banners(stages, mode=PipelineMode.CLI):
    lines = []
    context = PipelineContext(config=default_config(), mode=mode)
    orchestrator = PipelineOrchestrator(stages, mode=mode, announce=lines.append)
    error = None
    try:
        orchestrator.run(context)
    except Exception as caught:  # the banners are what is under test
        error = caught
    return lines, context, error


def starts(lines):
    return [line for line in lines if line.startswith(">>")]


def ends(lines):
    return [line for line in lines if line.startswith("<<")]


def test_a_stage_is_named_before_and_after_it_runs():
    lines, _, error = run_with_banners([_Recorded("alpha", "Alpha Stage")])

    assert error is None
    assert len(lines) == 2
    assert lines[0].startswith(">> STAGE 1/1")
    assert lines[1].startswith("<< STAGE 1/1")
    for line in lines:
        # Both halves carry the human name AND the id, so the transcript is
        # readable and greppable.
        assert "Alpha Stage" in line
        assert "[alpha]" in line
    assert "COMPLETE" in lines[1]


def default_graph_as_stubs():
    """The default graph's shape, with every stage body replaced by a no-op.

    The banner contract belongs to the orchestrator, so the real stage bodies
    are not just unnecessary here — running them would perform a real ingest
    against the paths in `default_config()`, which are the live archive.
    """
    return [
        _Recorded(stage.stage_id, stage.display_name, dependencies=stage.dependencies)
        for stage in build_default_stages()
    ]


def test_every_stage_in_the_default_pipeline_is_announced_twice():
    stages = default_graph_as_stubs()
    lines, _, _ = run_with_banners(stages)

    announced_start = {line.split("[", 1)[1].split("]", 1)[0] for line in starts(lines)}
    announced_end = {line.split("[", 1)[1].split("]", 1)[0] for line in ends(lines)}
    expected = {stage.stage_id for stage in stages}

    assert announced_start == expected
    assert announced_end == expected


def test_banners_are_paired_and_ordered():
    stages = [
        _Recorded("one", "One"),
        _Recorded("two", "Two", dependencies=("one",)),
        _Recorded("three", "Three", dependencies=("two",)),
    ]
    lines, _, _ = run_with_banners(stages)

    # Strictly alternating: no stage opens before the previous one closes.
    assert [line[:2] for line in lines] == [">>", "<<", ">>", "<<", ">>", "<<"]
    assert [line.split("[")[1].split("]")[0] for line in starts(lines)] == ["one", "two", "three"]


def test_a_failing_stage_still_gets_its_closing_banner():
    def explode(_context):
        raise RuntimeError("boom")

    stages = [
        _Recorded("ok", "Fine"),
        _Recorded("bad", "Broken", body=explode, dependencies=("ok",)),
    ]
    lines, _, error = run_with_banners(stages)

    assert isinstance(error, RuntimeError)
    closing = ends(lines)[-1]
    assert "FAILED" in closing
    assert "[bad]" in closing
    # The reason travels with the banner, so the console says why.
    assert "boom" in closing
    assert len(starts(lines)) == len(ends(lines))


def test_a_paused_stage_still_gets_its_closing_banner():
    def pause(_context):
        raise PipelinePaused("waiting on you")

    lines, _, error = run_with_banners([_Recorded("held", "Held", body=pause)])

    assert isinstance(error, PipelinePaused)
    closing = ends(lines)[-1]
    assert "PAUSED" in closing
    assert "[held]" in closing
    assert "waiting on you" in closing


def test_an_interrupt_still_gets_its_closing_banner():
    # KeyboardInterrupt is a BaseException, so no `except` in the orchestrator
    # catches it; only the finally-block can close the banner.
    def interrupt(_context):
        raise KeyboardInterrupt

    lines = []
    context = PipelineContext(config=default_config(), mode=PipelineMode.CLI)
    orchestrator = PipelineOrchestrator(
        [_Recorded("stopped", "Stopped", body=interrupt)],
        announce=lines.append,
    )
    with pytest.raises(KeyboardInterrupt):
        orchestrator.run(context)

    assert len(starts(lines)) == len(ends(lines)) == 1
    assert "ABORTED" in ends(lines)[0]


def test_position_counter_covers_the_whole_run():
    stages = default_graph_as_stubs()
    lines, _, _ = run_with_banners(stages)
    total = len(stages)

    assert starts(lines)[0].startswith(f">> STAGE {1:>{len(str(total))}}/{total}")
    assert f"/{total}" in ends(lines)[-1]


def test_banner_text_is_plain_and_stable():
    # Formatting is separate from printing, so captured banners never carry
    # ANSI escapes.
    start = format_start(3, 12, "rename-and-sort", "Rename and Sort")
    end = format_end(3, 12, "rename-and-sort", "Rename and Sort", "COMPLETE", 1.25)

    assert "\x1b" not in start and "\x1b" not in end
    assert start == ">> STAGE  3/12  START     Rename and Sort  [rename-and-sort]"
    assert end == "<< STAGE  3/12  COMPLETE  Rename and Sort  [rename-and-sort]  (1.2s)"


# --------------------------------------------------------------------------
# The sandbox that makes the two tests above safe
# --------------------------------------------------------------------------

def test_the_test_sandbox_reroots_the_default_config():
    # default_config() otherwise returns c:\__PHOTOS and the live Dropbox
    # Camera Uploads folder. A test that ran the real stages against those did
    # a real ingest; conftest re-roots them so that cannot happen again.
    paths = default_config()["paths"]
    assert not paths["root_folder"].lower().startswith("c:\__photos")
    assert "photosorter_tests_" in paths["root_folder"]


def test_file_primitives_refuse_to_touch_the_real_archive():
    from conftest import RealArchiveAccess

    from src import core

    with pytest.raises(RealArchiveAccess):
        core.safe_move(r"c:\__PHOTOS.jpg", r"c:\__PHOTOS.jpg")
    with pytest.raises(RealArchiveAccess):
        core.safe_delete(r"c:\__PHOTOS.jpg")
