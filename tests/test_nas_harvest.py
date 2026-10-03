"""NAS harvest: the NAS inbox is emptied into the local INBOX without ever
putting a file on the NAS at risk.

The NAS inbox lives inside the only backup share, so every test here asks the
same question in a different failure: after the run, is every byte that was on
the NAS still on the NAS -- in the inbox or parked under ``__HARVESTED`` -- and
is every byte that reached the local INBOX a verified copy of one of them?

A temporary folder stands in for the NAS; no real photo is involved.
"""

import os
import time
from pathlib import Path

import pytest

from src.core import PipelineContext, file_md5, normalize_config_paths
from src.pipeline_stages import nas_harvest
from src.pipeline_stages.nas_harvest import \
    NasHarvestStage, \
    rename_no_replace

OLD = time.time() - 24 * 3600


def make_context(tmp_path, **settings):
    root = tmp_path / "archive"
    working = root / "____INGEST_PIPELINE"
    nas = tmp_path / "nas" / "INBOX"
    nas.mkdir(parents=True)
    (working / "INBOX").mkdir(parents=True)
    context = PipelineContext(
        config={
            "paths": {
                "root_folder": str(root),
                "working_folder": str(working),
                "inbox_folder": str(working / "INBOX"),
                "unsorted_folder": str(working / "INBOX"),
                "ready_folder": str(working / "READY"),
                "temp_folder": str(working / ".TMP"),
                "temp_root": str(working / ".TMP"),
                "ingest": {"nas_inbox": str(nas)},
            },
            "extensions": {
                "lossy_images": [".jpg"],
                "raw_images": [".cr2"],
                "videos": [".mp4"],
            },
            "provenance": {"dont_move_folder": "__DONT_MOVE", "journal_folder": ".JOURNAL"},
            "safety": {"enabled": True, "hash_chunk_size": 1024},
            # Settling is tested on its own; elsewhere a file counts as finished.
            "nas_harvest": {"enabled": True, "settle_seconds": 0, **settings},
        }
    )
    return context, nas, working / "INBOX"


def drop(folder: Path, relative: str, content: bytes = b"photo") -> Path:
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    os.utime(path, (OLD, OLD))
    return path


def harvested(nas: Path) -> list[Path]:
    root = nas / "__HARVESTED"
    if not root.exists():
        return []
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.name != nas_harvest.MANIFEST_NAME
    )


def nas_bytes(nas: Path) -> list[bytes]:
    """Every media byte on the NAS, wherever it now sits, manifests aside."""
    return sorted(
        path.read_bytes() for path in nas.rglob("*")
        if path.is_file() and path.name != nas_harvest.MANIFEST_NAME
    )


def run(context):
    return NasHarvestStage().execute(context)


# -- the normal case ---------------------------------------------------------

def test_a_file_is_copied_verified_and_its_original_parked(tmp_path):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")

    run(context)

    assert (inbox / "IMG_1.jpg").read_bytes() == b"one"
    assert not (nas / "IMG_1.jpg").exists()
    [parked] = harvested(nas)
    assert parked.name == "IMG_1.jpg" and parked.read_bytes() == b"one"
    # The copy keeps the original's timestamp.
    assert (inbox / "IMG_1.jpg").stat().st_mtime == pytest.approx(OLD, abs=2)
    assert file_md5(inbox / "IMG_1.jpg") in context.input_snapshot
    assert context.stage_stats["nas-harvest"]["outputs"] == 1


def test_subfolders_keep_their_shape_and_empty_ones_are_tidied(tmp_path):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "Trip to Rome/IMG_2.jpg", b"two")

    run(context)

    assert (inbox / "Trip to Rome" / "IMG_2.jpg").read_bytes() == b"two"
    [parked] = harvested(nas)
    assert parked.parent.name == "Trip to Rome"
    assert not (nas / "Trip to Rome").exists()


def test_every_run_parks_into_a_new_folder_of_its_own(tmp_path):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")
    run(context)
    (inbox / "IMG_1.jpg").unlink()           # processed and sorted away
    drop(nas, "IMG_1.jpg", b"same name, later drop")
    second = PipelineContext(config=context.config)

    run(second)

    assert len(harvested(nas)) == 2
    assert len({path.parent for path in harvested(nas)}) == 2
    assert nas_bytes(nas) == sorted([b"one", b"same name, later drop"])


def test_a_manifest_records_each_park_on_the_nas(tmp_path):
    context, nas, _inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")

    run(context)

    [manifest] = list((nas / "__HARVESTED").rglob(nas_harvest.MANIFEST_NAME))
    text = manifest.read_text(encoding="utf-8")
    assert "IMG_1.jpg" in text and file_md5(harvested(nas)[0]) in text


# -- what is left alone --------------------------------------------------------

def test_a_file_still_arriving_is_left_alone(tmp_path):
    context, nas, inbox = make_context(tmp_path, settle_seconds=300)
    fresh = nas / "UPLOADING.jpg"
    fresh.write_bytes(b"half")

    run(context)

    assert fresh.read_bytes() == b"half"
    assert not (inbox / "UPLOADING.jpg").exists()
    assert context.stage_stats["nas-harvest"]["settling"] == 1
    [note] = context.stage_notes["nas-harvest"]
    assert "ready in about 5 min" in note


def test_synology_and_system_folders_are_never_taken(tmp_path):
    context, nas, inbox = make_context(tmp_path)
    for relative in ("@eaDir/IMG_1.jpg/SYNOPHOTO_THUMB_M.jpg", "#recycle/old.jpg",
                     "__DONT_MOVE/keep.jpg", "Thumbs.db", ".DS_Store",
                     "__HARVESTED/earlier/IMG_0.jpg"):
        drop(nas, relative)

    run(context)

    assert list(inbox.rglob("*")) == []
    assert (nas / "__DONT_MOVE" / "keep.jpg").exists()
    assert (nas / "@eaDir" / "IMG_1.jpg" / "SYNOPHOTO_THUMB_M.jpg").exists()


def test_a_different_file_of_the_same_name_in_the_inbox_blocks_the_harvest(tmp_path):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"nas version")
    drop(inbox, "IMG_1.jpg", b"local version")

    run(context)

    assert (nas / "IMG_1.jpg").read_bytes() == b"nas version"
    assert (inbox / "IMG_1.jpg").read_bytes() == b"local version"
    assert harvested(nas) == []
    assert context.stage_stats["nas-harvest"]["errors"] == 1


def test_a_copy_that_does_not_match_is_discarded_and_the_original_kept(tmp_path, monkeypatch):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")
    monkeypatch.setattr(nas_harvest, "file_md5", lambda *_args, **_kwargs: "0" * 32)

    run(context)

    assert (nas / "IMG_1.jpg").read_bytes() == b"one"
    assert list(inbox.rglob("*")) == []
    assert harvested(nas) == []
    assert list((Path(context.config["paths"]["temp_folder"])).rglob("*.partial")) == []


def test_a_file_that_changes_while_copied_is_left_on_the_nas(tmp_path, monkeypatch):
    context, nas, inbox = make_context(tmp_path)
    source = drop(nas, "IMG_1.jpg", b"one")
    original_copy = nas_harvest.copy_with_md5

    def copy_then_grow(src, dst, *args):
        digest = original_copy(src, dst, *args)
        with Path(src).open("ab") as handle:   # the phone app is still writing
            handle.write(b" more")
        return digest

    monkeypatch.setattr(nas_harvest, "copy_with_md5", copy_then_grow)

    run(context)

    assert source.read_bytes() == b"one more"
    assert list(inbox.rglob("*")) == []
    assert harvested(nas) == []


def test_an_unreachable_nas_is_skipped(tmp_path):
    context, nas, _inbox = make_context(tmp_path)
    context.config["paths"]["ingest"]["nas_inbox"] = str(tmp_path / "asleep" / "INBOX")

    run(context)

    assert "nas-harvest" not in context.stage_stats or \
        context.stage_stats["nas-harvest"].get("outputs", 0) == 0


def test_disabled_does_nothing(tmp_path):
    context, nas, inbox = make_context(tmp_path, enabled=False)
    drop(nas, "IMG_1.jpg")

    run(context)

    assert (nas / "IMG_1.jpg").exists()
    assert list(inbox.rglob("*")) == []


def test_a_nas_inbox_that_is_the_local_inbox_is_refused(tmp_path):
    """A run rooted on the NAS photo root would make the two the same folder."""
    context, _nas, inbox = make_context(tmp_path)
    context.config["paths"]["ingest"]["nas_inbox"] = str(inbox)
    drop(inbox, "IMG_1.jpg")

    run(context)

    assert (inbox / "IMG_1.jpg").exists()
    assert not (inbox / "__HARVESTED").exists()


# -- recovering from a run that died half-way ------------------------------------

def test_a_failed_park_is_finished_next_run_without_a_second_copy(tmp_path, monkeypatch):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")
    real_rename = nas_harvest.rename_no_replace

    def refuse_on_the_nas(source, target):
        if Path(target).is_relative_to(nas):
            raise OSError("network name no longer available")
        return real_rename(source, target)

    monkeypatch.setattr(nas_harvest, "rename_no_replace", refuse_on_the_nas)
    run(context)
    assert (nas / "IMG_1.jpg").exists()          # copied, but not parked
    assert (inbox / "IMG_1.jpg").exists()

    # Before the next run, the pipeline has processed the copy and moved it on.
    (inbox / "IMG_1.jpg").unlink()
    monkeypatch.setattr(nas_harvest, "rename_no_replace", real_rename)
    run(PipelineContext(config=context.config))

    assert not (nas / "IMG_1.jpg").exists()
    assert [path.read_bytes() for path in harvested(nas)] == [b"one"]
    assert list(inbox.rglob("*")) == []          # not delivered a second time


def test_an_identical_copy_already_in_the_inbox_just_parks_the_original(tmp_path):
    context, nas, inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")
    drop(inbox, "IMG_1.jpg", b"one")

    run(context)

    assert (inbox / "IMG_1.jpg").read_bytes() == b"one"
    assert [path.read_bytes() for path in harvested(nas)] == [b"one"]
    assert sorted(path.name for path in inbox.rglob("*")) == ["IMG_1.jpg"]


# -- the no-overwrite guarantee ----------------------------------------------------

def test_rename_no_replace_refuses_a_taken_name(tmp_path):
    source = drop(tmp_path, "a.jpg", b"a")
    target = drop(tmp_path, "b.jpg", b"b")

    with pytest.raises(FileExistsError):
        rename_no_replace(source, target)

    assert source.read_bytes() == b"a" and target.read_bytes() == b"b"


def test_a_park_that_would_land_on_a_taken_name_leaves_the_original(tmp_path, monkeypatch):
    context, nas, _inbox = make_context(tmp_path)
    drop(nas, "IMG_1.jpg", b"one")
    real_park_folder = nas_harvest.NasHarvestStage._run_folder

    def occupied(self, *args):
        folder = real_park_folder(self, *args)
        (folder / "IMG_1.jpg").write_bytes(b"already here")
        return folder

    monkeypatch.setattr(nas_harvest.NasHarvestStage, "_run_folder", occupied)

    run(context)

    assert (nas / "IMG_1.jpg").read_bytes() == b"one"
    assert nas_bytes(nas) == sorted([b"one", b"already here"])


def test_the_stage_never_reaches_for_a_replacing_or_deleting_call():
    source = Path(nas_harvest.__file__).read_text(encoding="utf-8")
    for forbidden in ("os.replace", "shutil.move", "shutil.copy", "rmtree",
                      "safe_move", "safe_delete", ".replace("):
        assert forbidden not in source, forbidden


# -- configuration -------------------------------------------------------------

def test_a_scratch_run_cannot_harvest_the_real_nas(tmp_path):
    """Same guard as Camera Uploads: an undeclared root confines the path."""
    declared = {
        "paths": {
            "root_folder": r"c:\__PHOTOS",
            "ingest": {"nas_inbox": r"\\synology-dell\SHARE\__PHOTOS\____INGEST_PIPELINE\INBOX"},
        }
    }
    config = {"paths": {"root_folder": r"c:\__PHOTOS",
                        "ingest": dict(declared["paths"]["ingest"])}}

    normalize_config_paths(config, base_folder=tmp_path, declared_config=declared)

    assert Path(config["paths"]["ingest"]["nas_inbox"]).is_relative_to(tmp_path)


# -- never processing the NAS inbox in place -------------------------------------

def test_a_run_whose_inbox_is_the_nas_inbox_refuses_to_start(tmp_path):
    from src.core import PipelineConfigError
    from src.pipeline_stages.initialization import InitializationStage

    context, nas, _inbox = make_context(tmp_path)
    context.config["paths"]["unsorted_folder"] = str(nas)
    context.config["paths"]["inbox_folder"] = str(nas)
    drop(nas, "IMG_1.jpg", b"one")

    with pytest.raises(PipelineConfigError, match="NAS inbox"):
        InitializationStage().execute(context)

    assert (nas / "IMG_1.jpg").read_bytes() == b"one"


def test_the_nas_inbox_check_ignores_case_and_a_trailing_slash(tmp_path):
    config = {"paths": {"ingest": {"nas_inbox": r"\\NAS\Share\__PHOTOS\____INGEST_PIPELINE\INBOX"}}}

    assert nas_harvest.is_nas_inbox(config, "\\\\nas\\share\\__photos\\____ingest_pipeline\\inbox\\")
    assert not nas_harvest.is_nas_inbox(config, r"c:\__PHOTOS\____INGEST_PIPELINE\INBOX")
    assert not nas_harvest.is_nas_inbox({"paths": {}}, r"c:\__PHOTOS\____INGEST_PIPELINE\INBOX")
