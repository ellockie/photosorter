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


# The end of a group's span (C6-C9): the shortest tail of a date that still
# says which day it is -- "#22" (same year and month), "#09-11" (same year) or
# "#2027-01-03" -- followed by the time of the subtree's latest file. The
# number of date fields disambiguates, so nothing is guessed.
#
# The time is optional *to read* and required to write. A span written before
# v0.9 carries a date and no time, and one typed by hand may too; both must
# still parse, the same read-old/write-new rule as N5. ``format_range_end`` is
# the only thing here that writes one, and it always writes the time.
RANGE_END_PATTERN = (
    r"#(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})"
    rf"(?:__({TIME_PATTERN}))?"
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
    range_end: str | None     # the raw "#..." span end, or None for one day
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
    """Expand a ``#`` span end against its start date, or None.

    ``2026-08-20`` + ``#22`` -> ``2026-08-22``; ``#09-11`` -> ``2026-09-11``;
    ``#2027-01-03`` -> itself. Fields the end omits are taken from the start,
    which is the whole point of the short forms: the common case is a few days
    in one month and repeating the year and month there would only add noise.
    """
    if not range_end:
        return None
    match = re.fullmatch(RANGE_END_PATTERN, range_end)
    if not match:
        return None
    year, month, day, _time = match.groups()
    start_year, start_month, _ = start_date.split("-")
    return f"{year or start_year}-{month or start_month}-{day}"


def range_end_time(range_end: str | None) -> str | None:
    """The ``HH.MM.SS`` half of a span end, or None when it carries none.

    None means the name predates C6 (or was typed by hand), not that the span
    ends at midnight -- which is why it is returned rather than defaulted.
    """
    if not range_end:
        return None
    match = re.fullmatch(RANGE_END_PATTERN, range_end)
    return match.group(4) if match else None


def format_range_end(start_date: str, end: datetime.datetime) -> str:
    """The ``#`` span end for a group starting on ``start_date`` (C6-C9).

    The date is trimmed to the shortest tail that still identifies the day --
    the year goes when it matches the start's, then the month -- and the time
    is always written. A span ending on the day it starts is written in full
    all the same (C9): one shape for a reader and for a parser, whether the
    group covers an afternoon or a fortnight.
    """
    start_year, start_month, _ = start_date.split("-")
    if f"{end:%Y}" != start_year:
        day = f"{end:%Y-%m-%d}"
    elif f"{end:%m}" != start_month:
        day = f"{end:%m-%d}"
    else:
        day = f"{end:%d}"
    return f"#{day}__{end:%H.%M.%S}"
