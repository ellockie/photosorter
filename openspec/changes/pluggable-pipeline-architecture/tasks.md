## 1. Core Pipeline Engine

- [x] 1.1 Create `src/core.py` with `MediaAsset`, including primary path, sidecar dictionary, and synchronized `rename_all`, `move_all`, and `delete_all` operations.
- [x] 1.2 Add Windows-safe file operation helpers with retry/backoff for rename, move, delete, and MD5 reads.
- [x] 1.3 Implement `PipelineContext` with assets, loaded config, counters, stage states, prompt queues, and input safety snapshot storage.
- [x] 1.4 Implement `PipelineStage` with metadata, dependency declarations, `execute`, and `cleanup` contracts.
- [x] 1.5 Implement DAG orchestration with dependency ordering, active/paused/failed/completed stage states, and headless/UI execution modes.
- [x] 1.6 Implement `StagedWorkspaceStage` for isolated temporary folders, extension filtering, external tool waits, sidecar sweeping, and cleanup.
- [x] 1.7 Implement `SafetyValidationStage` with output count checks, MD5 identity verification, zero-byte detection, registered exceptions, and `CatastrophicSafetyError`.
- [x] 1.8 Implement `NameCollisionResolver` with exact-MD5 suppression, older-and-larger original detection, significantly-smaller duplicate classification, and ambiguous prompt hooks.
- [x] 1.9 Add `config.json` schema/default loading for paths, extensions, external tools, camera symbols, dashboard port, and collision thresholds.

## 2. Pipeline Stages

- [x] 2.1 Create `src/stages.py`.
- [x] 2.2 Implement `InitializationStage` to validate directories, initialize context, and capture the startup safety snapshot.
- [x] 2.3 Implement `UploadHarvestStage` to sweep configured camera upload folders for photos and videos.
- [x] 2.4 Implement `ExiftoolBatchStage` to remove stale `_exif` sidecars and perform high-speed batch metadata generation.
- [x] 2.5 Implement `MetadataExtractionStage` to parse EXIF metadata, bind camera symbols, and populate `MediaAsset` state.
- [x] 2.6 Implement `RenameAndSortStage` to rename assets and route collisions through `NameCollisionResolver`. (Fixed 2026-06-13: collisions now go through the resolver with legacy `_DUPE_<md5>_<n>` / `_LOWRES_<md5>_<n>` naming.)
- [x] 2.7 Implement `RawStagedConversionStage` using `StagedWorkspaceStage` for `.CR2`, `.CRW`, and `.ARW` workflows.
- [x] 2.8 Implement `FolderSortingStage` to move final assets into year/month/ready folder structures.
- [x] 2.9 Wire the default DAG so `SafetyValidationStage` always runs before successful completion.
- [x] 2.10 Split concrete stage implementations into separate modules with `src/stages.py` retained only as a compatibility re-export layer.
- [x] 2.11 Add `StaleExifRelocationStage` as a separate module preserving legacy old-EXIF handling.
- [x] 2.12 Add `EmptyFileQuarantineStage` as a separate module preserving legacy zero-byte handling.
- [x] 2.13 Add `TimezoneAndTravelStage` as a separate module applying clock and trip corrections before naming. (Superseded by the Decision 9 two-timeline redesign — see Section 8; the offset/trip model below is replaced.)
- [x] 2.14 Add legacy naming/foldering helper modules for filename grammar, day-boundary date folders, EXIF/RAW subfolders, duplicate suffixes, and problematic taxonomy.
- [x] 2.15 Add migration input support from legacy `____TO_SORT\____UNSORTED` into the new `____INGEST_PIPELINE\INBOX`.
- [x] 2.16 Add standardized event-folder taxonomy helpers/config for all 17 `__` folders (`src/pipeline_stages/taxonomy.py` + `taxonomy` config section).
- [x] 2.17 Update final sorting/routing stages so RAW, extracted alternates, videos, geodata, and metadata artifacts land in the standardized `__` subfolders. (Edited/exported/resized/duplicate routing helpers exist; no stage produces those artifacts yet.)
- [x] 2.18 Add representative-image selection logic so only one shot-level representative image lives directly in each event/date folder (RAW-pair detection plus extracted-JPEG promotion for RAW-only shots).
- [x] 2.19 Add representative suffix generation for `_RAW`, `_EXT`, and `_EDT`, with deterministic ordering `_RAW`, `_EXT`, `_EDT`.
- [x] 2.20 Extend intake handling (INBOX and legacy `____UNSORTED`) to walk subfolders recursively, excluding a top-level `__DONT_MOVE` folder entirely (`FolderIntakeStage`, recursive `LegacyUnsortedMigrationStage`).
- [x] 2.21 Add origin-label extraction (containing folder name minus leading date/date-time part) and persist origin path, label, and MD5 to a run journal (`.JOURNAL\<run-id>.jsonl`) before files are moved.
- [x] 2.22 Make `FolderSortingStage` name labeled event folders `YYYY-MM-DD_(Ddd) - {label}` and keep labeled/unlabeled same-date groups in separate folders (never merge).
- [x] 2.23 Discover pre-existing metadata files at ingest (`._exif` matched by full filename, stem-matched sidecars like `.xmp`) and register them as `MediaAsset` sidecars so they travel through every stage.
- [x] 2.24 Route folder-level geodata files (e.g. GPX) to the event folder's `__GEOLOCATIONS` subfolder; GPX moved out of the `__EXIF` definition.
- [x] 2.25 Fix sidecar rename parity: keep the full original filename embedded (`photo.jpg._exif`), aligning `RenameAndSortStage` with legacy convention and metadata lookup.
- [x] 2.26 Make all config paths relative to `root_folder` (default `c:\__PHOTOS`), add the `--base-folder` CLI override, and normalize absolute legacy values to relative on save.
- [x] 2.27 Switch the new pipeline's event-folder subfolders from legacy `##   EXIFs   ##`/`##   RAWs   ##` names to the standardized `__EXIF`/`__RAW` (legacy names remain only in the legacy CLI path and problematic folders).

## 3. FastAPI Backend

- [x] 3.1 Create `src/server.py` with a FastAPI app and configurable localhost port, defaulting to 8888.
- [x] 3.2 Run the orchestrator in a background thread so HTTP/WebSocket handling remains responsive.
- [x] 3.3 Add REST routes for start, pause, resume, step, current state, graph structure, config read/write, and prompt answers.
- [x] 3.4 Add WebSocket event broadcasting for stage state, progress counts, logs, prompts, prompt resolutions, and safety alerts.
- [x] 3.5 Persist unknown camera mappings and config edits to `config.json`.
- [x] 3.6 Support collision prompt payloads and resolution actions such as keep existing, keep candidate, rename candidate, or cancel run.

## 4. Dashboard Frontend

- [x] 4.1 Serve a static vanilla HTML/CSS/JS dashboard from `src/pipeline/static/` via FastAPI. (Decided 2026-06-12: vanilla JS, not React/Vite.)
- [x] 4.2 Build the dark-mode vanilla dashboard layout (`index.html`, `app.css`, `app.js`).
- [x] 4.3 Render the pipeline DAG with pending, active, paused, completed, and failed states.
- [x] 4.4 Add a progress panel for processed count, remaining count, speed, elapsed time, active stage, and live logs.
- [x] 4.5 Add unknown camera prompts that submit shorthand mappings and update config immediately. (Vanilla prompt panel with a camera-symbol form; persistence via `/api/prompts/{id}/answer`. End-to-end check remains in manual task 7.2.)
- [x] 4.6 Add collision resolution prompts showing paths, timestamps, sizes, MD5 status, and available actions. (Vanilla prompt cards with keep-existing/keep-new/rename/cancel actions. End-to-end check remains in manual task 7.3.)
- [x] 4.7 Add a critical alert area for `SafetyValidationStage` failures and catastrophic halt states.
- [x] 4.8 Delete the abandoned React/Vite skeleton under `src/pipeline/frontend/`.

## 5. Entrypoint and Compatibility

- [x] 5.1 Refactor `src/main.py` into the primary entrypoint with `--ui`, `--cli`, `--port`, and config path arguments.
- [x] 5.2 Preserve `_photosorter.bat` as the launch path and keep it on the legacy CLI pipeline by default until the new stage pipeline has full parity.
- [x] 5.3 Keep existing EXIF and sorting helper behavior available behind stage adapters during the transition.
- [x] 5.4 Deprecate direct writes to `src/common/globals.py` and route counters/state through `PipelineContext`.
- [ ] 5.5 Define parity exit criteria (6.13 E2E matrix green plus a verified real-archive dry run, task 7.x) and switch `_photosorter.bat` from `--cli` to the new DAG pipeline once met.

## 6. Testing and Verification

- [x] 6.1 Add contract tests ensuring every `PipelineStage` accepts and returns valid `PipelineContext` and declares required metadata.
- [x] 6.2 Add unit tests for `MediaAsset` sidecar operations and Windows retry wrapper behavior.
- [x] 6.3 Add sandbox tests proving temporary workspace isolation, sidecar sweeping, and cleanup.
- [x] 6.4 Add collision tests covering identical MD5 suppression, older/larger original selection, significantly-smaller duplicates, and ambiguous prompt pauses.
- [x] 6.5 Add safety tests proving missing files, MD5 mismatches, and zero-byte outputs raise `CatastrophicSafetyError`.
- [x] 6.6 Add backend tests for REST controls and WebSocket event payload schemas. (Root cause of the skip: pytest was not installed in the Poetry venv, so `poetry run pytest` fell through to a system-wide pytest without fastapi. Fixed by installing pytest/httpx into the venv and pointing `run_tests.bat` at `poetry run python -m pytest`; seven real TestClient tests now cover REST + WebSocket.)
- [x] 6.7 Add end-to-end tests on isolated dummy photo folders verifying rename, sort, duplicate resolution, and zero-file-loss validation (`tests/test_e2e_pipeline.py` runs the full default DAG with a mocked ExifTool).
- [x] 6.8 Run `poetry run pytest`. (Now `poetry run python -m pytest`; 45 tests pass.)
- [x] 6.9 Add legacy parity E2E fixtures for naming grammar, date folders, day-boundary shifts, EXIF/RAW subfolders, and `_DUPE_<md5>_<n>` duplicates. (Problematic taxonomy fixtures remain at unit level in `test_pipeline_core.py`.)
- [x] 6.10 Add tests for standardized event-folder taxonomy: `__RAW`, `__EXIF`, `__VIDEOS`, `__EXTRACTED`, and `__GEOLOCATIONS`. (`__EDITED`/`__EXPORTED`/`__RESIZED`/`__DUPLICATES` have no producing stages yet.)
- [x] 6.11 Add tests proving root event/date folders contain only one representative image per shot.
- [x] 6.12 Add tests for representative suffix ordering and semantics: `_RAW`, `_EXT`, `_EDT`.
- [x] 6.13 Implement the E2E mock fixture matrix from design.md (trip offset, clock correction, exact-duplicate merge, `_DUPE` collision, lowres classification) as an automated test.
- [x] 6.14 Add ingest-provenance tests: subfolder intake, `__DONT_MOVE` exclusion, origin-label extraction with date-prefix stripping, journal persistence, labeled event folders, no-merge of same-date groups, and pre-existing `._exif` travel.
- [x] 6.15 Add tests for base-folder override and relative config path resolution (no photo outputs inside the repo).

## 7. Manual Verification

- [ ] 7.1 Run `_photosorter.bat` and confirm legacy transfer, EXIF sidecar movement, and final year/month/date folder sorting behavior are preserved.
- [ ] 7.2 Simulate an unknown camera model, map it through the dashboard, and verify `config.json` persistence.
- [ ] 7.3 Place conflicting files in the unsorted directory and verify automatic and interactive collision paths.
- [ ] 7.4 Complete a sample run and confirm the final safety verifier reports success.
- [ ] 7.5 Manually inspect a real event/date folder and confirm standardized subfolders and representative suffixes are understandable without opening subfolders.
- [ ] 7.6 Place a labeled subfolder (with images and `._exif` sidecars), loose files for the same date, and a `__DONT_MOVE` folder in the intake; verify labeled/unlabeled folders stay separate, sidecars travel, and `__DONT_MOVE` is untouched.

## 8. Timezone & Travel Two-Timeline Redesign (Decision 9)

Supersedes the offset/trip model behind task 2.13. Goal: derive offsets from named zones via two independent timelines, with the standalone retro tool sharing the same engine.

- [x] 8.1 Add `zones` alias map + `zoneinfo`-backed zone resolver to config loading; provide an on-demand `list_zones.py` (regenerates the full 598-name reference from `zoneinfo.available_timezones()` for copy-paste).
- [x] 8.2 Replace the `camera_clock_corrections` + `trips` config shapes with `locations` (with optional `label`, `coords`, `until` sugar) and per-camera `camera_clock_sets` (`at_reading`, `set_to`).
- [x] 8.3 Implement the LOCATION timeline lookup: given a true instant, return display zone, optional label suffix, and coords; `until` auto-inserts the resume-previous-era breakpoint.
- [x] 8.4 Implement the per-camera CAMERA-CLOCK timeline lookup: locate the `at_reading` interval for a reading, interpret the reading in that interval's `set_to` zone to produce the true instant.
- [x] 8.5 Enforce the `at_reading` "first corrected reading" convention in the loader: compute the expected jump from adjacent `set_to` offsets and warn when an entry looks recorded in the old (pre-adjustment) clock frame.
- [x] 8.6 Default ambiguous westward/fall-back (overlapping-reading) cases to the post-adjustment interval and collect the straggler set for optional hand-nudging.
- [x] 8.7 Rewrite `TimezoneAndTravelStage` to drive the new engine: reading → true instant → display time, feeding corrected local time (with day-boundary applied to corrected time) into naming/foldering.
- [x] 8.8 Add the `__GEOLOCATIONS` projection: write a derived `_location.json` per event folder from the active `locations` entry, and route real GPX tracks by timestamp into the matching folder.
- [x] 8.9 Build the stand-alone retro-correction script (`--from` / `--to` / `--folder`): EXIF-sourced (idempotent), carries descriptions verbatim, re-folds across the `04:44:44` day boundary, prompts on multi-placeholder ambiguity, and reuses `core.py` safe asset/sidecar operations.
- [x] 8.10 Tests: location/camera timeline lookups; derived-offset correctness (east clean-seam, DST fix); enforced `at_reading` frame-check warning; westward ambiguity default; geolocation projection; and an idempotency test proving the standalone script is safe to re-run (second run is a no-op).

## 9. Single-Call UI Launcher

Goal: launch the dashboard-backed pipeline with one call, run it in a single click, and stop the server (and the launcher process) from the UI — while keeping the server re-runnable if not stopped.

- [x] 9.1 Add browser auto-open (config `dashboard.open_browser`, `webbrowser.open(new=0)` to reuse the window) and "already running" detection so re-invoking the launcher reuses the live server instead of failing to bind a second one.
- [x] 9.2 Add a graceful-shutdown path: `/api/server/shutdown` signals uvicorn `should_exit` (wired via `app.state.request_shutdown` in `run_server`), so the launcher process returns/ends on demand.
- [x] 9.3 Add one-click `run_fresh()` + `/api/pipeline/run` (reset-then-start in a single action), replacing the prior two-click Restart→Start re-run.
- [x] 9.4 Add dashboard **Run** (primary) and **Stop server** (danger) buttons; stop the WebSocket reconnect loop cleanly after shutdown.
- [x] 9.5 Add `_photosorter_ui.bat` single-call entry (Poetry dep self-heal, then `main.py --ui`).
- [x] 9.6 Tests for `/api/pipeline/run` and `/api/server/shutdown` (route contract + shutdown handler invocation); live smoke test of launch → one-click run → shutdown and the re-invocation reuse path.
