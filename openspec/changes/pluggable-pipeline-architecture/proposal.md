## Why

The current `photosorter` application is a monolithic, tightly coupled sequence of procedural tasks in `src/main.py`, with shared mutable state in `src/common/globals.py` and file-system side effects spread across `src/common/common.py` and related modules. That makes the pipeline hard to extend, hard to visualize, and risky to refactor because related files, generated sidecars, counters, and manual prompts are not modeled as one coherent execution state.

This change upgrades the application into a pluggable DAG-based pipeline with explicit state, an embedded local FastAPI dashboard, robust post-run safety verification, and deterministic filename collision handling. The safety goal is strict: prevent catastrophic file loss or silent corruption during rename, move, conversion, and sorting operations.

## What Changes

- **BREAKING**: Refactor `src/main.py` from hardcoded sequential `_TASK_*()` calls into a CLI/UI entrypoint that starts either a headless pipeline run or a local dashboard-backed run.
- **BREAKING**: Deprecate module-level global state in `src/common/globals.py` and replace it with an encapsulated `PipelineContext` passed between stages.
- Add `src/core.py` containing `MediaAsset`, `PipelineContext`, `PipelineStage`, `StagedWorkspaceStage`, `SafetyValidationStage`, `NameCollisionResolver`, and shared file-operation safety helpers.
- Add `src/stages.py` containing stage wrappers for the existing pipeline behavior: initialization, upload harvesting, batch ExifTool generation, metadata extraction, rename/sort, raw staged conversion, and folder sorting.
- Require each pipeline stage to live in its own module, with reusable shared modules allowed for common logic, so individual stages can be developed and reviewed independently with minimal context/token usage.
- Add `src/server.py` containing a local FastAPI application with REST control routes and WebSocket progress/prompt channels.
- Add a static local dashboard (`index.html`, `style.css`, `app.js`) using vanilla HTML, CSS, and JavaScript to avoid frontend build steps and minimize local runtime fragility. (Decided: the React/Vite skeleton under `src/pipeline/frontend/` is abandoned and should be removed.)
- Add dynamic `config.json` persistence for paths, supported extensions, camera symbols, dashboard port, collision thresholds, and external tool locations.
- Add a robust safety verifier that snapshots input files and validates final output counts, MD5 identities, and zero-byte files.
- Preserve all legacy observable photo-processing behavior as hard parity requirements, including filename grammar, date grouping, EXIF/RAW subfolders, duplicate suffixes, problematic folder taxonomy, stale EXIF handling, and camera-upload ingestion semantics.
- Standardize final event/date-folder subdirectories to the canonical `__RAW`, `__EDITED`, `__EXTRACTED`, `__EXPORTED`, `__RESIZED`, `__DUPLICATES`, and `__EXIF` taxonomy to avoid folder sprawl and ambiguous asset placement.
- Treat files directly in the event/date folder as the shot-level representative images only: either an original straight-from-camera image, or an extracted representative when RAW-only capture produced no camera JPEG.
- Add representative filename suffix semantics so root-level images visibly disclose related assets:
  - `_RAW` means a RAW original exists and should be edited instead of the representative image.
  - `_EXT` means the representative image was extracted or derived from RAW rather than straight from the camera.
  - `_EDT` means a better edited/master version exists; it is always the final suffix.
- Keep the new single-root `____INGEST_PIPELINE` working structure as the internal pipeline layout, with legacy concepts mapped into the new structure rather than reverting the architecture.
- Add an advanced name collision resolver:
  - Identical MD5 files are treated as redundant duplicates.
  - If one file is both older and larger, it is kept as the original and the other is renamed.
  - If one file is significantly smaller than the other (default threshold: under 50%), it is automatically classified as a low-resolution duplicate and renamed.
  - Ambiguous collisions pause execution and prompt the user through the dashboard.
- Replace terminal beeps/blocking prompts for unknown cameras and ambiguous collisions with WebSocket-driven dashboard prompts.
- Accept subfolders (not only loose files) in the intake folders (`INBOX` and legacy `____UNSORTED`), excluding a top-level `__DONT_MOVE` folder which is never touched.
- Carry the containing folder name with each ingested file as an `origin_label` (the folder name with any leading date/date-time part stripped), persisted in a run journal so it survives restarts, and apply it to the final event folder name. Labeled and unlabeled files for the same date go to separate event folders — they are never merged.
- Discover pre-existing metadata files (most importantly `._exif` sidecars) next to ingested images and move them together with the image through every stage; folder-level geodata files (e.g. GPX) travel to the event folder's `__GEOLOCATIONS` subfolder.
- Extend the event-folder taxonomy beyond the initial seven folders with a configurable, centrally defined set (draft, final list pending user review): `__2_SHARE`, `__3D`, `___OTHER`, `__DUPLICATES`, `__EDITED`, `__EXIF`, `__EXPORTED`, `__EXTRACTED`, `__EXTRACTED_VIDEOS`, `__GEOLOCATIONS`, `__HASHES`, `__PANORAMAS`, `__PEOPLE`, `__RAW`, `__RESIZED`, `__SHARED`, `__VIDEOS`. `__PEOPLE`, `__PANORAMAS`, and `__3D` are manually curated; `__HASHES` (per-file MD5/SHA-256 manifests) and `__EXTRACTED_VIDEOS` (motion-photo videos extracted from e.g. Samsung Ultra images, originals left intact) are defined now but not implemented yet.
- Make `config.json` paths relative to a single `base_folder` (default `c:\__PHOTOS`) overridable via CLI parameter; only external ingest sources may stay absolute.
- Define explicit parity exit criteria (E2E fixture matrix green plus a verified real-archive dry run) after which `_photosorter.bat` switches from the legacy CLI to the new DAG pipeline.
- **Redesign the timezone/travel model (Decision 9, revised 2026-06-13)**: replace the hand-computed offset shapes (`camera_clock_corrections` + `trips`) with a two-timeline model — a `locations` timeline (where you were → display zone, label suffix, geolocation) and per-camera `camera_clock_sets` (what the camera was set to → reading→true-instant) — using named IANA zones (stdlib `zoneinfo`) so offsets are derived, not typed, and DST becomes an ordinary camera-clock breakpoint. Add a derived `__GEOLOCATIONS` projection and a stand-alone retro-correction script (`--from`/`--to`/`--folder`) that re-times and re-folds an already-sorted archive idempotently from EXIF.

## User Review Required

This is a major architectural refactor. It changes the execution model, runtime entrypoint, configuration ownership, user interaction model, and file-operation safety boundaries. The following assumptions were reviewed and decided (2026-06-12):

- **Decided**: The dashboard frontend is vanilla HTML, CSS, and JavaScript. The unfinished React/Vite variant is dropped.
- The dashboard will bind to `localhost:8888` by default, with an override in `config.json` and CLI args.
- The pipeline will remain a local, single-user Windows utility; no cloud, database, or multi-user support is included.
- **Decided**: `____INGEST_PIPELINE\INBOX` is the primary intake going forward; legacy `____TO_SORT\____UNSORTED` is preserved as a migration source until the new pipeline works flawlessly.
- **Decided**: `config.json` paths are defined relative to a single `base_folder` (default `c:\__PHOTOS`), which can be overridden by a CLI parameter.

## Capabilities

### New Capabilities

- `pipeline-core`: Pluggable DAG execution engine with `PipelineContext`, `MediaAsset`, transaction-like Windows-safe file operations, staged workspaces for external tools, safety snapshots, post-run validation, and collision resolution.
- `web-ui-dashboard`: Local FastAPI dashboard with WebSocket progress updates, REST controls, stage graph visualization, live logs, unknown camera prompts, collision prompts, and critical safety alerts.
- `legacy-behavior-parity`: Guarantees that the new staged pipeline preserves legacy naming, grouping, sidecar movement, RAW/EXIF subfolders, duplicate handling, problematic folder taxonomy, and camera-upload semantics while using the new working folder layout.
- `event-folder-taxonomy`: Standard final event/date-folder subdirectory taxonomy and representative-image suffix rules for RAW, extracted, edited, exported, resized, duplicate, and metadata artifacts.
- `ingest-provenance`: Recursive intake of subfolders (with top-level `__DONT_MOVE` exclusion), origin-label extraction and persistence, labeled event-folder naming, and discovery/travel of pre-existing metadata files alongside their images.
- `testing-framework`: Contract, unit, and end-to-end pytest coverage for stages, sandboxing, collision resolution, safety validation, and dashboard control surfaces.

### Modified Capabilities

(None. There are no pre-existing specification files in this repository.)

## Impact

- **Affected Files**:
  - `src/main.py`: Refactored into the primary runtime entrypoint with `--cli`, `--ui`, and port/config handling.
  - `src/common/globals.py`: Deprecated in favor of `PipelineContext`.
  - `src/common/common.py`: Existing helpers are retained where practical but adapted behind stage and asset abstractions.
  - `src/constants/constants.py`: Static constants are migrated or mirrored into `config.json`.
- **New Files**:
  - `src/core.py`
  - `src/stages.py`
  - `src/server.py`
  - Dashboard static files such as `index.html`, `style.css`, and `app.js`
  - `config.json`
- **Dependencies Added**:
  - `fastapi`, `uvicorn`, and `websockets`
  - Standard-library `dataclasses`, `pathlib`, `threading`, `queue`, and `hashlib` where possible
- **Runtime Behavior**:
- `_photosorter.bat` continues to launch the existing legacy CLI pipeline by default until the stage-based pipeline has full parity for date-folder sorting and EXIF sidecar handling.
- UI mode is available through `python src/main.py --ui` and starts a localhost FastAPI server.
- CLI/headless legacy mode remains available through `python src/main.py --cli`.
