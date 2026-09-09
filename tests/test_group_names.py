"""The group grammar: the marker, the count, the span with a time on both ends.

ARCHIVE_STANDARD.md section 3::

    2026-08-14_(Fri)__09.31.29 __GROUP[ Polska ] ___2026-08-20_(Thu)__11.06.58_(n=31)

The stamps at either end are ``stamps``' grammar and the arrangement around
them is ``grouping_names``', so these are the tests that hold the seam between
the two modules: building a name out of both and reading it back.

The pre-v1.1 shape -- the span welded to the start stamp, the marker opening a
" - " tail, "(d=N)" for the count -- is read here too and written nowhere. Most
of the archive is still in it.
"""

import datetime

import pytest

from src.pipeline_stages import grouping_names as grouping
from src.pipeline_stages import stamps


NORWAY = ("2026-08-20_(Thu)__09.14.02 __GROUP[ Norway ]"
          " ___2026-08-27_(Thu)__18.31.50_(n=7)")

LEGACY_NORWAY = ("2026-08-20_(Thu)__09.14.02#2026-08-27_(Thu)__18.31.50"
                 " - ____GROUP____(d=7) - Norway")


# --------------------------------------------------------------------------
# The span end (C6-C9)
# --------------------------------------------------------------------------

def test_a_span_ending_the_day_it_starts_writes_the_time_alone():
    """C9: the start two characters to the left already said which day."""
    assert stamps.format_range_end(
        "2026-07-18", datetime.datetime(2026, 7, 18, 22, 14, 9)) == " ___22.14.09"


def test_a_span_crossing_a_day_writes_the_whole_stamp():
    """C7: all of the date or none of it, weekday included -- never a fragment."""
    next_day = stamps.format_range_end(
        "2026-08-20", datetime.datetime(2026, 8, 27, 18, 31, 50))
    assert next_day == " ___2026-08-27_(Thu)__18.31.50"

    next_month = stamps.format_range_end(
        "2026-08-20", datetime.datetime(2026, 9, 11, 7, 0, 1))
    assert next_month == " ___2026-09-11_(Fri)__07.00.01"

    next_year = stamps.format_range_end(
        "2026-12-28", datetime.datetime(2027, 1, 3, 17, 2, 0))
    assert next_year == " ___2027-01-03_(Sun)__17.02.00"


def test_the_two_ends_of_a_span_are_written_in_one_grammar():
    """A cross-day end IS a canonical stamp, so the reader meets one shape."""
    end = datetime.datetime(2026, 8, 27, 18, 31, 50)
    assert (stamps.format_range_end("2026-08-20", end)
            == stamps.RANGE_END_SEPARATOR + stamps.format_stamp(end))


def test_the_end_closes_the_name_and_the_start_still_opens_it():
    """C6/C10: the machinery moved to the back so the description could move up.

    Welded to the start, the end put the longest run of digits in the name
    where the eye lands first. Alphabetical order still has to come out
    chronological, so what moved is the end and only the end.
    """
    assert NORWAY.startswith("2026-08-20_(Thu)__09.14.02 ")
    assert NORWAY.endswith(" ___2026-08-27_(Thu)__18.31.50_(n=7)")
    assert stamps.split_dated_folder(NORWAY).time == "09.14.02"


def test_a_span_end_carries_its_day_and_time_back_out_again():
    parsed = stamps.split_dated_folder(NORWAY)
    assert parsed.date == "2026-08-20"
    assert parsed.time == "09.14.02"
    assert parsed.range_end == " ___2026-08-27_(Thu)__18.31.50"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-27"
    assert stamps.range_end_time(parsed.range_end) == "18.31.50"


def test_an_end_welded_to_the_start_reads_exactly_the_same_way():
    """N5: where the end was written says nothing about what it means."""
    parsed = stamps.split_dated_folder(LEGACY_NORWAY)
    assert parsed.range_end == "#2026-08-27_(Thu)__18.31.50"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-27"
    assert stamps.range_end_time(parsed.range_end) == "18.31.50"


def test_a_time_only_end_resolves_to_the_day_the_span_started():
    name = "2026-08-14_(Fri)__13.40.23 __GROUP[ Kajaki ] ___17.47.04_(n=3)"
    parsed = stamps.split_dated_folder(name)
    assert parsed.range_end == " ___17.47.04"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-14"
    assert stamps.range_end_time(parsed.range_end) == "17.47.04"
    assert parsed.tail == " __GROUP[ Kajaki ] ___17.47.04_(n=3)"


def test_a_time_is_never_read_as_a_day_of_the_month():
    """The whole reason the time-only branch is tried first.

    Offered to the date branch, "#17.47.04" matches "#17" and leaves ".47.04"
    standing as tail -- a 17:47 span end silently becoming the 17th.
    """
    parsed = stamps.split_dated_folder(
        "2026-08-14_(Fri)__13.40.23 __GROUP[ Kajaki ] ___17.47.04_(n=2)")
    assert parsed.range_end == " ___17.47.04"
    assert stamps.range_end_time(parsed.range_end) == "17.47.04"
    assert stamps.resolve_range_end(parsed.date, parsed.range_end) == "2026-08-14"

    welded = stamps.split_dated_folder(
        "2026-08-14_(Fri)__13.40.23#17.47.04 - ____GROUP____(d=2)")
    assert welded.range_end == "#17.47.04"
    assert not welded.tail.startswith(".")


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
# The name around the stamps (C1, C14, C15, C15a)
# --------------------------------------------------------------------------

def test_a_group_name_is_built_from_a_prefix_a_count_and_a_description():
    built = grouping.group_name(
        "2026-08-20_(Thu)__09.14.02", 7, "Norway",
        " ___2026-08-27_(Thu)__18.31.50")
    assert built == NORWAY


def test_a_group_with_no_description_is_written_asking_for_one():
    """C16/N11: the brackets never come off, so a waiting group looks like one.

    The alternative -- marker and count with nothing between them -- says the
    same thing by saying nothing, and reads in Explorer as a folder simply
    named that way.
    """
    assert grouping.group_name(
        "2026-07-15_(Wed)__08.14.02", 3, range_end=" ___19.02.44") == (
        "2026-07-15_(Wed)__08.14.02 __GROUP[ __TO_LABEL__ ] ___19.02.44_(n=3)")


def test_zero_children_is_written_as_no_bracket_at_all():
    """A folder with no dated children is not a group; "_(n=0)" would claim it is.

    The separator comes with the bracket rather than sitting between it and the
    span end, so "no bracket" leaves nothing dangling off the name.
    """
    assert grouping.group_suffix(0) == ""
    assert grouping.group_suffix(7) == "_(n=7)"


def test_the_count_is_divided_off_the_span_end_it_follows():
    """A bracket opening straight off the seconds reads as part of the time."""
    assert grouping.group_name(
        "2026-07-18_(Sat)__11.03.27", 2, "pier", " ___22.14.09") == (
        "2026-07-18_(Sat)__11.03.27 __GROUP[ pier ] ___22.14.09_(n=2)")
    # Read-old/write-new reaches the separator too: a name written without one
    # still reports its count rather than losing it.
    assert grouping.split_group_name(
        "2026-07-18_(Sat)__11.03.27 __GROUP[ pier ] ___22.14.09(n=2)"
    ).children == 2


def test_the_count_letter_says_children_rather_than_days():
    """A group's children are as often sub-events of one day as days of a trip.

    "(d=4)" on a Saturday split into four hours claimed four days; "n" claims
    only that four nested dated folders are in there, which is all a group
    counts.
    """
    assert grouping.COUNT_LETTERS[0] == "n"
    assert "d" not in grouping.COUNT_LETTERS
    assert grouping.LEGACY_COUNT_LETTERS == ("d",)


def test_the_marker_is_recognised_and_the_description_read_back():
    assert grouping.carries_group_marker(NORWAY)
    assert grouping.group_description(NORWAY) == "Norway"
    assert grouping.split_group_name(NORWAY) == (
        "2026-08-20_(Thu)__09.14.02", "Norway",
        " ___2026-08-27_(Thu)__18.31.50", 7, False)


def test_a_name_in_the_older_shape_is_read_apart_into_the_same_pieces():
    """C15a: two conventions, one reading -- and the older one says so."""
    assert grouping.split_group_name(LEGACY_NORWAY) == (
        "2026-08-20_(Thu)__09.14.02", "Norway",
        "#2026-08-27_(Thu)__18.31.50", 7, True)


def test_a_description_carrying_its_own_separator_comes_back_whole():
    name = ("2026-08-20_(Thu)__09.14.02 __GROUP[ Norway - day 2 ]"
            " ___27__18.31.50_(n=7)")
    assert grouping.group_description(name) == "Norway - day 2"
    legacy = ("2026-08-20_(Thu)__09.14.02#27__18.31.50"
              " - ____GROUP____(d=7) - Norway - day 2")
    assert grouping.group_description(legacy) == "Norway - day 2"


def test_a_name_with_no_bracket_reports_an_unknown_count_not_zero():
    """None is "nobody has counted", which is not the claim "there are none"."""
    hand_typed = "2026-08-20_(Thu)__09.14.02 __GROUP[ Norway ]"
    assert grouping.split_group_name(hand_typed).children is None
    assert grouping.split_group_name(hand_typed).range_end is None
    assert grouping.split_group_name(
        "2026-08-20_(Thu)__09.14.02 - ____GROUP____").children is None


def test_a_marker_with_no_date_in_front_of_it_is_not_a_group():
    """C1 is about a *dated* folder; a bare tail is not a folder name at all."""
    assert grouping.split_group_name(" - ____GROUP____") is None
    assert grouping.split_group_name("__GROUP[ Norway ] ___17.47.04_(n=2)") is None


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

UNNAMED = ("2026-08-20_(Thu)__09.14.02 __GROUP[ __TO_LABEL__ ]"
           " ___27__18.31.50_(n=7)")


def test_the_question_marker_is_not_read_as_a_description():
    """Were it read as one, T7 would make the one replaceable word permanent."""
    assert grouping.group_description(UNNAMED) is None
    assert grouping.carries_group_marker(UNNAMED)
    # The raw grammar still reports what is written there: it parses, it judges
    # nothing. Only ``group_description`` answers "did a person name this".
    assert grouping.split_group_name(UNNAMED).description == "__TO_LABEL__"


@pytest.mark.parametrize("name, waiting", [
    (UNNAMED, True),
    ("2026-07-16_(Thu)__09.10.44 - __TO_LABEL__", True),        # a leaf day
    ("2026-08-20_(Thu)__09.14.02#27__18.31.50"
     " - ____GROUP____(d=7) - __TO_LABEL__", True),             # the older shape
    (NORWAY, False),
    (LEGACY_NORWAY, False),
    ("2026-08-20_(Thu)__09.14.02#27__18.31.50 - ____GROUP____(d=7)", False),
    ("2026-07-15_(Wed)__08.14.02 - Sopot weekend", False),
    ("07. July", False),
])
def test_a_folder_says_whether_it_is_still_waiting_for_a_name(name, waiting):
    assert grouping.awaits_label(name) is waiting


@pytest.mark.parametrize("name, description", [
    (NORWAY, "Norway"),
    (LEGACY_NORWAY, "Norway"),
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
        "2026-07-16_(Thu)__09.10.44 __GROUP[ Sopot ] ___19.02.44_(n=2)",
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


@pytest.mark.parametrize("legacy", [
    # C15/N13: the standard's own v0.8 proposal, which no tool ever wrote.
    "2026-08-20_(Thu)__09.14.02#22 - __CONTAINER__(d=3) - Malbork trip",
    # C15a: v0.9-v1.0, which wrote most of the archive.
    "2026-08-20_(Thu)__09.14.02#22 - ____GROUP____(d=3) - Malbork trip",
])
def test_every_older_shape_is_read_and_flagged_for_conversion(legacy):
    assert grouping.carries_group_marker(legacy)
    assert grouping.carries_legacy_group_marker(legacy)
    assert grouping.group_description(legacy) == "Malbork trip"
    assert not grouping.carries_legacy_group_marker(NORWAY)


def test_converting_a_legacy_name_keeps_the_description_and_the_count():
    """T7: the stamps and the count are the tool's; the description is theirs."""
    legacy = "2026-08-20_(Thu)__09.14.02#22 - __CONTAINER__(d=3) - Malbork trip"
    parsed = grouping.split_group_name(legacy)
    rebuilt = grouping.group_name(
        parsed.base, parsed.children, parsed.description, " ___22__17.40.11")
    assert rebuilt == (
        "2026-08-20_(Thu)__09.14.02 __GROUP[ Malbork trip ] ___22__17.40.11_(n=3)")
    assert not grouping.carries_legacy_group_marker(rebuilt)
    assert grouping.group_description(rebuilt) == "Malbork trip"


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
