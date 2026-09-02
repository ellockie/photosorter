"""Sort related files after screenshot grouping.

The pipeline stage. All of the matching lives in ``companion_matching.py`` —
see that module for why it is separate — and this file is the part that knows
about a pipeline run: which folders this run grouped, what the config says,
where the counters go.

``reconcile_folder`` is re-exported because the dashboard and the tests import
it from here, and because "reconcile this folder" reads better than the module
it happens to live in.
"""

from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    safe_move
from src.pipeline_stages.companion_matching import \
    PlacementReport, \
    ReconcileReport, \
    place_companions, \
    representative_keys, \
    shot_key
from src.pipeline_stages.companion_matching import \
    reconcile_folder as _reconcile_folder

__all__ = [
    "CompanionReconciliationStage",
    "PlacementReport",
    "ReconcileReport",
    "place_companions",
    "reconcile_folder",
    "representative_keys",
    "shot_key",
]


def reconcile_folder(event_folder: Path, config: dict,
                     log=lambda _msg: None) -> ReconcileReport:
    """Reconcile one event folder, moving with the project's retry convention.

    ``safe_move`` rather than the engine's plain default: a live run works over
    Dropbox and, on a restructure, over SMB, where a dropped handle must be
    retried instead of ending the folder.
    """
    return _reconcile_folder(event_folder, config, log, move=safe_move)


class CompanionReconciliationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="companion-reconciliation",
            display_name="Companion Reconciliation",
            dependencies=("grouping-review",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        settings = context.config.get("companion_reconciliation", {})
        context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)

        if not settings.get("enabled", False):
            context.log("Companion reconciliation disabled, skipping")
            return context

        folders = list(context.screenshot_grouped_folders)
        if not folders:
            context.log("No grouped folders to reconcile")
            return context

        totals = ReconcileReport()
        for folder in folders:
            try:
                report = reconcile_folder(folder, context.config, context.log)
            except Exception as error:  # never abandon the remaining folders
                totals.errors += 1
                context.log(f"  ! reconciling {folder.name} failed: {error!r}")
                continue
            if report.seen:
                context.log(f"Reconciled {folder.name}: {report.summary()}")
            totals.merge(report)

        context.counters["companions_reconciled"] += totals.moved
        context.counters["companions_unmatched"] += totals.unmatched
        context.counters["companions_left_behind"] += totals.left_behind
        context.counters["companions_reconcile_errors"] += totals.errors
        context.set_stage_stats(
            self.stage_id,
            inputs=totals.seen,
            outputs=totals.moved,
            errors=totals.errors,
        )
        context.log(
            f"Reconciled {totals.moved} companion file(s) across {len(folders)} folder(s)"
            + (f"; {totals.left_behind} left behind" if totals.left_behind else "")
            + (f"; {totals.errors} error(s)" if totals.errors else "")
        )
        return context
