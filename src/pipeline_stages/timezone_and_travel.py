import datetime
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage
from src.pipeline_stages.legacy import \
    date_folder_datetime
from src.pipeline_stages.stamps import \
    format_day_prefix, \
    format_stamp
from src.pipeline_stages.timezone_engine import \
    format_duration, \
    has_timezone_config, \
    model_from_config, \
    order_inversions

RETIME_PROMPT = "retime"
LOGS_FOLDER = "__LOGS"
# Nobody can answer in a headless run, and re-dating is a decision: the shots
# keep their camera readings and are listed for restructure step 0.
HEADLESS_ANSWER = {"action": "no"}


class TimezoneAndTravelStage(PipelineStage):
    """Name each shot by the local time it was taken (openspec camera-time-correction).

    Each asset's raw reading goes through the engine (camera clock, trips,
    calibrations). Where that changes a stamp, the shots are grouped by the
    event folder they are heading for and the user is asked once per folder:
    yes, yes to all remaining folders, or no. A declined folder's shots are
    named on their raw reading and listed in ``<year>\\__LOGS`` so restructure
    step 0 can re-date them later. Trips no longer write a label into names.
    """

    def __init__(self):
        super().__init__(
            stage_id="timezone-and-travel",
            display_name="Timezone and Travel",
            description=(
                "Corrects each capture time for the camera's clock and where you were, asking "
                "per folder, so filenames and folders carry the local time the shot was taken."
            ),
            dependencies=("metadata-extraction",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        if not has_timezone_config(context.config):
            context.log("Timezone/travel: nothing configured, leaving readings unchanged")
            return context
        model = model_from_config(context.config)
        if model.errors:
            raise ValueError("timezone.json cannot be used: " + "; ".join(model.errors))
        for warning in model.warnings:
            context.log(f"timezone.json: {warning}")

        groups: dict[str, list] = {}
        for asset in context.assets:
            captured_at = asset.metadata.get("captured_at")
            if isinstance(captured_at, str):
                captured_at = datetime.datetime.fromisoformat(captured_at)
            if not isinstance(captured_at, datetime.datetime):
                continue
            utc = asset.metadata.get("captured_utc")
            correction = model.correct_shot(asset.metadata.get("camera_symbol", ""),
                                            None if utc else captured_at, None, utc)
            day = format_day_prefix(date_folder_datetime(correction.stamp, context.config))
            label = asset.metadata.get("origin_label")
            groups.setdefault(day + (f" - {label}" if label else ""), []).append((asset, correction))

        corrected, declined, answer_all = 0, [], False
        for folder in sorted(groups):
            members = groups[folder]
            shifted = [(asset, correction) for asset, correction in members if correction.shift]
            if not shifted:
                continue
            if answer_all:
                choice = "all"
            else:
                prompt = context.create_prompt(RETIME_PROMPT, {
                    "folder": folder,
                    "instructions": "These shots would be re-dated to the local time they were taken. "
                                    "Yes / yes to all remaining folders / no (no keeps the camera's own "
                                    "time and lists them for restructure step 0).",
                    "lines": describe_group(folder, members, context.config, model),
                }, self.stage_id)
                choice = context.await_prompt(prompt, auto_answer=HEADLESS_ANSWER).get("action", "no")
            if choice == "all":
                answer_all = True
            if choice in ("yes", "all"):
                for asset, correction in shifted:
                    asset.metadata["captured_at_corrected"] = correction.stamp
                    if "image_datetime" in asset.metadata:
                        asset.metadata["image_datetime"] = format_stamp(correction.stamp)
                    corrected += 1
            else:
                declined.extend(shifted)
        for asset, correction in (pair for members in groups.values() for pair in members):
            asset.metadata["location_zone"] = correction.zone

        context.counters["timezone_corrected_assets"] += corrected
        context.log(f"Re-dated {corrected} asset(s) to local time")
        if declined:
            context.counters["timezone_declined_assets"] += len(declined)
            written = write_pending(declined, context.config)
            context.log(f"{len(declined)} asset(s) kept their camera time; listed for restructure step 0 in "
                        + ", ".join(str(path) for path in written))
        return context


def describe_group(folder: str, members: list, config: dict, model=None) -> list[str]:
    """What the prompt shows: per camera the clock, error and shift, examples, day moves, order."""
    lines = [f"Folder: {folder}"]
    cameras: dict = {}
    for asset, correction in members:
        if not correction.shift:
            continue
        cameras.setdefault(correction.camera, []).append((asset, correction))
    for camera, pairs in sorted(cameras.items()):
        shifts = sorted({int(c.shift.total_seconds()) for _, c in pairs})
        shift = format_duration(shifts[0]) if len(shifts) == 1 else \
            f"{format_duration(shifts[0])} .. {format_duration(shifts[-1])}"
        clocks = ", ".join(sorted({c.clock for _, c in pairs}))
        errors = ", ".join(f"{e:+d} s" for e in sorted({c.error_seconds for _, c in pairs}))
        sources = "/".join(sorted({c.source for _, c in pairs}))
        lines.append(f"{camera}: {len(pairs)} shot(s), clock {clocks}, error {errors} -> {shift} ({sources})")
        for _, c in sorted(pairs, key=lambda pair: pair[1].reading)[:3]:
            lines.append(f"    {format_stamp(c.reading)} -> {format_stamp(c.stamp)}")
        moved = sum(1 for _, c in pairs
                    if date_folder_datetime(c.reading, config).date() != date_folder_datetime(c.stamp, config).date())
        if moved:
            lines.append(f"    {moved} shot(s) change day")
        ambiguous = sum(1 for _, c in pairs if c.ambiguous)
        if ambiguous:
            lines.append(f"    {ambiguous} reading(s) in a repeated hour, taken as after the clock change")
    inversions = order_inversions([(c.stamp_text, c.true_utc, asset.primary_path.name) for asset, c in members])
    if inversions and model is not None and model.accepts_order(folder):
        lines.append(f"Name order: {len(inversions)} shot(s) out of time order, accepted in timezone.json")
    else:
        lines.append(f"Name order: {len(inversions)} shot(s) out of time order (reported only)" if inversions
                     else "Name order: chronological")
    return lines


def write_pending(declined: list, config: dict) -> list[Path]:
    """List declined shots in ``<root>\\<year>\\__LOGS`` (J1), one file per year."""
    root = Path(config.get("paths", {}).get("root_folder", "."))
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H.%M.%S")
    by_year: dict[str, list] = {}
    for asset, correction in declined:
        by_year.setdefault(f"{date_folder_datetime(correction.reading, config):%Y}", []).append((asset, correction))
    written = []
    for year, pairs in sorted(by_year.items()):
        path = root / year / LOGS_FOLDER / f"retime_pending_{stamp}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = ["Shots kept on their camera time at intake; re-date them with restructure step 0.",
                "reading -> local stamp   camera   original file", ""]
        rows += [f"{format_stamp(c.reading)} -> {format_stamp(c.stamp)}   {c.camera:<8} {asset.primary_path.name}"
                 for asset, c in sorted(pairs, key=lambda pair: pair[1].reading)]
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        written.append(path)
    return written
