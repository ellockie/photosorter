# photosorter

Windows-only photo and video sorting pipeline for moving media out of Dropbox Camera Uploads, generating EXIF sidecars, renaming files from metadata, and organising the final archive by year, month, and event folder.

The project is currently in a transition period. The default batch file still runs the legacy command-line sorter for safety, while a new pluggable pipeline and local dashboard are being introduced under the OpenSpec change `pluggable-pipeline-architecture`.

## Current Default Behaviour

Run:

```powershell
.\_photosorter.bat
```

This launches the legacy CLI pipeline:

```powershell
poetry run python src\main.py --cli
```

This is intentional for now. The new dashboard pipeline exists, but the batch file stays on the legacy path until the refactor is fully verified against the real archive.

## Legacy Folder Flow

The legacy workflow preserves the existing archive layout:

```text
c:\Users\luxxa\Dropbox\Camera Uploads\
    -> c:\__PHOTOS\____TO_SORT\____UNSORTED\
    -> c:\__PHOTOS\____TO_SORT\__READY\
    -> c:\__PHOTOS\____TO_SORT\__READY\2026\05. May\2026-05-14_(Thu) - 1. ######\
```

The `PHOTO_BASE_FOLDER` environment variable must point at the archive root, usually:

```text
c:\__PHOTOS
```

The code expects the legacy working tree below that root:

```text
c:\__PHOTOS\____TO_SORT\
```

## Naming Convention

Photos are renamed from EXIF metadata using the legacy format:

```text
YYYY-MM-DD_(Thu)_HH.MM.SS__RAW__f2.8__T1_250__L50__I100__CAMERA.CR2
YYYY-MM-DD_(Thu)_HH.MM.SS__f2.8__T1_250__L50__I100__CAMERA.jpg
```

RAW files keep uppercase RAW extensions and include the `RAW__` marker. Lossy files use lowercase extensions.

Event folders use:

```text
YYYY-MM-DD_(Thu) - 1. ######
```

Month folders use:

```text
05. May
```

Photos before the configured day boundary, currently `04.44.44`, are grouped into the previous day.

## EXIF Sidecars

ExifTool generates sidecar files using the `._exif` extension.

During sorting, EXIF sidecars are moved next to the final event folder, inside:

```text
##   EXIFs   ##
```

RAW files are moved into:

```text
##   RAWs   ##
```

Example final folder:

```text
c:\__PHOTOS\____TO_SORT\__READY\2026\05. May\2026-05-14_(Thu) - 1. ######\
    photo.jpg
    ##   RAWs   ##\
        photo.CR2
    ##   EXIFs   ##\
        photo._exif
```

Pre-existing stale `._exif` files found in the unsorted folder are treated as old sidecars and moved or removed before fresh EXIF generation.

## New Pluggable Pipeline

The refactor introduces a staged DAG pipeline with isolated modules for each stage. The goal is to make stages independently editable and reduce context needed for future work.

Key new modules:

```text
src/core.py
src/stages.py
src/pipeline_stages/
src/server.py
src/pipeline/static/
```

The new pipeline uses:

```text
c:\__PHOTOS\____INGEST_PIPELINE\INBOX
c:\__PHOTOS\____INGEST_PIPELINE\READY
c:\__PHOTOS\____INGEST_PIPELINE\.TMP
```

`INBOX` is the primary intake going forward; the legacy `____TO_SORT\____UNSORTED` folder is preserved as a migration source until the new pipeline is verified flawless.

All configured paths are relative to a single base folder (default `c:\__PHOTOS`), which will be overridable via a CLI parameter.

### Planned: Folder Intake With Origin Labels

The intake folders will accept not only loose files but also folders containing images (a top-level `__DONT_MOVE` folder is never touched). The containing folder's name — minus any leading date/date-time part — is carried with each file as an origin label, persisted in a run journal, and used to name the final event folder, e.g. `2024-01-15_(Mon) - Birthday`. Labeled and unlabeled files for the same date are kept in separate event folders. Pre-existing metadata files (most importantly `._exif` sidecars) travel with their images; folder-level GPX files go to `__GEOLOCATIONS`.

### Planned: Event Folder Taxonomy

Final event folders use a standardized `__` prefix subfolder set (draft, under review): `__2_SHARE`, `__3D`, `___OTHER`, `__DUPLICATES`, `__EDITED`, `__EXIF`, `__EXPORTED`, `__EXTRACTED`, `__EXTRACTED_VIDEOS`, `__GEOLOCATIONS`, `__HASHES`, `__PANORAMAS`, `__PEOPLE`, `__RAW`, `__RESIZED`, `__SHARED`, `__VIDEOS`. The new pipeline writes `__EXIF`/`__RAW`; the `##   EXIFs   ##` / `##   RAWs   ##` names remain only in legacy CLI output.

## Dashboard Runner

The local dashboard is plain HTML/CSS/JavaScript (no build step, no Node.js) served by FastAPI on port `8888`.

Run it manually with:

```powershell
poetry run python src\main.py --ui --port 8888
```

The dashboard is intended to show pipeline stage progress, logs, prompt handling, unknown camera mapping, collision resolution, and safety verification alerts.

### Every stage announces itself

The orchestrator prints a banner on entry to each stage and another on exit,
carrying the display name, the stage id and the outcome:

```
>> STAGE  12/23  START     Rename and Sort  [rename-and-sort]
<< STAGE  12/23  COMPLETE  Rename and Sort  [rename-and-sort]  (4.1s)
```

The exit banner comes from a `finally` block, so **every** way out of a stage is
announced exactly once — `COMPLETE`, `FAILED` (with the exception), `PAUSED`
(with the reason), or `ABORTED` for an interrupt. A stage cannot leave the
transcript with an opening line and no closing one, and a new stage cannot
forget to announce itself: stages never emit these, only the orchestrator does.
`tests/test_stage_banners.py` enforces it against the whole default graph.

### Prompts never time out

A prompt exists because the pipeline cannot proceed without a human decision, so
it waits as long as that takes. There is no timer anywhere in the wait; the
status line reads **Waiting for you** and the run stays open until you answer.
The only other way out is the **Pause** button, which releases the wait and ends
the run as paused (everything already written to disk stays written).

Prompts that block the run:

| Prompt | What it is asking |
| --- | --- |
| `name_collision` | Two files claim one name and neither age nor size settles it. |
| `crw_conversion` / `dpviewer_conversion` | Convert these RAWs before later stages move them. |
| `raw_conversion` | Convert the staged workspace; it is swept the moment you answer. |
| `grouping_review` | Event folders from this run are still unnamed. |

### Grouping review

Closing the grouper window is not the same as finishing the job. After grouping,
the **Grouping Review** stage lists every folder from this run still carrying
`__TO_SPLIT__`, `__TO_LABEL__`, or the bare `- 1. ######` placeholder, and holds
the run there. Rename them — in the grouper or in Explorer — and press
**Re-scan**; **Continue anyway** fast-forwards past folders you meant to leave
unnamed. Either way the stage then re-scans the archive as it stands *now*, so
companion reconciliation follows the folders the grouper actually created rather
than paths captured before it ran. Configured under `grouping_review.enabled`
(unset follows `screenshot_grouping.enabled`).

Folders are opened in the grouper — and listed in the review — in **alphabetical
order**, which for `YYYY-MM-DD…` names is oldest day first. That is the order
Explorer shows, so it is always obvious which folder the GUI is on and which are
still to come. With `screenshot_grouping.max_folders` set, the cap keeps the
first N in that order.

### Dated-name convention

One canonical form is written everywhere — note the **double** underscore before
the time, matching the screenshot grouper:

```
2026-08-14_(Fri)__15.32.01__f1.7__T1_180__L23.0.eq__I12__SG23U.jpg
```

Weekday abbreviations are fixed English, never locale-dependent. Earlier forms
(`_(Fri)_15.32.01` and `__15.32.01`) are still read, so an existing archive keeps
working and its sidecars keep matching their images.

## Safety Goals

The new architecture includes a safety verifier that checks:

- input/output file counts
- MD5 identity preservation
- zero-byte files
- unexpected missing files

The target behaviour is zero silent file loss. If the verifier detects a catastrophic mismatch, the pipeline should halt instead of continuing.

## Development Commands

Install dependencies:

```powershell
poetry install
```

Run tests:

```powershell
poetry run pytest
```

Run the legacy sorter:

```powershell
.\_photosorter.bat
```

Run the dashboard:

```powershell
poetry run python src\main.py --ui --port 8888
```

## External Requirements

The project depends on Windows tools and local binaries:

- `exiftool.exe`
- Canon Digital Photo Professional, for some RAW workflows
- Sony Imaging Edge Desktop, for some RAW workflows
- IrfanView, for legacy viewing/conversion helpers

## OpenSpec

The active refactor is tracked in:

```text
openspec/changes/pluggable-pipeline-architecture/
```

Implementation progress can be inspected with:

```powershell
openspec status --change pluggable-pipeline-architecture
```

The remaining work is primarily manual verification against the real photo archive and dashboard workflows.
