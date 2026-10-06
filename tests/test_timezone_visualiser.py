"""The timezone visualiser: lanes, slots, rules, merged roots (camera-time-correction)."""

import datetime

from src.pipeline_stages.clock_readings import scan_roots
from src.pipeline_stages.clock_view import ASCII, build_view, render_html, render_text
from src.pipeline_stages.timezone_engine import TimeModel
from tests.test_clock_evidence import CONFIG, sidecar_text, write_shot

H = datetime.timedelta(hours=1)


def scan(*roots, tmp_path):
    return scan_roots(list(roots), CONFIG, cache_dir=tmp_path / "cache")


def july_folder(root, name="2026-07-01_(Wed)__12.00.00 - Walk"):
    folder = root / "2026" / "07. July" / name
    write_shot(folder, "2026-07-01_(Wed)__12.00.00__ILC7R5.jpg",
               sidecar_text("ILCE-7RM5", "2026:07:01 12:00:00", "+00:00", 100))
    write_shot(folder, "2026-07-01_(Wed)__13.00.05__SG23U.jpg",
               sidecar_text("Galaxy S23 Ultra", "2026:07:01 13:00:05", "+01:00"))
    return folder


def test_same_offset_draws_distinct_slots(tmp_path):
    july_folder(tmp_path / "C")
    view = build_view(scan(tmp_path / "C", tmp_path=tmp_path),
                      TimeModel({"home": "GB", "mobiles": ["SG23U"]}))
    row = view.rows[0]
    # No entry for the camera: assumed right, so everything is on +01:00 --
    # local marker and both cameras, each in its own slot.
    assert row.local_lanes == {H}
    assert row.cameras["ILC7R5"].lanes == {H} and row.cameras["SG23U"].lanes == {H}
    line = next(line for line in render_text(view, ASCII) if "Walk" in line)
    assert line.startswith("* a b")


def test_dst_off_camera_sits_in_another_lane(tmp_path):
    july_folder(tmp_path / "C")
    model = TimeModel({"home": "GB", "mobiles": ["SG23U"], "camera_clocks": [{"camera": "ILC7R5", "clock": "home-winter"}]})
    row = build_view(scan(tmp_path / "C", tmp_path=tmp_path), model).rows[0]
    assert row.cameras["ILC7R5"].lanes == {datetime.timedelta(0)}
    assert row.local_lanes == {H}


def test_declared_offset_disagreement_is_a_note_not_an_input(tmp_path):
    july_folder(tmp_path / "C")
    row = build_view(scan(tmp_path / "C", tmp_path=tmp_path), TimeModel({"home": "GB", "mobiles": ["SG23U"]})).rows[0]
    assert row.cameras["ILC7R5"].lanes == {H}
    assert any("ILC7R5 declares +00:00" in note for note in row.notes)


def test_dst_rule_sits_between_folders(tmp_path):
    for name, reading in (("2026-03-28_(Sat)__10.00.00 - Before", "2026:03:28 10:00:00"),
                          ("2026-03-30_(Mon)__10.00.00 - After", "2026:03:30 10:00:00")):
        folder = tmp_path / "C" / "2026" / "03. March" / name
        write_shot(folder, f"{name[:26]}__SG23U.jpg", sidecar_text("Galaxy S23 Ultra", reading))
    lines = render_text(build_view(scan(tmp_path / "C", tmp_path=tmp_path),
                                   TimeModel({"home": "GB", "mobiles": ["SG23U"]})), ASCII)
    before = next(i for i, line in enumerate(lines) if "Before" in line)
    rule = next(i for i, line in enumerate(lines) if "DST Europe/London +00:00 -> +01:00" in line)
    after = next(i for i, line in enumerate(lines) if "After" in line)
    assert before < rule < after


def test_trip_rules_and_assumed_state(tmp_path):
    folder = tmp_path / "C" / "2026" / "04. April" / "2026-04-12_(Sun)__17.00.00 - Tokyo"
    write_shot(folder, "x.jpg", sidecar_text("ILCE-7RM5", "2026:04:12 09:00:00", counter=1))
    model = TimeModel({"home": "GB", "trips": [{"country": "JP", "from": "2026-04-11_(Sat)__07.00.00",
                                                 "to": "2026-04-20_(Mon)__21.00.00"}]})
    view = build_view(scan(tmp_path / "C", tmp_path=tmp_path), model)
    text = "\n".join(render_text(view, ASCII))
    assert "TRIP JP (Asia/Tokyo) from 2026-04-11_(Sat)__07.00.00" in text
    assert "ILC7R5 ASSUMED home +8h 00m 00s" in text


def test_merged_row_and_aligned_names(tmp_path):
    july_folder(tmp_path / "C")
    july_folder(tmp_path / "N")
    group = tmp_path / "N" / "2026" / "07. July" / "2026-07-02_(Thu)__09.00.00___GROUP___[ Trip ]___2026-07-03_(Fri)__10.00.00"
    write_shot(group / "2026-07-02_(Thu)__09.00.00 - Day one" / "2026-07-02_(Thu)__09.00.00 - Deep",
               "d.jpg", sidecar_text("Galaxy S23 Ultra", "2026:07:02 09:00:00"))
    folders = scan(tmp_path / "C", tmp_path / "N", tmp_path=tmp_path)
    walk = next(folder for folder in folders if folder.name.endswith("Walk"))
    assert sorted(walk.copies) == [0, 1]
    assert len(walk.readings) == 2  # read once, not once per root
    view = build_view(folders, TimeModel({"home": "GB", "mobiles": ["SG23U"]}), ["C", "NAS"])
    assert [row.roots for row in view.rows] == ["C+NAS", "NAS", "NAS", "NAS"]
    lines = [line for line in render_text(view, ASCII) if "2026-07-0" in line]
    columns = {line.index("2026-07-0") for line in lines}
    assert len(columns) == 1
    assert [row.depth for row in view.rows] == [1, 1, 2, 3]


def test_html_page_carries_rows_and_legend(tmp_path):
    july_folder(tmp_path / "C")
    view = build_view(scan(tmp_path / "C", tmp_path=tmp_path), TimeModel({"home": "GB", "mobiles": ["SG23U"]}))
    page = render_html(view, "Camera clocks by folder", "test")
    assert "2026-07-01_(Wed)__12.00.00 - Walk" in page and "ILCE-7RM5" in page
    assert "prefers-color-scheme: dark" in page


def test_root_labels():
    from pathlib import PureWindowsPath as P
    from src.pipeline_stages.clock_view import root_labels
    assert root_labels([P(r"c:\__PHOTOS"), P(r"d:\___PHOTOS"), P(r"\\synology-dell\share\__PHOTOS"), P(r"c:\other")]) == \
        ["C", "D", "NAS", "C2"]
