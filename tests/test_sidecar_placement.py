"""X10/X13: a companion belongs in the folder directly inside its subject's.

Two kinds, one rule. An ``._exif`` sidecar goes in ``__EXIF``; a ``.thm`` or
``.lrv`` preview goes in ``__PREVIEWS`` (X6, X13). Both sit one level below the
file they describe, wherever that file has ended up.

For sidecars this is a migration: everything that *writes* the archive already
honours X10, so what is left over is the ones written before it, sitting one
level too high in the dated folder's own ``__EXIF``. For previews it is the
first routing they have ever had — nothing has moved a ``.thm`` anywhere, so
they are still lying beside their subject exactly as the camera wrote them, in
camera form rather than X1.

Finding the subject is a name lookup rather than a stamp match (X1), which is
what makes it exact where ``reconcile_folder`` can only be careful.
"""

import hashlib
from pathlib import Path

import pytest

from src.pipeline_stages.companion_matching import place_companions
from src.pipeline_stages.grouping_names import sidecar_subject_name


def relocate_sidecars(root, config, log=lambda _m: None, move=None,
                      checksum=None, prune=True):
    """place_companions over one dated folder, parking beside it.

    Every test here works on a single dated folder, so it is passed as the one
    root and collision losers land in a "__DUPLICATES" beside it rather than
    under a year.
    """
    parking = Path(root).parent / "__DUPLICATES"
    return place_companions([root], config, lambda _folder: parking,
                            log, move=move, checksum=checksum, prune=prune)

STEM = "2026-07-18_(Sat)__17.04.53"
JPG = f"{STEM}__f8.0__6D.jpg"
RAW = f"{STEM}__RAW__f8.0__6D.CR2"


def make_config():
    return {
        "taxonomy": {"raw": "__RAW", "exif": "__EXIF", "edited": "__EDITED",
                     "previews": "__PREVIEWS"},
        "extensions": {"sidecars": ["._exif"], "previews": [".thm", ".lrv"]},
    }


def build_day(tmp_path, *, raw_sidecar_where="__EXIF"):
    """A day with a still at the top level and a RAW in ``__RAW``.

    ``raw_sidecar_where`` is where the RAW's sidecar starts out: "__EXIF" is
    the pre-X10 arrangement this migrates, "__RAW/__EXIF" is already correct.
    """
    day = tmp_path / "2026" / "07. July" / f"{STEM} - Lens tests"
    (day / "__RAW").mkdir(parents=True)
    (day / "__EXIF").mkdir(parents=True)
    (day / JPG).write_bytes(b"jpg")
    (day / "__RAW" / RAW).write_bytes(b"raw")
    (day / "__EXIF" / f"{JPG}._exif").write_bytes(b"exif")
    sidecar_dir = day.joinpath(*raw_sidecar_where.split("/"))
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    (sidecar_dir / f"{RAW}._exif").write_bytes(b"exif")
    return day


# --------------------------------------------------------------------------
# Naming a subject (X1)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("shot.jpg._exif", "shot.jpg"),
    ("clip.mp4._exif", "clip.mp4"),
    # X1 keeps the subject's FULL name, so the media extension is still there.
    (f"{RAW}._exif", RAW),
    # Not a sidecar.
    ("shot.jpg", None),
    ("shot.mp4", None),
    # Nothing but the extension is not a sidecar of anything.
    ("._exif", None),
])
def test_sidecar_subject_name(name, expected):
    assert sidecar_subject_name(name, {"._exif"}) == expected


def test_sidecar_subject_name_is_case_insensitive_on_the_extension():
    assert sidecar_subject_name("shot.JPG._EXIF", {"._exif"}) == "shot.JPG"


# --------------------------------------------------------------------------
# Placement
# --------------------------------------------------------------------------

def test_a_raws_sidecar_moves_down_into_raw_exif(tmp_path):
    day = build_day(tmp_path)
    report = relocate_sidecars(day, make_config())
    assert report.moved == 1
    assert (day / "__RAW" / "__EXIF" / f"{RAW}._exif").is_file()
    assert not (day / "__EXIF" / f"{RAW}._exif").exists()


def test_a_top_level_stills_sidecar_stays_in_the_folders_own_exif(tmp_path):
    day = build_day(tmp_path)
    relocate_sidecars(day, make_config())
    # The subject is at the top level, so the dated folder's own __EXIF is
    # already "directly inside the folder holding its subject".
    assert (day / "__EXIF" / f"{JPG}._exif").is_file()


def test_a_sidecar_already_in_place_is_not_moved(tmp_path):
    day = build_day(tmp_path, raw_sidecar_where="__RAW/__EXIF")
    report = relocate_sidecars(day, make_config())
    assert report.moved == 0
    assert report.in_place == 2
    assert (day / "__RAW" / "__EXIF" / f"{RAW}._exif").is_file()


def test_running_twice_changes_nothing_the_second_time(tmp_path):
    day = build_day(tmp_path)
    first = relocate_sidecars(day, make_config())
    second = relocate_sidecars(day, make_config())
    assert first.moved == 1
    assert second.moved == 0
    assert second.in_place == 2


def test_an_orphaned_sidecar_is_left_exactly_where_it_is(tmp_path):
    """X3: it is the only surviving record that the subject existed."""
    day = build_day(tmp_path)
    orphan = day / "__EXIF" / f"{STEM}__gone__f2.8__6D.jpg._exif"
    orphan.write_bytes(b"exif")
    logs = []
    report = relocate_sidecars(day, make_config(), logs.append)
    assert report.orphaned == 1
    assert orphan.is_file()
    assert any("nowhere in the tree" in line for line in logs)


# --------------------------------------------------------------------------
# Something already holds the destination name — compare by MD5
# --------------------------------------------------------------------------

def parked(day):
    folder = day.parent / "__DUPLICATES"
    return sorted(path.name for path in folder.iterdir()) if folder.is_dir() else []


def digest(payload):
    """The first 8 hex of the MD5, which is what F4 puts in the name."""
    return hashlib.md5(payload).hexdigest()[:8]


def test_an_identical_sidecar_is_parked_as_a_duplicate(tmp_path):
    day = build_day(tmp_path)
    (day / "__RAW" / "__EXIF").mkdir(parents=True)
    existing = day / "__RAW" / "__EXIF" / f"{RAW}._exif"
    existing.write_bytes(b"exif")               # byte-identical to the incoming
    report = relocate_sidecars(day, make_config())
    assert report.parked_duplicate == 1
    assert report.parked_differing == 0
    assert existing.read_bytes() == b"exif"     # the one in place is untouched
    assert not (day / "__EXIF" / f"{RAW}._exif").exists()
    assert parked(day) == [f"{RAW}_DUPE_{digest(b'exif')}_1._exif"]


def test_a_differing_sidecar_is_parked_and_flagged(tmp_path):
    day = build_day(tmp_path)
    (day / "__RAW" / "__EXIF").mkdir(parents=True)
    existing = day / "__RAW" / "__EXIF" / f"{RAW}._exif"
    existing.write_bytes(b"a completely different sidecar")
    logs = []
    report = relocate_sidecars(day, make_config(), logs.append)
    assert report.parked_differing == 1
    assert report.parked_duplicate == 0
    # Neither file is lost and neither is overwritten (T1, T2).
    assert existing.read_bytes() == b"a completely different sidecar"
    assert parked(day) == [f"{RAW}_DIFFERS_{digest(b'exif')}_1._exif"]
    assert any("DIFFERENT bytes" in line for line in logs)


def test_two_losers_of_one_name_are_both_parked(tmp_path):
    """Numbered, not overwritten: both belong in the report."""
    day = build_day(tmp_path)
    (day / "__RAW" / "__EXIF").mkdir(parents=True)
    (day / "__RAW" / "__EXIF" / f"{RAW}._exif").write_bytes(b"exif")
    # A second copy of the same sidecar, stranded somewhere else in the tree.
    elsewhere = day / "__EDITED"
    elsewhere.mkdir()
    (elsewhere / f"{RAW}._exif").write_bytes(b"exif")
    report = relocate_sidecars(day, make_config())
    assert report.parked_duplicate == 2
    assert parked(day) == [f"{RAW}_DUPE_{digest(b'exif')}_1._exif",
                           f"{RAW}_DUPE_{digest(b'exif')}_2._exif"]


def test_a_dry_run_parks_nothing(tmp_path):
    day = build_day(tmp_path)
    (day / "__RAW" / "__EXIF").mkdir(parents=True)
    (day / "__RAW" / "__EXIF" / f"{RAW}._exif").write_bytes(b"different")
    planned = []
    report = relocate_sidecars(
        day, make_config(),
        move=lambda s, t: planned.append((Path(s), Path(t))), prune=False)
    assert report.parked_differing == 1
    assert len(planned) == 1
    assert parked(day) == []
    assert (day / "__EXIF" / f"{RAW}._exif").is_file()


def test_a_sidecar_follows_its_subject_into_any_media_subfolder(tmp_path):
    """X10 is universal, not a __RAW special case."""
    day = build_day(tmp_path, raw_sidecar_where="__RAW/__EXIF")
    edited_name = f"{STEM}__f8.0__6D.psd"
    (day / "__EDITED").mkdir()
    (day / "__EDITED" / edited_name).write_bytes(b"psd")
    (day / "__EXIF" / f"{edited_name}._exif").write_bytes(b"exif")
    report = relocate_sidecars(day, make_config())
    assert report.moved == 1
    assert (day / "__EDITED" / "__EXIF" / f"{edited_name}._exif").is_file()


def test_a_dry_run_writes_nothing(tmp_path):
    day = build_day(tmp_path)
    planned = []

    def record(source, target):
        planned.append((Path(source), Path(target)))
        return Path(target)

    report = relocate_sidecars(day, make_config(), move=record, prune=False)
    assert report.moved == 1
    assert len(planned) == 1
    # Nothing on disk moved, and no destination folder was created.
    assert (day / "__EXIF" / f"{RAW}._exif").is_file()
    assert not (day / "__RAW" / "__EXIF").exists()


def test_an_archive_that_keeps_no_sidecars_is_left_alone(tmp_path):
    day = build_day(tmp_path)
    config = make_config()
    config["extensions"]["sidecars"] = []
    report = relocate_sidecars(day, config)
    assert report.seen == 0
    assert (day / "__EXIF" / f"{RAW}._exif").is_file()


def test_a_vanished_folder_is_an_error_not_a_crash(tmp_path):
    report = relocate_sidecars(tmp_path / "nowhere", make_config())
    assert report.errors == 1


def test_no_media_file_is_ever_moved(tmp_path):
    """The pass places sidecars; everything else stays exactly where it is."""
    day = build_day(tmp_path)
    relocate_sidecars(day, make_config())
    assert (day / JPG).is_file()
    assert (day / "__RAW" / RAW).is_file()


# --------------------------------------------------------------------------
# Previews (X6, X13) — .thm and .lrv into __PREVIEWS
# --------------------------------------------------------------------------

CLIP = f"{STEM}__f2.8__GP.mp4"


def build_video_day(tmp_path):
    """A video at the top level of a dated folder, previews beside it."""
    day = tmp_path / "2026" / "07. July" / f"{STEM} - Dive"
    day.mkdir(parents=True)
    (day / CLIP).write_bytes(b"mp4")
    return day


def test_a_camera_form_preview_is_routed_and_renamed_onto_x1(tmp_path):
    """"GX010042.LRV" beside "GX010042.MP4" — what a camera actually writes."""
    day = build_video_day(tmp_path)
    (day / f"{Path(CLIP).stem}.LRV").write_bytes(b"proxy")
    report = relocate_sidecars(day, make_config())
    assert report.moved == 1
    assert report.renamed == 1
    # X13: __PREVIEWS directly inside the folder holding the subject.
    # X6/X1: the subject's FULL name with the preview extension appended.
    assert (day / "__PREVIEWS" / f"{CLIP}.lrv").is_file()
    assert not (day / f"{Path(CLIP).stem}.LRV").exists()


def test_an_x1_form_preview_is_routed_without_renaming(tmp_path):
    day = build_video_day(tmp_path)
    (day / f"{CLIP}.thm").write_bytes(b"thumb")
    report = relocate_sidecars(day, make_config())
    assert report.moved == 1
    assert report.renamed == 0
    assert (day / "__PREVIEWS" / f"{CLIP}.thm").is_file()


def test_several_previews_of_one_subject_all_land(tmp_path):
    """X9: distinguished by their own extensions, subject name never mangled."""
    day = build_video_day(tmp_path)
    (day / f"{Path(CLIP).stem}.THM").write_bytes(b"thumb")
    (day / f"{Path(CLIP).stem}.LRV").write_bytes(b"proxy")
    report = relocate_sidecars(day, make_config())
    assert report.moved == 2
    assert (day / "__PREVIEWS" / f"{CLIP}.thm").is_file()
    assert (day / "__PREVIEWS" / f"{CLIP}.lrv").is_file()


def test_a_preview_follows_its_subject_into_a_subfolder(tmp_path):
    """X13 follows X10: one level below the subject, wherever the subject is."""
    day = build_video_day(tmp_path)
    parked = day / "__VIDEOS_TO_RENAME"
    parked.mkdir()
    clip = parked / "2026-07-18_(Sat)__17.04.53__TO_RENAME__DSC001.mp4"
    clip.write_bytes(b"mp4")
    (day / f"{clip.name}.thm").write_bytes(b"thumb")
    config = make_config()
    config["taxonomy"]["videos_to_rename"] = "__VIDEOS_TO_RENAME"
    report = relocate_sidecars(day, config)
    assert report.moved == 1
    assert (parked / "__PREVIEWS" / f"{clip.name}.thm").is_file()


def test_an_ambiguous_stem_is_left_alone(tmp_path):
    """Two subjects share the stem, so which one it describes is unknowable."""
    day = build_video_day(tmp_path)
    stem = Path(CLIP).stem
    (day / f"{stem}.jpg").write_bytes(b"jpg")      # same stem, different media
    preview = day / f"{stem}.THM"
    preview.write_bytes(b"thumb")
    logs = []
    report = relocate_sidecars(day, make_config(), logs.append)
    assert report.ambiguous == 1
    assert report.moved == 0
    assert preview.is_file()
    assert any("not knowable" in line for line in logs)


def test_an_orphaned_preview_is_left_alone(tmp_path):
    day = build_video_day(tmp_path)
    orphan = day / "GX999999.LRV"
    orphan.write_bytes(b"proxy")
    report = relocate_sidecars(day, make_config())
    assert report.orphaned == 1
    assert orphan.is_file()


def test_a_historical_stem_form_exif_is_renamed_onto_x1(tmp_path):
    """Older extraction omitted the media extension; read old, write X1."""
    day = build_video_day(tmp_path)
    stray = day / f"{Path(CLIP).stem}._exif"       # stem, not the full name
    stray.write_bytes(b"exif")
    report = relocate_sidecars(day, make_config())
    assert report.orphaned == 0
    assert report.moved == 1
    assert report.renamed == 1
    assert report.media_without_sidecar == 0
    assert (day / "__EXIF" / f"{CLIP}._exif").is_file()


def test_an_exif_name_is_normalized_to_the_subjects_real_extension_case(tmp_path):
    day = tmp_path / "2026" / "07. July" / f"{STEM} - Case"
    (day / "__EXIF").mkdir(parents=True)
    media = day / f"{STEM}__f2.8__6D.JPG"
    media.write_bytes(b"jpg")
    old = day / "__EXIF" / f"{media.stem}.jpg._EXIF"
    old.write_bytes(b"exif")

    config = make_config()
    config["extensions"]["lossy_images"] = [".jpg"]
    report = relocate_sidecars(day, config)

    assert report.orphaned == 0
    assert report.media_without_sidecar == 0
    assert report.renamed == 1
    assert (day / "__EXIF" / f"{media.name}._exif").is_file()


def test_a_stem_sidecar_beside_the_jpeg_does_not_claim_the_same_stem_raw(tmp_path):
    """X10 location disambiguates the historical stem shared by JPG and RAW."""
    day = tmp_path / "2026" / "07. July" / f"{STEM} - Same stem"
    (day / "__EXIF").mkdir(parents=True)
    (day / "__RAW").mkdir()
    shared_stem = f"{STEM}__RAW__f8.0__6D"
    jpg = f"{shared_stem}.JPG"
    raw = f"{shared_stem}.ARW"
    (day / jpg).write_bytes(b"jpg")
    (day / "__RAW" / raw).write_bytes(b"raw")
    old = day / "__EXIF" / f"{shared_stem}._EXIF"
    old.write_bytes(b"jpg exif")

    config = make_config()
    config["extensions"].update(
        {"lossy_images": [".jpg"], "raw_images": [".arw"]})
    report = relocate_sidecars(day, config)

    assert report.orphaned == 0
    assert report.ambiguous == 0
    assert report.media_without_sidecar == 1
    assert report.missing_sidecars == [day / "__RAW" / raw]
    assert (day / "__EXIF" / f"{jpg}._exif").is_file()


def test_a_preview_is_never_treated_as_a_subject(tmp_path):
    """X7: a preview is not media, so nothing pairs against it."""
    day = build_video_day(tmp_path)
    (day / f"{CLIP}.thm").write_bytes(b"thumb")
    (day / f"{CLIP}.thm._exif").write_bytes(b"exif")
    report = relocate_sidecars(day, make_config())
    # The ._exif names a preview as its subject, and a preview is not one.
    assert report.orphaned == 1
    assert (day / f"{CLIP}.thm._exif").is_file()


def test_previews_and_sidecars_are_placed_in_the_same_pass(tmp_path):
    day = build_video_day(tmp_path)
    (day / f"{CLIP}._exif").write_bytes(b"exif")
    (day / f"{Path(CLIP).stem}.LRV").write_bytes(b"proxy")
    report = relocate_sidecars(day, make_config())
    assert report.moved == 2
    assert (day / "__EXIF" / f"{CLIP}._exif").is_file()
    assert (day / "__PREVIEWS" / f"{CLIP}.lrv").is_file()


def test_routing_previews_is_idempotent(tmp_path):
    day = build_video_day(tmp_path)
    (day / f"{Path(CLIP).stem}.LRV").write_bytes(b"proxy")
    assert relocate_sidecars(day, make_config()).moved == 1
    second = relocate_sidecars(day, make_config())
    assert second.moved == 0
    assert second.in_place == 1


def test_a_dry_run_routes_no_preview(tmp_path):
    day = build_video_day(tmp_path)
    source = day / f"{Path(CLIP).stem}.LRV"
    source.write_bytes(b"proxy")
    planned = []
    report = relocate_sidecars(
        day, make_config(),
        move=lambda s, t: planned.append((Path(s), Path(t))),
        prune=False)
    assert report.moved == 1
    assert planned == [(source, day / "__PREVIEWS" / f"{CLIP}.lrv")]
    assert source.is_file()
    assert not (day / "__PREVIEWS").exists()


def test_an_archive_keeping_no_previews_leaves_them_alone(tmp_path):
    day = build_video_day(tmp_path)
    preview = day / f"{Path(CLIP).stem}.LRV"
    preview.write_bytes(b"proxy")
    config = make_config()
    config["extensions"]["previews"] = []
    report = relocate_sidecars(day, config)
    assert report.seen == 0
    assert preview.is_file()


# --------------------------------------------------------------------------
# Only a dated folder holds subjects, and a sidecar may lie anywhere
# --------------------------------------------------------------------------

def place(roots, config, log=lambda _m: None, parking=None):
    return place_companions(roots, config, lambda _folder: parking or roots[0],
                            log)


def build_two_years(tmp_path):
    """Two year trees, each with one dated folder holding one image."""
    made = {}
    for year, month, day, name in (
            ("2025", "08. August", "2025-08-01_(Fri) - Trip", "2025-08-01_(Fri)__12.00.00__f4__6D.jpg"),
            ("2026", "07. July", "2026-07-18_(Sat)__17.04.53 - Dive", JPG)):
        folder = tmp_path / year / month / day
        folder.mkdir(parents=True)
        (folder / name).write_bytes(b"media")
        made[year] = (tmp_path / year, folder, name)
    return made


def test_a_dated_folder_needs_no_time(tmp_path):
    """The format is read loosely: a leading date is enough (N1)."""
    made = build_two_years(tmp_path)
    year, folder, name = made["2025"]
    # "2025-08-01_(Fri) - Trip" carries no time at all.
    (folder / f"{name}._exif").write_bytes(b"e")
    report = place([year], make_config())
    assert report.moved == 1
    assert (folder / "__EXIF" / f"{name}._exif").is_file()


def test_a_sidecar_finds_its_subject_in_another_year(tmp_path):
    """Anywhere in the whole target, at any depth."""
    made = build_two_years(tmp_path)
    year_2025, folder_2025, name_2025 = made["2025"]
    year_2026, folder_2026, _name = made["2026"]
    # The 2025 sidecar is stranded deep inside a 2026 event folder.
    stranded = folder_2026 / "__RAW"
    stranded.mkdir()
    (stranded / f"{name_2025}._exif").write_bytes(b"e")

    report = place([year_2025, year_2026], make_config())

    assert report.moved == 1
    assert report.across_folders == 1
    assert (folder_2025 / "__EXIF" / f"{name_2025}._exif").is_file()


def test_media_outside_a_dated_folder_is_never_a_subject(tmp_path):
    """A stray JPG in a working folder must not answer some sidecar's search."""
    made = build_two_years(tmp_path)
    year, _folder, _name = made["2026"]
    junk = year / "07. July" / "Random Junk Folder"
    junk.mkdir()
    (junk / "stray.jpg").write_bytes(b"stray")
    (junk / "stray.jpg._exif").write_bytes(b"e")

    report = place([year], make_config())

    assert report.orphaned == 1                 # the subject is not indexed
    assert (junk / "stray.jpg._exif").is_file()
    assert (junk / "stray.jpg").is_file()


def test_a_folder_that_fits_no_shape_is_reported(tmp_path):
    made = build_two_years(tmp_path)
    year, _folder, _name = made["2026"]
    junk = year / "07. July" / "Random Junk Folder"
    junk.mkdir()

    report = place([year], make_config())

    assert [path for path, _reason in report.non_compliant] == [junk]
    assert "carries no date" in report.non_compliant[0][1]


def test_month_folders_and_dated_folders_are_not_reported(tmp_path):
    made = build_two_years(tmp_path)
    year, folder, _name = made["2026"]
    (folder / "__RAW").mkdir()
    (folder / "__RAW" / "__EXIF").mkdir()       # X11's one legal nest
    (year / "__DUPLICATES").mkdir()

    report = place([year], make_config())

    assert report.non_compliant == []


def test_an_unknown_folder_inside_a_dated_folder_is_reported(tmp_path):
    made = build_two_years(tmp_path)
    year, folder, _name = made["2026"]
    odd = folder / "my notes"
    odd.mkdir()

    report = place([year], make_config())

    assert [path for path, _reason in report.non_compliant] == [odd]
    assert "allowed subfolders" in report.non_compliant[0][1]


# --------------------------------------------------------------------------
# X6a/X15 -- generated previews and OCR text, routed by their subject's folder
# --------------------------------------------------------------------------

OCR_CLIP = f"{STEM}__fNA__T---__LNA__I---s__SG23U.mp4"


def make_full_config():
    """The config as shipped: compound preview forms and OCR text included."""
    config = make_config()
    config["taxonomy"]["ocr"] = "__OCR"
    config["extensions"]["previews"] = [".THM.jpg", ".PREVIEW.jpg", ".thm", ".lrv"]
    config["extensions"]["ocr"] = [".OCR.txt"]
    return config


def build_ocr_clip_day(tmp_path):
    """A day holding a video at the top level and a RAW in ``__RAW`` (V1, F2)."""
    day = tmp_path / "2026" / "07. July" / f"{STEM} - Lens tests"
    (day / "__RAW").mkdir(parents=True)
    (day / OCR_CLIP).write_bytes(b"video")
    (day / "__RAW" / RAW).write_bytes(b"raw")
    return day


def test_a_videos_generated_previews_land_beside_the_video(tmp_path):
    """X6a/X13: the video is at the top level, so its previews are one below it."""
    day = build_ocr_clip_day(tmp_path)
    for extension in (".thm", ".THM.jpg", ".PREVIEW.jpg"):
        (day / f"{OCR_CLIP}{extension}").write_bytes(b"preview")

    relocate_sidecars(day, make_full_config())

    assert sorted(path.name for path in (day / "__PREVIEWS").iterdir()) == [
        f"{OCR_CLIP}.PREVIEW.jpg", f"{OCR_CLIP}.THM.jpg", f"{OCR_CLIP}.thm"]
    assert [path.name for path in day.iterdir() if path.is_file()] == [OCR_CLIP]


def test_a_raws_previews_land_under_the_raw_folder_not_the_days(tmp_path):
    """X10/X13: the subject is in ``__RAW``, so its previews are in ``__RAW\\__PREVIEWS``.

    Including one that starts out in the day's own ``__PREVIEWS`` -- being in a
    preview folder is not the same as being in the right one.
    """
    day = build_ocr_clip_day(tmp_path)
    (day / f"{RAW}.thm").write_bytes(b"camera thumb")
    (day / "__PREVIEWS").mkdir()
    (day / "__PREVIEWS" / f"{RAW}.PREVIEW.jpg").write_bytes(b"generated")

    relocate_sidecars(day, make_full_config())

    assert sorted(path.name for path in (day / "__RAW" / "__PREVIEWS").iterdir()) == [
        f"{RAW}.PREVIEW.jpg", f"{RAW}.thm"]
    day_previews = day / "__PREVIEWS"
    assert not (day_previews.exists() and any(day_previews.iterdir()))


def test_a_generated_preview_is_never_treated_as_the_image_it_looks_like(tmp_path):
    """X7: ``Path.suffix`` says ".jpg", and it is still not media.

    The failure this guards against is not cosmetic: counted as an image, a
    thumbnail is offered to the grouper GUI and can be picked as the
    representative for the very shot it is a thumbnail of.
    """
    from src.pipeline_stages.grouping_names import count_media, select_media

    names = [OCR_CLIP, f"{OCR_CLIP}.THM.jpg", f"{OCR_CLIP}.PREVIEW.jpg"]
    previews = {".thm.jpg", ".preview.jpg", ".thm", ".lrv"}
    assert select_media(names, {".jpg"}, {".mp4"}, previews) == [OCR_CLIP]
    assert count_media(names, {".jpg"}, {".mp4"}, previews) == (0, 1)


def test_recognised_text_goes_to_its_own_folder(tmp_path):
    """X15: OCR text is a sidecar, and not one that belongs in ``__EXIF``."""
    day = build_ocr_clip_day(tmp_path)
    (day / f"{OCR_CLIP}.OCR.txt").write_bytes(b"text")
    (day / "__RAW" / f"{RAW}.OCR.txt").write_bytes(b"text")

    relocate_sidecars(day, make_full_config())

    assert (day / "__OCR" / f"{OCR_CLIP}.OCR.txt").is_file()
    assert (day / "__RAW" / "__OCR" / f"{RAW}.OCR.txt").is_file()
    assert not (day / "__EXIF").exists()


def test_a_companion_is_renamed_to_the_one_spelling_the_archive_uses(tmp_path):
    """Matched case-insensitively (X1a), written as the standard spells it.

    A camera, a converter and an earlier run will each have written a different
    case. Converging them means a later pass has one form to look for.
    """
    day = build_ocr_clip_day(tmp_path)
    (day / f"{OCR_CLIP}.preview.jpg").write_bytes(b"lower")
    (day / f"{OCR_CLIP}.ocr.TXT").write_bytes(b"mixed")

    relocate_sidecars(day, make_full_config())

    assert (day / "__PREVIEWS" / f"{OCR_CLIP}.PREVIEW.jpg").is_file()
    assert (day / "__OCR" / f"{OCR_CLIP}.OCR.txt").is_file()
