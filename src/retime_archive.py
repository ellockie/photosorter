"""Stand-alone retro time-correction for an already-sorted archive (Decision 9).

Runs the *same* two-timeline correction engine as the pipeline, but against
event folders that are already named and sorted. Given a date range and a parent
folder holding many event folders, it re-times each representative image and
re-folds it across the ``04:44:44`` day boundary when the correction moves its
day.

Design properties:

* **EXIF is the source, never the filename** — the original camera reading lives
  in the ``._exif`` sidecar (``Date/Time Original``); the filename already holds
  a corrected time, so reading it would double-correct. Reading EXIF makes the
  tool idempotent: a second run with the same config is a no-op.
* **Descriptions are opaque** — the event-folder description (``- Japan``,
  ``- Birthday``, ``- 1. ######``) is carried verbatim onto the corrected date;
  the tool never re-derives or second-guesses it.
* **Re-folds across the day boundary** — a corrected day lands the file in a
  sibling ``<new-date> - <same description>`` folder, created if missing.
* **Prompts, never guesses** — a file whose corrected day already holds multiple
  unnamed placeholder events is reported and skipped, not guessed.

This is intentionally NOT a ``main.py`` subcommand; it runs independently::

    python -m src.retime_archive --from 2026-04-01 --to 2026-04-30 --folder "c:/__PHOTOS/2026/04. April"
"""

import argparse
import datetime
import re
from pathlib import Path

from src.core import load_config, safe_move
from src.pipeline_stages.legacy import (
    date_folder_datetime,
    date_folder_suffix,
    parse_legacy_exif_sidecar,
)
from src.pipeline_stages.taxonomy import taxonomy_folder
from src.pipeline_stages.timezone_engine import correct, format_stamp

# Event folder: ``2026-04-12_(Sun)`` optionally followed by `` - <description>``.
_EVENT_FOLDER = re.compile(r"^(\d{4}-\d{2}-\d{2})_\(([A-Za-z]{3})\)(?: - (.*))?$")
_LEADING_STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}_\([A-Za-z]{3}\)_\d{2}\.\d{2}\.\d{2}")
_PLACEHOLDER = re.compile(r"######")


def _media_extensions(config: dict) -> set[str]:
    extensions = config.get("extensions", {})
    values = []
    for key in ("lossy_images", "other_images", "raw_images", "videos"):
        values.extend(extensions.get(key, []))
    return {value.lower() for value in values}


def _event_folders(parent: Path) -> list[Path]:
    return sorted(
        path for path in parent.rglob("*")
        if path.is_dir() and _EVENT_FOLDER.match(path.name)
    )


def _target_folder_name(new_date: datetime.datetime, description: str | None, config: dict) -> str:
    base = new_date.strftime("%Y-%m-%d_(%a)")
    if description:
        return f"{base} - {description}"
    return base + date_folder_suffix(config)


def _exif_sidecar(event_folder: Path, image_name: str, config: dict) -> Path | None:
    exif_dir = event_folder / taxonomy_folder(config, "exif")
    candidate = exif_dir / f"{image_name}._exif"
    return candidate if candidate.exists() else None


def retime_archive(folder, from_date, to_date, config: dict, dry_run: bool = False) -> dict:
    """Re-time and re-fold every representative image in ``folder``'s event folders.

    ``from_date``/``to_date`` bound the *original* EXIF reading. Returns a summary
    of what changed (``retimed``, ``refolded``, ``skipped``, ``unchanged``).
    """
    parent = Path(folder)
    from_dt = from_date if isinstance(from_date, datetime.datetime) else datetime.datetime.fromisoformat(str(from_date))
    to_dt = to_date if isinstance(to_date, datetime.datetime) else datetime.datetime.fromisoformat(str(to_date))
    media_extensions = _media_extensions(config)
    summary = {"retimed": 0, "refolded": 0, "skipped": [], "unchanged": 0, "moves": []}

    for event_folder in _event_folders(parent):
        match = _EVENT_FOLDER.match(event_folder.name)
        description = match.group(3)
        for image in sorted(event_folder.iterdir()):
            if not image.is_file() or image.suffix.lower() not in media_extensions:
                continue
            if not _LEADING_STAMP.match(image.name):
                continue
            sidecar = _exif_sidecar(event_folder, image.name, config)
            if sidecar is None:
                continue

            metadata = parse_legacy_exif_sidecar(sidecar, config)
            reading = metadata.get("captured_at")
            if not isinstance(reading, datetime.datetime) or not (from_dt <= reading <= to_dt):
                continue

            result = correct(config, reading, metadata.get("camera_symbol", ""))
            display = result["display"]
            new_name = _LEADING_STAMP.sub(format_stamp(display), image.name, count=1)
            new_date = date_folder_datetime(display, config)
            target_folder_name = _target_folder_name(new_date, description, config)
            target_folder = event_folder.parent / target_folder_name

            if target_folder == event_folder and new_name == image.name:
                summary["unchanged"] += 1
                continue

            # Refusing to guess: a placeholder file landing where several unnamed
            # events already live is ambiguous — report and skip.
            if target_folder != event_folder and description and _PLACEHOLDER.search(description):
                siblings = [
                    p for p in event_folder.parent.iterdir()
                    if p.is_dir() and p.name.startswith(new_date.strftime("%Y-%m-%d_(%a)"))
                    and _PLACEHOLDER.search(p.name)
                ]
                if len(siblings) > 1:
                    summary["skipped"].append(str(image))
                    continue

            summary["moves"].append((str(image), str(target_folder / new_name)))
            if not dry_run:
                target_exif = target_folder / taxonomy_folder(config, "exif")
                safe_move(image, target_folder / new_name)
                safe_move(sidecar, target_exif / f"{new_name}._exif")
            summary["retimed"] += 1
            if target_folder != event_folder:
                summary["refolded"] += 1

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retro time-correct an already-sorted archive.")
    parser.add_argument("--from", dest="from_date", required=True, help="Start of original-reading range (ISO date).")
    parser.add_argument("--to", dest="to_date", required=True, help="End of original-reading range (ISO date).")
    parser.add_argument("--folder", required=True, help="Parent folder holding many event folders.")
    parser.add_argument("--config", default=None, help="Path to config.json (defaults to project config).")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without moving files.")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    summary = retime_archive(args.folder, args.from_date, args.to_date, config, dry_run=args.dry_run)

    prefix = "[dry-run] " if args.dry_run else ""
    for source, destination in summary["moves"]:
        print(f"{prefix}{source}\n      -> {destination}")
    for skipped in summary["skipped"]:
        print(f"SKIPPED (ambiguous placeholder day): {skipped}")
    print(
        f"\n{prefix}retimed={summary['retimed']} refolded={summary['refolded']} "
        f"unchanged={summary['unchanged']} skipped={len(summary['skipped'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
