"""The pre-"__" containers the legacy CLI wrote, migrated to their modern names.

``##   EXIFs   ##`` becomes ``__EXIF`` and ``##   RAWs   ##`` becomes ``__RAW``.
Either by renaming the container outright, when nothing of that name is there
yet, or by moving files across one at a time when it is — and settling a name
collision by checksum, exactly as companion placement settles one.

A container left absolutely empty is parked in the sibling
``__EMPTY_SUBFOLDERS``, numbered when that name is taken. One still holding
anything is left where it is: a folder that would not empty is a question, not
a job.
"""

import hashlib
from pathlib import Path

from src.pipeline_stages.companion_matching import (
    migrate_legacy_containers,
    survey_trees,
)

LEGACY_EXIF = "##   EXIFs   ##"
LEGACY_RAW = "##   RAWs   ##"
STEM = "2026-07-18_(Sat)__17.04.53"
JPG = f"{STEM}__f8.0__6D.jpg"
RAW = f"{STEM}__RAW__f8.0__6D.CR2"


def make_config():
    return {
        "taxonomy": {"raw": "__RAW", "exif": "__EXIF"},
        "extensions": {"sidecars": ["._exif"], "previews": [".thm"],
                       "lossy_images": [".jpg"], "raw_images": [".cr2"]},
        "legacy": {"subfolders": {"exif": LEGACY_EXIF, "raw": LEGACY_RAW}},
    }


def build_year(tmp_path):
    year = tmp_path / "2026"
    day = year / "07. July" / f"{STEM} - Lens tests"
    day.mkdir(parents=True)
    (day / JPG).write_bytes(b"jpg")
    return year, day


def migrate(year, config, log=None):
    """Survey the tree, then migrate what the survey named."""
    parking = year / "__DUPLICATES"
    survey = survey_trees([year], config, log or (lambda _m: None))
    return migrate_legacy_containers(
        survey.legacy_containers, config, lambda _folder: parking,
        log or (lambda _m: None))


def parked_duplicates(year):
    folder = year / "__DUPLICATES"
    return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []


def digest(payload):
    return hashlib.md5(payload).hexdigest()[:8]


# --------------------------------------------------------------------------
# Renaming, when the modern folder is not there yet
# --------------------------------------------------------------------------

def test_a_legacy_container_is_renamed_when_nothing_holds_the_new_name(tmp_path):
    year, day = build_year(tmp_path)
    (day / LEGACY_RAW).mkdir()
    (day / LEGACY_RAW / RAW).write_bytes(b"raw")

    report = migrate(year, make_config())

    assert report.renamed == 1
    assert (day / "__RAW" / RAW).is_file()
    assert not (day / LEGACY_RAW).exists()


def test_renaming_keeps_everything_beneath_it(tmp_path):
    year, day = build_year(tmp_path)
    (day / LEGACY_RAW / "__EXIF").mkdir(parents=True)
    (day / LEGACY_RAW / RAW).write_bytes(b"raw")
    (day / LEGACY_RAW / "__EXIF" / f"{RAW}._exif").write_bytes(b"e")

    migrate(year, make_config())

    assert (day / "__RAW" / RAW).is_file()
    assert (day / "__RAW" / "__EXIF" / f"{RAW}._exif").is_file()


def test_both_containers_migrate_in_one_pass(tmp_path):
    year, day = build_year(tmp_path)
    (day / LEGACY_RAW).mkdir()
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_RAW / RAW).write_bytes(b"raw")
    (day / LEGACY_EXIF / f"{JPG}._exif").write_bytes(b"e")

    report = migrate(year, make_config())

    assert report.renamed == 2
    assert (day / "__RAW" / RAW).is_file()
    assert (day / "__EXIF" / f"{JPG}._exif").is_file()


# --------------------------------------------------------------------------
# Merging, when the modern folder already exists
# --------------------------------------------------------------------------

def test_files_move_across_when_the_modern_folder_exists(tmp_path):
    year, day = build_year(tmp_path)
    (day / "__EXIF").mkdir()
    (day / "__EXIF" / f"{JPG}._exif").write_bytes(b"e")
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_EXIF / f"{RAW}._exif").write_bytes(b"other")

    report = migrate(year, make_config())

    assert report.merged == 1
    assert report.files_moved == 1
    assert (day / "__EXIF" / f"{RAW}._exif").read_bytes() == b"other"
    assert (day / "__EXIF" / f"{JPG}._exif").read_bytes() == b"e"


def test_an_identical_file_is_parked_as_a_duplicate(tmp_path):
    year, day = build_year(tmp_path)
    (day / "__EXIF").mkdir()
    (day / "__EXIF" / f"{JPG}._exif").write_bytes(b"e")
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_EXIF / f"{JPG}._exif").write_bytes(b"e")     # same bytes

    report = migrate(year, make_config())

    assert report.files_moved == 1
    assert (day / "__EXIF" / f"{JPG}._exif").read_bytes() == b"e"
    assert parked_duplicates(year) == [f"{JPG}_DUPE_{digest(b'e')}_1._exif"]


def test_a_differing_file_is_parked_and_flagged(tmp_path):
    year, day = build_year(tmp_path)
    (day / "__EXIF").mkdir()
    (day / "__EXIF" / f"{JPG}._exif").write_bytes(b"the one already there")
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_EXIF / f"{JPG}._exif").write_bytes(b"a different one")
    logs = []

    migrate(year, make_config(), logs.append)

    # Neither is overwritten and neither is lost (T1, T2).
    assert (day / "__EXIF" / f"{JPG}._exif").read_bytes() == b"the one already there"
    assert parked_duplicates(year) == [
        f"{JPG}_DIFFERS_{digest(b'a different one')}_1._exif"]
    assert any("DIFFERENT from" in line for line in logs)


# --------------------------------------------------------------------------
# Parking the emptied container
# --------------------------------------------------------------------------

def test_an_emptied_container_is_parked(tmp_path):
    year, day = build_year(tmp_path)
    (day / "__EXIF").mkdir()
    (day / "__EXIF" / f"{JPG}._exif").write_bytes(b"e")
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_EXIF / f"{RAW}._exif").write_bytes(b"other")

    report = migrate(year, make_config())

    assert report.parked == 1
    assert (day.parent / "__EMPTY_SUBFOLDERS" / LEGACY_EXIF).is_dir()
    assert not (day / LEGACY_EXIF).exists()


def test_a_second_parking_of_one_name_is_numbered(tmp_path):
    """Recursively versioned: the discriminator N10a already uses."""
    year, day = build_year(tmp_path)
    (day.parent / "__EMPTY_SUBFOLDERS" / LEGACY_EXIF).mkdir(parents=True)
    (day / "__EXIF").mkdir()
    (day / "__EXIF" / f"{JPG}._exif").write_bytes(b"e")
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_EXIF / f"{RAW}._exif").write_bytes(b"other")

    migrate(year, make_config())

    assert (day.parent / "__EMPTY_SUBFOLDERS" / f"{LEGACY_EXIF}_2").is_dir()


def test_a_container_that_would_not_empty_is_left_alone(tmp_path):
    """A file that could not move keeps its container where it is."""
    year, day = build_year(tmp_path)
    (day / "__EXIF").mkdir()
    (day / LEGACY_EXIF).mkdir()
    (day / LEGACY_EXIF / f"{RAW}._exif").write_bytes(b"other")
    logs = []

    def refuse(source, target):
        raise OSError("locked")

    survey = survey_trees([year], make_config(), logs.append)
    report = migrate_legacy_containers(
        survey.legacy_containers, make_config(),
        lambda _folder: year / "__DUPLICATES", logs.append, move=refuse)

    assert report.errors
    assert (day / LEGACY_EXIF / f"{RAW}._exif").is_file()
    assert not (day.parent / "__EMPTY_SUBFOLDERS").exists()
    assert any("still holds files" in line for line in logs)


# --------------------------------------------------------------------------
# The containers with no modern equivalent
# --------------------------------------------------------------------------

def test_an_unmapped_container_is_reported_and_never_touched(tmp_path):
    year, day = build_year(tmp_path)
    unsupported = day / "##   UNSUPPORTED EXTENSIONS   ##"
    unsupported.mkdir()
    (unsupported / "weird.xyz").write_bytes(b"x")
    logs = []

    report = migrate(year, make_config(), logs.append)

    assert report.left == 1
    assert (unsupported / "weird.xyz").is_file()
    assert any("no modern folder corresponds" in line for line in logs)


def test_a_dry_run_migrates_nothing(tmp_path):
    year, day = build_year(tmp_path)
    (day / LEGACY_RAW).mkdir()
    (day / LEGACY_RAW / RAW).write_bytes(b"raw")
    planned = []

    survey = survey_trees([year], make_config())
    report = migrate_legacy_containers(
        survey.legacy_containers, make_config(),
        lambda _folder: year / "__DUPLICATES",
        move=lambda source, target: planned.append((Path(source), Path(target))))

    assert report.renamed == 1
    assert planned == [(day / LEGACY_RAW, day / "__RAW")]
    assert (day / LEGACY_RAW / RAW).is_file()      # nothing actually moved
    assert not (day / "__RAW").exists()
