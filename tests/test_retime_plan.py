"""Re-dating sorted folders: planning and applying (camera-time-correction)."""

import json
from pathlib import Path

from src.pipeline_stages.retime_plan import apply_plan, describe, plan_folder
from src.pipeline_stages.timezone_engine import TimeModel
from tests.test_clock_evidence import CONFIG, sidecar_text, write_shot

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "time_vectors.json").read_text(encoding="utf-8"))
ACCEPTANCE = TimeModel(VECTORS["corrections"][0]["config"])
CALIBRATION = "2026-09-27_(Sun)__19.08.31 - Sony 7riV mobile calibration photos, before and after"


def calibration_folder(root: Path) -> Path:
    """The real calibration folder's shape: two shots, their RAWs, sidecars at both levels."""
    folder = root / "2026" / "09. September" / CALIBRATION
    shots = (("19.08.31", "I320", "+00:00", 16878, "774"), ("20.20.58", "I250", "+01:00", 16879, "925"))
    for time, iso, offset, counter, subsec in shots:
        hh, mm, ss = time.split(".")
        text = sidecar_text("ILCE-7RM5", f"2026:09:27 {hh}:{mm}:{ss}", offset, counter, subsec)
        write_shot(folder, f"2026-09-27_(Sun)__{time}__f3.2__T1_100__L85.0.eq__{iso}__ILC7R5_HAS_RAW.jpg", text)
        write_shot(folder, f"2026-09-27_(Sun)__{time}__RAW__f3.2__T1_100__L85.0.eq__{iso}__ILC7R5.ARW", text,
                   subdir="__RAW")
    return folder


def names(folder: Path) -> list[str]:
    return sorted(str(path.relative_to(folder)).replace("\\", "/") for path in folder.rglob("*") if path.is_file())


def test_acceptance_plan(tmp_path):
    folder = calibration_folder(tmp_path)
    plan = plan_folder(folder, CONFIG, ACCEPTANCE)
    renames = {move.source.name: move.target.name for move in plan.moves}
    assert renames["2026-09-27_(Sun)__19.08.31__f3.2__T1_100__L85.0.eq__I320__ILC7R5_HAS_RAW.jpg"] == \
        "2026-09-27_(Sun)__20.09.51__f3.2__T1_100__L85.0.eq__I320__ILC7R5_HAS_RAW.jpg"
    assert renames["2026-09-27_(Sun)__20.20.58__RAW__f3.2__T1_100__L85.0.eq__I250__ILC7R5.ARW._exif"] == \
        "2026-09-27_(Sun)__20.20.59__RAW__f3.2__T1_100__L85.0.eq__I250__ILC7R5.ARW._exif"
    assert len(plan.moves) == 8          # 2 JPEGs + 2 RAWs, each with its sidecar
    assert all(shot.target_folder == folder for shot in plan.shots)
    assert plan.folder_time_after == "20.09.51"
    text = "\n".join(describe(plan))
    assert "day folder unchanged" in text and "name order: chronological" in text
    assert "+1h 01m 20s" in text


def test_apply_then_second_plan_is_empty(tmp_path):
    folder = calibration_folder(tmp_path)
    apply_plan(plan_folder(folder, CONFIG, ACCEPTANCE), log=lambda _: None)
    assert names(folder) == [
        "2026-09-27_(Sun)__20.09.51__f3.2__T1_100__L85.0.eq__I320__ILC7R5_HAS_RAW.jpg",
        "2026-09-27_(Sun)__20.20.59__f3.2__T1_100__L85.0.eq__I250__ILC7R5_HAS_RAW.jpg",
        "__EXIF/2026-09-27_(Sun)__20.09.51__f3.2__T1_100__L85.0.eq__I320__ILC7R5_HAS_RAW.jpg._exif",
        "__EXIF/2026-09-27_(Sun)__20.20.59__f3.2__T1_100__L85.0.eq__I250__ILC7R5_HAS_RAW.jpg._exif",
        "__RAW/2026-09-27_(Sun)__20.09.51__RAW__f3.2__T1_100__L85.0.eq__I320__ILC7R5.ARW",
        "__RAW/2026-09-27_(Sun)__20.20.59__RAW__f3.2__T1_100__L85.0.eq__I250__ILC7R5.ARW",
        "__RAW/__EXIF/2026-09-27_(Sun)__20.09.51__RAW__f3.2__T1_100__L85.0.eq__I320__ILC7R5.ARW._exif",
        "__RAW/__EXIF/2026-09-27_(Sun)__20.20.59__RAW__f3.2__T1_100__L85.0.eq__I250__ILC7R5.ARW._exif",
    ]
    assert not plan_folder(folder, CONFIG, ACCEPTANCE).changes


def test_revert_by_config(tmp_path):
    folder = calibration_folder(tmp_path)
    apply_plan(plan_folder(folder, CONFIG, ACCEPTANCE), log=lambda _: None)
    back = plan_folder(folder, CONFIG, TimeModel({"home": "GB"}))
    assert sorted(shot.new_name[:26] for shot in back.shots if shot.subject.parent == folder) == \
        ["2026-09-27_(Sun)__19.08.31", "2026-09-27_(Sun)__20.20.58"]


def test_shot_crossing_the_day_boundary_moves_with_its_unit(tmp_path):
    folder = tmp_path / "2026" / "07. July" / "2026-07-01_(Wed)__22.00.00 - Party"
    name = "2026-07-02_(Thu)__03.50.00__f2.8__C6D.jpg"
    write_shot(folder, name, sidecar_text("Canon EOS 6D", "2026:07:02 03:50:00"))
    (folder / "__PREVIEWS").mkdir()
    (folder / "__PREVIEWS" / f"{name}.thm").write_bytes(b"t")
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "6D", "clock": "home-winter"}]})
    plan = plan_folder(folder, {**CONFIG}, model)
    target = tmp_path / "2026" / "07. July" / "2026-07-02_(Thu) - Party"
    assert plan.shots[0].target_folder == target and target in plan.new_folders
    apply_plan(plan, log=lambda _: None)
    assert (target / "2026-07-02_(Thu)__04.50.00__f2.8__C6D.jpg").exists()
    assert (target / "__EXIF" / "2026-07-02_(Thu)__04.50.00__f2.8__C6D.jpg._exif").exists()
    assert (target / "__PREVIEWS" / "2026-07-02_(Thu)__04.50.00__f2.8__C6D.jpg.thm").exists()
    assert not list(folder.rglob("*.jpg"))


def test_crossing_into_another_month_creates_the_month_folder(tmp_path):
    folder = tmp_path / "2026" / "09. September" / "2026-09-30_(Wed)__23.00.00 - Night"
    write_shot(folder, "2026-10-01_(Thu)__04.30.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:10:01 04:30:00"))
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "6D", "clock": "home-winter"}]})
    plan = plan_folder(folder, CONFIG, model)
    assert plan.shots[0].target_folder == tmp_path / "2026" / "10. October" / "2026-10-01_(Thu) - Night"


def test_taken_name_is_a_question_unless_sub_seconds_tell_them_apart(tmp_path):
    folder = tmp_path / "2026" / "07. July" / "2026-07-01_(Wed)__12.00.00 - X"
    write_shot(folder, "2026-07-01_(Wed)__12.00.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:07:01 12:00:00"))
    # Already holding the target name, with a sidecar recording another sub-second.
    write_shot(folder, "2026-07-01_(Wed)__13.00.00__C6D.jpg",
               sidecar_text("Canon EOS 5D", "2026:07:01 13:00:00", subsec="10"))
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "6D", "clock": "home-winter"}]})
    plan = plan_folder(folder, CONFIG, model)
    assert not plan.shots and "F4" in plan.skipped[0][1]

    write_shot(folder, "2026-07-01_(Wed)__12.00.00__C6D.jpg",
               sidecar_text("Canon EOS 6D", "2026:07:01 12:00:00", subsec="55"))
    plan = plan_folder(folder, CONFIG, model)
    assert plan.shots[0].new_name == "2026-07-01_(Wed)__13.00.00.55__C6D.jpg"


def test_rename_chain_is_applied_without_overwriting(tmp_path):
    folder = tmp_path / "2026" / "07. July" / "2026-07-01_(Wed)__12.00.00 - X"
    write_shot(folder, "2026-07-01_(Wed)__12.00.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:07:01 12:00:00"))
    write_shot(folder, "2026-07-01_(Wed)__13.00.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:07:01 13:00:00"))
    (folder / "2026-07-01_(Wed)__12.00.00__C6D.jpg").write_bytes(b"first")
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "6D", "clock": "home-winter"}]})
    apply_plan(plan_folder(folder, CONFIG, model), log=lambda _: None)
    assert (folder / "2026-07-01_(Wed)__13.00.00__C6D.jpg").read_bytes() == b"first"
    assert (folder / "2026-07-01_(Wed)__14.00.00__C6D.jpg").exists()


def test_hand_renamed_and_edit_followers(tmp_path):
    folder = tmp_path / "2026" / "07. July" / "2026-07-01_(Wed)__12.00.00 - X"
    write_shot(folder, "2026-07-01_(Wed)__12.05.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:07:01 12:00:00"))
    (folder / "__EDITED").mkdir()
    (folder / "__EDITED" / "2026-07-01_(Wed)__12.05.00__C6D_edit.jpg").write_bytes(b"e")
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "6D", "clock": "home-winter"}]})
    plan = plan_folder(folder, CONFIG, model)
    assert any("renamed by hand" in flag for flag in plan.shots[0].flags)
    assert not any(move.role == "follower" for move in plan.moves)  # the edit is in another place
    write_shot(folder, "2026-07-01_(Wed)__12.05.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:07:01 12:05:00"))
    (folder / "2026-07-01_(Wed)__12.05.00__C6D.png").write_bytes(b"export")
    plan = plan_folder(folder, CONFIG, model)
    followers = [move for move in plan.moves if move.role == "follower"]
    assert [move.target.name for move in followers] == ["2026-07-01_(Wed)__13.05.00__C6D.png"]


def test_groups_are_not_planned(tmp_path):
    group = tmp_path / "2026" / "07. July" / "2026-07-01_(Wed)__12.00.00___GROUP___[ T ]___2026-07-02_(Thu)__10.00.00"
    write_shot(group / "2026-07-01_(Wed)__12.00.00 - Day", "2026-07-01_(Wed)__12.00.00__C6D.jpg",
               sidecar_text("Canon EOS 6D", "2026:07:01 12:00:00"))
    write_shot(group, "2026-07-01_(Wed)__12.30.00__C6D.jpg", sidecar_text("Canon EOS 6D", "2026:07:01 12:30:00"))
    model = TimeModel({"home": "GB", "camera_clocks": [{"camera": "6D", "clock": "home-winter"}]})
    plan = plan_folder(group, CONFIG, model)
    assert not plan.changes and "group" in plan.notes[0]
