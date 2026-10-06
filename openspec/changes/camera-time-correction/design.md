## Context

`pluggable-pipeline-architecture` Decision 9 built a two-timeline engine. A
location timeline gives the display zone; a per-camera `camera_clock_sets`
timeline turns a reading into a true instant. Offsets are derived from IANA
zones, and an adjustment is recorded at the first corrected reading
(`at_reading`).

The engine is wired into intake (`timezone-and-travel` stage, before
`rename-and-sort`) and into a stand-alone `src/retime_archive.py`. The
committed `timezone.json` is empty, so none of it has ever changed a file.

An explore session (2026-09-27 to 10-06) settled what it has to become.

**Facts that shaped it:**
- Cameras have no GPS. Phones always carry correct local time.
- The a7R V writes `OffsetTimeOriginal`. 462 of its September 2026 shots
  declare `+00:00` during BST.
- A calibration pair exists in
  `c:\__PHOTOS\2026\09. September\2026-09-27_(Sun)__19.08.31 - Sony 7riV mobile calibration photos, before and after`:

  | Shot | Shutter | Reading | Declared offset | Monitor clock |
  |---|---|---|---|---|
  | 1 | 16878 | 19:08:31.774 | +00:00 | 20:09:52.208 |
  | 2 | 16879 | 20:20:58.925 | +01:00 | 20:20:59.934 |

  Before the phone sync, between them, the camera was on GMT and 80.4 s slow.
  After it, it was 1.0 s slow.
- Sidecars (`__EXIF\*._exif`, ExifTool text) carry `Date/Time Original`,
  `Sub Sec Time Original`, `Offset Time Original` and `Shutter Count`.
- `config.json` `photo_roots` holds `c:\__PHOTOS` and
  `\\synology-dell\MOJ_BACKUP_NON-ENCRYPT\__PHOTOS\`.
- The venv's `tzdata` ships `iso3166.tab` and `zone1970.tab`.
- `tools/` is stdlib-only. On Windows, `zoneinfo` has no data without `tzdata`.

**User decisions:**
- Filenames show local time, plus a warning where name order ≠ true order
  (option c).
- A camera with no record inside a trip stayed on home time.
- Duplicate folders across roots merge into one visualiser row.
- Every re-dated folder asks yes / yes to all / no.
- Counter jumps are reported, never applied. Clock photos go through the
  calculator.
- `timezone.json` stays in the repo.
- Trip labels are dropped from filenames.
- Declared offsets are never trusted automatically.
- Drift before the first boundary is constant back to the camera's first shot.

## Goals / Non-Goals

**Goals:**
- One engine (T8) that turns a raw reading into a local stamp, used by intake,
  the restructure tool, the evidence report, the visualiser and (by
  re-implementation in JS, with test vectors) the calculator.
- A config a person can fill by pasting filename stamps.
- Retiming that is idempotent, reversible (delete the entry, re-run), confirmed
  per folder, and standard-compliant (X10, F9/F4, N6, P5).
- Visibility: what clock every camera was on, folder by folder, across all
  roots.

**Non-Goals:**
- Writing EXIF in any media file.
- Inferring trips or adjustments automatically. Evidence is only reported.
- Linear drift modelling.
- Geotagging and `__GEOLOCATIONS`. These are unchanged; `coords` leaves the
  trip schema.
- Sub-second filename stamps (F9 is untouched).

## Decisions

### D1. The true instant stays the spine; the inputs change

The flow is: reading + camera → clock segment → true UTC instant → location
zone → local wall time → stamp, then the day boundary and the folder.

The spine is kept from Decision 9 because it is right. The inputs are replaced
because "set_to zone, frozen at the moment of setting" could not express drift,
DST-off cameras, or a measured calibration.

*Alternative:* keep `camera_clock_sets` and bolt on an `error` field. Rejected:
the frozen-offset semantics surprised the user ("a camera set in summer then
shifts in winter even though I never told it anything") and the
vocabulary did not match how the user describes a camera.

### D2. Config schema (`timezone.json`, repo root)

```jsonc
{
  "home": "GB",
  "mobiles": ["IP13", "PX7"],
  "trips": [
    { "country": "JP", "from": "2026-04-11_(Sat)__07.12.40", "to": "2026-04-20_(Mon)__21.03.11" }
  ],
  "camera_clocks": [
    { "camera": "ILC7R5", "clock": "home-winter" },
    { "camera": "ILC7R5", "from": "2026-09-27_(Sun)__20.20.58", "counter": 16879, "clock": "local" }
  ],
  "calibrations": [
    { "camera": "ILC7R5", "reading": "2026-09-27_(Sun)__19.08.31.774", "true": "2026-09-27_(Sun)__20.09.52.208" },
    { "camera": "ILC7R5", "reading": "2026-09-27_(Sun)__20.20.58.925", "true": "2026-09-27_(Sun)__20.20.59.934" }
  ]
}
```

- **Stamps** are parsed by `stamps.py` (T8). Every historical form is accepted,
  plus an optional `.fff` fraction in calibration stamps only.
- **Countries** are ISO-3166 alpha-2. A multi-zone country (`US`, `CA`, `RU`,
  `AU`, `BR`, `MX`, `ID`, `ES`, `PT`, …) must be given as a region: an IANA
  name such as `America/New_York`. A bare country is a validation error that
  lists the choices. `home` follows the same rule.
- **`trips[].from` / `to`** are local wall times in the trip's zone. That makes
  "paste the name of the first/last phone photo there" correct.
- **`camera_clocks[].from`** is the first reading after the adjustment (the
  Decision 9 frame rule, kept). An entry with no `from` covers the camera from
  its first shot.
- **`counter`** is optional. It pins which side of a backward adjustment a
  repeated reading falls on.
- The old keys (`zones`, `locations`, `camera_clock_sets`) are rejected with a
  migration message. The file is empty today, so nothing needs converting.

### D3. Clock states

| `clock` | Resolves to | Follows DST of |
|---|---|---|
| `home` | home zone | home |
| `local` | the zone the user was in at `from` (trip zone, else home), fixed at that moment | that zone |
| `home-winter` / `home-summer` | home's standard / daylight UTC offset | — (fixed) |
| `JP`, `America/New_York` | that zone | that zone |
| `+05:30` | that fixed offset | — |

A named zone tracks its own DST: the camera is assumed to have been kept up
with it. A missed DST change is said explicitly, with `home-winter`,
`home-summer` or a fixed offset. That is exactly the a7R V case, and it is how
the user describes cameras ("on UK time, summer time off").

`local` resolves once, at `from`. A camera set to Tokyo time stays on Tokyo
time after the user flies home, until the next entry. That is physically true
of real cameras.

### D4. Defaults and segments

A camera's entries, sorted by `from`, cut its reading axis into segments. Each
segment's state comes from its entry. The implicit segment before the first
entry has state `home` and no error.

This one default gives the user's rules:
- Outside trips, home = local, so there is no shift.
- Inside a trip, a camera with no entry stays on home time and is shifted.

Mobiles are always `local`-tracking with zero error. An entry or calibration
naming a mobile is a validation error.

### D5. Calibrations become a whole-second error per segment

1. Interpret `true` in the location zone at that moment (trip or home). This
   gives a UTC instant.
2. Interpret `reading` in the segment's state. This gives a UTC instant.
3. error = (2) − (1), rounded to whole seconds.

The segment's error is that of the calibration nearest in reading. If two
calibrations in one segment disagree by more than 2 s, validation warns and
both are shown. The implicit first segment's error, and the error of a segment
whose only calibration lies later in it, apply constantly back to the
segment's start. For segment 0, that is the camera's first shot (user decision).

**Why whole seconds:** F9 pairs a filename's second with the file's own
`SubSecTimeOriginal`, which is never rewritten. A fractional shift would
decouple them, and calibration precision is about ±1 s anyway.

**Guard:** |error| ≥ 15 min almost always means the state is wrong. Validation
then warns and suggests the state that leaves the smallest remainder.

**Worked example (acceptance):**
- Segment 0 (`home-winter`, +00:00): reading 19:08:31.774 → 19:08:31.774Z;
  true 20:09:52.208 BST → 19:09:52.208Z. Error −80.434 s → −80 s.
  Stamp: 19:08:31 + 80 s + 1 h = **20:09:51**.
- Segment 1 (`local` at 20:20:58 → Europe/London, BST): error −1.009 s → −1 s.
  Stamp: **20:20:59**.

### D6. Where the reading and camera come from

- The reading is `Date/Time Original` from the `._exif` sidecar (intake: from
  ExifTool output). Sub-seconds are used only to report calibrations.
- The camera is `camera_symbol_for_model(Model)`, never the filename.
- The counter is `Shutter Count`, else `Image Number` / `File Number`, when
  present.
- A shot without a reading is never retimed (V4).

### D7. Backward-adjustment overlap

When a boundary's offset jump is negative, readings in
`[from, from + |jump|)` are ambiguous:
1. If the entry has `counter` and the shot has one, the counter decides.
2. Otherwise, the shot is assigned to the post-adjustment segment and listed as
   ambiguous in the report and the prompt.

This replaces Decision 9's silent default.

### D8. Retiming: one planner, two callers

A planner function (in `src/pipeline_stages/`, leaf module) takes folders plus
config and returns, per affected folder, a plan. For each shot:
- current name → target name
- target day folder (N7 boundary applied to the local stamp)
- unit members (X10: RAW, sidecars at every level, previews, OCR, motion clip,
  edits keyed by name)
- ambiguity and hand-rename flags
- the folder's name-order verdict

**Intake** (`timezone-and-travel` stage):
- Groups plans by proposed event folder. Each one with a non-zero shift raises a
  `PromptRequest` of type `retime` through `PipelineContext.await_prompt`, with
  the choices yes / yes to all / no.
- "No" names those shots on their raw reading and logs them for a later
  restructure.

**Restructure:**
- A new **step 0, "Re-time shots"**, runs before step 1. Existing step numbers
  and `--steps` stay valid.
- Dry run reports every plan and does not prompt.
- `--apply` asks per folder `[y] yes  [a] yes to all remaining folders  [n] no`.
  "a" holds for the rest of the invocation (all years under `--year ALL`).
  "n" leaves the folder untouched; the next run asks again.
- The existing assume-yes switch answers "a".
- Shots that change day move to the sibling dated folder `<new date> -
  <same description>`, created if missing. If that date falls in another month
  folder, the new folder is created in the correct month (P5).
- The source folder's date is never rewritten (N6). Steps 1 and 5 recompute
  its time (N3) and step 6 recomputes group spans (C11).
- Collisions go through `siblings.py` (F9), then the F4 collision rules.
- Every move is a companion-unit move via the companion-matching engine, not a
  file move.

`src/retime_archive.py` is deleted. Its `--from/--to/--folder` use case becomes
`restructure --steps 0 [--from --to]`.

### D9. Idempotency and hand renames

The target stamp is always computed from the reading. A shot already at its
target is untouched, so a second run is a no-op. Deleting an entry and
re-running moves shots back toward their raw-reading names, which makes
reversal a config edit.

A current name that matches neither the raw reading nor the target is flagged
"renamed by hand?" in the prompt. It still follows the user's answer.

### D10. Name-order verdict (option c)

After planning a folder, sort its shots by true instant and by target name. If
the orders differ, report the out-of-order shots, typically in-flight shots at a
westward seam or a DST fall-back hour. The report appears in the prompt, the
dry-run report and the visualiser. Nothing is reordered.

### D11. tzdata from a stdlib-only tool

Step 0 first tries `zoneinfo`. If the zone data is missing, it adds the
project venv's `site-packages` to the `tzdata` search (`PYTHONTZPATH` /
`importlib`). If that also fails, step 0 alone is skipped with a red banner;
the other steps still run.

The country tables are read from the same `tzdata` package, so country
resolution has a single source (T8).

### D12. Evidence report (report-only)

Per camera, ordered by counter (or by reading when there is none), it finds:
- **Backward reading jumps.** Certain adjustment.
- **Changes in declared `Offset Time Original`.** Possible adjustment; never
  trusted.
- **Forward jumps that coincide with either of the above.**
- For mobiles: **changes in declared offset.** Likely trip boundary.

Every finding prints a paste-ready `camera_clocks` or `trips` line built from
the actual stamps, with `counter` where known. Findings already covered by
`timezone.json` are marked "recorded". Output goes to the terminal and to a
text file under the run's log folder.

### D13. Visualiser

A CLI tool (`tools/`, stdlib + engine). It scans every `photo_roots` entry,
reading folder names and `__EXIF` sidecars only.

- **Rows** are dated folders at any depth, in path order. Folders with the
  same path relative to their roots merge into one row tagged with the roots
  (`C+N`).
- **Lanes** are UTC offsets in the scanned range, ascending, at fixed columns.
- **Slots:** each lane has fixed slots. Slot 0 is the local-time marker `◆`;
  then one slot per camera, in a global order fixed by first appearance. Two
  cameras on one offset therefore never overlap.
- A camera whose offset changes inside a folder is drawn in both lanes and
  marked.
- **Rules:** full-width rules are inserted chronologically for every DST change
  of home and trip zones and for every trip start and end.
- **Name column:** a depth column, then the folder name, all starting at the
  same column.
- **Annotations:** per row, assumed / declared / calibrated state, the shift,
  and the name-order warning.
- **Filters:** `--year`, `--from` / `--to`, `--root`.
- **Cache:** per root, keyed by folder path + sidecar mtimes, kept outside the
  archive. This keeps NAS rescans cheap.

### D14. Calculator

An offline single HTML file, generated by `tools/build_time_calculator.py` from
the tzdata tables. Its time-zone and DST rules come from the browser's `Intl`
API.

**Inputs:**
- camera symbol
- reading (stamp, optional `.fff`)
- reference: a clock in the photo, a phone photo stamp, or none
- location (country / region)
- camera state, or "infer"

**Outputs:**
- the local stamp
- the inferred state and whole-second error
- paste-ready `calibrations` and `camera_clocks` lines

Shared JSON test vectors (including the acceptance pair) are run against both
the Python engine and the page's JS, so the two cannot drift (T8 by test).

## Risks / Trade-offs

- [A `from` recorded in the old clock frame silently misfiles shots] → The
  Decision 9 true-time monotonicity check is kept. The evidence report shows
  the counter-pinned stamp to paste.
- [Constant drift back to the first shot is wrong by up to the full error on
  old shots] → Accepted by the user. It only matters for second-level
  interleaving with phones. An earlier calibration can be added at any time
  and will win for its own stretch.
- [The default "inside a trip, camera on home time" is wrong for a camera that
  was adjusted but never recorded] → The visualiser labels these "assumed".
  The prompt shows the shift before anything moves.
- [Retiming mass-renames hundreds of files] → Dry run first. A y/a/n prompt per
  folder. The pipeline safety snapshot and MD5 checks still apply. Reversal is
  a config edit plus re-run.
- [Prompts block an unattended intake] → The intake prompt goes through the
  dashboard like every other prompt. Answering "a" once covers the run.
- [A NAS scan is slow] → Sidecar-only reads plus a per-root cache.
- [The Python/JS engines diverge] → Shared test vectors.
- [Fall-back hour / westward seams misorder names] → By design (option c). The
  verdict is reported everywhere.

## Migration Plan

1. Land the engine, schema, validation and tests (acceptance vectors).
2. Land the evidence report and visualiser. These are read-only and safe on the
   live archive.
3. Land the calculator.
4. Land the planner, then restructure step 0 (dry run only), then intake
   prompts.
5. Fill `timezone.json` for the a7R V from the calibration pair. Dry-run step 0
   on `2026/09. September`. Apply on a scratch copy of the calibration folder,
   then live.
6. Delete `src/retime_archive.py`. Update ARCHIVE_STANDARD.md (time section +
   §8 YAML), AGENTS.md, and the Decision 9 note.

**Rollback:** remove or adjust the `timezone.json` entries and re-run step 0.
Names are recomputed from untouched EXIF.

## Open Questions

- Should the visualiser also emit an HTML version, beyond the terminal or text
  output? This is deferrable; the text form comes first.
- Intake "no": should those shots also get a log entry under `__LOGS` listing
  them for a later restructure? The default is yes, as part of the run log.
