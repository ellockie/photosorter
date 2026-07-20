"""Sort related files after screenshot grouping.

When the grouper GUI splits a sorted event folder (e.g.
"2026-07-18_(Sat) - __TO_SPLIT__(…)") into named sub-event folders, only the
top-level representative images move; each shot's RAW original, EXIF sidecar,
video, etc. stay behind in the event folder's taxonomy subdirs (__RAW, __EXIF,
__VIDEOS, …). This stage reunites them: for every companion file it finds the
sub-event folder that received the matching representative image (matched by the
leading date+time in the filename) and moves the companion into the same-named
taxonomy subdir there. Nothing is ever deleted; companions with no located
representative (e.g. videos that never appeared in the grouper) are left in
place and reported.
"""

import re
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.pipeline_stages.taxonomy import DEFAULT_TAXONOMY

# Leading date + time shared by every file of one shot, tolerant of the
# Photosorter form "2026-07-18_(Sat)_17.04.53…" and the grouper form
# "2026-07-18__14.30.00…". Normalised to bare digits so both compare equal.
_DT_KEY = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\(\w{3}\))?[ _]+(\d{2})\.(\d{2})\.(\d{2})"
)
_TO_SPLIT_MARKER = "__TO_SPLIT__"


def shot_key(name: str) -> str | None:
    """Return the normalized YYYYMMDDHHMMSS key of a filename, or None."""
    match = _DT_KEY.match(name)
    if not match:
        return None
    return "".join(match.groups())


def taxonomy_dir_names(config: dict) -> set[str]:
    names = set(DEFAULT_TAXONOMY.values())
    names.update((config.get("taxonomy") or {}).values())
    return names


def reconcile_folder(event_folder: Path, config: dict, log=lambda _msg: None) -> tuple[int, int]:
    """Move a folder's taxonomy companions to follow their representative images.

    Returns (moved, unmatched).
    """
    if not event_folder.is_dir():
        return (0, 0)

    tax_names = taxonomy_dir_names(config)
    tax_dirs = [
        child
        for child in event_folder.iterdir()
        if child.is_dir() and child.name in tax_names
    ]
    if not tax_dirs:
        return (0, 0)

    # Index every companion by its shot key: key -> [(taxonomy_dir_name, path)].
    companions: dict[str, list[tuple[str, Path]]] = {}
    for tax_dir in tax_dirs:
        for path in tax_dir.iterdir():
            if not path.is_file():
                continue
            key = shot_key(path.name)
            if key is None:
                continue
            companions.setdefault(key, []).append((tax_dir.name, path))
    if not companions:
        return (0, 0)

    # Map each shot key to the sub-event folder that received its representative
    # image. Sub-events are siblings created by the grouper, sharing the leading
    # YYYY-MM-DD date; the leftover TO_SPLIT folder itself is excluded.
    date_prefix = event_folder.name[:10]
    dest_by_key: dict[str, Path] = {}
    for sibling in event_folder.parent.iterdir():
        if not sibling.is_dir() or sibling == event_folder:
            continue
        if not sibling.name.startswith(date_prefix) or _TO_SPLIT_MARKER in sibling.name:
            continue
        for path in sibling.iterdir():
            if not path.is_file():
                continue
            key = shot_key(path.name)
            if key is not None:
                dest_by_key.setdefault(key, sibling)

    moved = 0
    unmatched = 0
    for key, items in companions.items():
        dest = dest_by_key.get(key)
        if dest is None:
            unmatched += len(items)
            continue
        for tax_name, path in items:
            target_dir = dest / tax_name
            target = target_dir / path.name
            if target.exists():
                # Idempotent re-run or genuine clash: leave the original in place
                # rather than risk overwriting; a later manual pass can resolve it.
                continue
            safe_move(path, target)
            moved += 1

    _prune_empty_taxonomy_dirs(tax_dirs, log)
    return (moved, unmatched)


def _prune_empty_taxonomy_dirs(tax_dirs: list[Path], log) -> None:
    for tax_dir in tax_dirs:
        try:
            if tax_dir.is_dir() and not any(tax_dir.iterdir()):
                tax_dir.rmdir()
        except OSError as error:
            log(f"  ! could not remove empty {tax_dir.name}: {error}")


class CompanionReconciliationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="companion-reconciliation",
            display_name="Companion Reconciliation",
            dependencies=("screenshot-grouping",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        settings = context.config.get("companion_reconciliation", {})
        context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)

        if not settings.get("enabled", False):
            context.log("Companion reconciliation disabled, skipping")
            return context

        folders = [f for f in context.screenshot_grouped_folders if f.is_dir()]
        if not folders:
            context.log("No grouped folders to reconcile")
            return context

        moved_total = 0
        unmatched_total = 0
        for folder in folders:
            moved, unmatched = reconcile_folder(folder, context.config, context.log)
            if moved or unmatched:
                context.log(
                    f"Reconciled {folder.name}: moved {moved} companion(s)"
                    + (f", {unmatched} left unmatched" if unmatched else "")
                )
            moved_total += moved
            unmatched_total += unmatched

        context.counters["companions_reconciled"] += moved_total
        context.counters["companions_unmatched"] += unmatched_total
        context.set_stage_stats(
            self.stage_id,
            inputs=moved_total + unmatched_total,
            outputs=moved_total,
            errors=unmatched_total,
        )
        context.log(
            f"Reconciled {moved_total} companion file(s) across {len(folders)} folder(s)"
            + (f"; {unmatched_total} left unmatched" if unmatched_total else "")
        )
        return context
