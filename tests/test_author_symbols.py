"""Author symbols: who took the shot, as opposed to what took it.

Standard F8/G4. The camera symbol identifies a device, so two people shooting the
same model are indistinguishable by it — which is the case merged foreign-origin
media creates.
"""

from src.core import default_config
from src.pipeline_stages.legacy import (
    author_symbol_for_name,
    legacy_filename,
    parse_legacy_exif_sidecar,
)

CONFIG = {
    "camera_symbols": {"": "NOID"},
    "author_symbols": {"": "", "Anna Kowalska": "AK", "Marek Wilk": "MW"},
    "extensions": {"raw_images": [".cr2"]},
    "legacy": {"raw_marker": "RAW__"},
}

BASE = {
    "image_datetime": "2026-05-14_(Thu)__10.30.00",
    "aperture": "f2.8",
    "exposure_time": "T1_250",
    "focal_length": "L50.0",
    "iso": "I200",
    "camera_symbol": "C6D",
}


def test_the_owner_carries_no_marker():
    # The default must stay empty: a marker on the owner's own media would mean
    # renaming every file already in the archive to state what its absence
    # already states.
    assert author_symbol_for_name(None, CONFIG) == ""
    assert author_symbol_for_name("", CONFIG) == ""
    assert legacy_filename(BASE, ".jpg", CONFIG) == \
        "2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I200__C6D.jpg"
    assert "author_symbols" in default_config()


def test_a_known_author_is_appended_after_the_camera():
    assert author_symbol_for_name("Anna Kowalska", CONFIG) == "AK"
    name = legacy_filename({**BASE, "author_symbol": "AK"}, ".jpg", CONFIG)
    assert name == "2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I200__C6D__@AK.jpg"
    # The "@" makes the token self-identifying: a third-party tool can tell an
    # author from a camera symbol without consulting the table.
    assert name.split("__")[-1].startswith("@")


def test_an_unknown_author_resolves_to_none_not_to_the_owner():
    # Silently falling back would file someone else's photo as the owner's —
    # the one outcome the marker exists to prevent.
    assert author_symbol_for_name("Someone Unlisted", CONFIG) is None


def test_the_marker_survives_alongside_raw_and_representative_suffixes():
    raw = legacy_filename({**BASE, "author_symbol": "MW"}, ".cr2", CONFIG)
    assert raw == \
        "2026-05-14_(Thu)__10.30.00__RAW__f2.8__T1_250__L50.0__I200__C6D__@MW.CR2"

    from src.pipeline_stages.taxonomy import apply_representative_suffixes
    jpg = legacy_filename({**BASE, "author_symbol": "MW"}, ".jpg", CONFIG)
    assert apply_representative_suffixes(jpg, has_raw=True) == \
        "2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I200__C6D__@MW_HAS_RAW.jpg"


def test_exif_artist_is_read_through_the_same_table(tmp_path):
    sidecar = tmp_path / "shot.jpg._exif"
    sidecar.write_text(
        "Camera Model Name               : Canon EOS 6D\n"
        "Artist                          : Anna Kowalska\n"
        "Date/Time Original              : 2026:05:14 10:30:00\n",
        encoding="iso-8859-1")

    metadata = parse_legacy_exif_sidecar(sidecar, CONFIG)

    assert metadata["author_name"] == "Anna Kowalska"
    assert metadata["author_symbol"] == "AK"


def test_exif_artist_unknown_to_the_table_is_left_unresolved(tmp_path):
    sidecar = tmp_path / "shot.jpg._exif"
    sidecar.write_text(
        "Camera Model Name               : Canon EOS 6D\n"
        "Artist                          : Nobody In Particular\n",
        encoding="iso-8859-1")

    metadata = parse_legacy_exif_sidecar(sidecar, CONFIG)

    assert metadata["author_name"] == "Nobody In Particular"
    assert metadata["author_symbol"] is None
    # An unresolved author writes no marker rather than a wrong one. The name is
    # then exactly what it would have been without the Artist tag at all.
    name = legacy_filename({**BASE, **metadata}, ".jpg", CONFIG)
    assert "@" not in name
    assert name.endswith("__6D.jpg")
