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
