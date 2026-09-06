import os
import datetime
from pathlib import Path

import pytest

from src.core import \
    CatastrophicSafetyError, \
    CollisionDecision, \
    MediaAsset, \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineOrchestrator, \
    PipelineStage, \
    SafetyValidationStage, \
    StagedWorkspaceStage, \
    file_md5
from src.core import normalize_config_paths
from src.pipeline_stages.empty_file_quarantine import EmptyFileQuarantineStage
from src.pipeline_stages.classify_other_images import ClassifyOtherImagesStage
from src.pipeline_stages.exiftool_batch import ExiftoolBatchStage
from src.pipeline_stages.legacy import \
    duplicate_name, \
    final_event_folder, \
    legacy_date_folder_name, \
    legacy_filename, \
    old_exif_folder, \
    parse_legacy_exif_sidecar, \
    problematic_folder
from src.pipeline_stages.legacy_unsorted_migration import LegacyUnsortedMigrationStage
from src.pipeline_stages.move_other_images import MoveOtherImagesStage
from src.pipeline_stages.metadata_extraction import MetadataExtractionStage
from src.pipeline_stages.rename_and_sort import RenameAndSortStage
from src.pipeline_stages.stale_exif_relocation import StaleExifRelocationStage
from src.stages import build_default_orchestrator, build_default_stages


class NoopStage(PipelineStage):
    def __init__(self, stage_id="noop", dependencies=()):
        super().__init__(
            stage_id=stage_id,
            display_name=stage_id,
            dependencies=dependencies,
        )

    def execute(self, context):
        context.counters[self.stage_id] += 1
        return context


class DummySandboxStage(StagedWorkspaceStage):
    def __init__(self):
        super().__init__(
            stage_id="dummy-sandbox",
            display_name="Dummy Sandbox",
            target_extensions=(".cr2",),
            sidecar_extension_map={"converted_jpg": ".jpg"},
        )
        self.seen_workspace = None
        self.seen_assets = []

    def run_workspace(self, context, workspace, staged_assets):
        self.seen_workspace = workspace
        self.seen_assets = staged_assets
        for asset in staged_assets:
            (workspace / f"{asset.primary_path.stem}.jpg").write_text("jpg", encoding="utf-8")


def make_context(tmp_path):
    return PipelineContext(
        config={
            "paths": {
                "root_folder": str(tmp_path / "archive"),
                "working_folder": str(tmp_path / "archive" / "____INGEST_PIPELINE"),
                "inbox_folder": str(tmp_path / "archive" / "____INGEST_PIPELINE" / "INBOX"),
                "ready_folder": str(tmp_path / "archive" / "____INGEST_PIPELINE" / "READY"),
                "temp_folder": str(tmp_path / "archive" / "____INGEST_PIPELINE" / ".TMP"),
                "legacy_unsorted_folder": str(tmp_path / "legacy" / "____UNSORTED"),
                "unsorted_folder": str(tmp_path / "archive" / "____INGEST_PIPELINE" / "INBOX"),
                "temp_root": str(tmp_path / "archive" / "____INGEST_PIPELINE" / ".TMP"),
            },
            "extensions": {
                "lossy_images": [".jpg", ".jpeg"],
                "other_images": [".png", ".gif"],
                "raw_images": [".cr2"],
                "videos": [".mp4"],
            },
            "safety": {
                "enabled": True,
                "hash_chunk_size": 1024,
            },
            "collision": {
                "significantly_smaller_ratio": 0.5,
                "duplicate_suffix": "_DUPE",
                "low_res_suffix": "_LOWRES",
            },
            "legacy": {
                "day_boundary_time": "04.44.44",
                "date_folder_suffix": " - 1. ######",
                "raw_marker": "RAW__",
                "subfolders": {
                    "raw": "##   RAWs   ##",
                    "exif": "##   EXIFs   ##",
                    "empty": "##   EMPTY FILES   ##",
                    "old_exif": "old_EXIF",
                    "unsupported": "##   UNSUPPORTED EXTENSIONS   ##",
                    "not_enough_info": "##   NOT_ENOUGH_INFO FILES   ##",
                    "duplicate_file_names": "##   DUPLICATE_FILE_NAMES FILES   ##",
                },
            },
        }
    )


def test_pipeline_stage_contract_executes_context():
    context = PipelineContext()
    stage = NoopStage()
    result = stage.execute(context)
    assert result is context
    assert context.counters["noop"] == 1
    assert stage.stage_id
    assert stage.display_name


def test_orchestrator_orders_dependencies():
    context = PipelineContext()
    orchestrator = PipelineOrchestrator([
        NoopStage("second", dependencies=("first",)),
        NoopStage("first"),
    ])
    orchestrator.run(context)
    assert context.counters["first"] == 1
    assert context.counters["second"] == 1


def test_orchestrator_logs_stage_transitions():
    context = PipelineContext()
    PipelineOrchestrator([NoopStage("first")]).run(context)

    assert "Stage: first" in context.logs
    assert "Completed." in context.logs


def test_media_asset_renames_and_moves_sidecars(tmp_path):
    primary = tmp_path / "IMG_1.jpg"
    sidecar = tmp_path / "IMG_1._exif"
    primary.write_text("photo", encoding="utf-8")
    sidecar.write_text("exif", encoding="utf-8")
    asset = MediaAsset(primary, {"exif": sidecar})

    asset.rename_all("RENAMED")
    assert asset.primary_path.name == "RENAMED.jpg"
    assert asset.sidecars["exif"].name == "RENAMED._exif"
    assert asset.primary_path.exists()
    assert asset.sidecars["exif"].exists()

    destination = tmp_path / "ready"
    asset.move_all(destination)
    assert asset.primary_path.parent == destination
    assert asset.sidecars["exif"].parent == destination


def test_staged_workspace_isolates_target_extensions(tmp_path):
    raw = tmp_path / "IMG_1.cr2"
    jpg = tmp_path / "IMG_1.jpg"
    raw.write_text("raw", encoding="utf-8")
    jpg.write_text("jpg", encoding="utf-8")
    context = make_context(tmp_path)
    context.assets = [MediaAsset(raw), MediaAsset(jpg)]
    stage = DummySandboxStage()

    stage.execute(context)

    assert len(stage.seen_assets) == 1
    assert stage.seen_assets[0].primary_path.suffix == ".cr2"
    assert stage.seen_workspace is not None
    assert not stage.seen_workspace.exists()


def test_collision_resolver_discards_exact_duplicate(tmp_path):
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("same", encoding="utf-8")
    candidate.write_text("same", encoding="utf-8")

    result = NameCollisionResolver().resolve(existing, candidate)

    assert result.decision == CollisionDecision.DISCARD_DUPLICATE
    assert result.reason == "identical-md5"


def test_collision_resolver_older_larger_wins(tmp_path):
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("larger-file", encoding="utf-8")
    candidate.write_text("small", encoding="utf-8")
    os.utime(existing, (100, 100))
    os.utime(candidate, (200, 200))

    result = NameCollisionResolver(threshold=0.1).resolve(existing, candidate)

    assert result.decision == CollisionDecision.RENAME_CANDIDATE
    assert result.original == existing


def test_collision_resolver_significantly_smaller_auto_renames(tmp_path):
    """_LOWRES needs both: much lighter AND actually fewer pixels (F10)."""
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("x" * 100, encoding="utf-8")
    candidate.write_text("x" * 10, encoding="utf-8")

    result = NameCollisionResolver(threshold=0.5).resolve(
        existing, candidate,
        existing_dimensions=(4000, 3000), candidate_dimensions=(1600, 1200))

    assert result.decision == CollisionDecision.RENAME_CANDIDATE
    assert result.reason == "significantly-smaller"


def test_collision_resolver_never_calls_the_same_resolution_low_res(tmp_path):
    """PS-10's second half: a compressible exposure is not a downscale.

    Two 4000x3000 photographs of the same scene can differ by more than half
    in bytes -- a plain sky against a crowded carriage -- and the archive used
    to file the lighter one as a low-resolution copy of the other.
    """
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("x" * 100, encoding="utf-8")
    candidate.write_text("y" * 10, encoding="utf-8")

    result = NameCollisionResolver(threshold=0.5).resolve(
        existing, candidate,
        existing_dimensions=(4000, 3000), candidate_dimensions=(4000, 3000))

    assert result.reason != "significantly-smaller"
    assert result.target_path is None or "_LOWRES" not in result.target_path.name


def test_collision_resolver_will_not_guess_low_res_without_dimensions(tmp_path):
    """Unknown is not smaller: nothing is demoted on a byte ratio alone."""
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("x" * 100, encoding="utf-8")
    candidate.write_text("y" * 10, encoding="utf-8")

    result = NameCollisionResolver(threshold=0.5).resolve(existing, candidate)

    assert result.reason != "significantly-smaller"


def test_collision_resolver_ambiguous_creates_prompt(tmp_path):
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("x" * 60, encoding="utf-8")
    candidate.write_text("x" * 80, encoding="utf-8")
    os.utime(existing, (100, 100))
    os.utime(candidate, (200, 200))
    context = make_context(tmp_path)

    result = NameCollisionResolver(threshold=0.5).resolve(existing, candidate, context)

    assert result.decision == CollisionDecision.PROMPT
    assert result.prompt is not None
    assert len(context.prompt_queue) == 1


def test_safety_validation_passes_for_matching_output(tmp_path):
    context = make_context(tmp_path)
    unsorted = Path(context.config["paths"]["unsorted_folder"])
    ready = Path(context.config["paths"]["ready_folder"])
    unsorted.mkdir(parents=True)
    ready.mkdir(parents=True)
    source = unsorted / "A.jpg"
    output = ready / "A.jpg"
    source.write_text("photo", encoding="utf-8")
    output.write_text("photo", encoding="utf-8")
    context.snapshot_inputs([unsorted])

    SafetyValidationStage().execute(context)

    assert file_md5(output) in context.input_snapshot


def test_safety_validation_halts_on_missing_output(tmp_path):
    context = make_context(tmp_path)
    unsorted = Path(context.config["paths"]["unsorted_folder"])
    ready = Path(context.config["paths"]["ready_folder"])
    unsorted.mkdir(parents=True)
    ready.mkdir(parents=True)
    source = unsorted / "A.jpg"
    source.write_text("photo", encoding="utf-8")
    context.snapshot_inputs([unsorted])
    source.unlink()

    with pytest.raises(CatastrophicSafetyError):
        SafetyValidationStage().execute(context)


def test_default_dag_ends_with_safety_validation():
    graph = build_default_orchestrator().graph()["nodes"]
    node_ids = [node["id"] for node in graph]
    assert graph[-1]["id"] == "safety-validation"
    assert "legacy-unsorted-migration" in node_ids
    assert "move-other-images" in node_ids
    assert node_ids.index("legacy-unsorted-migration") < node_ids.index("move-other-images")
    assert node_ids.index("move-other-images") < node_ids.index("upload-harvest")
    assert "stale-exif-relocation" in node_ids
    assert "empty-file-quarantine" in node_ids
    assert "timezone-and-travel" in node_ids
    assert "convert-crws" in node_ids
    assert "launch-dpviewer" in node_ids
    assert "show-stats" in node_ids
    assert "display-extra-messages" in node_ids
    assert "move-results" in node_ids
    assert node_ids.index("rename-and-sort") < node_ids.index("convert-crws")
    assert node_ids.index("convert-crws") < node_ids.index("launch-dpviewer")
    assert node_ids.index("move-results") < node_ids.index("folder-sorting")
    assert node_ids.index("show-stats") < node_ids.index("display-extra-messages")
    assert [stage.stage_id for stage in build_default_stages()]


def test_normalize_config_paths_keeps_photo_outputs_out_of_repo():
    config = {
        "paths": {
            "root_folder": r"c:\__PHOTOS\____TO_SORT",
            "unsorted_folder": r"____TO_SORT\____UNSORTED",
            "ready_folder": r"____TO_SORT\__READY",
        }
    }

    normalized = normalize_config_paths(config)

    assert normalized["paths"]["root_folder"] == r"c:\__PHOTOS"
    assert normalized["paths"]["working_folder"] == r"c:\__PHOTOS\____INGEST_PIPELINE"
    assert normalized["paths"]["unsorted_folder"] == r"c:\__PHOTOS\____INGEST_PIPELINE\____UNSORTED"
    assert normalized["paths"]["ready_folder"] == r"c:\__PHOTOS\____INGEST_PIPELINE\READY"


def test_legacy_filename_and_folder_grammar(tmp_path):
    context = make_context(tmp_path)
    metadata = {
        "image_datetime": "2026-05-14_(Thu)_03.30.00",
        "aperture": "f2.8",
        "exposure_time": "T1_250",
        "focal_length": "L50",
        "iso": "I100",
        "camera_symbol": "C6D",
    }

    assert legacy_filename(metadata, ".cr2", context.config) == "2026-05-14_(Thu)_03.30.00__RAW__f2.8__T1_250__L50__I100__C6D.CR2"
    captured = datetime.datetime(2026, 5, 14, 3, 30, 0)
    assert legacy_date_folder_name(captured, context.config) == "2026-05-13_(Wed) - 1. ######"
    assert str(final_event_folder(captured, context.config)).endswith(r"2026\05. May\2026-05-13_(Wed) - 1. ######")
    assert duplicate_name("photo", "abcd", 2, ".jpg") == "photo_DUPE_abcd_2.jpg"


def test_metadata_extraction_parses_legacy_exif_and_rename_matches_old_task(tmp_path):
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    photo = inbox / "IMG_0001.jpg"
    exif = inbox / "IMG_0001.jpg._exif"
    photo.write_text("photo", encoding="utf-8")
    exif.write_text(
        "\n".join([
            "Camera Model Name               : Canon EOS 6D",
            "Date/Time Original              : 2026:05:14 10:30:00",
            "Aperture                        : 2.8",
            "Exposure Time                   : 1/250",
            "ISO                             : 100",
            "Focal Length                    : 50.0 mm",
        ]),
        encoding="iso-8859-1",
    )

    metadata = parse_legacy_exif_sidecar(exif, context.config)
    assert metadata["image_datetime"] == "2026-05-14_(Thu)__10.30.00"
    assert metadata["camera_symbol"] == "6D"

    MetadataExtractionStage().execute(context)
    RenameAndSortStage().execute(context)

    renamed_photo = inbox / "2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I100__6D.jpg"
    # Sidecars keep the full primary filename embedded, including the photo's
    # extension, before their own extension.
    renamed_exif = inbox / "2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I100__6D.jpg._exif"
    assert renamed_photo.exists()
    assert renamed_exif.exists()
    assert context.assets[0].primary_path == renamed_photo
    assert context.assets[0].sidecars["exif"] == renamed_exif


def test_rename_collision_keeps_demoted_loser_asset_tracked(tmp_path):
    # KEEP_CANDIDATE demotes the existing target to _DIFFERS_<md5>_0 -- the two
    # files hold different bytes, so F4 forbids calling either a _DUPE (PS-10).
    # When the demoted file belongs to a tracked asset, the asset (and its
    # sidecars) must follow the rename, or folder sorting later skips it and
    # the file is stranded in the inbox.
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    metadata = {
        "image_datetime": "2026-05-14_(Thu)_10.30.00",
        "aperture": "f2.8",
        "exposure_time": "T1_250",
        "focal_length": "L50.0",
        "iso": "I100",
        "camera_symbol": "6D",
    }
    target_name = legacy_filename(metadata, ".jpg", context.config)

    # Sizes stay within the significantly_smaller_ratio (0.5) so the resolver
    # compares age/size instead of ruling the loser a low-res variant.
    loser = inbox / "IMG_0001.jpg"
    loser.write_text("loser content...", encoding="utf-8")
    loser_sidecar = inbox / "IMG_0001.jpg._exif"
    loser_sidecar.write_text("loser exif", encoding="utf-8")
    winner = inbox / "IMG_0002.jpg"
    winner.write_text("winner is bigger", encoding="utf-8")
    winner_sidecar = inbox / "IMG_0002.jpg._exif"
    winner_sidecar.write_text("winner exif", encoding="utf-8")

    # The resolver rules KEEP_CANDIDATE ("candidate-older-larger"): the winner
    # must be at least as old and as large as the already-renamed loser.
    os.utime(winner, (1_000_000_000, 1_000_000_000))
    os.utime(loser, (1_000_000_100, 1_000_000_100))
    loser_md5 = file_md5(loser)

    loser_asset = MediaAsset(loser, {"exif": loser_sidecar}, dict(metadata))
    winner_asset = MediaAsset(winner, {"exif": winner_sidecar}, dict(metadata))
    context.assets.extend([loser_asset, winner_asset])

    RenameAndSortStage().execute(context)

    target_path = inbox / target_name
    assert winner_asset.primary_path == target_path
    assert target_path.read_text(encoding="utf-8") == "winner is bigger"
    assert winner_asset.sidecars["exif"] == inbox / (target_name + "._exif")
    assert winner_asset.sidecars["exif"].read_text(encoding="utf-8") == "winner exif"

    demoted_path = inbox / f"{target_path.stem}_DIFFERS_{loser_md5}_0.jpg"
    assert loser_asset.primary_path == demoted_path
    assert demoted_path.read_text(encoding="utf-8") == "loser content..."
    assert loser_asset.sidecars["exif"] == inbox / (demoted_path.name + "._exif")
    assert loser_asset.sidecars["exif"].read_text(encoding="utf-8") == "loser exif"


def test_legacy_stages_move_old_exif_empty_and_legacy_unsorted(tmp_path):
    context = make_context(tmp_path)
    legacy_unsorted = Path(context.config["paths"]["legacy_unsorted_folder"])
    inbox = Path(context.config["paths"]["inbox_folder"])
    legacy_unsorted.mkdir(parents=True)
    inbox.mkdir(parents=True)
    (legacy_unsorted / "legacy.jpg").write_text("photo", encoding="utf-8")

    LegacyUnsortedMigrationStage().execute(context)
    assert (inbox / "legacy.jpg").exists()

    stale = inbox / "legacy.jpg._exif"
    stale.write_text("old", encoding="utf-8")
    StaleExifRelocationStage().execute(context)
    assert (old_exif_folder(context.config) / "legacy.jpg._exif").exists()

    empty = inbox / "empty.jpg"
    empty.write_bytes(b"")
    EmptyFileQuarantineStage().execute(context)
    assert (problematic_folder(context.config, "empty") / "empty.jpg").exists()


def test_exiftool_batch_writes_sidecars_next_to_originals(monkeypatch, tmp_path):
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    (inbox / "photo.jpg").write_bytes(b"jpeg-bytes")
    calls = []

    def fake_check_call(command):
        calls.append(command)

    monkeypatch.setattr("src.pipeline_stages.exiftool_batch.subprocess.check_call", fake_check_call)

    ExiftoolBatchStage().execute(context)

    assert calls
    assert "%d%f.%e._exif" in calls[0]
    assert "%f.%e._exif" not in calls[0]
    # Only the explicit media file is passed; non-media files are never targets.
    assert str(inbox / "photo.jpg") in calls[0]


def test_exiftool_batch_chunks_large_batches_under_windows_command_limit(monkeypatch, tmp_path):
    # 637 Camera Uploads files once exceeded the ~32k CreateProcess limit;
    # Python raised that as FileNotFoundError and the stage silently skipped
    # sidecar generation, sending every photo to READY.
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    for index in range(700):
        (inbox / f"2026-07-05 17.{index // 60:02d}.{index % 60:02d}_{index}.jpg").write_bytes(b"jpeg")
    calls = []
    monkeypatch.setattr(
        "src.pipeline_stages.exiftool_batch.subprocess.check_call",
        lambda command: calls.append(command),
    )

    ExiftoolBatchStage().execute(context)

    assert len(calls) > 1
    for command in calls:
        assert sum(len(part) + 3 for part in command) < 32000
    passed = {part for command in calls for part in command if part.endswith(".jpg")}
    assert len(passed) == 700


def test_exiftool_batch_reports_too_long_command_line(monkeypatch, tmp_path):
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    (inbox / "photo.jpg").write_bytes(b"jpeg")

    def raise_too_long(command):
        error = FileNotFoundError("The filename or extension is too long")
        error.winerror = 206
        raise error

    monkeypatch.setattr("src.pipeline_stages.exiftool_batch.subprocess.check_call", raise_too_long)

    ExiftoolBatchStage().execute(context)

    assert any("command line too long" in line for line in context.logs)
    assert not any("executable not found" in line for line in context.logs)
    assert context.stage_stats["exiftool-batch"]["errors"] == 1


def test_exiftool_batch_skips_non_media_files(monkeypatch, tmp_path):
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    (inbox / "page.html").write_text("<html></html>", encoding="utf-8")
    (inbox / "notes.txt").write_text("notes", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        "src.pipeline_stages.exiftool_batch.subprocess.check_call",
        lambda command: calls.append(command),
    )

    ExiftoolBatchStage().execute(context)

    # No media files present: ExifTool must not run, so no .html._exif appears.
    assert not calls


def test_move_other_images_stage_wraps_legacy_function(monkeypatch, tmp_path):
    import src.pipeline_stages.move_other_images as stage_module

    context = make_context(tmp_path)
    context.config["paths"]["camera_uploads"] = str(tmp_path / "Camera Uploads")
    context.config["paths"]["ingest"] = {"camera_uploads": str(tmp_path / "Camera Uploads")}
    seen_kwargs = {}
    legacy_counter = {
        "PHOTOS": 99,
        "VIDEOS": 99,
        "OTHER_IMAGES": 99,
        "OTHER_FILES": 99,
    }

    def fake_move_other_images(**kwargs):
        seen_kwargs.update(kwargs)
        legacy_counter["PHOTOS"] = 2
        legacy_counter["VIDEOS"] = 1
        legacy_counter["OTHER_IMAGES"] = 3
        legacy_counter["OTHER_FILES"] = 4

    monkeypatch.setattr(
        stage_module,
        "load_legacy_move_other_images",
        lambda: (fake_move_other_images, legacy_counter),
    )

    MoveOtherImagesStage().execute(context)

    assert context.counters["camera_upload_photos"] == 2
    assert context.counters["camera_upload_videos"] == 1
    assert context.counters["other_images_moved"] == 3
    assert context.counters["other_files_moved"] == 4
    assert seen_kwargs["src_path"] == str(tmp_path / "Camera Uploads")
    assert seen_kwargs["other_image_extensions"] == [".png", ".gif"]
    assert seen_kwargs["video_extensions"] == [".mp4"]


def test_classify_other_images_stage_publishes_live_input_output_stats(monkeypatch, tmp_path):
    import src.other_image_classifier as classifier_module

    context = make_context(tmp_path)
    camera_uploads = tmp_path / "Camera Uploads"
    context.config["paths"]["camera_uploads"] = str(camera_uploads)
    context.config["paths"]["ingest"] = {"camera_uploads": str(camera_uploads)}
    live_stats = []

    def fake_classify_other_images(path, progress_callback):
        assert path == str(camera_uploads / "_Other images")
        progress_callback(0, 4)
        live_stats.append(dict(context.stage_stats["classify-other-images"]))
        progress_callback(4, 0)
        return {
            classifier_module.PHOTO_FOLDER: 2,
            classifier_module.INFOGRAPHIC_FOLDER: 1,
            classifier_module.TEXT_SCREENSHOT_FOLDER: 0,
        }

    monkeypatch.setattr(
        classifier_module,
        "classify_other_images",
        fake_classify_other_images,
    )

    ClassifyOtherImagesStage().execute(context)

    assert live_stats == [{"inputs": 4, "outputs": 0, "errors": 0}]
    assert context.stage_stats["classify-other-images"] == {
        "inputs": 4,
        "outputs": 3,
        "errors": 1,
    }
