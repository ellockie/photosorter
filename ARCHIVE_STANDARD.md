# Photo & Video Archive Standard

**v0.1 — DRAFT. Under review. Not enforced by any code.**

The target structure of the photo + video archive on disk. It exists to (a) drive
the redesign of the **already-archived** material and (b) serve as the contract
that Photosorter and any third-party tool — group renamers, viewers, dedupers —
implement against. A tool that reads this file and follows §1–§7 will produce
folders and names the rest of the archive can join.

Nothing here is enforced yet. Existing tools are **not** assumed compliant.

**Conformance:** MUST / SHOULD / MAY as in RFC 2119. Every rule has a stable ID
(`P1`, `N3`, …); cite the ID when reporting a violation. §8 is the normative
machine-readable form of everything above it — parse that, not the prose.

---

## 1. Path — `P`

```text
<ROOT>/<YYYY>/<NN>. <Month>/<dated folder>[/<dated folder>…][/<__SUBFOLDER>]
```

| ID | Rule |
| --- | --- |
| P1 | `<ROOT>` is configured per run. Only its four-digit `<YYYY>` children are in scope; every other root entry is a working area and MUST be left alone (see §0 below). |
| P2 | Year folder name is exactly four digits. Nothing else at that level. |
| P3 | Month folder is `NN. Month` — zero-padded number, dot, space, **fixed English** month name (`01. January` … `12. December`). Never locale-derived. |
| P4 | Below a month folder, every directory MUST be either a dated folder (§2) or an allowed subfolder (§4). There is no third kind. |
| P5 | The year and month a folder sits under MUST match the date in its own name, after the N7 day shift. |

### §0 Out of scope

Only `<YYYY>` trees are governed. Present at the root today and **not** covered:
`____INGEST_PIPELINE` (pipeline working folder), `____TO_SORT` (legacy working
folder), `__PROCESSED` **[OPEN]**, `_Innych` **[OPEN]**. A conforming tool MUST NOT
descend into them or report their contents.

---

## 2. Dated folder names — `N`

```text
<prefix>[<tail>]

prefix:  YYYY-MM-DD_(Ddd)__HH.MM.SS      canonical — DOUBLE underscore before time
         YYYY-MM-DD_(Ddd)                date-only; legal, not preferred
```

| ID | Rule |
| --- | --- |
| N1 | Weekday is the fixed English set `Mon Tue Wed Thu Fri Sat Sun`. Never `strftime("%a")` — a Polish-locale host must not write `(pt)`. |
| N2 | The weekday is **decorative**. A wrong or stale one MUST NOT invalidate a folder; correct it, never reject it. |
| N3 | The time is the capture time of the folder's earliest file: earliest media where there is any, otherwise earliest `._exif` sidecar. For a container (§3) it is the earliest file in its whole subtree. |
| N4 | Two folders in one month folder MUST NOT share a name. The time is what separates two events on one day — which is why date-only is legal but discouraged. |
| N5 | Historical prefixes `YYYY-MM-DD_(Ddd)_HH.MM.SS` (single underscore) and `YYYY-MM-DD__HH.MM.SS` (no weekday) MUST still be **read**. They MUST NOT be newly **written**. |
| N6 | Only the **time** half of a prefix may ever be derived from folder contents. The **date** MUST NOT — rewriting it would move the folder out from under its month folder. A date that cannot exist (`2026-02-31`) is reported, never invented. |
| N7 | **Day boundary.** A capture at or before `04.44.44` (configurable) belongs to the **previous** day's folder. A night running past midnight is one event. Consequence: a folder's date may legitimately be one day earlier than some of its files. |

### Tails

| ID | Tail | Meaning |
| --- | --- | --- |
| N8 | ` - <description>` | Named by a human. **Finished** — no tool rewrites the tail. |
| N9 | ` - __CONTAINER__[(d=N)][ - <description>]` | Holds dated child folders. See §3. |
| N10 | ` - __TO_SPLIT__(<counts>)` | Day still to be split into sub-events. |
| N10a | ` - __TO_SPLIT__([f=N_]EMPTY)[_<n>]` | Holds no files anywhere in its subtree. The counts it carried go — there is nothing left to count. `f` states how many hollow subfolders still stand. |
| N10b | An `EMPTY` folder with no time takes `00.00.00`, so it still satisfies the full prefix of N1 rather than falling back to date-only. A folder emptied after it was named keeps its real time — N6 still forbids revising one. |
| N11 | ` - __TO_LABEL__` | Day still to be described. |
| N12 | ` - 1. ######` | Legacy placeholder. Read and converted to N10; never newly written. |

**Count bracket** (N9/N10): letters in the fixed order `d i v e s`, joined by `_`.

| Letter | Counts | Written when |
| --- | --- | --- |
| `d` | direct dated child folders | the folder is a container |
| `i` | top-level images | there are any |
| `v` | top-level videos | there are any |
| `e` | `._exif` in the whole subtree | the count ≠ media count in that subtree |
| `s` | non-sidecar files below the top level | there are any |
| `f` | subfolders in the whole subtree | the folder is `EMPTY` and has any |

`i`/`v` are the review job — they state what a grouper GUI will show. `e`/`s` are
audit markers: something the folder holds that `i`/`v` do not account for.

**Discriminator.** `EMPTY` discards what told two emptied folders on one day
apart, so the second and later carry `_2`, `_3` … appended after the bracket, in
name order. This is the only place a conforming tool may resolve a name clash by
renaming rather than reporting it; N4 still holds, and everywhere else two
folders claiming one name is an anomaly to surface, not to paper over.

---

## 3. Containers — `C`

A **container** is a dated folder that holds dated child folders. Nesting is
unlimited; two levels (day → sub-event) is the norm.

| ID | Rule |
| --- | --- |
| C1 | A dated folder holding ≥1 dated child folder MUST carry `__CONTAINER__` as the **first element of its tail**, so it is distinguishable from a leaf at a glance and by regex. |
| C2 | A leaf dated folder MUST NOT carry `__CONTAINER__`. Adding or removing the last child flips the marker; a conforming tool maintains it. |
| C3 | A container uses the **same prefix convention** as any dated folder (§2), timed per N3 from its whole subtree. |
| C4 | A container MAY carry `(d=N)` — its direct dated children — and a human description after the marker: ` - __CONTAINER__(d=3) - Sopot weekend`. |
| C5 | A child's date MUST fall within its parent's day ±1. A sub-event split near the day boundary can land on the neighbouring date; anything further is a violation. |
| C6 | Every level carries its own `__` subfolders. Companions follow their representative down into the child's own `__RAW`, `__EXIF`, … |
| C7 | A container MAY also hold loose top-level media (shots belonging to no sub-event). Those count into its own `i`/`v`. |

```text
2026\
  07. July\
    2026-07-15_(Wed)__08.14.02 - __CONTAINER__(d=3) - Sopot weekend\
        2026-07-15_(Wed)__08.14.02 - morning beach\
            2026-07-15_(Wed)__08.14.02__f1.7__T1_180__L23.0.eq__I12__SG23U_RAW.jpg
            __RAW\   __EXIF\
        2026-07-15_(Wed)__14.02.55 - __CONTAINER__(d=1) - pier\
            2026-07-15_(Wed)__14.31.09 - the gulls\
            __EXIF\
        2026-07-16_(Thu)__09.10.44 - __TO_LABEL__
        __GEOLOCATIONS\
    2026-07-18_(Sat)__11.03.27 - __TO_SPLIT__(i=79_v=3)\
```

---

## 4. Subfolders — `S`

Inside a dated folder, exactly these are permitted. All optional.

| Folder | Holds | Written by |
| --- | --- | --- |
| `__2_SHARE` | Selected for sharing | hand |
| `__3D` | Stereo / 3D captures (MPO etc.) | hand |
| `___OTHER` | Fits nowhere else — **three** leading underscores | hand |
| `__DUPLICATES` | Burst discards, unused brackets, accidental / low-res duplicates, collision losers | tool |
| `__EDITED` | Non-destructive edits and masters — `.xmp`, `.psd`, high-bit `.tif` | tool |
| `__EXIF` | `._exif` sidecars, JSON camera logs | tool |
| `__EXPORTED` | Full-resolution exports for print/archive | tool |
| `__EXTRACTED_VIDEOS` | Video extracted from other media | tool |
| `__GEOLOCATIONS` | `.gpx` tracks and other event geodata | tool |
| `__HASHES` | Content hashes / integrity records | tool |
| `__PANORAMAS` | Panorama sources and stitches | hand |
| `__PEOPLE` | Per-person crops / selections | hand |
| `__RAW` | RAW originals, untouched | tool |
| `__RESIZED` | Downscaled derivatives for web, social, email | tool |
| `__SHARED` | Already shared | hand |
| `__VIDEOS_TO_RENAME` | Videos still carrying a non-canonical name | tool |

| ID | Rule |
| --- | --- |
| S1 | The set is **closed**. Any other subfolder is a violation — except a dated child folder (§3), which is structure, not a violation. |
| S2 | Subfolders MUST NOT nest inside each other. `__RAW\__EXIF\` is a violation. |
| S3 | Folders marked *hand* are recognised and preserved but MUST NEVER be populated automatically. |
| S4 | A tool MUST read these names from §8, not restate them as literals. |

### **[OPEN]** — disagreements with the code as it stands

The table is the reviewer's list, transcribed. `DEFAULT_TAXONOMY` in
`src/pipeline_stages/taxonomy.py` differs, non-cosmetically:

1. **`__VIDEOS` is absent here but live in the code** — where video companions are
   routed, and `companion_reconciliation.py` / `canonicalise_timestamp_names.py`
   both reason about it by name. Dropping it is a breaking change. Keep it?
2. **`__EXTRACTED` is absent here but live in code and spec** — non-representative
   RAW extractions land there, and the `_EXT` filename suffix (N-file rules, §5)
   points at it. Keep it?
3. **`__VIDEOS_TO_RENAME` appears nowhere in the code.** New — or the intended
   replacement for `__VIDEOS`?
4. **`__2_SHARE` vs `__SHARED`** — read here as *queued to share* vs *already
   shared*. Confirm; the names invite being conflated.
5. **`__EMPTY_SUBFOLDERS`** — a holding area, not a taxonomy folder. It sits
   beside the day folders it takes, inside the month folder, and is created on
   first use. A dated folder holding no files anywhere in its subtree is moved
   there rather than offered to a grouper; it carries no day prefix, so a scan
   looking for dated folders neither matches it nor descends into it. Written
   by the grouping stage (`screenshot_grouping.py`); the maintenance tool
   renames what it finds there per N10a/N10b. Still open: which section should
   own it, and whether a tool other than the grouping stage may move folders
   into it.

---

## 5. Files — `F`

```text
YYYY-MM-DD_(Ddd)__HH.MM.SS[__RAW]__f<ap>__T<exp>__L<focal>__I<iso>__<CAM>[_RAW][_EXT][_EDT].<ext>

2026-08-14_(Fri)__15.32.01__f1.7__T1_180__L23.0.eq__I12__SG23U.jpg
2026-08-14_(Fri)__15.32.01__RAW__f8.0__T1_250__L50__I100__6D.CR2
```

| ID | Rule |
| --- | --- |
| F1 | The **leading timestamp** follows §2 exactly — same canonical form written, same historical forms read. It is the archive's join key: sidecars, RAWs and videos find their representative by it. A tool that renames files MUST preserve or correctly rewrite it. |
| F2 | `RAW__` after the timestamp marks a RAW file. RAW extensions are **uppercase**; lossy extensions **lowercase**. |
| F3 | Semantic suffixes on a representative announce what its subfolders hold, in this fixed order: `_RAW` (a RAW original exists), `_EXT` (extracted from RAW, not shot), `_EDT` (a better edit exists). Extension follows all of them. |
| F4 | Collision suffixes: `_DUPE_<md5>_<n>`, `_LOWRES`. |
| F5 | **One representative per shot at the top level, at most.** Every other version of the shot goes in a subfolder. |
| F6 | A camera-produced image is the preferred representative. For a RAW-only shot one selected extraction may stand in; the others go to `__EXTRACTED`. |
| F7 | RAW originals, sidecars, edits, exports, resizes and duplicates MUST NOT sit at the top level. *Why:* the top level is what a grouper GUI shows and what `i`/`v` count. A file in a subfolder is a file the reviewer never sees — which is what `s` exists to announce. |

---

## 6. Sidecars — `X`

| ID | Rule |
| --- | --- |
| X1 | A sidecar keeps its subject's **full** name and appends its own extension: `shot.jpg._exif`, `clip.mp4._exif`. |
| X2 | Therefore `Path.suffix` of a sidecar is `._exif`, never the media extension. That is what keeps sidecars out of media counts — match on the trailing extension, not by stripping it. |
| X3 | Therefore a sidecar carries its subject's capture time in its own name. A folder emptied of media can still be dated from what it left behind (N3). |
| X4 | **One sidecar per media file is the norm.** Any other ratio means a sidecar was orphaned when its image moved, or an image arrived without one — this is what `e` reports. |
| X5 | A tool renaming or moving media MUST carry its sidecars with it, renaming them per X1. Orphaning a sidecar is a defect, not a side effect. |

---

## 7. Tool obligations — `T`

Any tool writing to the archive, first-party or third-party:

| ID | Rule |
| --- | --- |
| T1 | **Nothing is deleted.** Move, rename, report. Never remove. |
| T2 | **Rename, never replace.** `os.rename`, not `os.replace` — an unexpected collision must fail loudly, not destroy the file it lands on. |
| T3 | **Report before writing.** Default run is a report; changes require an explicit `--apply`; every applied change is journalled so it can be replayed backwards. |
| T4 | **Never follow reparse points** — junctions, symlinks, mount points. Refuse and report each. |
| T5 | **Resolve a mapped drive to its UNC once, up front.** A drive letter is a per-session alias that can be remapped between check and write. |
| T6 | **Long paths.** Windows syscalls cap at `MAX_PATH`; a deep tree needs the `\\?\` prefix or a walk silently comes back short. |
| T7 | **A folder named by a human is finished** (N8). Its tail is never rewritten. |
| T8 | **One definition per rule.** Read names, markers and patterns from §8 or from the project's central modules — never restate them inline. A convention defined twice drifts, and half the pipeline ends up writing names the other half cannot parse. |

### Where the definitions live in this repo

| Concept | Home |
| --- | --- |
| Subfolder set | `src/pipeline_stages/taxonomy.py` — `DEFAULT_TAXONOMY` |
| Timestamp grammar | `src/pipeline_stages/stamps.py` |
| Folder-tail grammar, count bracket | `src/pipeline_stages/grouping_names.py` |
| Month names | `src/constants/constants.py` — `MONTH_FOLDERS` |
| Extensions, day boundary, collision suffixes, paths | `config.json` / `src/core.py` `default_config()` |

`stamps.py` and `grouping_names.py` are deliberately **leaf modules** importing
nothing from the project, so a maintenance tool can load one by file path without
dragging exiftool, the dashboard and the converters in behind it.

### **[OPEN]** — defined more than once today

1. **Taxonomy, twice** — `taxonomy.py:3` and again as a literal in `core.py:172`.
   Two lists that must agree, with nothing making them.
2. **`MONTH_FOLDERS`, twice** — `constants.py:316` (legacy CLI) and
   `legacy.py:11` (new pipeline).
3. **Four date regexes outside `stamps.py`** — `folder_sorter.py:29`,
   `organise_date_folders.py:24`, `retime_archive.py:44`, `provenance.py:9`. Each
   parses a dated name its own way; none accepts the full set of N5 forms.
4. `grouping_names.py:73` duplicates the leading-stamp regex **deliberately** (its
   docstring explains why: importing `stamps` pulls in the whole package
   `__init__`). An accepted exception — but a test should hold the two equal.

### The fixing tool (to be implemented)

Reports, does not fix, by default (T3). Reports every directory below a month
folder that is neither a dated folder nor an allowed subfolder — including
anything nested inside a subfolder (S2). Does not flag dated children (S1).
Maintains the `__CONTAINER__` marker (C2). Stays out of §0 roots. Exit codes
`0` nothing to do, `1` changes pending or failures, `2` error — matching
`tools/canonicalise_timestamp_names.py`.

---

## 8. Machine-readable definitions

**Normative.** A conforming tool parses this block rather than the prose above;
the repo's central modules (§7) mirror it. Regexes are Python flavour, matching
against a single path component.

```yaml
standard: photo-archive
version: 0.1
status: draft

path:
  levels: [root, year, month, dated_folder, "dated_folder*", subfolder]
  year: '^\d{4}$'
  month: '^(0[1-9]|1[0-2])\. (January|February|March|April|May|June|July|August|September|October|November|December)$'
  month_names:
    "01": "01. January"
    "02": "02. February"
    "03": "03. March"
    "04": "04. April"
    "05": "05. May"
    "06": "06. June"
    "07": "07. July"
    "08": "08. August"
    "09": "09. September"
    "10": "10. October"
    "11": "11. November"
    "12": "12. December"
  out_of_scope_root_entries: ["____INGEST_PIPELINE", "____TO_SORT", "__PROCESSED", "_Innych"]

stamp:
  weekdays: [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
  descriptor: "YYYY-MM-DD_(Ddd)__HH.MM.SS"
  strftime_write: "%Y-%m-%d_({weekday})__%H.%M.%S"
  date: '\d{4}-\d{2}-\d{2}'
  time: '\d{2}\.\d{2}\.\d{2}'
  # canonical form — the only one that may be WRITTEN
  write: '^(\d{4})-(\d{2})-(\d{2})_\((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\)__(\d{2})\.(\d{2})\.(\d{2})'
  # every form that must be READ; groups = y,m,d,H,M,S
  read: '^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\([A-Za-z]{3}\))?[ _]+(\d{2})\.(\d{2})\.(\d{2})'
  # folder prefixes only: the time half is optional
  read_folder_prefix: '^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\([A-Za-z]{3}\))?(?:[ _]+(\d{2})\.(\d{2})\.(\d{2}))?'
  weekday_is_decorative: true
  day_boundary: "04.44.44"          # capture <= this belongs to the previous day
  derivable_from_contents: [time]   # never [date]

folder_tail:
  named:      ' - (?P<description>.+)$'
  container:  ' - __CONTAINER__(?:\((?P<counts>[divse]=\d+(?:_[divse]=\d+)*)\))?(?: - (?P<description>.+))?$'
  to_split:   ' - __TO_SPLIT__\((?:(?P<counts>[divsef]=\d+(?:_[divsef]=\d+)*)|(?:(?P<empty_counts>[divsef]=\d+(?:_[divsef]=\d+)*)_)?(?P<empty>EMPTY))\)(?:_(?P<discriminator>\d+))?$'
  to_label:   ' - __TO_LABEL__$'
  legacy_placeholder: ' - 1\. ######$'
  markers: ["__CONTAINER__", "__TO_SPLIT__", "__TO_LABEL__"]
  count_letters: [d, i, v, e, s, f] # fixed order, joined by "_"
  count_meaning:
    d: direct dated child folders
    i: top-level images
    v: top-level videos
    e: sidecars in subtree, written only when != media count in subtree
    s: non-sidecar files below the top level
    f: subfolders in subtree, written only alongside EMPTY
  empty_marker: EMPTY               # holds no files anywhere; replaces the counts
  empty_time: "00.00.00"            # stands in when an EMPTY folder has no time
  discriminator: '_<n>'             # _2, _3 ... only on EMPTY names, only to keep N4

container:
  required_when: has_dated_child
  marker_position: first_element_of_tail
  child_date_tolerance_days: 1
  time_from: whole_subtree_earliest_file

subfolders:
  closed_set: true
  also_allowed: dated_child_folder
  may_nest: false
  tool_written:
    - "__DUPLICATES"
    - "__EDITED"
    - "__EXIF"
    - "__EXPORTED"
    - "__EXTRACTED_VIDEOS"
    - "__GEOLOCATIONS"
    - "__HASHES"
    - "__RAW"
    - "__RESIZED"
    - "__VIDEOS_TO_RENAME"
  hand_curated:                     # recognised, never auto-populated
    - "__2_SHARE"
    - "__3D"
    - "___OTHER"
    - "__PANORAMAS"
    - "__PEOPLE"
    - "__SHARED"
  disputed:                         # see the [OPEN] list in section 4
    - "__VIDEOS"
    - "__EXTRACTED"

files:
  leading_stamp_required: true
  grammar: "<stamp>[__RAW]__f<ap>__T<exp>__L<focal>__I<iso>__<CAM>[_RAW][_EXT][_EDT].<ext>"
  raw_marker: "RAW__"
  raw_extension_case: upper
  lossy_extension_case: lower
  representative_suffixes: ["_RAW", "_EXT", "_EDT"]   # fixed order
  collision_suffixes:
    duplicate: "_DUPE_<md5>_<n>"
    low_resolution: "_LOWRES"
  top_level: representatives_only
  max_representatives_per_shot: 1

sidecars:
  extensions: ["._exif"]
  naming: "<full media filename><sidecar extension>"
  match_by: trailing_extension        # not by stripping the media extension
  expected_ratio: one_per_media_file
  travels_with_media: true

extensions:
  lossy_images: [".jpg", ".jpeg", ".thm"]
  other_images: [".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"]
  raw_images:   [".arw", ".cr2", ".crw", ".dng", ".mpo", ".rw2"]
  videos:       [".mp4", ".mov", ".avi"]
  geodata:      [".gpx"]

tool_obligations:
  never_delete: true
  rename_not_replace: true
  dry_run_default: true
  journal_applied_changes: true
  follow_reparse_points: false
  resolve_mapped_drive_to_unc: true
  long_path_prefix: '\\?\'
  human_named_folder_is_final: true
  exit_codes: {clean: 0, pending_or_failed: 1, error: 2}
```

---

## 9. Amending

The names and the taxonomy are load-bearing — hundreds of thousands of files are
already on disk in this shape. An amendment is a change to this document **and** a
migration for the existing archive, together, never one alone. Bump `version` in
§8 with any normative change.
