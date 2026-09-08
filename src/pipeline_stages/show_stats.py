"""The run's own account of itself, in the order a person asks the questions.

The counters exist all along; what was missing was anywhere that reads them
back as a story. "assets=412, renamed=409, sorted=409" is three numbers you
have to know the pipeline to interpret. What a reader wants is: this much came
in, this is where it went, this much needs your attention, and here is where
the time went.

Grouped rather than dumped, because a flat list of thirty counters is as
unreadable as no counters at all. A group with nothing in it is skipped: a
line of zeroes is noise that hides the line that is not zero.
"""

from src.core import \
    PipelineContext, \
    PipelineStage
from src.utils.progress import \
    format_bytes, \
    format_count, \
    format_duration


# (heading, [(counter key, label)]). Keys absent or zero are dropped, so the
# same table serves a 4-file run and a 4,000-file one.
SUMMARY_GROUPS = (
    ("Came in", (
        ("input_files", "files in the inbox at the start"),
        ("input_checksums", "of them distinct by content"),
        ("input_bytes", "bytes to process"),
        ("legacy_unsorted_migrated", "migrated from the legacy unsorted folder"),
        ("uploaded_files_moved", "harvested from Camera Uploads"),
        ("folder_intake_files", "flattened out of inbox subfolders"),
        ("camera_upload_photos", "camera photos separated"),
        ("camera_upload_videos", "videos separated"),
    )),
    ("Processed", (
        ("assets", "assets with metadata read"),
        ("renamed_assets", "renamed to canonical names"),
        ("timezone_corrected_assets", "capture times corrected for clock/travel"),
        ("sorted_assets", "moved into event folders"),
        ("event_folders_touched", "event folders written"),
        ("companions_reconciled", "companion files placed beside their shot"),
    )),
    ("Set aside", (
        ("moved_old_exifs", "stale EXIF sidecars parked"),
        ("empty_files_quarantined", "zero-byte files quarantined"),
        ("rename_skipped_assets", "assets left with their original name"),
        ("raw_only_shots", "RAW-only shots (no camera JPEG)"),
        ("other_image_infographics", "infographics filed separately"),
        ("other_image_text_screenshots", "text screenshots filed separately"),
    )),
    ("Needs a look", (
        ("rename_exif_missing", "assets with no EXIF capture time"),
        ("timezone_ambiguous_assets", "readings inside a repeated hour"),
        ("companions_left_behind", "companions that found no shot"),
        ("companions_reconcile_errors", "folders that failed to reconcile"),
    )),
    ("Verified", (
        ("safety_inputs_matched", "input files found again in the output"),
        ("safety_files_scanned", "archive files checksummed"),
        ("safety_bytes_read", "bytes re-read to prove it"),
    )),
)

# Counters whose natural unit is bytes, not a count.
BYTE_KEYS = {"input_bytes", "safety_bytes_read"}


class ShowStatsStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="show-stats",
            display_name="Show Stats",
            description=(
                "Totals the run: what came in, where it went, what needs a look, "
                "and which stages took the time."
            ),
            dependencies=("folder-sorting",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        reported = self._report_counters(context)
        self._report_timings(context)
        self._report_outstanding(context)

        context.set_stage_stats(
            self.stage_id,
            inputs=context.counters.get("input_files", 0),
            outputs=context.counters.get("sorted_assets", 0),
            errors=len([p for p in context.prompt_queue if not p.answered]),
            counters_reported=reported,
        )
        return context

    def _report_counters(self, context: PipelineContext) -> int:
        shown = 0
        for heading, rows in SUMMARY_GROUPS:
            lines = [
                (key, context.counters.get(key, 0), label)
                for key, label in rows
                if context.counters.get(key, 0)
            ]
            if not lines:
                continue
            context.log(f"{heading}:")
            for key, value, label in lines:
                rendered = format_bytes(value) if key in BYTE_KEYS else format_count(value)
                context.log(f"  {rendered:>12}  {label}")
                shown += 1
        if not shown:
            context.log("Nothing moved this run -- every counter is zero.")
        return shown

    def _report_timings(self, context: PipelineContext) -> None:
        """Where the wall clock went, worst first.

        The run summary the orchestrator writes lands after every stage, which
        is after this one; repeating the ranking here puts it in the middle of
        the stats a reader is already looking at.
        """
        durations = sorted(
            (
                (stage_id, timing.get("duration_seconds") or 0.0)
                for stage_id, timing in context.stage_timings.items()
                if stage_id != "__run__" and timing.get("duration_seconds")
            ),
            key=lambda item: item[1],
            reverse=True,
        )
        if not durations:
            return
        total = sum(seconds for _stage, seconds in durations)
        context.log(f"Time so far: {format_duration(total)} across {len(durations)} stage(s)")
        for stage_id, seconds in durations[:5]:
            if seconds < 0.5:
                continue
            share = (seconds / total * 100) if total else 0
            context.log(f"  {format_duration(seconds):>12}  {stage_id} ({share:.0f}%)")

    def _report_outstanding(self, context: PipelineContext) -> None:
        pending = [prompt for prompt in context.prompt_queue if not prompt.answered]
        if not pending:
            return
        kinds: dict[str, int] = {}
        for prompt in pending:
            kinds[prompt.prompt_type] = kinds.get(prompt.prompt_type, 0) + 1
        context.log(f"Waiting on you: {len(pending)} decision(s)")
        for kind, count in sorted(kinds.items()):
            context.log(f"  {count:>12}  {kind.replace('_', ' ')}")
