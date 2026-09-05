"""Dependency-free ExifTool helpers for writing ``._exif`` sidecars.

The live ingest stages and ``tools/restructure_archive.py`` both need the same
command-line and Windows command-length rules. Keeping those here lets the
maintenance tool load them without importing ``src.core`` or the pipeline.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path


MAX_COMMAND_CHARS = 24000
SIDECAR_SUFFIX = "._exif"
WRITE_FORMAT = "%d%f.%e" + SIDECAR_SUFFIX


def chunk_targets(targets: list[Path],
                  budget: int = MAX_COMMAND_CHARS) -> list[list[str]]:
    """Split targets below Windows' approximately 32K command-line limit."""
    chunks: list[list[str]] = []
    current: list[str] = []
    used = 0
    for target in targets:
        argument = str(target)
        cost = len(argument) + 3
        if current and used + cost > budget:
            chunks.append(current)
            current = []
            used = 0
        current.append(argument)
        used += cost
    if current:
        chunks.append(current)
    return chunks


def adjacent_sidecar(media: str | Path) -> Path:
    """The canonical X1 sidecar name next to ``media``."""
    media = Path(media)
    return media.with_name(media.name + SIDECAR_SUFFIX)


def read_metadata_text(target, exiftool="exiftool", runner=None) -> str:
    """Read one file's ExifTool report without creating or changing a file."""
    runner = subprocess.check_output if runner is None else runner
    output = runner([str(exiftool), "-a", "-u", "-g1", str(target)])
    if isinstance(output, bytes):
        return output.decode("iso-8859-1")
    return str(output)


@dataclass
class GenerationReport:
    """Sidecars produced by ExifTool and media it could not process."""

    requested: int = 0
    created: list = None
    missing: list = None
    errors: int = 0

    def __post_init__(self):
        self.created = [] if self.created is None else self.created
        self.missing = [] if self.missing is None else self.missing


def generate_adjacent_sidecars(targets, exiftool="exiftool",
                               log=lambda _message: None,
                               runner=None) -> GenerationReport:
    """Extract metadata beside each target without overwriting any file.

    ExifTool first writes ``<full media name>._exif`` beside the RAW. The
    restructure caller then moves it into ``__RAW/__EXIF`` (X1/X10). ``-w`` is
    deliberately used without ``!``: an unexpected existing path is reported,
    never replaced (T2).
    """
    targets = [Path(target) for target in targets]
    report = GenerationReport(requested=len(targets))
    runner = subprocess.check_call if runner is None else runner
    command = [str(exiftool), "-a", "-u", "-g1", "-w", WRITE_FORMAT]

    for chunk in chunk_targets(targets):
        try:
            runner(command + chunk)
        except FileNotFoundError as error:
            if getattr(error, "winerror", None) == 206:
                log(f"ExifTool command line was too long: {error}")
            else:
                log(f"ExifTool executable not found: {exiftool}")
            report.errors += 1
        except subprocess.CalledProcessError as error:
            # ExifTool may still have written the readable files in this chunk.
            log(f"ExifTool reported errors (exit code {error.returncode})")
            report.errors += 1
        except OSError as error:
            log(f"ExifTool sidecar generation failed: {error}")
            report.errors += 1

        for name in chunk:
            media = Path(name)
            sidecar = adjacent_sidecar(media)
            if sidecar.is_file():
                report.created.append(sidecar)
            else:
                report.missing.append(media)

    return report
