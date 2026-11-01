"""Folders whose name order is expected to differ from time order (K8, order_accepted)."""

from src.pipeline_stages.clock_readings import scan_roots
from src.pipeline_stages.clock_view import build_view
from src.pipeline_stages.retime_plan import describe, plan_folder
from src.pipeline_stages.timezone_engine import TimeModel
from tests.test_clock_evidence import CONFIG, sidecar_text, write_shot

FOLDER = "2026-09-15_(Tue)__11.08.17 - Barcelona z samolotu"
TRIP = {"country": "Europe/Madrid", "from": "2026-09-15_(Tue)__12.08.14", "to": "2026-09-23_(Wed)__20.34.47"}


def barcelona(root):
    """The real case: the phone switched to Madrid time on landing, 3 s after its last UK-time shot."""
    folder = root / "2026" / "09. September" / FOLDER
    write_shot(folder, "2026-09-15_(Tue)__11.08.17__SG23U.jpg",
               sidecar_text("Galaxy S23 Ultra", "2026:09:15 11:08:17", "+01:00"))
    write_shot(folder, "2026-09-15_(Tue)__12.08.14__SG23U.jpg",
               sidecar_text("Galaxy S23 Ultra", "2026:09:15 12:08:14", "+02:00"))
    return folder


def model(accepted=()):
    return TimeModel({"home": "GB", "mobiles": ["SG23U"], "trips": [TRIP],
                      "order_accepted": [{"folder": name, "why": "phone synced on landing"} for name in accepted]})


def test_the_inversion_is_reported_until_accepted(tmp_path):
    folder = barcelona(tmp_path)
    plan = plan_folder(folder, CONFIG, model())
    assert plan.inversions and not plan.order_accepted
    plan = plan_folder(folder, CONFIG, model([FOLDER]))
    assert plan.order_accepted
    assert "accepted in timezone.json" in "\n".join(describe(plan))


def test_matched_on_date_and_description_not_time():
    # Re-dating may change the folder's time; the acceptance still holds.
    assert model([FOLDER]).accepts_order("2026-09-15_(Tue)__13.00.00 - Barcelona z samolotu")
    assert not model([FOLDER]).accepts_order("2026-09-16_(Wed)__11.08.17 - Barcelona z samolotu")
    assert not model([FOLDER]).accepts_order("2026-09-15_(Tue)__11.08.17 - Barcelona")


def test_bad_entry_is_an_error():
    assert any("order_accepted[0]" in error for error in TimeModel({"order_accepted": ["Barcelona"]}).errors)


def test_visualiser_drops_the_note(tmp_path):
    barcelona(tmp_path / "C")
    folders = scan_roots([tmp_path / "C"], CONFIG, cache_dir=tmp_path / "cache")
    assert any("out of time order" in note for note in build_view(folders, model()).rows[0].notes)
    assert not any("out of time order" in note for note in build_view(folders, model([FOLDER])).rows[0].notes)
