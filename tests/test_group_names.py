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


NORWAY = ("2026-08-20_(Thu)__09.14.02#2026-08-27_(Thu)__18.31.50"
          " - ____GROUP____(d=7) - Norway")


# --------------------------------------------------------------------------
# The span end (C6-C9)
# --------------------------------------------------------------------------

def test_a_span_ending_the_day_it_starts_writes_the_time_alone():
    """C9: the start two characters to the left already said which day."""
    assert stamps.format_range_end(
        "2026-07-18", datetime.datetime(2026, 7, 18, 22, 14, 9)) == "#22.14.09"


def test_a_span_crossing_a_day_writes_the_whole_stamp():
    """C7: all of the date or none of it, weekday included -- never a fragment."""
    next_day = stamps.format_range_end(
        "2026-08-20", datetime.datetime(2026, 8, 27, 18, 31, 50))
    assert next_day == "#2026-08-27_(Thu)__18.31.50"

    next_month = stamps.format_range_end(
        "2026-08-20", datetime.datetime(2026, 9, 11, 7, 0, 1))
    assert next_month == "#2026-09-11_(Fri)__07.00.01"

    next_year = stamps.format_range_end(
        "2026-12-28", datetime.datetime(2027, 1, 3, 17, 2, 0))
    assert next_year == "#2027-01-03_(Sun)__17.02.00"


def test_the_two_ends_of_a_span_are_written_in_one_grammar():
    """A cross-day end IS a canonical stamp, so the reader meets one shape."""
    end = datetime.datetime(2026, 8, 27, 18, 31, 50)
    assert stamps.format_range_end("2026-08-20", end) == "#" + stamps.format_stamp(end)


def test_a_span_end_carries_its_day_and_time_back_out_again():
    parsed = stamps.split_dated_folder(NORWAY)
    assert parsed.date == "2026-08-20"
    assert parsed.time == "09.14.02"
    assert parsed.range_end == "#2026-08-27_(Thu)__18.31.50"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-27"
    assert stamps.range_end_time(parsed.range_end) == "18.31.50"


def test_a_time_only_end_resolves_to_the_day_the_span_started():
    name = "2026-08-14_(Fri)__13.40.23#17.47.04 - ____GROUP____(d=3) - Kajaki"
    parsed = stamps.split_dated_folder(name)
    assert parsed.range_end == "#17.47.04"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-14"
    assert stamps.range_end_time(parsed.range_end) == "17.47.04"
    assert parsed.tail == " - ____GROUP____(d=3) - Kajaki"


def test_a_time_is_never_read_as_a_day_of_the_month():
    """The whole reason the time-only branch is tried first.

    Offered to the date branch, "#17.47.04" matches "#17" and leaves ".47.04"
    standing as tail -- a 17:47 span end silently becoming the 17th.
    """
    parsed = stamps.split_dated_folder(
        "2026-08-14_(Fri)__13.40.23#17.47.04 - ____GROUP____(d=2)")
    assert parsed.range_end == "#17.47.04"
    assert not parsed.tail.startswith(".")


@pytest.mark.parametrize("name, day, time", [
    # N5 read-old/write-new: every shape written before this still parses.
    ("2026-08-20_(Thu)__09.14.02#27__18.31.50 - X", "2026-08-27", "18.31.50"),
    ("2026-08-20_(Thu)__09.14.02#09-11__18.31.50 - X", "2026-09-11", "18.31.50"),
    ("2026-12-28_(Mon)__09.14.02#2027-01-03__18.31.50 - X", "2027-01-03", "18.31.50"),
    # A span written before the time existed says None, not midnight: a name
    # that never carried a time is not one claiming the span ends at 00.00.00.
    ("2026-08-20_(Thu)__09.14.02#22 - Malbork", "2026-08-22", None),
])
def test_every_earlier_span_end_still_reads(name, day, time):
    parsed = stamps.split_dated_folder(name)
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == day
    assert stamps.range_end_time(parsed.range_end) == time


def test_a_leaf_folder_has_no_span():
    parsed = stamps.split_dated_folder("2026-08-20_(Thu)__09.14.02 - Malbork")
    assert parsed.range_end is None
    assert stamps.range_end_time(parsed.range_end) is None


# --------------------------------------------------------------------------
# The tail (C1, C14, C15)
# --------------------------------------------------------------------------

def test_a_group_name_is_built_from_a_prefix_a_count_and_a_description():
    built = grouping.group_name(
        "2026-08-20_(Thu)__09.14.02#2026-08-27_(Thu)__18.31.50", 7, "Norway")
    assert built == NORWAY


def test_a_group_with_no_description_carries_marker_and_count_alone():
    assert grouping.group_name("2026-07-15_(Wed)__08.14.02#19.02.44", 3) == (
        "2026-07-15_(Wed)__08.14.02#19.02.44 - ____GROUP____(d=3)")


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


# --------------------------------------------------------------------------
# N11 -- a group nobody has named
# --------------------------------------------------------------------------

UNNAMED = "2026-08-20_(Thu)__09.14.02#27__18.31.50 - ____GROUP____(d=7) - __TO_LABEL__"


def test_the_question_marker_is_not_read_as_a_description():
    """Were it read as one, T7 would make the one replaceable word permanent."""
    assert grouping.group_description(UNNAMED) is None
    assert grouping.carries_group_marker(UNNAMED)
    # The raw grammar still reports what is written there: it parses, it judges
    # nothing. Only ``group_description`` answers "did a person name this".
    assert grouping.split_group_tail(
        " - ____GROUP____(d=7) - __TO_LABEL__") == (7, "__TO_LABEL__")


@pytest.mark.parametrize("name, waiting", [
    (UNNAMED, True),
    ("2026-07-16_(Thu)__09.10.44 - __TO_LABEL__", True),        # a leaf day
    (NORWAY, False),
    ("2026-08-20_(Thu)__09.14.02#27__18.31.50 - ____GROUP____(d=7)", False),
    ("2026-07-15_(Wed)__08.14.02 - Sopot weekend", False),
    ("07. July", False),
])
def test_a_folder_says_whether_it_is_still_waiting_for_a_name(name, waiting):
    assert grouping.awaits_label(name) is waiting


@pytest.mark.parametrize("name, description", [
    (NORWAY, "Norway"),
    (UNNAMED, None),
    ("2026-08-20_(Thu)__09.14.02#27__18.31.50 - ____GROUP____(d=7)", None),
    ("2026-07-15_(Wed)__08.14.02 - Sopot weekend", "Sopot weekend"),
    ("2026-07-15_(Wed)__08.14.02 - 1. Sopot weekend", "Sopot weekend"),
    ("2026-07-18_(Sat)__11.03.27 - __TO_SPLIT__(i=79_v=2)", None),
    ("2026-07-16_(Thu)__09.10.44 - __TO_LABEL__", None),
    ("2026-07-15_(Wed) - 1. ######", None),
    ("2026-07-15_(Wed)__08.14.02", None),
])
def test_one_reading_of_whether_a_person_named_this_folder(name, description):
    """Group or leaf, the same question in the same words."""
    assert grouping.folder_description(name) == description


def test_children_that_all_say_the_same_thing_name_their_group():
    assert grouping.shared_child_description([
        "2026-07-15_(Wed)__08.14.02 - Sopot",
        "2026-07-15_(Wed)__14.31.09 - sopot",          # case is not a difference
        "2026-07-16_(Thu)__09.10.44 - ____GROUP____(d=2) - Sopot",
    ]) == "Sopot"                                      # the first one's spelling


@pytest.mark.parametrize("names", [
    # Two claims, not one.
    ["2026-07-15_(Wed)__08.14.02 - Sopot",
     "2026-07-15_(Wed)__14.31.09 - the pier"],
    # One child nobody has named: a group's name has to cover all of it.
    ["2026-07-15_(Wed)__08.14.02 - Sopot",
     "2026-07-15_(Wed)__14.31.09 - __TO_LABEL__"],
    ["2026-07-15_(Wed)__08.14.02 - Sopot",
     "2026-07-15_(Wed)__14.31.09 - __TO_SPLIT__(i=6)"],
    ["2026-07-15_(Wed)__08.14.02 - Sopot", "2026-07-15_(Wed)__14.31.09"],
    # Nothing to agree on.
    [],
])
def test_anything_short_of_agreement_names_nothing(names):
    assert grouping.shared_child_description(names) is None


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
