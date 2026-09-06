"""Give every JPEG extracted from a RAW a sidecar of its own.

A RAW-only shot promotes its extraction to representative (standard V/F6), and
X4 says one sidecar per media file — but the ``._exif`` the pipeline already
holds describes the *RAW*: its dimensions, its file size, its type. Handing that
sidecar to the JPEG would make it lie about its subject, and leaving the JPEG
bare trips the ``e`` audit marker on every RAW-only folder.

So the extraction is put through exiftool exactly like any other media file. It
has to happen here rather than in ``exiftool-batch``: the extractions do not
exist yet when that stage runs — the converters (``convert-crws``,
``launch-dpviewer``, ``raw-staged-conversion``) produce them several stages
later. This runs after the last of them and before ``folder-sorting`` places
the files, so the sidecar travels with its subject.

The sidecar is attached to the asset as ``converted_jpg_exif``; folder-sorting
handles that key beside the extraction itself, since it is named after the JPEG
rather than after the asset's RAW primary.
"""

import subprocess
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    project_root
from src.pipeline_stages.exiftool_sidecars import \
    SIDECAR_SUFFIX, \
    WRITE_FORMAT, \
    chunk_targets, \
    exiftool_command


def pending_extractions(context: PipelineContext) -> list:
    """Assets whose extracted JPEG exists and has no sidecar yet.

    Re-runnable: an extraction that already has one is skipped, so a resumed
    run does not pay for exiftool twice.
    """
    pending = []
    for asset in context.assets:
        extracted = asset.sidecars.get("converted_jpg")
        if extracted is None or not Path(extracted).exists():
            continue
        if Path(f"{extracted}{SIDECAR_SUFFIX}").exists():
            continue
        pending.append(asset)
    return pending


class ExtractedSidecarsStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="extracted-sidecars",
            display_name="Extracted Sidecars",
            dependencies=("raw-staged-conversion",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        pending = pending_extractions(context)
        context.set_stage_stats(self.stage_id, inputs=len(pending), outputs=0, errors=0)
        if not pending:
            context.log("No extracted JPEGs awaiting a sidecar")
            return context

        exiftool = exiftool_command(context.config, project_root())
        targets = [Path(asset.sidecars["converted_jpg"]) for asset in pending]
        base_command = [exiftool, "-a", "-u", "-g1", "-w!", WRITE_FORMAT]

        for chunk in chunk_targets(targets):
            try:
                subprocess.check_call(base_command + chunk)
            except FileNotFoundError as error:
                # WinError 206 ("filename or extension is too long") also maps
                # to FileNotFoundError; do not mistake it for a missing binary.
                if getattr(error, "winerror", None) == 206:
                    context.log(f"Extracted sidecars failed: command line too long ({error})")
                else:
                    context.log(f"ExifTool executable not found: {exiftool}")
                break
            except subprocess.CalledProcessError as error:
                # Exit 1 means some files could not be read; the rest were still
                # written, so keep going.
                context.log(f"ExifTool reported errors (exit code {error.returncode})")
            except OSError as error:
                context.log(f"Extracted sidecars failed: {error}")
                break

        created = 0
        for asset in pending:
            sidecar = Path(f"{asset.sidecars['converted_jpg']}{SIDECAR_SUFFIX}")
            if sidecar.exists():
                asset.sidecars["converted_jpg_exif"] = sidecar
                created += 1

        missing = len(pending) - created
        context.set_stage_stats(self.stage_id, outputs=created, errors=missing)
        context.counters["extracted_sidecars"] = created
        context.log(f"Generated {created} sidecars for {len(pending)} extracted JPEG(s)")
        if missing:
            # Named, not just counted: a bare extraction is exactly what the
            # "e" audit marker will report later, so say which ones now.
            context.log(f"No sidecar for {missing} extracted JPEG(s):")
            for asset in pending:
                if "converted_jpg_exif" not in asset.sidecars:
                    context.log(f"  - {Path(asset.sidecars['converted_jpg']).name}")
        return context
