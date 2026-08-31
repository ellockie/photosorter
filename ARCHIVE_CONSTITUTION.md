# Archive Constitution

**Status: DRAFT — under review. Nothing in this document is enforced yet.**

The rules below describe the **photo + video archive on disk** — not the code that
writes it. They are the contract every stage, tool and agent is expected to honour
once the draft is accepted. Until then this file is the proposal being reviewed;
no stage refuses a run, and no tool rewrites anything, because of it.

Sections marked **[OPEN]** are questions for the reviewer, not settled rules. They
are places where this draft and the current code disagree, or where the intent is
not yet unambiguous.

---

## Article 0 — What this governs

The archive is everything under the **archive root** (`paths.root_folder`,
currently `c:\__PHOTOS`, overridable per run).

Within that root, this constitution governs **year trees only** — a top-level
folder whose name is exactly four digits (`2018`, `2026`), and everything beneath
it.

Anything else at the root is a working area, an ingest staging area or historical
residue, and is **out of scope**. Present on the real archive today:

| Root entry | What it is |
| --- | --- |
| `<YYYY>` | A year tree. Governed by this document. |
| `____INGEST_PIPELINE` | New pipeline working folder (`INBOX`, `READY`, `.TMP`). Transient. |
| `____TO_SORT` | Legacy working folder (`____UNSORTED`, `__READY`, `__PROBLEMATIC`). Transient. |
| `__PROCESSED` | **[OPEN]** Not referenced anywhere in the code. Purpose? |
| `_Innych` | **[OPEN]** Not referenced anywhere in the code. Purpose? |

A fixing tool MUST NOT descend into an out-of-scope root entry, and MUST NOT
report its contents as violations.

---

## Article 1 — The canonical path

Every media file in the archive lives at:

```text
ROOT / <YYYY> / <NN>. <Month> / <dated folder> [ / <dated folder> ... ] [ / <__SUBFOLDER> ]
```

Concretely:

```text
c:\__PHOTOS\2026\07. July\2026-07-15_(Wed)__08.14.02 - Sopot weekend\
```

1. **Year** — exactly four digits. Nothing else at that level.
2. **Month** — `NN. MonthName`, zero-padded number, then a dot, a space, and the
   fixed English month name: `01. January` … `12. December`. Fixed English, never
   locale-derived — a Polish-locale Windows must not start writing `07. lipiec`.
3. **Dated folder** — an event folder or a nested sub-event folder (Article 2).
4. Below a dated folder: further dated folders (Article 3) and/or allowed
   `__`-prefixed subfolders (Article 4). Nothing else.

The year and month a folder sits under MUST agree with the date in its own name,
after the day-boundary shift of Article 2.5.

**[OPEN]** The request spelled the month level as `<NN>. <MM>`. This draft reads
that as *number + month name* (`07. July`), which is what the code writes
(`MONTH_FOLDERS`) and what the archive holds. Confirm — or say if `<MM>` meant the
numeric month (`07. 07`).

---

## Article 2 — Naming a dated folder

A dated folder name is a **dated prefix**, optionally followed by a **tail**.

### 2.1 The dated prefix

```text
YYYY-MM-DD_(Ddd)__HH.MM.SS        canonical — note the DOUBLE underscore
YYYY-MM-DD_(Ddd)                  date only; acceptable, but a time is preferred
```

* Weekday abbreviations are the fixed English three-letter set
  (`Mon Tue Wed Thu Fri Sat Sun`), never `strftime("%a")`.
* The weekday is **decorative**. A stale or wrong weekday never invalidates a
  folder; it is corrected, not rejected.
* The time is the capture time of the folder's earliest file — its earliest media
  where there is any, otherwise its earliest `._exif` sidecar.
* Two folders on the same day must not share a name. The time is what separates
  them, which is why a date-only prefix is tolerated but not preferred.

Historical prefix forms are still **read**, so an existing archive keeps working:

```text
YYYY-MM-DD_(Ddd)_HH.MM.SS         single underscore (earlier Photosorter)
YYYY-MM-DD__HH.MM.SS              no weekday (legacy grouper)
```

They are legal to encounter and should converge on the canonical form; they are
not legal to newly write.

### 2.2 The tail — a named folder

```text
2026-07-15_(Wed)__08.14.02 - Sopot weekend
```

` - ` (space hyphen space) then a human description. A folder with a description
has been named by a person and is **finished**. No tool rewrites its tail.

### 2.3 The tail — awaiting review

```text
2026-07-15_(Wed)__08.14.02 - __TO_SPLIT__(i=79_v=3)
2026-07-15_(Wed)__08.14.02 - __TO_LABEL__
```

`__TO_SPLIT__` means the day still has to be split into sub-events; `__TO_LABEL__`
means it still has to be described. The count bracket after `__TO_SPLIT__` uses the
letters `i` (top-level images), `v` (top-level videos), `e` (sidecars in the whole
tree, written only when the count does not match the media), `s` (non-sidecar files
below the top level), in that order. Full semantics live in
`src/pipeline_stages/grouping_names.py` and are documented in the README.

### 2.4 The tail — legacy placeholder

```text
2026-07-15_(Wed) - 1. ######
```

What legacy folder-sorting wrote. Recognised, converted to `__TO_SPLIT__` by the
maintenance tool, never newly written.

### 2.5 The day boundary

A shot taken at or before the configured day boundary (`legacy.day_boundary_time`,
currently `04.44.44`) belongs to the **previous** day's folder. A night that runs
past midnight is one event, not two.

A consequence a fixing tool must respect: a folder's date may legitimately be one
day earlier than the timestamps of some of its files. **Only the time in a dated
prefix may ever be corrected from folder contents — never the date**, because
rewriting the date would also move the folder out from under its month folder.

---

## Article 3 — Nesting

A dated folder MAY contain further dated folders, to any depth:

```text
2026-07-15_(Wed)__08.14.02 - Sopot weekend\
    2026-07-15_(Wed)__08.14.02 - morning beach\
    2026-07-15_(Wed)__14.02.55 - pier\
        2026-07-15_(Wed)__14.31.09 - the gulls\
    __EXIF\
```

Rules:

1. Every folder at every level below the month folder MUST be either a dated
   folder (Article 2) or an allowed subfolder (Article 4). There is no third kind.
2. A nested folder's date MUST fall inside its parent's day, ±1 day. A sub-event
   split near the day boundary can legitimately land on the neighbouring date;
   anything further apart is a violation.
3. Every level of nesting carries its own taxonomy subfolders. Companions follow
   their representative down into the sub-event folder's own `__RAW`, `__EXIF`, …
4. Depth is unlimited by rule. In practice two levels (day → sub-event) is the
   norm and three is rare.

---

## Article 4 — Allowed subfolders

Inside a dated folder, exactly these `__`-prefixed subfolders are permitted. All
are **optional** — a folder is not required to have any of them:

| Folder | Holds |
| --- | --- |
| `__2_SHARE` | Selected for sharing. Curated by hand. |
| `__3D` | Stereo / 3D captures (MPO and friends). Curated by hand. |
| `___OTHER` | Anything that fits nowhere else. **Three** leading underscores. Curated by hand. |
| `__DUPLICATES` | Burst discards, unused brackets, accidental and low-resolution duplicates, collision losers. |
| `__EDITED` | Non-destructive edits and masters — `.xmp`, `.psd`, high-bit `.tif`. |
| `__EXIF` | `._exif` sidecars and JSON camera logs. |
| `__EXPORTED` | Full-resolution exports for print/archive. |
| `__EXTRACTED_VIDEOS` | Video extracted from other media. |
| `__GEOLOCATIONS` | `.gpx` tracks and other geodata for the event. |
| `__HASHES` | Content hashes / integrity records. |
| `__PANORAMAS` | Panorama sources and stitches. Curated by hand. |
| `__PEOPLE` | Per-person crops/selections. Curated by hand. |
| `__RAW` | RAW originals, untouched and unmodified. |
| `__RESIZED` | Downscaled derivatives for web, social, email. |
| `__SHARED` | Already shared. Curated by hand. |
| `__VIDEOS_TO_RENAME` | Videos still carrying a non-canonical name. |

**Any other subfolder is a violation**, with one exception: a nested dated folder
(Article 3) is not a violation, it is structure.

Rules:

1. The set is **closed**. A new kind of artifact means amending this document and
   the central taxonomy, not inventing a folder name in a stage.
2. Taxonomy folders do not nest inside each other. `__RAW\__EXIF\` is a violation.
3. Names come from the central taxonomy (Article 8), never from a string literal
   in a stage module.
4. Folders marked *curated by hand* are recognised and preserved by the pipeline
   but **never populated automatically** (`MANUALLY_CURATED_KEYS` in
   `src/pipeline_stages/taxonomy.py`).

### **[OPEN]** Four disagreements with the current code

The list above is the reviewer's list, transcribed verbatim. It does not match
`DEFAULT_TAXONOMY` in `src/pipeline_stages/taxonomy.py`, and the differences are
not cosmetic:

1. **`__VIDEOS` is missing from the list but is live in the code.** It is where
   the pipeline routes video companions, and both
   `src/pipeline_stages/companion_reconciliation.py` and
   `tools/canonicalise_timestamp_names.py` reason about it by name (a video-only
   day is one whose files all sit in `__VIDEOS`). Dropping it is a breaking
   change; it is likelier that it was simply omitted. **Should `__VIDEOS` be in
   the allowed set?**
2. **`__EXTRACTED` is missing from the list but is live in the code and in the
   spec.** `openspec/.../pipeline-core/spec.md` requires non-representative
   RAW extractions to land there, and `_EXT` on a representative filename
   (Article 6) points at it. **Keep it?**
3. **`__VIDEOS_TO_RENAME` is in the list but appears nowhere in the code.** New
   folder, to be implemented? Or the intended replacement for `__VIDEOS`?
4. **`__2_SHARE` and `__SHARED` both exist.** The draft above reads them as
   *"queued to share"* vs *"already shared"*. Confirm, since the names invite
   being conflated.

Also unaccounted for: **`__EMPTY_SUBFOLDERS`**, referenced in
`tools/canonicalise_timestamp_names.py` as the place emptied day folders are
parked. It is not a taxonomy subfolder — it looks like a holding area. Where does
it live, and which article should cover it?

---

## Article 5 — What sits at the top level of a dated folder

The top level of a dated folder holds **representative images and nothing else**
that is not a folder.

1. **One representative per shot, at most.** Every other version of the same shot
   belongs in a subfolder.
2. A camera-produced image is the preferred representative. For a RAW-only shot,
   one selected extraction may stand in; the other extractions go to
   `__EXTRACTED`.
3. RAW originals, sidecars, edits, exports, resizes and duplicates never sit at
   the top level.
4. **Why it matters:** the top level is what the grouper GUI shows and what the
   `i`/`v` counts describe. A file hidden in a subfolder is a file the reviewer
   never sees — which is exactly what the `s` audit marker exists to announce.

---

## Article 6 — File names

Canonical media name:

```text
YYYY-MM-DD_(Ddd)__HH.MM.SS[__RAW]__f<aperture>__T<exposure>__L<focal>__I<iso>__<CAMERA>[_RAW][_EXT][_EDT].<ext>
```

```text
2026-08-14_(Fri)__15.32.01__f1.7__T1_180__L23.0.eq__I12__SG23U.jpg
2026-08-14_(Fri)__15.32.01__RAW__f8.0__T1_250__L50__I100__6D.CR2
```

* The **leading timestamp** follows Article 2.1 exactly — same grammar, same
  historical forms read, same canonical form written. It is the join key for the
  whole archive: sidecars, RAWs and videos find their representative by it.
* `RAW__` after the timestamp marks a RAW file. RAW extensions are **uppercase**;
  lossy extensions are **lowercase**.
* Trailing **semantic suffixes** on a representative announce what its subfolders
  hold, in this fixed order: `_RAW` (a RAW original exists under `__RAW`), `_EXT`
  (this image was extracted from RAW, not shot), `_EDT` (a better edit exists
  under `__EDITED`). The extension follows all of them.
* Collision suffixes: `_DUPE_<md5>_<n>` for a duplicate, `_LOWRES` for a
  lower-resolution loser.

### Sidecars

A sidecar keeps its subject's full name and appends its own extension:
`shot.jpg._exif`, `clip.mp4._exif`. Two consequences that are rules, not
observations:

1. `Path.suffix` of a sidecar is `._exif`, never the media extension — that is
   what keeps sidecars out of media counts.
2. A sidecar therefore carries its subject's capture time in its own name, which
   is what lets an emptied folder still be dated (Article 2.1).

**One sidecar per media file is the norm.** Any other ratio means a sidecar was
orphaned when its image moved, or an image arrived without one — this is what the
`e` marker reports.

---

## Article 7 — Invariants

Rules that hold everywhere and that any tool touching the archive must not break:

1. **Nothing is deleted.** Reconciliation, fixing and canonicalisation move,
   rename and report. They never remove.
2. **Rename, never replace.** Use `os.rename`, not `os.replace`, so an unexpected
   collision fails loudly instead of destroying the file it lands on.
3. **Report before writing.** A structural tool's default run is a report;
   changes require an explicit `--apply`, and every applied change is journalled
   so it can be replayed backwards.
4. **Never follow reparse points** — junctions, symlinks, mount points. Refuse and
   report each one.
5. **Resolve mapped drives to UNC once, up front.** A drive letter is a
   per-session alias that can be remapped between check and write.
6. **Long paths.** Windows syscalls are capped at `MAX_PATH`; a deep archive tree
   needs the `\\?\` prefix or it silently comes back short.
7. **A folder named by a human is finished.** Its tail is never rewritten.

---

## Article 8 — One definition per rule

Every constant, name and regex in this document has exactly one definition in the
code. A convention defined twice is a convention that will drift, leaving half the
pipeline writing names the other half fails to parse.

### Where the definitions live today

| Concept | Home |
| --- | --- |
| Subfolder taxonomy | `src/pipeline_stages/taxonomy.py` — `DEFAULT_TAXONOMY` |
| Timestamp grammar (files + folder prefixes) | `src/pipeline_stages/stamps.py` |
| Folder tail grammar (`__TO_SPLIT__`, count bracket) | `src/pipeline_stages/grouping_names.py` |
| Month folder names | `src/constants/constants.py` — `MONTH_FOLDERS` |
| Extensions, day boundary, collision suffixes, paths | `config.json` / `src/core.py` `default_config()` |
| Legacy `##   … ##` subfolders | `config.json` `legacy.subfolders` |

`stamps.py` and `grouping_names.py` are deliberately **leaf modules** — they import
nothing from the project, so a maintenance tool can load one by file path without
dragging the whole pipeline (exiftool, dashboard, converters) in behind it.

### **[OPEN]** Where it is defined more than once today

Found while drafting. Listed, not fixed:

1. **The taxonomy is written out twice** — `DEFAULT_TAXONOMY` in
   `src/pipeline_stages/taxonomy.py:3` and again as a literal inside
   `default_config()` at `src/core.py:172`. Two lists that must agree, with
   nothing making them.
2. **`MONTH_FOLDERS` is defined twice** — `src/constants/constants.py:316`
   (legacy CLI) and `src/pipeline_stages/legacy.py:11` (new pipeline).
3. **Four more date regexes exist outside `stamps.py`**:
   `src/folder_sorter.py:29`, `src/organise_date_folders.py:24`,
   `src/retime_archive.py:44`, `src/pipeline_stages/provenance.py:9`. Each parses
   a dated name its own way, and none of them accept the full set of historical
   forms `stamps.py` does.
4. `grouping_names.py:73` duplicates the leading-stamp regex **on purpose** — the
   module docstring explains why (importing `stamps` would pull in the whole
   `pipeline_stages` package `__init__`). This one is a documented, accepted
   exception, not drift — but it does mean the grammar exists in two places, and
   `tests/test_stamps.py` should be the thing that keeps them equal.

---

## Article 9 — The fixing tool

To be implemented. What this document expects of it:

1. **Reports, does not fix, by default.** Dry run is the default; `--apply`
   journals every change; `--undo` replays the journal backwards. This is how
   `tools/canonicalise_timestamp_names.py` already behaves and the pattern to
   follow.
2. **Reports every folder below a month folder that is neither a dated folder nor
   an allowed subfolder** — including anything nested inside a taxonomy subfolder,
   which is always a violation.
3. **Does not report a nested dated folder** as an unknown subfolder (Article 3).
4. **Does not descend into out-of-scope root entries** (Article 0).
5. **Reads the taxonomy and the grammars from their central definitions**
   (Article 8) rather than restating them.
6. **Never guesses a date.** A prefix claiming a date that cannot exist
   (`2026-02-31`) is reported, never invented; only the time half is ever derived
   from folder contents.
7. **Exit codes**, matching the existing tool: `0` nothing to do, `1` changes
   pending or failures, `2` error.

---

## Amending this document

The taxonomy and the naming grammars are load-bearing: an archive of hundreds of
thousands of files is already on disk in this shape. Changing a rule here means
the maintenance tool has to migrate the existing archive to match, so an amendment
is a change to this document **and** a migration, together — never one alone.
