"""Restructure step 0: re-time shots against timezone.json (camera-time-correction).

Every test runs on a scratch archive under ``tmp_path`` with its own
timezone file; ``--steps 0`` keeps the other steps out of it.
"""

import json
import sys

import pytest

from tests.test_clock_evidence import sidecar_text, write_shot
from tests.test_restructure_archive import config, fake_grouper, run, tool  # noqa: F401 (fixtures)
from tests.test_retime_plan import VECTORS, calibration_folder

ACCEPTANCE = VECTORS["corrections"][0]["config"]


@pytest.fixture
def timezone(tmp_path, monkeypatch, config):  # noqa: F811
    config["camera_symbols"] = {"ILCE-7RM5": "ILC7R5", "": "NOID"}
    path = tmp_path / "timezone.json"

    def write(data):
        path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(tool, "TIMEZONE_PATH", path)
    write(ACCEPTANCE)
    return write


def answers(monkeypatch, *replies):
    queue = list(replies)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr("builtins.input", lambda prompt="": queue.pop(0))
    return queue


def archive(tmp_path, count=1):
    root = tmp_path / "__PHOTOS_BACKUP"
    folders = []
    for index in range(count):
        folders.append(calibration_folder(root if index == 0 else tmp_path / f"extra{index}"))
    return root, folders


def stamps_in(folder):
    return sorted(path.name[18:26] for path in folder.glob("*.jpg"))


def test_dry_run_reports_and_changes_nothing(tmp_path, timezone, capsys):
    root, (folder,) = archive(tmp_path)
    assert run(str(root), "--year", "2026", "--steps", "0") == 1
    out = capsys.readouterr().out
    assert "19.08.31 -> 20.09.51" in out and "Nothing was changed (dry run)" in out
    assert stamps_in(folder) == ["19.08.31", "20.20.58"]


def test_yes_applies_the_acceptance_renames_and_journals_them(tmp_path, timezone, monkeypatch):
    root, (folder,) = archive(tmp_path)
    answers(monkeypatch, "y")
    assert run(str(root), "--year", "2026", "--steps", "0", "--apply") == 0
    assert stamps_in(folder) == ["20.09.51", "20.20.59"]
    assert sorted(path.name[18:26] for path in (folder / "__RAW").glob("*.ARW")) == ["20.09.51", "20.20.59"]
    journal = next((root / "2026" / "__LOGS").glob("_restructure_journal_*.jsonl")).read_text(encoding="utf-8")
    assert journal.count('"event": "retime"') == 8
    # Idempotent: the next run has nothing to ask.
    answers(monkeypatch)
    assert run(str(root), "--year", "2026", "--steps", "0", "--apply") == 0


def test_no_leaves_the_folder_and_asks_again_next_time(tmp_path, timezone, monkeypatch):
    root, (folder,) = archive(tmp_path)
    answers(monkeypatch, "n")
    assert run(str(root), "--year", "2026", "--steps", "0", "--apply") == 1
    assert stamps_in(folder) == ["19.08.31", "20.20.58"]
    queue = answers(monkeypatch, "y")
    run(str(root), "--year", "2026", "--steps", "0", "--apply")
    assert not queue and stamps_in(folder) == ["20.09.51", "20.20.59"]


def test_yes_to_all_stops_asking(tmp_path, timezone, monkeypatch):
    root = tmp_path / "__PHOTOS_BACKUP"
    month = root / "2026" / "09. September"
    first = calibration_folder(root)
    second = month / "2026-09-26_(Sat)__10.00.00 - Earlier"
    write_shot(second, "2026-09-26_(Sat)__10.00.00__ILC7R5.jpg",
               sidecar_text("ILCE-7RM5", "2026:09:26 10:00:00", "+00:00", 16000))
    queue = answers(monkeypatch, "a")   # one answer for two folders
    assert run(str(root), "--year", "2026", "--steps", "0", "--apply") == 0
    assert not queue
    assert stamps_in(first) == ["20.09.51", "20.20.59"]
    assert stamps_in(second) == ["11.01.20"]


def test_no_terminal_is_not_a_yes(tmp_path, timezone, monkeypatch):
    root, (folder,) = archive(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    assert run(str(root), "--year", "2026", "--steps", "0", "--apply") == 1
    assert stamps_in(folder) == ["19.08.31", "20.20.58"]


def test_yes_flag_answers_all(tmp_path, timezone):
    root, (folder,) = archive(tmp_path)
    assert run(str(root), "--year", "2026", "--steps", "0", "--apply", "--yes") == 0
    assert stamps_in(folder) == ["20.09.51", "20.20.59"]


def test_from_to_bounds_the_readings(tmp_path, timezone, monkeypatch):
    root, (folder,) = archive(tmp_path)
    answers(monkeypatch, "y")
    run(str(root), "--year", "2026", "--steps", "0", "--apply", "--from", "2026-09-28", "--to", "2026-09-30")
    assert stamps_in(folder) == ["19.08.31", "20.20.58"]


def test_empty_record_is_nothing_to_do(tmp_path, timezone, capsys):
    timezone({"home": "GB"})
    root, _ = archive(tmp_path)
    assert run(str(root), "--year", "2026", "--steps", "0") == 0
    assert "nothing to re-time" in capsys.readouterr().out


def test_unusable_record_is_reported_and_steps_go_on(tmp_path, timezone, capsys):
    timezone({"camera_clock_sets": []})
    root, (folder,) = archive(tmp_path)
    assert run(str(root), "--year", "2026", "--steps", "0,1") == 1
    out = capsys.readouterr().out
    assert "superseded schema" in out and "STEP 1" in out.upper()
    assert stamps_in(folder) == ["19.08.31", "20.20.58"]


def test_collision_is_reported_not_overwritten(tmp_path, timezone, monkeypatch, capsys):
    root, (folder,) = archive(tmp_path)
    taken = folder / "2026-09-27_(Sun)__20.09.51__f3.2__T1_100__L85.0.eq__I320__ILC7R5_HAS_RAW.jpg"
    taken.write_bytes(b"someone else")
    answers(monkeypatch, "y")
    run(str(root), "--year", "2026", "--steps", "0", "--apply")
    assert taken.read_bytes() == b"someone else"
    assert "F4: needs a person" in capsys.readouterr().out
