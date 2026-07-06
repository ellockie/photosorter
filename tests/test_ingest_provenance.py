import json
from pathlib import Path

from src.core import PipelineContext, load_config, normalize_config_paths, relativize_config_paths
from src.pipeline_stages.folder_intake import FolderIntakeStage
from src.pipeline_stages.legacy_unsorted_migration import LegacyUnsortedMigrationStage
from src.pipeline_stages.provenance import \
    extract_origin_label, \
    journal_dir, \
    renamed_sidecar_path, \
    resolve_sidecar_target, \
    rewrite_sidecar_path_fields


def make_context(tmp_path):
    root = tmp_path / "archive"
    working = root / "____INGEST_PIPELINE"
    return PipelineContext(
        config={
            "paths": {
                "root_folder": str(root),
                "working_folder": str(working),
                "inbox_folder": str(working / "INBOX"),
                "ready_folder": str(working / "READY"),
                "temp_folder": str(working / ".TMP"),
                "legacy_unsorted_folder": str(tmp_path / "legacy" / "____UNSORTED"),
                "unsorted_folder": str(working / "INBOX"),
                "temp_root": str(working / ".TMP"),
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
            "provenance": {
                "dont_move_folder": "__DONT_MOVE",
                "journal_folder": ".JOURNAL",
                "geodata_extensions": [".gpx"],
            },
        }
    )


def test_extract_origin_label_strips_date_prefixes():
    assert extract_origin_label("2024-01-15 Birthday") == "Birthday"
    assert extract_origin_label("2024-01-15_18.30 Party") == "Party"
    assert extract_origin_label("2024.01.15-Trip") == "Trip"
    assert extract_origin_label("2024-01-15_(Mon) - Walk") == "Walk"
    assert extract_origin_label("Holidays") == "Holidays"
    assert extract_origin_label("2024-01-15") is None


def test_renamed_sidecar_path_keeps_embedded_extension(tmp_path):
    sidecar = tmp_path / "IMG_001.jpg._exif"
    renamed = renamed_sidecar_path(sidecar, "IMG_001.jpg", "NEW_NAME.jpg")
    assert renamed.name == "NEW_NAME.jpg._exif"

    stem_sidecar = tmp_path / "IMG_001.xmp"
    renamed = renamed_sidecar_path(stem_sidecar, "IMG_001.jpg", "NEW_NAME.jpg")
    assert renamed.name == "NEW_NAME.xmp"


def test_resolve_sidecar_target_drops_identical_and_replaces_stale(tmp_path):
    source = tmp_path / "src" / "photo.jpg._exif"
    source.parent.mkdir()
    source.write_text("EXIF-A", encoding="utf-8")
    dest_dir = tmp_path / "__EXIF"
    dest_dir.mkdir()
    target = dest_dir / "photo.jpg._exif"

    # Target free: returned as-is.
    assert resolve_sidecar_target(source, target) == target

    # Identical content already there: caller should drop the redundant copy.
    target.write_text("EXIF-A", encoding="utf-8")
    assert resolve_sidecar_target(source, target) is None

    # Different content = stale orphan from a prior run: replace it in place.
    # The sidecar never gets a hash of its own embedded in the name.
    target.write_text("EXIF-STALE", encoding="utf-8")
    resolved = resolve_sidecar_target(source, target)
    assert resolved == target
    assert not target.exists()  # stale orphan deleted, name freed for the move
    assert "_DUPE_" not in resolved.name


def test_rewrite_sidecar_path_fields_only_touches_name_and_directory(tmp_path):
    sidecar = tmp_path / "out.jpg._exif"
    sidecar.write_text(
        "\n".join([
            "File Name                       : IMG_0001.jpg",
            "Directory                       : C:/__PHOTOS/____INGEST_PIPELINE/INBOX",
            "File Modification Date/Time     : 2018:10:14 17:28:25+02:00",
            "Camera Model Name               : ILCE-7RM2",
            "Aperture                        : 4.0",
        ]),
        encoding="iso-8859-1",
    )

    rewrite_sidecar_path_fields(
        sidecar,
        "2018-10-14_(Sun)_17.28.25__f4.0__ILC7R2.jpg",
        r"C:\__PHOTOS\2018\10. October\2018-10-14_(Sun) - 1. ######",
    )

    text = sidecar.read_text(encoding="iso-8859-1")
    assert "File Name                       : 2018-10-14_(Sun)_17.28.25__f4.0__ILC7R2.jpg" in text
    assert r"Directory                       : C:\__PHOTOS\2018\10. October\2018-10-14_(Sun) - 1. ######" in text
    # Sibling System field and intrinsic fields are left exactly as-is.
    assert "File Modification Date/Time     : 2018:10:14 17:28:25+02:00" in text
    assert "Camera Model Name               : ILCE-7RM2" in text
    assert "IMG_0001.jpg" not in text


def test_folder_intake_flattens_labels_and_journals(tmp_path):
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["inbox_folder"])
    origin = inbox / "2024-01-15 Birthday"
    origin.mkdir(parents=True)
    (origin / "IMG_002.jpg").write_text("photo-two", encoding="utf-8")
    (origin / "IMG_002.jpg._exif").write_text("exif", encoding="utf-8")
    (origin / "track.gpx").write_text("<gpx/>", encoding="utf-8")

    FolderIntakeStage().execute(context)

    assert (inbox / "IMG_002.jpg").exists()
    assert (inbox / "IMG_002.jpg._exif").exists()
    assert (inbox / "track.gpx").exists()
    assert not origin.exists()

    records = list(context.provenance.values())
    assert len(records) == 1
    assert records[0]["origin_label"] == "Birthday"

    journals = list(journal_dir(context.config).glob("*.jsonl"))
    assert len(journals) == 1
    lines = [json.loads(line) for line in journals[0].read_text(encoding="utf-8").splitlines()]
    kinds = {line["kind"] for line in lines}
    assert kinds == {"media", "geodata"}
    media_record = next(line for line in lines if line["kind"] == "media")
    assert media_record["origin_label"] == "Birthday"
    assert media_record["md5"]


def test_folder_intake_skips_dont_move(tmp_path):
    context = make_context(tmp_path)
    inbox = Path(context.config["paths"]["inbox_folder"])
    protected = inbox / "__DONT_MOVE" / "nested"
    protected.mkdir(parents=True)
    keep = protected / "keep.jpg"
    keep.write_text("keep", encoding="utf-8")

    FolderIntakeStage().execute(context)

    assert keep.exists()
    assert not (inbox / "keep.jpg").exists()
    assert context.provenance == {}


def test_legacy_migration_moves_folders_except_dont_move(tmp_path):
    context = make_context(tmp_path)
    legacy = Path(context.config["paths"]["legacy_unsorted_folder"])
    inbox = Path(context.config["paths"]["inbox_folder"])
    (legacy / "2024-02-01 Walk").mkdir(parents=True)
    (legacy / "2024-02-01 Walk" / "IMG_1.jpg").write_text("photo", encoding="utf-8")
    (legacy / "__DONT_MOVE").mkdir()
    (legacy / "__DONT_MOVE" / "stay.jpg").write_text("stay", encoding="utf-8")
    (legacy / "loose.jpg").write_text("loose", encoding="utf-8")
    inbox.mkdir(parents=True)

    LegacyUnsortedMigrationStage().execute(context)

    assert (inbox / "loose.jpg").exists()
    assert (inbox / "2024-02-01 Walk" / "IMG_1.jpg").exists()
    assert (legacy / "__DONT_MOVE" / "stay.jpg").exists()


def test_normalize_and_relativize_config_roundtrip(tmp_path):
    base = tmp_path / "BASE"
    config = {
        "paths": {
            "root_folder": r"c:\__PHOTOS",
            "working_folder": "____INGEST_PIPELINE",
            "inbox_folder": "____INGEST_PIPELINE\\INBOX",
            "legacy_unsorted_folder": "____TO_SORT\\____UNSORTED",
        }
    }

    normalized = normalize_config_paths(config, base_folder=str(base))

    assert normalized["paths"]["root_folder"] == str(base)
    assert normalized["paths"]["working_folder"] == str(base / "____INGEST_PIPELINE")
    assert normalized["paths"]["inbox_folder"] == str(base / "____INGEST_PIPELINE" / "INBOX")
    assert normalized["paths"]["legacy_unsorted_folder"] == str(base / "____TO_SORT" / "____UNSORTED")

    relativized = relativize_config_paths(normalized)
    assert relativized["paths"]["root_folder"] == str(base)
    assert relativized["paths"]["working_folder"] == "____INGEST_PIPELINE"
    assert relativized["paths"]["inbox_folder"] == str(Path("____INGEST_PIPELINE") / "INBOX")


def test_base_folder_override_reroots_absolute_working_paths(tmp_path):
    # Regression: a config.json persisted with absolute c:\__PHOTOS paths must
    # not keep pointing at the real tree when --base-folder redirects the run.
    base = tmp_path / "SCRATCH"
    config = {
        "paths": {
            "root_folder": r"c:\__PHOTOS",
            "working_folder": r"c:\__PHOTOS\____INGEST_PIPELINE",
            "inbox_folder": r"c:\__PHOTOS\____INGEST_PIPELINE\INBOX",
            "ready_folder": r"c:\__PHOTOS\____INGEST_PIPELINE\READY",
            "temp_folder": r"c:\__PHOTOS\____INGEST_PIPELINE\.TMP",
            "legacy_unsorted_folder": r"c:\__PHOTOS\____TO_SORT\____UNSORTED",
            "legacy_ready_folder": r"c:\__PHOTOS\____TO_SORT\__READY",
        }
    }

    paths = normalize_config_paths(config, base_folder=str(base))["paths"]

    assert paths["root_folder"] == str(base)
    assert paths["working_folder"] == str(base / "____INGEST_PIPELINE")
    assert paths["inbox_folder"] == str(base / "____INGEST_PIPELINE" / "INBOX")
    assert paths["ready_folder"] == str(base / "____INGEST_PIPELINE" / "READY")
    assert paths["temp_folder"] == str(base / "____INGEST_PIPELINE" / ".TMP")
    assert paths["legacy_unsorted_folder"] == str(base / "____TO_SORT" / "____UNSORTED")
    assert paths["legacy_ready_folder"] == str(base / "____TO_SORT" / "__READY")
    assert paths["unsorted_folder"] == paths["inbox_folder"]


def test_base_folder_override_keeps_external_absolute_paths(tmp_path):
    # An absolute path deliberately outside the persisted root is an external
    # location and must survive a base-folder override untouched.
    base = tmp_path / "SCRATCH"
    external_inbox = tmp_path / "ELSEWHERE" / "INBOX"
    config = {
        "paths": {
            "root_folder": r"c:\__PHOTOS",
            "inbox_folder": str(external_inbox),
        }
    }

    paths = normalize_config_paths(config, base_folder=str(base))["paths"]

    assert paths["inbox_folder"] == str(external_inbox)
    assert paths["root_folder"] == str(base)


def test_load_config_with_base_folder_reroots_absolute_config(tmp_path):
    # End-to-end through load_config: an absolute-path config.json plus the
    # --base-folder CLI override must produce a fully scratch-rooted config.
    base = tmp_path / "SCRATCH"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "paths": {
                    "root_folder": r"c:\__PHOTOS",
                    "inbox_folder": r"c:\__PHOTOS\____INGEST_PIPELINE\INBOX",
                    "legacy_unsorted_folder": r"c:\__PHOTOS\____TO_SORT\____UNSORTED",
                }
            }
        ),
        encoding="utf-8",
    )

    paths = load_config(str(cfg_path), base_folder=str(base))["paths"]

    base_str = str(base).lower()
    for key in (
        "root_folder",
        "working_folder",
        "inbox_folder",
        "ready_folder",
        "temp_folder",
        "legacy_unsorted_folder",
        "legacy_ready_folder",
        "unsorted_folder",
        "temp_root",
    ):
        assert paths[key].lower().startswith(base_str), f"{key} not rerooted: {paths[key]}"
