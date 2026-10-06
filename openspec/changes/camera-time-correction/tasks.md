## 1. Engine and schema

- [x] 1.1 Add shared JSON test vectors (`tests/fixtures/time_vectors.json`). Include the acceptance pair (−80 s → `20.09.51`; −1 s → `20.20.59`), the DST-off summer case, the home-time-inside-trip case, a mobile, a fall-back overlap with and without `counter`, and a multi-zone rejection.
- [x] 1.2 Add a country→zone resolver that reads `iso3166.tab` / `zone1970.tab` from `tzdata`. It accepts IANA region names and lists candidates for multi-zone countries. `src/list_zones.py` becomes a country/region lister.
- [x] 1.3 Extend `stamps.py` with an optional `.fff` fraction, used for calibration stamps only (T8: no second grammar).
- [x] 1.4 Rewrite `timezone_engine.py`:
  - clock states (D3)
  - segments with the `home` default and mobiles (D4)
  - calibration error, whole seconds (D5)
  - trip location lookup and reading → local stamp (truncated)
  - backward-overlap resolution by counter (D7)
- [x] 1.5 Rewrite validation:
  - old-key rejection with a migration message
  - old-frame `from` check
  - mobile entries rejected
  - calibrations disagreeing by more than 2 s
  - |error| ≥ 15 min with a suggested state
- [x] 1.6 Update `src/core.py` loading (`TIMEZONE_KEYS`, defaults) and reset `timezone.json` to the new empty shape.
- [x] 1.7 Rewrite `tests/test_timezone_travel.py` against the vectors and the spec scenarios in `camera-clock-model`.

## 2. Evidence report (read-only)

- [x] 2.1 Add a sidecar reader that returns reading, sub-second, declared offset, counter and camera symbol per shot (reuse `legacy.parse_legacy_exif_text` / `camera_symbol_for_model`).
- [x] 2.2 Implement counter-ordered detection: backward jumps (certain), declared-offset changes (possible), coinciding forward gaps; mobile offset changes as trip boundaries.
- [x] 2.3 Emit paste-ready `camera_clocks` / `trips` lines, mark findings already in config as "recorded", and write the report to the log folder.
- [x] 2.4 Add tests: synthetic sidecars reproducing the `ILC7R5` 16878→16879 change produce the expected line.

## 3. Visualiser (read-only)

- [x] 3.1 Add a scanner over all `photo_roots`: dated folders at any depth, `__EXIF` sidecars only, rows merged by relative path with root tags, and a per-root cache outside the archive.
- [x] 3.2 Build the lane layout: offsets ascending at fixed columns; slot 0 for the local marker, then global camera slots; changing cameras drawn in every lane they used.
- [x] 3.3 Insert DST rules (home and trip zones) and trip start/end rules chronologically. Keep the depth column and aligned name column.
- [x] 3.4 Add row annotations: assumed / configured / calibrated, shift, name-order verdict. Add `--year`, `--from` / `--to` and `--root` filters.
- [x] 3.5 Add tests: same-offset no-overlap, DST-off camera lane, DST rule placement, merged row, alignment.
- [x] 3.6 Run against `c:\__PHOTOS` 2026 and share the output with the user before any retiming.

## 4. Calculator

- [x] 4.1 Write `tools/build_time_calculator.py`, which generates a self-contained offline HTML page with the country/region list embedded from tzdata.
- [x] 4.2 Implement calibration mode (infer state + whole-second error from a clock or phone reference) and translate mode. Emit paste-ready lines.
- [x] 4.3 Run the shared vectors against the page's JS (headless or a node runner in tests) and assert parity with the engine.

## 5. Retime planner

- [x] 5.1 Add a leaf planner module in `src/pipeline_stages/`. Per folder it produces: current → target names, target day folder (N7), X10 unit members, ambiguity and hand-rename flags.
- [x] 5.2 Add the name-order verdict: true-instant order vs target-name order, listing differing shots.
- [x] 5.3 Plan cross-day and cross-month targets: a sibling with the same description, in the correct month folder (P5); the source folder's date is never touched (N6).
- [x] 5.4 Add tests: an acceptance plan built from synthetic sidecars of the calibration folder; idempotent second plan; revert-by-config plan.

## 6. Restructure step 0

- [x] 6.1 Add step 0 "Re-time shots" to `STEPS` in `tools/restructure_archive.py`, with optional `--from` / `--to`; keep existing numbers.
- [x] 6.2 Load tzdata, falling back to the project venv. If neither works, skip step 0 with a banner and let the other steps run.
- [x] 6.3 Add the per-folder prompt `[y] yes  [a] yes to all remaining folders  [n] no`, showing the per-camera state, error, shift, examples, day moves and verdict. "a" persists across `--year ALL`; assume-yes means "a"; a dry run reports only.
- [x] 6.4 Apply plans: companion-unit moves via the companion-matching engine, F9 then F4 on collision, folder creation for new days/months.
- [x] 6.5 Update the `_restructure_archive.bat` / `.ps1` help text and the module docstring.
- [x] 6.6 Add tests on a scratch tree: yes / all / no behaviour, a day-boundary move, a month crossing, and a collision.

## 7. Intake

- [x] 7.1 Rewrite `TimezoneAndTravelStage` to use the new engine, with no filename labels and no `location_suffix`.
- [x] 7.2 Group shifted assets by proposed event folder and raise a `retime` `PromptRequest` per folder (yes / yes to all / no) via `await_prompt`. Render it in the dashboard.
- [x] 7.3 Declined folders: name from raw readings and log them as pending retime.
- [x] 7.4 Add tests: an intake run with the acceptance config under each answer.

## 8. Rollout and docs

- [x] 8.1 Fill `timezone.json` for `ILC7R5` from the calibration pair: `home-winter` from the first shot, `local` from `20.20.58` with counter 16879, both calibrations.
- [ ] 8.2 Dry-run step 0 on `2026/09. September`. Apply to a scratch copy of the calibration folder and verify `20.09.51` / `20.20.59`, companions and folder time. Then apply live with the user.
- [x] 8.3 Delete `src/retime_archive.py` and its tests.
- [x] 8.4 Add a time section to `ARCHIVE_STANDARD.md` (stamps are local time; EXIF never written; whole-second errors; name-order verdict) and its §8 YAML.
- [x] 8.5 Update AGENTS.md "where to look" rows. Add a note in `pluggable-pipeline-architecture/design.md` Decision 9 that it is superseded by this change.

## 9. Video capture times (added 2026-10-06)

- [x] 9.1 Read a video's wall reading as QuickTime UTC + the device's recorded offset (`Android Time Zone`, Sony `Time Zone`, Apple `Creation Date`); name the device from `Device Model Name` / `Author`; never from file times (K11, V4). One reader in `clock_readings`, used by intake (`legacy.parse_legacy_exif_text`), V12 migration and step 0.
- [x] 9.2 `TimeModel.correct_shot`: a no-offset video from a mobile is placed by its UTC instant; from a camera it is taken as the camera's clock.
- [x] 9.3 Tests: Samsung, Sony, Apple, no-offset phone and camera, intake parser, step 0 renaming a video named from its file time (`tests/test_video_times.py`); ARCHIVE_STANDARD K11 + §8.
