"""What a run says about itself, so a reader never has to guess.

Three separate promises, tested separately because they fail separately:

  * every stage carries a description, so the dashboard can say what is
    running without the reader opening the source;
  * every stage that runs gets a timing, so "which stage ate the 22 minutes"
    always has an answer -- including for the stage that died;
  * a long stage publishes progress while it runs, so it cannot be mistaken
    for a hang.

The last one matters most for safety-validation, which re-reads the whole
archive and, before this, said nothing at all for the entire time.
"""

import time
from pathlib import Path

import pytest

from src.core import \
    CatastrophicSafetyError, \
    PipelineContext, \
    PipelineMode, \
    PipelineOrchestrator, \
    PipelineStage, \
    SafetyValidationStage, \
    default_config
from src.pipeline_stages import build_default_stages
from src.pipeline_stages.default import build_default_orchestrator
from src.pipeline_stages.initialization import InitializationStage
from src.utils.progress import \
    StageProgress, \
    format_bytes, \
    format_count, \
    format_duration
from src.utils.stage_banner import format_end, format_stats

from test_pipeline_core import make_context


class _Body(PipelineStage):
    """A stage whose body the test supplies."""

    def __init__(self, stage_id="worker", body=None, **kwargs):
        super().__init__(stage_id=stage_id, display_name=stage_id.title(), **kwargs)
        self._body = body

    def execute(self, context):
        if self._body:
            self._body(context)
        return context


def run(stages, mode=PipelineMode.CLI):
    context = PipelineContext(config=default_config(), mode=mode)
    orchestrator = PipelineOrchestrator(stages, mode=mode, announce=lambda _line: None)
    error = None
    try:
        orchestrator.run(context)
    except Exception as caught:
        error = caught
    return context, error


# --------------------------------------------------------------------------
# Every stage says what it is for
# --------------------------------------------------------------------------

def test_every_default_stage_describes_itself():
    missing = [
        stage.stage_id
        for stage in build_default_stages()
        if not (stage.description or "").strip()
    ]
    assert missing == [], f"stages with no description: {missing}"


def test_descriptions_are_sentences_not_restated_names():
    for stage in build_default_stages():
        assert len(stage.description) > 40, f"{stage.stage_id} description is too thin"
        # A description that is just the display name back again tells a
        # reader nothing they could not read off the node already.
        assert stage.description.strip().lower() != stage.display_name.lower()


def test_the_graph_endpoint_carries_the_description_and_position():
    nodes = build_default_orchestrator().graph()["nodes"]
    assert all(node["description"] for node in nodes)
    assert [node["position"] for node in nodes] == list(range(1, len(nodes) + 1))


def test_the_slowest_stage_warns_that_it_is_slow():
    # The one stage whose cost surprises people has to say so up front.
    safety = next(
        stage for stage in build_default_stages()
        if stage.stage_id == "safety-validation"
    )
    assert "slow" in safety.description.lower()
    assert "archive" in safety.description.lower()


# --------------------------------------------------------------------------
# Timing: recorded by the orchestrator, so no stage can skip it
# --------------------------------------------------------------------------

def test_a_stage_records_when_it_ran_and_for_how_long():
    context, error = run([_Body("alpha", body=lambda _c: time.sleep(0.01))])

    assert error is None
    timing = context.stage_timings["alpha"]
    assert timing["outcome"] == "COMPLETE"
    assert timing["duration_seconds"] >= 0.005
    assert timing["started_at"] <= timing["finished_at"]
    assert timing["position"] == 1


def test_a_failing_stage_is_still_timed():
    """The duration of a stage that died is the most useful one there is."""
    def explode(_context):
        raise RuntimeError("boom")

    context, error = run([_Body("bad", body=explode)])

    assert isinstance(error, RuntimeError)
    timing = context.stage_timings["bad"]
    assert timing["outcome"] == "FAILED"
    assert timing["duration_seconds"] is not None
    assert "boom" in timing["detail"]


def test_the_run_summary_ranks_the_stages_by_time():
    context, _ = run([
        _Body("quick", body=lambda _c: None),
        _Body("slow", body=lambda _c: time.sleep(0.05), dependencies=("quick",)),
    ])

    run_summary = context.stage_timings["__run__"]
    assert run_summary["stages_run"] == 2
    assert run_summary["stage_count"] == 2
    assert run_summary["slowest"][0]["stage_id"] == "slow"
    assert run_summary["duration_seconds"] > 0


def test_the_run_is_summarised_even_when_it_dies_midway():
    """An aborted run is exactly when you want to know where the time went."""
    def explode(_context):
        raise RuntimeError("boom")

    context, error = run([
        _Body("ok", body=lambda _c: time.sleep(0.02)),
        _Body("bad", body=explode, dependencies=("ok",)),
    ])

    assert isinstance(error, RuntimeError)
    summary = context.stage_timings["__run__"]
    assert summary["stages_run"] == 2
    assert "duration_seconds" in summary
    assert any("Run finished in" in line for line in context.logs)


def test_the_description_is_logged_when_the_stage_starts():
    context, _ = run([_Body("alpha", description="Does the alpha thing to files.")])
    assert "  Does the alpha thing to files." in context.logs


# --------------------------------------------------------------------------
# Progress: published while the stage runs, cleared when it ends
# --------------------------------------------------------------------------

def test_progress_reports_share_rate_and_eta():
    context = PipelineContext(config=default_config())
    # publish_interval_seconds=0 defeats the throttle, so the record under
    # test is the latest advance rather than whatever the timer let through.
    reporter = StageProgress(context, "worker", "Hashing", total=100,
                             total_bytes=1000, publish_interval_seconds=0)
    for _ in range(25):
        reporter.advance(size_bytes=10)

    record = context.stage_progress["worker"]
    assert record["done"] == 25
    assert record["fraction"] == pytest.approx(0.25)
    assert record["bytes_done"] == 250
    assert record["eta_seconds"] > 0
    assert record["byte_rate"] > 0
    assert "25/100" in record["summary"]
    assert "25%" in record["summary"]


def test_progress_without_a_total_is_open_ended_not_zero():
    """A stage that cannot know its total yet must not look stuck at 0%."""
    context = PipelineContext(config=default_config())
    reporter = StageProgress(context, "walker", "Scanning")
    reporter.advance()

    record = context.stage_progress["walker"]
    assert record["total"] is None
    assert record["fraction"] is None
    assert record["eta_seconds"] is None


def test_a_finished_stage_has_no_stale_progress_bar():
    """Leaving the bar up makes a completed stage look mid-flight."""
    def work(context):
        reporter = context.progress("worker", "Working", total=2)
        reporter.advance()
        assert "worker" in context.stage_progress

    context, _ = run([_Body("worker", body=work)])
    assert "worker" not in context.stage_progress


def test_progress_lines_reach_the_log_but_only_for_big_work():
    context = PipelineContext(config=default_config())
    # A handful of items is over before a progress line would help.
    small = StageProgress(context, "small", "Working", total=3, log_interval_seconds=0)
    small.advance()
    assert context.logs == []

    big = StageProgress(context, "big", "Working", total=500, log_interval_seconds=0)
    big.advance()
    assert any(line.strip().startswith("...") for line in context.logs)


def test_finish_returns_a_line_naming_the_whole_span():
    context = PipelineContext(config=default_config())
    reporter = StageProgress(context, "worker", "Checksumming archive", total=4)
    for _ in range(4):
        reporter.advance(size_bytes=1024)

    line = reporter.finish()
    assert "Checksumming archive" in line
    assert "4 files" in line
    assert "4.0 KB" in line


# --------------------------------------------------------------------------
# The stage this whole change is about
# --------------------------------------------------------------------------

def make_archive(tmp_path):
    context = make_context(tmp_path)
    unsorted = Path(context.config["paths"]["unsorted_folder"])
    ready = Path(context.config["paths"]["ready_folder"])
    unsorted.mkdir(parents=True)
    ready.mkdir(parents=True)
    return context, unsorted, ready


def test_safety_validation_says_what_it_is_reading_and_why(tmp_path):
    context, unsorted, ready = make_archive(tmp_path)
    for index in range(3):
        (unsorted / f"IN_{index}.jpg").write_text(f"photo {index}", encoding="utf-8")
        (ready / f"OUT_{index}.jpg").write_text(f"photo {index}", encoding="utf-8")
    context.snapshot_inputs([unsorted])
    for path in unsorted.glob("*.jpg"):
        path.unlink()

    SafetyValidationStage().execute(context)

    log = "\n".join(context.logs)
    # The cost, stated before it is paid.
    assert "Verifying 3 ingested file(s)" in log
    assert "costs the size of the archive" in log
    # What it actually read, per root, so a slow run can be attributed.
    assert "files, " in log
    assert "Checksumming archive" in log
    assert "All 3 ingested file(s) accounted for" in log

    stats = context.stage_stats["safety-validation"]
    assert stats["inputs"] == 3
    assert stats["outputs"] == 3
    assert stats["errors"] == 0
    assert stats["scanned"] == 3
    assert stats["bytes_read"] > 0
    assert context.counters["safety_inputs_matched"] == 3


def test_safety_validation_reads_each_file_once_across_nested_roots(tmp_path):
    """READY and INBOX sit inside root_folder in the default layout.

    Walking all three roots therefore reaches the same file two or three
    times, and hashing it again reads the same bytes for no new proof. The
    reported scan count is what makes that visible, so it is what is pinned.
    """
    context, unsorted, ready = make_archive(tmp_path)
    root = Path(context.config["paths"]["root_folder"])
    assert ready.is_relative_to(root) and unsorted.is_relative_to(root), (
        "this test is only meaningful while the roots nest"
    )
    (unsorted / "A.jpg").write_text("photo a", encoding="utf-8")
    (ready / "B.jpg").write_text("photo b", encoding="utf-8")
    context.snapshot_inputs([unsorted])
    (unsorted / "A.jpg").rename(ready / "A.jpg")

    SafetyValidationStage().execute(context)

    assert context.stage_stats["safety-validation"]["scanned"] == 2
    assert context.counters["safety_files_scanned"] == 2


def test_safety_validation_skips_the_hashing_when_nothing_was_ingested(tmp_path):
    """No inputs to find means reading every byte proves nothing.

    The walk still happens -- zero-byte outputs are still caught -- but the
    expensive half is skipped and the log says so rather than leaving a reader
    wondering why the slow stage was fast this time.
    """
    context, _unsorted, ready = make_archive(tmp_path)
    (ready / "OLD.jpg").write_text("already here", encoding="utf-8")

    SafetyValidationStage().execute(context)

    log = "\n".join(context.logs)
    assert "Nothing was ingested this run" in log
    assert "Skipped checksumming" in log
    assert context.counters.get("safety_bytes_read", 0) == 0


def test_safety_validation_still_catches_zero_byte_outputs_with_no_ingest(tmp_path):
    context, _unsorted, ready = make_archive(tmp_path)
    (ready / "BROKEN.jpg").write_bytes(b"")

    with pytest.raises(CatastrophicSafetyError):
        SafetyValidationStage().execute(context)


def test_safety_validation_records_its_findings_for_the_node(tmp_path):
    context, unsorted, ready = make_archive(tmp_path)
    (unsorted / "A.jpg").write_text("photo", encoding="utf-8")
    (ready / "A.jpg").write_text("photo", encoding="utf-8")
    context.snapshot_inputs([unsorted])
    (unsorted / "A.jpg").unlink()

    SafetyValidationStage().execute(context)

    notes = context.stage_notes["safety-validation"]
    assert any("accounted for" in note for note in notes)


# --------------------------------------------------------------------------
# Intake reporting
# --------------------------------------------------------------------------

def test_initialization_counts_files_not_snapshot_entries(tmp_path):
    """Byte-identical inputs share one snapshot entry.

    Counting entries reported 251 for a 600-file intake, which read as though
    349 files had gone missing before the run even started.
    """
    context, unsorted, _ready = make_archive(tmp_path)
    (unsorted / "A.jpg").write_text("same bytes", encoding="utf-8")
    (unsorted / "B.jpg").write_text("same bytes", encoding="utf-8")
    (unsorted / "C.jpg").write_text("other bytes", encoding="utf-8")

    InitializationStage().execute(context)

    assert context.counters["input_files"] == 3
    assert context.counters["input_checksums"] == 2
    assert context.counters["input_duplicate_files"] == 1
    assert context.counters["input_bytes"] > 0
    # And it is explained, not just counted.
    assert any("byte-identical" in note for note in context.stage_notes["initialization"])


def test_snapshot_inputs_reports_progress_when_given_a_stage(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    for index in range(4):
        (unsorted / f"F{index}.jpg").write_text(f"bytes {index}", encoding="utf-8")

    tally = context.snapshot_inputs([unsorted], stage_id="initialization")

    assert tally["files"] == 4
    assert tally["unique"] == 4
    assert tally["bytes"] > 0
    record = context.stage_progress["initialization"]
    assert record["finished"] is True
    assert record["done"] == 4


# --------------------------------------------------------------------------
# The console transcript carries the same numbers as the dashboard
# --------------------------------------------------------------------------

def test_the_closing_banner_carries_the_stage_stats():
    line = format_end(
        3, 12, "rename-and-sort", "Rename and Sort", "COMPLETE", 1.25,
        stats={"inputs": 1200, "outputs": 1198, "errors": 2, "skipped": 4},
    )
    assert "in 1,200" in line
    assert "out 1,198" in line
    assert "err 2" in line
    assert "skipped 4" in line


def test_a_banner_without_stats_is_unchanged():
    # The old format is load-bearing for anything already parsing transcripts.
    assert format_end(3, 12, "rename-and-sort", "Rename and Sort", "COMPLETE", 1.25) == (
        "<< STAGE  3/12  COMPLETE  Rename and Sort  [rename-and-sort]  (1.2s)"
    )


def test_zero_errors_are_dropped_from_the_banner():
    """"err 0" on twenty lines hides the one line that says "err 3"."""
    line = format_stats({"inputs": 5, "outputs": 5, "errors": 0})
    assert "err" not in line
    assert line == "in 5, out 5"


# --------------------------------------------------------------------------
# Human-readable numbers
# --------------------------------------------------------------------------

@pytest.mark.parametrize("seconds,expected", [
    (0.4, "<1s"), (42, "42s"), (200, "3m 20s"), (3840, "1h 04m"),
])
def test_durations_read_like_a_person_would_say_them(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize("value,expected", [
    (512, "512 B"), (2048, "2.0 KB"), (5 * 1024 ** 3, "5.0 GB"),
])
def test_byte_sizes_read_like_a_person_would_say_them(value, expected):
    assert format_bytes(value) == expected


def test_large_counts_get_thousands_separators():
    # 120000 and 12000 are the same shape at a glance and a factor of ten apart.
    assert format_count(120000) == "120,000"
