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

Currently **v1.0, settled, partially enforced by the restructure tool** — and
existing tools are not assumed compliant. Settled means the rules are decided,
not that the code implements them: §7's fixing tool is still to be built, and
steps 7 and 8 of the restructure tool are the placeholders waiting for it.

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

Final event folders use a standardized `__` prefix subfolder set: `__TO_SHARE`,
`__3D`, `___OTHER`, `__DUPLICATES`, `__EDITED`, `__EXIF`, `__EXPORTED`,
`__GEOLOCATIONS`, `__HASHES`, `__PANORAMAS`, `__PEOPLE`, `__PREVIEWS`, `__RAW`,
`__RAW_EXTRACTED_JPGS`, `__RESIZED`, `__SHARED`, `__VIDEOS_EXTRACTED`,
`__VIDEOS_TO_RENAME`. The new pipeline writes `__EXIF`/`__RAW`; the
`##   EXIFs   ##` / `##   RAWs   ##` names remain only in legacy CLI output.

**The set has exactly one definition** — `DEFAULT_TAXONOMY` in
[`src/pipeline_stages/taxonomy.py`](src/pipeline_stages/taxonomy.py), matching
[`ARCHIVE_STANDARD.md`](ARCHIVE_STANDARD.md) §4. `default_config()` deliberately
writes no `taxonomy` block, so there is no second copy to keep in step and
`save_config()` cannot bake a stale one into a config file; a config may still
override an individual key. `tests/test_taxonomy_single_source.py` holds the code
and the standard equal, and fails if any stage hardcodes a folder name.

**Videos are not in the taxonomy.** A video that can be dated from its own
metadata is a representative and sits at the top level of the event folder beside
the stills (§5.1 V1), its sidecar in the same `__EXIF`. `__VIDEOS` and
`__EXTRACTED_VIDEOS` (and `__EXTRACTED`, now `__RAW_EXTRACTED_JPGS`) were the
earlier arrangement: they live on in
`LEGACY_TAXONOMY`, recognised case-insensitively when read so an existing archive
is not reported as malformed, and written by nothing (S5). Reconciliation in
`tools/restructure_archive.py` now drains legacy `__VIDEOS`: dated videos move
up beside images, intrinsic ExifTool metadata names an unstamped video, and a
genuinely undatable one is tagged and moved to `__VIDEOS_TO_RENAME`. Sidecars
and previews follow; the verified-empty legacy folder is parked under the
month's `__EMPTY_SUBFOLDERS` (V12/L4).

**Groups (§3) are written.** A dated folder holding dated child folders carries
`____GROUP____` as the first element of its tail and states the whole span it
covers in its prefix -- start stamp, then `#` and the end. The end says all of
the date or none of it: the time alone when the span closes the day it opened,
and the whole canonical stamp when it crosses a day.

    2026-08-20_(Thu)__09.14.02#2026-08-27_(Thu)__18.31.50 - ____GROUP____(d=7) - Norway
    2026-08-14_(Fri)__13.40.23#17.47.04 - ____GROUP____(d=3) - Kajaki z Marco

Both stamps and the `d` count are the tool's, rebuilt from the subtree on every
run; the description after them is the only part a person owns -- and a group
nobody has named carries `__TO_LABEL__` there until somebody does, or until its
children agree on a name of their own (C16). Step 6 of
`tools/restructure_archive.py` maintains them, adds the marker to a folder that
has gained dated children and takes it off one that has lost its last. What it
holds (C3) is only reported: moving media down into a child of its own is C4,
which since v1.0 is a settled action of the fixing tool — under `--apply`, after
a prompt — and not of step 6. A group may hold one `__GEOLOCATIONS` (C3a), for a
track spanning more days than any single child, and that is the only taxonomy
subfolder it may hold. `__CONTAINER__` was the v0.8 spelling; nothing ever wrote
one, and step 6 converts any that a person typed.

The standard proposes more that no code writes yet:

- **the interactive cleanup for undatable videos** (V9/V11) — automatic
  migration now tags an undatable video `__TO_RENAME__<original name>` **and**
  moves it to `__VIDEOS_TO_RENAME` with its companions. The reserved `__EST__`
  interpolation marker is not written; choosing neighbouring anchors remains
  unresolved. The future cleanup UI still needs to resolve the `w=N` backlog;
- **`__PREVIEWS`** (X6–X9) for camera thumbnails and proxies. `.thm` and `.lrv`
  are classified as previews rather than media, so a thumbnail no longer counts
  as an image or can be picked as a representative. Routing them into the folder
  is implemented in `place_companions` and run by the restructure tool, but
  nothing _writes_ one there during a live ingest yet.

### Shooting modes

Three ways a shot arrives, each announced by the representative's own name, so
the top level alone tells you whether there is a RAW worth developing instead:

| Mode      | Top level            | Meaning                                           |
| --------- | -------------------- | ------------------------------------------------- |
| JPG only  | `…__SG23U.jpg`       | no suffix — what the camera wrote is all there is |
| JPG + RAW | `…__6D_HAS_RAW.jpg`  | straight from the camera; a RAW sits in `__RAW`   |
| RAW only  | `…__6D_FROM_RAW.jpg` | extracted from the RAW, which had no camera JPG   |

### Author markers

The camera symbol says _what_ took a shot. When the archive holds media from more
than one person — a partner's camera at the same event — the name also says _who_:

```text
…__I200__C6D.jpg        the archive owner's — no marker, so nothing already filed changes
…__I200__C6D__@AK.jpg   someone else's
```

The mechanism mirrors camera symbols: a `author_symbols` table in `config.json`
maps a person's name to a short symbol, and the same table serves both sources of
authorship — which folder a batch was merged from, and EXIF `Artist` where the
camera recorded it. There is no built-in table, since camera models are universal
and the people in one archive are not. A name the table does not know writes **no
marker at all** and is reported, rather than falling back to the owner and filing
someone else's photo as yours. The `@` sigil makes the token self-identifying, so
a third-party tool can tell an author from a camera symbol without the table.

`_HAS_*` names a sibling elsewhere, `_FROM_*` names this file's own provenance,
and the two RAW suffixes never combine — `_FROM_RAW` already implies a RAW.
A better edit under `__EDITED` adds `_HAS_EDIT` last. The earlier `_RAW`, `_EXT`
and `_EDT` are still read but never written: `_RAW` on a camera JPG read as _this
is a RAW_, the sense `RAW__` carries inside a filename, when it meant _a RAW
exists_.

**JPGs are not extracted when the camera already wrote one.** The camera JPG is
the better representative and the RAW is preserved untouched; an automatic twin
would double the JPEG count for the commonest mode while adding nothing the RAW
does not already hold. An extraction that does show up beside a camera JPG — from
a converter run — is an alternate and goes to `__RAW_EXTRACTED_JPGS`.

Every extracted JPEG gets **its own** `._exif` (the `Extracted Sidecars` stage,
between the last converter and folder sorting) rather than sharing the RAW's,
which describes the RAW's dimensions and type. RAW-only shots are counted and
reported at the end of folder sorting, including any with no extraction at all —
those have no representative image.

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

| Prompt                                   | What it is asking                                                |
| ---------------------------------------- | ---------------------------------------------------------------- |
| `name_collision`                         | Two files claim one name and neither age nor size settles it.    |
| `crw_conversion` / `dpviewer_conversion` | Convert these RAWs before later stages move them.                |
| `raw_conversion`                         | Convert the staged workspace; it is swept the moment you answer. |
| `grouping_review`                        | Event folders from this run are still unnamed.                   |

### Grouping review

Closing the grouper window is not the same as finishing the job. After grouping,
the **Grouping Review** stage lists every folder from this run still carrying
`__TO_SPLIT__`, `__TO_LABEL__`, or the bare `- 1. ######` placeholder, and holds
the run there. Rename them — in the grouper or in Explorer — and press
**Re-scan**; **Continue anyway** fast-forwards past folders you meant to leave
unnamed. Either way the stage then re-scans the archive as it stands _now_, so
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

Empty means empty _all the way down_. A day whose media was routed into
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

| Letter | Counts                                | Written when                                      |
| ------ | ------------------------------------- | ------------------------------------------------- |
| `i`    | top-level images                      | there are any                                     |
| `v`    | top-level videos                      | there are any                                     |
| `e`    | `._exif` sidecars in the whole folder | the count does not match the media in that folder |
| `s`    | non-sidecar files below the top level | there are any                                     |
| `f`    | subfolders in the whole subtree       | the folder is `EMPTY` and has any                 |

`i` and `v` are the review job. The grouper GUI shows the top level only, so
they state exactly what it will put in front of you. A day whose every file was
routed into a subfolder — a video-only day, everything in `__VIDEOS` — is
counted from the subtree instead, rather than reported as empty.

`e`, `c` and `s` are audit markers. They are written only by the maintenance tool
below, and only when something does not add up:

```text
2026-07-01_(Wed)__13.07.11 - __TO_SPLIT__(i=129_s=6)   6 files sit in subfolders
2026-07-25_(Sat) - __TO_SPLIT__(e=7)                   7 sidecars, and no media
2026-07-15_(Wed)__09.12.53 - __TO_SPLIT__(i=1_c=1)     2 sidecars claim one shot
```

One `._exif` per media file is the norm, so `e` appears only when that breaks:
`e=7` beside no images means the day's photos left without their sidecars, and
`e=0` beside a folder full of images means the sidecars are gone. `s` means the
grouper will not show you everything the folder holds.

**`e` counts subjects, not files, and `c` is why.** The useful question is how
many media are _covered_ by a sidecar, not how many `._exif` are lying about — so
`e` counts the distinct subjects the folder's sidecars name, and `c` counts the
files beyond the first for any one of them. Splitting the two is what stops one
fault masking another: two sidecars naming the JPG and none naming the RAW used
to total 2 against 2 media and report nothing at all. That folder now reads
`e=1_c=1` — one subject covered, one file too many — and both faults are visible.

In a folder in order every subject is covered, so `e` is silent and `c` absent —
which is the state [companion placement](#restructuring-an-existing-archive)
leaves behind: it compares the clashing files by checksum, parks the loser, and
`c` goes.

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
emptied _after_ it was named keeps its real time: a genuine capture beats a
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

Only the _time_ is taken from the earliest file. The date stays as
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
label is their writing and is kept verbatim — only the _first_ `-` separates
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

After the summary the tool explains the count bracket — but only the letters it
actually wrote this run, so a run that produced `(i=1_c=1)` explains `i` and `c`
and nothing else:

```text
2 to rename, 0 conflict(s), 0 failure(s), 0 unparseable, 0 refused.

What the counts in those names mean:
  i=  top-level images -- the review job, what a grouper GUI will show
  e=  media covered by a sidecar, counted by subject; shown only when it does not match the media in the subtree
```

The meanings come from `COUNT_MEANINGS` in
[`grouping_names.py`](src/pipeline_stages/grouping_names.py), mirroring §8 —
a legend spelled out in the tool would be the second definition that drifts.
`--quiet` suppresses it, and a run where no name gained a bracket prints
nothing.

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

| Step | What it does                                                                             |
| ---- | ---------------------------------------------------------------------------------------- |
| 1    | Canonicalise names (the tool above)                                                      |
| 2    | Reunite companions with their representatives, and sidecars/previews with their subjects |
| 3    | Open the grouper GUI on every `__TO_SPLIT__` folder, one at a time                       |
| 4    | Reunite companions and sidecars again                                                    |
| 5    | Canonicalise names again                                                                 |
| 6    | Check compliance with the archive standard — **not implemented**                         |
| 7    | Fix compliance with the archive standard — **not implemented**                           |

```powershell
_restructure_archive.bat                                        # dry run over <root_folder>\<year>
_restructure_archive.bat --apply
_restructure_archive.bat --year ALL                             # every year the root holds
_restructure_archive.bat "d:\__PHOTOS_BACKUP" --year 2024 --apply
_restructure_archive.bat "d:\__PHOTOS_BACKUP" --year ALL --apply
_restructure_archive.bat "\\NAS\PhotoBackup" --year 2024 --apply
_restructure_archive.bat --list-to-split                        # just the folders step 2 would open
_restructure_archive.bat --steps 3 --apply                      # only the grouping pass
_restructure_archive.bat --steps 2,4 --apply                    # only the reconcile passes
```

The `.ps1` takes the same arguments and returns the same exit codes, and adds
`-NoPause`:

```powershell
.\_restructure_archive.ps1 "d:\__PHOTOS_BACKUP" --year 2024 --apply
.\_restructure_archive.ps1 --steps 1,3 -NoPause
```

Two things it does that the `.bat` does not have to. PowerShell splits an
unquoted `1,3` into an array _before_ the script sees it, and splatting an array
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

#### Reading the output

Every step closes with a framed verdict — green when it left nothing to
address, red when it did, naming what it found. The run closes with two frames
and nothing after them: **every issue it gathered**, in full and grouped by
kind, and then the **summary**, with the verdict in a heavy box of its own.
The summary is last on purpose — whichever block is printed last is the one
still on screen when the run ends.

An issue is anything the tool deliberately declined to settle: a folder that
fits no shape in the standard, a junction it would not follow, a companion
whose subject it could not find, a group nobody has named, a step that did not
finish. None of them is fixed for you, and each is listed with the reason it
was left where it is.

The verdict answers _is there anything left for me?_ The exit code answers _did
the tool do its work?_ — and they are not the same question: a run that finds
twenty folders the standard cannot describe did its work perfectly, exits `0`,
and still prints a red banner saying twenty things are waiting.

Every line the tool says itself is tagged `[restructure]` and coloured cyan;
every line it relays from a tool it called — the canonicaliser's rename report,
the grouper's stderr, the matching engine's log, ExifTool's — is neither. The
tag is always the same colour whoever is speaking, so the colour tells you
_who_, while the message keeps the colour its own meaning earned: green for
done, yellow for wants-a-look, red for broken, inside a cyan-tagged line.

Frames are drawn with box characters where the console can encode them and with
`+`/`-` where it cannot, so a legacy code page gets a plainer box rather than a
traceback. Colour goes to a terminal only; `--no-colour` turns it off and leaves
the frames and the tag, because a redirected log needs both as much as a console
does.

**Nothing is changed without `--apply`.** Exit codes match the canonicaliser's:
`0` nothing left to do, `1` changes pending or failures, `2` error. An applied
run journals what each step did and which folders were opened; the canonicaliser
writes its own rename journal per year tree, and `--undo` on _that_ tool replays
those renames backwards. Step 2 is not undoable — what the GUI does inside a
folder is your own work.

**Only the folders worth opening.** Step 3 opens a marked folder only when it has
an image or a video **at its top level**, which is the whole of what the grouper's
thumbnail grid shows. A folder can carry the marker and have nothing for it to do
— an earlier pass already split the day into sub-events, the day's files all sit
in `__VIDEOS` or `__RAW`, or it is one of the hollow folders parked in
`__EMPTY_SUBFOLDERS` that the canonicaliser marks `(EMPTY)`. Opening one of those
puts an empty grid in front of you and waits for you to close it; on a batch of
ninety that is the difference between a job and an afternoon. They are listed
with the reason rather than dropped silently, and `--open-all` opens them anyway.

The count comes off the disk, never off the folder's own name — the canonicaliser
counts the whole subtree when a top level is bare, so a day whose every video was
routed into `__VIDEOS` is named `__TO_SPLIT__(v=3)` while having nothing to show:

```text
2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=3)   [i=3 v=0]   opened
2026-07-17_(Fri)__10.00.00 - __TO_SPLIT__(v=2)   [i=0 v=2]   opened — videos count
2026-07-16_(Thu)__09.00.00 - __TO_SPLIT__(v=3)               passed over — all in __VIDEOS
2026-07-18_(Sat)__00.00.00 - __TO_SPLIT__(f=2_EMPTY)         passed over — nothing anywhere
2026-07-19_(Sun)__06.19.06 - __TO_SPLIT__(e=2)               passed over — sidecars only
```

The same question is asked again immediately before each window opens, because
splitting a day moves its files down into the new sub-event folders: a folder
that had a gridful when the batch was planned can have an empty top level by the
time the batch reaches it.

**Reuniting companions and sidecars (steps 2 and 4).** Six passes, in this
order and no other:

- **`hoist_parking_areas`** — a parking area sits **where dated folders sit**:
  under a month folder, or inside a group beside its dated children (H2). One
  found anywhere else — inside a leaf day, where the legacy-container migration
  used to leave a shell — is merged into the nearest allowed one above it, and
  no further: a sub-event emptied out of a group stays in that group. Name
  collisions gain `_2`, `_3` …; each emptied shell is removed only after it is
  verified to hold nothing at all. One sitting _above_ its level, under a year
  folder, is reported and never pushed down (H7). A parking area is then a
  traversal boundary wherever it sits, so parked days do not re-enter grouping
  or reconciliation.
- **`migrate_legacy_videos`** — every video in a case-variant `__VIDEOS` moves
  up beside images when its filename or intrinsic metadata supplies a time.
  A genuinely undatable one is tagged and routed to `__VIDEOS_TO_RENAME`; an
  ExifTool failure leaves it untouched. Companions follow and the verified-empty
  legacy folder is parked beside the dated folder it sat in (V12/L4).
- **`migrate_legacy_containers`** — `##   EXIFs   ##` becomes `__EXIF` and
  `##   RAWs   ##` becomes `__RAW`. Renamed outright where nothing of that name
  is there yet (one atomic operation that cannot half-finish); where one is,
  each file moves across individually and a collision is settled by checksum. An
  emptied container is parked in the `__EMPTY_SUBFOLDERS` beside its dated
  folder — one level up, since a leaf day is not a level one may sit on — numbered
  `_2`, `_3` … when that name is taken. One with no modern equivalent —
  `old_EXIF`, the three `FILES` holders — is **reported and never touched**.
- **`reconcile_folder`** — a companion left behind in an event folder's taxonomy
  subdir follows the representative the grouper moved into a sibling sub-event.
  Matched on capture time, because the representative has been renamed since.
- **`place_companions`** — **X10 and X13**: a companion goes into the folder
  _directly inside_ the one that holds its subject — an `._exif` into `__EXIF`,
  a `.thm`/`.lrv` into `__PREVIEWS`. Canonical names match directly; historical
  EXIF names without the media extension or with different case match by stem
  and X10 location, then are renamed onto X1 (X1a).
- **`generate_missing_raw_sidecars`** — once tolerant matching has removed the
  false positives, genuinely uncovered RAWs are read by ExifTool and receive a
  canonical sidecar in their own `__RAW\__EXIF` (X14).

The order is the dependency order. Parking is normalized first, then legacy
migration gives everything after it one set of folder names. Reconciliation moves
_subjects_: a RAW still in the wrong event folder has no business having its
sidecar placed beside it yet. Placement settles old names before generation,
so only genuinely absent RAW sidecars are created.

**A sidecar is looked for anywhere in the target** — at any depth, and across
year trees. Placement indexes every tree of the run at once before it moves
anything, so one stranded in a different event folder, or a different year,
still finds its subject. Cross-folder moves are counted and reported separately.

**Only a dated folder holds subjects.** A media file outside one is not a
candidate however plausible its name: the archive's shape is what says which
files are the archive's, and a stray JPG in a working folder must not become the
answer to some sidecar's search. The date format is read **loosely**, as N1
allows — a leading `YYYY-MM-DD` is enough, with or without the weekday and the
time. A day folder that never gained a time is still a day folder.

```text
2026-07-18_(Sat)__17.04.53 - Dive    2026-07-18…__f2.8__GP.mp4
    __EXIF\        …__f2.8__GP.mp4._exif        stays — subject is here
    __PREVIEWS\    …__f2.8__GP.mp4.lrv          was "…__f2.8__GP.LRV" beside it
    __RAW\         …__RAW__f8.0__6D.CR2
    __RAW\__EXIF\  …__RAW__f8.0__6D.CR2._exif   moved down out of __EXIF
```

**Historical companions may arrive in stem form** — the subject's _stem_ plus
the companion extension. That includes `shot._exif` from older extraction and
`GX010042.LRV` beside `GX010042.MP4` — because nothing has ever renamed one. They
are matched by stem and **renamed onto X1 as they move**: `GX010042.MP4.lrv`,
extension lower-cased. X10 location distinguishes a same-stem top-level JPEG
from its RAW; multiple candidates at that same location are left for review.

#### When something already holds the destination name

The two files are compared by **MD5** rather than one being picked:

|               |                                                                                                           |
| ------------- | --------------------------------------------------------------------------------------------------------- |
| **identical** | the incoming copy is redundant — parked as `<name>_DUPE_<md5>_<n>` (F4)                                   |
| **different** | one is wrong and which is not knowable here — parked as `<name>_DIFFERS_<md5>_<n>` and counted separately |

Both land in `<year>\__DUPLICATES`, one per year tree, chosen from the _subject's_
tree so a multi-year run does not pool them. **Nothing is overwritten and nothing
is deleted** (T1, T2), and the parking folder is excluded from the next run's
index so its contents are not re-reported as orphans.

> `__DUPLICATES` under a _year_ is the standard's own rule since v1.0 — S7,
> with P6 admitting it beside the month folders — rather than an extension this
> tool was making on its own. The in-event `__DUPLICATES` keeps its separate
> job, and nothing migrates between the two. Empty legacy containers park in
> the `__EMPTY_SUBFOLDERS` beside their dated folder under H2/L4.

A companion whose subject is nowhere in the target is **left exactly where it
is** and reported (X3). The pass also counts the media that have **no sidecar at
all** (X4).

**Folders that fit no shape are reported at the end, in red.** Anything that is
neither a dated folder, nor an allowed subfolder, nor a holding area, nor a
recognised legacy container is gathered as the run goes and printed after the
summary. A structural problem noticed halfway through a rename report scrolls
past; these are the one part of the output somebody has to act on by hand.
Reported, never fixed.

```text
NON-COMPLIANT FOLDERS  (2) -- reported, not touched
  …6. July\Random Junk Folder
      below a month folder but carries no date (N1) and is not a subfolder
  …6-07-15_(Wed)__09.12.53 - Lens tests\##   UNSUPPORTED EXTENSIONS   ##
      legacy container with no modern equivalent; its contents are a decision for a person
```

**A dry run does each thing once.** Steps 4 and 5 repeat 2 and 1 to clean up
after the grouper; in a dry run the grouper never opens, so nothing has changed
between the passes and the second would print the first's report word for word.
Those are skipped, with a line saying why. Asked for on their own (`--steps 5`)
they still run.

**Why canonicalise twice.** Step 1 is what makes step 3 possible: the grouper is
opened on folders carrying the `__TO_SPLIT__` marker, and a legacy `- 1. ######`
day does not carry it until the canonicaliser has rewritten the tail. Step 5 is
what makes steps 3 and 4 durable: the grouper writes on its own convention and
rebuilds a count bracket from scratch every time it touches a folder, dropping
the `e`/`s` audit markers and stamping new sub-event folders in whatever shape it
favours — and step 4 then moves files between folders, changing those counts
again. Running the canonicaliser last folds all of it back onto the canonical
form and re-derives the audit markers from what is finally on disk.

**Steps 7 and 8 are placeholders.** The standard is v1.0 and settled, but only
partly enforced: what is missing is the tool, not the decisions. Both steps
announce themselves and do nothing; the plumbing is there so implementing them
is a change to one function each, against "The fixing tool" in §7 and the
machine-readable definitions in §8. The two obligations to build first are the
ones v1.0 settled and step 6 already reports — gathering loose media out of a
group (C4) and moving a group whose start crossed into another month folder
(C12) — both writing only under `--apply` and only after a prompt.

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

`--year ALL` reads the root for the years it actually holds and runs each of
them as a run of its own — its own journal, its own summary — oldest first,
closing with one frame covering the lot. Nothing needs listing or keeping up to
date: a gap year costs nothing and a year added since the last run is picked up
without being named. It differs from naming the root, which is a *single* run
over every year tree at once: a year is what every step is scoped to and what
the canonicaliser journals against, so a year per run is what leaves a per-year
record to undo. A network root is confirmed once, up front, rather than once
per year, and a year that stops does not stop the years after it.

Each year's journals go to that year's own `__LOGS` — `<ROOT>\2024\__LOGS\` (`J1`)
— named `_restructure_journal_2024_<stamp>.jsonl` and `_rename_journal_2024_<stamp>.jsonl`.
Pooling them one level up would interleave two years in the same second, since
the stamp resolves no finer, and `--undo` would then replay one year's renames
while reverting another's.

`__LOGS` is therefore the one child a year folder may have besides its month
folders and `__DUPLICATES` (`P6`). That works only because **every walk skips it
by name** (`J2`) — by name and not by path, since a dry run writes no journal and
so has no path to skip. Without that, a journal outliving its run would be
renamed, parked, counted or reported on every later pass.

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
