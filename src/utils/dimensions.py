"""Pixel dimensions of a media file, read from its ExifTool sidecar (T8).

Defined here, and imported by both layers, for the same reason ``checksums.py``
is: ``core``'s collision resolver has to know whether one file is a *smaller
rendering* of another, and so does ``pipeline_stages.siblings``, which answers
the neighbouring question of whether they are two exposures. ``src/utils`` is
the layer both can reach without ``core`` importing a stage.

**Why dimensions and not file size.** F4's ``_LOWRES`` is a claim that one file
is a downscaled version of another, and the resolver used to reach it from the
byte sizes alone -- a file under half the weight of the one it collided with was
called low-resolution. That is not what "resolution" means, and it was wrong in
practice: two exposures of the same scene, one of a plain sky and one of a
crowded carriage, differ by more than half on JPEG compressibility alone at
identical pixel dimensions. PS-10's own archive held the proof --

    …13.28.11__f2.2__T1_387__L13.0.eq__I50__SG23U.jpg              6.7 MB
    …13.28.11__f2.2__T1_387__L13.0.eq__I50__SG23U_LOWRES_…_1.jpg   2.5 MB

-- both **4000x3000**, and two different photographs. A ratio cannot tell a
compressible picture from a resized one; the pixel count can, and it is written
in the sidecar the archive already keeps.

**Reading it is not simply grepping for "Image Width".** The sidecars are
ExifTool's grouped text output, and a JPEG carries its embedded *thumbnail* in
IFD1 with dimension tags of its own:

    ---- File ----          Image Width : 4000    Image Height : 3000
    ---- IFD1 ----          Image Width : 512     Image Height : 384
    ---- Composite ----     Image Size  : 4000x3000

Taking the last match, or any match, would read a 512x384 thumbnail as the
picture's size and call a full-resolution file a downscale of itself. So the
group heading is tracked, the thumbnail IFDs are refused outright, and the
groups that describe the picture are consulted in a fixed order of preference.
"""

import re
from pathlib import Path

# ExifTool's "-g1" group heading, e.g. "---- Composite ----".
GROUP_HEADING_RE = re.compile(r"^-+\s*(.+?)\s*-+$")

# IFD1 and IFD2 hold the embedded thumbnail and preview. Their dimensions
# describe those, never the picture, so they are never a candidate.
THUMBNAIL_GROUPS = frozenset({"IFD1", "IFD2"})

# Which group's answer to believe, best first. "Composite" is ExifTool's own
# computed size for the picture and already accounts for orientation; "File" is
# what the JPEG's start-of-frame header states; the EXIF groups are the
# camera's claim, which a re-encoder may leave stale.
GROUP_PREFERENCE = ("Composite", "File", "ExifIFD", "IFD0")

IMAGE_SIZE_FIELD = "Image Size"
WIDTH_FIELDS = ("Image Width", "Exif Image Width")
HEIGHT_FIELDS = ("Image Height", "Exif Image Height")

IMAGE_SIZE_RE = re.compile(r"^\s*(\d+)\s*[xX]\s*(\d+)\s*$")


def parse_exif_dimensions(text: str) -> tuple[int, int] | None:
    """``(width, height)`` of the picture an ExifTool text sidecar describes.

    None when the sidecar states none it can be believed -- a video container
    ExifTool could not measure, a truncated dump, or a file whose only
    dimension tags sit in a thumbnail IFD. None means *unknown*, never "the
    same": a caller must not conclude anything about a downscale from it.
    """
    found = {}
    group = None
    for line in text.splitlines():
        heading = GROUP_HEADING_RE.match(line.strip())
        if heading:
            group = heading.group(1)
            continue
        if group in THUMBNAIL_GROUPS:
            continue
        key, separator, value = line.partition(": ")
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        pair = found.setdefault(group, {})
        if key == IMAGE_SIZE_FIELD:
            match = IMAGE_SIZE_RE.match(value)
            if match:
                pair["width"], pair["height"] = int(match.group(1)), int(match.group(2))
        elif key in WIDTH_FIELDS and value.isdigit():
            pair.setdefault("width", int(value))
        elif key in HEIGHT_FIELDS and value.isdigit():
            pair.setdefault("height", int(value))

    for group_name in GROUP_PREFERENCE:
        pair = found.get(group_name) or {}
        if "width" in pair and "height" in pair:
            return pair["width"], pair["height"]
    # A group this reader does not rank, but which is not a thumbnail either --
    # a video's track group, say. Better than nothing, and still never IFD1.
    for group_name, pair in found.items():
        if group_name not in THUMBNAIL_GROUPS and "width" in pair and "height" in pair:
            return pair["width"], pair["height"]
    return None


def dimensions_of_sidecar(path: str | Path) -> tuple[int, int] | None:
    """The picture size the sidecar at ``path`` records, or None.

    An absent or unreadable sidecar answers None rather than raising: not
    knowing a file's dimensions is an ordinary case that callers must handle,
    not an error.
    """
    try:
        with open(path, encoding="iso-8859-1") as sidecar:
            return parse_exif_dimensions(sidecar.read())
    except OSError:
        return None


def same_dimensions(one: tuple[int, int] | None, other: tuple[int, int] | None) -> bool:
    """Are both known, and equal? Unknown is never "same"."""
    return one is not None and other is not None and tuple(one) == tuple(other)


def is_downscaled(reference: tuple[int, int] | None,
                  candidate: tuple[int, int] | None) -> bool:
    """Is ``candidate`` a smaller rendering of ``reference``? (F4/F10)

    True only on positive evidence: both sizes are known, neither axis of the
    candidate is larger, and at least one is smaller. Everything else is False:

      * **equal dimensions are never a downscale**, whatever the file sizes say.
        That is the defect this function exists to end -- the same picture at
        the same resolution, saved at a different quality, is not a lower
        resolution of anything, and two different exposures at one resolution
        are not versions of each other at all.
      * **unknown is not smaller.** A file whose dimensions cannot be read is
        not demoted on a guess; it stays a question for a person (F4).
      * one axis larger and the other smaller is a **crop or a rotation**, not
        a downscale, and which it is is not decidable here.
    """
    if reference is None or candidate is None:
        return False
    reference_width, reference_height = reference
    candidate_width, candidate_height = candidate
    if candidate_width > reference_width or candidate_height > reference_height:
        return False
    return (candidate_width, candidate_height) != (reference_width, reference_height)
