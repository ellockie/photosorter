"""Motion photos: the video they carry is extracted, filed, and travels (X16).

ExifTool is faked everywhere except one test, which builds a tiny motion photo
of the older Google ``MicroVideo`` kind byte by byte and runs the bundled
ExifTool on it for real. No photograph from anywhere is used: a test that
needs a motion photo makes one.
"""

import struct
import sys
from pathlib import Path

import pytest

# Load the application normally before the standalone tool installs its
# dependency-free package stubs (see test_archive_compliance.py).
import src.pipeline_stages
from src.core import MediaAsset, PipelineContext, project_root
from src.pipeline_stages import embedded_videos as ev
from src.pipeline_stages.companion_matching import place_companions, reconcile_folder
from src.pipeline_stages.embedded_video_extraction import EmbeddedVideoExtractionStage
from src.pipeline_stages.exiftool_sidecars import bundled_exiftool
from src.pipeline_stages.grouping_names import count_media, select_media

from test_restructure_archive import tool, config, fake_grouper, make_archive, run

DAY = "2026-07-15_(Wed)__08.14.00 - Trip"
STILL = "2026-07-15_(Wed)__08.14.00__f1.7__SG23U.jpg"
CLIP = STILL + ".MOTION.mp4"

# The smallest thing that opens like an MP4: an "ftyp" box and a "free" box.
MP4 = struct.pack(">I", 24) + b"ftypisom" + b"\x00\x00\x02\x00" + b"isommp41" \
    + struct.pack(">I", 8) + b"free"
JPEG_SOI, JPEG_EOI = b"\xff\xd8", b"\xff\xd9"


def xmp_segment(xmp: str) -> bytes:
    """A JPEG APP1 segment carrying ``xmp`` the way every camera writes it."""
    payload = b"http://ns.adobe.com/xap/1.0/\x00" + xmp.encode("utf-8")
    return b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload


# A real (1x1 pixel) baseline JPEG body -- everything after its SOI -- so
# ExifTool reads the file as the JPEG it claims to be.
TINY_JPEG_BODY = bytes.fromhex(
    "ffe000104a46494600010100000100010000ffdb004300080606070605080707070909"
    "080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c231c1c283729"
    "2c30313434341f27393d38323c2e333432ffc0000b080001000101011100ffc4001f00"
    "00010501010101010100000000000000000102030405060708090a0bffc400b5100002"
    "010303020403050504040000017d01020300041105122131410613516107227114328"
    "191a1082342b1c11552d1f02433627282090a161718191a25262728292a3435363738"
    "393a434445464748494a535455565758595a636465666768696a737475767778797a83"
    "8485868788898a92939495969798999aa2a3a4a5a6a7a8a9aab2b3b4b5b6b7b8b9bac2"
    "c3c4c5c6c7c8c9cad2d3d4d5d6d7d8d9dae1e2e3e4e5e6e7e8e9eaf1f2f3f4f5f6f7f8"
    "f9faffda0008010100003f00fbd3ffd9")


def micro_video_photo(path: Path, clip: bytes = MP4) -> Path:
    """An older Google motion photo: XMP says how far from the end the clip is."""
    xmp = ('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF '
           'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
           '<rdf:Description rdf:about="" '
           'xmlns:GCamera="http://ns.google.com/photos/1.0/camera/" '
           'GCamera:MicroVideo="1" GCamera:MicroVideoVersion="1" '
           f'GCamera:MicroVideoOffset="{len(clip)}"/>'
           '</rdf:RDF></x:xmpmeta>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(JPEG_SOI + xmp_segment(xmp) + TINY_JPEG_BODY + clip)
    return path


def plain_jpeg(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(JPEG_SOI + TINY_JPEG_BODY)
    return path


def samsung_tail_jpeg(path: Path) -> Path:
    """Only the Samsung trailer footer -- no XMP to say what it holds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(JPEG_SOI + TINY_JPEG_BODY + b"\x00" * 16 + b"SEFT")
    return path


class FakeExifTool:
    """Stands in for ExifTool: reads the argfile, answers like the real one.

    ``videos`` maps a still's name to the tag that holds its clip and the bytes
    to write for it. A probe prints what matches; ``-b -TAG -w FMT`` writes
    the clip where the format says, and never over an existing file.
    """

    def __init__(self, videos=None):
        self.videos = videos or {}
        self.commands = []

    def __call__(self, command):
        self.commands.append(command)
        argfile = Path(command[command.index("-@") + 1])
        paths = [Path(line) for line in argfile.read_text(encoding="utf-8").splitlines()]
        stdout = []
        if "-w" in command:
            tag = command[command.index("-b") + 1].lstrip("-")
            pattern = command[command.index("-w") + 1]
            for path in paths:
                held = self.videos.get(path.name)
                if held is None or held[0] != tag:
                    continue
                target = Path(pattern.replace("%d", str(path.parent) + "/")
                              .replace("%f", path.stem).replace("%e", path.suffix[1:]))
                if not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(held[1])
        elif "-p" in command and "|" not in command[command.index("-p") + 1]:
            stdout = [path.as_posix() for path in paths if path.name in self.videos]
        return type("Result", (), {"stdout": "\n".join(stdout).encode("utf-8")})()

    def probed(self):
        return [command for command in self.commands if "-w" not in command]


@pytest.fixture
def cfg():
    return {"extensions": {"lossy_images": [".jpg", ".jpeg"],
                           "other_images": [".heic"],
                           "videos": [".mp4", ".mov"],
                           "sidecars": ["._exif"]}}


# --------------------------------------------------------------------------
# Naming, recognition, and never counting as media
# --------------------------------------------------------------------------

def test_the_extraction_is_named_after_the_still_one_level_below_it(tmp_path, cfg):
    still = tmp_path / DAY / STILL
    assert ev.extracted_video_path(still, cfg) == \
        tmp_path / DAY / "__VIDEOS_EXTRACTED" / CLIP


def test_only_a_still_can_carry_one(cfg):
    assert ev.is_carrier(STILL, cfg)
    assert ev.is_carrier("shot.HEIC", cfg)
    assert not ev.is_carrier(CLIP, cfg)
    assert not ev.is_carrier("clip.mp4", cfg)
    assert not ev.is_carrier("shot.CR2", cfg)


def test_an_extracted_video_is_never_media():
    names = [STILL, CLIP, "2026-07-15_(Wed)__09.00.00.mp4"]
    assert count_media(names, {".jpg"}, {".mp4"}) == (1, 1)
    assert CLIP not in select_media(names, {".jpg"}, {".mp4"})


def test_sniffing_rules_out_only_what_shows_no_sign(tmp_path):
    assert ev.sniff(micro_video_photo(tmp_path / "a.jpg")) is True
    assert ev.sniff(samsung_tail_jpeg(tmp_path / "b.jpg")) is True
    assert ev.sniff(plain_jpeg(tmp_path / "c.jpg")) is False
    heic = tmp_path / "d.heic"
    heic.write_bytes(b"anything")
    assert ev.sniff(heic) is None            # not sniffable: ExifTool decides


# --------------------------------------------------------------------------
# Finding the ones still to extract
# --------------------------------------------------------------------------

def test_exiftool_is_asked_only_about_what_sniffing_could_not_rule_out(tmp_path, cfg):
    motion = micro_video_photo(tmp_path / DAY / STILL)
    plain = plain_jpeg(tmp_path / DAY / "2026-07-15_(Wed)__08.15.00.jpg")
    exiftool = FakeExifTool({motion.name: ("MotionPhotoVideo", MP4)})

    found = ev.find_pending([motion, plain], cfg, runner=exiftool)

    assert found.pending == [motion]
    assert (found.examined, found.probed) == (2, 1)
    argfile_paths = exiftool.probed()
    assert len(argfile_paths) == 1


def test_a_still_already_extracted_is_not_pending(tmp_path, cfg):
    motion = micro_video_photo(tmp_path / DAY / STILL)
    clip = ev.extracted_video_path(motion, cfg)
    clip.parent.mkdir()
    clip.write_bytes(MP4)
    exiftool = FakeExifTool({motion.name: ("MotionPhotoVideo", MP4)})

    found = ev.find_pending([motion], cfg, runner=exiftool)

    assert found.pending == [] and found.already_extracted == 1
    assert exiftool.commands == []


# --------------------------------------------------------------------------
# Extracting
# --------------------------------------------------------------------------

def test_samsungs_block_is_preferred_and_lands_in_videos_extracted(tmp_path, cfg):
    still = samsung_tail_jpeg(tmp_path / DAY / STILL)
    exiftool = FakeExifTool({still.name: ("EmbeddedVideoFile", MP4)})

    result = ev.extract([still], cfg, runner=exiftool)

    clip = tmp_path / DAY / "__VIDEOS_EXTRACTED" / CLIP
    assert result.created == [(still, clip)]
    assert clip.read_bytes() == MP4
    first = exiftool.commands[0]
    assert first[first.index("-b") + 1] == "-EmbeddedVideoFile"
    assert first[first.index("-w") + 1] == "%d__VIDEOS_EXTRACTED/%f.%e.MOTION.mp4"
    # Once it is extracted, no later tag is tried for it.
    assert len(exiftool.commands) == 1


def test_google_motion_photo_video_is_the_fallback(tmp_path, cfg):
    still = samsung_tail_jpeg(tmp_path / DAY / STILL)
    exiftool = FakeExifTool({still.name: ("MotionPhotoVideo", MP4)})

    result = ev.extract([still], cfg, runner=exiftool)

    assert [clip.name for _still, clip in result.created] == [CLIP]


def test_an_existing_extraction_is_never_replaced_or_reported_as_new(tmp_path, cfg):
    still = samsung_tail_jpeg(tmp_path / DAY / STILL)
    clip = ev.extracted_video_path(still, cfg)
    clip.parent.mkdir()
    clip.write_bytes(b"somebody else's")

    result = ev.extract([still], cfg, runner=FakeExifTool({still.name: ("EmbeddedVideoFile", MP4)}))

    assert clip.read_bytes() == b"somebody else's"
    assert result.requested == 0 and result.created == []


def test_an_extraction_that_is_not_a_video_is_kept_and_reported(tmp_path, cfg):
    still = samsung_tail_jpeg(tmp_path / DAY / STILL)
    exiftool = FakeExifTool({still.name: ("EmbeddedVideoFile", b"not a video at all")})

    result = ev.extract([still], cfg, runner=exiftool)

    clip = ev.extracted_video_path(still, cfg)
    assert result.created == [] and result.not_video == [(still, clip)]
    assert clip.is_file()                    # T1: kept, for a person to judge


@pytest.mark.skipif(not bundled_exiftool(project_root()).is_file(),
                    reason="the bundled ExifTool is not in this checkout")
def test_real_exiftool_finds_and_extracts_a_micro_video(tmp_path, cfg):
    """End to end, with the ExifTool this project ships -- and a Polish name,
    which only survives the trip through an argfile read as UTF-8."""
    exiftool = str(bundled_exiftool(project_root()))
    still = micro_video_photo(tmp_path / "2026-07-15_(Wed)__08.14.00 - Zażółć" / STILL)
    plain = plain_jpeg(still.parent / "2026-07-15_(Wed)__08.15.00.jpg")

    found = ev.find_pending([still, plain], cfg, exiftool)
    assert found.pending == [still]

    result = ev.extract(found.pending, cfg, exiftool)

    clip = still.parent / "__VIDEOS_EXTRACTED" / CLIP
    assert result.created == [(still, clip)]
    assert clip.read_bytes() == MP4
    assert still.read_bytes().endswith(MP4)  # the still is never rewritten
    assert ev.find_pending([still], cfg, exiftool).pending == []


# --------------------------------------------------------------------------
# It travels with its still
# --------------------------------------------------------------------------

def test_placement_brings_a_stranded_extraction_home(tmp_path, cfg):
    month = tmp_path / "2026" / "07. July"
    home = month / DAY
    (home / STILL).parent.mkdir(parents=True)
    (home / STILL).write_bytes(b"still")
    elsewhere = month / "2026-07-16_(Thu)__10.00.00" / "__VIDEOS_EXTRACTED" / CLIP
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(MP4)

    report = place_companions([tmp_path / "2026"], cfg,
                              lambda folder: folder / "__DUPLICATES")

    assert (home / "__VIDEOS_EXTRACTED" / CLIP).read_bytes() == MP4
    assert not elsewhere.exists()
    assert report.moved == 1 and report.orphaned == 0
    # An extraction is a companion, not media wanting a sidecar of its own.
    assert report.media == 1


def test_reconciliation_carries_it_after_a_still_the_grouper_moved(tmp_path):
    month = tmp_path / "2026" / "07. July"
    event = month / DAY
    clip = event / "__VIDEOS_EXTRACTED" / CLIP
    clip.parent.mkdir(parents=True)
    clip.write_bytes(MP4)
    sub_event = month / "2026-07-15_(Wed)__08.14.00 - Breakfast"
    sub_event.mkdir()
    (sub_event / STILL).write_bytes(b"still")   # the grouper moved only this

    report = reconcile_folder(event, {})

    assert report.moved == 1
    assert (sub_event / "__VIDEOS_EXTRACTED" / CLIP).read_bytes() == MP4


# --------------------------------------------------------------------------
# The pipeline stage
# --------------------------------------------------------------------------

def test_the_stage_extracts_what_folder_sorting_filed(tmp_path, cfg, monkeypatch):
    still = samsung_tail_jpeg(tmp_path / DAY / STILL)
    plain = plain_jpeg(tmp_path / DAY / "2026-07-15_(Wed)__08.15.00.jpg")
    exiftool = FakeExifTool({still.name: ("EmbeddedVideoFile", MP4)})
    monkeypatch.setattr(ev, "_default_runner", exiftool)
    context = PipelineContext(config=cfg)
    context.assets = [MediaAsset(still), MediaAsset(plain)]

    EmbeddedVideoExtractionStage().execute(context)

    assert (tmp_path / DAY / "__VIDEOS_EXTRACTED" / CLIP).read_bytes() == MP4
    assert context.counters["embedded_videos_extracted"] == 1
    assert context.counters["embedded_video_errors"] == 0


def test_the_stage_can_be_switched_off(tmp_path, cfg, monkeypatch):
    still = samsung_tail_jpeg(tmp_path / DAY / STILL)
    monkeypatch.setattr(ev, "_default_runner",
                        lambda *_: pytest.fail("disabled must not run ExifTool"))
    cfg["embedded_video_extraction"] = {"enabled": False}
    context = PipelineContext(config=cfg)
    context.assets = [MediaAsset(still)]

    EmbeddedVideoExtractionStage().execute(context)

    assert not (tmp_path / DAY / "__VIDEOS_EXTRACTED").exists()


def test_the_stage_runs_after_folder_sorting_and_before_the_grouper():
    order = [stage.stage_id for stage in src.pipeline_stages.build_default_stages()]
    here = order.index("embedded-video-extraction")
    assert order.index("folder-sorting") < here < order.index("screenshot-grouping")


# --------------------------------------------------------------------------
# The restructure tool: pass 7 of reconciliation, and step 7's X16
# --------------------------------------------------------------------------

def archive_with_motion_photo(tmp_path):
    root = make_archive(tmp_path)
    still = samsung_tail_jpeg(root / "2026" / "07. July" / DAY / STILL)
    return root, still


def fake_restructure_exiftool(monkeypatch, still):
    exiftool = FakeExifTool({still.name: ("EmbeddedVideoFile", MP4)})
    monkeypatch.setattr(tool.embedded_videos, "_default_runner", exiftool)
    return exiftool


def test_a_dry_run_lists_the_motion_photos_and_extracts_nothing(
        tmp_path, config, monkeypatch, capsys):
    root, still = archive_with_motion_photo(tmp_path)
    exiftool = fake_restructure_exiftool(monkeypatch, still)

    assert run(str(root), "--steps", "2") == 1

    assert not (still.parent / "__VIDEOS_EXTRACTED").exists()
    assert all("-w" not in command for command in exiftool.commands)
    out = capsys.readouterr().out
    assert "1 carry a video not yet extracted" in out
    assert "1 embedded video(s) to extract" in out


def test_apply_extracts_and_a_second_run_finds_nothing_left(
        tmp_path, config, monkeypatch, capsys):
    root, still = archive_with_motion_photo(tmp_path)
    fake_restructure_exiftool(monkeypatch, still)

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0

    assert (still.parent / "__VIDEOS_EXTRACTED" / CLIP).read_bytes() == MP4
    assert "Extracted 1/1 embedded video(s)" in capsys.readouterr().out
    assert run(str(root), "--steps", "2") == 0


def test_step_7_reports_an_unextracted_motion_photo_as_x16(
        tmp_path, config, monkeypatch, capsys):
    root, still = archive_with_motion_photo(tmp_path)
    fake_restructure_exiftool(monkeypatch, still)

    assert run(str(root), "--steps", "7") == 1
    out = capsys.readouterr().out
    assert "X16" in out and still.name in out

    assert run(str(root), "--steps", "2", "--apply", "--yes") == 0
    capsys.readouterr()
    run(str(root), "--steps", "7")
    assert "X16" not in capsys.readouterr().out


def test_a_misplaced_extraction_is_reported_by_step_7_as_x10(
        tmp_path, config, monkeypatch, capsys):
    root, still = archive_with_motion_photo(tmp_path)
    fake_restructure_exiftool(monkeypatch, still)
    stray = still.parent / "__EXIF" / CLIP
    stray.parent.mkdir()
    stray.write_bytes(MP4)

    run(str(root), "--steps", "7")

    out = capsys.readouterr().out
    assert "X10" in out and "__VIDEOS_EXTRACTED" in out
