"""ExifTool extraction shared by live ingest and archive restructuring."""

from pathlib import Path

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
