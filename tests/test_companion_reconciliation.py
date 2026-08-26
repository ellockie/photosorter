from pathlib import Path

import pytest

from src.core import PipelineContext
from src.pipeline_stages import companion_reconciliation
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


def collect(logs):
    return "\n".join(logs)


def test_shot_key_normalizes_forms():
    assert shot_key("2026-07-18_(Sat)_17.04.53__meta.JPG") == "20260718170453"
    assert shot_key("2026-07-18__17.04.53__SCR.png") == "20260718170453"
    assert shot_key("2026-07-18_(Sat)_17.04.53__RAW__meta.CR2") == "20260718170453"
    assert shot_key("not-a-dated-file.png") is None


def test_representative_reprefixed_by_the_grouper_still_matches(tmp_path):
    """An older grouper re-standardised names by *prefixing* its own timestamp
    (taken from the file's mtime) and pushing the Photosorter name into trailing
    text. The sidecar in __EXIF still carries only the original stamp, so
    matching on the leading stamp alone stranded every one of them — the state
    found in the July 2026 folders. Both stamps must be honoured."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-19_(Sun) - __TO_SPLIT__(i=1)"
    (to_split / "__EXIF").mkdir(parents=True)
    original = "2026-07-19_(Sun)_15.37.10__f1.7__T1_460__SG23U"
    (to_split / "__EXIF" / f"{original}.jpg._exif").write_bytes(b"exif")

    sub_event = month / "2026-07-19__21.29.04 - Hikaru's guitar exam place"
    sub_event.mkdir(parents=True)
    # Grouper prefix (mtime-derived) + the original Photosorter name.
    (sub_event / f"2026-07-19__21.29.04__SCR__{original}.jpg").write_bytes(b"jpg")

    report = reconcile_folder(to_split, make_config())

    assert (report.moved, report.unmatched, report.errors) == (1, 0, 0)
    assert (sub_event / "__EXIF" / f"{original}.jpg._exif").is_file()


def test_companions_follow_representative_into_sub_event(tmp_path):
    to_split, sub_event = build_split_layout(tmp_path)

    report = reconcile_folder(to_split, make_config())

    assert (report.moved, report.unmatched, report.errors) == (2, 0, 0)
    assert (sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()
    assert (sub_event / "__EXIF" / f"{STEM}__f8.0__6D_RAW.JPG._exif").is_file()
    # Emptied taxonomy subdirs in the leftover folder are pruned.
    assert not (to_split / "__RAW").exists()
    assert not (to_split / "__EXIF").exists()


def test_sub_event_past_the_day_boundary_is_matched(tmp_path):
    """A group starting after midnight is named by the grouper after the *next*
    day, but still belongs to this event folder — its companions must follow."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    (to_split / "__RAW").mkdir(parents=True)
    night = "2026-07-19_(Sun)_00.30.00"
    companion = to_split / "__RAW" / f"{night}__RAW__f2.8__6D.CR2"
    companion.write_bytes(b"raw")

    sub_event = month / "2026-07-19__00.30.00 - Night walk"
    sub_event.mkdir(parents=True)
    (sub_event / f"{night}__f2.8__6D_RAW.JPG").write_bytes(b"jpg")

    report = reconcile_folder(to_split, make_config())

    assert (report.moved, report.unmatched) == (1, 0)
    assert (sub_event / "__RAW" / f"{night}__RAW__f2.8__6D.CR2").is_file()


def test_unsplit_group_in_new_to_split_sibling_is_matched(tmp_path):
    """A group the user left unsplit gets its own __TO_SPLIT__ sibling folder;
    its companions must follow it there, not be stranded."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=2)"
    (to_split / "__EXIF").mkdir(parents=True)
    (to_split / "__EXIF" / f"{STEM}__f8.0__6D.JPG._exif").write_bytes(b"exif")

    leftover = month / "2026-07-18__17.04.53 - __TO_SPLIT__(i=1)"
    leftover.mkdir(parents=True)
    (leftover / f"{STEM}__f8.0__6D.JPG").write_bytes(b"jpg")

    report = reconcile_folder(to_split, make_config())

    assert (report.moved, report.unmatched) == (1, 0)
    assert (leftover / "__EXIF" / f"{STEM}__f8.0__6D.JPG._exif").is_file()


def test_representative_still_in_event_folder_counts_as_in_place(tmp_path):
    """The user kept a group in the original folder: its companions belong here
    and must not be reported as unmatched."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    (to_split / "__RAW").mkdir(parents=True)
    (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").write_bytes(b"raw")
    (to_split / f"{STEM}__f8.0__6D_RAW.JPG").write_bytes(b"jpg")

    report = reconcile_folder(to_split, make_config())

    assert (report.moved, report.in_place, report.unmatched) == (0, 1, 0)
    assert (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()


def test_unmatched_companion_left_in_place_and_logged(tmp_path):
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

    logs = []
    report = reconcile_folder(to_split, make_config(), logs.append)

    assert (report.moved, report.unmatched) == (0, 1)
    assert orphan.is_file()  # untouched
    assert orphan.name in collect(logs)


def test_companion_without_date_in_name_is_counted_and_logged(tmp_path):
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    (to_split / "__RAW").mkdir(parents=True)
    odd = to_split / "__RAW" / "IMG_1234.CR2"
    odd.write_bytes(b"raw")

    logs = []
    report = reconcile_folder(to_split, make_config(), logs.append)

    assert report.unkeyed == 1
    assert odd.is_file()
    assert "IMG_1234.CR2" in collect(logs)


def test_no_taxonomy_dirs_is_noop(tmp_path):
    month = tmp_path / "2026" / "07. July"
    folder = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=1)"
    folder.mkdir(parents=True)
    (folder / f"{STEM}__meta.JPG").write_bytes(b"jpg")

    assert reconcile_folder(folder, make_config()).seen == 0


def test_missing_event_folder_is_reported_as_an_error(tmp_path):
    logs = []
    report = reconcile_folder(tmp_path / "gone", make_config(), logs.append)

    assert report.errors == 1
    assert "gone" in collect(logs)


def test_existing_target_not_overwritten_but_logged(tmp_path):
    to_split, sub_event = build_split_layout(tmp_path)
    # Pre-existing companion at the destination
    (sub_event / "__RAW").mkdir()
    existing = sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2"
    existing.write_bytes(b"original")

    logs = []
    report = reconcile_folder(to_split, make_config(), logs.append)

    # RAW skipped (already present), EXIF moved
    assert (report.moved, report.already_present) == (1, 1)
    assert existing.read_bytes() == b"original"
    assert (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()  # left in place
    assert "already present" in collect(logs)


def test_move_failure_is_logged_and_does_not_stop_the_folder(tmp_path, monkeypatch):
    to_split, sub_event = build_split_layout(tmp_path)

    def fake_move(source, destination, *args, **kwargs):
        if Path(source).suffix == ".CR2":
            raise PermissionError("file is locked by another process")
        Path(destination).parent.mkdir(parents=True, exist_ok=True)
        Path(source).rename(destination)
        return Path(destination)

    monkeypatch.setattr(companion_reconciliation, "safe_move", fake_move)

    logs = []
    report = reconcile_folder(to_split, make_config(), logs.append)

    assert report.errors == 1
    assert report.moved == 1  # the EXIF companion still went through
    assert (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()
    log_text = collect(logs)
    assert "could not move" in log_text
    assert "locked by another process" in log_text


def test_burst_shots_sharing_a_second_go_to_the_right_sub_event(tmp_path):
    """Two shots in the same second, split into different sub-events: the
    companion follows the representative whose name it shares the most with."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=2)"
    (to_split / "__RAW").mkdir(parents=True)
    (to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").write_bytes(b"a")
    (to_split / "__RAW" / f"{STEM}__RAW__f2.8__5D.CR2").write_bytes(b"b")

    first = month / "2026-07-18__17.04.53 - Wide"
    first.mkdir(parents=True)
    (first / f"{STEM}__f8.0__6D_RAW.JPG").write_bytes(b"jpg")
    second = month / "2026-07-18__17.04.53 - Close"
    second.mkdir(parents=True)
    (second / f"{STEM}__f2.8__5D_RAW.JPG").write_bytes(b"jpg")

    report = reconcile_folder(to_split, make_config())

    assert report.moved == 2
    assert (first / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()
    assert (second / "__RAW" / f"{STEM}__RAW__f2.8__5D.CR2").is_file()


def test_burst_split_between_here_and_a_sub_event(tmp_path):
    """One of two same-second shots was moved out, the other kept in place: each
    companion follows its own representative."""
    month = tmp_path / "2026" / "07. July"
    to_split = month / "2026-07-18_(Sat) - __TO_SPLIT__(i=2)"
    (to_split / "__RAW").mkdir(parents=True)
    stays = to_split / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2"
    stays.write_bytes(b"a")
    (to_split / "__RAW" / f"{STEM}__RAW__f2.8__5D.CR2").write_bytes(b"b")
    (to_split / f"{STEM}__f8.0__6D_RAW.JPG").write_bytes(b"jpg")

    sub_event = month / "2026-07-18__17.04.53 - Close"
    sub_event.mkdir(parents=True)
    (sub_event / f"{STEM}__f2.8__5D_RAW.JPG").write_bytes(b"jpg")

    report = reconcile_folder(to_split, make_config())

    assert (report.moved, report.in_place, report.unmatched) == (1, 1, 0)
    assert stays.is_file()
    assert (sub_event / "__RAW" / f"{STEM}__RAW__f2.8__5D.CR2").is_file()


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
    assert context.counters["companions_reconcile_errors"] == 0
    assert (sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()


def test_stage_reports_vanished_folder_and_keeps_going(tmp_path):
    to_split, sub_event = build_split_layout(tmp_path)
    context = PipelineContext(config=make_config(enabled=True))
    context.screenshot_grouped_folders = [tmp_path / "vanished", to_split]

    CompanionReconciliationStage().execute(context)

    log_text = collect(context.logs)
    assert "vanished" in log_text
    assert context.counters["companions_reconcile_errors"] == 1
    # The surviving folder was still processed.
    assert context.counters["companions_reconciled"] == 2
    assert (sub_event / "__RAW" / f"{STEM}__RAW__f8.0__6D.CR2").is_file()
    assert context.stage_stats["companion-reconciliation"]["errors"] == 1


def test_stage_survives_an_unexpected_failure_on_one_folder(tmp_path, monkeypatch):
    to_split, _ = build_split_layout(tmp_path)
    context = PipelineContext(config=make_config(enabled=True))
    context.screenshot_grouped_folders = [to_split]

    def boom(*args, **kwargs):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(companion_reconciliation, "reconcile_folder", boom)

    CompanionReconciliationStage().execute(context)

    assert "unexpected" in collect(context.logs)
    assert context.counters["companions_reconcile_errors"] == 1


def test_stage_in_default_pipeline_after_grouping():
    from src.pipeline_stages import build_default_stages

    stages = build_default_stages()
    ids = [stage.stage_id for stage in stages]
    assert "companion-reconciliation" in ids
    stage = stages[ids.index("companion-reconciliation")]
    assert stage.dependencies == ("grouping-review",)
