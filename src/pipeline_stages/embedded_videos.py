"""Videos embedded in stills -- found, and extracted into ``__VIDEOS_EXTRACTED``.

A motion photo is one file holding two things: the still, and a few seconds of
video the phone recorded around it, appended after the JPEG's end-of-image
marker. Samsung writes it as a trailer block tagged ``MotionPhoto_Data``;
Google (and Samsung since ~2021, alongside its own) describes it in XMP as a
``MotionPhoto`` / ``MicroVideo``. Almost nothing but the phone's own gallery
plays it back, so an archive that keeps only the still keeps the video in a
form nobody can watch.

Standard X16 makes the extraction a **companion** of the still, not a video in
its own right: named per X1 with a compound suffix -- ``shot.jpg.MOTION.mp4``,
the same device X6a uses for ``clip.mp4.THM.jpg`` -- and filed in the
``__VIDEOS_EXTRACTED`` directly inside the folder holding the still, exactly
where X10 puts that still's ``._exif``. Being a companion is what makes it
travel: ``companion_matching`` carries it after its still like any sidecar,
and it never counts as media (X7), so it is never offered as a representative
and never breaks the one-sidecar-per-media ratio ``e`` reports.

The still is never rewritten. The embedded copy stays where the phone put it;
extraction only adds a file, and never over one that is already there (T2).

Two callers, one implementation (T8): the ``embedded-video-extraction``
pipeline stage runs this over what a live ingest just filed, and
``tools/restructure_archive.py`` runs it over an existing archive, where a dry
run reports what ``--apply`` would extract. Like ``exiftool_sidecars`` this is
a **leaf module** -- it imports only other leaf modules -- so the maintenance
tool can load it on a bare interpreter.

Finding them cheaply
--------------------
Asking ExifTool about every JPEG in a year is minutes of work over a share.
So each JPEG is first **sniffed**: a motion photo announces itself in its XMP
(``MotionPhoto``, ``MicroVideo``), which sits in the first few APP segments,
or ends with Samsung's ``SEFT`` trailer footer. A JPEG showing neither is not
one. Anything sniffing cannot rule out -- a JPEG that shows a marker, any HEIC
-- is then **confirmed by ExifTool reading the file itself**, never its
sidecar: a ``._exif`` written by an older ExifTool may simply not know the tag
exists (F9a-i makes the same choice for the same reason).
"""

import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from src.pipeline_stages.grouping_names import \
    configured_extensions, \
    DEFAULT_EXTRACTED_VIDEO_EXTENSIONS, \
    extracted_video_extensions
from src.pipeline_stages.taxonomy import \
    sidecar_subdir, \
    taxonomy_folder

# The taxonomy key of the folder an extraction is filed in (X16, S4).
EXTRACTED_VIDEOS_KEY = "videos_extracted"

# ExifTool tags holding the embedded video, in the order they are tried.
# Samsung's own block first: it is the bare MP4. Google's ``MotionPhotoVideo``
# is read out of the same bytes on a Samsung file but, there, carries the
# trailer's framing after the MP4 -- still playable, not byte-exact. On a
# Pixel it is the only tag, and it is exact.
EMBEDDED_VIDEO_TAGS = ("EmbeddedVideoFile", "MotionPhotoVideo")

# The older Google format (``MVIMG_*.jpg``, Pixel 2/3) that ExifTool reads but
# does not hand over as a tag: the XMP says only how many bytes from the end
# of the file the video starts. Tried last, and sliced out here.
MICRO_VIDEO_OFFSET_TAG = "MicroVideoOffset"

# Which stills can carry one. Only JPEG is sniffed; the others always go to
# ExifTool, because their metadata is not in a fixed place near the start.
CARRIER_EXTENSIONS = (".jpg", ".jpeg", ".heic", ".heif")
SNIFFED_EXTENSIONS = (".jpg", ".jpeg")

# Enough of the file's head to cover the APP1 EXIF segment (64 KB at most,
# thumbnail included), an ICC profile, and the XMP segment behind them.
SNIFF_HEAD_BYTES = 256 * 1024
XMP_MARKERS = (b"MotionPhoto", b"MicroVideo")
SAMSUNG_TRAILER_FOOTER = b"SEFT"

# What every MP4/MOV opens with, four bytes in: the "ftyp" box. An extraction
# that does not is not a video, and is reported rather than trusted.
MP4_SIGNATURE = b"ftyp"


def extraction_enabled(config: dict) -> bool:
    return (config.get("embedded_video_extraction") or {}).get("enabled", True) is not False


def extraction_suffix(config: dict) -> str:
    """The compound suffix an extraction is written with, as configured (X16)."""
    written = configured_extensions(config, "extracted_videos",
                                    DEFAULT_EXTRACTED_VIDEO_EXTENSIONS)
    return written[0] if written else DEFAULT_EXTRACTED_VIDEO_EXTENSIONS[0]


def extracted_video_folder(subject: str | Path, config: dict) -> Path:
    """The ``__VIDEOS_EXTRACTED`` directly inside the folder holding ``subject``."""
    return Path(sidecar_subdir(Path(subject).parent, config, EXTRACTED_VIDEOS_KEY))


def extracted_video_path(subject: str | Path, config: dict) -> Path:
    """Where ``subject``'s extraction belongs: X10's folder, X1's name."""
    subject = Path(subject)
    return extracted_video_folder(subject, config) / (subject.name + extraction_suffix(config))


def has_extraction(subject: str | Path, config: dict) -> bool:
    """True when an extraction of ``subject`` is already filed, in any spelling.

    Windows compares names case-insensitively, so the configured spellings are
    all that has to be tried; a stem-form or misplaced one is companion
    placement's to find and move, not this module's to count as done.
    """
    subject = Path(subject)
    folder = extracted_video_folder(subject, config)
    for suffix in configured_extensions(config, "extracted_videos",
                                        DEFAULT_EXTRACTED_VIDEO_EXTENSIONS):
        if (folder / (subject.name + suffix)).is_file():
            return True
    return False


def is_carrier(path: str | Path, config: dict) -> bool:
    """True when ``path`` is a still that could hold an embedded video."""
    name = Path(path).name
    lowered = name.lower()
    if any(lowered.endswith(suffix.lower()) for suffix in extracted_video_extensions(config)):
        return False
    return Path(name).suffix.lower() in CARRIER_EXTENSIONS


def sniff(path: str | Path) -> bool | None:
    """Does ``path`` look like a motion photo? None when sniffing cannot say.

    False only for a JPEG showing neither XMP marker and no Samsung footer --
    those are the files ExifTool is spared. An unreadable file is None: not
    knowing is not the same as knowing it is not one.
    """
    path = Path(path)
    if path.suffix.lower() not in SNIFFED_EXTENSIONS:
        return None
    try:
        with open(path, "rb") as handle:
            head = handle.read(SNIFF_HEAD_BYTES)
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - len(SAMSUNG_TRAILER_FOOTER)))
            tail = handle.read()
    except OSError:
        return None
    if any(marker in head for marker in XMP_MARKERS):
        return True
    return tail == SAMSUNG_TRAILER_FOOTER


def _key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _run_with_argfile(command: list[str], paths, runner) -> str:
    """Run ExifTool over ``paths`` listed in a UTF-8 argfile; stdout as text.

    An argfile rather than the command line for two reasons: a year's worth of
    paths does not fit in Windows' command line, and a name with a Polish
    diacritic survives only when ExifTool is told the list is UTF-8
    (``-charset filename=utf8``) -- passed as arguments, it would be mangled
    through the ANSI code page before ExifTool ever saw it.
    """
    handle, argfile = tempfile.mkstemp(prefix="photosorter_exiftool_", suffix=".args")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as listing:
            for path in paths:
                listing.write(str(path) + "\n")
        result = runner(command + ["-@", argfile])
    finally:
        try:
            os.remove(argfile)
        except OSError:
            pass
    output = getattr(result, "stdout", result) or b""
    if isinstance(output, bytes):
        return output.decode("utf-8", errors="replace")
    return str(output)


def _default_runner(command):
    # ExifTool exits 1 when a file could not be read and 2 when every file
    # failed an -if condition; neither is a reason to stop the batch.
    return subprocess.run(command, capture_output=True, check=False)


def probe(paths, exiftool: str = "exiftool", runner=None) -> set[str]:
    """Which of ``paths`` ExifTool reads an embedded video out of.

    Returns normalized path keys (``os.path.normcase(os.path.abspath(...))``),
    because ExifTool prints the path back with forward slashes.
    """
    paths = [Path(path) for path in paths]
    if not paths:
        return set()
    runner = _default_runner if runner is None else runner
    condition = " or ".join(
        "$" + tag for tag in EMBEDDED_VIDEO_TAGS + (MICRO_VIDEO_OFFSET_TAG,))
    command = [str(exiftool), "-charset", "filename=utf8", "-q", "-q",
               "-if", condition, "-p", "$Directory/$FileName"]
    output = _run_with_argfile(command, paths, runner)
    wanted = {_key(path) for path in paths}
    found = set()
    for line in output.splitlines():
        line = line.strip()
        if line and _key(line) in wanted:
            found.add(_key(line))
    return found


@dataclass
class PendingReport:
    """Stills that carry a video and have no extraction filed yet."""

    examined: int = 0              # carriers without an extraction, looked at
    already_extracted: int = 0     # carriers whose extraction is already filed
    probed: int = 0                # of ``examined``, how many ExifTool read
    pending: list = field(default_factory=list)


def find_pending(subjects, config: dict, exiftool: str = "exiftool",
                 runner=None) -> PendingReport:
    """Every still among ``subjects`` holding a video nobody has extracted (X16).

    Read-only, so a dry run can call it: it opens files and runs ExifTool, and
    writes nothing.
    """
    report = PendingReport()
    to_probe = []
    for subject in subjects:
        subject = Path(subject)
        if not is_carrier(subject, config) or not subject.is_file():
            continue
        if has_extraction(subject, config):
            report.already_extracted += 1
            continue
        report.examined += 1
        if sniff(subject) is False:
            continue
        to_probe.append(subject)
    report.probed = len(to_probe)
    carrying = probe(to_probe, exiftool, runner)
    report.pending = [subject for subject in to_probe if _key(subject) in carrying]
    return report


def is_video_file(path: str | Path) -> bool:
    """True when ``path`` opens the way an MP4/MOV does."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(12)
    except OSError:
        return False
    return len(head) >= 8 and head[4:8] == MP4_SIGNATURE


def _micro_video_offsets(paths, exiftool, runner) -> dict[str, int]:
    """``{path key: MicroVideoOffset}`` for the paths that declare one."""
    command = [str(exiftool), "-charset", "filename=utf8", "-q", "-q",
               "-if", "$" + MICRO_VIDEO_OFFSET_TAG,
               "-p", "$Directory/$FileName|$" + MICRO_VIDEO_OFFSET_TAG]
    try:
        output = _run_with_argfile(command, paths, runner)
    except OSError:
        return {}
    offsets = {}
    for line in output.splitlines():
        path, _, value = line.strip().rpartition("|")
        if path and value.isdigit():
            offsets[_key(path)] = int(value)
    return offsets


def _slice_micro_video(subject: Path, offset: int, target: Path, log) -> None:
    """Copy the last ``offset`` bytes of ``subject`` to ``target`` -- if they are a video.

    Checked before anything is written: an offset that does not land on an
    ``ftyp`` box is a lie about the file, and writing what it points at would
    file a fragment of JPEG as a video. Exclusive creation keeps T2.
    """
    try:
        size = subject.stat().st_size
        if not 0 < offset < size:
            log(f"{subject.name}: MicroVideoOffset {offset} is outside the file")
            return
        with open(subject, "rb") as source:
            source.seek(size - offset)
            clip = source.read()
        if clip[4:8] != MP4_SIGNATURE:
            log(f"{subject.name}: nothing video-shaped at MicroVideoOffset {offset}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "xb") as output:
            output.write(clip)
    except FileExistsError:
        return                  # already there; never replaced (T2)
    except OSError as error:
        log(f"{subject.name}: could not extract its MicroVideo: {error}")


@dataclass
class ExtractionReport:
    """What became of every still extraction was asked for."""

    requested: int = 0
    created: list = field(default_factory=list)       # [(subject, extraction)]
    not_video: list = field(default_factory=list)     # [(subject, extraction)]
    missing: list = field(default_factory=list)       # [subject]
    errors: int = 0


def _write_format(config: dict) -> str:
    """ExifTool's ``-w`` pattern for X10's folder and X1's name.

    ``%d`` is the subject's own directory, trailing slash included, so the
    folder name is appended to it rather than replacing it. ExifTool creates
    the folder when it is missing.
    """
    return "%d" + taxonomy_folder(config, EXTRACTED_VIDEOS_KEY) + "/%f.%e" + extraction_suffix(config)


def extract(subjects, config: dict, exiftool: str = "exiftool",
            log=lambda _message: None, runner=None) -> ExtractionReport:
    """Write each subject's embedded video to its X16 place. Never overwrites.

    One ExifTool pass per tag in ``EMBEDDED_VIDEO_TAGS``, each over the
    subjects the previous passes left without an extraction. ``-w`` without
    ``!`` refuses an existing destination (T2), and writes nothing at all for
    a file without the tag, so a pass that finds nothing costs nothing. What
    is left after them is asked for a ``MicroVideoOffset`` and sliced here.

    Every result is checked to open like an MP4. One that does not is left in
    place -- nothing is deleted (T1) -- and reported.
    """
    # One already filed is not this call's to report as created.
    subjects = [Path(subject) for subject in subjects
                if not has_extraction(subject, config)]
    report = ExtractionReport(requested=len(subjects))
    runner = _default_runner if runner is None else runner
    remaining = list(subjects)
    for tag in EMBEDDED_VIDEO_TAGS:
        if not remaining:
            break
        command = [str(exiftool), "-charset", "filename=utf8", "-q", "-q",
                   "-b", "-" + tag, "-w", _write_format(config)]
        try:
            _run_with_argfile(command, remaining, runner)
        except FileNotFoundError:
            log(f"ExifTool executable not found: {exiftool}")
            report.errors += 1
            break
        except OSError as error:
            log(f"ExifTool video extraction failed: {error}")
            report.errors += 1
            break
        remaining = [subject for subject in remaining
                     if not extracted_video_path(subject, config).is_file()]

    if remaining and not report.errors:
        offsets = _micro_video_offsets(remaining, exiftool, runner)
        for subject in remaining:
            offset = offsets.get(_key(subject))
            if offset is not None:
                _slice_micro_video(subject, offset,
                                   extracted_video_path(subject, config), log)

    for subject in subjects:
        target = extracted_video_path(subject, config)
        if not target.is_file():
            report.missing.append(subject)
        elif is_video_file(target):
            report.created.append((subject, target))
        else:
            report.not_video.append((subject, target))
    return report
