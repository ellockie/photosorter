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

### Dashboard Frontend (`src/pipeline/static/`)

A hand-written vanilla HTML/CSS/JavaScript dashboard with zero build step and zero Node.js dependency:

```
src/pipeline/static/
├── index.html                ← layout, controls, progress panel, prompt containers
├── assets/
│   ├── app.js                ← fetch/WebSocket wiring, DAG rendering, prompts, alerts
│   └── app.css               ← dark styling
```

FastAPI statically mounts `src/pipeline/static/`. During everyday execution (`_photosorter.bat`), everything runs directly from Python.

**Auto-open behaviour:** The server automatically opens the dashboard in the default browser on launch (configurable via `dashboard.open_browser` in config).

## Decisions

### 1. Use a Vanilla HTML/CSS/JS Frontend (Decided 2026-06-12)

The dashboard is plain HTML, CSS, and JavaScript served as static files — no React, no Vite, no build step. This was decided after review: the tool is local and single-user, and runtime fragility matters more than UI sophistication. The abandoned React/Vite skeleton under `src/pipeline/frontend/` should be deleted.

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
    "legacy_unsorted_folder": "____TO_SORT\\____UNSORTED",
    "legacy_ready_folder": "____TO_SORT\\__READY",
    "ingest": {
        "camera_uploads": "c:/Users/luxxa/Dropbox/Camera Uploads"
    }
}
```

**Resolution rules:**
- `root_folder` (the base folder) is the only absolute path for the archive, defaulting to `c:\__PHOTOS`. It is the single source of truth.
- `root_folder` can be overridden by a CLI parameter (e.g. `--base-folder`), which takes precedence over the config value.
- All other working paths MUST be stored relative to `root_folder` in `config.json` (absolute values are tolerated for backward compatibility but normalized to relative on save).
- Ingest paths (under `paths.ingest`) are external sources and may be absolute.
- The legacy `PHOTO_BASE_FOLDER` environment variable maps to `root_folder` as a fallback when neither the CLI parameter nor the config file specifies it.
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
│   │   ├── 2024-01-15_(Mon) - Birthday/
│   │   │   ├── photo_001.jpg
│   │   │   └── __EXIF/
│   │   │       └── photo_001.jpg._exif
│   │   └── 2024-01-22_(Mon) - 1. ######/
│   │       ├── photo_002.jpg
│   │       └── __EXIF/
│   ├── 02. February/
│   ├── 03. March/
│   └── ...
```

- Month folders: `{NN}. {MonthName}` — e.g. `01. January`, `02. February`, `12. December`
- Event/date folders preserve the legacy default grammar `YYYY-MM-DD_(Thu) - 1. ######` when no origin label is known; with an origin label (Decision 11) the suffix becomes ` - {label}`.
- Event folders use exclusively the standardized `__` prefix subdirectory taxonomy described in Decision 10. The legacy `##   EXIFs   ##` / `##   RAWs   ##` names exist only in folders produced by the legacy CLI; the new pipeline writes `__EXIF/` and `__RAW/`.
- Sidecar filenames keep the full original filename embedded: `photo_001.jpg._exif` (not `photo_001._exif`).
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

Camera clocks are zone-unaware wall clocks. They go wrong in two independent ways: the world's local time changes (you cross a border, or DST flips) and the camera is not adjusted until later — or never. The earlier "interval + offset" model (`camera_clock_corrections` + `trips`, each carrying a hand-computed `offset_seconds`/`timezone_offset_hours`) conflated two genuinely separate concerns and made you compute every offset by hand. This is replaced by a **two-timeline model** driven by named IANA zones, where offsets are *derived*, never typed.

#### Two independent timelines

```
 LOCATION timeline   — where I physically was   → DISPLAY zone + folder suffix + geolocation
 CAMERA-CLOCK timeline (per camera) — what it was set to → reading → TRUE INSTANT (truth recovery)
```

They are independent because the two events are independent: you cross a zone at one moment (possibly mid-flight), and you adjust a given camera at another moment, or not at all. They meet at exactly one computed value — the **true instant** — which is the spine of the engine:

```
  EXIF reading R  +  camera C
        │  CAMERA-CLOCK timeline: which zone was C set to at R?  → that zone's offset
        ▼
  TRUE INSTANT  (absolute, zone-free)
        │  LOCATION timeline: where was I at that instant?  → display zone + suffix
        ▼
  DISPLAY time  →  filename  →  day-boundary(04:44:44)  →  event folder
```

There is deliberately **no privileged "home" zone constant**. Home was a different place in different eras and must not be hardcoded as a string. Home is simply the long, label-less stretches of the location timeline.

#### Named zones, derived offsets

All zones are IANA names (`Europe/London`, `Asia/Tokyo`), resolved through the stdlib `zoneinfo` database (598 zones, no third-party dependency). Because the zones carry their own DST rules, **DST stops being a special case**: `Europe/London` already knows BST↔GMT. A DST change therefore needs *nothing* on the location side — it is only ever a camera-clock breakpoint ("I set the camera back to London wall-time on this date"). Travel and DST collapse into one primitive: `set_to` a zone at a moment.

A small user-curated alias map keeps zone entry typo-free; the full 598-name list is regenerated on demand from `zoneinfo.available_timezones()` for copy-paste when visiting somewhere new.

```jsonc
"zones": { "PL": "Europe/Warsaw", "UK": "Europe/London", "JP": "Asia/Tokyo" },

"locations": [
  { "since": "2015-01-01_(Thu)_00.00.00", "zone": "UK" },                         // home era (no label)
  { "since": "2026-04-11_(Sat)_07.00.00", "zone": "JP",
    "label": "Japan", "coords": [35.68, 139.69],
    "until":  "2026-04-20_(Mon)_22.00.00" }                                        // 'until' = sugar: auto-resume prior era
],

"camera_clock_sets": [
  { "camera": "NE71", "at_reading": "2026-04-11_(Sat)_18.00.00", "set_to": "JP" },
  { "camera": "NE71", "at_reading": "2026-03-29_(Sun)_03.00.00", "set_to": "UK" }   // a DST fix, same location
]
```

- `locations` replaces both the old `home_zone` and `trips`. A trip is just an entry with a `label`; an era is an entry without one. `until` is optional sugar that auto-inserts the "resume previous era" breakpoint.
- `camera_clock_sets` is **per camera**. A camera never adjusted during a trip simply has no entry in that window — it stays on its prior zone, so the whole trip is one lag gap for that body. No special case.

#### The `at_reading` frame convention (ENFORCED)

`at_reading` is the dividing line the engine compares each photo's reading against to choose the clock interval. A bare timestamp is **ambiguous about which clock it is measured in**, and around an adjustment there are two clocks in play:

```
 Fixing NE71 from London(+0) to Tokyo(+9):

 camera SHOWS:  …08:58  08:59  09:00 ──[press SET]── 18:00  18:01…
                └──── London frame ────┘             └─ Tokyo frame ─┘
```

The last London reading `09:00` and the first Tokyo reading `18:00` are **the same physical instant**, 9 hours apart on paper. If the recorded `at_reading` does not commit to one frame, a future reader (human or loader) cannot tell which was meant, and a wrong guess silently classifies every photo near the seam on the wrong side of the boundary.

**Hard rule: `at_reading` is ALWAYS the first reading the camera showed *after* it was corrected** — i.e. the timestamp of the first correctly-stamped photo (the Tokyo `18:00`). With that frame fixed, the interval test is unambiguous:

```
 reading <  at_reading  → pre-adjustment interval  (camera still on the old zone → correct it)
 reading ≥  at_reading  → post-adjustment interval (camera already on the new zone → leave it)
```

When you travel **east** (or spring forward), the clock jumps *forward* at the adjustment, leaving an empty gap (here: nothing can read between 09:00 and 18:00). No photo can land in that gap, so the seam is clean and exact.

**Why this is enforced and not merely documented:** this is the one field where a plausible, innocent entry produces a *silent* wrong answer. The human instinct is to record "when I noticed the clock was wrong" (an old-frame value) rather than "the first right photo" (the new-frame value). Every other schema field fails *loudly* on bad input; this one fails *invisibly* — no crash, no validation error, just photos quietly filed into the wrong day. So the loader enforces the convention with a consistency check: each `set_to` zone's offset and the previous interval's offset imply an expected jump magnitude; the loader verifies the recorded boundary is consistent with that jump and **warns** when an entry looks recorded in the old (pre-adjustment) frame — e.g. *"camera-clock set for NE71 at 2026-04-11_09.00.00 appears to be in the OLD clock frame; at_reading must be the first corrected reading (expected ~18.00.00)."* The `set_to` zone is therefore required precisely so this check is possible.

**Westward / fall-back caveat (documented, not silently wrong):** when the clock jumps *backward* (flying west, or autumn fall-back) the readings *overlap* — the same wall-clock value exists on both sides of the adjustment (the genuine "repeated hour," identical to a phone showing 01:30 twice on DST night). No recorded boundary can fully disambiguate a repeated reading. The engine defaults such ambiguous readings to the **post-adjustment (already-corrected)** interval and surfaces the small straggler set for optional hand-nudging, rather than guessing silently.

#### Processing order (per asset)

1. Extract raw EXIF reading `R` and camera symbol `C` (from EXIF make/model, not the filename — see Decision 12).
2. CAMERA-CLOCK timeline: locate the `at_reading` interval containing `R` for camera `C`; interpret `R` in that interval's `set_to` zone → **true instant**.
3. LOCATION timeline: locate the location active at the true instant → display zone + optional `label` suffix + `coords`.
4. Convert the true instant into the display zone → corrected local time.
5. Corrected local time drives filename and folder; the `04:44:44` day-boundary rule is applied to the corrected time, not the raw reading.

**Output naming with travel:**
- With label: `2026-04-12_(Sun)_18.00.00__Japan__f4.0__T1_250__I100__NE71.jpg`
- Without: `2026-05-01_(Fri)_14.30.00__f2.8__T1_500__I200__C6D.cr2`

**Event folder naming with travel:**
- With label: `2026-04-12_(Sun) - Japan/`
- Without: `2026-05-01_(Fri)/`

#### Geolocation is derived, never stored per-folder

The trip definition lives only in the central `locations` timeline — it cannot live in any one event folder's `__GEOLOCATIONS`, because a trip spans many folders. Each event folder instead receives a *projection* of the timeline:

```
  locations[]  (central source of truth: zone + label + coords)
        │  projected per event folder
        ▼
  <event folder>/__GEOLOCATIONS/
        ├── _location.json   ← derived stamp: zone, label, approx coords for this folder's dates
        └── track.gpx        ← real GPS tracks whose timestamps fall in this folder (if any)
```

This yields **basic geolocation for free** — every photo gets a country/zone from the timeline even with no GPS hardware — and real GPX tracks enrich it where present.

#### Stand-alone retro-correction tool

The same correction engine must run **outside the pipeline** against an already-named, already-sorted archive, given a date range and a target folder containing many event folders. It is delivered as its **own stand-alone script** (not a `main.py` subcommand), so it can be run independently of the pipeline entrypoint, takes `--from` / `--to` (date range) and a `--folder` (a parent holding many event folders) as arguments, and imports the shared correction engine + `core.py` asset/file-safety helpers so renames and moves go through the same Windows-safe, sidecar-aware operations as the pipeline. It is purely mechanical and re-runnable:

```
  read EXIF time + make/model  (idempotent: NEVER reads the already-corrected filename)
        │  apply both timelines → corrected display time
        ▼
  rename file + EVERY sidecar (._exif, .xmp, RAW, extracted…)
        │  did day-boundary(04:44:44) move the day?
        ▼
  move into  <new-date> - <SAME description carried verbatim>
```

- **EXIF is the source, not the filename** — the filename already holds a corrected time, so re-reading it would double-correct; EXIF holds the untouched original reading, making the tool safely idempotent. Derivatives/sidecars without their own EXIF follow their representative image rather than being timed independently.
- **Descriptions are opaque** — the tool does **not** distinguish a trip suffix (`- Japan`) from a manual label (`- Birthday`); it carries the existing description string verbatim onto the corrected date. Suffixes are only ever *derived* in the pipeline's first naming pass; the retro tool never second-guesses an existing name.
- **Re-foldering across event folders is in scope** — a correction that crosses the day boundary moves the file (and sidecars) to the corrected day's folder, created if missing.
- **Residual ambiguity prompts, never guesses** — a shifted file landing on a day that already holds multiple unnamed placeholder events (`1. ######`, `2. ######`) is surfaced for user choice.

### 10. Standardized Event Folder Taxonomy and Representatives

Each final event/date folder is both a browsable contact sheet and a complete asset container. Files directly in the event/date folder are the shot-level representative images only. A representative is either:

- An original, straight-from-camera image such as a JPEG/HEIC produced by the camera.
- An extracted image derived from RAW when the camera produced only RAW and no straight-from-camera representative exists.

All supporting or alternate artifacts live in canonical `__` prefix subfolders:

| Folder | Managed by | Contents |
|--------|-----------|----------|
| `__RAW` | pipeline | Original, untouched camera RAW files such as `.dng`, `.cr2`, `.crw`, `.arw`, `.nef`, `.rw2`, `.mpo`. |
| `__EDITED` | pipeline | Non-destructive master edits and high-quality working masters such as Lightroom `.xmp`, Photoshop `.psd`, or high-bit `.tif` files. |
| `__EXTRACTED` | pipeline | Alternative or batch-extracted JPEGs from RAW that did not become the root-level representative image. |
| `__EXTRACTED_VIDEOS` | pipeline (future) | Motion-photo videos (e.g. Samsung Ultra embedded videos) extracted as separate video files; the original image file stays intact in place. Defined now, extraction not implemented yet. |
| `__EXPORTED` | pipeline | Final, full-resolution JPEG exports with color profiles applied, ready for printing or long-term archive export. |
| `__RESIZED` | pipeline | Downscaled, compressed derivatives optimized for web, social media, email, or temporary sharing. |
| `__DUPLICATES` | pipeline | Burst-mode discards, unused bracket exposures, accidental duplicates, low-resolution duplicates, and collision-renamed duplicates. |
| `__EXIF` | pipeline | Metadata artifacts such as `._exif` sidecars, JSON camera logs, and related capture logs. |
| `__GEOLOCATIONS` | pipeline | Geodata artifacts such as GPX track files covering the event, moved here from the intake folder. |
| `__HASHES` | pipeline (future) | Per-file MD5 / SHA-256 hash manifests for the event folder. Defined now, generation not implemented yet. |
| `__VIDEOS` | pipeline | Video files captured during the event. |
| `__2_SHARE` | manual | Sharing queue — files selected and prepared to be shared. |
| `__SHARED` | manual | Files that have already been shared. |
| `__PEOPLE` | manual | Manually curated portraits/people selections. |
| `__PANORAMAS` | manual | Manually curated panorama sources/results. |
| `__3D` | manual | Manually curated stereo/3D material. |
| `___OTHER` | manual | Anything that does not fit the other folders. |

The folder set is a draft pending a final taxonomy review by the user; the pipeline MUST treat the list (names and routing rules) as configuration, never as string literals in stage modules. Folders marked "manual" are created or recognized by the pipeline but never populated automatically.

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

### 11. Ingest Provenance: Folders in the Intake, Origin Labels, and Sidecar Travel

The intake folders (`INBOX` and, during migration, legacy `____TO_SORT\____UNSORTED`) accept not only loose media files but also folders containing media. Processing rules:

- A top-level folder named `__DONT_MOVE` is excluded entirely — the pipeline never reads, moves, or modifies anything inside it. The exclusion applies at the top level of the intake folder only.
- All other subfolders are walked recursively. Each ingested file records an **origin label**: the name of its containing folder with any leading date or date-time part stripped (e.g. `2024-01-15 Birthday` → `Birthday`, `2024-01-15_18.30 Party` → `Party`). Files lying directly in the intake folder have no origin label.
- The origin label and origin path are stored in `MediaAsset.metadata` and persisted to a run journal (e.g. `____INGEST_PIPELINE\.JOURNAL\<run-id>.jsonl`, one JSON record per file: origin path, origin label, MD5) so provenance survives crashes and restarts and is never held only in memory.
- During final sorting, a file with an origin label lands in an event folder named `YYYY-MM-DD_(Ddd) - {label}` instead of the generic `YYYY-MM-DD_(Ddd) - 1. ######`. Labeled and unlabeled files sharing the same capture date go to **separate** event folders; groups are never merged, since same-date folders may represent different events.
- Pre-existing metadata files found next to an ingested image — most importantly `._exif` sidecars, matched by full filename stem (`IMG_001.jpg` ↔ `IMG_001.jpg._exif`) — are registered as `MediaAsset` sidecars at ingest time and travel with the image through every rename, move, and sort.
- Folder-level geodata files (e.g. a GPX track covering the whole folder) travel to the `__GEOLOCATIONS` subfolder of the event folder(s) derived from that origin folder.

```
____UNSORTED\ (or INBOX\)
├── IMG_001.jpg                        → 2024-03-02_(Sat) - 1. ######\           (no label)
├── 2024-01-15 Birthday\
│   ├── IMG_002.jpg                    → 2024-01-15_(Mon) - Birthday\
│   ├── IMG_002.jpg._exif              → 2024-01-15_(Mon) - Birthday\__EXIF\
│   └── track.gpx                      → 2024-01-15_(Mon) - Birthday\__GEOLOCATIONS\
└── __DONT_MOVE\                       → untouched
```

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
