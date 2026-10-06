## Why

Photos from several cameras only interleave correctly in a folder sorted by name
if every filename stamp is the true local time. Today they are not. Dedicated
cameras miss DST changes and travel, and their clocks drift. Example: the a7R V
was found running on GMT, 80 s slow, all through BST 2026. Its whole September
is filed 1 h 01 m 20 s early.

An engine for this already exists (Decision 9: `timezone_engine.py`, the
`timezone-and-travel` stage, `src/retime_archive.py`). It has never been used:
`timezone.json` is empty. It also has three shortcomings:
- It expresses a clock only as "set to zone X", so it cannot represent drift or
  a measured calibration.
- Its stand-alone retimer predates `ARCHIVE_STANDARD.md`. It moves only the
  image and its `._exif` (breaking X10), ignores F9/F4 collisions, and never
  runs as part of the restructure tool.
- Nothing shows the user what clock each camera was on, so a missing record is
  invisible.

## What Changes

- **BREAKING (config)** Replace the `timezone.json` schema (`zones` /
  `locations` / `camera_clock_sets`) with an evidence-based one:
  - `home` country
  - `mobiles` (camera symbols whose clock is always right)
  - `trips` (country + local `from`/`to`)
  - `camera_clocks` (per-camera boundaries, each with a clock state such as
    `local`, `home`, `home-winter`, `home-summer`, a country/zone, or a fixed
    offset)
  - `calibrations` (point measurements of a reading against true local time)

  The file stays in the repo. It is currently empty, so nothing needs migrating.
- Countries resolve to IANA zones through tzdata's `iso3166.tab` /
  `zone1970.tab`. A country with several zones requires a region.
- Defaults:
  - Outside any trip: no shift.
  - Mobiles: never shifted.
  - A camera with no record inside a trip stayed on home time.
- A calibration's remainder, after the clock state is accounted for, is a
  whole-second **error** for its segment. Before the camera's first boundary,
  the error is constant back to the camera's first shot.
- An in-camera declared offset (`OffsetTimeOriginal`) is **never trusted
  automatically**. It is evidence only.
- Filenames stay in **local time**. A folder whose name order would differ from
  true chronological order is **reported**, never silently reordered.
- Retiming is always derived from the untouched EXIF reading (the `._exif`
  sidecar), so it is idempotent. EXIF in the media is never written.
- Every folder whose photos would be re-dated asks **yes / yes to all
  remaining folders / no**, in both intake and restructure.
- **BREAKING (tooling)** `src/retime_archive.py` is folded into
  `tools/restructure_archive.py` as a new retime step that runs before step 1.
  The retime step:
  - moves whole companion units (X10)
  - resolves collisions through `siblings.py` (F9) and the collision rules (F4)
  - never rewrites a folder's date (N6)
  - lets steps 1, 5 and 6 recompute folder times (N3) and group spans (C11)
- Trip labels are no longer written into filenames.
- New **evidence report**. It is report-only and gives paste-ready
  `timezone.json` lines for:
  - backward/forward reading jumps against the shutter counter
  - changes in a camera's declared offset
  - changes in the phones' offset (likely trip starts)
- New **camera time calculator**: an offline HTML page. It turns a clock photo
  or a phone photo taken at the same moment into a clock state plus error, and
  a stamp into local time, and emits `timezone.json` lines.
- New **timezone visualiser**. It works like a git-log view, one row per
  folder at any nesting depth, across every `photo_roots` entry (duplicate
  folders merged). Each UTC offset is a fixed lane with a fixed slot per camera
  and a distinct local-time marker. DST changes and trip boundaries are drawn
  as rules.

## Capabilities

### New Capabilities
- `camera-clock-model`: the `timezone.json` schema, country → zone resolution,
  clock states, calibrations and errors, the defaults, and how a reading becomes
  a local stamp.
- `archive-retiming`: applying the model at intake and in the restructure tool.
  Covers the per-folder y/a/n confirmation, companion-unit moves, day-boundary
  refiling, idempotency, and the name-order warning.
- `clock-evidence-report`: report-only detection of likely clock adjustments and
  trips, with paste-ready config lines.
- `camera-time-calculator`: the offline calculator page.
- `timezone-visualiser`: the per-folder lane view across all photo roots.

### Modified Capabilities
<!-- None: no archived baseline spec covers timezone behaviour; Decision 9 lives only in the in-progress pluggable-pipeline-architecture change, whose design note is superseded here. -->

## Impact

- **Code**
  - `src/pipeline_stages/timezone_engine.py`: rewritten.
  - `src/pipeline_stages/timezone_and_travel.py`: confirmation prompt; no
    filename labels.
  - `src/core.py`: `TIMEZONE_KEYS`, loader and validation.
  - `src/retime_archive.py`: removed; superseded by the restructure step.
  - `src/list_zones.py`: becomes a country/zone lister.
  - `tools/restructure_archive.py`: new step plus prompt.
  - `_restructure_archive.bat` / `.ps1`: step numbering in the help text.
  - New modules for the evidence report, visualiser and calculator generator.
- **Docs**
  - `ARCHIVE_STANDARD.md` gains a time section (stamps are local time; EXIF is
    never modified; whole-second errors) and its §8 YAML.
  - `design.md` Decision 9 of `pluggable-pipeline-architecture` gets a note
    pointing here.
  - AGENTS.md "where to look" rows.
- **Dependencies**: no new packages. `tzdata` (already in the venv) is
  required on Windows, so the restructure tool's retime step needs the venv's
  tzdata even though `tools/` is otherwise stdlib-only.
- **Data**: on `--apply` and confirmation, filenames and day folders of affected
  shots change. The first live target is
  `2026/09. September` (≈460 a7R V shots).
- **Tests**: `tests/test_timezone_travel.py` is rewritten. New tests use a
  scratch copy of the calibration folder as the acceptance fixture. Images are
  never committed; the fixture is built from sidecar text.
