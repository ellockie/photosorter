## Context

`photosorter` currently runs through a fixed sequence of procedural task functions, mutates module-level globals, and uses physical folders as implicit state between operations. This makes it difficult to add stages, pause safely, handle unknown cameras consistently, inspect progress, or prove that all original media survived the run.

The new design introduces an explicit pipeline runtime: assets are modeled as `MediaAsset` objects, execution state lives in `PipelineContext`, work happens through `PipelineStage` nodes in a DAG, and user interaction moves from blocking terminal prompts to a localhost FastAPI dashboard.

## Goals / Non-Goals

**Goals:**
- Replace monolithic orchestration with a pluggable DAG-based execution engine.
- Encapsulate all pipeline state in `PipelineContext`.
- Model primary files and sidecars as a single `MediaAsset` unit.
- Provide transaction-like Windows-safe file operations with retry wrappers.
- Sandbox external tool stages in isolated temporary workspaces.
- Guarantee zero file loss or corruption with input snapshots and final MD5/count validation.
- Resolve filename collisions automatically when safe and prompt the user when ambiguous.
- Provide a local dashboard for progress, logs, stage graph status, and interactive decisions.
- Keep the frontend dependency-light by using vanilla HTML, CSS, and JavaScript by default.

**Non-Goals:**
- No cloud service, multi-user dashboard, remote access, or database-backed history.
- No complete rewrite of low-level EXIF parsing unless needed to fit the stage contracts.
- No replacement of existing external tools such as ExifTool, Canon DPP/DPViewer, Sony IED, or IrfanView.
- No cross-platform support beyond the current Windows-first project constraints.

## Architecture

### Core Engine (`src/core.py`)

`MediaAsset` is a dataclass representing a primary media file plus related sidecars such as `_exif` files, extracted JPEGs, converted RAW outputs, and temporary artifacts. It exposes operations such as `rename_all`, `move_all`, and `delete_all`, each implemented with Windows retry handling and state rollback where practical.

`PipelineContext` owns:
- Active `MediaAsset` objects.
- Loaded `config.json` values.
- Pipeline counters and timing metrics.
- Input safety snapshot records: original path, size, timestamp, and MD5.
- Prompt queues and stage status for UI/CLI coordination.
- Registered safety exceptions for intentional non-media byproducts or exact duplicate suppression.

`PipelineStage` is the abstract base interface for every node. Each stage declares metadata such as `stage_id`, `display_name`, dependencies, input contracts, output contracts, and whether it can run headless. `execute(context)` returns the updated context; `cleanup(context)` handles partial failure recovery where needed.

`StagedWorkspaceStage` extends `PipelineStage` for external tools that need clean folders. It selects target extensions, creates an isolated temporary folder, moves or copies only eligible files, invokes or waits for the external tool, sweeps produced files back into `MediaAsset.sidecars`, and cleans the sandbox.

`SafetyValidationStage` runs at the end of successful pipeline execution. It scans output folders and validates that every input media file is accounted for by MD5, has a non-zero size, and is either present as an output or explicitly registered as a safe duplicate/exclusion. Any mismatch raises `CatastrophicSafetyError` and broadcasts a critical alert.

`NameCollisionResolver` evaluates collisions before overwrites:
- Exact MD5 match: suppress redundant duplicate and register the safety exception.
- Older and larger: keep the older/larger file as original, rename the other.
- Significantly smaller: classify as low-resolution duplicate using a configurable threshold, defaulting to under 50% of the larger file.
- Ambiguous: pause the pipeline and issue a prompt payload for user resolution.

### Pipeline Stages (`src/pipeline_stages/`)

The initial stage set wraps current behavior without trying to redesign every helper at once:

- `InitializationStage`: validates directories, loads config, initializes counters, and records the input snapshot.
- `UploadHarvestStage`: sweeps photos and videos from configured camera upload folders into the new `INBOX` while preserving legacy upload semantics.
- `StaleExifRelocationStage`: moves pre-existing `._exif` sidecars out of `INBOX` into the problematic old-EXIF location before fresh ExifTool generation.
- `EmptyFileQuarantineStage`: moves zero-byte media files into the legacy empty-files problematic subfolder.
- `ExiftoolBatchStage`: performs bulk ExifTool metadata generation and removes stale `_exif` files before regeneration.
- `MetadataExtractionStage`: parses metadata, binds camera symbols, and constructs or enriches `MediaAsset` instances.
- `RenameAndSortStage`: applies naming rules, calls `NameCollisionResolver`, and performs safe asset renames/moves.
- `TimezoneAndTravelStage`: applies camera clock corrections and travel timezone shifts before final renaming (see Travel & Timezone Engine below).
- `RawStagedConversionStage`: inherits `StagedWorkspaceStage` to isolate `.CR2`, `.CRW`, and `.ARW` files for external development workflows.
- `FolderSortingStage`: moves final assets into year/month/ready folder structures.
- `SafetyValidationStage`: validates counts, MD5 identities, and zero-byte failures before declaring success.

Each stage must live in a separate module under `src/pipeline_stages/`, for example `initialization.py`, `upload_harvest.py`, `exiftool_batch.py`, and so on. Shared logic may live in common support modules, but stage-specific behavior should stay isolated so future changes can be made with a small focused context window. `src/stages.py` may remain only as a compatibility/re-export layer during the transition.

### FastAPI Backend (`src/server.py`)

The local backend runs on `localhost:8888` by default and uses a configurable port. It owns a background pipeline runner thread and exposes:

- `POST /api/pipeline/start`
- `POST /api/pipeline/pause`
- `POST /api/pipeline/resume`
- `POST /api/pipeline/step`
- `POST /api/prompts/{prompt_id}/answer`
- `GET /api/pipeline/state`
- `GET /api/pipeline/graph`
- `GET /api/config`
- `PUT /api/config`
- `WS /ws/events`

The WebSocket channel broadcasts stage starts, stage completions, per-asset progress, log lines, prompt requests, prompt resolutions, and critical safety alerts. Prompt responses flow back through REST or WebSocket messages and unblock the orchestrator.

### Dashboard Frontend (`src/pipeline/frontend/`)

A Vite + React application using React Flow for an interactive draggable/zoomable stage graph and Tailwind CSS for glassmorphic dark styling.

**Development structure:**

```
src/pipeline/frontend/        ← Vite React project (dev-time only)
├── src/
│   ├── App.tsx               ← main layout, WebSocket connection, state
│   ├── components/
│   │   ├── StageGraph.tsx    ← React Flow DAG visualisation
│   │   ├── ProgressPanel.tsx ← counters, speed, elapsed, live logs
│   │   ├── PromptModal.tsx   ← interactive decisions (camera, collision)
│   │   └── AlertHUD.tsx      ← critical safety alerts
│   └── ...
├── tailwind.config.js
├── vite.config.ts
└── package.json
```

**Compiled & static serving:**

```
src/pipeline/static/          ← Vite build output (committed, no Node.js at runtime)
├── index.html
├── assets/
│   ├── app-[hash].js
│   └── app-[hash].css
```

FastAPI statically mounts `src/pipeline/static/` and serves the pre-compiled bundle. During everyday execution (`_photosorter.bat`), there are zero Node.js dependencies — everything runs directly from Python.

**Auto-open behaviour:** The server automatically opens the dashboard in the default browser on launch (configurable via `dashboard.open_browser` in config).

## Decisions

### 1. Use Vite React Frontend with Static Serving

The dashboard uses Vite, React, React Flow (interactive stage graph), and Tailwind CSS (glassmorphic dark theme). The compiled bundle is committed to `src/pipeline/static/` and served by FastAPI as static files. Node.js is a dev-time dependency only — runtime execution requires only Python.

### 2. Keep Existing Helpers Behind Stage Boundaries

Existing EXIF, rename, MD5, and folder helpers should be reused where reliable, then gradually extracted into cleaner units. The stage boundary is the first refactor target; replacing every helper at once would increase risk.

### 3. Keep Stage Modules Independently Workable

Each concrete stage should be implemented in its own module, importing only the core contracts and the small helper modules it needs. This keeps review and implementation sessions narrow, reduces token usage when modifying one stage, and prevents stage-specific changes from forcing agents to load a monolithic stage file.

### 4. Use Local JSON Configuration

`config.json` becomes the runtime configuration source for paths, extensions, camera mappings, external tools, dashboard port, and collision thresholds. Existing constants can provide defaults/migration support but should stop being the authoritative mutable configuration.

### 5. Single-Root Path Model With Legacy-Parity Mapping

All pipeline activity is contained within one absolute `root_folder` — the photo archive root (e.g. `c:\__PHOTOS`). A dedicated working subfolder holds all in-progress pipeline state. Legacy `____TO_SORT\____UNSORTED` and `____TO_SORT\__READY` are not the primary implementation model anymore, but their observable behavior is preserved through explicit mappings.

**Folder layout:**

```
root_folder/                                ← single absolute path (the photo archive)
├── 2024/                                   ← sorted output
│   ├── 01 - January/
│   │   └── 2024-01-15_Birthday_001/
│   └── ...
├── ____INGEST_PIPELINE/                    ← working area (all processing happens here)
│   ├── INBOX/                              ← ingested raw files awaiting processing
│   ├── READY/                              ← renamed/processed, awaiting final sort into archive
│   └── .TMP/                               ← pipeline temp workspaces (sandboxes, staging)
└── ...
```

**Config shape:**

```json
"paths": {
    "root_folder": "c:\\__PHOTOS",
    "working_folder": "____INGEST_PIPELINE",
    "inbox_folder": "____INGEST_PIPELINE\\INBOX",
    "ready_folder": "____INGEST_PIPELINE\\READY",
    "temp_folder": "____INGEST_PIPELINE\\.TMP",
    "ingest": {
        "camera_uploads": "c:/Users/luxxa/Dropbox/Camera Uploads"
    }
}
```

**Resolution rules:**
- `root_folder` is the only absolute path for the archive. It is the single source of truth.
- All other working paths are relative to `root_folder` unless they are absolute.
- Ingest paths (under `paths.ingest`) are external sources and may be absolute.
- The legacy `PHOTO_BASE_FOLDER` environment variable maps to `root_folder` as a fallback when the config file does not specify it.
- `photo_base_folder` is removed from the config schema entirely.

**Legacy concept mapping:**

| Legacy concept | Legacy path | New primary path |
|----------------|-------------|------------------|
| Upload source | `c:\Users\luxxa\Dropbox\Camera Uploads\` | unchanged external ingest source |
| Unsorted intake | `c:\__PHOTOS\____TO_SORT\____UNSORTED\` | `root_folder\____INGEST_PIPELINE\INBOX\` |
| Processing ready area | `c:\__PHOTOS\____TO_SORT\__READY\` | `root_folder\____INGEST_PIPELINE\READY\` |
| Temp/raw staging | `c:\__PHOTOS\____TO_SORT\1. Original RAW_*` | `root_folder\____INGEST_PIPELINE\.TMP\...` stage workspaces |
| Final archive | moved later from `__READY` by folder sorter | `root_folder\{year}\{NN}. {MonthName}\{date folder}\` |

**Sorted output destination:**
- `FolderSortingStage` moves final assets from `READY/` directly into `root_folder/{year}/{month}/{legacy_date_folder}/`.
- The archive root is the sorted collection.
- The new pipeline must support a migration/compatibility mode that can also read legacy `____TO_SORT\____UNSORTED` as an input source when users still have files there.

**Archive naming conventions:**

```
root_folder/
├── 2024/
│   ├── 01. January/
│   │   ├── 2024-01-15_Birthday/
│   │   │   ├── photo_001.jpg
│   │   │   └── ##   EXIFs   ##/
│   │   │       └── photo_001._exif
│   │   └── 2024-01-22_Walk/
│   │       ├── photo_002.jpg
│   │       └── ##   EXIFs   ##/
│   ├── 02. February/
│   ├── 03. March/
│   └── ...
```

- Month folders: `{NN}. {MonthName}` — e.g. `01. January`, `02. February`, `12. December`
- Event/date folders preserve the legacy default grammar: `YYYY-MM-DD_(Thu) - 1. ######`
- Each event folder contains a `##   EXIFs   ##/` subfolder holding sidecar `._exif` files
- Event folders use the standardized `__` prefix subdirectory taxonomy described in Decision 10.
- RAW originals are placed under `__RAW/`.

### 6. Legacy Naming, Grouping, and Problem Handling

The staged pipeline must preserve these old-version behaviors as explicit compatibility requirements:

- Filename grammar:
  `YYYY-MM-DD_(Thu)_HH.MM.SS__{RAW__ optional}f...__T...__L...__I...__CAMERA.ext`
- RAW marker: `RAW__`
- Extension casing: RAW extensions uppercase, lossy image extensions lowercase.
- Day boundary: media captured before `04.44.44` belongs to the previous date folder.
- Date folder suffix: ` - 1. ######`
- EXIF sidecars use `._exif`.
- Pre-existing stale EXIF files are relocated before regeneration to the old-EXIF problematic area.
- Problematic taxonomy is preserved:
  - `##   UNSUPPORTED EXTENSIONS   ##`
  - `##   EMPTY FILES   ##`
  - `##   NOT_ENOUGH_INFO FILES   ##`
  - `##   DUPLICATE_FILE_NAMES FILES   ##`
- Duplicate suffix style is preserved: `_DUPE_<md5>_<n>`, including existing target rename to `_DUPE_<existing_md5>_0`.
- RAW and EXIF subfolder behavior is preserved semantically but standardized to the new canonical names:
  - RAW originals: `__RAW`
  - Metadata sidecars: `__EXIF`

### 7. Treat Safety as a Pipeline Contract

No stage may silently overwrite, delete, or drop media files. Every destructive or replacing operation must either preserve MD5 identity, register an intentional duplicate/exclusion, or pause for user input. The final validation stage is required in the default DAG.

### 8. Make Ambiguity Interactive

Unknown camera models, manual RAW development waits, and ambiguous collisions should pause the orchestrator and surface dashboard prompts. CLI mode may either fail fast, use configured defaults, or ask in-terminal depending on the selected mode.

### 9. Travel & Timezone Clock Correction Engine

Camera clocks drift, get left unshifted across timezones, or are manually adjusted late. A central date-bounded compensation module inside `PipelineContext` corrects EXIF timestamps before renaming/sorting. Loaded from `config.json`:

**Camera clock corrections** — fixes per-camera drift or DST errors within a date range:

```json
"camera_clock_corrections": [
  {
    "camera_symbol": "NE71",
    "from_date": "2026-04-10T00:00:00",
    "to_date": "2026-04-20T23:59:59",
    "offset_seconds": -3600,
    "description": "Forgot daylight saving adjustment"
  }
]
```

**Trip location mapping** — when corrected date falls inside a travel window, applies timezone normalisation and location suffix to output naming:

```json
"trips": [
  {
    "name": "Japan Trip",
    "start": "2026-04-10T00:00:00",
    "end": "2026-04-20T23:59:59",
    "timezone_offset_hours": 9,
    "location_suffix": "Japan"
  }
]
```

**Processing order:**
1. Raw EXIF timestamp extracted
2. Camera clock correction applied (if matching camera + date range)
3. Trip timezone offset applied (if corrected date falls within a trip window)
4. Corrected local time used for filename and folder placement

**Output naming with travel:**
- With trip: `2026-04-12_(Sun)_18.00.00__Japan__f4.0__T1_250__I100__NE71.jpg`
- Without trip: `2026-05-01_(Fri)_14.30.00__f2.8__T1_500__I200__C6D.cr2`

**Event folder naming with travel:**
- With trip: `2026-04-12_(Sun) - Japan/`
- Without trip: `2026-05-01_(Fri)/`

### 10. Standardized Event Folder Taxonomy and Representatives

Each final event/date folder is both a browsable contact sheet and a complete asset container. Files directly in the event/date folder are the shot-level representative images only. A representative is either:

- An original, straight-from-camera image such as a JPEG/HEIC produced by the camera.
- An extracted image derived from RAW when the camera produced only RAW and no straight-from-camera representative exists.

All supporting or alternate artifacts live in canonical `__` prefix subfolders:

| Folder | Contents |
|--------|----------|
| `__RAW` | Original, untouched camera RAW files such as `.dng`, `.cr2`, `.crw`, `.arw`, `.nef`, `.rw2`, `.mpo`. |
| `__EDITED` | Non-destructive master edits and high-quality working masters such as Lightroom `.xmp`, Photoshop `.psd`, or high-bit `.tif` files. |
| `__EXTRACTED` | Alternative or batch-extracted JPEGs from RAW that did not become the root-level representative image. |
| `__EXPORTED` | Final, full-resolution JPEG exports with color profiles applied, ready for printing or long-term archive export. |
| `__RESIZED` | Downscaled, compressed derivatives optimized for web, social media, email, or temporary sharing. |
| `__DUPLICATES` | Burst-mode discards, unused bracket exposures, accidental duplicates, low-resolution duplicates, and collision-renamed duplicates. |
| `__EXIF` | Metadata artifacts such as `._exif` sidecars, GPX track files, JSON camera logs, and related capture logs. |

Representative filenames include semantic suffixes to disclose related assets without forcing the user to inspect subfolders:

- `_RAW` means a RAW original exists in `__RAW`; edit the RAW rather than treating the representative as the best source.
- `_EXT` means the representative itself was extracted or derived from RAW rather than captured directly as an in-camera image.
- `_EDT` means a better edited/master version exists in `__EDITED`; this suffix is always last.

Suffix ordering is deterministic:

1. Base legacy filename stem.
2. `_RAW` when a RAW original exists, always first immediately after the base filename.
3. `_EXT` when the representative image was derived/extracted from RAW.
4. `_EDT` when an edited/master version exists, always at the end of the suffix list.
5. Extension.

Examples:

```
2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50__I100__6D_RAW.jpg
2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50__I100__6D_RAW_EXT.jpg
2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50__I100__6D_RAW_EXT_EDT.jpg
```

The stage implementation should centralize this taxonomy in configuration and helper functions so folder names do not reappear as ad hoc string literals throughout stage modules.

## Risks / Trade-offs

- **Large refactor risk**: Introduce the engine and stages incrementally, keeping current behavior wrapped first before deeper rewrites.
- **Windows file locks**: Centralize retry/backoff and lock checks in `MediaAsset` operations.
- **External GUI tools**: Model these as interactive stages that pause and resume explicitly.
- **Browser/backend disconnects**: Keep pipeline state in the background runner and replay current state when clients reconnect.
- **Safety validation runtime cost**: MD5 hashing can be slow, but correctness is more important than speed for final verification. The design can cache MD5s per snapshot and avoid rehashing unchanged files where safe.
- **Port conflicts**: Default to 8888 but allow CLI/config override and fail with a clear message if unavailable.

## Verification Plan

Automated verification uses `poetry run pytest` and includes:

- Contract tests for all `PipelineStage` implementations.
- Unit tests for `MediaAsset` sidecar movement and Windows retry wrappers.
- Sandbox tests for temporary workspace isolation and cleanup.
- Collision tests for identical MD5, older/larger original detection, low-resolution threshold handling, and ambiguous prompt pauses.
- Safety tests proving `CatastrophicSafetyError` is raised for missing outputs, MD5 mismatches, and zero-byte outputs.
- Backend tests for start/pause/resume/step routes and WebSocket event payload shapes.
- Travel/timezone correction tests verifying clock drift and trip offset application.

### E2E Mock Test Fixture Matrix

The automated E2E integration test suite physically writes mock assets into the INBOX source directory, runs them through the complete pipeline, and asserts output names, MD5 hashes, and folder paths match expected results.

**Mock trip config:** Japan Trip active `2026-04-10` to `2026-04-20` (+9h offset, suffix `Japan`). Sony RX100 (`NE71`) clock correction `-3600s` during this window.

| Input | Camera | EXIF DateTime | Corrections | Expected Output |
|-------|--------|---------------|-------------|-----------------|
| `test1.jpg` (2MB, MD5 `a1b2...`) | NE71 | 2026-04-12 10:00:00 | Clock -1h → 09:00, Trip +9h → 18:00 | `2026-04-12_(Sun)_18.00.00__Japan__f4.0__T1_250__I100__NE71.jpg` in `READY/2026-04-12_(Sun) - Japan/` |
| `test2.cr2` (15MB, MD5 `c7d8...`) | C6D | 2026-05-01 14:30:00 | None | `2026-05-01_(Fri)_14.30.00__f2.8__T1_500__I200__C6D.cr2` in `READY/2026-05-01_(Fri)/` |
| `test3.jpg` (2MB, MD5 `a1b2...`) | NE71 | 2026-04-12 10:00:00 | Exact duplicate of test1 (same MD5) | Safely merged — no output |
| `test4.jpg` (2MB, MD5 `8888...`) | NE71 | 2026-04-12 10:00:00 | Name collision, different content | `..._DUPE_8888..._1.jpg` in `READY/2026-04-12_(Sun) - Japan/` |
| `test5.jpg` (120KB, MD5 `eeee...`) | NE71 | 2026-04-12 10:00:00 | Significantly smaller (<50%) | `..._lowres_eeee....jpg` in problematic/duplicates |

Manual verification includes:

- Launching `_photosorter.bat` and confirming legacy behavior is preserved: Camera Uploads move to `c:\__PHOTOS\____INGEST_PIPELINE\INBOX\`, EXIF sidecars travel with files, and final images land in year/month/date folders.
- Launching `python src/main.py --ui` and confirming the dashboard opens.
- Simulating an unknown camera and confirming the mapping persists to `config.json`.
- Creating conflicting files and confirming automatic and interactive collision paths.
- Running a sample folder end-to-end and verifying final safety validation passes.
