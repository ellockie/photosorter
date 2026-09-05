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


# The end of a group's span (C6-C9). Two shapes, and which one is written is
# decided by one question -- does the span cross a day?
#
#   "#17.47.04"                    ends the day it starts: the time alone
#   "#2026-08-16_(Sun)__19.02.44"  ends on another day: the whole canonical stamp
#
# Either nothing about the date or all of it. A same-day group repeating its
# own date said nothing the start had not already said two characters to the
# left, and a cross-day one abbreviating it ("#16") made the reader carry the
# start's year and month across the "#" to work out which day was meant. The
# weekday comes with the full form for the same reason the start carries one:
# a bare date is not a day anybody reads at a glance.
#
# Read-old/write-new (N5). Every earlier shape still parses and none is written
# again: the abbreviated tails "#22" (same year and month) and "#09-11" (same
# year), the full "#2027-01-03" with no weekday, and any of those with the time
# missing, which is how a span written before v0.9 looks.
# ``format_range_end`` is the only thing here that writes one.
#
# The time-only branch is tried FIRST, and that ordering is load-bearing:
# "#17.47.04" offered to the date branch matches "#17" and leaves ".47.04"
# behind as tail, silently reading a time as the 17th of the month.
RANGE_END_PATTERN = (
    rf"#(?:({TIME_PATTERN})"
    r"|(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})"
    rf"(?:{DATE_TIME_SEPARATOR_PATTERN}({TIME_PATTERN}))?)"
)

# A dated folder's whole prefix: the date, the decorative weekday, the canonical
# time when the folder carries one, and the span end when it covers more than a
# day. Everything after it is the tail, whose grammar belongs to
# ``grouping_names``, not here.
DATED_FOLDER_RE = re.compile(
    rf"^({DATE_PATTERN})(?:[ _]+\([A-Za-z]{{3}}\))?(?:[ _]+({TIME_PATTERN}))?"
    rf"(?:({RANGE_END_PATTERN}))?"
)


class DatedFolder(NamedTuple):
    """The parsed prefix of a dated folder name."""

    date: str                 # YYYY-MM-DD, always the *start* of the span
    time: str | None          # HH.MM.SS, or None for a date-only prefix
    range_end: str | None     # the raw "#..." span end, or None when it states none
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
    return DatedFolder(match.group(1), match.group(2), match.group(3),
                       name[match.end():])


def resolve_range_end(start_date: str, range_end: str | None) -> str | None:
    """The ``YYYY-MM-DD`` a ``#`` span end names, or None when there is no span.

    A time-only end says the span closes the day it opened, so it resolves to
    ``start_date`` itself -- that is what makes writing the date there
    unnecessary. The full form carries its own date and needs no start to read.

    The abbreviated forms are still expanded against the start for the archive
    written before this: ``2026-08-20`` + ``#22`` -> ``2026-08-22``, ``#09-11``
    -> ``2026-09-11``, ``#2027-01-03`` -> itself.
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
    """The ``#`` span end for a group starting on ``start_date`` (C6-C9).

    The time alone when the span ends on the day it began, and the whole
    canonical stamp when it does not -- literally ``format_stamp``, so the two
    ends of a span are written in one grammar and a reader meets the same shape
    either side of the ``#``.
    """
    if f"{end:%Y-%m-%d}" == start_date:
        return f"#{end:%H.%M.%S}"
    return f"#{format_stamp(end)}"
