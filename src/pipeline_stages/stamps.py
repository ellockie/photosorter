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
