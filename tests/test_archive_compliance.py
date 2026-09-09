"""Steps 7/8 only ever operate on explicit disposable archive roots here."""

import json
import types

import pytest

# Load the application normally before the standalone tool installs optional
# dependency-free package stubs. Other test modules exercise the real package.
import src.pipeline_stages

from test_restructure_archive import tool, config, fake_grouper, make_archive, run


def write(path, content=b"photo"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def group_fixture(tmp_path):
    root = make_archive(tmp_path)
    group = root / "2026" / "07. July" / "2026-07-15_(Wed)__08.00.00 - Trip"
    child = group / "2026-07-15_(Wed)__08.00.00 - Breakfast"
    write(child / "2026-07-15_(Wed)__08.00.00.jpg")
    return root, group


def snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_report_detects_structure_without_writing_or_scanning_working_areas(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    write(root / "2026" / "loose.txt")
    write(root / "2026" / "07. July" / "unknown" / "nested" / "file.jpg")
    write(root / "2026" / "__DUPLICATES" / "ignored" / "bad.jpg")
    write(root / "__PROCESSED" / "ignored" / "bad.jpg")
    before = snapshot(root)
    assert run(str(root), "--steps", "7") == 1
    assert snapshot(root) == before
    output = capsys.readouterr().out
    assert "P6" in output and "P4" in output and "S2" in output
    assert "ignored" not in output


def test_c4_dry_run_lists_exact_destinations(tmp_path, config, capsys):
    root, group = group_fixture(tmp_path)
    shot = write(group / "2026-07-15_(Wed)__12.00.00.jpg")
    before = snapshot(root)
    assert run(str(root), "--steps", "8") == 1
    assert snapshot(root) == before
    output = capsys.readouterr().out
    assert "C4" in output and shot.name in output
    assert "2026-07-15_(Wed)__12.00.00 - __TO_LABEL__" in output


def test_c4_apply_moves_taxonomy_and_ocr_intact_and_is_idempotent(tmp_path, config):
    root, group = group_fixture(tmp_path)
    name = "2026-07-15_(Wed)__12.00.00.jpg"
    write(group / name)
    write(group / "__EXIF" / (name + "._exif"), b"metadata")
    write(group / "__OCR" / (name + ".OCR.txt"), b"recognised text")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    children = list(root.rglob("* - __TO_LABEL__"))
    assert len(children) == 1
    child = children[0]
    assert (child / name).read_bytes() == b"photo"
    assert (child / "__EXIF" / (name + "._exif")).read_bytes() == b"metadata"
    assert (child / "__OCR" / (name + ".OCR.txt")).read_bytes() == b"recognised text"
    assert run(str(root), "--steps", "7") == 0
    before = snapshot(root / "2026")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert snapshot(root / "2026") == before
    records = [json.loads(line) for path in (root / "__LOGS").glob("*.jsonl") for line in path.read_text(encoding="utf-8").splitlines()]
    assert any(record["event"] == "standard_move" and record["rule"] == "C4" for record in records)
    assert any(record["event"] == "group_rename" for record in records)


def test_c4_refusal_preserves_media(tmp_path, config, monkeypatch):
    root, group = group_fixture(tmp_path)
    name = "2026-07-15_(Wed)__12.00.00.jpg"
    write(group / name)
    prompts = []
    monkeypatch.setattr(tool.Run, "confirm", lambda self, message: prompts.append(message) or False)
    assert run(str(root), "--steps", "8", "--apply") == 1
    assert len(prompts) == 1
    assert len(list(root.rglob(name))) == 1
    assert not list(root.rglob("* - __TO_LABEL__"))


def test_c4_inclusive_boundary_creates_previous_day_child(tmp_path, config):
    root, group = group_fixture(tmp_path)
    write(group / "2026-07-16_(Thu)__04.44.44.jpg")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert list(root.rglob("2026-07-15_(Wed)__04.44.44 - __TO_LABEL__"))


def test_c4_undatable_media_never_uses_file_times(tmp_path, config):
    root, group = group_fixture(tmp_path)
    write(group / "unknown.mp4")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    assert list(root.rglob("unknown.mp4"))
    assert not list(root.rglob("* - __TO_LABEL__"))


def test_c4_collision_never_merges_or_overwrites(tmp_path, config):
    root, group = group_fixture(tmp_path)
    name = "2026-07-15_(Wed)__12.00.00.jpg"
    write(group / name, b"loose")
    write(group / "2026-07-15_(Wed)__12.00.00 - __TO_LABEL__" / name, b"existing")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    assert {path.read_bytes() for path in root.rglob(name)} == {b"loose", b"existing"}


def test_c12_moves_group_to_month_of_stated_start(tmp_path, config):
    root, group = group_fixture(tmp_path)
    wrong = root / "2026" / "08. August" / group.name
    wrong.parent.mkdir()
    group.rename(wrong)
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert not wrong.exists()
    # No glob for the name: "[" is a character class to fnmatch, and a
    # group's description sits in brackets.
    assert [path.name for path in (root / "2026" / "07. July").iterdir()
            if "__GROUP[ Trip ]" in path.name]
    assert run(str(root), "--steps", "7") == 0


def test_invalid_dates_report_instead_of_crashing_or_being_invented(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    write(root / "2026" / "07. July" / "2026-02-31_(Mon)__12.00.00 - Bad" / "photo.jpg")
    assert run(str(root), "--steps", "7") == 1
    assert "N6" in capsys.readouterr().out


def test_group_geodata_excluded_from_span_but_contents_are_checked(tmp_path, config, capsys):
    root, group = group_fixture(tmp_path)
    write(group / "__GEOLOCATIONS" / "1999-01-01_(Fri)__00.00.00.gpx")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert not list(root.rglob("*#1999*"))
    track_dir = next(root.rglob("__GEOLOCATIONS"))
    write(track_dir / "not-geodata.jpg")
    assert run(str(root), "--steps", "7") == 1
    assert "C3a" in capsys.readouterr().out


def test_nested_ocr_legal_but_deeper_nesting_is_not(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day"
    name = "2026-07-15_(Wed)__12.00.00.jpg"
    write(event / "__EDITED" / name)
    write(event / "__EDITED" / "__OCR" / (name + ".OCR.txt"))
    assert run(str(root), "--steps", "7") == 0
    write(event / "__EDITED" / "__OCR" / "__OCR" / "bad.txt")
    assert run(str(root), "--steps", "7") == 1
    assert "S2" in capsys.readouterr().out


def test_unkeyed_edited_derivative_is_permitted(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    write(root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day" / "__EDITED" / "untitled.jpg")
    assert run(str(root), "--steps", "7") == 0
    assert "D5 unkeyed" in capsys.readouterr().out


def test_video_resolution_moves_companions_and_clears_waiting_count(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - __TO_SPLIT__(w=2)"
    decisions = {}
    for index in range(2):
        video = write(event / "__VIDEOS_TO_RENAME" / ("__TO_RENAME__clip%d.mp4" % index))
        write(video.parent / "__EXIF" / (video.name + "._exif"), b"exif")
        write(video.parent / "__PREVIEWS" / (video.name + ".lrv"), b"preview")
        decisions[video.relative_to(root).as_posix()] = "2026-07-15T12:00:0%d" % index
    times = tmp_path / "times.json"
    times.write_text(json.dumps(decisions), encoding="utf-8")
    before = snapshot(root)
    assert run(str(root), "--steps", "8", "--video-times", str(times)) == 1
    assert snapshot(root) == before
    assert run(str(root), "--steps", "8", "--apply", "--yes", "--video-times", str(times)) == 0
    videos = list(root.rglob("*.mp4"))
    assert len(videos) == 2
    for video in videos:
        assert not video.name.startswith("__TO_RENAME__")
        assert video.parent.name.endswith("__TO_SPLIT__(v=2_s=2)")
        assert (video.parent / "__EXIF" / (video.name + "._exif")).read_bytes() == b"exif"
        assert (video.parent / "__PREVIEWS" / (video.name + ".lrv")).read_bytes() == b"preview"
    assert run(str(root), "--steps", "7") == 0


def test_canonicaliser_writes_and_preserves_w_count(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - __TO_SPLIT__(w=1)"
    write(event / "__VIDEOS_TO_RENAME" / "__TO_RENAME__clip.mp4")
    assert run(str(root), "--steps", "1", "--apply", "--yes") == 0
    names = [path.name for path in (root / "2026" / "07. July").iterdir()]
    assert len(names) == 1 and "w=1" in names[0]


def test_video_time_outside_event_is_rejected_without_mutation(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day"
    video = write(event / "__VIDEOS_TO_RENAME" / "__TO_RENAME__clip.mp4")
    times = tmp_path / "times.json"
    times.write_text(json.dumps({video.relative_to(root).as_posix(): "2026-07-20T12:00:00"}), encoding="utf-8")
    before = snapshot(root / "2026")
    assert run(str(root), "--steps", "8", "--apply", "--yes", "--video-times", str(times)) == 1
    assert snapshot(root / "2026") == before


def test_c4_multiday_taxonomy_distributes_companions_without_deleting_shells(tmp_path, config):
    root, group = group_fixture(tmp_path)
    for day in (15, 16):
        name = "2026-07-%d__12.00.00.jpg" % day
        write(group / name, str(day).encode())
        write(group / "__EXIF" / (name + "._exif"), str(day).encode())
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    for day in (15, 16):
        photo = next(root.rglob("2026-07-%d__12.00.00.jpg" % day))
        assert (photo.parent / "__EXIF" / (photo.name + "._exif")).read_bytes() == str(day).encode()


def test_failed_c4_move_rolls_files_back(tmp_path, config, monkeypatch):
    root, group = group_fixture(tmp_path)
    write(group / "2026-07-15_(Wed)__12.00.00.jpg", b"one")
    write(group / "2026-07-15_(Wed)__13.00.00.jpg", b"two")
    original = tool.canonicalise.rename_path
    def fail_second(source, target, *args):
        if source.name.endswith("13.00.00.jpg"):
            raise OSError("simulated disconnected share")
        return original(source, target, *args)
    monkeypatch.setattr(tool.canonicalise, "rename_path", fail_second)
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    for hour, content in ((12, b"one"), (13, b"two")):
        file = next(root.rglob("*__%d.00.00.jpg" % hour))
        assert file.read_bytes() == content
        assert not file.parent.name.endswith("__TO_LABEL__")


def test_reparse_refusal_blocks_whole_group_migration(tmp_path, config, monkeypatch, capsys):
    root, group = group_fixture(tmp_path)
    write(group / "2026-07-15_(Wed)__12.00.00.jpg")
    blocked = group / "unreadable"
    blocked.mkdir()
    original = tool.canonicalise.is_reparse_point
    monkeypatch.setattr(tool.canonicalise, "is_reparse_point", lambda entry: entry.name == blocked.name or original(entry))
    before = snapshot(root / "2026")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    assert snapshot(root / "2026") == before
    assert "T4" in capsys.readouterr().out


def test_c12_refusal_and_collision_preserve_both_trees(tmp_path, config, monkeypatch):
    root, group = group_fixture(tmp_path)
    wrong = root / "2026" / "08. August" / group.name
    wrong.parent.mkdir()
    group.rename(wrong)
    write(group / "preserve.txt", b"existing")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    assert (group / "preserve.txt").read_bytes() == b"existing"
    assert list((root / "2026" / "08. August").glob("*Trip*"))


def test_journal_failure_prevents_migration(tmp_path, config, monkeypatch):
    root, group = group_fixture(tmp_path)
    name = "2026-07-15_(Wed)__12.00.00.jpg"
    write(group / name)
    def refuse_journal(self, event, **fields):
        self.path = None
    monkeypatch.setattr(tool.Journal, "write", refuse_journal)
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    assert not next(root.rglob(name)).parent.name.endswith("__TO_LABEL__")


def test_c4_raw_and_its_sidecar_land_below_the_new_child(tmp_path, config):
    root, group = group_fixture(tmp_path)
    name = "2026-07-15_(Wed)__12.00.00__RAW__f8.CR2"
    write(group / name)
    write(group / "__EXIF" / (name + "._exif"), b"raw metadata")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    raw = next(root.rglob(name))
    assert raw.parent.name == "__RAW"
    assert (raw.parent / "__EXIF" / (raw.name + "._exif")).read_bytes() == b"raw metadata"


def test_check_then_successful_fix_returns_clean_status(tmp_path, config, capsys):
    root, group = group_fixture(tmp_path)
    write(group / "2026-07-15_(Wed)__12.00.00.jpg")
    assert run(str(root), "--steps", "7,8", "--apply", "--yes") == 0
    output = capsys.readouterr().out
    assert "ALL CLEAR" in output


def test_leaf_retime_preserves_human_tail_byte_for_byte(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__10.00.00 - 12. Keep this"
    write(event / "2026-07-15_(Wed)__12.00.00.jpg")
    assert run(str(root), "--steps", "7,8", "--apply", "--yes") == 0
    assert (event.parent / "2026-07-15_(Wed)__12.00.00 - 12. Keep this").is_dir()


def test_video_date_only_does_not_invent_midnight(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day"
    video = write(event / "__VIDEOS_TO_RENAME" / "__TO_RENAME__clip.mp4")
    times = tmp_path / "times.json"
    times.write_text(json.dumps({video.relative_to(root).as_posix(): "2026-07-16"}), encoding="utf-8")
    assert run(str(root), "--steps", "8", "--apply", "--yes", "--video-times", str(times)) == 1
    assert video.is_file()


# --------------------------------------------------------------------------
# F9 / PS-10 -- collision suffixes an earlier version wrote on sibling shots
# --------------------------------------------------------------------------

BASE = "2026-07-15_(Wed)__12.00.00__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
LOSER = ("2026-07-15_(Wed)__12.00.00__f2.4__T1_50__L69.0.eq__I100__SG23U"
         "_DUPE_57d0a98927ce997d1d9c80912bc3e776_0.jpg")


def exif_sidecar(subsecond):
    lines = ["Date/Time Original              : 2026:07:15 12:00:00"]
    if subsecond is not None:
        lines.append("Sub Sec Time Original           : " + subsecond)
    return ("\n".join(lines) + "\n").encode("iso-8859-1")


def sibling_fixture(tmp_path, kept_subsecond="633", loser_subsecond="433",
                    loser_bytes=b"a second exposure"):
    """A dated folder holding PS-10's own shape: a shot and a false duplicate."""
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Roldal"
    write(event / BASE, b"the first exposure")
    write(event / "__EXIF" / (BASE + "._exif"), exif_sidecar(kept_subsecond))
    write(event / LOSER, loser_bytes)
    write(event / "__EXIF" / (LOSER + "._exif"), exif_sidecar(loser_subsecond))
    return root, event


def many_sibling_pairs(root, count):
    """``count`` mismarked pairs spread over one year tree, four files each."""
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Roldal"
    for minute in range(count):
        stem = "2026-07-15_(Wed)__12.%02d.00__f2.4__T1_50__L69.0.eq__I100__SG23U" % minute
        kept, loser = stem + ".jpg", stem + "_DUPE_%032x_1.jpg" % minute
        write(event / kept, b"exposure one %d" % minute)
        write(event / "__EXIF" / (kept + "._exif"), exif_sidecar("633"))
        write(event / loser, b"exposure two %d" % minute)
        write(event / "__EXIF" / (loser + "._exif"), exif_sidecar("433"))
    return event


def test_f9_check_reports_a_collision_suffix_on_a_second_exposure(tmp_path, config, capsys):
    root, _ = sibling_fixture(tmp_path)
    before = snapshot(root)

    assert run(str(root), "--steps", "7") == 1

    assert snapshot(root) == before, "a check writes nothing (T2)"
    output = capsys.readouterr().out
    assert "F9" in output and LOSER in output


def test_f9_apply_renames_both_shots_to_their_own_sub_seconds(tmp_path, config):
    root, event = sibling_fixture(tmp_path)

    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0

    kept = event / "2026-07-15_(Wed)__12.00.00.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
    arrived = event / "2026-07-15_(Wed)__12.00.00.433__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
    # Both files move: the pair then sorts in the order it was shot.
    assert kept.read_bytes() == b"the first exposure"
    assert arrived.read_bytes() == b"a second exposure"
    assert not (event / BASE).exists() and not (event / LOSER).exists()
    # Every sidecar followed its subject, named per X1 and placed per X10.
    assert sorted(path.name for path in (event / "__EXIF").iterdir()) == \
        [arrived.name + "._exif", kept.name + "._exif"]
    # And the repair is a fixed point: nothing left to report or to redo.
    assert run(str(root), "--steps", "7") == 0


def test_f9_leaves_a_genuine_duplicate_marked(tmp_path, config, capsys):
    """Identical bytes: the suffix was telling the truth, so it stands."""
    root, event = sibling_fixture(tmp_path, kept_subsecond="633",
                                  loser_subsecond="633",
                                  loser_bytes=b"the first exposure")
    assert run(str(root), "--steps", "8", "--apply", "--yes") in (0, 1)

    assert (event / LOSER).exists()
    assert "F9" not in capsys.readouterr().out


def test_f9_refuses_to_guess_when_no_camera_recorded_a_fraction(tmp_path, config, capsys):
    """No sub-second anywhere: a burst and one shot saved twice look alike.

    V4's rule holds -- what cannot be known is left for a person, not invented.
    """
    root, event = sibling_fixture(tmp_path, kept_subsecond=None, loser_subsecond=None)
    assert run(str(root), "--steps", "8", "--apply", "--yes") in (0, 1)

    assert (event / LOSER).exists()
    assert "F9" not in capsys.readouterr().out


def test_f9_asks_once_for_the_whole_year_not_once_per_pair(tmp_path, config, monkeypatch):
    """A prompt met seventy times in a row is a prompt nobody reads.

    ``--year ALL`` is one Run per year, so one confirmation per run is one
    confirmation per year -- the same judgement the network prompt makes.
    """
    root = make_archive(tmp_path)
    event = many_sibling_pairs(root, 12)
    prompts = []
    monkeypatch.setattr(tool.Run, "confirm",
                        lambda self, message: prompts.append(message) or True)

    assert run(str(root), "--steps", "8", "--apply") == 0

    assert len(prompts) == 1, "one confirmation, whatever the pair count"
    assert "12 collision name(s)" in prompts[0]
    assert "F9" in prompts[0] and "12 x" in prompts[0], "the prompt says what kind"
    assert "48 file(s)" in prompts[0], "media and sidecars are both counted"
    assert str(root / "2026") in prompts[0], "the year being approved is named"
    assert "and 4 more" in prompts[0], "a long list is capped, not dumped"
    # All twelve pairs were actually renamed on that one answer.
    assert not list(event.glob("*_DUPE_*"))
    assert len(list(event.glob("*12.??.00.433__*.jpg"))) == 12
    assert len(list(event.glob("*12.??.00.633__*.jpg"))) == 12


def test_f9_refusing_the_single_prompt_leaves_every_pair_untouched(tmp_path, config, monkeypatch):
    root = make_archive(tmp_path)
    event = many_sibling_pairs(root, 3)
    # The year tree only: an applied run always writes its own journal into
    # __LOGS, which is bookkeeping and not a change to the archive (J2).
    before = snapshot(root / "2026")
    prompts = []
    monkeypatch.setattr(tool.Run, "confirm",
                        lambda self, message: prompts.append(message) or False)

    assert run(str(root), "--steps", "8", "--apply") == 1

    assert len(prompts) == 1
    assert snapshot(root / "2026") == before, "one no means none of them move"
    assert len(list(event.glob("*_DUPE_*"))) == 3


# --------------------------------------------------------------------------
# F10 -- _LOWRES is a claim about resolution, and only pixels can support it
# --------------------------------------------------------------------------

LOWRES = ("2026-07-15_(Wed)__12.00.00__f2.4__T1_50__L69.0.eq__I100__SG23U"
          "_LOWRES_179f5c34508c562bc978490bcb3047b4_1.jpg")


def sized_sidecar(width, height, subsecond="633"):
    """A sidecar shaped like ExifTool's, thumbnail IFD and all."""
    return ("\n".join([
        "---- File ----",
        "Image Width                     : %d" % width,
        "Image Height                    : %d" % height,
        "---- IFD0 ----",
        "Date/Time Original              : 2026:07:15 12:00:00",
        "Sub Sec Time Original           : " + subsecond,
        "---- IFD1 ----",
        "Image Width                     : 512",
        "Image Height                    : 384",
        "---- Composite ----",
        "Image Size                      : %dx%d" % (width, height),
    ]) + "\n").encode("iso-8859-1")


def low_res_fixture(tmp_path, kept=(4000, 3000), loser=(4000, 3000),
                    kept_subsecond="633", loser_subsecond="633"):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Allotment"
    write(event / BASE, b"the full-resolution shot")
    write(event / "__EXIF" / (BASE + "._exif"), sized_sidecar(*kept, kept_subsecond))
    write(event / LOWRES, b"a lighter file entirely")
    write(event / "__EXIF" / (LOWRES + "._exif"), sized_sidecar(*loser, loser_subsecond))
    return root, event


def test_f10_reports_lowres_on_a_file_of_the_same_dimensions(tmp_path, config, capsys):
    """The archive's own case: 4000x3000 both, one merely compressed better."""
    root, _ = low_res_fixture(tmp_path)
    before = snapshot(root)

    assert run(str(root), "--steps", "7") == 1

    assert snapshot(root) == before
    output = capsys.readouterr().out
    assert "F10" in output and LOWRES in output


def test_f10_renames_a_false_lowres_to_what_it_actually_is(tmp_path, config):
    """_DIFFERS: different bytes, one name, and resolution ruled out.

    The checksum and index survive the rename, so the pair can still be
    matched up by eye (F4).
    """
    root, event = low_res_fixture(tmp_path)

    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0

    repaired = event / LOWRES.replace("_LOWRES_", "_DIFFERS_")
    assert repaired.read_bytes() == b"a lighter file entirely"
    assert not (event / LOWRES).exists()
    assert (event / "__EXIF" / (repaired.name + "._exif")).is_file()
    assert (event / BASE).read_bytes() == b"the full-resolution shot"


def test_f10_leaves_a_genuine_downscale_marked_but_moves_it_to_resized(tmp_path, config):
    """Lower dimensions really are lower resolution -- and a derivative (F7)."""
    root, event = low_res_fixture(tmp_path, kept=(4000, 3000), loser=(1024, 768))

    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0

    moved = event / "__RESIZED" / LOWRES
    assert moved.read_bytes() == b"a lighter file entirely"
    assert not (event / LOWRES).exists(), "a downscale is not a representative"
    # X10: its sidecar goes to the __EXIF beside it, not the event folder's.
    assert (event / "__RESIZED" / "__EXIF" / (LOWRES + "._exif")).is_file()
    assert not (event / "__EXIF" / (LOWRES + "._exif")).exists()


def test_f10_prefers_the_sibling_reading_when_the_sub_seconds_differ(tmp_path, config):
    """Same dimensions AND two exposures: F9 wins, and both get their fraction."""
    root, event = low_res_fixture(tmp_path, kept_subsecond="925", loser_subsecond="325")

    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0

    stem = "2026-07-15_(Wed)__12.00.00.%s__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
    assert (event / (stem % "925")).read_bytes() == b"the full-resolution shot"
    assert (event / (stem % "325")).read_bytes() == b"a lighter file entirely"
    assert not list(event.glob("*_LOWRES_*")) and not list(event.glob("*_DIFFERS_*"))


# --------------------------------------------------------------------------
# S7 -- a collision loser is parked in its own dated folder
# --------------------------------------------------------------------------

def test_s7_parks_a_collision_loser_in_the_dated_folder_not_the_year(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Roldal"
    write(event / BASE, b"photo")
    # Two sidecars claiming one X1 name: the second must be parked (F4/L3).
    write(event / "__EXIF" / (BASE + "._exif"), b"the sidecar that keeps the name")
    write(event / (BASE + "._exif"), b"a different sidecar, same name")

    assert run(str(root), "--steps", "2", "--apply", "--yes") in (0, 1)

    parked = list(event.rglob("__DUPLICATES/*"))
    assert parked, "the loser is parked inside the dated folder it belongs to"
    assert not (root / "2026" / "__DUPLICATES").exists(), "not at the year level"


def test_s7_a_group_never_holds_the_parking_folder(tmp_path, config):
    """C3: a group holds no files, so the walk climbs past it to the leaf."""
    root = make_archive(tmp_path)
    group = (root / "2026" / "07. July"
             / "2026-07-15_(Wed)__08.00.00 __GROUP[ Roldal ] ___12.00.00_(n=2)")
    event = group / "2026-07-15_(Wed)__12.00.00 - Roldal"
    write(event / BASE, b"photo")

    # duplicates_folder needs only the run's trees to decide.
    run_stub = types.SimpleNamespace(trees=tool.scan_roots(root, lambda *a, **k: None))
    config = tool.canonicalise._config()

    assert tool.duplicates_folder(event, run_stub, config) == event / "__DUPLICATES"
    # A subject sitting directly in the group never parks in the group: the
    # walk climbs past it, and with no dated leaf below it falls back to the
    # year folder, which is where an archive written before S7 changed has one.
    assert tool.duplicates_folder(group, run_stub, config) == root / "2026" / "__DUPLICATES"


# --------------------------------------------------------------------------
# F9c -- a fraction that separates nothing comes off
# --------------------------------------------------------------------------

FRACTIONED = "2026-07-15_(Wed)__12.00.00.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"


def test_f9c_strips_a_sub_second_from_a_shot_with_no_sibling(tmp_path, config):
    """The fraction exists to separate two shots. Alone, it separates nothing."""
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Roldal"
    write(event / FRACTIONED, b"the only shot in that second")
    write(event / "__EXIF" / (FRACTIONED + "._exif"), sized_sidecar(4000, 3000, "633"))

    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0

    assert (event / BASE).read_bytes() == b"the only shot in that second"
    assert not (event / FRACTIONED).exists()
    assert (event / "__EXIF" / (BASE + "._exif")).is_file()
    assert run(str(root), "--steps", "7") == 0


def test_f9c_keeps_the_fraction_where_a_sibling_shares_the_second(tmp_path, config):
    """Two in the second: both fractions stay, and the scan is clean."""
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Roldal"
    other = FRACTIONED.replace(".633__", ".433__")
    write(event / FRACTIONED, b"one exposure")
    write(event / "__EXIF" / (FRACTIONED + "._exif"), sized_sidecar(4000, 3000, "633"))
    write(event / other, b"another exposure")
    write(event / "__EXIF" / (other + "._exif"), sized_sidecar(4000, 3000, "433"))
    before = snapshot(root / "2026")

    assert run(str(root), "--steps", "7") == 0, "a settled sibling pair is compliant"
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert snapshot(root / "2026") == before, "nothing to change"


# --------------------------------------------------------------------------
# PS-11: a leaf under the wrong month, an orphan with nowhere to point, and
# a __LOGS that is not where journals go
# --------------------------------------------------------------------------

def misplaced_leaf(tmp_path, month="08. August"):
    """One dated leaf whose own name disagrees with the month holding it (P5)."""
    root = make_archive(tmp_path)
    event = root / "2026" / month / "2026-07-15_(Wed)__08.00.00 - Flowers"
    write(event / "2026-07-15_(Wed)__08.00.00.jpg")
    return root, event


def test_p5_dry_run_names_the_destination_and_writes_nothing(tmp_path, config, capsys):
    root, event = misplaced_leaf(tmp_path)
    before = snapshot(root)
    assert run(str(root), "--steps", "8") == 1
    assert snapshot(root) == before
    output = capsys.readouterr().out
    assert "P5" in output and "07. July" in output


def test_p5_moves_a_leaf_to_the_month_its_own_name_states(tmp_path, config):
    root, event = misplaced_leaf(tmp_path)
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert not event.exists()
    moved = root / "2026" / "07. July" / event.name
    assert (moved / "2026-07-15_(Wed)__08.00.00.jpg").is_file()
    assert run(str(root), "--steps", "7") == 0


def test_p5_crossing_a_year_creates_the_tree_and_keeps_checking_it(tmp_path, config):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2025-07-15_(Tue)__08.00.00 - Last year"
    write(event / "2025-07-15_(Tue)__08.00.00.jpg")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert (root / "2025" / "07. July" / event.name
            / "2025-07-15_(Tue)__08.00.00.jpg").is_file()
    assert run(str(root), "--steps", "7") == 0


def test_p5_asks_once_for_the_whole_run_and_a_refusal_moves_nothing(tmp_path, config,
                                                                    monkeypatch):
    root, first = misplaced_leaf(tmp_path)
    second = root / "2026" / "08. August" / "2026-07-16_(Thu)__09.00.00 - Also July"
    write(second / "2026-07-16_(Thu)__09.00.00.jpg")
    prompts = []
    monkeypatch.setattr(tool.Run, "confirm", lambda self, message: prompts.append(message) or False)
    assert run(str(root), "--steps", "8", "--apply") == 1
    assert len(prompts) == 1
    assert first.is_dir() and second.is_dir()


def test_p5_never_moves_a_folder_whose_date_cannot_be_read(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-02-31_(Mon)__12.00.00 - Bad"
    write(event / "photo.jpg")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 1
    assert event.is_dir()
    assert "N6" in capsys.readouterr().out


def orphaned_sidecar(tmp_path, name="2026-07-15_(Wed)__12.00.00.jpg"):
    """A sidecar correctly placed and named for a subject that is not there."""
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day"
    write(event / name)
    orphan = write(event / "__EXIF" / ("gone_" + name + "._exif"), b"exif")
    return root, event, orphan


def test_x1_orphan_is_parked_in_the_months_orphans_and_stays_parked(tmp_path, config):
    root, event, orphan = orphaned_sidecar(tmp_path)
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert not orphan.exists()
    parked = root / "2026" / "07. July" / "__ORPHANS" / orphan.name
    assert parked.read_bytes() == b"exif"
    assert run(str(root), "--steps", "7") == 0
    before = snapshot(root / "2026")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert snapshot(root / "2026") == before


def test_x1_orphan_dry_run_reports_the_destination_without_writing(tmp_path, config,
                                                                   capsys):
    root, event, orphan = orphaned_sidecar(tmp_path)
    before = snapshot(root)
    assert run(str(root), "--steps", "8") == 1
    assert snapshot(root) == before
    assert "__ORPHANS" in capsys.readouterr().out


def test_x1_a_sidecar_whose_subject_is_elsewhere_follows_it_instead(tmp_path, config):
    """X10 first: parking is only for a subject that is nowhere at all."""
    root, event, _orphan = orphaned_sidecar(tmp_path)
    other = root / "2026" / "07. July" / "2026-07-16_(Thu)__12.00.00 - Next"
    name = "2026-07-16_(Thu)__12.00.00.jpg"
    write(other / name)
    stray = write(event / "__EXIF" / (name + "._exif"), b"follows")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert not stray.exists()
    assert (other / "__EXIF" / (name + "._exif")).read_bytes() == b"follows"


def test_two_orphans_of_one_name_are_prefixed_rather_than_overwritten(tmp_path, config):
    """The counter goes in front so the trailing extension survives (X2)."""
    root = make_archive(tmp_path)
    month = root / "2026" / "07. July"
    for day, payload in (("15_(Wed)", b"first"), ("16_(Thu)", b"second")):
        event = month / ("2026-07-%s__12.00.00 - Day" % day)
        write(event / ("2026-07-%s__12.00.00.jpg" % day))
        write(event / "__EXIF" / "gone.jpg._exif", payload)
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    parked = {path.name: path.read_bytes()
              for path in (month / "__ORPHANS").iterdir()}
    assert parked == {"gone.jpg._exif": b"first", "_2_gone.jpg._exif": b"second"}
    assert run(str(root), "--steps", "7") == 0


def test_an_orphans_folder_inside_a_leaf_is_hoisted_to_its_month(tmp_path, config):
    """H2/H6 apply to both parking areas, and never pool one into the other."""
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day"
    write(event / "2026-07-15_(Wed)__12.00.00.jpg")
    write(event / "__ORPHANS" / "gone.jpg._exif", b"exif")
    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    assert not (event / "__ORPHANS").exists()
    assert (root / "2026" / "07. July" / "__ORPHANS" / "gone.jpg._exif"
            ).read_bytes() == b"exif"


def test_a_logs_folder_below_a_year_is_reported_but_never_walked(tmp_path, config,
                                                                 capsys):
    """J1: journals go directly under a year folder, and nowhere else."""
    root = make_archive(tmp_path)
    write(root / "2026" / "07. July" / "__LOGS" / "_restructure_journal.jsonl", b"{}")
    assert run(str(root), "--steps", "7") == 1
    output = capsys.readouterr().out
    assert "J4" in output
    assert "_restructure_journal.jsonl" not in output


def test_a_years_own_logs_folder_is_still_exempt(tmp_path, config, capsys):
    root = make_archive(tmp_path)
    write(root / "2026" / "__LOGS" / "_restructure_journal.jsonl", b"{}")
    assert run(str(root), "--steps", "7") == 0
    assert "__LOGS" not in capsys.readouterr().out


def test_an_orphan_inside_a_group_parks_in_that_group(tmp_path, config):
    """H2: the nearest level a parking area may sit on, not the month."""
    root, group = group_fixture(tmp_path)
    child = next(path for path in group.iterdir() if path.is_dir())
    write(child / "__EXIF" / "gone.jpg._exif", b"exif")
    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    # The marker pass renames the group in the same run, so it is found again
    # by the one thing that did not change: the parking area it now holds.
    parked = list(root.rglob("__ORPHANS/gone.jpg._exif"))
    assert len(parked) == 1
    assert parked[0].read_bytes() == b"exif"
    assert parked[0].parent.parent.parent.name == "07. July"
    assert not (root / "2026" / "07. July" / "__ORPHANS").exists()
    assert run(str(root), "--steps", "7") == 0


def test_ps11_reported_shapes_are_all_settled_in_one_run(tmp_path, config, capsys):
    """The three findings PS-11 was opened for, in the shapes it reported them.

    A leaf under the wrong month, a canonically named sidecar whose subject is
    gone from a marked folder, and a year's own ``__LOGS`` -- which was never
    a violation and must not be named as one.
    """
    root = make_archive(tmp_path)
    write(root / "2026" / "__LOGS" / "_restructure_journal_2026.jsonl", b"{}")

    misplaced = root / "2026" / "07. July" / "2026-08-01_(Sat)__00.10.51 - Flowers"
    write(misplaced / "2026-08-01_(Sat)__00.10.51.jpg")

    marked = root / "2026" / "07. July" / "2026-07-22_(Wed)__18.35.29 - __TO_SPLIT__(e=1)"
    write(marked / "2026-07-22_(Wed)__18.35.29.jpg")
    subject = "2026-07-22_(Wed)__18.35.29__f2.2__T1_313__L13.0.eq__I50__SG23U.jpg"
    write(marked / "__EXIF" / (subject + "._exif"), b"exif")

    assert run(str(root), "--steps", "7") == 1
    reported = capsys.readouterr().out
    assert "P5" in reported and "X1" in reported
    assert "__LOGS" not in reported and "P3" not in reported

    assert run(str(root), "--steps", "8", "--apply", "--yes") == 0
    assert (root / "2026" / "08. August" / misplaced.name
            / "2026-08-01_(Sat)__00.10.51.jpg").is_file()
    assert (root / "2026" / "07. July" / "__ORPHANS" / (subject + "._exif")
            ).read_bytes() == b"exif"
    assert (root / "2026" / "__LOGS" / "_restructure_journal_2026.jsonl").is_file()
    assert run(str(root), "--steps", "7") == 0


def test_a_parked_orphan_survives_every_other_step_untouched(tmp_path, config,
                                                             fake_grouper):
    """Nothing after step 8 renames, re-matches or re-parks what it parked."""
    root = make_archive(tmp_path)
    event = root / "2026" / "07. July" / "2026-07-15_(Wed)__12.00.00 - Day"
    write(event / "2026-07-15_(Wed)__12.00.00.jpg")
    write(event / "__EXIF" / "2026-07-15_(Wed)__12.00.00.jpg._exif", b"kept")
    write(event / "__EXIF" / "2026-07-14_(Tue)__09.00.00.jpg._exif", b"orphan")

    steps = "1,2,4,5,6,7,8"          # 3 opens the grouper GUI
    assert run(str(root), "--steps", steps, "--apply", "--yes") == 0
    parked = root / "2026" / "07. July" / "__ORPHANS" / "2026-07-14_(Tue)__09.00.00.jpg._exif"
    assert parked.read_bytes() == b"orphan"

    def archive(): # J2: a run's own journals are not part of the archive
        return {name: content for name, content in snapshot(root / "2026").items()
                if not name.startswith("__LOGS")}

    before = archive()
    assert run(str(root), "--steps", steps, "--apply", "--yes") == 0
    assert archive() == before
