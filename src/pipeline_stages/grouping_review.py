"""Gate the pipeline until this run's event folders have really been named.

The grouper GUI exiting does not mean the work is finished. Closing the window
is one keystroke; naming the day is not. Folders can be left carrying
"__TO_SPLIT__" or "__TO_LABEL__", or the bare " - 1. ######" placeholder that
folder-sorting wrote — and the user often finishes the job afterwards, by hand,
in Explorer.

Running companion-reconciliation at that moment reconciles against a half-done
tree: sidecars follow representatives that are about to move again, and the
folder paths recorded before the GUI ran may no longer exist at all.

So this stage does two things, and neither of them guesses:

1. Reports every folder from this run that is still unnamed, and blocks on a
   prompt until the user either says they are done or asks for a re-scan. The
   wait has no timeout (see PipelineContext.await_prompt) — "Continue anyway"
   is there for when there is nothing left to wait for, not for when the clock
   runs out.
2. Re-resolves which folders companion-reconciliation should look at, by
   scanning the archive as it stands *now* rather than trusting paths captured
   before the GUI renamed and deleted things.
"""

import datetime
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.legacy import date_folder_suffix
from src.pipeline_stages.stamps import day_prefix
from src.pipeline_stages.taxonomy import DEFAULT_TAXONOMY

# Names the grouper leaves on a folder it could not name for the user.
UNNAMED_MARKERS = ("__TO_SPLIT__", "__TO_LABEL__")

# A group that runs past midnight is named after its earliest file, so it keeps
# the day it started on — but a sub-event split off near the boundary can land
# on the neighbouring date. One day either side covers that without dragging in
# unrelated history.
_DAY_SPAN = 1


def _taxonomy_dir_names(config: dict) -> set[str]:
    names = set(DEFAULT_TAXONOMY.values())
    names.update((config.get("taxonomy") or {}).values())
    return names


def _neighbouring_days(date_text: str) -> set[str]:
    try:
        day = datetime.date.fromisoformat(date_text)
    except ValueError:
        return {date_text}
    return {
        (day + datetime.timedelta(days=offset)).isoformat()
        for offset in range(-_DAY_SPAN, _DAY_SPAN + 1)
    }


def review_scope(context: PipelineContext) -> dict[Path, set[str]]:
    """Parent folder -> the day prefixes this run touched under it.

    Built from the folders the grouper was opened on and the event folders
    folder-sorting wrote to, so the scan can never wander into parts of the
    archive this run never touched.
    """
    scope: dict[Path, set[str]] = {}
    touched = list(context.screenshot_grouped_folders) + list(context.affected_event_folders)
    for folder in touched:
        date_text = day_prefix(folder.name)
        if date_text is None:
            continue
        scope.setdefault(folder.parent, set()).update(_neighbouring_days(date_text))
    return scope


def _in_scope(folder: Path, days: set[str]) -> bool:
    prefix = day_prefix(folder.name)
    return prefix is not None and prefix in days


def is_unnamed(folder: Path, config: dict) -> bool:
    """True when a folder still needs a human to give it a name."""
    name = folder.name
    if any(marker in name for marker in UNNAMED_MARKERS):
        return True
    return name.endswith(date_folder_suffix(config))


def pending_folders(context: PipelineContext, scope: dict[Path, set[str]]) -> list[Path]:
    """Every in-scope folder that is still unnamed, in alphabetical order."""
    found: list[Path] = []
    for parent, days in scope.items():
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if not child.is_dir() or not _in_scope(child, days):
                continue
            if is_unnamed(child, context.config):
                found.append(child)
    # Alphabetical, matching the order the grouper opened them in.
    found.sort(key=lambda path: str(path).lower())
    return found


def reconcilable_folders(context: PipelineContext, scope: dict[Path, set[str]]) -> list[Path]:
    """In-scope folders that still hold companions needing a home.

    Any folder with a taxonomy subdir qualifies, whether or not the grouper
    touched it: reconciling one whose representatives never left is a harmless
    no-op ("representative still here"), whereas missing one strands its
    sidecars for good. Scanning live also picks up the folder the grouper
    renamed out from under the path recorded before it ran.
    """
    tax_names = _taxonomy_dir_names(context.config)
    found: list[Path] = []
    for parent, days in scope.items():
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if not child.is_dir() or not _in_scope(child, days):
                continue
            if any((child / name).is_dir() for name in tax_names):
                found.append(child)
    found.sort(key=lambda path: str(path).lower())
    return found


class GroupingReviewStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="grouping-review",
            display_name="Grouping Review",
            dependencies=("screenshot-grouping",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        settings = context.config.get("grouping_review", {})
        enabled = settings.get("enabled")
        if enabled is None:
            # Unset follows the grouper: naming is only expected of a run that
            # actually opened it.
            enabled = context.config.get("screenshot_grouping", {}).get("enabled", False)
        scope = review_scope(context)
        context.set_stage_stats(self.stage_id, inputs=len(scope), outputs=0, errors=0)

        if not enabled:
            context.log("Grouping review disabled, skipping")
        elif not scope:
            context.log("No folders from this run to review")
        else:
            self._review(context, scope, settings)

        # Always re-resolve, even when the review itself is switched off: the
        # paths recorded before the GUI ran are stale either way.
        folders = reconcilable_folders(context, scope)
        context.screenshot_grouped_folders = folders
        context.log(f"{len(folders)} folder(s) queued for companion reconciliation")
        context.set_stage_stats(self.stage_id, outputs=len(folders))
        return context

    def _review(self, context: PipelineContext, scope: dict[Path, set[str]],
                settings: dict) -> None:
        """Prompt, re-scan, prompt again — until the user says to move on."""
        round_number = 0
        while True:
            round_number += 1
            pending = pending_folders(context, scope)
            if not pending:
                context.log("Every folder from this run is named")
                return

            context.log(f"{len(pending)} folder(s) still unnamed:")
            for folder in pending:
                context.log(f"  - {folder.name}")
            context.counters["grouping_review_pending"] = len(pending)

            prompt = context.create_prompt(
                "grouping_review",
                {
                    "round": round_number,
                    "folders": [str(folder) for folder in pending],
                    "names": [folder.name for folder in pending],
                    "instructions": (
                        "Rename these folders (in the grouper or in Explorer), "
                        "then press Re-scan. Continue anyway leaves them as they "
                        "are and reconciles the rest."
                    ),
                },
                self.stage_id,
            )
            # No UI to ask means no one can rename them either, so continuing is
            # the only honest fallback — and it is logged, not silent.
            answer = context.await_prompt(prompt, auto_answer={"action": "continue"})
            if str(answer.get("action", "continue")) != "rescan":
                context.log(
                    f"Continuing with {len(pending)} folder(s) still unnamed"
                )
                return
