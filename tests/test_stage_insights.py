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

import os
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
    default_config, \
    file_md5
from src.pipeline_stages import build_default_stages
from src.pipeline_stages.default import build_default_orchestrator
from src.pipeline_stages.initialization import InitializationStage
from src.pipeline_stages.legacy_unsorted_migration import LegacyUnsortedMigrationStage
from src.pipeline_stages.upload_harvest import UploadHarvestStage
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


def test_the_snapshot_records_which_folders_the_files_came_from(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    (unsorted / "LOOSE.jpg").write_text("loose", encoding="utf-8")
    trip = unsorted / "Japan 2026"
    nested = trip / "Kyoto"
    nested.mkdir(parents=True)
    (trip / "A.jpg").write_text("a", encoding="utf-8")
    (trip / "B.jpg").write_text("b", encoding="utf-8")
    (nested / "C.jpg").write_text("c", encoding="utf-8")

    tally = context.snapshot_inputs([unsorted])

    by_path = {entry["path"]: entry for entry in tally["folders"]}
    assert set(by_path) == {unsorted, trip, nested}
    assert by_path[unsorted]["files"] == 1
    assert by_path[trip]["files"] == 2
    assert by_path[nested]["files"] == 1
    assert all(entry["bytes"] > 0 for entry in tally["folders"])
    # The root each folder was reached under travels with it, so the caller
    # can show a relative path without re-deriving which root that was.
    assert {entry["root"] for entry in tally["folders"]} == {unsorted}


def test_folders_are_listed_in_path_order_so_siblings_stay_together(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    for name in ("Zebra", "Alpha", "Middle"):
        (unsorted / name).mkdir()
        (unsorted / name / "X.jpg").write_text(name, encoding="utf-8")

    tally = context.snapshot_inputs([unsorted])

    listed = [entry["path"].name for entry in tally["folders"]]
    assert listed == sorted(listed, key=str.lower)


def test_initialization_names_the_folders_the_intake_came_from(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    (unsorted / "LOOSE.jpg").write_text("loose", encoding="utf-8")
    trip = unsorted / "Japan 2026"
    trip.mkdir()
    (trip / "A.jpg").write_text("a", encoding="utf-8")

    InitializationStage().execute(context)

    log = "\n".join(context.logs)
    assert "Files came from 2 folder(s):" in log
    # A subfolder is shown relative to the inbox: the absolute prefix is the
    # same on every line and the part that differs is the part worth reading.
    assert "Japan 2026  -- 1 file(s)" in log
    # Files sitting loose in the inbox are labelled, not shown as ".".
    assert "(inbox root)  -- 1 file(s)" in log
    assert context.counters["input_folders"] == 2
    assert context.stage_stats["initialization"]["folders"] == 2


def test_initialization_flags_subfolders_as_future_origin_labels(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    for name in ("Wedding", "Japan 2026"):
        (unsorted / name).mkdir()
        (unsorted / name / "A.jpg").write_text(name, encoding="utf-8")

    InitializationStage().execute(context)

    notes = context.stage_notes["initialization"]
    assert any("2 subfolder(s)" in note and "origin labels" in note for note in notes)


def test_a_flat_inbox_reports_one_folder_and_no_subfolder_note(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    (unsorted / "A.jpg").write_text("a", encoding="utf-8")

    InitializationStage().execute(context)

    assert context.counters["input_folders"] == 1
    assert not any(
        "origin labels" in note
        for note in context.stage_notes.get("initialization", [])
    )
    # Everything sat in the folder the stage already named, so there is no
    # breakdown to print -- neither in the headline nor as a list.
    assert not any(line.startswith("Files came from") for line in context.logs)
    assert not any(", from 1 folder(s)" in line for line in context.logs)


def test_the_folder_list_is_capped_so_it_cannot_bury_the_run_log(tmp_path):
    context, unsorted, _ready = make_archive(tmp_path)
    cap = InitializationStage.MAX_FOLDERS_LISTED
    for index in range(cap + 5):
        folder = unsorted / f"Import {index:03d}"
        folder.mkdir()
        (folder / "A.jpg").write_text(str(index), encoding="utf-8")

    InitializationStage().execute(context)

    listed = [line for line in context.logs if line.startswith("  Import ")]
    assert len(listed) == cap
    assert any("and 5 more folder(s)" in line for line in context.logs)


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
# Media that arrives after the opening snapshot
# --------------------------------------------------------------------------
# The snapshot is taken against the INBOX before any stage runs, so anything a
# later stage carries in was invisible to the safety check and a loss of it
# went undetected. These pin the two stages that carry files in, and -- just
# as important -- the two places that must NOT be watched, because a file that
# never reaches an output root would be reported lost at the end of every run.

def harvest_archive(tmp_path):
    """An archive with a Camera Uploads folder and a legacy unsorted folder."""
    context, unsorted, ready = make_archive(tmp_path)
    uploads = tmp_path / "Camera Uploads"
    legacy = tmp_path / "____UNSORTED"
    uploads.mkdir()
    legacy.mkdir()
    context.config["paths"]["camera_uploads"] = str(uploads)
    context.config["paths"]["ingest"] = {"camera_uploads": str(uploads)}
    context.config["paths"]["legacy_unsorted_folder"] = str(legacy)
    return context, unsorted, ready, uploads, legacy


def test_harvested_camera_uploads_come_under_the_safety_check(tmp_path):
    context, unsorted, _ready, uploads, _legacy = harvest_archive(tmp_path)
    (uploads / "FROM_PHONE.jpg").write_text("a phone photo", encoding="utf-8")
    InitializationStage().execute(context)
    assert context.input_snapshot == {}     # nothing was in the inbox

    UploadHarvestStage().execute(context)

    assert file_md5(unsorted / "FROM_PHONE.jpg") in context.input_snapshot
    assert context.counters["input_files_added_later"] == 1
    assert context.counters["input_checksums"] == 1
    assert context.stage_stats["upload-harvest"]["watched"] == 1


def test_losing_a_harvested_file_is_now_detected(tmp_path):
    """The whole point: before this, this deletion passed validation."""
    context, unsorted, _ready, uploads, _legacy = harvest_archive(tmp_path)
    (uploads / "FROM_PHONE.jpg").write_text("a phone photo", encoding="utf-8")
    InitializationStage().execute(context)
    UploadHarvestStage().execute(context)
    (unsorted / "FROM_PHONE.jpg").unlink()

    with pytest.raises(CatastrophicSafetyError):
        SafetyValidationStage().execute(context)


def test_other_images_under_camera_uploads_are_never_watched(tmp_path):
    """They are moved *within* Camera Uploads, which is not an output root.

    Snapshotting Camera Uploads wholesale would report every screenshot as
    lost and fail every run -- which is why the snapshot is extended by the
    stage that moves files into the INBOX, not by scanning the source.
    """
    context, _unsorted, _ready, uploads, _legacy = harvest_archive(tmp_path)
    other = uploads / "_Other images"
    other.mkdir()
    screenshot = other / "SCREENSHOT.jpg"
    screenshot.write_text("a screenshot", encoding="utf-8")
    InitializationStage().execute(context)

    UploadHarvestStage().execute(context)

    assert file_md5(screenshot) not in context.input_snapshot
    assert context.counters.get("input_files_added_later", 0) == 0


def test_a_file_left_behind_by_a_collision_prompt_is_not_watched(tmp_path):
    """Registering a file that never arrived would have the safety check hunt
    at the end for something the run never took.

    The clash is built to be genuinely undecidable: the resolver settles a
    collision only when one side is both older *and* at least as large, so an
    incoming file that is newer *and* larger falls through to a prompt, and
    the harvest stops with the file still in Camera Uploads.
    """
    context, unsorted, _ready, uploads, _legacy = harvest_archive(tmp_path)
    occupant = unsorted / "CLASH.jpg"
    occupant.write_text("the one already here", encoding="utf-8")
    left_behind = uploads / "CLASH.jpg"
    left_behind.write_text("a different photo, and a longer one" * 4, encoding="utf-8")
    os.utime(occupant, (1_600_000_000, 1_600_000_000))      # older, smaller
    os.utime(left_behind, (1_700_000_000, 1_700_000_000))   # newer, larger
    InitializationStage().execute(context)

    UploadHarvestStage().execute(context)

    assert left_behind.exists(), "precondition: the collision stopped the move"
    assert any(p.prompt_type == "name_collision" for p in context.prompt_queue)
    assert file_md5(left_behind) not in context.input_snapshot
    assert context.counters.get("input_files_added_later", 0) == 0


def test_legacy_migration_brings_loose_files_and_whole_folders_under_watch(tmp_path):
    context, unsorted, _ready, _uploads, legacy = harvest_archive(tmp_path)
    (legacy / "LOOSE.jpg").write_text("a loose legacy file", encoding="utf-8")
    trip = legacy / "Holiday 2019"
    trip.mkdir()
    (trip / "NESTED.jpg").write_text("inside a migrated folder", encoding="utf-8")
    InitializationStage().execute(context)

    LegacyUnsortedMigrationStage().execute(context)

    assert file_md5(unsorted / "LOOSE.jpg") in context.input_snapshot
    # A whole folder moves in one go, so the walk has to reach inside it.
    assert file_md5(unsorted / "Holiday 2019" / "NESTED.jpg") in context.input_snapshot
    assert context.counters["input_files_added_later"] == 2


def test_extending_the_snapshot_keeps_what_was_already_in_it(tmp_path):
    """`snapshot_inputs` replaces the snapshot wholesale, so a second call
    would have discarded the opening one."""
    context, unsorted, _ready, uploads, _legacy = harvest_archive(tmp_path)
    (unsorted / "ALREADY_HERE.jpg").write_text("in the inbox first", encoding="utf-8")
    (uploads / "ARRIVES_LATER.jpg").write_text("harvested after", encoding="utf-8")
    InitializationStage().execute(context)
    first = dict(context.input_snapshot)
    assert len(first) == 1

    UploadHarvestStage().execute(context)

    assert set(first) <= set(context.input_snapshot)
    assert len(context.input_snapshot) == 2


def test_an_arrival_identical_to_a_watched_file_is_counted_not_double_watched(tmp_path):
    context, unsorted, _ready, uploads, _legacy = harvest_archive(tmp_path)
    (unsorted / "ORIGINAL.jpg").write_text("identical bytes", encoding="utf-8")
    (uploads / "COPY.jpg").write_text("identical bytes", encoding="utf-8")
    InitializationStage().execute(context)

    UploadHarvestStage().execute(context)

    # One checksum covers both, which is why files and checksums differ.
    assert len(context.input_snapshot) == 1
    assert context.counters["input_files_added_later"] == 1
    assert context.stage_stats["upload-harvest"]["watched"] == 1


def test_arrivals_inside_dont_move_are_still_excluded(tmp_path):
    context, unsorted, _ready, _uploads, legacy = harvest_archive(tmp_path)
    protected = unsorted / "__DONT_MOVE"
    protected.mkdir()
    (legacy / "LOOSE.jpg").write_text("a legacy file", encoding="utf-8")
    InitializationStage().execute(context)
    LegacyUnsortedMigrationStage().execute(context)
    # Something already parked in __DONT_MOVE must stay out of the snapshot
    # even though the migration extended it.
    (protected / "KEEP.jpg").write_text("precious", encoding="utf-8")

    added = context.extend_snapshot([protected])

    assert added["files"] == 0
    assert file_md5(protected / "KEEP.jpg") not in context.input_snapshot


# --------------------------------------------------------------------------
# __DONT_MOVE: outside the pipeline, and outside its accounting
# --------------------------------------------------------------------------

def protected_archive(tmp_path):
    context, unsorted, ready = make_archive(tmp_path)
    protected = unsorted / "__DONT_MOVE"
    protected.mkdir()
    return context, unsorted, ready, protected


def test_dont_move_is_not_counted_as_intake(tmp_path):
    context, unsorted, _ready, protected = protected_archive(tmp_path)
    (unsorted / "REAL.jpg").write_text("real", encoding="utf-8")
    (protected / "KEEP.jpg").write_text("precious", encoding="utf-8")

    InitializationStage().execute(context)

    assert context.counters["input_files"] == 1
    assert context.counters["input_protected_skipped"] == 1
    assert len(context.input_snapshot) == 1
    # And the exclusion is stated, so the intake count is never mistaken for
    # "every media file under the inbox".
    assert any("excluded from the intake" in note
               for note in context.stage_notes["initialization"])


def test_a_dont_move_copy_cannot_stand_in_for_a_lost_input(tmp_path):
    """The false pass this exclusion closes.

    While `__DONT_MOVE` was scanned as output, a file parked there that
    happened to be byte-identical to an ingested one satisfied that input's
    checksum — so losing the real file looked like success.
    """
    context, unsorted, _ready, protected = protected_archive(tmp_path)
    (unsorted / "REAL.jpg").write_text("identical bytes", encoding="utf-8")
    (protected / "COPY.jpg").write_text("identical bytes", encoding="utf-8")
    InitializationStage().execute(context)
    (unsorted / "REAL.jpg").unlink()

    with pytest.raises(CatastrophicSafetyError):
        SafetyValidationStage().execute(context)


def test_a_zero_byte_file_parked_in_dont_move_does_not_fail_the_run(tmp_path):
    """It is there because the user put it there; the pipeline never sees it."""
    context, unsorted, ready, protected = protected_archive(tmp_path)
    (unsorted / "REAL.jpg").write_text("real", encoding="utf-8")
    (protected / "EMPTY.jpg").write_bytes(b"")
    InitializationStage().execute(context)
    (unsorted / "REAL.jpg").rename(ready / "REAL.jpg")

    SafetyValidationStage().execute(context)  # must not raise


def test_dont_move_is_watched_by_count_and_size_not_by_checksum(tmp_path):
    context, unsorted, _ready, protected = protected_archive(tmp_path)
    (protected / "A.jpg").write_text("aa", encoding="utf-8")
    (protected / "B.jpg").write_text("bbbb", encoding="utf-8")

    measured = context.snapshot_protected_folders()

    entry = measured[str(protected)]
    assert entry == {"files": 2, "bytes": 6, "exists": True}
    assert context.verify_protected_folders() == []


def test_tampering_with_dont_move_is_reported_but_does_not_end_the_run(tmp_path):
    """Loud, but not fatal.

    A change there is far more likely to be the user editing their own staging
    area mid-run than a pipeline bug, and ending a twenty-minute run over files
    the pipeline was not handling would be the wrong trade.
    """
    context, unsorted, ready, protected = protected_archive(tmp_path)
    (unsorted / "REAL.jpg").write_text("real", encoding="utf-8")
    (protected / "A.jpg").write_text("a", encoding="utf-8")
    (protected / "B.jpg").write_text("b", encoding="utf-8")
    InitializationStage().execute(context)
    (unsorted / "REAL.jpg").rename(ready / "REAL.jpg")
    (protected / "B.jpg").unlink()

    SafetyValidationStage().execute(context)  # reported, not raised

    assert context.counters["protected_folders_changed"] == 1
    assert any("1 file(s) fewer" in note
               for note in context.stage_notes["safety-validation"])
    assert any("CHANGED during the run" in line for line in context.logs)


def test_the_protected_check_still_runs_when_validation_fails(tmp_path):
    """A failing run is exactly when it matters whether the folder was
    disturbed too — a raise must not take that answer with it."""
    context, unsorted, _ready, protected = protected_archive(tmp_path)
    (unsorted / "REAL.jpg").write_text("real", encoding="utf-8")
    (protected / "A.jpg").write_text("a", encoding="utf-8")
    InitializationStage().execute(context)
    (unsorted / "REAL.jpg").unlink()
    (protected / "A.jpg").unlink()

    with pytest.raises(CatastrophicSafetyError):
        SafetyValidationStage().execute(context)

    assert context.counters["protected_folders_changed"] == 1


def test_only_a_top_level_dont_move_is_protected(tmp_path):
    """The spec scopes the exclusion to the top level of the intake folder.

    A folder of that name nested deeper is an ordinary import folder, and
    treating it as protected would silently drop real photos from the count.
    """
    context, unsorted, _ready, _protected = protected_archive(tmp_path)
    nested = unsorted / "Japan 2026" / "__DONT_MOVE"
    nested.mkdir(parents=True)
    (nested / "PHOTO.jpg").write_text("an ordinary photo", encoding="utf-8")

    InitializationStage().execute(context)

    assert context.counters["input_files"] == 1
    assert context.counters.get("input_protected_skipped", 0) == 0


def test_the_dont_move_name_has_one_definition(tmp_path):
    """`provenance.dont_move_folder` delegates to core rather than repeating
    the default (T8)."""
    from src.core import dont_move_folder_name
    from src.pipeline_stages.provenance import dont_move_folder

    config = {"provenance": {"dont_move_folder": "__KEEP_OUT"}}
    assert dont_move_folder(config) == dont_move_folder_name(config) == "__KEEP_OUT"
    assert dont_move_folder({}) == "__DONT_MOVE"


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
