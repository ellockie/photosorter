"""Steps 7/8 only ever operate on explicit disposable archive roots here."""

import json

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
    assert list((root / "2026" / "07. July").glob("*Trip"))
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
    assert list((root / "2026" / "08. August").glob("*Trip"))


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
