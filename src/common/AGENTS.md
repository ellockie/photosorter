# src/common — Shared Logic

> **Target archive layout is defined by `../../ARCHIVE_STANDARD.md`** (v0.8, draft,
> not enforced). `get_file_name()` and `create_date_folder()` here write names the
> standard describes (§1, §2, §5) — this is the legacy CLI half of the pipeline, so
> its forms are the *historical* ones the standard still reads (N5) but no longer
> prescribes writing.

## OVERVIEW

Core logic layer: EXIF extraction, file renaming, path building, folder creation, duplicate detection. Imported by all major modules. ~830 lines in `common.py`.

## WHERE TO LOOK

| Function | File | Role |
|----------|------|------|
| `extract_data_from_exif_file_and_rename_original_image()` | `common.py:192` | Main EXIF extraction entry |
| `extract_basic_info_from_EXIF()` | `common.py:309` | Reads camera model, datetime, aperture, exposure, ISO, focal length from EXIF |
| `get_camera_symbol()` | `common.py:377` | Maps camera model → short symbol; prompts if unknown |
| `get_file_name()` | `common.py:586` | Builds rename string: `<datetime>__RAW__f<N>__T<N>__L<N>__I<N>__<camera>` |
| `create_date_folder()` | `common.py:472` | Determines date folder based on time with day-division logic |
| `get_the_destination_path()` | `common.py:413` | Resolves destination with duplicate handling |
| `full_path_of()` | `common.py:348` | Path builder: joins root + folder + trailing parts |
| `file_md5()` | `common.py:358` | MD5 hex digest for duplicate detection |
| `COUNTERS` | `globals.py:1` | Mutable dict: FAILS, DUPLICATES, PROBLEMATIC_FILES, etc. |
| `FULL_PATH_SUBFOLDER` | `globals.py:14` | Resolved paths for PROBLEMATIC subfolders |

## CONVENTIONS

- All functions are module-level, no classes
- Yield generators for file iteration (`yield_image_files_from_location`, `yield_exif_files_from_location`)
- ExifTool output parsed line-by-line (not XML/JSON) via `extract_value_of_EXIF_key()`
- Unknown camera models trigger terminal beep + interactive input
- Duplicate files resolved by MD5 comparison before overwrite/remove

## ANTI-PATTERNS

- Bare `except:` in `get_the_destination_path()` and `move_image_to_problematic_folder()`
- `file_info_array` global list mutated across calls
- No error returns — counter-based failure tracking instead
