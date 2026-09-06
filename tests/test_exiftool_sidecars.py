"""ExifTool extraction shared by live ingest and archive restructuring."""

from pathlib import Path

from src.pipeline_stages import exiftool_sidecars
from src.pipeline_stages.exiftool_sidecars import (
    SIDECAR_SUFFIX,
    WRITE_FORMAT,
    generate_adjacent_sidecars,
)


def test_generation_uses_x1_name_and_never_requests_overwrite(tmp_path):
    raw = tmp_path / "SHOT.ARW"
    raw.write_bytes(b"raw")
    calls = []

    def fake_exiftool(command):
        calls.append(command)
        Path(str(raw) + SIDECAR_SUFFIX).write_bytes(b"metadata")

    report = generate_adjacent_sidecars(
        [raw], "exiftool.exe", runner=fake_exiftool)

    assert report.created == [Path(str(raw) + SIDECAR_SUFFIX)]
    assert report.missing == []
    assert calls == [[
        "exiftool.exe", "-a", "-u", "-g1", "-w", WRITE_FORMAT, str(raw)]]
    assert "-w!" not in calls[0]


def test_a_missing_exiftool_names_every_raw_left_without_output(tmp_path):
    first = tmp_path / "A.ARW"
    second = tmp_path / "B.CR2"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    logs = []

    def missing(_command):
        raise FileNotFoundError("not installed")

    report = generate_adjacent_sidecars(
        [first, second], "missing-exiftool", logs.append, runner=missing)

    assert report.created == []
    assert report.missing == [first, second]
    assert report.errors == 1
    assert any("not found" in line for line in logs)


# --------------------------------------------------------------------------
# Which ExifTool actually runs
# --------------------------------------------------------------------------

def test_the_bundled_exiftool_is_preferred_over_the_bare_name(tmp_path):
    """Windows searches the working directory before PATH, so a bare
    "exiftool" means "whichever copy the launch directory happened to expose".
    On this machine that is a 2015 build with no long-path support, which
    reports a 289-character file as not found -- and a sidecar never written is
    a shot with no SubSecTimeOriginal for F9 to read.
    """
    bundled = tmp_path / exiftool_sidecars.BUNDLED_EXIFTOOL
    bundled.write_bytes(b"MZ")

    assert exiftool_sidecars.exiftool_command({}, tmp_path) == str(bundled)
    assert exiftool_sidecars.exiftool_command(
        {"external_tools": {"exiftool": "exiftool"}}, tmp_path) == str(bundled)


def test_an_explicitly_configured_exiftool_still_wins(tmp_path):
    """Naming a specific binary means it, bundled copy present or not."""
    (tmp_path / exiftool_sidecars.BUNDLED_EXIFTOOL).write_bytes(b"MZ")

    assert exiftool_sidecars.exiftool_command(
        {"external_tools": {"exiftool": r"D:\tools\exiftool.exe"}},
        tmp_path) == r"D:\tools\exiftool.exe"


def test_without_a_bundled_copy_the_bare_name_is_the_fallback(tmp_path):
    """The helpers stay usable outside a checkout."""
    assert exiftool_sidecars.exiftool_command({}, tmp_path) == "exiftool"


def test_this_repo_really_does_bundle_one():
    """The preference above is worth nothing if the file is not there."""
    from src.core import project_root

    assert exiftool_sidecars.bundled_exiftool(project_root()).is_file()
    # The small launcher, so its Perl folder has to be beside it or it cannot run.
    assert (project_root() / "exiftool_files").is_dir()
