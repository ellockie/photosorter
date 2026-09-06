r"""Two files claiming one name: two exposures, or two renderings of one? (F9)

A generated name states the second a shot was taken, the camera, and the four
exposure settings. A burst, a bracket, or two taps of the shutter inside one
second produce files that agree on every one of them, so they generate the same
name -- and the archive then has to say which of two very different things it
is looking at:

  * **siblings** -- two separate exposures that happen to share a second. Both
    are representatives (F5), both belong at the top level, and neither is a
    defect. They only need telling apart.
  * **renderings** -- one exposure, saved twice: a re-encode, a resize, an
    edit. One of them is redundant or wrong, and which is a question for a
    person (F4).

Calling the first case ``_DUPE`` -- which F4 defines as a **byte-identical**
loser -- is the defect this module exists to end. Two files with different
bytes are not duplicates, and the checksum in the name of only one of them says
nothing about the other.

**What separates them is EXIF, not the filesystem.** ``SubSecTimeOriginal`` is
the fraction of the second the camera recorded, and it is the one field that
distinguishes two exposures inside one second. Where both files carry it and
the values differ, they are siblings and the archive can say so with the
camera's own number:

    2026-08-21_(Fri)__20.43.52.433__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg
    2026-08-21_(Fri)__20.43.52.633__f2.4__T1_50__L69.0.eq__I100__SG23U.jpg

That form is preferred over a counter for three reasons. It is **true** -- the
number came off the camera, and nothing here invents a time (V4). It is
**stable**: a file's name depends on that file alone, so a third sibling
arriving next year does not renumber the two already filed, and a re-run
reaches the same name it reached last time. And it **sorts into capture
order**, which a counter assigned by discovery order does not.

Where neither file carries a sub-second -- older cameras and most video
containers write none -- nothing here can tell a burst from one photo saved
twice, so the pair is not called siblings on its own: it goes to F4's collision
prompt, and a person who recognises a burst answers that these are different
shots. The name they then get is an ordinal, appended after the camera symbol
and any author marker (F8), before the representative suffixes (F3):

    2026-07-04_(Sat)__11.02.09__f2.8__T1_60__L35.0__I200__C6D.jpg
    2026-07-04_(Sat)__11.02.09__f2.8__T1_60__L35.0__I200__C6D_2.jpg

The first sibling keeps the bare name; the ordinal starts at 2, so the common
case -- one shot in a second -- is never renumbered into ``_1``.

**When one file carries a sub-second and the other does not, they are not
called siblings.** Nothing can be compared, and guessing would file a re-encode
beside its own original as though it were a second exposure. That case, and the
case where both carry the *same* fraction, fall through to F4's existing
handling: a question a person answers.

This is a **leaf module** -- standard library and ``stamps`` only -- because
both worlds reach it: the pipeline, when it renames an incoming file, and the
restructure tool, when it repairs a name an earlier version wrote.
"""

import re

from src.pipeline_stages.stamps import \
    apply_subsecond, \
    normalise_subsecond

# The EXIF field, and the field ``parse_legacy_exif_text`` files it under. Both
# spellings live here because this module is the only thing that cares which
# fraction of the second a file was taken in.
SUBSECOND_EXIF_FIELD = "Sub Sec Time Original"
SUBSECOND_METADATA_KEY = "subsecond"

# The picture's pixel size, the other half of "two exposures, or two
# renderings?". Reading it belongs to ``src.utils.dimensions`` -- the collision
# resolver needs the same answer and cannot import a stage -- but the key an
# asset files it under is named here, beside the fraction, because these two
# fields are consulted together and by the same callers.
DIMENSIONS_METADATA_KEY = "dimensions"

# The ordinal fallback. A bare ``_<n>`` rather than a worded suffix: it sits
# where F8 puts the author marker's neighbours, and every other token in the
# grammar is already read by position, so a trailing number needs no keyword to
# be found. It is matched at the end of a *stem*, before any representative
# suffix has been applied.
ORDINAL_SEPARATOR = "_"
FIRST_ORDINAL = 2
ORDINAL_RE = re.compile(r"_(\d+)$")


def subsecond_from_exif_text(text: str) -> str | None:
    """``SubSecTimeOriginal`` out of an ExifTool text sidecar, or None.

    ``Sub Sec Time Digitized`` and the bare ``Sub Sec Time`` are deliberately
    not accepted as stand-ins. They usually agree with the original and
    occasionally do not, and a fraction taken from the wrong field would name a
    moment the camera never claimed the shutter opened at.
    """
    for line in text.splitlines():
        key, separator, value = line.partition(": ")
        if separator and key.strip() == SUBSECOND_EXIF_FIELD:
            return normalise_subsecond(value)
    return None


def subsecond_of_sidecar(path) -> str | None:
    """The fraction the sidecar at ``path`` records, or None if it says none.

    An unreadable or absent sidecar answers None rather than raising: a missing
    fraction is the ordinary case this module is built to handle, not an error.
    """
    try:
        with open(path, encoding="iso-8859-1") as sidecar:
            return subsecond_from_exif_text(sidecar.read())
    except OSError:
        return None


def are_siblings(existing_subsecond: str | None, candidate_subsecond: str | None) -> bool:
    """Do two byte-different files claiming one name hold two exposures? (F9a)

    One clause: **both** record a sub-second and the two **differ**. The camera
    itself says the shutter opened twice, and that is the only evidence here
    that is evidence rather than a guess. It beats the ``_LOWRES`` size test it
    is checked ahead of -- a ratio is a heuristic about renderings, and this is
    a fact about exposures.

    Everything else is false, and deliberately so:

      * **neither** records a fraction -- two exposures from an older camera
        look exactly like one photo saved twice. Nothing here can tell them
        apart, and the archive's standing rule is that what cannot be known is
        reported for a person rather than invented (V4, F8d, L5). That pair
        goes to F4, and a person who recognises it as a burst answers
        ``siblings``, which is what ``next_ordinal_name`` is for.
      * **one** records a fraction and the other does not -- nothing to compare.
      * both record the **same** fraction -- one instant, saved twice.

    **The caller must have established that the bytes differ.** Two identical
    files carry identical EXIF, and a duplicate must not be filed twice.
    """
    existing = normalise_subsecond(existing_subsecond)
    candidate = normalise_subsecond(candidate_subsecond)
    if existing is None or candidate is None:
        return False
    return existing != candidate


def bare_name(name: str) -> str:
    """``name`` with any sub-second stripped from its stamp.

    The form every shot taken in one second shares, and therefore the key a
    same-second family is gathered under. ``…52.633__f2.4…`` and
    ``…52.433__f2.4…`` both reduce to ``…52__f2.4…``; so does a name that
    never carried a fraction, which is what lets the three be recognised as
    one family however they are currently named.
    """
    return apply_subsecond(name, None)


def family_counts(names) -> dict:
    """``{bare name: how many files claim that second}`` (F9c).

    What decides whether a fraction is written at all. One is a lone shot and
    takes the plain second form; two or more are siblings and each states the
    fraction its own camera recorded.
    """
    counts = {}
    for name in names:
        key = bare_name(name)
        counts[key] = counts.get(key, 0) + 1
    return counts


def occupant_names(name: str) -> list[str]:
    """Every existing name ``name`` could be colliding with, best first.

    A name generated today carries the camera's sub-second (F9c). The archive
    holds names written before it did, so the **fraction-less** form of the
    same shot is a collision too -- and it is the one that matters, because a
    re-ingested copy of a photo already filed would otherwise be given a name
    nothing in the folder answers to and quietly filed a second time.

    One entry when the name carries no fraction, two when it does. The
    fractioned form is tried first: it is what this run writes, so it is the
    one a second file from the same batch will have taken.
    """
    bare = apply_subsecond(name, None)
    return [name] if bare == name else [name, bare]


def sibling_name(name: str, subsecond: str | None) -> str:
    """The name a proven sibling takes: ``name`` carrying the camera's fraction.

    The two disambiguators are never combined. A fraction is the whole answer
    where one exists, and an ordinal beside it would number files that already
    say which came first; where no fraction exists there is no proven sibling
    either (F9a), and the ordinal path runs through ``next_ordinal_name`` on a
    person's say-so instead (F9b). A name with no fraction to write comes back
    unchanged.
    """
    digits = normalise_subsecond(subsecond)
    return apply_subsecond(name, digits) if digits else name


def with_ordinal(name: str, ordinal: int) -> str:
    """``photo.jpg`` -> ``photo_2.jpg``, replacing an ordinal already there."""
    stem, dot, extension = name.rpartition(".")
    if not dot:
        stem, extension = name, ""
        suffix = ""
    else:
        suffix = "." + extension
    return f"{strip_ordinal(stem)}{ORDINAL_SEPARATOR}{ordinal}{suffix}"


def strip_ordinal(stem: str) -> str:
    """A stem with a trailing sibling ordinal removed, if it carries one."""
    return ORDINAL_RE.sub("", stem)


def next_ordinal_name(name: str, taken) -> str:
    """The first free ``_<n>`` form of ``name``, starting at 2.

    ``taken(candidate_name)`` answers whether that name is already in use --
    a directory probe in the pipeline, a set membership in a planning pass.
    Passing the test in rather than doing the probe here is what keeps this
    module free of the filesystem, so a dry run can plan a rename it will not
    perform.
    """
    ordinal = FIRST_ORDINAL
    while True:
        candidate = with_ordinal(name, ordinal)
        if not taken(candidate):
            return candidate
        ordinal += 1
