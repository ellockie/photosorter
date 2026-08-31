# SRC — Application Source

> **Archive layout is governed by `../ARCHIVE_CONSTITUTION.md`** (draft, under
> review, not enforced). Any change to a stage that creates, moves, renames or
> scans archive folders must be read against it — especially its Article 4 (the
> closed set of `__` subfolders) and Article 8 (one definition per rule: the
> taxonomy lives in `pipeline_stages/taxonomy.py`, the timestamp grammar in
> `pipeline_stages/stamps.py`, the folder-tail grammar in
> `pipeline_stages/grouping_names.py`, and nowhere else).

## OVERVIEW

All photosorter application code. 12 Python files, ~100KB. Single-entry pipeline (main.py) calling sequential `_TASK_*()` functions.

## STRUCTURE

```
src/
├── main.py                  # Orchestrator — calls all tasks in order
├── common/
│   ├── common.py            # Core logic: EXIF extraction, file rename, path building
│   └── globals.py           # Module-level counter dict + mutable state
├── constants/
│   └── constants.py         # All hardcoded paths, camera symbols, extensions
├── utils/
│   ├── colorise.py          # Colorama terminal colour wrapper
│   └── decorators.py        # @print_current_task_name, @display_timing
├── folder_sorter.py         # Moves dated photo folders into year/month hierarchy
├── move_other_images.py     # Separates "my" camera photos from uploads by EXIF Model
├── organise_date_folders.py # WIP — date-based folder organisation
├── photo_folder_copier.py   # Selective folder copy by marker file
├── photo_util_folder_copier.py   # FolderCopier class
├── photo_util_folder_parser.py   # FolderParser class
└── sortHDRfiles (cleaner).py     # Python 2 legacy — HDR cluster detection
```

## WHERE TO LOOK

| Concern | File | Notes |
|---------|------|-------|
| Pipeline orchestration | `main.py` | `main()` calls 10+ tasks sequentially |
| EXIF parsing & rename | `common/common.py` | `extract_data_from_exif_file_and_rename_original_image()` |
| Duplicate detection | `common/common.py` | `file_md5()` — MD5 comparison before overwrite |
| Folder creation logic | `common/common.py` | `create_date_folder()`, `create_missing_folders()` |
| All constants | `constants/constants.py` | 316 lines — paths, cameras, extensions |
| RAW file routing | `constants/constants.py` | `RAW_EXTENSIONS__FOLDERS_MAP` |
| Terminal colours | `utils/colorise.py` | Static methods on `Colorise` class |
| Timing/logging decorators | `utils/decorators.py` | Enforces `_TASK_` naming convention |
| Folder sorting | `folder_sorter.py` | `ReadyPhotosFolderMover` class |
| Camera upload separation | `move_other_images.py` | Filters by EXIF:Model vs `MY_CAMERA_SYMBOLS` |

## CONVENTIONS

- Every task function decorated with `@print_current_task_name` then `@display_timing`
- Functions that are pipeline steps must start with `_TASK_` — verified at runtime
- Imports: explicit multi-line `from X import Y \`, one symbol per line
- Paths: `full_path_of(folder_name, ...)` in `common.py` — never `os.path.join` directly
- No `if __name__ == "__main__":` in most files — side effects on import (e.g. `organise_date_folders.py`)

## ANTI-PATTERNS

- Bare `except:` everywhere — accepted pattern, do not add new ones
- Print-based logging — no logger module used
- Global counters mutated across module boundaries (`COUNTERS` dict)
- Legacy Python 2 file `sortHDRfiles (cleaner).py` still in tree
