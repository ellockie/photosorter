"""The dated-name convention: one canonical form written, every form read."""

import datetime

from src.pipeline_stages.stamps import \
    day_prefix, \
    format_day_prefix, \
    format_stamp, \
    leading_stamp_key, \
    parse_stamp, \
    stamp_keys

MOMENT = datetime.datetime(2026, 8, 14, 15, 32, 1)


def test_canonical_form_uses_a_double_underscore_before_the_time():
    assert format_stamp(MOMENT) == "2026-08-14_(Fri)__15.32.01"
    assert format_day_prefix(MOMENT) == "2026-08-14_(Fri)"


def test_weekday_is_fixed_english_not_the_system_locale():
    # strftime("%a") follows the locale, so a Polish-locale Windows would write
    # "(pt)" and every regex here would stop matching its own output.
    for day in range(1, 8):
        stamp = format_stamp(datetime.datetime(2026, 6, day, 12, 0, 0))
        assert stamp.split("_(")[1][:3] in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def test_every_historical_form_still_parses():
    for text in (
        "2026-08-14_(Fri)__15.32.01",   # canonical
        "2026-08-14_(Fri)_15.32.01",    # previous Photosorter
        "2026-08-14__15.32.01",         # legacy grouper, no weekday
    ):
        assert parse_stamp(text) == MOMENT, text
        assert leading_stamp_key(text) == "20260814153201", text


def test_a_wrong_weekday_does_not_reject_a_valid_stamp():
    # The day name is decorative; a stale one must not lose the file.
    assert parse_stamp("2026-08-14_(Mon)__15.32.01") == MOMENT


def test_all_stamps_in_a_name_are_reported_in_order():
    name = "2026-07-19__21.29.04__SCR__2026-07-19_(Sun)_15.37.10__f1.7.jpg"
    assert stamp_keys(name) == ["20260719212904", "20260719153710"]


def test_undated_names_yield_nothing():
    assert parse_stamp("Screenshot 2026.png") is None
    assert leading_stamp_key("Screenshot 2026.png") is None
    assert stamp_keys("Screenshot 2026.png") == []
    assert day_prefix("__EMPTY_SUBFOLDERS") is None


def test_day_prefix_reads_folder_names():
    assert day_prefix("2026-08-14_(Fri) - __TO_SPLIT__(i=7)") == "2026-08-14"
    assert day_prefix("2026-08-14_(Fri)__15.32.01 - Kajaki") == "2026-08-14"
    assert day_prefix("2026-08-14 - Trip") == "2026-08-14"


def test_split_dated_folder_reads_every_prefix_form():
    """One parser for a dated folder's prefix, timed or not (N3/N5)."""
    from src.pipeline_stages.stamps import split_dated_folder

    assert split_dated_folder("2026-04-12_(Sun)") == ("2026-04-12", None, None, "")
    assert split_dated_folder("2026-04-12_(Sun) - Japan") == (
        "2026-04-12", None, None, " - Japan")
    # Canonical timed form — the shape the archive is being converged onto.
    assert split_dated_folder("2026-07-15_(Wed)__08.14.02 - Sopot") == (
        "2026-07-15", "08.14.02", None, " - Sopot")
    # Historical forms (N5) still read.
    assert split_dated_folder("2026-07-15_(Wed)_08.14.02") == (
        "2026-07-15", "08.14.02", None, "")
    assert split_dated_folder("2026-07-15__08.14.02 - x") == (
        "2026-07-15", "08.14.02", None, " - x")
    assert split_dated_folder("__EXIF") is None


def test_multi_day_span_end_is_read_and_expanded():
    """C8: a container covering several days states the end after "#", written
    as the shortest tail of a date that still identifies the day."""
    from src.pipeline_stages.stamps import resolve_range_end, split_dated_folder

    same_month = split_dated_folder("2026-08-20_(Thu)__09.14.02#22 - Malbork")
    assert same_month == ("2026-08-20", "09.14.02", "#22", " - Malbork")
    assert resolve_range_end(same_month.date, same_month.range_end) == "2026-08-22"

    same_year = split_dated_folder("2026-08-20_(Thu)__09.14.02#09-11 - Baltic")
    assert resolve_range_end(same_year.date, same_year.range_end) == "2026-09-11"

    across_years = split_dated_folder("2026-12-28_(Mon)__17.02.00#2027-01-03 - NY")
    assert resolve_range_end(across_years.date, across_years.range_end) == "2027-01-03"

    # A single-day folder has no span, and the start still leads so alphabetical
    # order stays chronological.
    single = split_dated_folder("2026-08-20_(Thu)__09.14.02 - Malbork")
    assert single.range_end is None
    assert resolve_range_end(single.date, single.range_end) is None


def test_retime_sees_folders_carrying_the_canonical_time():
    """Regression: retime_archive's own regex demanded the weekday and then
    either " - <description>" or end-of-name, so every folder carrying the
    canonical time was silently skipped — and the canonicaliser has been
    putting the archive onto exactly that form."""
    from src.retime_archive import _event_description

    assert _event_description("2026-07-15_(Wed)__08.14.02 - Sopot") == "Sopot"
    assert _event_description("2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=79)") == \
        "__TO_SPLIT__(i=79)"
    assert _event_description("2026-07-15__08.14.02 - legacy grouper") == "legacy grouper"
    # Still recognised, unchanged.
    assert _event_description("2026-04-12_(Sun) - Japan") == "Japan"
    assert _event_description("2026-04-12_(Sun)") is None
    # A tail that is not the folder-name grammar is not an event folder, so an
    # unrelated sibling is never renamed.
    assert _event_description("2026-04-12_(Sun)_backup") is False
    assert _event_description("__EXIF") is False
