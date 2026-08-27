"""Canonical grammar for the grouping placeholder on event-folder names.

The companion of ``stamps.py``: that module owns the timestamp half of a folder
name, this one owns the suffix that says whether the day still needs reviewing.

Folder-sorting drops a day's photos into an event folder carrying the legacy
placeholder suffix::

    2026-07-15_(Wed) - 1. ######

Once it is known how much top-level media the day holds, the placeholder is
replaced by the grouper's own convention, which states the counts up front so
the size of the job is visible in Explorer before the GUI is opened. The day
prefix also picks up the time-of-day of its earliest photo, following the
canonical stamp convention (``stamps.py``) that every other dated name in the
archive already carries::

    2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=111)
    2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=79_v=3)

A labelled folder ("... - Lens tests") is already named by a human and never
carries either form.

This lives in its own leaf module, importing nothing from the project, for the
same two reasons ``stamps.py`` does: one definition means a change to the
convention cannot leave half the code writing names the other half fails to
recognise (``__TO_SPLIT__`` was already spelled out in two separate stages),
and a maintenance tool can load it by file path without dragging the whole
pipeline -- exiftool, the dashboard, the converters -- in behind it. A regular
``from src.pipeline_stages.stamps import ...`` would defeat that: importing a
submodule of ``src.pipeline_stages`` still runs that package's ``__init__``
first, which imports every stage. So the one bit of ``stamps`` grammar this
module needs -- recognising a *leading* timestamp -- is duplicated below
rather than imported, same as ``DEFAULT_DATE_FOLDER_SUFFIX`` already was.
"""

import datetime
import re
from pathlib import Path

TO_SPLIT_MARKER = "__TO_SPLIT__"

# Matches config.json legacy.date_folder_suffix; repeated here so the module
# stays loadable with no config in hand.
DEFAULT_DATE_FOLDER_SUFFIX = " - 1. ######"

# Matches stamps.LEADING_STAMP_RE: a leading "YYYY-MM-DD[_(Ddd)]_HH.MM.SS".
# Duplicated rather than imported -- see the module docstring.
_LEADING_STAMP_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\([A-Za-z]{3}\))?[ _]+(\d{2})\.(\d{2})\.(\d{2})"
)


def date_folder_suffix(config: dict) -> str:
    """The placeholder suffix folder-sorting writes, from config."""
    return config.get("legacy", {}).get("date_folder_suffix", DEFAULT_DATE_FOLDER_SUFFIX)


def extension_sets(config: dict) -> tuple[set[str], set[str]]:
    """``(image_extensions, video_extensions)``, lower-cased, from config."""
    extensions = config.get("extensions", {})
    video_exts = {value.lower() for value in extensions.get("videos", [])}
    image_exts = {
        value.lower()
        for group in ("lossy_images", "other_images", "raw_images")
        for value in extensions.get(group, [])
    }
    return image_exts, video_exts


def select_media(paths, image_exts: set[str], video_exts: set[str]) -> list:
    """The image and video files among ``paths``, in order.

    Sidecars fall out for free: "shot.mp4._exif" has the suffix "._exif",
    which is in neither set.
    """
    return [
        path for path in paths
        if Path(path).suffix.lower() in video_exts
        or Path(path).suffix.lower() in image_exts
    ]


def count_media(paths, image_exts: set[str], video_exts: set[str]) -> tuple[int, int]:
    """Count images and videos among ``paths``, ignoring anything else."""
    images = 0
    videos = 0
    for path in paths:
        suffix = Path(path).suffix.lower()
        if suffix in video_exts:
            videos += 1
        elif suffix in image_exts:
            images += 1
    return images, videos


def earliest_capture_time(media) -> datetime.datetime | None:
    """The earliest LEADING stamp among ``media`` (paths or names), or None.

    Only a name's leading stamp counts: a grouper-mangled name can carry a
    second, later stamp trailing the original ("...__SCR__2026-07-19..."),
    and that one must not win. By the time this runs, rename-and-sort has
    already stamped every filename with its real capture time, so the
    folder's own files are the source of truth -- no EXIF re-read needed. A
    file rename-and-sort skipped (missing EXIF) carries no stamp and is
    silently ignored rather than guessed at.
    """
    moments = []
    for path in media:
        match = _LEADING_STAMP_RE.match(Path(path).name)
        if not match:
            continue
        try:
            moments.append(datetime.datetime(*(int(part) for part in match.groups())))
        except ValueError:
            continue
    return min(moments) if moments else None


def with_earliest_time(base: str, media) -> str:
    """Give a day prefix the time of its earliest file: ``2026-07-03_(Fri)__09.12.53``.

    Only the time is taken -- the date stays exactly as folder-sorting wrote
    it, since a shot after midnight but before the day boundary belongs to the
    previous day's folder, and rewriting the date would move the day out from
    under its month folder too. A ``base`` that already opens with a full
    timestamp, or a folder with no stamped file, is left unchanged rather than
    guessed at.
    """
    if _LEADING_STAMP_RE.match(base):
        return base
    earliest = earliest_capture_time(media)
    return f"{base}__{earliest:%H.%M.%S}" if earliest else base


def to_split_suffix(images: int, videos: int) -> str:
    # "=" not ":" — the grouper uses ":" on macOS but Photosorter is Windows,
    # where ":" is illegal in filenames (matches COUNT_SEPARATOR in the grouper).
    parts = []
    if images:
        parts.append(f"i={images}")
    if videos:
        parts.append(f"v={videos}")
    return "(" + "_".join(parts) + ")" if parts else ""


def to_split_name(base: str, images: int, videos: int) -> str:
    """The full ``__TO_SPLIT__`` folder name for a dated ``base`` prefix.

    ``base`` is expected to already carry whatever time it needs (see
    ``with_earliest_time``); this only appends the marker and its counts.
    """
    return f"{base} - {TO_SPLIT_MARKER}{to_split_suffix(images, videos)}"


def strip_placeholder(name: str, placeholder: str) -> str | None:
    """The dated base of a placeholder folder name, or None if it has no placeholder."""
    if not name.endswith(placeholder):
        return None
    return name[: -len(placeholder)]


def split_to_split_name(name: str) -> tuple[str, str] | None:
    """``(dated_base, tail)`` of a ``__TO_SPLIT__`` folder name, else None.

    The tail keeps the marker and its counts verbatim, so a caller can rewrite
    the dated half without touching a count the grouper is mid-review on.
    """
    separator = f" - {TO_SPLIT_MARKER}"
    index = name.find(separator)
    if index == -1:
        return None
    return name[:index], name[index:]
