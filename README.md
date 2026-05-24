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
src/pipeline/frontend/
src/pipeline/static/
```

The new pipeline uses:

```text
c:\__PHOTOS\____INGEST_PIPELINE\INBOX
c:\__PHOTOS\____INGEST_PIPELINE\READY
c:\__PHOTOS\____INGEST_PIPELINE\.TMP
```

It also keeps legacy paths in configuration so existing folders can be migrated safely.

## Dashboard Runner

The local dashboard is served by FastAPI on port `8888`.

Run it manually with:

```powershell
poetry run python src\main.py --ui --port 8888
```

The dashboard is intended to show pipeline stage progress, logs, prompt handling, unknown camera mapping, collision resolution, and safety verification alerts.

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
