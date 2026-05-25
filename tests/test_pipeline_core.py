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
    existing = tmp_path / "A.jpg"
    candidate = tmp_path / "B.jpg"
    existing.write_text("x" * 100, encoding="utf-8")
    candidate.write_text("x" * 10, encoding="utf-8")

    result = NameCollisionResolver(threshold=0.5).resolve(existing, candidate)

    assert result.decision == CollisionDecision.RENAME_CANDIDATE
    assert result.reason == "significantly-smaller"


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
    assert metadata["image_datetime"] == "2026-05-14_(Thu)_10.30.00"
    assert metadata["camera_symbol"] == "6D"

    MetadataExtractionStage().execute(context)
    RenameAndSortStage().execute(context)

    renamed_photo = inbox / "2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50.0__I100__6D.jpg"
    renamed_exif = inbox / "2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50.0__I100__6D._exif"
    assert renamed_photo.exists()
    assert renamed_exif.exists()
    assert context.assets[0].primary_path == renamed_photo
    assert context.assets[0].sidecars["exif"] == renamed_exif


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
    calls = []

    def fake_check_call(command):
        calls.append(command)

    monkeypatch.setattr("src.pipeline_stages.exiftool_batch.subprocess.check_call", fake_check_call)

    ExiftoolBatchStage().execute(context)

    assert calls
    assert "%d%f.%e._exif" in calls[0]
    assert "%f.%e._exif" not in calls[0]


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
