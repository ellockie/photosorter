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

``i`` and ``v`` state what the grouper GUI will put in front of the reviewer:
the day's top-level images and videos. Two further letters may follow, and
they are audit markers rather than work counts -- each appears only when the
folder holds something those first two do not account for::

    2026-07-01_(Wed)__13.07.11 - __TO_SPLIT__(i=129_s=6)   6 files in subfolders
    2026-07-25_(Sat) - __TO_SPLIT__(e=7)                   7 orphaned sidecars

``e`` is the number of sidecars ("._exif") in the whole folder tree, written
only when it does not match the number of media files in that tree -- one
sidecar per media file is the norm, and any other number means a sidecar was
orphaned when its image moved, or an image arrived without one. ``s`` is the
number of non-sidecar files below the top level, written whenever there are
any: RAWs, a legacy "__VIDEOS", an already-split sub-event. Both are
written by the maintenance tool (``tools/canonicalise_timestamp_names.py``);
the live grouping stage writes ``i``/``v`` alone.

A labelled folder ("... - Lens tests") is already named by a human and never
carries either form.

The other name this module owns is a **group**'s -- a dated folder holding
dated children and no photographs of its own (section 3)::

    2026-08-14_(Fri)__09.31.29 __GROUP[ Polska ] ___2026-08-20_(Thu)__11.06.58_(n=31)

The start stamp opens it, the description sits in padded brackets where a
reader looks next, and the machinery that is rebuilt on every run -- the far
end of the span and the count of nested dated children -- closes it. Up to v1.0
the same four things were written as
``...__09.31.29#2026-08-20_(Thu)__11.06.58 - ____GROUP____(d=31) - Polska``,
which put the longest run of digits in the name first and the one word a person
cares about last. Every earlier shape is still read and none is written again
(N5, C15, C15a); ``split_group_name`` is where both are read and
``carries_legacy_group_marker`` is what says which one arrived.

This lives in its own leaf module, importing nothing from the project, for the
same two reasons ``stamps.py`` does: one definition means a change to the
convention cannot leave half the code writing names the other half fails to
recognise (``__TO_SPLIT__`` was already spelled out in two separate stages),
and a maintenance tool can load it by file path without dragging the whole
pipeline -- exiftool, the dashboard, the converters -- in behind it. A regular
``from src.pipeline_stages.stamps import ...`` would defeat that: importing a
submodule of ``src.pipeline_stages`` still runs that package's ``__init__``
first, which imports every stage. So the bits of ``stamps`` grammar this module
needs -- recognising a *leading* timestamp, and a leading date -- are spelled
out again below rather than imported, same as ``DEFAULT_DATE_FOLDER_SUFFIX``
already was. They sit in one block with this module's own patterns, under the
same fragment names ``stamps`` uses, so the two can be read side by side.
"""

import datetime
import re
from pathlib import Path
from typing import NamedTuple

TO_SPLIT_MARKER = "__TO_SPLIT__"

# A day nobody has named yet (N11). Nothing writes one today -- the grouper
# names a sub-event or leaves it to the counts -- but a tool converting a day
# into a group has to know that a tail saying "still to be described" is not a
# description, so the word belongs here rather than in the tool that reads it.
TO_LABEL_MARKER = "__TO_LABEL__"

# What a dated folder holding dated children carries, between its start stamp
# and its description (C1). Two underscores, and nothing trailing: the bracket
# that opens immediately after it closes the word, so the marker needs no
# closing sigil of its own, and the pair "__GROUP[" is as unmistakable in a
# month folder's listing as the four-underscore spelling it replaces was --
# while leaving room for the description to sit where a reader looks first.
GROUP_MARKER = "__GROUP"

# The description sits in brackets, padded a space each side. The padding is
# the point: a group's name is three machine-written parts and one human one,
# and the air around the human part is what stops it reading as another field.
GROUP_DESCRIPTION_OPEN = "[ "
GROUP_DESCRIPTION_CLOSE = " ]"

# What stands between the start stamp and the marker. A plain space, so the
# start stamp ends exactly where every other dated folder's does.
GROUP_MARKER_SEPARATOR = " "

# What stands between the span end and the count. The end is a timestamp and
# the count is not, and a bracket opening straight off the seconds reads as
# part of the time -- "...11.06.58(n=31)" invites the eye to carry the number
# back into the stamp. The underscore is the divider the stamp already uses
# between its own parts, so the name breaks where a reader expects it to. It
# belongs to the bracket rather than sitting between two things, which is why
# a group with no children writes neither (``group_suffix``).
GROUP_COUNT_SEPARATOR = "_"

# Every spelling of the marker this module still reads. Only ``GROUP_MARKER``
# is ever written, so reading an old name and writing it back converts it
# (C15, N13, C15a):
#
#   "__CONTAINER__"   the standard's own proposal up to v0.8; no tool wrote one
#   "____GROUP____"   v0.9-v1.0, welded to a " - " tail with the span in the
#                     prefix -- the shape most of the archive is still in
LEGACY_GROUP_MARKERS = ("____GROUP____", "__CONTAINER__")

# Where a day folder holding no files is parked: a sibling of the folder
# itself, so it leaves the month folder's working list without leaving the
# month. Created on first use. Named here because the grouping stage moves
# folders into it and the maintenance tool reasons about what it finds there,
# and the two must not drift over the spelling.
EMPTY_SUBFOLDERS_FOLDER = "__EMPTY_SUBFOLDERS"

# Where a companion whose subject is nowhere in the archive is parked (X4).
# It sits where "__EMPTY_SUBFOLDERS" sits and for the same reason: the record
# leaves the working list without leaving the month it belongs to. Named here
# beside the other parking folder so the two cannot drift over the spelling.
ORPHANS_FOLDER = "__ORPHANS"

# V8: the unresolved-video prefix is shared by counting and migration.
TO_RENAME_PREFIX = "__TO_RENAME__"

# What stands between a folder's dated half and whatever it is called.
LABEL_SEPARATOR = " - "

# Matches config.json legacy.date_folder_suffix; repeated here so the module
# stays loadable with no config in hand.
DEFAULT_DATE_FOLDER_SUFFIX = " - 1. ######"

# Matches config.json extensions.sidecars, for the same reason.
DEFAULT_SIDECAR_EXTENSIONS = ("._exif",)

# Matches config.json extensions.previews, for the same reason. Previews are
# sidecars by X6 and live in "__PREVIEWS", not in the media counts.
#
# Four forms, and the last two are why every match here is on the **longest
# trailing extension** rather than on ``Path.suffix`` (X6a). A preview a tool
# generates is a JPEG, and says what it is with a compound suffix --
# "clip.mp4.THM.jpg", "shot.CR2.PREVIEW.jpg". Ask ``Path.suffix`` and the
# answer is ".jpg", which would make the file media, put it at the top level,
# and let a 320-pixel thumbnail be picked as the representative for the shot it
# is a thumbnail OF. Matched on the whole tail, the compound forms are
# unmistakable.
DEFAULT_PREVIEW_EXTENSIONS = (".THM.jpg", ".PREVIEW.jpg", ".thm", ".lrv")

# Matches config.json extensions.ocr. Recognised text is a sidecar too (X15),
# and lives in "__OCR" rather than "__EXIF": that folder holds what a camera
# recorded, where OCR text is a later reading of the picture, regenerable and
# revisable as engines improve.
DEFAULT_OCR_EXTENSIONS = (".OCR.txt",)

# The letters of the count bracket, in the order they are written, matching
# ARCHIVE_STANDARD.md 2. "n" (nested dated children) is the one letter a group
# carries, and the only one it may (C14).
# "c" sits next to "e" because it is the other half of the same question: "e"
# says how many subjects here have a sidecar, "c" how many sidecars are fighting
# over one.
COUNT_LETTERS = ("n", "i", "v", "e", "c", "s", "w", "f")

# "d" is what "n" was called up to v1.0, and it was the wrong letter: it read
# as "days", and a group's children are as often sub-events of one day as they
# are days of a trip -- "(d=4)" on a Saturday split into four hours said
# something false about what was in it. "n" says how many nested dated folders
# and nothing else. Read forever, written never (N5).
LEGACY_COUNT_LETTERS = ("d",)

# What each letter means, in one line, for a tool to print after it has written
# a name carrying one. Mirrors "count_meaning" in ARCHIVE_STANDARD.md section 8;
# a legend spelled out in a tool would be a second definition, and the one that
# drifts is always the one nobody is testing (T8).
#
# "w" remains until a human resolves the tagged videos (V9).
COUNT_MEANINGS = {
    "n": "nested dated child folders -- the only count a group carries",
    "d": "nested dated child folders (pre-v1.1 spelling of \"n\")",
    "i": "top-level images -- the review job, what a grouper GUI will show",
    "v": "top-level videos -- likewise",
    "e": "media covered by a sidecar, counted by subject; shown only when it "
         "does not match the media in the subtree",
    "c": "sidecars beyond the first for one subject -- two files claiming one shot",
    "s": "files below the top level that are not sidecars, which the GUI will "
         "not put in front of you",
    "w": "unresolved videos awaiting a real capture time",
    "f": "subfolders still standing in a folder holding no files",
}

# A folder holding no files at all, however deep you look, says so instead of
# counting: "(EMPTY)", or "(f=3_EMPTY)" when empty subfolders are all it has
# left. The counts it used to carry go -- there is nothing there to count.
EMPTY_MARKER = "EMPTY"

# The time an emptied folder carries. It has no capture to be dated by, but a
# dated prefix without a time is the one shape the convention only tolerates,
# so midnight stands in -- unmistakable next to the EMPTY that explains it.
EMPTY_TIME = "00.00.00"

# What separates two emptied folders that would otherwise land on one name.
DISCRIMINATOR_PATTERN = r"_\d+"

# Every pattern this module matches on, in one place and built from named
# fragments, the way stamps.py builds its own.
#
# The first five mirror stamps.DATE_PATTERN, stamps.DATE_TIME_SEPARATOR_PATTERN,
# stamps.STAMP_CAPTURE_PATTERN, stamps.RANGE_END_SEPARATOR and
# stamps._RANGE_END_BODY_PATTERN under the same names, and are spelled out
# again rather than imported -- see the module docstring for why this module
# imports nothing at all. test_t8_single_definition compares them character for
# character, which is what keeps a deliberate copy from becoming a quiet fork.
_DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"
_TIME_PATTERN = r"\d{2}\.\d{2}\.\d{2}"
# Every separator ever written between the date and the time halves.
_DATE_TIME_SEPARATOR_PATTERN = r"(?:[ _]+\([A-Za-z]{3}\))?[ _]+"
# (year, month, day, hour, minute, second)
_STAMP_CAPTURE_PATTERN = (
    r"(\d{4})-(\d{2})-(\d{2})"
    rf"{_DATE_TIME_SEPARATOR_PATTERN}"
    r"(\d{2})\.(\d{2})\.(\d{2})"
)
# What opens a group's span end, and the end itself (C6). Written with the
# first, read with either -- the "#" of the pre-v1.1 convention welded the end
# to the start stamp; since v1.1 it closes the name.
_RANGE_END_SEPARATOR = " ___"
_LEGACY_RANGE_END_SEPARATOR = "#"
_RANGE_END_BODY_PATTERN = (
    rf"(?:({_TIME_PATTERN})"
    r"|(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})"
    rf"(?:{_DATE_TIME_SEPARATOR_PATTERN}({_TIME_PATTERN}))?)"
)

# A leading "YYYY-MM-DD[_(Ddd)]_HH.MM.SS", captured part by part so the instant
# can be read off it. Matches stamps.LEADING_STAMP_RE.
_LEADING_STAMP_RE = re.compile(rf"^{_STAMP_CAPTURE_PATTERN}")

# A leading date, whether or not a weekday and time follow: enough to tell a
# dated folder from a month folder ("10. October"), which is all it is for.
_DAY_PREFIX_RE = re.compile(rf"^{_DATE_PATTERN}")

# A dated prefix and NOTHING ELSE -- anchored at both ends. What it is for is
# telling a leaf's prefix from a group's: a group's prefix carries its span
# ("...__08.14.02#16__21.40.55"), and both ends of that are maintained together
# by whatever run touches the subtree (C11), never one end at a time by a
# retiming pass. Both historical separators are read (N5); neither is written.
_DATED_PREFIX_ONLY_RE = re.compile(
    rf"^{_DATE_PATTERN}(?:[ _]+\([A-Za-z]{{3}}\))?"
    rf"(?:[ _]+\d{{2}}\.\d{{2}}\.\d{{2}})?$")

# The number folder-sorting wrote in front of every day folder: "1. ".
_LABEL_NUMBERING_RE = re.compile(r"^\d+\.\s+")

# A count bracket and nothing else: "(i=79_v=3)", "(EMPTY)", "(f=3_EMPTY)" --
# optionally followed by the discriminator that keeps two emptied folders apart.
_COUNT_PAIR_PATTERN = r"[%s]=\d+" % "".join(COUNT_LETTERS + LEGACY_COUNT_LETTERS)
_COUNTS_PATTERN = r"%s(?:_%s)*" % (_COUNT_PAIR_PATTERN, _COUNT_PAIR_PATTERN)
_EMPTY_COUNTS_PATTERN = r"(?:%s_)?%s" % (_COUNTS_PATTERN, EMPTY_MARKER)
_COUNT_BRACKET_RE = re.compile(
    r"\((?:%s|%s)\)(?:%s)?" % (_COUNTS_PATTERN, _EMPTY_COUNTS_PATTERN,
                               DISCRIMINATOR_PATTERN))
_EMPTY_BRACKET_RE = re.compile(
    r"\(%s\)(?:%s)?$" % (_EMPTY_COUNTS_PATTERN, DISCRIMINATOR_PATTERN))

# What a group is called, whole (C1, C6, C14, C16):
#
#   2026-08-14_(Fri)__09.31.29 __GROUP[ Polska ] ___2026-08-20_(Thu)__11.06.58_(n=31)
#   \_____ start stamp _____/ \__ marker and __/ \____ span end ____/\_ count __/
#                              \  description  /
#
# Four parts, and only one of them is a person's. The start stamp opens the
# name so alphabetical order stays chronological (C10); the description sits
# where a reader looks next, in brackets padded a space each side; the span end
# and the count close it, together, because both are read off the subtree and
# rewritten whenever it changes (C11).
#
# Everything after the description is optional to READ, the count's own
# separator included. C6 says a group states its span always, and a tool writes
# one always -- but a name a person typed by hand is still a group, and
# refusing to recognise it would leave the one folder that most needs
# correcting invisible to the pass that corrects it.
_GROUP_NAME_RE = re.compile(
    r"^(?P<base>.*?)%s%s%s(?P<description>.*?)%s"
    r"(?P<range_end>(?:%s|%s)%s)?"
    r"(?:%s?\((?P<counts>[%s]=\d+)\))?$"
    % (re.escape(GROUP_MARKER_SEPARATOR), re.escape(GROUP_MARKER),
       re.escape(GROUP_DESCRIPTION_OPEN), re.escape(GROUP_DESCRIPTION_CLOSE),
       re.escape(_RANGE_END_SEPARATOR), re.escape(_LEGACY_RANGE_END_SEPARATOR),
       _RANGE_END_BODY_PATTERN, re.escape(GROUP_COUNT_SEPARATOR),
       "".join(COUNT_LETTERS[:1] + LEGACY_COUNT_LETTERS)))

# What a group was called up to v1.0: the marker as the first element of a
# " - " tail, the count after it, the description after that, and the span
# welded to the start stamp rather than closing the name. Read and converted;
# never written (C15, C15a, N13). The description is captured so the conversion
# can put it back verbatim, which is what T7 means by a name a human wrote
# being finished.
_LEGACY_GROUP_TAIL_RE = re.compile(
    r"^%s(?P<marker>%s)(?:\((?P<counts>[%s]=\d+)\))?(?:%s(?P<description>.+))?$"
    % (re.escape(LABEL_SEPARATOR),
       "|".join(re.escape(marker) for marker in LEGACY_GROUP_MARKERS),
       "".join(COUNT_LETTERS[:1] + LEGACY_COUNT_LETTERS),
       re.escape(LABEL_SEPARATOR)))


def count_letters_in(name: str) -> set[str]:
    """The count-bracket letters ``name`` actually carries.

    So a tool can explain the names it just wrote and nothing else: a legend of
    every letter, on a run where only two appeared, is a legend nobody reads.
    """
    match = _COUNT_BRACKET_RE.search(name)
    if match is None:
        return set()
    return {letter for letter in COUNT_LETTERS + LEGACY_COUNT_LETTERS
            if f"{letter}=" in match.group(0)}


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


# The config key each companion kind reads, and what it falls back to. One
# tuple so the readers below and ``companion_extension_spellings`` cannot come
# to disagree about which keys exist (T8).
COMPANION_EXTENSION_KEYS = (
    ("sidecars", DEFAULT_SIDECAR_EXTENSIONS),
    ("previews", DEFAULT_PREVIEW_EXTENSIONS),
    ("ocr", DEFAULT_OCR_EXTENSIONS),
)


def configured_extensions(config: dict, key: str, defaults) -> tuple:
    """The extensions configured under ``key``, **exactly as written**.

    Casing preserved, which is the whole point of it being separate from the
    readers below: matching is case-insensitive, but the name a companion is
    *renamed to* has to carry the spelling the standard documents --
    ".THM.jpg", not ".thm.jpg" (X6a), ".OCR.txt", not ".ocr.txt" (X15).
    """
    extensions = config.get("extensions", {})
    if key not in extensions:
        return tuple(defaults)
    return tuple(extensions[key])


def companion_extension_spellings(config: dict) -> dict:
    """``{lower-cased extension: the spelling to write}`` for every kind.

    What turns a match back into a name. A companion arriving as ".thm.jpg" or
    ".OCR.TXT" is recognised either way and comes to rest under the one
    spelling this archive uses, so a later run has one form to look for rather
    than however many a camera and three tools happened to write.
    """
    spellings = {}
    for key, defaults in COMPANION_EXTENSION_KEYS:
        for value in configured_extensions(config, key, defaults):
            spellings[value.lower()] = value
    return spellings


def sidecar_extensions(config: dict) -> set[str]:
    """Sidecar suffixes (``._exif``), lower-cased, from config.

    An explicitly empty list means the archive keeps no sidecars, and the
    ``e=`` marker is then never written; a missing key just means this module
    was handed a bare config and falls back to the project default.
    """
    extensions = config.get("extensions", {})
    if "sidecars" not in extensions:
        return {value.lower() for value in DEFAULT_SIDECAR_EXTENSIONS}
    return {value.lower() for value in extensions["sidecars"]}


def preview_extensions(config: dict) -> set[str]:
    """Preview suffixes (``.thm``, ``.lrv``), lower-cased, from config.

    A camera thumbnail and a GoPro proxy are sidecars too (standard X6): never
    media, never a representative, never counted in ``i``/``v`` or ``e``. They
    are read from their own config key rather than from the image and video
    lists, which is what stops a 40x30 ".thm" being picked as the
    representative for a shot whose real image is missing.
    """
    extensions = config.get("extensions", {})
    if "previews" not in extensions:
        return {value.lower() for value in DEFAULT_PREVIEW_EXTENSIONS}
    return {value.lower() for value in extensions["previews"]}


def ocr_extensions(config: dict) -> set[str]:
    """OCR suffixes (``.OCR.txt``), lower-cased, from config.

    Its own key, and its own folder, for the reason X15 gives: what a camera
    recorded and what an engine later read off the picture are different kinds
    of claim, and a stale ``__OCR`` should be discardable wholesale without
    touching a single piece of capture metadata.
    """
    extensions = config.get("extensions", {})
    if "ocr" not in extensions:
        return {value.lower() for value in DEFAULT_OCR_EXTENSIONS}
    return {value.lower() for value in extensions["ocr"]}


def companion_subject_name(name: str, extensions) -> str | None:
    """The file ``name`` is a companion of, or None -- longest tail wins (X6a).

    Longest first is the whole of the rule: "clip.mp4.THM.jpg" ends with
    ".jpg" and with ".THM.jpg", and only the second answer is true. Testing the
    compound forms before the plain ones is what keeps a generated preview from
    reading as a JPEG of its own.
    """
    lowered = name.lower()
    for extension in sorted(extensions, key=len, reverse=True):
        if lowered.endswith(extension) and len(name) > len(extension):
            return name[: -len(extension)]
    return None


def is_preview(name: str, preview_exts) -> bool:
    """True when ``name`` is a preview of something and never media itself (X7)."""
    return companion_subject_name(name, preview_exts) is not None


def sidecar_subject_name(name: str, sidecar_exts: set[str]) -> str | None:
    """The name of the file a companion describes, or None if it is not one.

    X1 makes this exact rather than a guess: a sidecar keeps its subject's
    **full** name and appends its own extension, so "shot.jpg._exif" describes
    "shot.jpg" and the answer is a string comparison.

    It lives here rather than beside the code that moves companions because the
    count bracket needs it too: "e" counts the distinct subjects a folder's
    sidecars name, and "c" counts the sidecars beyond the first for any one of
    them. Two definitions of "which file is this a sidecar of" would let the
    counts and the placement disagree about the same folder.
    """
    return companion_subject_name(name, sidecar_exts)


def sidecar_subjects(paths, sidecar_exts: set[str]) -> dict[str, int]:
    """How many sidecars each subject under ``paths`` has, keyed case-insensitively.

    One per subject is the norm (X4). Anything more is a clash: two files
    claiming to describe the same shot, which is what "c" reports and what
    companion placement settles by checksum.
    """
    counts: dict[str, int] = {}
    for path in paths:
        subject = sidecar_subject_name(Path(path).name, sidecar_exts)
        if subject is None:
            continue
        key = subject.lower()
        counts[key] = counts.get(key, 0) + 1
    return counts


def select_sidecars(paths, sidecar_exts: set[str]) -> list:
    """The sidecar files among ``paths``, in order.

    A sidecar keeps its subject's extension in front of its own --
    "shot.jpg._exif" -- so ``Path.suffix`` is "._exif" and the set match is
    exact, the mirror image of ``select_media`` letting them fall out.

    A sidecar is also named after the file it describes, so it carries that
    file's capture time in its own leading stamp: a folder whose images have
    gone can still be dated from what they left behind.
    """
    return [path for path in paths if Path(path).suffix.lower() in sidecar_exts]


def count_sidecars(paths, sidecar_exts: set[str]) -> int:
    """How many of ``paths`` are sidecars."""
    return len(select_sidecars(paths, sidecar_exts))


def select_media(paths, image_exts: set[str], video_exts: set[str],
                 preview_exts: set[str] | None = None) -> list:
    """The image and video files among ``paths``, in order.

    Sidecars fall out for free: "shot.mp4._exif" has the suffix "._exif", which
    is in neither set. **Previews do not**, and that is what ``preview_exts``
    is for: a generated one is a real JPEG by extension (X6a) and would be
    counted as an image, offered to a grouper GUI, and eligible to be picked as
    a representative for the very shot it is a thumbnail of. X7 says a preview
    is never media; this is where that is enforced.

    ``preview_exts`` defaults to the module's own list rather than being
    required, so a caller with no config in hand still excludes the forms every
    config in this project sets.
    """
    preview_exts = _preview_set(preview_exts)
    selected = []
    for path in paths:
        if is_preview(Path(path).name, preview_exts):
            continue
        suffix = Path(path).suffix.lower()
        if suffix in video_exts or suffix in image_exts:
            selected.append(path)
    return selected


def _preview_set(preview_exts) -> set[str]:
    """The preview extensions to match on, lower-cased, defaulted if absent."""
    if preview_exts is None:
        return {value.lower() for value in DEFAULT_PREVIEW_EXTENSIONS}
    return {value.lower() for value in preview_exts}


def count_media(paths, image_exts: set[str], video_exts: set[str],
                preview_exts: set[str] | None = None) -> tuple[int, int]:
    """Count images and videos among ``paths``, ignoring anything else.

    Previews are excluded on the same terms as ``select_media``: a name a
    thumbnail carries is not a shot the folder holds, and counting one would
    put "i=1" on a day whose only image is a proxy for a video (X7).
    """
    preview_exts = _preview_set(preview_exts)
    images = 0
    videos = 0
    for path in paths:
        if is_preview(Path(path).name, preview_exts):
            continue
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


def latest_capture_time(media) -> datetime.datetime | None:
    """The latest LEADING stamp among ``media`` (paths or names), or None.

    The other end of ``earliest_capture_time``, read the same way and with the
    same reservations: only the leading stamp counts, and an unstamped file is
    ignored rather than guessed at. A group needs both ends to state its span
    (C6), and a span whose end came from a different source than its start
    would be comparing two different clocks.
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
    return max(moments) if moments else None


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


def prefix_day(base: str) -> datetime.date | None:
    """The date a dated prefix opens with, or None when it opens with none."""
    match = _DAY_PREFIX_RE.match(base)
    if not match:
        return None
    try:
        return datetime.date(*(int(part) for part in match.group(0).split("-")))
    except ValueError:                  # "2026-02-31": a shape, not a date
        return None


def _days_after_prefix(base: str, moment: datetime.datetime) -> int | None:
    """How many days ``moment`` falls after the day ``base`` is named for."""
    day = prefix_day(base)
    return None if day is None else (moment.date() - day).days


def earliest_outside_its_day(base: str, media) -> datetime.datetime | None:
    """The earliest stamp in ``media`` when it is not one this day may hold.

    N7 puts a capture at or before the day boundary in the **previous** day's
    folder, so a folder dated D legitimately holds files stamped D and D+1, and
    nothing else. A stamp outside that pair is a file in the wrong folder, or a
    folder under the wrong date -- either way something a person has to look
    at, and never a time to rename the folder from.

    ``None`` when the earliest file is one the folder may hold, when nothing in
    ``media`` carries a stamp, or when ``base`` opens with no readable date.
    """
    earliest = earliest_capture_time(media)
    if earliest is None:
        return None
    offset = _days_after_prefix(base, earliest)
    if offset is None or offset in (0, 1):
        return None
    return earliest


def with_corrected_time(base: str, media) -> str:
    """``base`` carrying the capture time of its earliest file, whatever it said.

    N3 is not "a folder gets a time", it is "the time **is** the capture time
    of the folder's earliest file". ``with_earliest_time`` only ever fills a
    blank, so a prefix stamped before its contents settled -- by an older
    grouper, by a split that moved the early shots into a sibling, by a hand --
    kept a time that named no photograph in it. This corrects one, and N6 is
    why only the time half moves: rewriting the date would move the folder out
    from under its month folder.

    ``base`` comes back unchanged when there is nothing to correct it from --
    an emptied folder keeps the real time it was named with (N10b) -- and in
    two cases where reading its contents would be the wrong thing to do:

      * ``base`` is not a dated prefix on its own. A group carries its span
        there, and both ends of a span are recomputed together by the run that
        changed the subtree (C11), not one end at a time by this.
      * the earliest file is not one this day may hold (N7). Renaming a folder
        onto a stray from another year is how one misfiled file rewrites the
        name of a day that was right; ``earliest_outside_its_day`` is what
        reports it instead.
    """
    if not _DATED_PREFIX_ONLY_RE.match(base):
        return base
    earliest = earliest_capture_time(media)
    if earliest is None or earliest_outside_its_day(base, media) is not None:
        return base
    stamped = _LEADING_STAMP_RE.match(base)
    if stamped is None:
        return f"{base}__{earliest:%H.%M.%S}"
    # Everything up to the hour: the date, the weekday and the separator
    # between them, exactly as they are. Only the time is this function's.
    return f"{base[:stamped.start(4)]}{earliest:%H.%M.%S}"


def to_split_suffix(images: int, videos: int,
                    sidecars: int | None = None,
                    clashes: int | None = None,
                    subfolder_files: int | None = None,
                  waiting: int = 0) -> str:
    """The count bracket: ``(i=79_v=3_e=83_s=4)``, or "" when it has nothing to say.

    ``images`` and ``videos`` are omitted when zero, since a day with no video
    should not carry "v=0" forever. The two audit markers work the other way
    round: they are omitted when ``None``, and the caller passes ``None``
    precisely when there is nothing to report -- so ``e=0`` is a real and
    deliberate statement ("this folder's sidecars are all gone"), not padding.
    """
    # "=" not ":" — the grouper uses ":" on macOS but Photosorter is Windows,
    # where ":" is illegal in filenames (matches COUNT_SEPARATOR in the grouper).
    parts = []
    if images:
        parts.append(f"i={images}")
    if videos:
        parts.append(f"v={videos}")
    if sidecars is not None:
        parts.append(f"e={sidecars}")
    if clashes is not None:
        parts.append(f"c={clashes}")
    if subfolder_files is not None:
        parts.append(f"s={subfolder_files}")
    if waiting:
        parts.append(f"w={waiting}")
    return "(" + "_".join(parts) + ")" if parts else ""


def empty_suffix(subfolders: int) -> str:
    """The bracket of a folder holding no files: ``(EMPTY)`` or ``(f=3_EMPTY)``.

    ``f`` is every subfolder in the subtree, not just the direct ones. They are
    all empty by definition -- the folder holds no files anywhere -- so the
    number says how much hollow structure is left standing.
    """
    parts = ([f"f={subfolders}"] if subfolders else []) + [EMPTY_MARKER]
    return "(" + "_".join(parts) + ")"


def with_empty_time(base: str) -> str:
    """Give a dated prefix the placeholder time when it has none.

    An emptied folder holds nothing to read a capture time off, and would
    otherwise keep a bare date -- the one prefix shape the convention would
    rather not see. ``00.00.00`` fills it: a real, sortable time that no camera
    is likely to have produced, sitting next to the ``EMPTY`` that says why it
    is there. A prefix that already carries a time keeps it; a real capture
    time, even on a folder since emptied, beats a placeholder.
    """
    if _LEADING_STAMP_RE.match(base):
        return base
    return f"{base}__{EMPTY_TIME}"


def empty_to_split_name(base: str, subfolders: int) -> str:
    """The full name of an emptied ``__TO_SPLIT__`` folder.

    The placeholder time is applied here rather than by the caller, so no route
    to an empty name can leave one without it.
    """
    return f"{with_empty_time(base)} - {TO_SPLIT_MARKER}{empty_suffix(subfolders)}"


def carries_empty_bracket(name: str) -> bool:
    """True when ``name`` ends in an ``EMPTY`` bracket, discriminator or not."""
    return bool(_EMPTY_BRACKET_RE.search(name))


def to_split_name(base: str, images: int, videos: int,
                  sidecars: int | None = None,
                  clashes: int | None = None,
                  subfolder_files: int | None = None,
                  waiting: int = 0) -> str:
    """The full ``__TO_SPLIT__`` folder name for a dated ``base`` prefix.

    ``base`` is expected to already carry whatever time it needs (see
    ``with_earliest_time``); this only appends the marker and its counts. The
    two audit markers default to absent, so the live grouping stage keeps
    writing the plain ``(i=N_v=M)`` name it always has.
    """
    return (f"{base} - {TO_SPLIT_MARKER}"
            f"{to_split_suffix(images, videos, sidecars, clashes, subfolder_files, waiting)}")


def split_labelled_name(name: str) -> tuple[str, str] | None:
    """``(dated_base, label)`` of a human-named event folder, else None.

    A labelled folder is a dated prefix, the separator, and a name somebody
    chose: "2026-07-24_(Fri)__18.34.56 - Lens tests". Only the first separator
    counts, so a label carrying one of its own ("Lens tests - flowers") comes
    back whole.
    """
    if not _DAY_PREFIX_RE.match(name):
        return None
    base, separator, label = name.partition(LABEL_SEPARATOR)
    if not separator or not label:
        return None
    return base, label


def strip_label_numbering(label: str) -> str:
    """A label without the legacy number folder-sorting left in front of it.

    Every day folder was written as " - 1. ######", and a human naming one
    typed over the "######" and left the "1. " standing. The number is
    machinery rather than part of the name -- it never counted anything, being
    hard-coded into the suffix, and no folder named since carries one -- so a
    label sheds it. A label that is nothing but a number keeps it: there is no
    name underneath to uncover.
    """
    stripped = _LABEL_NUMBERING_RE.sub("", label, count=1)
    return stripped or label


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


def to_split_tail_is_only_counts(tail: str) -> bool:
    """True when a ``__TO_SPLIT__`` tail carries counts and nothing else.

    Recomputing a folder's counts means rewriting the whole tail, which would
    silently throw away anything a human added after the marker. So the rewrite
    is only offered for a tail this recognises: the bare marker, or the marker
    followed by a bracket of nothing but ``letter=number`` pairs, an ``EMPTY``,
    or both -- with the discriminator that may trail an emptied folder's name.
    """
    remainder = tail[len(f" - {TO_SPLIT_MARKER}"):]
    return remainder == "" or bool(_COUNT_BRACKET_RE.fullmatch(remainder))


# --------------------------------------------------------------------------
# Groups (ARCHIVE_STANDARD.md section 3)
# --------------------------------------------------------------------------
#
# A group is a dated folder whose contents are other dated folders, and the
# archive's only nesting device: a day split into sub-events and a fortnight in
# Norway are the same shape, differing only in how far the span runs. What it
# holds is closed (C3) and what it is called is derived (C11) -- both ends of
# the span are read off the subtree and rewritten whenever it changes, so the
# only part of the name a person owns is the description in the brackets.
#
# The two stamps are stamps.py's grammar; how they and the marker, the
# description and the count are arranged into one name is this module's.


class GroupName(NamedTuple):
    """A group folder name, read apart.

    ``children`` is None when the name carries no count bracket -- an unknown
    number, which is not the same claim as zero. ``range_end`` is the raw span
    end **with its opener**, exactly as ``stamps.format_range_end`` writes one
    and as ``stamps.resolve_range_end`` expects to be handed one, or None when
    the name states no span. ``legacy`` is True when the name was written in
    the pre-v1.1 shape and so wants converting on the next rewrite (C15a).
    """

    base: str                 # the start stamp, exactly as the folder carries it
    description: str | None   # what a person wrote, or __TO_LABEL__, or None
    range_end: str | None     # the raw span end with its opener, or None
    children: int | None      # the count bracket, or None when it carries none
    legacy: bool              # written in a shape no tool writes any more


def group_suffix(children: int) -> str:
    """The count bracket of a group: ``_(n=7)``, or "" for none.

    ``n`` is the only letter a group may carry (C14) -- the others count files,
    and C3 leaves a group with none. Zero children is written as no bracket at
    all rather than ``_(n=0)``, for the same reason ``i``/``v`` are omitted when
    zero, and because a folder with no dated children is not a group. The
    separator comes with the bracket, so "no bracket" really is nothing.
    """
    return (f"{GROUP_COUNT_SEPARATOR}({COUNT_LETTERS[0]}={children})"
            if children else "")


def group_name(base: str, children: int, description: str | None = None,
               range_end: str = "") -> str:
    """The full group folder name (C1, C6, C14, C16).

    ``base`` is the start stamp and nothing else -- an ordinary dated prefix,
    the same one a leaf carries (C10). ``range_end`` is what
    ``stamps.format_range_end`` returned for the other end of the span, opener
    included; it is a keyword with an empty default only so a caller that has
    no span to state can still be given a name it will recognise again.

    A group with no description is written asking for one: ``__TO_LABEL__``
    goes in the brackets rather than the brackets coming off (N11, C16). A
    group waiting for a name should look like it is waiting, and an empty
    bracket says the same thing quietly enough to be missed.

    Written with ``GROUP_MARKER``, the padded brackets and the trailing span
    always, which is how reading a legacy name and writing it back converts it
    (C15, C15a, N13).
    """
    return "%s%s%s%s%s%s%s%s" % (
        base, GROUP_MARKER_SEPARATOR, GROUP_MARKER, GROUP_DESCRIPTION_OPEN,
        description or TO_LABEL_MARKER, GROUP_DESCRIPTION_CLOSE,
        range_end, group_suffix(children))


def split_group_name(name: str) -> GroupName | None:
    """``name`` read apart as a group, or None when it is not one.

    Both conventions, one reading. The v1.1 shape is tried first -- it is what
    every tool writes and what the archive is being moved onto -- and the
    pre-v1.1 " - " tail second, with the span picked off the start stamp where
    that convention welded it.

    A group is a **dated** folder holding dated children (C1), so a name with
    no date in front of the marker is not one, however it is spelled. That
    keeps a bare tail handed in by mistake from coming back as a group whose
    start stamp is the empty string.
    """
    if not _DAY_PREFIX_RE.match(name):
        return None
    match = _GROUP_NAME_RE.match(name)
    if match is not None:
        counts = match.group("counts")
        return GroupName(
            match.group("base"),
            match.group("description") or None,
            match.group("range_end"),
            int(counts[2:]) if counts else None,
            legacy=False,
        )

    base, separator, tail = name.partition(LABEL_SEPARATOR)
    if not separator:
        return None
    legacy = _LEGACY_GROUP_TAIL_RE.match(LABEL_SEPARATOR + tail)
    if legacy is None:
        return None
    counts = legacy.group("counts")
    # The pre-v1.1 span sat inside the prefix. Split it off so a caller is
    # handed the same two things either convention was written in.
    span = re.search(
        r"%s%s$" % (re.escape(_LEGACY_RANGE_END_SEPARATOR),
                    _RANGE_END_BODY_PATTERN), base)
    return GroupName(
        base[:span.start()] if span else base,
        legacy.group("description"),
        span.group(0) if span else None,
        int(counts[2:]) if counts else None,
        legacy=True,
    )


def carries_group_marker(name: str) -> bool:
    """True when ``name`` is a group name in either convention."""
    return split_group_name(name) is not None


def carries_legacy_group_marker(name: str) -> bool:
    """True when ``name`` is written in a shape no tool writes any more.

    Either of the older marker spellings, the span welded to the start stamp,
    the " - " tail around them -- all one answer, because they are all one
    thing: a group whose next rewrite will bring it onto the current
    convention (C15, C15a, N13).
    """
    parsed = split_group_name(name)
    return parsed is not None and parsed.legacy


def group_description(name: str) -> str | None:
    """What a human called a group, or None -- the one part of the name they own.

    Kept verbatim across every rewrite of the stamps and the count (C11/T7),
    including the rewrite that converts a legacy name.

    ``__TO_LABEL__`` in the description slot is **not** a description: it is
    N11's word for a folder still waiting for one, written by a tool and
    addressed to a person. Reading it as a name would make it permanent -- T7
    protects a description from every later rewrite, so the one marker meant to
    be replaced would be the one thing nothing could replace.
    """
    parsed = split_group_name(name)
    if parsed is None or parsed.description == TO_LABEL_MARKER:
        return None
    return parsed.description


def awaits_label(name: str) -> bool:
    """True when a tool has marked ``name`` as still waiting for a description.

    Either shape of N11: the bare tail on a leaf day (" - __TO_LABEL__") and
    the marker sitting in a group's description slot
    ("__GROUP[ __TO_LABEL__ ]"). One question -- has anybody named this yet --
    so one answer, whichever kind of folder is asking.
    """
    parsed = split_group_name(name)
    if parsed is not None:
        return parsed.description == TO_LABEL_MARKER
    _, separator, tail = name.partition(LABEL_SEPARATOR)
    return bool(separator) and tail == TO_LABEL_MARKER


def folder_description(
        name: str,
        date_folder_suffix: str = DEFAULT_DATE_FOLDER_SUFFIX) -> str | None:
    """What a human called this dated folder -- group or leaf -- or None.

    The one reading of "has a person named this?", so a group and its children
    are asked the same question in the same words. Three shapes answer it:

      * a **group**: the description after the marker (C11/T7), which is None
        for a bare marker and for ``__TO_LABEL__``;
      * a **placeholder**: ``__TO_SPLIT__(i=79)`` is a count, ``__TO_LABEL__``
        is a request, and " - 1. ######" is what folder-sorting wrote before
        either existed. None of the three is a name;
      * a **label**: everything else after the separator, less the legacy
        numbering a person typed around rather than over.
    """
    if carries_group_marker(name):
        return group_description(name)
    for marker in (TO_SPLIT_MARKER, TO_LABEL_MARKER):
        if LABEL_SEPARATOR + marker in name:
            return None
    if name.endswith(date_folder_suffix):
        return None
    labelled = split_labelled_name(name)
    if labelled is None:
        return None
    return strip_label_numbering(labelled[1]) or None


def shared_child_description(
        names,
        date_folder_suffix: str = DEFAULT_DATE_FOLDER_SUFFIX) -> str | None:
    """The one description every dated child agrees on, or None.

    A group nobody has named still has to be called something, and the only
    honest source is its own contents. Agreement is the whole test: when every
    child says "Sopot" the group is about Sopot, and saying so invents nothing.
    Anything short of that -- one child unnamed, or two children disagreeing --
    is a name the group would be making up, and N6's refusal to derive a date
    from contents is the same refusal one step over. Those get ``__TO_LABEL__``
    from the caller instead, which asks a person rather than guessing.

    **Every** child must be named, not merely the ones that are: a group spans
    everything under it, so a description drawn from half of them would claim
    the other half too. Matching ignores case only, never punctuation or word
    order -- two labels that differ at all are two claims, and the spelling
    handed back is the first child's, so the group reads as the archive is
    written rather than as a comparison key.
    """
    agreed = None
    seen = False
    for name in names:
        description = folder_description(name, date_folder_suffix)
        if description is None:
            return None
        if not seen:
            agreed, seen = description, True
        elif description.casefold() != agreed.casefold():
            return None
    return agreed if seen else None


def unresolved_video_count(paths, video_extensions):
    """V8/V9: tagged videos count as a pending naming job, not previews."""
    return sum(Path(path).name.startswith(TO_RENAME_PREFIX)
               and Path(path).suffix.casefold() in video_extensions for path in paths)
