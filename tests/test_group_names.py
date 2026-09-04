"""The group grammar: the marker, the count, the span with a time on both ends.

ARCHIVE_STANDARD.md section 3. The two halves of a group's name live in two
modules on purpose -- the prefix and its "#" span end in ``stamps``, the tail
and its marker in ``grouping_names`` -- so these are the tests that hold the
seam between them, building a name out of both and reading it back.
"""

import datetime

import pytest

from src.pipeline_stages import grouping_names as grouping
from src.pipeline_stages import stamps


NORWAY = "2026-08-20_(Thu)__09.14.02#27__18.31.50 - ____GROUP____(d=7) - Norway"


# --------------------------------------------------------------------------
# The span end (C6-C9)
# --------------------------------------------------------------------------

def test_a_span_end_is_trimmed_to_the_shortest_day_that_identifies_it():
    """C7: the year goes when it matches the start's, then the month."""
    same_month = stamps.format_range_end(
        "2026-08-20", datetime.datetime(2026, 8, 27, 18, 31, 50))
    assert same_month == "#27__18.31.50"

    same_year = stamps.format_range_end(
        "2026-08-20", datetime.datetime(2026, 9, 11, 7, 0, 1))
    assert same_year == "#09-11__07.00.01"

    across_years = stamps.format_range_end(
        "2026-12-28", datetime.datetime(2027, 1, 3, 17, 2, 0))
    assert across_years == "#2027-01-03__17.02.00"


def test_a_single_day_span_is_still_written_in_full():
    """C9: one shape, whether the group covers an afternoon or a fortnight."""
    assert stamps.format_range_end(
        "2026-07-18", datetime.datetime(2026, 7, 18, 22, 14, 9)) == "#18__22.14.09"


def test_a_span_end_carries_its_time_back_out_again():
    parsed = stamps.split_dated_folder(NORWAY)
    assert parsed.date == "2026-08-20"
    assert parsed.time == "09.14.02"
    assert parsed.range_end == "#27__18.31.50"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-27"
    assert stamps.range_end_time(parsed.range_end) == "18.31.50"


def test_a_span_end_written_before_the_time_existed_still_reads():
    """N5's read-old/write-new rule, applied to the span: date-only parses.

    ``range_end_time`` says None rather than midnight, because a name that
    never carried a time is not a name claiming the span ends at 00.00.00.
    """
    parsed = stamps.split_dated_folder("2026-08-20_(Thu)__09.14.02#22 - Malbork")
    assert parsed.range_end == "#22"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-22"
    assert stamps.range_end_time(parsed.range_end) is None


def test_a_leaf_folder_has_no_span():
    parsed = stamps.split_dated_folder("2026-08-20_(Thu)__09.14.02 - Malbork")
    assert parsed.range_end is None
    assert stamps.range_end_time(parsed.range_end) is None


# --------------------------------------------------------------------------
# The tail (C1, C14, C15)
# --------------------------------------------------------------------------

def test_a_group_name_is_built_from_a_prefix_a_count_and_a_description():
    built = grouping.group_name(
        "2026-08-20_(Thu)__09.14.02#27__18.31.50", 7, "Norway")
    assert built == NORWAY


def test_a_group_with_no_description_carries_marker_and_count_alone():
    assert grouping.group_name("2026-07-15_(Wed)__08.14.02#15__19.02.44", 3) == (
        "2026-07-15_(Wed)__08.14.02#15__19.02.44 - ____GROUP____(d=3)")


def test_zero_children_is_written_as_no_bracket_at_all():
    """A folder with no dated children is not a group; "(d=0)" would claim it is."""
    assert grouping.group_suffix(0) == ""
    assert grouping.group_suffix(7) == "(d=7)"


def test_the_marker_is_recognised_and_the_description_read_back():
    assert grouping.carries_group_marker(NORWAY)
    assert grouping.group_description(NORWAY) == "Norway"
    assert grouping.split_group_tail(
        " - ____GROUP____(d=7) - Norway") == (7, "Norway")


def test_a_description_carrying_its_own_separator_comes_back_whole():
    name = "2026-08-20_(Thu)__09.14.02#27__18.31.50 - ____GROUP____(d=7) - Norway - day 2"
    assert grouping.group_description(name) == "Norway - day 2"


def test_a_tail_with_no_bracket_reports_an_unknown_count_not_zero():
    assert grouping.split_group_tail(" - ____GROUP____") == (None, None)


@pytest.mark.parametrize("name", [
    "2026-07-15_(Wed)__08.14.02 - Sopot weekend",
    "2026-07-18_(Sat)__11.03.27 - __TO_SPLIT__(i=79_v=2)",
    "2026-07-16_(Thu)__09.10.44 - __TO_LABEL__",
    "__EMPTY_SUBFOLDERS",
])
def test_nothing_else_is_mistaken_for_a_group(name):
    assert not grouping.carries_group_marker(name)
    assert grouping.group_description(name) is None


def test_the_legacy_marker_is_read_and_flagged_for_conversion():
    """C15/N13: "__CONTAINER__" is read, never written, and says so."""
    legacy = "2026-08-20_(Thu)__09.14.02#22 - __CONTAINER__(d=3) - Malbork trip"
    assert grouping.carries_group_marker(legacy)
    assert grouping.carries_legacy_group_marker(legacy)
    assert grouping.group_description(legacy) == "Malbork trip"
    assert not grouping.carries_legacy_group_marker(NORWAY)


def test_converting_a_legacy_name_keeps_the_description_and_the_count():
    legacy = "2026-08-20_(Thu)__09.14.02#22 - __CONTAINER__(d=3) - Malbork trip"
    children, description = grouping.split_group_tail(
        legacy[legacy.index(grouping.LABEL_SEPARATOR):])
    rebuilt = grouping.group_name(
        "2026-08-20_(Thu)__09.14.02#22__17.40.11", children, description)
    assert rebuilt == (
        "2026-08-20_(Thu)__09.14.02#22__17.40.11 - ____GROUP____(d=3) - Malbork trip")
    assert not grouping.carries_legacy_group_marker(rebuilt)


# --------------------------------------------------------------------------
# Both ends of the span come off the files (C5, C8)
# --------------------------------------------------------------------------

def test_the_two_ends_are_read_off_the_leading_stamps():
    names = [
        "2026-08-21_(Fri)__07.30.11__f1.7__SG23U.jpg",
        "2026-08-20_(Thu)__09.14.02__f1.7__SG23U.jpg",
        "2026-08-27_(Sat)__18.31.50__f1.7__SG23U.jpg",
    ]
    assert grouping.earliest_capture_time(names) == datetime.datetime(2026, 8, 20, 9, 14, 2)
    assert grouping.latest_capture_time(names) == datetime.datetime(2026, 8, 27, 18, 31, 50)


def test_only_the_leading_stamp_counts_at_either_end():
    """A grouper-mangled name can carry a second, later stamp trailing it."""
    names = ["2026-08-20_(Thu)__09.14.02__SCR__2027-01-01_(Fri)__23.59.59.jpg"]
    assert grouping.latest_capture_time(names) == datetime.datetime(2026, 8, 20, 9, 14, 2)


def test_an_unstamped_file_is_ignored_rather_than_guessed_at():
    assert grouping.latest_capture_time(["__TO_RENAME__VID_0034.mp4"]) is None
    assert grouping.earliest_capture_time([]) is None


# --------------------------------------------------------------------------
# Correcting a prefix time that no longer names anything in the folder (N3)
# --------------------------------------------------------------------------

MORNING = ["2026-07-15_(Wed)__09.30.00__f1.7__SG23U.jpg"]


def test_a_time_that_disagrees_with_the_earliest_file_is_replaced():
    assert grouping.with_corrected_time(
        "2026-07-15_(Wed)__08.00.00", MORNING) == "2026-07-15_(Wed)__09.30.00"


def test_a_prefix_with_no_time_still_gains_one():
    assert grouping.with_corrected_time(
        "2026-07-15_(Wed)", MORNING) == "2026-07-15_(Wed)__09.30.00"


def test_the_date_and_the_weekday_are_never_touched():
    """N6: only the time half may ever be derived from the contents."""
    assert grouping.with_corrected_time(
        "2026-07-15_(Wed)__08.00.00",
        ["2026-07-16_(Thu)__02.15.00__f1.7.jpg"]) == "2026-07-15_(Wed)__02.15.00"


def test_a_prefix_carrying_a_span_is_left_to_the_run_that_owns_both_ends():
    """C11: a group's start and end move together, never one at a time."""
    span = "2026-08-20_(Thu)__09.14.02#27__18.31.50"
    assert grouping.with_corrected_time(span, MORNING) == span


def test_a_folder_with_nothing_stamped_in_it_keeps_what_it_says():
    assert grouping.with_corrected_time(
        "2026-07-15_(Wed)__08.00.00", []) == "2026-07-15_(Wed)__08.00.00"


def test_a_capture_the_day_after_is_one_the_folder_may_hold():
    """N7: the small hours belong to the previous day's folder."""
    assert grouping.earliest_outside_its_day(
        "2026-07-15_(Wed)__08.00.00", ["2026-07-16_(Thu)__02.15.00.jpg"]) is None


def test_a_capture_from_another_year_is_not_one_it_may_hold():
    stray = ["2019-03-02_(Sat)__11.00.00.jpg"]
    assert grouping.earliest_outside_its_day(
        "2026-07-15_(Wed)__08.00.00", stray) == datetime.datetime(2019, 3, 2, 11, 0)
    # And it renames nothing: one misfiled file must not retime a whole day.
    assert grouping.with_corrected_time(
        "2026-07-15_(Wed)__08.00.00", stray) == "2026-07-15_(Wed)__08.00.00"


def test_a_capture_the_day_before_is_not_one_it_may_hold_either():
    assert grouping.earliest_outside_its_day(
        "2026-07-15_(Wed)__08.00.00",
        ["2026-07-14_(Tue)__23.00.00.jpg"]) == datetime.datetime(2026, 7, 14, 23, 0)


def test_the_day_a_prefix_names_is_read_off_it():
    assert grouping.prefix_day("2026-07-15_(Wed)__08.00.00") == datetime.date(2026, 7, 15)
    assert grouping.prefix_day("2026-02-31_(Wed)") is None
    assert grouping.prefix_day("07. July") is None
