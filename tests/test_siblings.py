"""PS-10 / F9 -- two shots inside one second are siblings, not duplicates.

The archive names a shot by the second it was taken in, the camera and the four
exposure settings. A burst produces two files that agree on every one of them,
so they generate one name -- and the pipeline used to settle that by calling one
of them ``_DUPE_<md5>``, which F4 reserves for a **byte-identical** loser. It
was a false claim twice over: the two files differ, and the checksum written
into one name says nothing about the other.

These tests pin the three things that fix it:

  * ``SubSecTimeOriginal`` is read, and it is what separates the pair;
  * a byte-different loser is never called ``_DUPE`` again, anywhere;
  * the leading stamp stays the archive's join key (F1) even with a fraction
    on it, so nothing that matches a sidecar to its subject by timestamp is
    disturbed.
"""

import datetime
import os
from pathlib import Path

from src.core import \
    MediaAsset, \
    PipelineContext, \
    default_config, \
    file_md5
from src.pipeline_stages.folder_sorting import FolderSortingStage
from src.pipeline_stages.legacy import \
    final_event_folder, \
    legacy_filename, \
    parse_legacy_exif_text
from src.pipeline_stages.rename_and_sort import RenameAndSortStage
from src.pipeline_stages.siblings import \
    SUBSECOND_METADATA_KEY, \
    are_siblings, \
    next_ordinal_name, \
    sibling_name, \
    strip_ordinal, \
    subsecond_from_exif_text, \
    with_ordinal
from src.pipeline_stages.stamps import \
    apply_subsecond, \
    leading_stamp_key, \
    leading_subsecond, \
    normalise_subsecond, \
    parse_stamp, \
    stamp_keys


BARE = "2026-08-21_(Fri)__20.43.52__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"


def build_config(tmp_path: Path) -> dict:
    config = default_config()
    root = tmp_path / "archive"
    working = tmp_path / "pipeline"
    config["paths"].update({
        "root_folder": str(root),
        "working_folder": str(working),
        "inbox_folder": str(working / "INBOX"),
        "unsorted_folder": str(working / "INBOX"),
        "ready_folder": str(working / "READY"),
        "temp_folder": str(working / ".TMP"),
        "temp_root": str(working / ".TMP"),
    })
    return config


def exif_text(subsecond: str | None) -> str:
    """An ExifTool text sidecar of the shape the pipeline actually writes."""
    lines = [
        "Camera Model Name               : SM-S928B",
        "Date/Time Original              : 2026:08:21 20:43:52",
    ]
    if subsecond is not None:
        lines += [
            "Sub Sec Time                    : " + subsecond,
            "Sub Sec Time Original           : " + subsecond,
            "Sub Sec Time Digitized          : " + subsecond,
        ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# The grammar: a fraction on the stamp, and the join key that survives it
# --------------------------------------------------------------------------

def test_a_fraction_goes_on_the_time_and_replaces_one_already_there():
    fractioned = apply_subsecond(BARE, "633")

    assert fractioned == (
        "2026-08-21_(Fri)__20.43.52.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg")
    assert leading_subsecond(fractioned) == "633"
    assert leading_subsecond(BARE) is None
    # Idempotent, and a second application replaces rather than appends.
    assert apply_subsecond(fractioned, "633") == fractioned
    assert leading_subsecond(apply_subsecond(fractioned, "433")) == "433"
    assert apply_subsecond(fractioned, None) == BARE


def test_the_fraction_does_not_disturb_the_join_key():
    """F1: sidecars, RAWs and videos find their subject by the stamp.

    A RAW or a sidecar carries only the second, so a fractioned representative
    has to keep answering to the same ``YYYYMMDDHHMMSS`` -- otherwise adding a
    fraction would orphan every companion of that shot.
    """
    fractioned = apply_subsecond(BARE, "633")

    assert leading_stamp_key(fractioned) == leading_stamp_key(BARE)
    assert stamp_keys(fractioned) == stamp_keys(BARE)
    assert parse_stamp(fractioned) == parse_stamp(BARE)
    assert parse_stamp(fractioned) == datetime.datetime(2026, 8, 21, 20, 43, 52)


def test_a_name_without_a_parseable_stamp_is_left_alone():
    """Nothing here may invent the timestamp F1 calls the join key."""
    assert apply_subsecond("IMG_0001.jpg", "633") == "IMG_0001.jpg"


def test_a_fraction_is_kept_as_the_camera_wrote_it_or_not_at_all():
    assert normalise_subsecond(" 633 ") == "633"
    assert normalise_subsecond("07") == "07"       # not rescaled to "070"
    assert normalise_subsecond(0) == "0"
    assert normalise_subsecond("") is None
    assert normalise_subsecond("n/a") is None
    assert normalise_subsecond(None) is None


def test_ordinals_replace_rather_than_accumulate():
    numbered = with_ordinal(BARE, 2)

    assert numbered == (
        "2026-08-21_(Fri)__20.43.52__f2.4__T1_50__L69.0.eq__I100__SG23U_2.jpg")
    assert with_ordinal(numbered, 3) == with_ordinal(BARE, 3)
    assert strip_ordinal(Path(numbered).stem) == Path(BARE).stem
    # Numbering starts at 2: the first sibling keeps the bare name, so the
    # common case -- one shot in a second -- is never renumbered into "_1".
    assert next_ordinal_name(BARE, lambda name: False) == with_ordinal(BARE, 2)
    assert next_ordinal_name(BARE, lambda name: name == with_ordinal(BARE, 2)) \
        == with_ordinal(BARE, 3)


def test_sibling_name_writes_the_camera_fraction_and_nothing_else():
    assert sibling_name(BARE, "633") == apply_subsecond(BARE, "633")
    # No fraction, no proven sibling (F9a): the ordinal is a separate path a
    # person opens (F9b), never something this function reaches for.
    assert sibling_name(BARE, None) == BARE


# --------------------------------------------------------------------------
# The rule: what counts as evidence of two exposures (F9a)
# --------------------------------------------------------------------------

def test_only_two_differing_fractions_prove_two_exposures():
    assert are_siblings("633", "433") is True
    # Same instant, different bytes: one shot saved twice.
    assert are_siblings("633", "633") is False
    # Nothing to compare -- guessing here would file a re-encode as a sibling.
    assert are_siblings("633", None) is False
    assert are_siblings(None, "433") is False
    # Neither camera recorded one: a burst and a re-save look identical, so
    # this goes to a person (F4) rather than being invented either way.
    assert are_siblings(None, None) is False


def test_the_fraction_is_read_from_the_original_field_only():
    """``Sub Sec Time Digitized`` is not accepted as a stand-in for it."""
    assert subsecond_from_exif_text(exif_text("633")) == "633"
    assert subsecond_from_exif_text(
        "Sub Sec Time Digitized          : 633\n") is None
    assert subsecond_from_exif_text(exif_text(None)) is None


def test_the_sidecar_parser_carries_the_fraction_onto_the_asset():
    metadata = parse_legacy_exif_text(exif_text("433"), default_config())

    assert metadata[SUBSECOND_METADATA_KEY] == "433"
    # A shot's name does not carry it. The fraction is what tells two shots in
    # one second apart, so it is written only where there are two (F9c) — by
    # the stage that can see the whole second's worth of files, not by the
    # name builder, which sees one file at a time.
    name = legacy_filename(metadata, ".jpg", default_config())
    assert name.startswith("2026-08-21_(Fri)__20.43.52__")
    assert leading_subsecond(name) is None


# --------------------------------------------------------------------------
# The pipeline: PS-10's own case, end to end
# --------------------------------------------------------------------------

def _inbox_shot(inbox: Path, name: str, content: str, subsecond: str | None):
    """A media file plus the sidecar the ExifTool stage would have left."""
    path = inbox / name
    path.write_text(content, encoding="utf-8")
    sidecar = inbox / (name + "._exif")
    sidecar.write_text(exif_text(subsecond), encoding="iso-8859-1")
    return path, sidecar


def _metadata(subsecond: str | None) -> dict:
    metadata = {
        "image_datetime": "2026-08-21_(Fri)__20.43.52",
        "aperture": "f2.4",
        "exposure_time": "T1_50",
        "focal_length": "L69.0.eq",
        "iso": "I100",
        "camera_symbol": "SG23U",
        "captured_at": datetime.datetime(2026, 8, 21, 20, 43, 52),
    }
    if subsecond is not None:
        metadata[SUBSECOND_METADATA_KEY] = subsecond
    return metadata


def test_two_shots_in_one_second_are_both_kept_and_both_fractioned(tmp_path):
    """PS-10 exactly: the two files from the issue, and neither is a duplicate.

    Both carry their own fraction rather than only the arrival, so the pair
    sorts in the order it was shot -- "." precedes "_", so a bare
    "…52__f2.4" would sort *after* a fractioned "…52.633__f2.4".
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    first, first_sidecar = _inbox_shot(inbox, "IMG_0001.jpg", "x" * 900, "633")
    second, second_sidecar = _inbox_shot(inbox, "IMG_0002.jpg", "y" * 880, "433")

    context = PipelineContext(config=config)
    context.assets = [
        MediaAsset(first, {"exif": first_sidecar}, _metadata("633")),
        MediaAsset(second, {"exif": second_sidecar}, _metadata("433")),
    ]

    RenameAndSortStage().execute(context)

    names = sorted(path.name for path in inbox.iterdir() if path.suffix == ".jpg")
    assert names == [
        "2026-08-21_(Fri)__20.43.52.433__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
        "2026-08-21_(Fri)__20.43.52.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
    ]
    assert not [path for path in inbox.iterdir()
                if "_DUPE_" in path.name or "_DIFFERS_" in path.name]
    assert context.counters["renamed_assets"] == 2
    # Sorted order is capture order: .433 was taken before .633.
    assert names[0] < names[1]
    # Every sidecar followed its subject (X5), and none was orphaned (X4).
    for asset in context.assets:
        assert asset.sidecars["exif"].exists()
        assert asset.sidecars["exif"].name == asset.primary_path.name + "._exif"


def test_a_true_duplicate_in_the_same_second_is_still_a_duplicate(tmp_path):
    """Identical bytes carry identical EXIF, so the fractions match: not siblings."""
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    first, first_sidecar = _inbox_shot(inbox, "IMG_0001.jpg", "same", "633")
    second, second_sidecar = _inbox_shot(inbox, "IMG_0002.jpg", "same", "633")

    context = PipelineContext(config=config)
    context.assets = [
        MediaAsset(first, {"exif": first_sidecar}, _metadata("633")),
        MediaAsset(second, {"exif": second_sidecar}, _metadata("633")),
    ]

    RenameAndSortStage().execute(context)

    jpgs = [path for path in inbox.iterdir() if path.suffix == ".jpg"]
    assert len(jpgs) == 1, "the redundant copy is discarded, not filed twice"
    assert leading_subsecond(jpgs[0].name) == "633", \
        "the survivor still carries its own fraction (F9c)"
    assert "_DUPE_" not in jpgs[0].name


def test_one_shot_saved_twice_never_becomes_a_sibling(tmp_path):
    """Same fraction, different bytes: a rendering, and F4's question.

    The loser is a ``_DIFFERS`` -- the two files are provably not the same
    file, which is the only thing ``_DUPE`` is allowed to claim.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    first, first_sidecar = _inbox_shot(inbox, "IMG_0001.jpg", "x" * 900, "633")
    second, second_sidecar = _inbox_shot(inbox, "IMG_0002.jpg", "y" * 880, "633")
    os.utime(first, (1_000_000, 1_000_000))
    os.utime(second, (2_000_000, 2_000_000))

    context = PipelineContext(config=config)
    context.assets = [
        MediaAsset(first, {"exif": first_sidecar}, _metadata("633")),
        MediaAsset(second, {"exif": second_sidecar}, _metadata("633")),
    ]

    RenameAndSortStage().execute(context)

    names = [path.name for path in inbox.iterdir() if path.suffix == ".jpg"]
    assert any("_DIFFERS_" in name for name in names)
    assert not any("_DUPE_" in name for name in names)


def test_a_sibling_arriving_at_a_folder_already_holding_one_is_not_demoted(tmp_path):
    """The other half of PS-10: the collision that happens on the way in.

    A shot already filed and a shot arriving can generate the same name just as
    two inbox files can, and that path used to flag the file already in the
    archive as a duplicate of the newcomer without comparing a single byte.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    captured = datetime.datetime(2026, 8, 21, 20, 43, 52)
    name = legacy_filename(_metadata(None), ".jpg", config)

    event_folder = final_event_folder(captured, config)
    exif_folder = event_folder / "__EXIF"
    exif_folder.mkdir(parents=True)
    filed = event_folder / name
    filed.write_text("already filed", encoding="utf-8")
    (exif_folder / (name + "._exif")).write_text(exif_text("633"), encoding="iso-8859-1")

    arriving, arriving_sidecar = _inbox_shot(inbox, name, "just arrived", "433")
    asset = MediaAsset(arriving, {"exif": arriving_sidecar}, _metadata("433"))

    context = PipelineContext(config=config)
    context.assets = [asset]
    FolderSortingStage().execute(context)

    top_level = sorted(path.name for path in event_folder.iterdir() if path.is_file())
    assert top_level == [
        "2026-08-21_(Fri)__20.43.52.433__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
        "2026-08-21_(Fri)__20.43.52.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
    ]
    assert not any("_DUPE_" in one or "_DIFFERS_" in one for one in top_level)
    # The file that was already there kept its content and took its own
    # fraction; its sidecar followed it out of the old name (X5).
    assert (event_folder / top_level[1]).read_text(encoding="utf-8") == "already filed"
    assert sorted(path.name for path in exif_folder.iterdir()) == \
        [one + "._exif" for one in top_level]


def test_the_demoted_loser_still_carries_its_own_checksum(tmp_path):
    """A ``_DIFFERS`` names the loser's hash, exactly as ``_DUPE`` did.

    Only the claim changes, not the grammar: F4's ``<suffix>_<md5>_<n>`` is
    what lets a person match the pair up again by eye.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    first, first_sidecar = _inbox_shot(inbox, "IMG_0001.jpg", "x" * 900, "633")
    second, second_sidecar = _inbox_shot(inbox, "IMG_0002.jpg", "y" * 880, "633")
    os.utime(first, (1_000_000, 1_000_000))
    os.utime(second, (2_000_000, 2_000_000))
    second_md5 = file_md5(second)

    context = PipelineContext(config=config)
    context.assets = [
        MediaAsset(first, {"exif": first_sidecar}, _metadata("633")),
        MediaAsset(second, {"exif": second_sidecar}, _metadata("633")),
    ]

    RenameAndSortStage().execute(context)

    loser = next(path for path in inbox.iterdir() if "_DIFFERS_" in path.name)
    assert second_md5 in loser.name
    assert loser.name.endswith("_1.jpg")


# --------------------------------------------------------------------------
# F9c -- the fraction is in every name, not only a contested one
# --------------------------------------------------------------------------

def test_two_shots_in_one_second_never_collide_at_all(tmp_path):
    """The point of writing the fraction always: no collision to settle.

    Neither file is ever compared against the other, so no suffix and no
    checksum is written on either -- the names were distinct the moment they
    were generated.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    first, first_sidecar = _inbox_shot(inbox, "IMG_0001.jpg", "x" * 900, "633")
    second, second_sidecar = _inbox_shot(inbox, "IMG_0002.jpg", "y" * 880, "433")

    context = PipelineContext(config=config)
    context.assets = [
        MediaAsset(first, {"exif": first_sidecar}, _metadata("633")),
        MediaAsset(second, {"exif": second_sidecar}, _metadata("433")),
    ]

    RenameAndSortStage().execute(context)

    names = sorted(path.name for path in inbox.iterdir() if path.suffix == ".jpg")
    assert names == [
        "2026-08-21_(Fri)__20.43.52.433__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
        "2026-08-21_(Fri)__20.43.52.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
    ]
    assert not any(mark in name for name in names
                   for mark in ("_DUPE_", "_DIFFERS_", "_LOWRES_"))


def test_a_reingested_copy_still_meets_its_fraction_less_twin(tmp_path):
    """F9c must not blind the pipeline to what the archive already holds.

    A photo filed before fractions were written is called "…20.43.52__f2.4…".
    The same photo arriving again now generates "…20.43.52.633__f2.4…", and
    without looking for the older form too it would be filed a second time
    under a name nothing in the folder answers to.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    already_filed = inbox / "2026-08-21_(Fri)__20.43.52__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
    already_filed.write_text("the very same bytes", encoding="utf-8")
    (inbox / (already_filed.name + "._exif")).write_text(
        exif_text("633"), encoding="iso-8859-1")

    arriving, arriving_sidecar = _inbox_shot(
        inbox, "IMG_0002.jpg", "the very same bytes", "633")

    context = PipelineContext(config=config)
    context.assets = [MediaAsset(arriving, {"exif": arriving_sidecar}, _metadata("633"))]
    RenameAndSortStage().execute(context)

    jpgs = sorted(path.name for path in inbox.iterdir() if path.suffix == ".jpg")
    assert jpgs == [already_filed.name], "the redundant copy is discarded, not re-filed"


def test_an_older_twin_that_differs_is_renamed_to_carry_its_own_fraction(tmp_path):
    """The same meeting, but two exposures: the older name gains its fraction."""
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    already_filed = inbox / "2026-08-21_(Fri)__20.43.52__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
    already_filed.write_text("the first exposure", encoding="utf-8")
    (inbox / (already_filed.name + "._exif")).write_text(
        exif_text("925"), encoding="iso-8859-1")

    arriving, arriving_sidecar = _inbox_shot(inbox, "IMG_0002.jpg", "a second exposure", "325")

    context = PipelineContext(config=config)
    context.assets = [MediaAsset(arriving, {"exif": arriving_sidecar}, _metadata("325"))]
    RenameAndSortStage().execute(context)

    names = sorted(path.name for path in inbox.iterdir() if path.suffix == ".jpg")
    assert names == [
        "2026-08-21_(Fri)__20.43.52.325__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
        "2026-08-21_(Fri)__20.43.52.925__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
    ]
    assert not any("_DIFFERS_" in name or "_DUPE_" in name for name in names)
    # The renamed file kept its sidecar (X5).
    for name in names:
        assert (inbox / (name + "._exif")).is_file()


def test_folder_sorting_also_meets_the_fraction_less_twin(tmp_path):
    """The same F9c blind spot, on the way into the archive rather than in the inbox.

    A shot filed before fractions were written keeps its bare name; an arrival
    that is a different exposure gets its own fraction, and the older file is
    renamed to carry its own -- not demoted, and never onto the arrival's name.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    captured = datetime.datetime(2026, 8, 21, 20, 43, 52)
    bare = "2026-08-21_(Fri)__20.43.52__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"

    event_folder = final_event_folder(captured, config)
    exif_folder = event_folder / "__EXIF"
    exif_folder.mkdir(parents=True)
    (event_folder / bare).write_text("filed before fractions", encoding="utf-8")
    (exif_folder / (bare + "._exif")).write_text(exif_text("925"), encoding="iso-8859-1")

    fractioned = "2026-08-21_(Fri)__20.43.52.325__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"
    arriving, arriving_sidecar = _inbox_shot(inbox, fractioned, "a second exposure", "325")

    context = PipelineContext(config=config)
    context.assets = [MediaAsset(arriving, {"exif": arriving_sidecar}, _metadata("325"))]
    FolderSortingStage().execute(context)

    top_level = sorted(path.name for path in event_folder.iterdir() if path.is_file())
    assert top_level == [
        "2026-08-21_(Fri)__20.43.52.325__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
        "2026-08-21_(Fri)__20.43.52.925__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg",
    ]
    assert (event_folder / top_level[1]).read_text(encoding="utf-8") == "filed before fractions"
    assert not any("_DUPE_" in one or "_DIFFERS_" in one for one in top_level)
    assert sorted(path.name for path in exif_folder.iterdir()) == \
        [one + "._exif" for one in top_level]


def test_a_lone_shot_in_its_second_gets_no_fraction(tmp_path):
    """F9c: the fraction separates siblings, so one shot alone takes none."""
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)

    only, only_sidecar = _inbox_shot(inbox, "IMG_0001.jpg", "x" * 900, "633")
    context = PipelineContext(config=config)
    context.assets = [MediaAsset(only, {"exif": only_sidecar}, _metadata("633"))]

    RenameAndSortStage().execute(context)

    names = [path.name for path in inbox.iterdir() if path.suffix == ".jpg"]
    assert names == [
        "2026-08-21_(Fri)__20.43.52__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"]
    assert leading_subsecond(names[0]) is None


def test_a_third_shot_joins_two_already_fractioned_siblings(tmp_path):
    """The case an exact-name collision cannot see (F9c).

    Once two siblings carry ``.925`` and ``.325`` the plain name is free, so a
    third shot in that second meets no collision at all. It still belongs to
    the family and still needs its own fraction.
    """
    config = build_config(tmp_path)
    inbox = Path(config["paths"]["unsorted_folder"])
    inbox.mkdir(parents=True)
    stem = "2026-08-21_(Fri)__20.43.52.%s__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg"

    for fraction, body in (("925", "first"), ("325", "second")):
        (inbox / (stem % fraction)).write_text(body, encoding="utf-8")
        (inbox / ((stem % fraction) + "._exif")).write_text(
            exif_text(fraction), encoding="iso-8859-1")

    arriving, arriving_sidecar = _inbox_shot(inbox, "IMG_0003.jpg", "third", "700")
    context = PipelineContext(config=config)
    context.assets = [MediaAsset(arriving, {"exif": arriving_sidecar}, _metadata("700"))]

    RenameAndSortStage().execute(context)

    names = sorted(path.name for path in inbox.iterdir() if path.suffix == ".jpg")
    assert names == [stem % "325", stem % "700", stem % "925"]
    assert not any("_DUPE_" in name or "_DIFFERS_" in name for name in names)
