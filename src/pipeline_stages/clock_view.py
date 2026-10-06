"""What clock every camera was on, folder by folder -- the timezone visualiser.

Laid out like ``git log --graph``. Each UTC offset is a **lane** at a fixed
column. Inside every lane the **slots** are fixed too: slot 0 is local time
(where the user was, per ``timezone.json``), then one slot per camera in a
global order that never changes between rows. A camera is drawn in the lane of
the offset its *clock* was on, so a camera that matches local time sits beside
the local marker rather than on top of it, and a lagging one stands out in
another lane. Full-width rules mark DST changes and trip boundaries in time
order. Folder names all start in one column; depth is its own column.

READ-ONLY: built from sidecars through the engine, never writes a file.
Leaf module: engine, readings, stamps.
"""

import dataclasses
import datetime
import html

from src.pipeline_stages.clock_readings import exposures
from src.pipeline_stages.stamps import \
    LEADING_STAMP_RE, \
    format_stamp
from src.pipeline_stages.timezone_engine import \
    SOURCE_ASSUMED, \
    SOURCE_CALIBRATED, \
    SOURCE_CONFIGURED, \
    SOURCE_MOBILE, \
    TimeModel, \
    format_duration, \
    order_inversions

LANE_STEP = datetime.timedelta(minutes=15)
GLYPHS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
UNICODE = {"local": "◆", "empty": "·", "rule": "═", "lane": "│", "change": "↕"}
ASCII = {"local": "*", "empty": ".", "rule": "=", "lane": "|", "change": "~"}


def lane_of(offset: datetime.timedelta) -> datetime.timedelta:
    steps = round(offset / LANE_STEP)
    return steps * LANE_STEP


def format_offset(offset: datetime.timedelta) -> str:
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    hours, minutes = divmod(abs(minutes), 60)
    return f"{sign}{hours:02d}:{minutes:02d}"


def _declared(text):
    if not text:
        return None
    try:
        sign = -1 if text.strip()[0] == "-" else 1
        hours, minutes = text.strip().lstrip("+-").split(":")[:2]
        return sign * datetime.timedelta(hours=int(hours), minutes=int(minutes))
    except (ValueError, IndexError):
        return None


@dataclasses.dataclass
class CameraCell:
    camera: str
    lanes: set
    sources: set
    shifts: set
    shots: int = 0
    ambiguous: int = 0


@dataclasses.dataclass
class Row:
    depth: int
    name: str
    path: str
    roots: str
    first_utc: datetime.datetime | None
    cameras: dict
    local_lanes: set
    inversions: list
    notes: list

    @property
    def has_shots(self) -> bool:
        return bool(self.cameras)


@dataclasses.dataclass
class Rule:
    instant: datetime.datetime
    text: str
    kind: str          # "dst" | "trip"


@dataclasses.dataclass
class View:
    rows: list
    rules: list
    lanes: list        # offsets, ascending
    cameras: list      # global camera order
    glyphs: dict       # camera -> glyph
    models: dict       # camera -> camera model names seen


def root_labels(roots) -> list[str]:
    """A short tag per root: its drive letter, or ``NAS`` for a network share; numbered if repeated."""
    labels = []
    for root in roots:
        drive = getattr(root, "drive", "") or ""
        label = drive[0].upper() if len(drive) == 2 and drive[1] == ":" else "NAS"
        if label in labels:
            label = f"{label}{sum(1 for existing in labels if existing.startswith(label)) + 1}"
        labels.append(label)
    return labels


def build_view(folders, model: TimeModel, labels=None) -> View:
    """``folders`` are ``MergedFolder``-like: ``depth``, ``relative``, ``copies``, ``readings``."""
    rows, cameras, models = [], [], {}
    lanes = set()
    first, last = None, None
    for folder in folders:
        cells: dict[str, CameraCell] = {}
        local_lanes, notes, items = set(), [], []
        phone_says, camera_says = set(), set()
        first_utc = None
        for shot in exposures(folder.readings):
            correction = model.correct_shot(shot.camera, shot.reading, shot.counter, shot.utc)
            if shot.camera not in cameras:
                cameras.append(shot.camera)
            models.setdefault(shot.camera, set()).add(shot.model or "?")
            cell = cells.setdefault(shot.camera, CameraCell(shot.camera, set(), set(), set()))
            clock_lane = lane_of(correction.clock_offset)
            local_lane = lane_of(correction.local_offset)
            cell.lanes.add(clock_lane)
            cell.sources.add(correction.source)
            cell.shifts.add(int(correction.shift.total_seconds()))
            cell.shots += 1
            cell.ambiguous += correction.ambiguous
            local_lanes.add(local_lane)
            lanes.update((clock_lane, local_lane))
            declared = _declared(shot.declared_offset)
            if correction.source == SOURCE_MOBILE:
                if declared is not None and lane_of(declared) != local_lane:
                    phone_says.add((format_offset(declared), format_offset(local_lane)))
            elif declared is not None and lane_of(declared) != clock_lane:
                camera_says.add((shot.camera, format_offset(declared), format_offset(clock_lane)))
            if shot.subdir == "":
                match = LEADING_STAMP_RE.match(shot.subject.name)
                tail = shot.subject.name[match.end():] if match else shot.subject.name
                items.append((correction.stamp_text + tail, correction.true_utc, shot.subject.name))
            if first_utc is None or correction.true_utc < first_utc:
                first_utc = correction.true_utc
            first = correction.true_utc if first is None or correction.true_utc < first else first
            last = correction.true_utc if last is None or correction.true_utc > last else last
        for said, local in sorted(phone_says):
            notes.append(f"phones say {said} but local is {local} -- a trip missing from timezone.json?")
        for camera, said, assumed in sorted(camera_says):
            notes.append(f"{camera} declares {said} but its clock is taken as {assumed} "
                         "(declared offsets are evidence only -- check with a calibration)")
        inversions = order_inversions(items)
        if inversions:
            notes.append(f"{len(inversions)} shot(s) would sort out of time order, e.g. {inversions[0][0]}")
        for cell in cells.values():
            if cell.ambiguous:
                notes.append(f"{cell.camera}: {cell.ambiguous} reading(s) in a repeated hour (assumed after the change)")
        rows.append(Row(folder.depth, folder.relative.name, str(folder.relative),
                        "+".join(labels[index] if labels and index < len(labels) else str(index)
                                 for index in sorted(folder.copies)),
                        first_utc, cells, local_lanes, inversions, notes))
    rules = []
    if first is not None:
        for instant, zone, before, after in model.dst_changes(first - datetime.timedelta(days=1),
                                                              last + datetime.timedelta(days=1)):
            rules.append(Rule(instant, f"DST {zone} {format_offset(before)} -> {format_offset(after)}  "
                                       f"{instant:%Y-%m-%d %H:%M} UTC", "dst"))
        for trip in model.trips:
            # A trip overlapping what is shown shows both its ends, wherever they fall.
            if trip.end_utc < first - datetime.timedelta(days=1) or trip.start_utc > last + datetime.timedelta(days=1):
                continue
            place = trip.place if trip.place == trip.zone.key else f"{trip.place} ({trip.zone.key})"
            rules.append(Rule(trip.start_utc, f"TRIP {place} from {format_stamp(trip.start_wall)}", "trip"))
            rules.append(Rule(trip.end_utc, f"TRIP {place} ends {format_stamp(trip.end_wall)}", "trip"))
    rules.sort(key=lambda rule: rule.instant)
    glyphs = {camera: GLYPHS[index % len(GLYPHS)] for index, camera in enumerate(cameras)}
    return View(rows, rules, sorted(lanes), cameras, glyphs, models)


def _cell_summary(cell: CameraCell) -> str:
    if SOURCE_MOBILE in cell.sources:
        return f"{cell.camera} mobile"
    source = ("calibrated" if SOURCE_CALIBRATED in cell.sources else
              "configured" if SOURCE_CONFIGURED in cell.sources else
              "ASSUMED home" if SOURCE_ASSUMED in cell.sources else "no shift")
    shifts = sorted(cell.shifts)
    if shifts == [0]:
        return f"{cell.camera} {source}"
    shift = format_duration(shifts[0]) if len(shifts) == 1 else \
        f"{format_duration(shifts[0])}..{format_duration(shifts[-1])}"
    return f"{cell.camera} {source} {shift}"


def _interleave(view: View):
    """Rows and rules in one sequence: each rule before the first row taken after it."""
    pending = list(view.rules)
    for row in view.rows:
        while pending and row.first_utc is not None and pending[0].instant <= row.first_utc:
            yield pending.pop(0)
        yield row
    yield from pending


def render_text(view: View, glyph_set=UNICODE, width_name: int = 0) -> list[str]:
    slots = 1 + len(view.cameras)
    lane_width = max(slots * 2 - 1, len("UTC+00:00"))
    lane_sep = f" {glyph_set['lane']} "
    graph_width = len(view.lanes) * lane_width + max(0, len(view.lanes) - 1) * len(lane_sep)

    def graph_line(row: Row) -> str:
        parts = []
        for lane in view.lanes:
            cells = [glyph_set["local"] if lane in row.local_lanes else glyph_set["empty"]]
            for camera in view.cameras:
                cell = row.cameras.get(camera)
                if cell is None or lane not in cell.lanes:
                    cells.append(glyph_set["empty"] if cell is None else " ")
                else:
                    cells.append(view.glyphs[camera] if len(cell.lanes) == 1 else glyph_set["change"])
            parts.append(" ".join(cells).ljust(lane_width))
        return lane_sep.join(parts)

    lines = ["Camera clocks by folder (read-only). Lanes are UTC offsets; in every lane the first slot is",
             f"local time ({glyph_set['local']}), then one fixed slot per camera. A camera sits in the lane its CLOCK was on.",
             ""]
    for camera in view.cameras:
        lines.append(f"  {view.glyphs[camera]} = {camera:<8} {', '.join(sorted(view.models.get(camera, [])))}")
    lines.append(f"  {glyph_set['change']} = this camera's clock changed inside the folder")
    lines.append("")
    header = lane_sep.join(f"UTC{format_offset(lane)}".center(lane_width) for lane in view.lanes)
    slot_header = lane_sep.join(" ".join([glyph_set["local"]] + [view.glyphs[c] for c in view.cameras]).ljust(lane_width)
                                for _ in view.lanes)
    lines.append(f"{header}{lane_sep}dep roots    folder")
    lines.append(f"{slot_header}{lane_sep}")
    for item in _interleave(view):
        if isinstance(item, Rule):
            label = f" {item.text} "
            lines.append(glyph_set["rule"] * 3 + label + glyph_set["rule"] * max(3, graph_width - len(label)))
            continue
        name = item.name if not width_name else item.name[:width_name]
        summary = "; ".join(_cell_summary(cell) for cell in item.cameras.values())
        tail = f"   [{summary}]" if summary else ""
        lines.append(f"{graph_line(item)}{lane_sep}{item.depth:>3} {item.roots:<7}  {name}{tail}")
        for note in item.notes:
            lines.append(f"{' ' * graph_width}{lane_sep}{'':>3} {'':<7}  ! {note}")
    return lines


HTML_COLOURS = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf", "#8c564b", "#e377c2",
                "#7f7f7f", "#bcbd22"]


def render_html(view: View, title: str, scope: str) -> str:
    colour = {camera: HTML_COLOURS[index % len(HTML_COLOURS)] for index, camera in enumerate(view.cameras)}
    esc = html.escape
    head_lanes = "".join(f'<th class="lane">UTC{esc(format_offset(lane))}</th>' for lane in view.lanes)
    slot_cells = "".join(
        '<th class="lane"><span class="slot local">&#9670;</span>'
        + "".join(f'<span class="slot" style="color:{colour[c]}">{esc(view.glyphs[c])}</span>' for c in view.cameras)
        + "</th>" for _ in view.lanes)
    body = []
    columns = len(view.lanes) + 4
    for item in _interleave(view):
        if isinstance(item, Rule):
            body.append(f'<tr class="rule {item.kind}"><td colspan="{columns}">{esc(item.text)}</td></tr>')
            continue
        cells = []
        for lane in view.lanes:
            spans = ['<span class="slot local">&#9670;</span>' if lane in item.local_lanes
                     else '<span class="slot dim">&middot;</span>']
            for camera in view.cameras:
                cell = item.cameras.get(camera)
                if cell is None:
                    spans.append('<span class="slot dim">&middot;</span>')
                elif lane in cell.lanes:
                    glyph = view.glyphs[camera] if len(cell.lanes) == 1 else "&#8597;"
                    spans.append(f'<span class="slot cam" style="background:{colour[camera]}" '
                                 f'title="{esc(_cell_summary(cell))}">{glyph}</span>')
                else:
                    spans.append('<span class="slot"> </span>')
            cells.append(f'<td class="lane">{"".join(spans)}</td>')
        summary = "; ".join(_cell_summary(cell) for cell in item.cameras.values())
        notes = "".join(f'<div class="note">&#9888; {esc(note)}</div>' for note in item.notes)
        flag = " warn" if item.notes or any(SOURCE_ASSUMED in c.sources for c in item.cameras.values()) else ""
        body.append(f'<tr class="row{flag}">{"".join(cells)}<td class="num">{item.depth}</td>'
                    f'<td class="roots">{esc(item.roots)}</td>'
                    f'<td class="name" title="{esc(item.path)}">{esc(item.name)}{notes}</td>'
                    f'<td class="summary">{esc(summary)}</td></tr>')
    legend = "".join(
        f'<li><span class="slot cam" style="background:{colour[c]}">{esc(view.glyphs[c])}</span> '
        f'<b>{esc(c)}</b> {esc(", ".join(sorted(view.models.get(c, []))))}</li>' for c in view.cameras)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Camera clocks by folder</title>
<style>
:root {{ --bg:#fbfbf9; --fg:#1d1d1b; --muted:#77756f; --line:#e3e1db; --rule-dst:#fff3d6; --rule-trip:#e2f0ff; --local:#111; --warn:#fff6f3; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#18191b; --fg:#e8e6e1; --muted:#9a978f; --line:#2c2d30; --rule-dst:#3a3120; --rule-trip:#1d2d40; --local:#f2f2f2; --warn:#2a1f1c; }} }}
body {{ background:var(--bg); color:var(--fg); font:13px/1.45 system-ui, sans-serif; margin:16px; }}
h1 {{ font-size:18px; margin:0 0 4px; }} p.scope {{ color:var(--muted); margin:0 0 12px; }}
ul.legend {{ list-style:none; padding:0; display:flex; flex-wrap:wrap; gap:6px 18px; margin:0 0 12px; }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; white-space:nowrap; }}
th {{ position:sticky; top:0; background:var(--bg); text-align:left; font-weight:600; border-bottom:1px solid var(--line); }}
td, th {{ padding:2px 6px; vertical-align:top; }}
td.lane, th.lane {{ border-left:1px solid var(--line); font-family:ui-monospace, Consolas, monospace; }}
.slot {{ display:inline-block; width:1.35em; text-align:center; border-radius:3px; }}
.slot.cam {{ color:#fff; font-weight:700; }} .slot.local {{ color:var(--local); }} .slot.dim {{ color:var(--muted); opacity:.45; }}
td.num, td.roots {{ color:var(--muted); font-family:ui-monospace, Consolas, monospace; }}
td.summary {{ color:var(--muted); }}
tr.row:hover td {{ background:rgba(127,127,127,.08); }}
tr.warn td.name {{ background:var(--warn); }}
.note {{ color:#c0392b; white-space:normal; max-width:60em; }}
tr.rule td {{ font-weight:600; padding:3px 8px; }} tr.rule.dst td {{ background:var(--rule-dst); }} tr.rule.trip td {{ background:var(--rule-trip); }}
</style></head><body>
<h1>{esc(title)}</h1>
<p class="scope">{esc(scope)} &middot; read-only &middot; lanes are UTC offsets; first slot in each lane is local time (&#9670;), then one fixed slot per camera, drawn in the lane its clock was on. &#8597; = clock changed inside the folder.</p>
<ul class="legend">{legend}</ul>
<div class="wrap"><table>
<thead><tr>{head_lanes}<th>dep</th><th>roots</th><th>folder</th><th>cameras</th></tr>
<tr>{slot_cells}<th></th><th></th><th></th><th></th></tr></thead>
<tbody>
{chr(10).join(body)}
</tbody></table></div>
</body></html>
"""
