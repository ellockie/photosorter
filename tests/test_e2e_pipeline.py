import datetime
from pathlib import Path

import pytest

from src.core import PipelineContext, PipelineMode, file_md5
from src.pipeline_stages.default import build_default_orchestrator
from src.pipeline_stages.folder_sorting import FolderSortingStage
from src.pipeline_stages.legacy import final_event_folder
from src.core import MediaAsset


# Two-timeline model: camera NE71 is on home (London, BST=+1h on 2026-04-12) and
# was never re-set for the trip; the location timeline places the photographer in
# Tokyo. So reading 10:00 London -> 09:00 UTC -> Tokyo 18:00, suffix "Japan".
ZONES = {"UK": "Europe/London", "JP": "Asia/Tokyo"}

LOCATIONS = [
    {"since": "2000-01-01_(Sat)_00.00.00", "zone": "UK"},
    {
        "since": "2026-04-10_(Fri)_00.00.00",
        "zone": "JP",
        "label": "Japan",
        "until": "2026-04-20_(Mon)_23.59.59",
    },
]


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
        "zones": ZONES,
        "locations": LOCATIONS,
        "camera_clock_sets": [],
    }


# Last field is the picture's pixel size. Only test5 is genuinely downscaled;
# _LOWRES is a claim about resolution and nothing else may earn it (F10).
EXIF_FIXTURES = {
    "test1.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm", (5472, 3648)),
    "test2.cr2": ("Canon EOS 6D", "2026:05:01 14:30:00", "2.8", "1/500", "200", "50.0 mm", (5472, 3648)),
    "test3.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm", (5472, 3648)),
    "test4.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm", (5472, 3648)),
    "test5.jpg": ("Sony RX100", "2026:04:12 10:00:00", "4.0", "1/250", "100", "28.0 mm", (1024, 683)),
    "test6.jpg": ("Canon EOS 6D", "2026:05:02 03:30:00", "2.8", "1/60", "400", "35.0 mm", (5472, 3648)),
}


def fake_exiftool(inbox: Path):
    def check_call(command):
        for path in inbox.iterdir():
            fixture = EXIF_FIXTURES.get(path.name)
            if fixture is None:
                continue
            camera, taken_at, aperture, exposure, iso, focal, size = fixture
            width, height = size
            (inbox / f"{path.name}._exif").write_text(
                "\n".join([
                    "---- File ----",
                    f"Image Width                     : {width}",
                    f"Image Height                    : {height}",
                    "---- IFD0 ----",
                    f"Camera Model Name               : {camera}",
                    f"Date/Time Original              : {taken_at}",
                    f"Aperture                        : {aperture}",
                    f"Exposure Time                   : {exposure}",
                    f"ISO                             : {iso}",
                    f"Focal Length                    : {focal}",
                    # The embedded thumbnail. Its dimensions must never be
                    # mistaken for the picture's own (F10).
                    "---- IFD1 ----",
                    "Image Width                     : 160",
                    "Image Height                    : 120",
                    "---- Composite ----",
                    f"Image Size                      : {width}x{height}",
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
    expected_stem = "2026-04-12_(Sun)__18.00.00__Japan__f4.0__T1_250__L28.0__I100__NE71"
    representative = japan_folder / f"{expected_stem}.jpg"
    assert representative.exists(), sorted(p.name for p in japan_folder.iterdir()) if japan_folder.exists() else "missing folder"
    assert (japan_folder / "__EXIF" / f"{expected_stem}.jpg._exif").exists()
    # Derived geolocation projection from the location timeline.
    assert (japan_folder / "__GEOLOCATIONS" / "_location.json").exists()

    may_folder = root / "2026" / "05. May" / "2026-05-01_(Fri) - 1. ######"
    raw_name = "2026-05-01_(Fri)__14.30.00__RAW__f2.8__T1_500__L50.0__I200__C6D.CR2"
    assert (may_folder / "__RAW" / raw_name).exists()
    # X10: a sidecar lives in the __EXIF of the folder holding its subject. The
    # RAW is in __RAW, so its sidecar is in __RAW\__EXIF — not the event
    # folder's own __EXIF, which serves the top level.
    assert (may_folder / "__RAW" / "__EXIF" / f"{raw_name}._exif").exists()
    assert not (may_folder / "__EXIF" / f"{raw_name}._exif").exists()

    # test3 was an exact duplicate of test1: merged away with a safety exception.
    # test4 only shares test1's name -- its bytes differ, so it is a _DIFFERS,
    # not a _DUPE. Nothing byte-identical survives to carry a _DUPE at all.
    all_jpgs = list(root.rglob("*.jpg"))
    assert not [p for p in all_jpgs if "_DUPE_" in p.name]
    differs = [p for p in all_jpgs if "_DIFFERS_" in p.name]
    assert len(differs) == 1
    assert test4_md5 in differs[0].name
    assert differs[0].parent == japan_folder

    # test5 is a real downscale -- 1024x683 against 5472x3648 -- so it earns
    # _LOWRES, and being a derivative it goes in __RESIZED rather than beside
    # the shot it is a smaller copy of (F7/F10).
    lowres = [p for p in all_jpgs if "_LOWRES_" in p.name]
    assert len(lowres) == 1
    assert test5_md5 in lowres[0].name
    assert lowres[0].parent == japan_folder / "__RESIZED"

    # Day boundary: 03:30 is before 04.44.44, so the file keeps its own date
    # in the filename but groups into the previous day's folder.
    boundary_folder = root / "2026" / "05. May" / "2026-05-01_(Fri) - 1. ######"
    boundary_files = list(boundary_folder.glob("2026-05-02_(Sat)__03.30.00*.jpg"))
    assert len(boundary_files) == 1

    # Zero file loss: the safety stage completed without raising.
    assert context.stage_states["safety-validation"].value == "complete"
    assert not list(inbox.glob("*.jpg"))
    assert not list(inbox.glob("*.cr2"))


def test_e2e_labeled_folder_stays_separate_from_loose_files(tmp_path, monkeypatch, no_legacy_uploads):
    config = build_config(tmp_path)
    config["locations"] = []
    config["camera_clock_sets"] = []
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


def test_folder_sorting_demotes_existing_occupant_on_name_collision(tmp_path):
    # Two different assets land on the same event folder + file name (e.g. two
    # distinct shots that both got named "shot.jpg" upstream). The asset moved
    # in first must not be left silently occupying the plain name once a
    # second, different file wants it too. Their bytes differ and no camera
    # here recorded a sub-second, so this is F4's _DIFFERS_<md5> and not a
    # sibling pair (F9a) -- and the first asset's sidecar follows its rename.
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["inbox_folder"])
    inbox.mkdir(parents=True)
    other = inbox / "other"
    other.mkdir(parents=True)
    captured = datetime.datetime(2026, 5, 14, 10, 30, 0)
    shared = {
        "captured_at": captured,
        "image_datetime": "2026-05-14_(Thu)_10.30.00",
        "camera_symbol": "C6D",
    }

    first = inbox / "shot.jpg"
    first.write_text("first-content", encoding="utf-8")
    first_exif = inbox / "shot.jpg._exif"
    first_exif.write_text("first exif", encoding="utf-8")
    second = other / "shot.jpg"
    second.write_text("second-content-different", encoding="utf-8")

    first_asset = MediaAsset(first, {"exif": first_exif})
    first_asset.metadata.update(shared)
    second_asset = MediaAsset(second)
    second_asset.metadata.update(shared)

    first_md5 = file_md5(first)

    context = PipelineContext(config=config)
    context.assets = [first_asset, second_asset]
    FolderSortingStage().execute(context)

    event_folder = final_event_folder(captured, config)
    assert (event_folder / "shot.jpg").exists()
    assert second_asset.primary_path == event_folder / "shot.jpg"

    demoted = event_folder / f"shot_DIFFERS_{first_md5}_1.jpg"
    assert demoted.exists()
    assert demoted.read_text(encoding="utf-8") == "first-content"
    assert first_asset.primary_path == demoted
    assert first_asset.sidecars["exif"] == event_folder / "__EXIF" / (demoted.name + "._exif")
    assert first_asset.sidecars["exif"].read_text(encoding="utf-8") == "first exif"


def test_representative_suffix_ordering():
    from src.pipeline_stages.taxonomy import apply_representative_suffixes

    # Straight from the camera, RAW alongside it.
    assert apply_representative_suffixes("a.jpg", has_raw=True) == "a_HAS_RAW.jpg"
    # Extracted from the RAW. F3a: _FROM_RAW already implies the RAW exists, so
    # the two are never combined.
    assert apply_representative_suffixes(
        "a.jpg", has_raw=True, extracted_from_raw=True) == "a_FROM_RAW.jpg"
    assert apply_representative_suffixes("a.jpg", extracted_from_raw=True) == "a_FROM_RAW.jpg"
    assert apply_representative_suffixes(
        "a.jpg", has_raw=True, extracted_from_raw=True, has_edited=True) == "a_FROM_RAW_HAS_EDIT.jpg"
    assert apply_representative_suffixes("a.jpg", has_edited=True) == "a_HAS_EDIT.jpg"
    # A JPG-only shot carries nothing.
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
    # A dated video is a representative and sits at the top level beside the
    # stills (ARCHIVE_STANDARD.md V1) — there is no __VIDEOS subfolder.
    assert (event_folder / "clip.mp4").exists()
    assert not (event_folder / "__VIDEOS").exists()
    # RAW-only shot: the extracted JPEG is promoted to representative and marked
    # _FROM_RAW — its own provenance, distinct from a camera JPG's _HAS_RAW.
    assert (event_folder / "shot_extracted_FROM_RAW.jpg").exists()
    # Promotion means the extraction is the representative, so nothing is left
    # over in __RAW_EXTRACTED_JPGS.
    assert not (event_folder / "__RAW_EXTRACTED_JPGS").exists()


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
    # Straight from the camera, and a RAW exists: _HAS_RAW, never _FROM_RAW.
    assert (event_folder / "pair_HAS_RAW.jpg").exists()
    assert (event_folder / "__RAW" / "pair.cr2").exists()
    root_files = [path for path in event_folder.iterdir() if path.is_file()]
    assert len(root_files) == 1


def test_three_shooting_modes_are_distinguishable_at_the_top_level(tmp_path):
    """a) JPG-only, b) JPG+RAW, c) RAW-only — each says so in its own name.

    The point of the vocabulary: looking at the top level alone tells you how a
    shot was taken and whether there is a RAW worth developing instead.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["inbox_folder"])
    inbox.mkdir(parents=True)
    captured = datetime.datetime(2026, 5, 14, 10, 30, 0)

    def make(name, content, **extra):
        path = inbox / name
        path.write_text(content, encoding="utf-8")
        asset = MediaAsset(path, extra.pop("sidecars", None) or {})
        asset.metadata.update({
            "captured_at": captured,
            "image_datetime": extra["stamp"],
            "camera_symbol": "C6D",
        })
        return asset

    # a) JPG-only
    alone = make("alone.jpg", "solo", stamp="2026-05-14_(Thu)_10.30.00")
    # b) JPG + RAW, same shot key
    paired_jpg = make("paired.jpg", "cam-jpg", stamp="2026-05-14_(Thu)_10.31.00")
    paired_raw = make("paired.cr2", "raw-bytes", stamp="2026-05-14_(Thu)_10.31.00")
    # c) RAW-only, with an extraction and that extraction's own sidecar
    extracted = inbox / "lonely_extracted.jpg"
    extracted.write_text("from-raw", encoding="utf-8")
    extracted_exif = inbox / "lonely_extracted.jpg._exif"
    extracted_exif.write_text("File Name : lonely_extracted.jpg", encoding="utf-8")
    raw_only = make("lonely.cr2", "raw-only-bytes", stamp="2026-05-14_(Thu)_10.32.00",
                    sidecars={"converted_jpg": extracted,
                              "converted_jpg_exif": extracted_exif})

    context = PipelineContext(config=config)
    context.assets = [alone, paired_jpg, paired_raw, raw_only]
    FolderSortingStage().execute(context)

    event = final_event_folder(captured, config)
    top_level = sorted(p.name for p in event.iterdir() if p.is_file())
    assert top_level == [
        "alone.jpg",                       # a) nothing to say
        "lonely_extracted_FROM_RAW.jpg",   # c) this file came out of a RAW
        "paired_HAS_RAW.jpg",              # b) camera JPG, a RAW exists
    ]
    # The RAWs are below, not at the top level.
    assert (event / "__RAW" / "paired.cr2").is_file()
    assert (event / "__RAW" / "lonely.cr2").is_file()
    # X4/V: the promoted extraction has a sidecar of its own, named after it and
    # sitting in the __EXIF beside it — not borrowing the RAW's.
    assert (event / "__EXIF" / "lonely_extracted_FROM_RAW.jpg._exif").is_file()
    # RAW-only shots are reported, not silently absorbed.
    assert context.counters["raw_only_shots"] == 1
    assert context.counters["raw_only_promoted"] == 1


def test_extraction_beside_a_camera_jpg_goes_to_raw_extracted_jpgs(tmp_path):
    """The one case an extraction is *not* the representative: the shot already
    has a straight-from-camera JPG, so the extraction is an alternate."""
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["inbox_folder"])
    inbox.mkdir(parents=True)
    captured = datetime.datetime(2026, 5, 14, 10, 30, 0)
    shared = {"captured_at": captured, "image_datetime": "2026-05-14_(Thu)_10.30.00",
              "camera_symbol": "C6D"}

    jpg = inbox / "pair.jpg"
    jpg.write_text("cam-jpg", encoding="utf-8")
    camera = MediaAsset(jpg)
    camera.metadata.update(shared)

    raw = inbox / "pair.cr2"
    raw.write_text("raw-bytes", encoding="utf-8")
    extracted = inbox / "pair_extracted.jpg"
    extracted.write_text("from-raw", encoding="utf-8")
    raw_asset = MediaAsset(raw, {"converted_jpg": extracted})
    raw_asset.metadata.update(shared)

    context = PipelineContext(config=config)
    context.assets = [camera, raw_asset]
    FolderSortingStage().execute(context)

    event = final_event_folder(captured, config)
    assert (event / "pair_HAS_RAW.jpg").is_file()
    assert (event / "__RAW_EXTRACTED_JPGS" / "pair_extracted.jpg").is_file()
    # Exactly one representative at the top level (F5).
    assert [p.name for p in event.iterdir() if p.is_file()] == ["pair_HAS_RAW.jpg"]
    # Not a RAW-only shot, so nothing is reported as one.
    assert context.counters["raw_only_shots"] == 0
