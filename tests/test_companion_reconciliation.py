from pathlib import Path

import pytest

from src.core import PipelineContext
from src.pipeline_stages.companion_reconciliation import (
    CompanionReconciliationStage,
    reconcile_folder,
    shot_key,
)

# A representative image and its companions, sharing the leading date+time.
STEM = "2026-07-18_(Sat)_17.04.53"


def make_config(enabled=True):
    return {
        "taxonomy": {"raw": "__RAW", "exif": "__EXIF", "videos": "__VIDEOS"},
        "companion_reconciliation": {"enabled": enabled},
    }


def build_split_layout(tmp_path):
    """A grouped day: leftover __TO_SPLIT__ folder with companions in taxonomy
    subdirs, and a sibling sub-event folder that received the representative."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    (to_split / "__RAW").mkdir(parents=True)
    (to_split / "__EXIF").mkdir(parents=True)
    (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").write_bytes(b"raw")
    (to_split / "__EXIF" / f"{STEM}__f8.0__6D_RAW.JPG._exif").write_bytes(b"exif")

    sub_event = month / "2026-07-18__17.04.53 - Morning hike"
    sub_event.mkdir(parents=True)
    (sub_event / f"{STEM}__f8.0__6D_RAW.JPG").write_bytes(b"jpg")
    return to_split, sub_event


def test_shot_key_normalizes_forms():
    assert shot_key("2026-07-18_(Sat)_17.04.53__meta.JPG") == "20260718170453"
    assert shot_key("2026-07-18__17.04.53__SCR.png") == "20260718170453"
    assert shot_key("2026-07-18_(Sat)_17.04.53__RAW__meta.CR2") == "20260718170453"
    assert shot_key("not-a-dated-file.png") is None


def test_companions_follow_representative_into_sub_event(tmp_path):
    to_split, sub_event = build_split_layout(tmp_path)

    moved, unmatched = reconcile_folder(to_split, make_config())

    assert (moved, unmatched) == (2, 0)
    assert (sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()
    assert (sub_event / "__EXIF" / f"{STEM}__f8.0__6D_RAW.JPG._exif").is_file()
    # Emptied taxonomy subdirs in the leftover folder are pruned.
    assert not (to_split / "__RAW").exists()
    assert not (to_split / "__EXIF").exists()


def test_unmatched_companion_left_in_place(tmp_path):
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    (to_split / "__VIDEOS").mkdir(parents=True)
    # A video whose shot was never shown in the grouper — no representative moved
    orphan = to_split / "__VIDEOS" / "2026-07-18_(Sat)_09.00.00__clip.MP4"
    orphan.write_bytes(b"vid")
    # A sub-event exists but for a different shot
    sub = month / "2026-07-18__17.04.53 - Hike"
    sub.mkdir(parents=True)
    (sub / f"{STEM}__meta.JPG").write_bytes(b"jpg")

    moved, unmatched = reconcile_folder(to_split, make_config())

    assert (moved, unmatched) == (0, 1)
    assert orphan.is_file()  # untouched


def test_no_taxonomy_dirs_is_noop(tmp_path):
    month = tmp_path / "2026" / "07. July"
    folder = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    folder.mkdir(parents=True)
    (folder / f"{STEM}__meta.JPG").write_bytes(b"jpg")

    assert reconcile_folder(folder, make_config()) == (0, 0)


def test_existing_target_not_overwritten(tmp_path):
    to_split, sub_event = build_split_layout(tmp_path)
    # Pre-existing companion at the destination
    (sub_event / "__RAW").mkdir()
    existing = sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2"
    existing.write_bytes(b"original")

    moved, unmatched = reconcile_folder(to_split, make_config())

    # RAW skipped (already present), EXIF moved
    assert moved == 1
    assert existing.read_bytes() == b"original"
    assert (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()  # left in place


def test_stage_disabled_skips(tmp_path):
    to_split, _ = build_split_layout(tmp_path)
    context = PipelineContext(config=make_config(enabled=False))
    context.screenshot_grouped_folders = [to_split]

    CompanionReconciliationStage().execute(context)

    assert any("disabled" in line for line in context.logs)
    assert (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()  # not moved


def test_stage_reconciles_grouped_folders(tmp_path):
    to_split, sub_event = build_split_layout(tmp_path)
    context = PipelineContext(config=make_config(enabled=True))
    context.screenshot_grouped_folders = [to_split]

    CompanionReconciliationStage().execute(context)

    assert context.counters["companions_reconciled"] == 2
    assert (sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()


def test_stage_in_default_pipeline_after_grouping():
    from src.pipeline_stages import build_default_stages

    stages = build_default_stages()
    ids = [stage.stage_id for stage in stages]
    assert "companion-reconciliation" in ids
    stage = stages[ids.index("companion-reconciliation")]
    assert stage.dependencies == ("screenshot-grouping",)
