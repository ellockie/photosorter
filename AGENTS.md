# PROJECT KNOWLEDGE BASE

**Generated:** 2026-05-23
**Commit:** ba189bd
**Branch:** master

## READ FIRST — THE ARCHIVE STANDARD

**`ARCHIVE_STANDARD.md` (repo root) defines the target shape of the photo + video
archive on disk.** Read it before writing or changing any code that creates, moves,
renames or scans archive folders. It defines:

- the path `ROOT/<YYYY>/<NN>. <Month>/<dated folder>/…` and what may sit at each level
- the dated-folder and media-file naming grammars, and the historical forms still read
- `__CONTAINER__` marking on any dated folder holding dated children
- the **closed** set of `__`-prefixed subfolders allowed inside a dated folder
- sidecar naming and pairing
- **one definition per rule** (T8) — taxonomy, regexes and constants each live in
  exactly one module. Never restate one in a stage.

Rules carry stable IDs (`P1`, `N3`, `C2`, `S1`, `F5`, `X4`, `T2`); cite the ID.
§8 is the machine-readable YAML form — parse that, not the prose.

It is **v0.8, draft, not enforced**, and it is also written to be handed to
third-party tools, so it describes the target, not the current code. Do not add
enforcement, and do not "fix" the archive or the taxonomy to match it, until the
open questions in it are answered.

## OVERVIEW

photosorter — Python 3.13 photo processing pipeline: rename, sort, and organise digital photos by EXIF metadata. Uses exiftool for metadata extraction and Poetry for dependency management. Windows-only.

## STRUCTURE

```
./
├── src/           # All application code
│   ├── main.py    # Orchestrator — sequential task pipeline
│   ├── common/    # Shared functions + globals
│   ├── constants/ # All config (paths, camera symbols, extensions)
│   └── utils/     # Terminal colour + timing decorators
├── tests/         # 1 test file (6 cases)
├── _Backup/       # Archived old versions and test images
├── openspec/      # OpenSpec spec-driven change management
├── .opencode/     # oh-my-openagent plugin (node tooling)
├── .{claude,cursor,gemini,qwen,windsurf,codex,kiro}/  # AI harness configs (same openspec skills)
└── _photosorter.bat  # Entry: self-healing Poetry launch
```

## WHERE TO LOOK

| Task | Location | Notes |
|------|----------|-------|
| Main pipeline logic | `src/main.py` | Sequential `_TASK_*()` calls |
| EXIF extraction & file rename | `src/common/common.py` | ~830 lines — core logic |
| All paths & camera symbols | `src/constants/constants.py` | `PHOTO_BASE_FOLDER` env var required |
| Global counters | `src/common/globals.py` | Mutable module-level state |
| Folder sorting into year/month | `src/folder_sorter.py` | `ReadyPhotosFolderMover` class |
| Camera-upload separation | `src/move_other_images.py` | Uses pyexiftool wrapper |
| Photo selection/copying | `src/photo_folder_copier.py` | Marker-based selective copy |
| HDR cluster detection | `src/sortHDRfiles (cleaner).py` | Python 2 legacy, standalone |
| Archive maintenance tools | `tools/` | Stdlib-only; run on a bare interpreter, load name grammars by file path |
| Restructuring an archive | `tools/restructure_archive.py` | The seven-step front door; `_restructure_archive.bat` / `.ps1` at the root |
| Where the grouper GUI lives | `src/pipeline_stages/grouper_launch.py` | Leaf module: install detection + command line, one definition |
| Companion + sidecar matching | `src/pipeline_stages/companion_matching.py` | Leaf module: the engine. `reconcile_folder` (per event folder, capture time), `place_companions` (whole target, gather-then-distribute, name match; X10/X13 + MD5 on collision), `migrate_legacy_containers` (`##   EXIFs   ##`->`__EXIF`), `survey_trees` (read-only: non-compliant folders, legacy containers). Pipeline stage AND restructure tool both run it |
| Tests | `tests/test_organise_date_folders.py` | Pytest, 6 cases |

## CONVENTIONS

- Task functions **must** be named `_TASK_*()` — enforced at runtime by `verify_if_function_is_a_task`
- Every task gets `@print_current_task_name` + `@display_timing` decorators
- Global state lives in `common/globals.py` as bare module variables
- Imports use explicit multi-line `from X import Y` (one per line with `\`)
- Print-based logging with `Colorise.*` for terminal colours
- Bare `except:` blocks (no exception type) are accepted project-wide pattern
- Path building uses `full_path_of(folder_name, ...)` helper, never raw `os.path.join`
- Duplicate detection uses MD5 comparison via `file_md5()` before overwriting
- Stale `._exif` files cleaned before regeneration in pipeline

## ANTI-PATTERNS (THIS PROJECT)

- Bare `except:` without exception type — **accepted but don't add new ones**
- `print()` as logging — no structured logging anywhere
- Mutable global counters mutated across module boundaries
- No `if __name__ == "__main__":` guards in several modules (side effects on import)
- Python 2 file in repo: `sortHDRfiles (cleaner).py` uses `print` statement

## COMMANDS

```bash
# Launch full pipeline
_photosorter.bat

# Restructure an existing archive: canonicalise -> reconcile -> group ->
# reconcile -> canonicalise -> check/fix against ARCHIVE_STANDARD.md (last two
# not implemented). Dry run by default; .ps1 is the same, for PowerShell.
_restructure_archive.bat
_restructure_archive.bat "d:\__PHOTOS_BACKUP" --year 2024 --apply

# Run tests
poetry run pytest
```

## NOTES

- Requires `PHOTO_BASE_FOLDER` environment variable (set via `SETX`)
- Depends on external binaries: `exiftool.exe`, IrfanView, Canon DPP, Sony IED
- ExifTool wrapper: `pip install git+https://github.com/smarnach/pyexiftool.git`
- Project uses Poetry; `_photosorter.bat` auto-installs missing deps
