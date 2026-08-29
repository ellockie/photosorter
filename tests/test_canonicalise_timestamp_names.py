"""The bulk renamer: every historical name shape converges on the canonical one.

Every test here passes an explicit ``--target`` under ``tmp_path``. The tool's
default target is the real archive (``c:\\__PHOTOS\\2026``) and it renames with
bare ``os.rename``, so it is not covered by the ``src.core`` sandbox guard in
conftest: a test that omitted the target would rename the live archive.
"""

import importlib.util
import json
from pathlib import Path

import pytest

TOOL_PATH = Path(__file__).resolve().parent.parent / "tools" / "canonicalise_timestamp_names.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("canonicalise_timestamp_names", TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


# --------------------------------------------------------------------------
# Name transformation
# --------------------------------------------------------------------------

@pytest.mark.parametrize("original, expected", [
    # Already canonical: untouched.
    ("2026-08-25_(Tue)__10.23.12.JPG", "2026-08-25_(Tue)__10.23.12.JPG"),
    # Previous Photosorter form: single underscore before the time.
    ("2026-08-25_(Tue)_10.23.12.JPG", "2026-08-25_(Tue)__10.23.12.JPG"),
    # Legacy grouper form: no weekday at all.
    ("2026-08-25__10.23.12.JPG", "2026-08-25_(Tue)__10.23.12.JPG"),
    # Space separators.
    ("2026-08-25 (Tue) 10.23.12.JPG", "2026-08-25_(Tue)__10.23.12.JPG"),
])
def test_every_historical_shape_becomes_the_canonical_one(original, expected):
    assert tool.canonical_name(original) == expected


def test_a_wrong_weekday_is_corrected_from_the_date():
    # 2026-08-25 is a Tuesday; a stale name claiming Friday is repaired.
    assert tool.canonical_name("2026-08-25_(Fri)__10.23.12.JPG") == \
        "2026-08-25_(Tue)__10.23.12.JPG"


def test_weekday_case_is_normalised():
    assert tool.canonical_name("2026-08-25_(tue)__10.23.12.JPG") == \
        "2026-08-25_(Tue)__10.23.12.JPG"


def test_the_rest_of_the_name_survives_byte_for_byte():
    original = "2015-11-23_(Mon)_09.26.27__RAW__f4.0__T1_20..50mm1250__DUPL_(3).CRW"
    assert tool.canonical_name(original) == \
        "2015-11-23_(Mon)__09.26.27__RAW__f4.0__T1_20..50mm1250__DUPL_(3).CRW"


def test_both_timestamps_in_a_grouper_name_are_rewritten():
    original = "2026-07-19__21.29.04__SCR__2026-07-19_(Sun)_15.37.10__f1.7.png"
    assert tool.canonical_name(original) == \
        "2026-07-19_(Sun)__21.29.04__SCR__2026-07-19_(Sun)__15.37.10__f1.7.png"


def test_a_day_folder_without_a_weekday_gains_one():
    assert tool.canonical_name("2014-05-08 - 1. ######") == \
        "2014-05-08_(Thu) - 1. ######"


def test_a_day_folder_that_is_already_canonical_is_untouched():
    assert tool.canonical_name("2014-05-08_(Thu) - 1. ######") == \
        "2014-05-08_(Thu) - 1. ######"


def test_a_name_carrying_no_timestamp_is_untouched():
    for name in ("##   RAWs   ##", "holiday pictures", "notes.txt", "__DONT_MOVE"):
        assert tool.canonical_name(name) == name


def test_an_impossible_date_is_left_alone_rather_than_invented():
    # The shape matches the grammar; the calendar rejects it. Renaming it would
    # have to guess a real date, so the name stays exactly as found.
    for name in ("2026-02-31__10.00.00.JPG", "2026-08-25__25.99.99.JPG"):
        assert tool.canonical_name(name) == name
        assert tool.carries_impossible_stamp(name)


# --------------------------------------------------------------------------
# The grouping placeholder
# --------------------------------------------------------------------------

CONFIG = {
    "legacy": {"date_folder_suffix": " - 1. ######"},
    "extensions": {
        "lossy_images": [".jpg", ".jpeg", ".thm"],
        "other_images": [".png", ".heic"],
        "raw_images": [".arw", ".cr2", ".crw"],
        "videos": [".mp4", ".mov"],
        "sidecars": ["._exif"],
    },
}

MEDIA_EXTENSIONS = {
    extension
    for group in ("lossy_images", "other_images", "raw_images", "videos")
    for extension in CONFIG["extensions"][group]
}


def _placeholder_folder(root, name, files, sidecars=True):
    """A day folder holding ``files``.

    By default every media file also gets its "._exif" in "__EXIF", which is
    how the pipeline leaves a real day. That matters now that the folder name
    reports what the media counts do not account for: a day set up this way is
    in order, and must come out carrying no audit markers at all.
    """
    folder = root / name
    folder.mkdir(parents=True)
    for filename in files:
        (folder / filename).write_text("x", encoding="utf-8")
    if sidecars:
        _sidecars_for(folder, files)
    return folder


def _sidecars_for(folder, filenames):
    media = [name for name in filenames
             if Path(name).suffix.lower() in MEDIA_EXTENSIONS]
    if not media:
        return
    exif = folder / "__EXIF"
    exif.mkdir(exist_ok=True)
    for name in media:
        (exif / (name + "._exif")).write_text("x", encoding="utf-8")


def _stamped(day, time, extension=".jpg"):
    return f"{day}__{time}__f2.8__SG23U{extension}"


def test_a_placeholder_folder_takes_the_to_split_convention(tmp_path):
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######", [
        _stamped("2026-07-15_(Wed)", "09.12.53"),
        _stamped("2026-07-15_(Wed)", "11.04.02"),
        _stamped("2026-07-15_(Wed)", "14.22.10"),
    ])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=3)").is_dir()


def test_the_name_takes_the_earliest_time_not_the_first_listed(tmp_path):
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-03_(Fri) - 1. ######", [
        _stamped("2026-07-03_(Fri)", "23.59.59"),
        _stamped("2026-07-03_(Fri)", "06.01.02"),
        _stamped("2026-07-03_(Fri)", "12.00.00"),
    ])

    tool.main([str(year), "--apply", "--no-colour"])

    assert (year / "2026-07-03_(Fri)__06.01.02 - __TO_SPLIT__(i=3)").is_dir()


def test_images_and_videos_are_counted_separately(tmp_path):
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######", [
        _stamped("2026-07-15_(Wed)", "09.12.53"),
        _stamped("2026-07-15_(Wed)", "10.00.00", ".crw"),
        _stamped("2026-07-15_(Wed)", "11.00.00", ".mp4"),
    ])

    tool.main([str(year), "--apply", "--no-colour"])

    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=2_v=1)").is_dir()


def test_top_level_media_wins_over_nested(tmp_path):
    # The count states what the grouper GUI will show, and it shows the top
    # level only -- sidecars and EXIF subfolders must not inflate it.
    year = tmp_path / "2026"
    folder = _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######", [
        _stamped("2026-07-15_(Wed)", "09.12.53"),
        "notes.txt",
    ])
    nested = folder / "##   EXIFs   ##"
    nested.mkdir()
    (nested / _stamped("2026-07-15_(Wed)", "05.00.00")).write_text("x", encoding="utf-8")

    tool.main([str(year), "--apply", "--no-colour"])

    # i=1: the nested image is not counted, because the grouper will not show
    # it. s=1/e=1: it is still reported, for exactly the same reason.
    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=1_e=1_s=1)").is_dir()


def test_a_video_only_day_is_counted_from_its_subfolders(tmp_path):
    # Every file routed into __VIDEOS/, sidecars into __EXIF/, nothing at the
    # top level. These are real days and must not be treated as empty.
    year = tmp_path / "2026"
    folder = _placeholder_folder(year, "2026-06-08_(Mon) - 1. ######", [])
    videos = folder / "__VIDEOS"
    videos.mkdir()
    exif = folder / "__EXIF"
    exif.mkdir()
    for time in ("21.21.43", "22.30.00"):
        (videos / _stamped("2026-06-08_(Mon)", time, ".mp4")).write_text("x", encoding="utf-8")
        (exif / (_stamped("2026-06-08_(Mon)", time, ".mp4") + "._exif")).write_text(
            "x", encoding="utf-8")

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    # s=2: the videos counted by v=2 are the very files the GUI cannot show.
    assert (year / "2026-06-08_(Mon)__21.21.43 - __TO_SPLIT__(v=2_s=2)").is_dir()


def test_a_completely_empty_day_folder_still_gets_the_marker(tmp_path):
    # No media anywhere, so no counts and no time to take -- but the legacy
    # placeholder still goes.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-06-09_(Tue) - 1. ######", [])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-06-09_(Tue) - __TO_SPLIT__").is_dir()


def test_an_existing_marked_folder_is_recounted_from_what_is_on_disk(tmp_path):
    # The stale count is the reason to run this tool: 111 images were named,
    # 2 are there. The name has to say what the folder holds now.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-18_(Sat) - __TO_SPLIT__(i=111)", [
        _stamped("2026-07-18_(Sat)", "11.04.02"),
        _stamped("2026-07-18_(Sat)", "08.15.00"),
    ])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-18_(Sat)__08.15.00 - __TO_SPLIT__(i=2)").is_dir()


def test_a_marked_folder_whose_name_is_already_right_is_untouched(tmp_path):
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-18_(Sat)__08.15.00 - __TO_SPLIT__(i=2)", [
        _stamped("2026-07-18_(Sat)", "08.15.00"),
        _stamped("2026-07-18_(Sat)", "09.00.00"),
    ])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-18_(Sat)__08.15.00 - __TO_SPLIT__(i=2)").is_dir()


def test_text_written_after_the_marker_survives_the_recount(tmp_path):
    # Rebuilding the counts rewrites the whole tail. A tail somebody has
    # written in is therefore left alone, and the folder only gains its time.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-18_(Sat) - __TO_SPLIT__(i=111) ask Ana", [
        _stamped("2026-07-18_(Sat)", "08.15.00"),
    ])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-18_(Sat)__08.15.00 - __TO_SPLIT__(i=111) ask Ana").is_dir()


def test_two_marked_folders_on_one_day_stop_colliding(tmp_path):
    # The whole point of the time: same day, same marker, different events.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-24_(Fri) - __TO_SPLIT__(i=6)",
                        [_stamped("2026-07-24_(Fri)", "09.12.53")])
    _placeholder_folder(year, "2026-07-24_(Fri) - __TO_SPLIT__(i=79)",
                        [_stamped("2026-07-24_(Fri)", "18.34.56")])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-24_(Fri)__09.12.53 - __TO_SPLIT__(i=1)").is_dir()
    assert (year / "2026-07-24_(Fri)__18.34.56 - __TO_SPLIT__(i=1)").is_dir()


def test_the_folder_date_survives_a_file_past_the_day_boundary(tmp_path):
    # Folder-sorting puts a 00:49 shot in the previous day's folder. Taking the
    # date from the file would undo that and move the day to another month.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-05-31_(Sun) - 1. ######",
                        [_stamped("2026-06-01_(Mon)", "00.49.28")])

    tool.main([str(year), "--apply", "--no-colour"])

    assert (year / "2026-05-31_(Sun)__00.49.28 - __TO_SPLIT__(i=1)").is_dir()


def test_a_labelled_folder_is_never_touched(tmp_path):
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-24_(Fri)__18.34.56 - Lens tests",
                        [_stamped("2026-07-24_(Fri)", "18.34.56")])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-24_(Fri)__18.34.56 - Lens tests").is_dir()


def test_the_timestamp_and_the_placeholder_are_fixed_in_one_pass(tmp_path):
    # An old day folder needs both halves: the weekday added and the
    # placeholder converted.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2014-05-08 - 1. ######", [
        "2014-05-08_(Thu)_07.30.00__f2.8.jpg",       # also a legacy stamp
        _stamped("2014-05-08_(Thu)", "09.00.00", ".mp4"),
    ])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2014-05-08_(Thu)__07.30.00 - __TO_SPLIT__(i=1_v=1)").is_dir()


def test_skip_placeholders_rewrites_timestamps_only(tmp_path):
    year = tmp_path / "2026"
    _placeholder_folder(year, "2014-05-08 - 1. ######",
                        [_stamped("2014-05-08_(Thu)", "09.00.00")])

    tool.main([str(year), "--apply", "--skip-placeholders", "--no-colour"])

    assert (year / "2014-05-08_(Thu) - 1. ######").is_dir()


def test_an_emptied_folder_keeps_the_count_of_what_it_held(tmp_path):
    # "__EMPTY_SUBFOLDERS" parks day folders whose files have all moved on.
    # The count is the last thing they say about themselves, and four of them
    # can share a date -- blanking it would erase that and collide the names.
    year = tmp_path / "2026"
    archive = year / "__EMPTY_SUBFOLDERS"
    for count in ("12", "184", "198"):
        _placeholder_folder(archive, "2026-08-19_(Wed) - __TO_SPLIT__(i=%s)" % count, [])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    for count in ("12", "184", "198"):
        assert (archive / ("2026-08-19_(Wed) - __TO_SPLIT__(i=%s)" % count)).is_dir()


def test_a_folder_the_pipeline_left_in_order_carries_no_audit_markers(tmp_path):
    # One sidecar per image, nothing below the top level: nothing to report,
    # so the name stays as short as it has always been.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######", [
        _stamped("2026-07-15_(Wed)", "09.12.53"),
        _stamped("2026-07-15_(Wed)", "10.00.00"),
    ])

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=2)").is_dir()


def test_files_hidden_in_subfolders_are_reported(tmp_path):
    # The day the marker is for: 2 images to review, and 3 videos the GUI will
    # never put in front of anyone because they were routed into __VIDEOS.
    year = tmp_path / "2026"
    files = [_stamped("2026-07-15_(Wed)", "09.12.53"),
             _stamped("2026-07-15_(Wed)", "10.00.00")]
    folder = _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######", files)
    videos = folder / "__VIDEOS"
    videos.mkdir()
    for time in ("11.00.00", "12.00.00", "13.00.00"):
        name = _stamped("2026-07-15_(Wed)", time, ".mp4")
        (videos / name).write_text("x", encoding="utf-8")
        (folder / "__EXIF" / (name + "._exif")).write_text("x", encoding="utf-8")

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    # i=2 still states the review job; s=3 states what is not part of it.
    # e= stays quiet: all five media files do have their sidecar.
    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=2_s=3)").is_dir()


def _emptied_folder(root, name, times):
    """A day whose images have gone, leaving only their "._exif" files."""
    folder = _placeholder_folder(root, name, [])
    exif = folder / "__EXIF"
    exif.mkdir()
    for time in times:
        (exif / (_stamped("2026-07-25_(Sat)", time) + "._exif")).write_text(
            "x", encoding="utf-8")
    return folder


def test_sidecars_left_behind_by_their_images_are_reported(tmp_path):
    # The grouper moved the day's photos out; the __EXIF folder stayed put.
    year = tmp_path / "2026"
    _emptied_folder(year, "2026-07-25_(Sat) - __TO_SPLIT__(i=7)",
                    ("06.19.06", "15.26.28", "18.01.39"))

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-25_(Sat)__06.19.06 - __TO_SPLIT__(e=3)").is_dir()


def test_a_folder_with_no_media_is_dated_from_its_earliest_sidecar(tmp_path):
    # A sidecar is named after the image it described, so it carries that
    # image's capture time. Without reading it these two would both come out
    # as a bare "2026-07-25_(Sat) - __TO_SPLIT__" and collide on one name.
    year = tmp_path / "2026"
    _emptied_folder(year, "2026-07-25_(Sat) - __TO_SPLIT__(i=2)",
                    ("06.19.06", "07.00.00"))
    _emptied_folder(year, "2026-07-25_(Sat) - __TO_SPLIT__(i=3)",
                    ("18.01.39", "19.00.00", "20.00.00"))

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-25_(Sat)__06.19.06 - __TO_SPLIT__(e=2)").is_dir()
    assert (year / "2026-07-25_(Sat)__18.01.39 - __TO_SPLIT__(e=3)").is_dir()


def test_media_still_outranks_a_sidecar_when_dating_a_folder(tmp_path):
    # The sidecars are only a fallback: an image at the top level dates the
    # folder even when a sidecar in __EXIF carries an earlier stamp.
    year = tmp_path / "2026"
    folder = _placeholder_folder(year, "2026-07-25_(Sat) - 1. ######",
                                 [_stamped("2026-07-25_(Sat)", "09.30.00")])
    (folder / "__EXIF" / (_stamped("2026-07-25_(Sat)", "04.00.00") + "._exif")).write_text(
        "x", encoding="utf-8")

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-25_(Sat)__09.30.00 - __TO_SPLIT__(i=1_e=2)").is_dir()


def test_images_that_lost_every_sidecar_are_reported_as_zero(tmp_path):
    # "e=0" beside a folder full of images is the point of reporting zero.
    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######", [
        _stamped("2026-07-15_(Wed)", "09.12.53"),
        _stamped("2026-07-15_(Wed)", "10.00.00"),
    ], sidecars=False)

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=2_e=0)").is_dir()


def test_an_archive_that_keeps_no_sidecars_never_reports_them(tmp_path, monkeypatch):
    config = json.loads(json.dumps(CONFIG))
    config["extensions"]["sidecars"] = []
    monkeypatch.setattr(tool, "_config", lambda: config)

    year = tmp_path / "2026"
    _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######",
                        [_stamped("2026-07-15_(Wed)", "09.12.53")], sidecars=False)

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    assert (year / "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=1)").is_dir()


def test_the_audit_markers_settle_after_one_pass(tmp_path):
    # The markers are part of the name, so a second run must read them back
    # and agree -- otherwise the tool would rename the same folder forever.
    year = tmp_path / "2026"
    folder = _placeholder_folder(year, "2026-07-15_(Wed) - 1. ######",
                                 [_stamped("2026-07-15_(Wed)", "09.12.53")],
                                 sidecars=False)
    videos = folder / "__VIDEOS"
    videos.mkdir()
    (videos / _stamped("2026-07-15_(Wed)", "11.00.00", ".mp4")).write_text(
        "x", encoding="utf-8")

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0
    settled = "2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=1_e=0_s=1)"
    assert (year / settled).is_dir()

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0
    assert (year / settled).is_dir()


def test_the_tool_and_the_grouping_stage_build_the_same_name(tmp_path):
    """The tool must not drift from the stage it is standing in for."""
    from src.pipeline_stages.grouping_names import to_split_name

    settings = tool.GroupingSettings(CONFIG)
    for files, images, videos in (
        (["a.jpg", "b.jpg"], 2, 0),
        (["a.mp4"], 0, 1),
        (["a.jpg", "b.mp4"], 1, 1),
    ):
        # Unstamped names, so no time is added and the two must agree exactly.
        folder = _placeholder_folder(tmp_path / str(len(files) + images * 10),
                                     "2026-07-15_(Wed) - 1. ######", files)
        assert tool.canonical_placeholder_name(
            folder, folder.name, [folder / name for name in files], settings) == \
            to_split_name("2026-07-15_(Wed)", images, videos)


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------

def _tree(root):
    """A year folder holding one old-style day folder and its files."""
    day = root / "2026-08-25_(Fri)"          # wrong weekday: really a Tuesday
    day.mkdir(parents=True)
    (day / "2026-08-25_(Tue)_10.23.12__f2.8.JPG").write_text("a", encoding="utf-8")
    (day / "2026-08-25__10.24.00__RAW.CRW").write_text("b", encoding="utf-8")
    (day / "read me.txt").write_text("c", encoding="utf-8")
    return day


def test_a_dry_run_changes_nothing_and_reports_work_pending(tmp_path, capsys):
    year = tmp_path / "2026"
    day = _tree(year)
    before = sorted(path.name for path in year.rglob("*"))

    exit_code = tool.main([str(year), "--no-colour"])

    assert exit_code == 1                     # pending changes
    assert sorted(path.name for path in year.rglob("*")) == before
    assert day.is_dir()
    assert "Re-run with --apply" in capsys.readouterr().out


def test_a_rename_prints_its_two_paths_in_one_column(tmp_path, capsys):
    # The report is read by running an eye down it, so the old and the new
    # path have to start at the same character.
    year = tmp_path / "2026"
    _tree(year)

    tool.main([str(year), "--no-colour"])

    pairs = [line for line in capsys.readouterr().out.splitlines()
             if line.startswith((tool.RENAME_FROM_PREFIX, tool.RENAME_TO_PREFIX))]
    assert pairs
    assert len(tool.RENAME_FROM_PREFIX) == len(tool.RENAME_TO_PREFIX)
    column = len(tool.RENAME_FROM_PREFIX)
    assert all(not line[column].isspace() for line in pairs)


def test_a_rename_is_coloured_only_where_the_two_names_part():
    source = r"c:\photos\2026-07-01_(Wed) - __TO_SPLIT__(i=129)"
    target = r"c:\photos\2026-07-01_(Wed) - __TO_SPLIT__(i=129_s=6)"

    was, now, _rule = tool.rename_report(
        source, target, tool.CHANGED, "", True).split("\n")

    shared = r"c:\photos\2026-07-01_(Wed) - __TO_SPLIT__(i=129"
    off = tool.COLOURS["off"]
    # Everything the two share keeps the outcome's own colour ...
    assert tool.COLOURS[tool.CHANGED] + shared + off in was
    assert tool.COLOURS[tool.CHANGED] + shared + off in now
    # ... and only past that point do they differ: white going, red coming.
    assert was.endswith(tool.COLOURS["old"] + ")" + off)
    assert now.endswith(tool.COLOURS["new"] + "_s=6)" + off)


def test_the_report_carries_no_escape_codes_when_colour_is_off():
    plain = tool.rename_report("a/one.jpg", "a/two.jpg", tool.CHANGED, "note", False)

    assert "\033" not in plain
    assert plain.split("\n") == [
        tool.RENAME_FROM_PREFIX + "a/one.jpg",
        tool.RENAME_TO_PREFIX + "a/two.jpg" + "  note",
        tool.RENAME_FROM_PREFIX + tool.RENAME_RULE_CHAR * tool.RENAME_RULE_WIDTH,
    ]


def test_a_rule_closes_each_pair_at_one_width_and_barely_shows():
    # Same width every time: a ragged right edge down the report would read as
    # content, and the rule is meant to read as nothing.
    short = tool.rename_report("a/one.jpg", "a/two.jpg", tool.CHANGED, "", True)
    deep = tool.rename_report("a/" + "down/" * 20 + "one.jpg",
                              "a/" + "down/" * 20 + "two.jpg", tool.CHANGED, "", True)

    rules = [report.split("\n")[-1] for report in (short, deep)]
    assert rules[0] == rules[1]
    assert rules[0] == (tool.RENAME_FROM_PREFIX
                        + tool.COLOURS["rule"]
                        + tool.RENAME_RULE_CHAR * tool.RENAME_RULE_WIDTH
                        + tool.COLOURS["off"])
    assert tool.COLOURS["rule"] == "\033[2;90m"        # faint *and* grey


def test_apply_renames_folder_and_files_and_leaves_the_rest_alone(tmp_path):
    year = tmp_path / "2026"
    _tree(year)

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    day = year / "2026-08-25_(Tue)"
    assert day.is_dir()
    assert (day / "2026-08-25_(Tue)__10.23.12__f2.8.JPG").read_text(encoding="utf-8") == "a"
    assert (day / "2026-08-25_(Tue)__10.24.00__RAW.CRW").read_text(encoding="utf-8") == "b"
    assert (day / "read me.txt").read_text(encoding="utf-8") == "c"


def test_a_second_run_finds_nothing_left_to_do(tmp_path):
    year = tmp_path / "2026"
    _tree(year)
    tool.main([str(year), "--apply", "--no-colour"])

    assert tool.main([str(year), "--no-colour"]) == 0


def test_the_journal_replays_backwards_and_restores_every_name(tmp_path):
    year = tmp_path / "2026"
    _tree(year)
    before = sorted(str(path.relative_to(year)) for path in year.rglob("*"))
    journal = tmp_path / "journal.jsonl"

    tool.main([str(year), "--apply", "--journal", str(journal), "--no-colour"])
    assert sorted(str(path.relative_to(year)) for path in year.rglob("*")) != before

    assert tool.main(["--undo", str(journal), "--apply", "--no-colour"]) == 0
    assert sorted(str(path.relative_to(year)) for path in year.rglob("*")) == before


def test_the_journal_records_one_line_per_rename(tmp_path):
    year = tmp_path / "2026"
    _tree(year)
    journal = tmp_path / "journal.jsonl"

    tool.main([str(year), "--apply", "--journal", str(journal), "--no-colour"])

    records = [json.loads(line) for line in
               journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 3          # two files and the day folder
    assert all("from" in record and "to" in record for record in records)


def test_the_journal_is_not_itself_a_rename_candidate(tmp_path):
    # The default journal lives inside the target and is dated, so the walk
    # would find it, try to rename it, and fail: it is still open.
    year = tmp_path / "2026"
    _tree(year)

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    journals = list(year.glob("_rename_journal_*.jsonl"))
    assert len(journals) == 1
    assert tool.canonical_name(journals[0].name) == journals[0].name


def test_a_name_collision_leaves_both_files_untouched(tmp_path):
    year = tmp_path / "2026"
    year.mkdir()
    # Two historical shapes of the same instant: renaming one onto the other
    # would destroy a photo, so neither moves.
    (year / "2026-08-25_(Tue)_10.23.12.JPG").write_text("old", encoding="utf-8")
    (year / "2026-08-25_(Tue)__10.23.12.JPG").write_text("new", encoding="utf-8")

    assert tool.main([str(year), "--apply", "--no-colour"]) == 1
    assert (year / "2026-08-25_(Tue)_10.23.12.JPG").read_text(encoding="utf-8") == "old"
    assert (year / "2026-08-25_(Tue)__10.23.12.JPG").read_text(encoding="utf-8") == "new"


def test_the_target_root_itself_is_never_renamed(tmp_path):
    # The root is addressed by the caller; renaming it would strand the run.
    year = tmp_path / "2026-08-25__10.23.12"
    year.mkdir()
    (year / "2026-08-25__10.24.00.JPG").write_text("a", encoding="utf-8")

    tool.main([str(year), "--apply", "--no-colour"])

    assert year.is_dir()


def test_deeply_nested_folders_are_renamed_deepest_first(tmp_path):
    year = tmp_path / "2026"
    inner = year / "2026-08-25__00.00.00" / "2026-08-26__00.00.00"
    inner.mkdir(parents=True)
    (inner / "2026-08-26__12.00.00.JPG").write_text("a", encoding="utf-8")

    assert tool.main([str(year), "--apply", "--no-colour"]) == 0

    moved = year / "2026-08-25_(Tue)__00.00.00" / "2026-08-26_(Wed)__00.00.00"
    assert (moved / "2026-08-26_(Wed)__12.00.00.JPG").read_text(encoding="utf-8") == "a"


# --------------------------------------------------------------------------
# Year warning and target guards
# --------------------------------------------------------------------------

def test_a_year_folder_that_is_not_the_current_year_warns(tmp_path, capsys):
    year = tmp_path / "2019"
    year.mkdir()

    tool.main([str(year), "--no-colour"])

    assert "not the current year" in capsys.readouterr().out


def test_the_current_year_does_not_warn(tmp_path, capsys):
    import datetime
    year = tmp_path / str(datetime.date.today().year)
    year.mkdir()

    tool.main([str(year), "--no-colour"])

    assert "not the current year" not in capsys.readouterr().out


def test_a_target_that_is_not_a_year_folder_warns_but_proceeds(tmp_path, capsys):
    target = tmp_path / "loose photos"
    target.mkdir()

    assert tool.main([str(target), "--no-colour"]) == 0
    assert "not a year folder" in capsys.readouterr().out


def test_a_missing_target_is_an_error_not_an_empty_run(tmp_path):
    assert tool.main([str(tmp_path / "nope"), "--no-colour"]) == 2


def test_the_walk_refuses_a_path_outside_the_root():
    root_key = tool.path_key(r"c:\__PHOTOS\2026")
    assert tool.inside(root_key, r"c:\__PHOTOS\2026\2026-08-25_(Tue)")
    assert not tool.inside(root_key, r"c:\__PHOTOS\2025")
    assert not tool.inside(root_key, r"c:\__PHOTOS\20260")
