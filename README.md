# photosorter

Windows-only photo and video sorting pipeline for moving media out of Dropbox Camera Uploads, generating EXIF sidecars, renaming files from metadata, and organising the final archive by year, month, and event folder.

The project is currently in a transition period. The default batch file still runs the legacy command-line sorter for safety, while a new pluggable pipeline and local dashboard are being introduced under the OpenSpec change `pluggable-pipeline-architecture`.

## Archive Standard

**[`ARCHIVE_STANDARD.md`](ARCHIVE_STANDARD.md) defines the target shape of the
archive on disk** — the year/month/event path, the dated-folder and file naming
grammars, container marking, the closed set of `__` subfolders, and sidecar
behaviour. It is written to be handed to third-party tools (group renamers,
viewers, dedupers) as the contract they implement against: §8 is a machine-readable
YAML block carrying every regex, folder name and marker.

Read it before writing any stage or tool that creates, moves, renames or scans
archive folders. The sections below describe what the current code does; where the
two disagree, the standard is the intent and the code is the gap.

Currently **v0.1, draft, not enforced anywhere** — and existing tools are not
assumed compliant.

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

The rules are stated in [`ARCHIVE_STANDARD.md`](ARCHIVE_STANDARD.md) §2 (folders)
and §5 (files); what follows is how the current code writes them.

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

That placeholder is the legacy form. A folder awaiting review now carries the
`__TO_SPLIT__` marker and its counts instead — see
[Event-folder counts](#event-folder-counts).

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

The set above is what `DEFAULT_TAXONOMY` holds today.
[`ARCHIVE_STANDARD.md`](ARCHIVE_STANDARD.md) §4 is the list under review, and it
differs — `__VIDEOS_TO_RENAME` is proposed, `__VIDEOS` and `__EXTRACTED` are absent
from the proposal. The open questions are listed there; until they are settled the
code keeps the set above.

The standard also proposes a `__CONTAINER__` marker (§3) on any dated folder that
holds dated child folders, so a container is distinguishable from a leaf by regex.
Nothing writes it yet.

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

### Empty folders are parked, not grouped

Opening the grouper on a folder with nothing in it costs the reviewer a window
to read and close, and teaches them to click through the GUI without looking —
the one habit this stage cannot afford. So before anything is opened, a day
folder holding **no files anywhere in its subtree** is moved into
`__EMPTY_SUBFOLDERS`, a sibling created on first use:

```text
2026  07. July    __EMPTY_SUBFOLDERS        2026-07-19_(Sun) - 1. ######
    2026-07-20_(Mon) - __TO_SPLIT__(i=42)
```

The day leaves the month folder's working list without leaving the month, and
the folder itself is kept — its name still records which day it was and what it
held. `__EMPTY_SUBFOLDERS` carries no day prefix, so the grouping review neither
matches it nor descends into it, and a parked folder cannot hold up a run.

Empty means empty *all the way down*. A day whose media was routed into
`__VIDEOS` or `__RAW` is not empty — it is a day the GUI happens not to show,
which is a different thing and is skipped where it stands. Nothing is ever
overwritten: a name already parked means an earlier run put one there, so the
folder is left in place and the clash is logged.

### Dated-name convention

One canonical form is written everywhere — note the **double** underscore before
the time, matching the screenshot grouper:

```
2026-08-14_(Fri)__15.32.01__f1.7__T1_180__L23.0.eq__I12__SG23U.jpg
```

Weekday abbreviations are fixed English, never locale-dependent. Earlier forms
(`_(Fri)_15.32.01` and `__15.32.01`) are still read, so an existing archive keeps
working and its sidecars keep matching their images.

### Event-folder counts

An event folder still awaiting review carries the `__TO_SPLIT__` marker and a
bracket of counts, so the size of the job is visible in Explorer before the
grouper is opened:

```text
2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=79_v=3)
```

| Letter | Counts | Written when |
| --- | --- | --- |
| `i` | top-level images | there are any |
| `v` | top-level videos | there are any |
| `e` | `._exif` sidecars in the whole folder | the count does not match the media in that folder |
| `s` | non-sidecar files below the top level | there are any |
| `f` | subfolders in the whole subtree | the folder is `EMPTY` and has any |

`i` and `v` are the review job. The grouper GUI shows the top level only, so
they state exactly what it will put in front of you. A day whose every file was
routed into a subfolder — a video-only day, everything in `__VIDEOS` — is
counted from the subtree instead, rather than reported as empty.

`e` and `s` are audit markers. They are written only by the maintenance tool
below, and only when something does not add up:

```text
2026-07-01_(Wed)__13.07.11 - __TO_SPLIT__(i=129_s=6)   6 files sit in subfolders
2026-07-25_(Sat) - __TO_SPLIT__(e=7)                   7 sidecars, and no media
```

One `._exif` per media file is the norm, so `e` appears only when that breaks:
`e=7` beside no images means the day's photos left without their sidecars, and
`e=0` beside a folder full of images means the sidecars are gone. `s` means the
grouper will not show you everything the folder holds.

A folder holding **no files at all**, however deep you look, says so instead of
counting — there is nothing there to count:

```text
2026-07-19_(Sun)__00.00.00 - __TO_SPLIT__(EMPTY)        nothing left
2026-06-09_(Tue)__00.00.00 - __TO_SPLIT__(f=3_EMPTY)    three hollow subfolders
2026-08-17_(Mon)__11.46.15 - __TO_SPLIT__(EMPTY)        emptied after it was named
```

`f` is every subfolder in the subtree, not just the direct ones; they are all
empty by definition.

An emptied folder holds nothing to read a capture time off, and a dated prefix
without a time is the one shape the convention would rather not see — so
`00.00.00` stands in. It is a real, sortable time that no camera is likely to
have produced, sitting next to the `EMPTY` that says why it is there. A folder
emptied *after* it was named keeps its real time: a genuine capture beats a
placeholder. Dropping the counts is what makes two emptied folders on
one day land on the same name, so the second and later take `_2`, `_3` … in the
order Explorer sorts them. That numbering is the only place this tool resolves
a collision rather than reporting one — everywhere else, two folders claiming
one name is a real anomaly.

The grammar lives in `src/pipeline_stages/grouping_names.py` and nowhere else.
The live grouping stage writes `i`/`v` alone; so does the screenshot grouper,
which rebuilds the bracket from scratch when it touches a folder and will
therefore drop any `e`/`s` it finds. They come back on the next tool run.

## Maintenance Tools

### Canonicalising an existing archive

`tools/canonicalise_timestamp_names.py` rewrites names an earlier version of the
pipeline — or the screenshot grouper — left in a different shape, so an existing
archive converges on the conventions above.

```powershell
python tools/canonicalise_timestamp_names.py                       # dry run over <root_folder>\<year>
python tools/canonicalise_timestamp_names.py "c:\__PHOTOS\2026" --apply
python tools/canonicalise_timestamp_names.py --undo <journal> --apply
```

**Nothing is renamed without `--apply`.** The default run is a report; with
`--apply` every rename is appended to a journal that `--undo` replays backwards.
Exit codes: `0` nothing left to do, `1` changes pending or failures, `2` error.

It does two things:

- **Timestamps.** Every dated name converges on the canonical form:
  `_(Fri)_15.32.01`, `__15.32.01`, and a stale or lower-case weekday all become
  `_(Fri)__15.32.01`. Only the timestamp span is touched — markers, camera
  symbols, exposure suffixes and capitalisation survive byte for byte. A name
  claiming a date that cannot exist (`2026-02-31`) is reported, never invented.
- **Event folders.** A legacy `- 1. ######` placeholder becomes the
  `__TO_SPLIT__` marker, the dated prefix gains the time of the folder's
  earliest file, and the counts are rebuilt from what is on disk now with the
  `e`/`s` audit markers above. `--skip-placeholders` turns this half off and
  rewrites timestamps only.

Only the *time* is taken from the earliest file. The date stays as
folder-sorting wrote it, since a shot after midnight but before the day boundary
belongs to the previous day's folder, and rewriting the date would move the day
out from under its month folder too.

A folder whose media has gone — the grouper moved the images out, `__EXIF`
stayed put — is dated from its earliest **sidecar** instead. A `._exif` is named
after the image it described, so it carries that image's capture time:

```text
2026-07-25_(Sat) - __TO_SPLIT__(e=7)   ->   2026-07-25_(Sat)__06.19.06 - __TO_SPLIT__(e=7)
```

Without that fallback such a folder keeps a bare date, and two of them on one
day collide on a single name — which is the whole reason the time is there.
Media always wins where there is any; the sidecars are only fallen back to.

**Every question is asked of the whole subtree.** The earliest capture, the
file and folder counts, whether a folder is empty at all — none of them stop at
the top level. This is where the time and the counts part ways: `i`/`v` state
the review job, which is the top level alone, while the time states when the
day began, wherever the earliest file happens to sit. A video routed into
`__VIDEOS` at 09.59 dates the day even with nothing above it before noon.

An existing time is still never revised — a prefix that already carries one is
left as found rather than second-guessed. Only a folder with no time gets one.

A folder whose tail carries something a human wrote after the marker keeps that
tail verbatim and only gains the time.

A folder somebody has named gets the same dated half and nothing else. The
label is their writing and is kept verbatim — only the *first* ` - ` separates
it, so `- Lens tests - flowers` survives whole — and it never gains counts, a
bracket being the mark of a folder still awaiting review. The one thing it does
shed is the legacy number folder-sorting left in front of it:

```text
2018-10-14_(Sun) - 1. Natsumi Kuroda in Burnham Beeches
2018-10-14_(Sun)__17.28.25 - Natsumi Kuroda in Burnham Beeches
```

That `1.` never counted anything — it was hard-coded into the `- 1. ######`
suffix, and a human naming the folder typed over the `######` and left it
standing.

#### Reading the report

Each rename prints as two lines whose prefixes are the same width, so the paths
land in one column, closed by a faint rule. Everything the two paths share keeps
the outcome's own colour; past the point where they part, the text going away is
white and the text replacing it is red.

```text
        c:\__PHOTOS\2026\07. July\2026-07-01_(Wed)__13.07.11 - __TO_SPLIT__(i=129)
    ->  c:\__PHOTOS\2026\07. July\2026-07-01_(Wed)__13.07.11 - __TO_SPLIT__(i=129_s=6)
        --------------------------------------------------------------------------------
```

`--no-colour` drops the escape codes; `--quiet` drops the per-rename lines,
leaving the summary.

#### On a network target

A mapped drive letter is a per-session alias that can be remapped between the
moment a target is checked and the moment a file is renamed. The tool therefore
resolves a mapped letter to its UNC once, up front, and works on the UNC
(`--keep-drive-letter` opts out). It never follows reparse points — junctions,
symlinks, mount points — and reports each one it refused; it re-checks that
every directory it is about to scan is still inside the resolved root; it
renames with `os.rename`, never `os.replace`, so an unexpected collision fails
loudly instead of destroying the file it lands on; and it retries transient SMB
failures instead of aborting a tree half-renamed. It handles no credentials of
any kind — authenticating the share is the operating system's job.

### Restructuring an existing archive

`_restructure_archive.bat` at the repo root — or `_restructure_archive.ps1`, the
same thing for PowerShell — is the front door for restructuring work, over
`tools/restructure_archive.py`. It runs the five steps that turn a
tree written by an older Photosorter, an older grouper or a third-party tool
into the shape [`ARCHIVE_STANDARD.md`](ARCHIVE_STANDARD.md) describes, in the one
order that makes sense, over one target, under one set of safety rules:

| Step | What it does |
| --- | --- |
| 1 | Canonicalise names (the tool above) |
| 2 | Open the grouper GUI on every `__TO_SPLIT__` folder, one at a time |
| 3 | Canonicalise names again |
| 4 | Check compliance with the archive standard — **not implemented** |
| 5 | Fix compliance with the archive standard — **not implemented** |

```powershell
_restructure_archive.bat                                        # dry run over <root_folder>\<year>
_restructure_archive.bat --apply
_restructure_archive.bat "d:\__PHOTOS_BACKUP" --year 2024 --apply
_restructure_archive.bat "\\NAS\PhotoBackup" --year 2024 --apply
_restructure_archive.bat --list-to-split                        # just the folders step 2 would open
_restructure_archive.bat --steps 2 --apply                      # only the grouping pass
```

The `.ps1` takes the same arguments and returns the same exit codes, and adds
`-NoPause`:

```powershell
.\_restructure_archive.ps1 "d:\__PHOTOS_BACKUP" --year 2024 --apply
.\_restructure_archive.ps1 --steps 1,3 -NoPause
```

Two things it does that the `.bat` does not have to. PowerShell splits an
unquoted `1,3` into an array *before* the script sees it, and splatting an array
to a native command passes each element separately — so `--steps 1,3` would
arrive as `--steps 1` plus a stray `3`, which argparse would quietly take for the
target path. The script joins it back up, so both shells behave the same. And it
pauses at the end only when there is a console to press a key at, so a scheduled
or piped run cannot hang waiting for one.

Double-clicking a `.ps1` opens it in an editor rather than running it, and an
unsigned script is blocked under the default execution policy, so a shortcut
wants the long form:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<path>\_restructure_archive.ps1" --apply
```

**Nothing is changed without `--apply`.** Exit codes match the canonicaliser's:
`0` nothing left to do, `1` changes pending or failures, `2` error. An applied
run journals what each step did and which folders were opened; the canonicaliser
writes its own rename journal per year tree, and `--undo` on *that* tool replays
those renames backwards. Step 2 is not undoable — what the GUI does inside a
folder is your own work.

**Why canonicalise twice.** Step 1 is what makes step 2 possible: the grouper is
opened on folders carrying the `__TO_SPLIT__` marker, and a legacy `- 1. ######`
day does not carry it until the canonicaliser has rewritten the tail. Step 3 is
what makes step 2 durable: the grouper writes on its own convention and rebuilds
a count bracket from scratch every time it touches a folder, dropping the `e`/`s`
audit markers and stamping new sub-event folders in whatever shape it favours.
The second pass folds all of that back onto the canonical form.

**Steps 4 and 5 are placeholders.** The standard is v0.1, a draft, enforced by
nothing — its `S4` subfolder set and its `T8` "defined more than once" list carry
open questions whose answers change what "compliant" means. Both steps announce
themselves and do nothing; the plumbing is there so implementing them is a change
to one function each, against "The fixing tool" in §7 and the machine-readable
definitions in §8.

#### Targets

The default is the canonicaliser's: the year folder under `paths.root_folder`,
chosen with `--year`. Beyond that, anything can be named — a local disk, a UNC
path, a folder deep inside a tree. Naming an **archive root** (a folder holding
year folders) restricts the run to those year trees, because `P1` and §0 put
everything else at a root — `____INGEST_PIPELINE`, `____TO_SORT` — out of scope:
a tool that walked into the ingest pipeline would be renaming files still in
flight.

A target that is neither a year folder, nor inside one, nor holds any is
**refused**, so a mistyped path or a bare drive letter stops before the first
rename rather than after it. `--force-target` overrides that, deliberately
awkwardly.

#### On a network target

Everything the canonicaliser does (above), plus: the run asks for a typed
confirmation before writing to a network location, and refuses to apply at all
with no terminal to ask at unless `--yes` says the run is unattended. Every
folder is re-checked immediately before the GUI is opened on it — still inside
the resolved root, still not a reparse point, still under that name, since the
previous window in the same batch may have split it away. Folder names reach the
GUI as an argument vector, never through a shell.

The grouper itself will **not be run off the network**: if either
`screenshot_grouping.python` or `.project_path` sits on a share or a mapped
drive the run stops, because an executable on a share is an executable somebody
else can replace between one folder and the next. `--allow-network-tool`
overrides it.

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
