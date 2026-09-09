"""Canonical dated-name grammar shared by every stage that writes or reads one.

One place defines the timestamp form so a change to the convention cannot leave
half the pipeline writing names the other half fails to parse.

Canonical form (matches the screenshot grouper's own convention):

    2026-08-14_(Fri)__15.32.01        <- double underscore before the time

Historical forms still parsed, so an archive written by an earlier version keeps
working and its files keep matching their sidecars:

    2026-08-14_(Fri)_15.32.01         single underscore (previous Photosorter)
    2026-08-14__15.32.01              no weekday (legacy grouper)

The weekday abbreviations are fixed English, never ``strftime("%a")``: that
follows the system locale, so a Polish-locale Windows would silently start
writing "2026-08-14_(pt)__15.32.01" and every regex here would stop matching.
"""

import datetime
import re
from typing import NamedTuple

WEEKDAY_ABBR = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Human-readable descriptor of the canonical form, for logs and prompts.
STAMP_FORMAT_DESCRIPTOR = "YYYY-MM-DD_(Ddd)__HH.MM.SS"

DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"
TIME_PATTERN = r"\d{2}\.\d{2}\.\d{2}"
# Every separator ever written between the date and the time halves.
DATE_TIME_SEPARATOR_PATTERN = r"(?:[ _]+\([A-Za-z]{3}\))?[ _]+"

STAMP_PATTERN = rf"{DATE_PATTERN}{DATE_TIME_SEPARATOR_PATTERN}{TIME_PATTERN}"
# (year, month, day, hour, minute, second)
STAMP_CAPTURE_PATTERN = (
    r"(\d{4})-(\d{2})-(\d{2})"
    rf"{DATE_TIME_SEPARATOR_PATTERN}"
    r"(\d{2})\.(\d{2})\.(\d{2})"
)

STAMP_RE = re.compile(STAMP_CAPTURE_PATTERN)
LEADING_STAMP_RE = re.compile(rf"^{STAMP_CAPTURE_PATTERN}")
# Event/day folder prefix, e.g. "2026-08-14_(Fri)".
DAY_PREFIX_RE = re.compile(rf"^({DATE_PATTERN})(?:[ _]+\([A-Za-z]{{3}}\))?")


def format_day_prefix(value: datetime.datetime | datetime.date) -> str:
    """Return the dated folder prefix, e.g. ``2026-08-14_(Fri)``."""
    return f"{value:%Y-%m-%d}_({WEEKDAY_ABBR[value.weekday()]})"


def format_stamp(value: datetime.datetime) -> str:
    """Return the canonical timestamp, e.g. ``2026-08-14_(Fri)__15.32.01``."""
    return f"{format_day_prefix(value)}__{value:%H.%M.%S}"


def parse_stamp(text: str) -> datetime.datetime | None:
    """First timestamp in ``text`` in any accepted form, or None.

    The weekday is decorative and never validated: a stale or wrong day name
    must not reject an otherwise valid stamp.
    """
    match = STAMP_RE.search(text)
    if not match:
        return None
    try:
        return datetime.datetime(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def stamp_keys(name: str) -> list[str]:
    """Every timestamp in ``name`` as a bare ``YYYYMMDDHHMMSS`` key, in order.

    A name can carry more than one: the grouper may prefix a file with its own
    timestamp while keeping the Photosorter name as trailing text
    ("2026-07-19__21.29.04__SCR__2026-07-19_(Sun)_15.37.10__f1.7…"). Indexing a
    representative under *all* of them is what lets its sidecar — which carries
    only the original stamp — still find it.
    """
    return ["".join(match.groups()) for match in STAMP_RE.finditer(name)]


def leading_stamp_key(name: str) -> str | None:
    """The ``YYYYMMDDHHMMSS`` key a name *opens* with, or None."""
    match = LEADING_STAMP_RE.match(name)
    return "".join(match.groups()) if match else None


def day_prefix(name: str) -> str | None:
    """The ``YYYY-MM-DD`` a folder or file name opens with, or None."""
    match = DAY_PREFIX_RE.match(name)
    return match.group(1) if match else None


# The sub-second a camera recorded, appended to the time half of a *file* stamp
# (F9). Folders never carry one: N3 dates a folder from its earliest file, and
# a fraction of a second is not a fact about an event.
#
#   2026-08-21_(Fri)__20.43.52.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg
#
# Written only to separate two shots that landed in the same second (F9), never
# by default. Two reasons it is not on every name: the second-precision form is
# the convention the screenshot grouper shares, and a stamp is the archive's
# join key (F1) -- a value written everywhere is a value every existing name
# would have to be rewritten to carry.
#
# The join key survives it. ``STAMP_RE`` stops at the seconds and the fraction
# is left as trailing text, so ``stamp_keys`` and ``leading_stamp_key`` answer
# the same ``YYYYMMDDHHMMSS`` for a file with a sub-second as for one without:
# a sidecar or RAW that carries only the second still finds its subject.
SUBSECOND_SEPARATOR = "."
SUBSECOND_PATTERN = r"\d{1,6}"

# The leading stamp of a *file*, with the optional fraction consumed rather
# than left behind -- which is what makes ``apply_subsecond`` replace one
# instead of appending a second.
LEADING_FILE_STAMP_RE = re.compile(
    rf"^{STAMP_PATTERN}(?:{re.escape(SUBSECOND_SEPARATOR)}({SUBSECOND_PATTERN}))?"
)


def normalise_subsecond(value: str | int | None) -> str | None:
    """The digits of a ``SubSecTimeOriginal``, or None when it says nothing.

    ExifTool hands back the fraction as the camera wrote it -- "633", "43",
    sometimes padded or trailed by whitespace. The digits are kept exactly as
    recorded rather than scaled to a fixed width: the value's only job is to
    differ from the neighbouring shot's, and rescaling it would be inventing
    precision the camera did not claim (V4). A non-numeric or empty value is
    no value at all.
    """
    if value is None:
        return None
    digits = str(value).strip()
    return digits if digits.isdigit() else None


def leading_subsecond(name: str) -> str | None:
    """The fraction a file name's leading stamp carries, or None."""
    match = LEADING_FILE_STAMP_RE.match(name)
    return match.group(1) if match else None


def apply_subsecond(name: str, subsecond: str | int | None) -> str:
    """``name`` with ``subsecond`` on its leading stamp, replacing any already there.

    A name whose leading stamp does not parse is returned untouched: nothing
    here may invent the timestamp F1 calls the archive's join key.
    """
    digits = normalise_subsecond(subsecond)
    match = LEADING_FILE_STAMP_RE.match(name)
    if match is None:
        return name
    stamp = name[:match.end()]
    if match.group(1):
        stamp = stamp[:-(len(match.group(1)) + len(SUBSECOND_SEPARATOR))]
    if digits:
        stamp += SUBSECOND_SEPARATOR + digits
    return stamp + name[match.end():]


# Where a group's span end sits, and what opens it (C6).
#
# Up to v1.0 the end was welded to the start -- "…__09.31.29#2026-08-20…" --
# which put the longest, most machine-looking half of the name where a reader's
# eye lands first and pushed the one word a person cares about, the
# description, off the end of the column. Since v1.1 the end closes the name
# instead, opened by " ___":
#
#   2026-08-14_(Fri)__09.31.29 __GROUP[ Polska ] ___2026-08-20_(Thu)__11.06.58_(n=31)
#
# Three underscores, one more than the marker's two, so the two separators
# cannot be misread for each other and the end is still visibly machinery. The
# "#" opener is read forever and never written again (N5, C15a).
RANGE_END_SEPARATOR = " ___"
LEGACY_RANGE_END_SEPARATOR = "#"

# The end itself. Two shapes, and which one is written is decided by one
# question -- does the span cross a day?
#
#   " ___17.47.04"                    ends the day it starts: the time alone
#   " ___2026-08-16_(Sun)__19.02.44"  ends on another day: the whole canonical stamp
#
# Either nothing about the date or all of it. A same-day group repeating its
# own date said nothing the start had not already said, and a cross-day one
# abbreviating it ("#16") made the reader carry the start's year and month
# across the separator to work out which day was meant. The weekday comes with
# the full form for the same reason the start carries one: a bare date is not a
# day anybody reads at a glance.
#
# Read-old/write-new (N5). Every earlier shape still parses and none is written
# again: the "#" opener wherever it sits, the abbreviated tails "#22" (same year
# and month) and "#09-11" (same year), the full "#2027-01-03" with no weekday,
# and any of those with the time missing, which is how a span written before
# v0.9 looks. ``format_range_end`` is the only thing here that writes one.
#
# The time-only branch is tried FIRST, and that ordering is load-bearing:
# "#17.47.04" offered to the date branch matches "#17" and leaves ".47.04"
# behind as tail, silently reading a time as the 17th of the month.
#
# One body, three openers: the opener is the only thing that differs between a
# span end read anywhere, one read welded to the prefix, and one read closing
# the name, so it is the only thing spelled three times. The capture groups are
# identical in all three, which is what lets ``resolve_range_end`` and
# ``range_end_time`` read whichever a caller hands them.
_RANGE_END_BODY_PATTERN = (
    rf"(?:({TIME_PATTERN})"
    r"|(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})"
    rf"(?:{DATE_TIME_SEPARATOR_PATTERN}({TIME_PATTERN}))?)"
)
RANGE_END_PATTERN = (
    rf"(?:{re.escape(RANGE_END_SEPARATOR)}|{LEGACY_RANGE_END_SEPARATOR})"
    rf"{_RANGE_END_BODY_PATTERN}"
)
# Welded to the prefix: the pre-v1.1 position, read and never written.
_PREFIX_RANGE_END_PATTERN = (
    rf"{LEGACY_RANGE_END_SEPARATOR}{_RANGE_END_BODY_PATTERN}")
# Closing the name: the v1.1 position. The bracket that may follow it is
# ``grouping_names``' grammar, not this module's, so it is matched loosely --
# all that is needed here is to know the end is still the last thing but one.
_CLOSING_RANGE_END_RE = re.compile(
    rf"({re.escape(RANGE_END_SEPARATOR)}{_RANGE_END_BODY_PATTERN})"
    r"(?:_?\([A-Za-z]+=\d+\))?$")

# A dated folder's whole prefix: the date, the decorative weekday, the canonical
# time when the folder carries one, and -- on a name written before v1.1 -- the
# span end welded to it. Everything after it is the tail, whose grammar belongs
# to ``grouping_names``, not here.
DATED_FOLDER_RE = re.compile(
    rf"^({DATE_PATTERN})(?:[ _]+\([A-Za-z]{{3}}\))?(?:[ _]+({TIME_PATTERN}))?"
    rf"(?:({_PREFIX_RANGE_END_PATTERN}))?"
)


class DatedFolder(NamedTuple):
    """The parsed prefix of a dated folder name."""

    date: str                 # YYYY-MM-DD, always the *start* of the span
    time: str | None          # HH.MM.SS, or None for a date-only prefix
    range_end: str | None     # the raw span end with its opener, or None for no span
    tail: str                 # everything after the prefix, unparsed


def split_dated_folder(name: str) -> DatedFolder | None:
    """The prefix of a dated folder name, or None if it is not one.

    The time and the span end are optional, and the tail is returned unparsed:
    a caller that cares which *kind* of tail it is asks ``grouping_names``.
    Splitting here rather than in each caller is what keeps a folder written in
    the canonical timed form (``2026-07-15_(Wed)__08.14.02 - Sopot``) readable
    by tools that predate the time — or the span — being there.
    """
    match = DATED_FOLDER_RE.match(name)
    if not match:
        return None
    tail = name[match.end():]
    range_end = match.group(3)
    if range_end is None:
        # v1.1: the end closes the name rather than the prefix. Looked for only
        # when the prefix carried none, so a legacy name is never read twice
        # and a folder cannot end up claiming two different spans.
        closing = _CLOSING_RANGE_END_RE.search(tail)
        if closing is not None:
            range_end = closing.group(1)
    return DatedFolder(match.group(1), match.group(2), range_end, tail)


def resolve_range_end(start_date: str, range_end: str | None) -> str | None:
    """The ``YYYY-MM-DD`` a span end names, or None when there is no span.

    A time-only end says the span closes the day it opened, so it resolves to
    ``start_date`` itself -- that is what makes writing the date there
    unnecessary. The full form carries its own date and needs no start to read.

    The abbreviated forms are still expanded against the start for the archive
    written before this: ``2026-08-20`` + ``#22`` -> ``2026-08-22``, ``#09-11``
    -> ``2026-09-11``, ``#2027-01-03`` -> itself. Either opener is accepted --
    the position an end was written in says nothing about what it means.
    """
    if not range_end:
        return None
    match = re.fullmatch(RANGE_END_PATTERN, range_end)
    if not match:
        return None
    same_day, year, month, day, _time = match.groups()
    if same_day is not None:
        return start_date
    start_year, start_month, _ = start_date.split("-")
    return f"{year or start_year}-{month or start_month}-{day}"


def range_end_time(range_end: str | None) -> str | None:
    """The ``HH.MM.SS`` half of a span end, or None when it carries none.

    None means the name predates C6 (or was typed by hand), not that the span
    ends at midnight -- which is why it is returned rather than defaulted. Only
    a legacy end can answer None: both forms written today carry the time, and
    the same-day one is nothing else.
    """
    if not range_end:
        return None
    match = re.fullmatch(RANGE_END_PATTERN, range_end)
    if not match:
        return None
    return match.group(1) or match.group(5)


def format_range_end(start_date: str, end: datetime.datetime) -> str:
    """The span end for a group starting on ``start_date`` (C6-C9).

    The time alone when the span ends on the day it began, and the whole
    canonical stamp when it does not -- literally ``format_stamp``, so the two
    ends of a span are written in one grammar and a reader meets the same shape
    at both ends of the name. Always opened by ``RANGE_END_SEPARATOR``; the
    ``#`` of the older convention is read and never written again.
    """
    if f"{end:%Y-%m-%d}" == start_date:
        return f"{RANGE_END_SEPARATOR}{end:%H.%M.%S}"
    return f"{RANGE_END_SEPARATOR}{format_stamp(end)}"
