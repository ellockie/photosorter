import datetime
from pathlib import Path

import pytest

from src.core import PipelineContext, PipelineMode, file_md5
from src.pipeline_stages.default import build_default_orchestrator
from src.pipeline_stages.folder_sorting import FolderSortingStage
from src.pipeline_stages.legacy import final_event_folder
from src.core import MediaAsset


JAPAN_TRIP = {
    "name": "Japan Trip",
    "start": "2026-04-10T00:00:00",
    "end": "2026-04-20T23:59:59",
    "timezone_offset_hours": 9,
    "location_suffix": "Japan",
}

NE71_CLOCK_FIX = {
    "camera_symbol": "NE71",
    "from_date": "2026-04-10T00:00:00",
    "to_date": "2026-04-20T23:59:59",
    "offset_seconds": -3600,
    "description": "Forgot daylight saving adjustment",
}


def build_config(tmp_path):
    root = tmp_path / "archive"
    working = root / "____INGEST_PIPELINE"
    return {
        "paths": {
            "root_folder": str(root),
            "working_folder": str(working),
            "inbox_folder": str(working / "INBOX"),
            "ready_folder": str(working / "READY"),
            "temp_folder": str(working / ".TMP"),
            "temp_root": str(working / ".TMP"),
            "unsorted_folder": str(working / "INBOX"),
            "legacy_unsorted_folder": str(tmp_path / "missing-legacy"),
            "legacy_ready_folder": str(tmp_path / "missing-legacy-ready"),
            "camera_uploads": str(tmp_path / "missing-uploads"),
            "ingest": {"camera_uploads": str(tmp_path / "missing-uploads")},
        },
        "extensions": {
            "lossy_images": [".jpg"],
            "other_images": [".png"],
            "raw_images": [".cr2"],
            "videos": [".mp4"],
            "sidecars": ["._exif"],
        },
        "collision": {
            "significantly_smaller_ratio": 0.5,
            "duplicate_suffix": "_DUPE",
            "low_res_suffix": "_LOWRES",
        },
        "camera_symbols": {
            "Sony RX100": "NE71",
            "Canon EOS 6D": "C6D",
            "": "NOID",
        },
        "legacy": {
            "day_boundary_time": "04.44.44",
            "date_folder_suffix": " - 1. ######",
            "raw_marker": "RAW__",
        },
        "safety": {"enabled": True, "hash_chunk_size": 1024},
        "camera_clock_corrections": [NE71_CLOCK_FIX],
        "trips": [JAPAN_TRIP],
    }


EXIF_FIXTURES = {
    "test1.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm"),
    "test2.cr2": ("Canon EOS 6D", "2026:05:01 14:30:00", "2.8", "1/500", "200", "50.0 mm"),
    "test3.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm"),
    "test4.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm"),
    "test5.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm"),
    "test6.jpg": ("Canon EOS 6D", "2026:05:02 03:30:00", "2.8", "1/60", "400", "35.0 mm"),
}


def fake_exiftool(inbox: Path):
    def check_call(command):
        for path in inbox.iterdir():
            fixture = EXIF_FIXTURES.get(path.name)
            if fixture is None:
                continue
            camera, taken_at, aperture, exposure, iso, focal = fixture
            (inbox / f"{path.name}._exif").write_text(
                "\n".join([
                    f"Camera Model Name               : {camera}",
                    f"Date/Time Original              : {taken_at}",
                    f"Aperture                        : {aperture}",
                    f"Exposure Time                   : {exposure}",
                    f"ISO                             : {iso}",
                    f"Focal Length                    : {focal}",
                ]),
                encoding="iso-8859-1",
            )
    return check_call


@pytest.fixture
def no_legacy_uploads(monkeypatch):
    import src.pipeline_stages.move_other_images as move_other_images_module

    counter = {"PHOTOS": 0, "VIDEOS": 0, "OTHER_IMAGES": 0, "OTHER_FILES": 0}
    monkeypatch.setattr(
        move_other_images_module,
        "load_legacy_move_other_images",
        lambda: (lambda **kwargs: None, counter),
    )


def test_e2e_fixture_matrix_full_default_dag(tmp_path, monkeypatch, no_legacy_uploads):
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["inbox_folder"])
    root = Path(config["paths"]["root_folder"])
    inbox.mkdir(parents=True)

    (inbox / "test1.jpg").write_text("photo-one-content-x" * 10, encoding="utf-8")
    (inbox / "test2.cr2").write_text("raw-two-content-yy" * 50, encoding="utf-8")
    (inbox / "test3.jpg").write_text("photo-one-content-x" * 10, encoding="utf-8")
    (inbox / "test4.jpg").write_text("photo-four-content" * 10, encoding="utf-8")
    (inbox / "test5.jpg").write_text("tiny", encoding="utf-8")
    (inbox / "test6.jpg").write_text("night-photo-content" * 10, encoding="utf-8")
    import os
    os.utime(inbox / "test1.jpg", (1_000_000, 1_000_000))
    test4_md5 = file_md5(inbox / "test4.jpg")
    test5_md5 = file_md5(inbox / "test5.jpg")

    monkeypatch.setattr(
        "src.pipeline_stages.exiftool_batch.subprocess.check_call",
        fake_exiftool(inbox),
    )

    context = PipelineContext(config=config, mode=PipelineMode.CLI)
    build_default_orchestrator().run(context)

    japan_folder = root / "2026" / "04. April" / "2026-04-12_(Sun) - Japan"
    expected_stem = "2026-04-12_(Sun)_18.00.00__Japan__f4.0__T1_250__L28.0__I100__NE71"
    representative = japan_folder / f"{expected_stem}.jpg"
    assert representative.exists(), sorted(p.name for p in japan_folder.iterdir()) if japan_folder.exists() else "missing folder"
    assert (japan_folder / "__EXIF" / f"{expected_stem}.jpg._exif").exists()

    may_folder = root / "2026" / "05. May" / "2026-05-01_(Fri) - 1. ######"
    raw_name = "2026-05-01_(Fri)_14.30.00__RAW__f2.8__T1_500__L50.0__I200__C6D.CR2"
    assert (may_folder / "__RAW" / raw_name).exists()
    assert (may_folder / "__EXIF" / f"{raw_name}._exif").exists()

    # test3 was an exact duplicate of test1: merged away with a safety exception.
    all_jpgs = list(root.rglob("*.jpg"))
    assert len([p for p in all_jpgs if "_DUPE_" in p.name]) == 1
    dupe = next(p for p in all_jpgs if "_DUPE_" in p.name)
    assert test4_md5 in dupe.name
    assert dupe.parent == japan_folder

    lowres = [p for p in all_jpgs if "_LOWRES_" in p.name]
    assert len(lowres) == 1
    assert test5_md5 in lowres[0].name
    assert lowres[0].parent == japan_folder

    # Day boundary: 03:30 is before 04.44.44, so the file keeps its own date
    # in the filename but groups into the previous day's folder.
    boundary_folder = root / "2026" / "05. May" / "2026-05-01_(Fri) - 1. ######"
    boundary_files = list(boundary_folder.glob("2026-05-02_(Sat)_03.30.00*.jpg"))
    assert len(boundary_files) == 1

    # Zero file loss: the safety stage completed without raising.
    assert context.stage_states["safety-validation"].value == "complete"
    assert not list(inbox.glob("*.jpg"))
    assert not list(inbox.glob("*.cr2"))


def test_e2e_labeled_folder_stays_separate_from_loose_files(tmp_path, monkeypatch, no_legacy_uploads):
    config = build_config(tmp_path)
    config["trips"] = []
    config["camera_clock_corrections"] = []
    inbox = Path(config["paths"]["inbox_folder"])
    root = Path(config["paths"]["root_folder"])
    origin = inbox / "2026-04-12 Birthday"
    origin.mkdir(parents=True)
    (origin / "test1.jpg").write_text("labeled-photo-content", encoding="utf-8")
    (origin / "track.gpx").write_text("<gpx/>", encoding="utf-8")
    (inbox / "test4.jpg").write_text("loose-photo-content", encoding="utf-8")

    monkeypatch.setattr(
        "src.pipeline_stages.exiftool_batch.subprocess.check_call",
        fake_exiftool(inbox),
    )

    context = PipelineContext(config=config, mode=PipelineMode.CLI)
    build_default_orchestrator().run(context)

    month = root / "2026" / "04. April"
    labeled = month / "2026-04-12_(Sun) - Birthday"
    generic = month / "2026-04-12_(Sun) - 1. ######"
    assert labeled.exists() and any(labeled.glob("*.jpg"))
    assert generic.exists() and any(generic.glob("*.jpg"))
    # Folder-level geodata travels to the labeled event folder.
    assert (labeled / "__GEOLOCATIONS" / "track.gpx").exists()


def test_representative_suffix_ordering():
    from src.pipeline_stages.taxonomy import apply_representative_suffixes

    assert apply_representative_suffixes("a.jpg", has_raw=True) == "a_RAW.jpg"
    assert apply_representative_suffixes("a.jpg", has_raw=True, extracted_from_raw=True) == "a_RAW_EXT.jpg"
    assert apply_representative_suffixes(
        "a.jpg", has_raw=True, extracted_from_raw=True, has_edited=True) == "a_RAW_EXT_EDT.jpg"
    assert apply_representative_suffixes("a.jpg", has_edited=True) == "a_EDT.jpg"
    assert apply_representative_suffixes("a.jpg") == "a.jpg"


def test_folder_sorting_taxonomy_routing(tmp_path):
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["inbox_folder"])
    inbox.mkdir(parents=True)
    captured = datetime.datetime(2026, 5, 14, 10, 30, 0)

    video = inbox / "clip.mp4"
    video.write_text("video", encoding="utf-8")
    raw_only = inbox / "shot.cr2"
    raw_only.write_text("raw-bytes", encoding="utf-8")
    extracted = inbox / "shot_extracted.jpg"
    extracted.write_text("extracted-bytes", encoding="utf-8")

    raw_asset = MediaAsset(raw_only, {"converted_jpg": extracted})
    raw_asset.metadata.update({
        "captured_at": captured,
        "image_datetime": "2026-05-14_(Thu)_10.30.00",
        "camera_symbol": "C6D",
    })
    video_asset = MediaAsset(video)
    video_asset.metadata.update({"captured_at": captured})

    context = PipelineContext(config=config)
    context.assets = [raw_asset, video_asset]
    FolderSortingStage().execute(context)

    event_folder = final_event_folder(captured, config)
    assert (event_folder / "__RAW" / "shot.cr2").exists()
    assert (event_folder / "__VIDEOS" / "clip.mp4").exists()
    # RAW-only shot: the extracted JPEG is promoted to representative with
    # _RAW (original exists) and _EXT (derived from RAW) suffixes.
    assert (event_folder / "shot_extracted_RAW_EXT.jpg").exists()


def test_folder_sorting_marks_camera_image_with_raw_pair(tmp_path):
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["inbox_folder"])
    inbox.mkdir(parents=True)
    captured = datetime.datetime(2026, 5, 14, 10, 30, 0)
    shared = {
        "captured_at": captured,
        "image_datetime": "2026-05-14_(Thu)_10.30.00",
        "camera_symbol": "C6D",
    }

    jpg = inbox / "pair.jpg"
    jpg.write_text("jpg-bytes", encoding="utf-8")
    raw = inbox / "pair.cr2"
    raw.write_text("raw-bytes", encoding="utf-8")
    jpg_asset = MediaAsset(jpg)
    jpg_asset.metadata.update(shared)
    raw_asset = MediaAsset(raw)
    raw_asset.metadata.update(shared)

    context = PipelineContext(config=config)
    context.assets = [jpg_asset, raw_asset]
    FolderSortingStage().execute(context)

    event_folder = final_event_folder(captured, config)
    assert (event_folder / "pair_RAW.jpg").exists()
    assert (event_folder / "__RAW" / "pair.cr2").exists()
    root_files = [path for path in event_folder.iterdir() if path.is_file()]
    assert len(root_files) == 1
