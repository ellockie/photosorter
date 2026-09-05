r"""Undoing the grouper's prefix: what it strips, and everything it must not.

Every test here passes an explicit ``--target`` under ``tmp_path``. The tool's
default target is the real archive (``c:\\__PHOTOS\\2026``) and it renames with
bare ``os.rename``, so it is not covered by the ``src.core`` sandbox guard in
conftest: a test that omitted the target would rename the live archive.
"""

import importlib.util
import json
from pathlib import Path

import pytest

TOOL_PATH = (Path(__file__).resolve().parent.parent
             / "tools" / "unwrap_grouper_prefixes.py")


def _load_tool():
    spec = importlib.util.spec_from_file_location("unwrap_grouper_prefixes",
                                                  TOOL_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load_tool()

# One real name off the archive, so the fixtures are not a tidier version of the
# thing being repaired.
CAPTURE = "2026-07-18_(Sat)__15.18.20__f1.7__T1_522__L23.0.eq__I10__SG23U.jpg"
WRAPPED = "2026-07-18_(Sat)__15.18.44__SCR__" + CAPTURE


# --------------------------------------------------------------------------
# Reading a wrapped name
# --------------------------------------------------------------------------

def test_reads_the_real_wrapped_name():
    wrapped = tool.read_wrapped(WRAPPED)
    assert wrapped is not None
    assert wrapped.inner_name == CAPTURE
    assert wrapped.marker == "SCR"
    assert wrapped.gap_seconds == 24


@pytest.mark.parametrize("name", [
    # A genuine screenshot: one stamp, and the trailing text is not a date.
    "2026-07-18_(Sat)__14.30.00__SCR__Chrome.png",
    # A genuine screenshot with no trailing text at all.
    "2026-07-18_(Sat)__14.30.00__SCR.png",
    # An ordinary Photosorter capture.
    CAPTURE,
    # The marker without a timestamp in front of it.
    "SCR__" + CAPTURE,
    # A stamp trailing rather than leading: nothing to strip from the front.
    "holiday__" + CAPTURE,
])
def test_leaves_names_that_are_not_wrapped(name):
    assert tool.read_wrapped(name) is None


def test_reads_the_legacy_no_weekday_prefix():
    """The grouper wrote "YYYY-MM-DD__HH.MM.SS" before it carried a weekday."""
    wrapped = tool.read_wrapped("2026-07-19__21.29.04__SCR__" + CAPTURE)
    assert wrapped is not None and wrapped.inner_name == CAPTURE


def test_reads_the_collision_counter_the_grouper_writes():
    wrapped = tool.read_wrapped("2026-07-18_(Sat)__15.18.44__2__SCR__" + CAPTURE)
    assert wrapped is not None and wrapped.inner_name == CAPTURE


def test_reads_a_wrapped_video():
    name = "2026-07-18_(Sat)__15.18.44__VIDEO__2026-07-18_(Sat)__15.18.20.mp4"
    wrapped = tool.read_wrapped(name)
    assert wrapped is not None and wrapped.marker == "VIDEO"


def test_reads_a_wrapped_sidecar():
    """A companion carrying the wrapped name is unwrapped by the same rule."""
    wrapped = tool.read_wrapped(WRAPPED + "._exif")
    assert wrapped is not None and wrapped.inner_name == CAPTURE + "._exif"


def test_rejects_an_impossible_date():
    assert tool.read_wrapped("2026-02-30_(Mon)__15.18.44__SCR__" + CAPTURE) is None


def test_refuses_a_prefix_earlier_than_the_capture_it_wraps():
    """A creation time cannot precede the capture; this is some other name."""
    wrapped = tool.read_wrapped("2026-07-18_(Sat)__15.18.01__SCR__" + CAPTURE)
    reason = tool.reason_to_refuse(wrapped)
    assert reason is not None and "EARLIER" in reason


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------

def _event_folder(tmp_path):
    folder = tmp_path / "2026-07-18_(Sat)__15.18.42 - Trip to Camden"
    (folder / "__EXIF").mkdir(parents=True)
    return folder


def test_dry_run_changes_nothing_and_asks_to_be_re_run(tmp_path, capsys):
    folder = _event_folder(tmp_path)
    (folder / WRAPPED).write_bytes(b"jpg")

    assert tool.main([str(tmp_path), "--no-colour"]) == 1
    assert (folder / WRAPPED).exists()
    assert not (folder / CAPTURE).exists()
    assert "Re-run with --apply" in capsys.readouterr().out


def test_apply_restores_the_name_the_sidecar_was_written_for(tmp_path):
    folder = _event_folder(tmp_path)
    (folder / WRAPPED).write_bytes(b"jpg")
    sidecar = folder / "__EXIF" / (CAPTURE + "._exif")
    sidecar.write_text("exif")

    assert tool.main([str(tmp_path), "--apply", "--no-colour"]) == 0

    assert (folder / CAPTURE).exists()
    assert not (folder / WRAPPED).exists()
    # The pair place_companions could not see before.
    assert sidecar.name.startswith((folder / CAPTURE).name)


def test_a_genuine_screenshot_beside_it_is_untouched(tmp_path):
    folder = _event_folder(tmp_path)
    (folder / WRAPPED).write_bytes(b"jpg")
    screenshot = folder / "2026-07-18_(Sat)__14.30.00__SCR__Chrome.png"
    screenshot.write_bytes(b"png")

    assert tool.main([str(tmp_path), "--apply", "--no-colour"]) == 0
    assert screenshot.exists()


def test_a_taken_name_is_a_conflict_not_an_overwrite(tmp_path, capsys):
    folder = _event_folder(tmp_path)
    (folder / WRAPPED).write_bytes(b"wrapped")
    (folder / CAPTURE).write_bytes(b"original")

    assert tool.main([str(tmp_path), "--apply", "--no-colour"]) == 1
    assert (folder / WRAPPED).read_bytes() == b"wrapped"
    assert (folder / CAPTURE).read_bytes() == b"original"
    assert "already exists" in capsys.readouterr().out


def test_two_wrappers_of_one_name_are_both_left(tmp_path, capsys):
    """Two files claiming one name is an anomaly to report, not to number."""
    folder = _event_folder(tmp_path)
    first = folder / WRAPPED
    second = folder / ("2026-07-18_(Sat)__15.18.49__SCR__" + CAPTURE)
    first.write_bytes(b"one")
    second.write_bytes(b"two")

    assert tool.main([str(tmp_path), "--apply", "--no-colour"]) == 1
    assert (folder / CAPTURE).exists()          # the first one won
    assert first.exists() != second.exists()    # exactly one was unwrapped
    assert "unwraps to the same name" in capsys.readouterr().out


def test_undo_puts_the_prefix_back(tmp_path):
    folder = _event_folder(tmp_path)
    (folder / WRAPPED).write_bytes(b"jpg")
    journal = tmp_path / "journal.jsonl"

    assert tool.main([str(tmp_path), "--apply", "--journal", str(journal),
                      "--no-colour"]) == 0
    assert (folder / CAPTURE).exists()

    records = [json.loads(line) for line in
               journal.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 1

    assert tool.main(["--undo", str(journal), "--apply", "--no-colour"]) == 0
    assert (folder / WRAPPED).exists()
    assert not (folder / CAPTURE).exists()


def test_reports_the_folder_time_the_unwrap_moves(tmp_path, capsys):
    """The folder is stamped from a creation time; after the unwrap it is not."""
    folder = _event_folder(tmp_path)
    (folder / WRAPPED).write_bytes(b"jpg")

    tool.main([str(tmp_path), "--no-colour"])
    out = capsys.readouterr().out
    assert "earliest capture time changes" in out
    assert "15.18.44  ->  15.18.20" in out
