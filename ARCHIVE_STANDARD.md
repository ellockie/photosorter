# Photo & Video Archive Standard

**v0.8 — DRAFT. Under review. Not enforced by any code.**

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
| P4 | Below a month folder, every directory MUST be a dated folder (§2), an allowed subfolder (§4), or a holding area (§4.1). There is no fourth kind. |
| P5 | The year and month a folder sits under MUST match the date in its own name, after the N7 day shift. |

### §0 Out of scope

Only `<YYYY>` trees are governed. A conforming tool MUST NOT descend into any
other root entry or report its contents. Present at the root today:

| Entry | What it is | Fate |
| --- | --- | --- |
| `____INGEST_PIPELINE` | Pipeline working folder (`INBOX`, `READY`, `.TMP`) | Transient |
| `____TO_SORT` | Legacy working folder | Transient |
| `__PROCESSED` | Edits and derivatives made outside the pipeline | **Migration source** — see §0.1 |
| `_Innych` | Media from other people, e.g. a second photographer at the same event | **Opt-in ingest source** — see §0.2 |

### §0.1 `__PROCESSED` — derivatives to be reunited

Its contents are derivatives of shots that live in the archive, so they belong in
their subject's `__EDITED` (or `__EXPORTED`, `__RESIZED`). Matching is by the
leading stamp, like everything else. The problem is that editing tools rewrite
names and metadata, so some files arrive with no stamp at all and nothing to key
on.

| ID | Rule |
| --- | --- |
| D1 | A derivative SHOULD carry its subject's leading stamp, which is what keys it to the shot. One that does is filed under that shot's event folder automatically. |
| D2 | **A derivative with no usable stamp is never given an invented one** — the same rule as V4, for the same reason. It is not renamed from a neighbour, a folder name, or a file time. |
| D3 | Instead, **the dated folder supplies the date the filename lacks**: an unkeyed derivative MUST still come to rest inside the `__EDITED` of the event folder it belongs to, and its own name is kept byte for byte. The folder is then the only claim being made, and it is one a person made. |
| D4 | Attributing an unkeyed derivative to an event is a **human decision**, not a tool's. Until someone makes it, the file stays in `__PROCESSED` and is reported. A tool MUST NOT distribute unkeyed derivatives by guesswork. |
| D5 | D3 is the **second exemption from F1** (after V10): a file inside `__EDITED` may open with something other than a stamp. A compliance checker reports it as unkeyed, not as malformed. |

**[OPEN]** — D3 says the *event* folder is enough. It could be tightened to
require the sub-event folder, which would be more precise and much more work to
establish for a file with no time. Is event-level attribution enough?

### §0.2 `_Innych` — other people's media

Photos from someone else at the same event — a partner's camera, a friend's
phone. Wanted in the archive sometimes, for a fuller picture of the day; never
processed behind your back.

| ID | Rule |
| --- | --- |
| G1 | A foreign-origin folder is **never** ingested automatically. No run touches it, and nothing in it is renamed, moved or reported as a violation. |
| G2 | Merging is **opt-in and per-batch**: a person points a run at it deliberately. There is no configuration that turns it on for good. |
| G3 | Once merged, the files are ordinary archive media — renamed, stamped and sorted by the normal rules, so they interleave with the event's own shots by capture time, which is the point of merging them at all. |
| G4 | A merged file **carries an author marker** (F8). The camera symbol names the device, not the person: two people shooting the same model are indistinguishable by it, which is exactly the case merging creates. |

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

**Count bracket** (N9/N10): letters in the fixed order `d i v e c s w f`, joined by `_`.

| Letter | Counts | Written when |
| --- | --- | --- |
| `d` | direct dated child folders | the folder is a container |
| `i` | top-level images | there are any |
| `v` | top-level videos | there are any |
| `e` | distinct **subjects** the subtree's `._exif` files name | the count ≠ media count in that subtree |
| `c` | `._exif` files beyond the first for any one subject | there are any |
| `s` | non-sidecar files below the top level | there are any |
| `w` | videos in `__VIDEOS_TO_RENAME` awaiting a name (V8) | there are any |
| `f` | subfolders in the whole subtree | the folder is `EMPTY` and has any |

`i`/`v` are the review job — they state what a grouper GUI will show.
`e`/`c`/`s`/`w` are audit markers: something the folder holds that `i`/`v` do not
account for. `w` differs from the others in that it is addressed to a tool, not
only to a reader — see V9.

**`e` counts subjects, not files, and `c` is why.** One sidecar per media file is
the norm (X4), so the useful question is how many media are *covered*, not how
many `._exif` are lying about. Counting files let one fault mask another: two
sidecars naming the JPG and none naming the RAW totalled two against two media
and reported nothing at all. Split in two, that folder reads `e=1_c=1` — one
subject covered, one file too many — and both faults are visible.

In a folder in order, every subject is covered, so `e` is silent and `c` absent.
`c` is what companion placement (§6) settles: it compares the clashing files by
checksum and parks the loser, after which `c` goes and `e` matches.

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
| C5 | A child's date MUST fall within its parent's day ±1 — or its span ±1, see C11. A sub-event split near the day boundary can land on the neighbouring date; anything further is a violation. |
| C6 | Every level carries its own `__` subfolders. Companions follow their representative down into the child's own `__RAW`, `__EXIF`, … |
| C7 | A container MAY also hold loose top-level media (shots belonging to no sub-event). Those count into its own `i`/`v`. |
| C8 | **A container MAY span more than one day.** It states the end of the span as `#<end>` appended directly to its dated prefix, before the tail: `2026-08-20_(Thu)__09.14.02#22 - __CONTAINER__(d=3) - Malbork trip`. |
| C9 | The end is the **shortest tail of a date that still identifies the day** — `#22` (same year and month), `#09-11` (same year), `#2027-01-03` (any). The field count disambiguates, so nothing is inferred from context. |
| C10 | The **start** keeps the full canonical prefix (C3) and leads the name, so alphabetical order stays chronological and every parser still reads the start date and time unchanged. The end carries no weekday and no time: a span is a range of *days*. |
| C11 | Only a container may carry a span — a leaf dated folder is one day by definition, and N7 decides which. For a spanning container, C5 reads against the whole range: a child's date MUST fall within `[start, end]` ±1 day. |

```text
2026\
  07. July\
    2026-07-15_(Wed)__08.14.02 - __CONTAINER__(d=3) - Sopot weekend\
        2026-07-15_(Wed)__08.14.02 - morning beach\
            2026-07-15_(Wed)__08.14.02__f1.7__T1_180__L23.0.eq__I12__SG23U_HAS_RAW.jpg
            __EXIF\                          <- sidecar for the .jpg above it (X10)
            __RAW\
                2026-07-15_(Wed)__08.14.02__RAW__f1.7__…__SG23U.ARW
                __EXIF\                      <- sidecar for the RAW beside it (X11)
        2026-07-15_(Wed)__14.02.55 - __CONTAINER__(d=1) - pier\
            2026-07-15_(Wed)__14.31.09 - the gulls\
            __EXIF\
        2026-07-16_(Thu)__09.10.44 - __TO_LABEL__
        __GEOLOCATIONS\
    2026-08-20_(Thu)__09.14.02#22 - __CONTAINER__(d=3) - Malbork trip\
        2026-08-20_(Thu)__09.14.02 - arrival\
        2026-08-21_(Fri)__10.55.13 - the castle\
        2026-08-22_(Sat)__08.02.44 - going home\
    2026-07-18_(Sat)__11.03.27 - __TO_SPLIT__(i=79_v=2_w=1)\
        2026-07-18_(Sat)__11.03.27__fNA__T---__LNA__I---s__SG23U.mp4
        __EXIF\                              <- stills and videos share it (V3)
        __VIDEOS_TO_RENAME\
            __TO_RENAME__VID_0034.mp4
            __EXIF\                          <- travels with the video (V8c)
```

---

## 4. Subfolders — `S`

Inside a dated folder, exactly these are permitted. All optional.

| Folder | Holds | Written by |
| --- | --- | --- |
| `__TO_SHARE` | Queued for sharing — not yet sent | hand |
| `__3D` | Stereo / 3D captures (MPO etc.) | hand |
| `___OTHER` | Fits nowhere else — **three** leading underscores | hand |
| `__DUPLICATES` | Burst discards, unused brackets, accidental / low-res duplicates, collision losers | tool |
| `__EDITED` | Non-destructive edits and masters — `.xmp`, `.psd`, high-bit `.tif` | tool |
| `__EXIF` | `._exif` sidecars, JSON camera logs | tool |
| `__EXPORTED` | Full-resolution exports for print/archive | tool |
| `__GEOLOCATIONS` | `.gpx` tracks and other event geodata | tool |
| `__HASHES` | Content hashes / integrity records | tool |
| `__PANORAMAS` | Panorama sources and stitches | hand |
| `__PEOPLE` | Per-person crops / selections | hand |
| `__PREVIEWS` | Camera thumbnails and low-res proxies — `.thm`, `.lrv`, generated previews. See X6 | tool |
| `__RAW` | RAW originals, untouched | tool |
| `__RAW_EXTRACTED_JPGS` | JPEGs extracted from a RAW for a shot that already has a camera JPEG | tool |
| `__RESIZED` | Downscaled derivatives for web, social, email | tool |
| `__SHARED` | Already shared | hand |
| `__VIDEOS_EXTRACTED` | Video extracted out of other media | tool |
| `__VIDEOS_TO_RENAME` | Videos that could not be dated — tagged `__TO_RENAME__` (V8) | tool |

| ID | Rule |
| --- | --- |
| S1 | The set is **closed**. Any other subfolder is a violation — except a dated child folder (§3), which is structure, not a violation. |
| S2 | Subfolders MUST NOT nest inside each other, with one exception: a folder holding media may hold its subjects' sidecar folders, `__EXIF` and `__PREVIEWS` (X10–X13). So `__RAW\__EXIF\` is legal and `__RAW\__EDITED\` is not. |
| S3 | Folders marked *hand* are recognised and preserved but MUST NEVER be populated automatically. |
| S4 | A tool MUST read these names from §8, not restate them as literals. |
| S5 | **No video folder in the ordinary case.** A datable video is a representative at the top level (V1). `__VIDEOS` and `__EXTRACTED_VIDEOS` were an earlier arrangement: they are **read** — recognised as taxonomy folders so an existing archive is not reported as malformed and its companions can still be reunited — and **never written**, the same read-old/write-new rule N5 applies to timestamps. |

### Implemented

`src/pipeline_stages/taxonomy.py` is the single definition (T8/S4).
`default_config()` writes no `taxonomy` block, so there is nothing to keep in
step with it; `LEGACY_TAXONOMY` in the same module carries the two retired names
for S5. Videos are routed to the top level by `folder_sorting.py`.

### 4.1 Holding areas — `H`

A **holding area** is a named folder that sits where dated folders sit — directly
under a month folder, or beside the children inside a container — and holds
dated folders rather than media of its own. It is not a taxonomy subfolder: those
live *inside* an event folder and hold that event's files.

| ID | Rule |
| --- | --- |
| H1 | A holding area MUST carry no dated prefix, so a scan looking for dated folders neither matches it nor mistakes it for an event. |
| H2 | It MAY appear at any level where a dated folder may appear, and is created on first use. |
| H3 | It holds **dated folders**, which keep their own names and go on obeying §2. Moving a folder into one does not rename it. |
| H4 | The set is closed, as §4's is. Today there is exactly one: `__EMPTY_SUBFOLDERS`, for day folders emptied of every file — parked rather than offered to a grouper. |

### **[OPEN]** — still to settle

1. **Where does a collision loser go?** S4 puts `__DUPLICATES` inside a dated
   folder. Companion placement (§6) instead writes one per **year tree**,
   `<YYYY>\__DUPLICATES`, so a whole year's losers are in a single place to
   review rather than scattered one per event. That is outside §4 as written and
   wants either an amendment here or a change there before this leaves draft.
2. **May a tool other than the grouping stage move folders into
   `__EMPTY_SUBFOLDERS`?** §4.1 now gives it a home — a sibling of the dated
   folders it takes, at whatever level they live — but only
   `screenshot_grouping.py` writes to it today.

---

## 5. Files — `F`

```text
YYYY-MM-DD_(Ddd)__HH.MM.SS[__RAW]__f<ap>__T<exp>__L<focal>__I<iso>__<CAM>[_RAW][_EXT][_EDT].<ext>

2026-08-14_(Fri)__15.32.01__f1.7__T1_180__L23.0.eq__I12__SG23U.jpg
2026-08-14_(Fri)__15.32.01__RAW__f8.0__T1_250__L50__I100__6D.CR2
```

| ID | Rule |
| --- | --- |
| F1 | The **leading timestamp** follows §2 exactly — same canonical form written, same historical forms read. It is the archive's join key: sidecars, RAWs and videos find their representative by it. A tool that renames files MUST preserve or correctly rewrite it. One exemption exists: a `__TO_RENAME__`-tagged file (V10). |
| F2 | `RAW__` after the timestamp marks a RAW file. RAW extensions are **uppercase**; lossy extensions **lowercase**. |
| F3 | Semantic suffixes announce how the shot was taken and what else exists, in this fixed order: `_HAS_RAW` **or** `_FROM_RAW`, then `_HAS_EDIT`. Extension follows all of them. `_HAS_*` names a sibling elsewhere; `_FROM_*` names this file's own provenance. |
| F3a | The two RAW suffixes are **mutually exclusive**: `_FROM_RAW` already says a RAW exists, so it never carries `_HAS_RAW` as well. |
| F3b | Earlier names `_RAW` (has raw), `_EXT` (extracted) and `_EDT` (has edit) MUST still be **read** and MUST NOT be newly written — the N5 rule again. `_RAW` was the ambiguous one: on a camera JPEG it read as *this is a RAW*, the sense `RAW__` carries inside a filename, when it meant *a RAW exists*. |
| F4 | Collision suffixes: `_DUPE_<md5>_<n>`, `_DIFFERS_<md5>_<n>`, `_LOWRES`. `_DUPE` is a byte-identical loser; `_DIFFERS` is one that claimed the same name with **different** bytes, which is a defect a person has to settle. Both are written by companion placement (§6). |
| F5 | **One representative per shot at the top level, at most.** Every other version of the shot goes in a subfolder. |
| F6 | A camera-produced image is the preferred representative. For a RAW-only shot one selected extraction may stand in; the others go to `__EXTRACTED`. |
| F7 | RAW originals, sidecars, edits, exports, resizes and duplicates MUST NOT sit at the top level. *Why:* the top level is what a grouper GUI shows and what `i`/`v` count. A file in a subfolder is a file the reviewer never sees — which is what `s` exists to announce. |

### 5.2 Author markers — `F8`

The camera symbol says **what** took a shot. When an archive holds media from
more than one person — a partner's camera at the same event (§0.2) — it also has
to say **who**, because two people shooting the same model are indistinguishable
by the device alone.

```text
2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I200__C6D.jpg        the owner's — no marker
2026-05-14_(Thu)__10.30.00__f2.8__T1_250__L50.0__I200__C6D__@AK.jpg   someone else's
```

| ID | Rule |
| --- | --- |
| F8 | An author marker is `__@<SYMBOL>`, written **last**, immediately after the camera symbol and before any representative suffix. Camera and author together are the file's provenance and belong side by side. |
| F8a | **The archive owner carries no marker.** Absent means "mine". Marking the owner too would mean renaming every file already in the archive to state what its absence already states. |
| F8b | The `@` sigil makes the token **self-identifying**: a tool can tell an author from a camera symbol without consulting a table. That matters for a convention other people's tools have to implement. |
| F8c | Symbols come from a table keyed by person, the same shape as the camera-symbol table — `author_symbols` in config, name → short symbol. Unlike camera models there is **no built-in table**: models are universal, the people in one person's archive are not. |
| F8d | A name the table does not know resolves to **nothing at all**, and no marker is written. Falling back to the owner would file someone else's photo as theirs, which is the one outcome the marker exists to prevent. Such a file is reported for a person to map. |
| F8e | Authorship is taken from where a batch was ingested (§0.2), or from EXIF `Artist` where the camera recorded it — the only claim a file can make about itself. Both resolve through the one table. |

### 5.1 Videos — `V`

A video is media, not a companion. Where its own metadata can date it, it is
named and placed exactly like a still and needs no rules of its own; §5.1 exists
for the case a still almost never hits — a container format that carries no usable
capture time.

```text
2026-07-15_(Wed)__14.22.30__fNA__T---__LNA__I---s__SG23U.mp4   dated from its own metadata
__TO_RENAME__VID_20150612_004411.mp4                           undatable; tagged, in __VIDEOS_TO_RENAME
```

| ID | Rule |
| --- | --- |
| V1 | A video whose capture time is readable from its own metadata is a **representative** (F5). It sits at the **top level beside the images**, named by the F-grammar, and MUST NOT be routed into a subfolder. It counts into `v`. |
| V2 | Fields the format does not carry take the placeholder tokens the grammar already defines — `fNA`, `T---`, `LNA`, `I---s`, `NOID` — rather than being omitted. The token count is what keeps the name parseable by position. |
| V3 | **A video's sidecar is not segregated by media kind.** A top-level video sits in the dated folder, so by X10 its sidecar goes in that folder's `__EXIF`, beside the images' — named per X1 (`clip.mp4._exif`). A tool MUST NOT create a video-only sidecar folder alongside it. |
| V4 | **A capture time is never invented.** A video whose own metadata gives no usable one is not dated from its neighbours, its position, or its file times. A stamp in the canonical form is a claim that the camera recorded that moment; a derived one is indistinguishable from a read one once written, and the archive would carry a fact it never had. |
| V5 | Such a video is **tagged and moved** instead (V8) and left for a person. Interpolating from the surrounding stills is a reasonable idea and may come back — see the reserved `__EST__` marker below — but not as an automatic rewrite of a name that is meant to be evidence. |
| V8 | A video with no usable capture time of its own MUST NOT be guessed at. It is **tagged and moved**: the name becomes `__TO_RENAME__<original name>` and the file goes to **`__VIDEOS_TO_RENAME`**. The run **warns**, and the folder carries `w=N` in its count bracket so the backlog is visible in Explorer without opening anything. |
| V8a | The tag is a **prefix**, and the original name follows it **byte for byte** — that name is the only remaining evidence of the file's identity, and often holds the real time in a form nothing could parse. Stripping a known prefix recovers it exactly; no other part of the name is touched. |
| V8b | Tag **and** folder, not either alone. The folder is positional and is lost the moment the file is dragged elsewhere; the tag travels with the file and says what is wrong with it wherever it ends up. A tool finding a `__TO_RENAME__` file outside `__VIDEOS_TO_RENAME` MUST report it rather than assume it was resolved. |
| V8c | A tagged video's sidecar and previews travel **with it**, landing in `__VIDEOS_TO_RENAME\__EXIF\` and `__VIDEOS_TO_RENAME\__PREVIEWS\` per X10 and renamed per X1 (`__TO_RENAME__VID_0034.mp4._exif`). This is X10 applied, not an exception to it: the sidecar follows its subject's folder, so the unresolved unit stays together for the tool that will resolve it instead of leaving a stamp-less sidecar among stamped ones upstairs. |
| V9 | `w=N` is a **standing request for the cleanup tool** (§7), not a transient log line. It is cleared only when the videos are named, and only by a tool that had the user in the loop. |
| V10 | A `__TO_RENAME__` name is the **one exemption from F1** — it deliberately does not open with a stamp, because there is no stamp to write and a guessed one would be indistinguishable from a read one. A compliance checker MUST recognise the tag rather than report the missing stamp. |
| V11 | Resolving a tagged video means: write the real stamp, drop `__TO_RENAME__`, move it back to the top level **with its sidecar and previews following it into the top-level `__EXIF`/`__PREVIEWS` (X10)**, and decrement `w`. All of it together — a tool that renames without moving, or moves the video without its companions, leaves the archive lying about itself. |

**Matching the tag, not the folder.** The file tag `__TO_RENAME__` and the folder
`__VIDEOS_TO_RENAME` share a substring, so a naive search for `TO_RENAME` hits
both. They are still unambiguous: the tag is bounded by double underscores on both
sides **and** anchored to the start of a file name, the folder is a directory name
beginning `__VIDEOS_`. Match the tag as `^__TO_RENAME__` and the folder by exact
name — never by substring.

**Reserved: `__EST__`.** If interpolating a time from the surrounding stills is
ever adopted, the result must be marked `<stamp>__EST__<original stem>.<ext>` so
a derived time is never mistaken for a read one, must not feed N3 folder timing
while any read stamp exists in the folder, and must be replaced the moment a real
capture time is recovered. The marker is reserved for that; **nothing writes it
today** and a conforming tool must not.

Deciding *which* neighbours to interpolate between is the unsolved half. Ordering
by original name holds for one camera writing one sequence, but a device that
numbers video separately from stills (`VID_0034` beside `IMG_0033`) interleaves
wrongly, and a mixed-source day breaks it outright. Until that is settled, V4
stands: no invented times.

**[OPEN] — the cleanup tool.** To be implemented. Expected to be the interactive
counterpart of the fixing tool (§7): it lists `w=N` folders, shows each unresolved
video with its anchors, takes the user's decision, and applies it under the same
T1–T8 obligations. Not yet designed.

---

## 6. Sidecars — `X`

**Placement, in one line: a sidecar lives in `__EXIF` directly inside the folder
that holds its subject** — always exactly one level below the file it describes,
wherever that file has ended up. X10–X13 spell out what follows from that.

| ID | Rule |
| --- | --- |
| X1 | A sidecar keeps its subject's **full** name and appends its own extension: `shot.jpg._exif`, `clip.mp4._exif`. |
| X2 | Therefore `Path.suffix` of a sidecar is `._exif`, never the media extension. That is what keeps sidecars out of media counts — match on the trailing extension, not by stripping it. |
| X3 | Therefore a sidecar carries its subject's capture time in its own name. A folder emptied of media can still be dated from what it left behind (N3). |
| X4 | **One sidecar per media file is the norm.** Any other ratio means a sidecar was orphaned when its image moved, or an image arrived without one — this is what `e` reports. |
| X5 | A tool renaming or moving media MUST carry its sidecars with it, renaming them per X1. Orphaning a sidecar is a defect, not a side effect. |
| X6 | **Thumbnails and previews are sidecars** — a camera `.thm`, a GoPro `.lrv` proxy, any generated preview. They follow X1 (`clip.mp4.thm`, `clip.mp4.lrv`), travel with their subject (X5), and live in **`__PREVIEWS`**. |
| X7 | A preview is **never** a representative and **never** counted as media: not at the top level, not in `i`/`v`. It is one more file below the top level, so it counts into `s` like any other. |
| X8 | A preview is **not** counted in `e`. `e` compares `._exif` sidecars against media (X4); folding previews in would break a ratio that is only meaningful one-to-one. |
| X9 | A subject may have several previews of different kinds. They are distinguished by their own extensions, never by mangling the subject name. |
| X10 | **A sidecar sits in `__EXIF` directly inside the folder holding its subject** — one level below the subject, never two, never in an `__EXIF` further up. Top-level media (stills and videos alike, V1) therefore share the dated folder's own `__EXIF`; media parked in a subfolder uses that subfolder's `__EXIF`. |
| X11 | It follows that **any folder holding media may hold an `__EXIF`** — `__RAW\__EXIF\`, `__VIDEOS_TO_RENAME\__EXIF\`. This is the single exception to S2, and it exists so that moving a folder carries its sidecars with it instead of stranding them: locality is what makes the move atomic. |
| X12 | The exception is **one level and sidecar folders only**. `__EXIF` holds nothing but sidecars — no media, no further subfolders — and no other subfolder may nest in any other. `__RAW\__EDITED\` stays a violation. |
| X13 | `__PREVIEWS` follows X10–X12 exactly: previews sit beside their subject's `__EXIF`, one level below the subject (`__VIDEOS_TO_RENAME\__PREVIEWS\`). |

**X10 reaches further than videos — universal, and applied.** The rule governs
`__RAW` too: a RAW original lives in `__RAW`, so its sidecar is in
`__RAW\__EXIF\`, not the dated folder's own `__EXIF`. Same for `__EDITED`,
`__EXPORTED`, `__RESIZED` — any subfolder holding media.

The gain is that a sidecar moves when its folder moves, so a `__RAW` dragged
anywhere arrives intact — the class of bug `companion_reconciliation.py` exists
to repair. The cost is a migration of the sidecars already in the archive, which
the fixing tool reports and moves.

**Implemented.** `folder_sorting.py` places each sidecar relative to where its
subject landed (`sidecar_subdir` in `taxonomy.py`), and
`companion_reconciliation.py` preserves a companion's path *depth* when it
follows a representative into a sub-event, so `__RAW/__EXIF/x._exif` arrives at
`<sub>/__RAW/__EXIF/x._exif` rather than being flattened. This supersedes the
OpenSpec `pipeline-core` scenario that puts every `._exif` under the event
folder's own `__EXIF`.
The folder is `__PREVIEWS` — settled. It holds both a 40×30 `.thm` and a
four-minute `.lrv` proxy, which is why it is not `__THUMBNAILS`. **Routing is
implemented** — `place_companions` in `companion_matching.py`, run by the
restructure tool — though nothing *writes* a preview there during a live
ingest yet.

**`.thm` and `.lrv` are previews, not media — applied.** `.thm` used to sit in
`extensions.lossy_images`, so a camera thumbnail counted into `i` and could be
selected as the representative for a shot whose real image was absent. Both now
live in `extensions.previews` and are neither media nor `._exif` sidecars: they
count into `s` (X7), never into `i`/`v` or `e` (X8). This reclassifies `.thm`
files already in the archive — their `i` counts fall on the next tool run.

**Routing them is implemented — applied.** `place_companions` places a preview
in the `__PREVIEWS` directly inside the folder holding its subject (X13), in the
same pass that places `._exif` sidecars in `__EXIF` (X10).

A preview arrives in **camera form** — the subject's *stem* plus its own
extension, `GX010042.LRV` beside `GX010042.MP4` — because nothing has ever
renamed one. X6 requires previews to follow X1, and once a preview is in
`__PREVIEWS` the stem is all that would be left to pair it by, so a camera-form
preview is **renamed onto X1 as it moves**: `GX010042.LRV` becomes
`GX010042.MP4.lrv`. The extension is lower-cased, following the convention for
every other non-RAW extension. A stem shared by two subjects is not knowable
from the name, so that preview is left where it is and reported.
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

### Defined more than once — fixed

1. ~~**Taxonomy, twice**~~ — the literal in `core.py`'s `default_config()` is
   gone; `taxonomy.py` is the only definition, and `default_config()` writes no
   `taxonomy` block at all, so `save_config()` cannot bake a stale copy into a
   config file. `tests/test_taxonomy_single_source.py` holds it against this
   document and fails if any stage carries a folder name as a literal.
2. ~~**`taxonomy_dir_names()`, twice**~~ — the same function was defined
   identically in `companion_reconciliation.py` and `grouping_review.py`. One
   copy now, in `taxonomy.py`.

3. ~~**`retime_archive.py`'s event-folder regex**~~ — folded into
   `stamps.split_dated_folder()`. It demanded the weekday and then either
   `` - <description>`` or the end of the name, so a folder carrying the
   canonical time never matched and the tool skipped it — and the canonicaliser
   has been converging the archive onto exactly that form. Consolidating fixed
   the blindness; `tests/test_stamps.py` covers it.

### Deliberately *not* consolidated

Three date regexes remain outside `stamps.py`. Each parses something `stamps`
does not, so folding them in would widen a grammar rather than share one:

1. **`provenance.py:9`** parses **foreign** folder names at intake —
   `2024.01.15-Trip`, `2024-01-15_18.30 Party` — with separators the archive
   never writes. `stamps` is the grammar of names *we* produce; conflating them
   would let intake spellings into the archive's own parser.
2. **`organise_date_folders.py:24`** asserts that an already-extracted string
   *is* a date. It validates a value, where `stamps` matches a prefix inside a
   name — a different question.
3. **`folder_sorter.py:29`** belongs to the legacy CLI, which works in
   `____TO_SORT` — out of scope by §0 — and already accepts the forms it meets.

### **[OPEN]** — still defined more than once

1. **`file_md5`, twice** — `core.py:465` and `common/common.py:360`. Companion
   placement needs a checksum and cannot import either without dragging the
   pipeline in, so it takes one as a parameter and carries a stdlib default
   (`default_checksum`). That is three implementations of MD5-a-file, which is
   two too many.
2. **`MONTH_FOLDERS`, twice** — `constants.py:316` (legacy CLI) and
   `legacy.py:11` (new pipeline). The legacy copy is reachable only from the
   legacy CLI; consolidating means the new pipeline importing `constants.py`,
   which asserts `PHOTO_BASE_FOLDER` at import time. Worth doing, not free.
3. `grouping_names.py:73` duplicates the leading-stamp regex **deliberately** (its
   docstring explains why: importing `stamps` pulls in the whole package
   `__init__`). An accepted exception — but a test should hold the two equal.

### The fixing tool (to be implemented)

Reports, does not fix, by default (T3). Reports every directory below a month
folder that is neither a dated folder nor an allowed subfolder — including
anything nested inside a subfolder except a sidecar folder (S2, X11). Does not
flag dated children (S1).
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
version: 0.8
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
  migration_sources: {"__PROCESSED": derivatives}       # section 0.1
  opt_in_ingest_sources: {"_Innych": foreign_origin}    # section 0.2, never automatic

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
  read_folder_prefix: '^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\([A-Za-z]{3}\))?(?:[ _]+(\d{2})\.(\d{2})\.(\d{2}))?(?:#(?:(?:(\d{4})-)?(\d{2})-)?(\d{2}))?'
  # C8-C11: end of a multi-day container span; groups = year?, month?, day
  range_end: '#(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})'
  range_end_forms: ["#DD", "#MM-DD", "#YYYY-MM-DD"]   # omitted fields taken from the start
  range_end_applies_to: container_only
  weekday_is_decorative: true
  day_boundary: "04.44.44"          # capture <= this belongs to the previous day
  day_boundary_config_key: day_boundary_time   # top level; "legacy" block still read
  derivable_from_contents: [time]   # never [date]

folder_tail:
  named:      ' - (?P<description>.+)$'
  container:  ' - __CONTAINER__(?:\((?P<counts>[divsew]=\d+(?:_[divsew]=\d+)*)\))?(?: - (?P<description>.+))?$'
  to_split:   ' - __TO_SPLIT__\((?:(?P<counts>[divsewf]=\d+(?:_[divsewf]=\d+)*)|(?:(?P<empty_counts>[divsewf]=\d+(?:_[divsewf]=\d+)*)_)?(?P<empty>EMPTY))\)(?:_(?P<discriminator>\d+))?$'
  to_label:   ' - __TO_LABEL__$'
  legacy_placeholder: ' - 1\. ######$'
  markers: ["__CONTAINER__", "__TO_SPLIT__", "__TO_LABEL__"]
  count_letters: [d, i, v, e, c, s, w, f]   # fixed order, joined by "_"
  count_meaning:
    d: direct dated child folders
    i: top-level images
    v: top-level videos
    e: distinct subjects named by the subtree's sidecars, written only when != media count in subtree
    c: sidecars beyond the first for any one subject; written whenever there are any
    s: non-sidecar files below the top level
    w: videos in __VIDEOS_TO_RENAME awaiting a name; a request to the cleanup tool
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
  may_nest_exception: ["__EXIF", "__PREVIEWS"]   # S2 / X11: sidecar folders, one level
  tool_written:
    - "__DUPLICATES"
    - "__EDITED"
    - "__EXIF"
    - "__EXPORTED"
    - "__GEOLOCATIONS"
    - "__HASHES"
    - "__PREVIEWS"
    - "__RAW"
    - "__RAW_EXTRACTED_JPGS"
    - "__RESIZED"
    - "__VIDEOS_EXTRACTED"
    - "__VIDEOS_TO_RENAME"          # purpose fixed by V8
  legacy:                           # S5: recognised when read, never written
    - "__VIDEOS"
    - "__EXTRACTED_VIDEOS"
    - "__EXTRACTED"                 # renamed to __RAW_EXTRACTED_JPGS
    - "__2_SHARE"                   # renamed to __TO_SHARE
  hand_curated:                     # recognised, never auto-populated
    - "__TO_SHARE"
    - "__3D"
    - "___OTHER"
    - "__PANORAMAS"
    - "__PEOPLE"
    - "__SHARED"

files:
  leading_stamp_required: true
  leading_stamp_exemptions: ["^__TO_RENAME__", "unkeyed derivative in __EDITED"]  # V10, D5
  markers:                            # in-name markers, distinct from folder_tail.markers
    raw: "RAW__"                      # F2
    to_rename: "__TO_RENAME__"       # V8; a prefix, anchor it to ^
    author: "@"                       # F8; sigil opening the author token
    estimated_stamp_reserved: "__EST__"   # V5: reserved, nothing writes it today
  grammar: "<stamp>[__RAW]__f<ap>__T<exp>__L<focal>__I<iso>__<CAM>[__@<AUTHOR>][_HAS_RAW|_FROM_RAW][_HAS_EDIT].<ext>"
  raw_marker: "RAW__"
  raw_extension_case: upper
  lossy_extension_case: lower
  author_marker:                      # F8 -- who took it, vs <CAM> = what took it
    token: "__@<SYMBOL>"
    position: after_camera_symbol_before_representative_suffixes
    owner_symbol: ""                  # F8a: the archive owner carries no marker
    table: author_symbols             # config; name -> symbol, no built-in list
    unknown_name: write_nothing_and_report          # F8d: never fall back to the owner
    sources: [ingest_batch, exif_artist]            # F8e, both through the one table
  representative_suffixes: ["_HAS_RAW", "_FROM_RAW", "_HAS_EDIT"]   # fixed order
  representative_suffixes_exclusive: ["_HAS_RAW", "_FROM_RAW"]      # F3a
  legacy_representative_suffixes: ["_RAW", "_EXT", "_EDT"]          # F3b: read, never written
  collision_suffixes:
    duplicate: "_DUPE_<md5>_<n>"
    differing: "_DIFFERS_<md5>_<n>"
    low_resolution: "_LOWRES"
  top_level: representatives_only
  max_representatives_per_shot: 1
  absent_field_placeholders:          # V2: written, never omitted
    aperture: "fNA"
    exposure: "T---"
    focal_length: "LNA"
    iso: "I---s"
    camera: "NOID"

videos:
  placement: top_level_beside_images  # V1 — a video is media, not a companion
  sidecars_share_image_exif_dir: true # V3 — one __EXIF per dated folder
  counts_as: v
  estimated_stamp_reserved:          # V5: reserved, NOT implemented
    marker: "__EST__"
    written_today: false
    open_question: which neighbours to interpolate between
  unresolvable:                       # V8 — tagged AND moved, never one alone
    tag: "__TO_RENAME__"
    tag_position: prefix
    name: "__TO_RENAME__<original name>"
    keep_original_name: byte_for_byte
    subfolder: "__VIDEOS_TO_RENAME"
    companions_travel_with_it: true   # V8c — the one exception to sidecars_share_image_exif_dir
    exempt_from_leading_stamp: true   # V10
    warn: true
    folder_count_letter: w
    resolved_by: [write_real_stamp, drop_tag, move_to_top_level, decrement_w]  # V11
    cleared_by: interactive_cleanup_tool   # V9, not yet implemented

sidecars:
  extensions: ["._exif"]
  naming: "<full media filename><sidecar extension>"
  match_by: trailing_extension        # not by stripping the media extension
  expected_ratio: one_per_media_file
  travels_with_media: true
  placement:                          # X10-X13
    subfolder: "__EXIF"
    relative_to: folder_holding_the_subject
    depth_below_subject: 1
    segregated_by_media_kind: false   # stills and videos share one __EXIF per folder
    nests_inside_other_subfolders: true    # the S2 exception; sidecar folders only
    may_contain: [sidecars]           # never media, never further subfolders
  previews:                           # X6-X9; placed by the same rule
    subfolder: "__PREVIEWS"
    extensions: [".thm", ".lrv"]
    naming: "<full media filename><preview extension>"
    counts_as: s                      # never i/v, never e
    may_be_representative: false

extensions:
  lossy_images: [".jpg", ".jpeg"]
  other_images: [".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"]
  raw_images:   [".arw", ".cr2", ".crw", ".dng", ".mpo", ".rw2"]
  videos:       [".mp4", ".mov", ".avi"]
  previews:     [".thm", ".lrv"]      # sidecars, not media — X6; ".thm" was a lossy image
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
