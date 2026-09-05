# Photo & Video Archive Standard

**v1.0 — settled. Partially enforced by the restructure tool.**

The target structure of the photo + video archive on disk. It exists to (a) drive
the redesign of the **already-archived** material and (b) serve as the contract
that Photosorter and any third-party tool — group renamers, viewers, dedupers —
implement against. A tool that reads this file and follows §1–§7 will produce
folders and names the rest of the archive can join.

Only the sections explicitly marked implemented are enforced. Existing tools
are **not** otherwise assumed compliant.

**What v1.0 means, and what it does not.** Every rule here is decided: a tool
implementing one is implementing its final form, not a proposal that may move
underneath it. It does not mean the archive complies, and it does not mean this
repo implements all of it — §7's fixing tool is still to be built. The sections
marked *Implemented* say what is enforced today; the rest is a contract waiting
for its tool.

**Conformance:** MUST / SHOULD / MAY as in RFC 2119. Every rule has a stable ID
(`P1`, `N3`, …); cite the ID when reporting a violation. §8 is the normative
machine-readable form of everything above it — parse that, not the prose.

---

## 1. Path — `P`

```text
<ROOT>/<YYYY>/<NN>. <Month>/<dated folder>[/<dated folder>…][/<__SUBFOLDER>]
<ROOT>/<YYYY>/__DUPLICATES                    <- the one year-level subfolder (S7)
```

| ID | Rule |
| --- | --- |
| P1 | `<ROOT>` is configured per run. Only its four-digit `<YYYY>` children are in scope; every other root entry is a working area and MUST be left alone (see §0 below). |
| P2 | Year folder name is exactly four digits. Nothing else at that level. |
| P3 | Month folder is `NN. Month` — zero-padded number, dot, space, **fixed English** month name (`01. January` … `12. December`). Never locale-derived. |
| P4 | Below a month folder, every directory MUST be a dated folder (§2) — leaf or group (§3) — an allowed subfolder (§4), or a parking area (§4.1). There is no fourth kind. |
| P5 | The year and month a folder sits under MUST match the date in its own name, after the N7 day shift. |
| P6 | Directly under a year folder sit its **month folders** and, optionally, **one `__DUPLICATES`** (S7). There is no third kind. A tool MUST NOT read `__DUPLICATES` as a month folder, and MUST NOT walk into it looking for dated folders: what is in it lost a name collision and is waiting for a person, not for the next pass. |

### §0 Out of scope

Only `<YYYY>` trees are governed. A conforming tool MUST NOT descend into any
other root entry or report its contents. Present at the root today:

| Entry | What it is | Fate |
| --- | --- | --- |
| `____INGEST_PIPELINE` | Pipeline working folder (`INBOX`, `READY`, `.TMP`) | Transient |
| `____TO_SORT` | Legacy working folder | Transient |
| `__PROCESSED` | Edits and derivatives made outside the pipeline | **Migration source** — see §0.1 |
| `__LOGS` | Rename/restructure run journals (`_rename_journal_*.jsonl`, `_restructure_journal_*.jsonl`) | Tool bookkeeping — see §0.3 |
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
| D3 | Instead, **the dated folder supplies the date the filename lacks**: an unkeyed derivative MUST still come to rest inside the `__EDITED` of the event folder it belongs to, and its own name is kept byte for byte. The folder is then the only claim being made, and it is one a person made. That folder is a **leaf** (§3) — not because leaves are more precise but because a group may hold no `__EDITED` at all (C3), so there is no other legal resting place. |
| D3a | **"Somewhere in the trip" is not an attribution.** A person who can name the group but not the day has not finished D4, and no rule here finishes it for them: the file stays in `__PROCESSED` and is reported every run until someone picks a leaf. Reporting the same file indefinitely is the intended behaviour, not a defect — it is the archive saying a decision is outstanding. |
| D4 | Attributing an unkeyed derivative to an event is a **human decision**, not a tool's. Until someone makes it, the file stays in `__PROCESSED` and is reported. A tool MUST NOT distribute unkeyed derivatives by guesswork. |
| D5 | D3 is the **second exemption from F1** (after V10): a file inside `__EDITED` may open with something other than a stamp. A compliance checker reports it as unkeyed, not as malformed. |

**Settled — v1.0.** This section used to ask whether event-level attribution
was enough, or whether D3 should demand the sub-event folder. C3 answers it:
the only dated folder that may hold an `__EDITED` is a leaf, so "the event
folder" can only ever have meant the leaf, and the question was really about
what happens to a derivative nobody can place that precisely. D3a says: nothing
happens to it. It waits in `__PROCESSED`, reported, which is where D4 already
put it.

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

### §0.3 `__LOGS` — run journals

`tools/restructure_archive.py` and `tools/canonicalise_timestamp_names.py` each
append-only journal what an applied run did, so the run can be replayed
backwards (`--undo`) or audited afterwards. A journal is dated and reopened on
every applied run, so it cannot sit inside a `<YYYY>` tree without becoming a
standing violation: a year folder's only permitted children are month folders
(P2/P4), and a journal that outlives one run would keep appearing on the next
walk. It is written instead to `__LOGS`, directly under the same root its
target's year folder sits under — the same working-area level as
`____INGEST_PIPELINE`.

| ID | Rule |
| --- | --- |
| J1 | A journal is **never** written inside a `<YYYY>` tree. Its default location is `__LOGS` beside the year folders, resolved from whatever `target` a run was given — one level up when `target` is itself a year folder, directly under it otherwise. |
| J2 | `__LOGS` is **tool bookkeeping only**: no rule in §1–§7 governs its contents, and a conforming tool MUST NOT report what is in it as a violation. |
| J3 | An explicit `--journal <path>` overrides the default outright; that path is used exactly as given, `__LOGS` or not. |

**Implemented** — `log_directory` in `tools/canonicalise_timestamp_names.py` is
the one definition (T8); `tools/restructure_archive.py` calls it for its own
journal rather than restating the rule.

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
| N3 | The time is the capture time of the folder's earliest file: earliest media where there is any, otherwise earliest `._exif` sidecar. For a group (§3) it is the earliest file in its whole subtree, and the group also carries the latest (C8). |
| N4 | Two folders in one month folder MUST NOT share a name. The time is what separates two events on one day — which is why date-only is legal but discouraged. |
| N5 | Historical prefixes `YYYY-MM-DD_(Ddd)_HH.MM.SS` (single underscore) and `YYYY-MM-DD__HH.MM.SS` (no weekday) MUST still be **read**. They MUST NOT be newly **written**. |
| N6 | Only the **time** half of a prefix may ever be derived from folder contents. The **date** MUST NOT — rewriting it would move the folder out from under its month folder. A date that cannot exist (`2026-02-31`) is reported, never invented. |
| N7 | **Day boundary.** A capture at or before `04.44.44` (configurable) belongs to the **previous** day's folder. A night running past midnight is one event. Consequence: a folder's date may legitimately be one day earlier than some of its files. |

**Implemented (N3)** — `with_corrected_time` in `grouping_names.py`, applied to
every event folder by `tools/canonicalise_timestamp_names.py`. N3 is an
equality, not a default: a prefix whose time disagrees with the folder's
earliest file is **corrected**, not left standing, since a folder stamped
before a later pass moved its early shots into a sibling names a photograph
that is no longer in it. Only the time moves (N6), and T7 does not shield it —
a labelled folder is retimed and its description kept (C11 says the same for a
group). Two folders are never retimed this way: a group, whose prefix carries a
span maintained at both ends together (C11), and one whose earliest file is
outside the pair of days N7 allows it — that one is reported as `MISTIMED`,
because one misfiled stray must not rewrite the name of a day that was right.
`--keep-times` restores the older behaviour of filling a blank only.

### Tails

| ID | Tail | Meaning |
| --- | --- | --- |
| N8 | ` - <description>` | Named by a human. **Finished** — no tool rewrites the tail. |
| N9 | ` - ____GROUP____[(d=N)][ - <description>]` | Holds dated child folders and nothing else. Its prefix carries both ends of the span. The description slot may hold N11 instead of a name. See §3. |
| N10 | ` - __TO_SPLIT__(<counts>)` | Day still to be split into sub-events. |
| N10a | ` - __TO_SPLIT__([f=N_]EMPTY)[_<n>]` | Holds no files anywhere in its subtree. The counts it carried go — there is nothing left to count. `f` states how many hollow subfolders still stand. |
| N10b | An `EMPTY` folder with no time takes `00.00.00`, so it still satisfies the full prefix of N1 rather than falling back to date-only. A folder emptied after it was named keeps its real time — N6 still forbids revising one. |
| N11 | ` - __TO_LABEL__` | Still to be described. On a day, the whole tail. On a group, the description slot after the marker (` - ____GROUP____(d=3) - __TO_LABEL__`), since C1 keeps the marker first. It is a **question addressed to a person, not a description**: a tool reading a name must not treat it as one, or T7 would protect the one word meant to be replaced. Written by C16; removed the moment anything answers it. |
| N12 | ` - 1. ######` | Legacy placeholder. Read and converted to N10; never newly written. |
| N13 | ` - __CONTAINER__[(d=N)][ - <description>]` | Legacy spelling of N9. Read and converted; never newly written. See C15. |

**Count bracket** (N9/N10): letters in the fixed order `d i v e c s w f`, joined by `_`.

| Letter | Counts | Written when |
| --- | --- | --- |
| `d` | direct dated child folders | the folder is a group |
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

## 3. Groups — `C`

A **group** is a dated folder whose contents are other dated folders. It is the
archive's only nesting device, and it is one device, not two: a day split into
sub-events and a two-week trip to Norway are the same shape, differing only in
how far the span runs. Nesting is unlimited; two levels (trip → day, or day →
sub-event) is the norm.

A group holds **no media of its own** — that is what separates it from a leaf
dated folder, and it is why the marker is `____GROUP____`, four underscores each
side, the loudest sigil in the archive and the one the root working folders
carry (§0). A person who opens one is looking at structure, never at
photographs; a tool that meets one knows there is nothing in it to review, rate,
stamp or de-duplicate at this level.

| ID | Rule |
| --- | --- |
| C1 | A dated folder holding ≥1 dated child folder MUST carry `____GROUP____` as the **first element of its tail**, so it is distinguishable from a leaf at a glance and by regex: `2026-08-20_(Thu)__09.14.02#2026-08-27_(Thu)__18.31.50 - ____GROUP____(d=7) - Norway`. |
| C2 | A leaf dated folder MUST NOT carry the marker. Adding or removing the last dated child flips it; a conforming tool maintains it. |
| C3 | **A group's contents are closed.** Exactly four kinds may sit in one: dated leaf folders, dated groups, at most one parking area (§4.1) holding the children it has emptied, and at most one `__GEOLOCATIONS` (C3a). No media, no loose files of any kind, and no other taxonomy subfolder (§4) — a group has no files for an `__EXIF` or a `__RAW` to be about. |
| C3a | **`__GEOLOCATIONS` is the one taxonomy subfolder a group may hold.** A track covering a fortnight in Norway is about the *group*, the way a sidecar is about one shot: filing it under the day it happens to start says something false, and cutting it into seven daily fragments edits a recording to fit the folders. So it is admitted here, and narrowly — geodata only (§8 `extensions.geodata`), never media, never a further subfolder — which leaves C3's real claim standing: a person or a tool that opens a group still finds nothing in it to review, rate, stamp or de-duplicate. A `.gpx` whose span fits inside one dated child belongs in **that child's** `__GEOLOCATIONS`; this one is for the tracks no single child can hold. It is *hand* in the sense of S3: recognised and preserved, never auto-populated — deciding a track spans a whole group is a reading of the track. Its contents are **excluded from the group's span and from its counts**, exactly as a parking area's are (H5, C14): a group states the extent of the photography it holds, and a track is a record of the trip, not a shot taken during it. |
| C4 | Loose media met in a group is **moved down, never deleted and never renamed**: the shots are gathered into a dated child folder of their own by the ordinary rules — day boundary per N7, time per N3, tail ` - __TO_LABEL__` because no person has named them yet — and their sidecars and companions travel with them (X10), which carries the taxonomy subfolders holding those companions down one level too. A tool MAY perform this: the child it creates invents no date (N7 fixes the day, N3 the time) and no name (`__TO_LABEL__` is precisely the refusal to name one), which is what separates it from the inventions N6, D4 and V4 refuse. It writes only under `--apply`, and only after naming the group, the shots and the child it proposes, and getting a yes — the way step 2 prompts. Without `--apply` it reports. This is a **migration action**; after it, nothing ever writes media into a group again. |
| C5 | A group uses the **same prefix convention** as any dated folder (§2). Its start is the capture time of the earliest file in its **whole subtree** (N3). |
| C6 | **A group states both ends of its span, always** — `#<end>` appended directly to the dated prefix, before the tail. The name therefore carries an initial timestamp and a final one, and the range between them is exactly the extent of what the group holds. |
| C7 | The end states **all of the date or none of it**. A span that closes on the day it opened writes the time alone — `#17.47.04` — because the start, two characters to the left, has already said which day. One that crosses a day writes the whole canonical stamp of N1, weekday included — `#2026-08-27_(Thu)__18.31.50`. There is no third case and no abbreviation: a fragment like `#27` made the reader carry the start's year and month across the `#` to work out which day was meant. |
| C8 | The end **time** is the capture time of the latest file in the subtree, in the same `HH.MM.SS` form as the start, and is always written. A cross-day end is therefore literally `format_stamp` of that instant: one grammar either side of the `#`, so a reader meets the same shape twice rather than a stamp and an abbreviation of one. |
| C9 | A single-day group still states its end, as the time — `…__11.03.27#22.14.09`. The claim is the same as a cross-day group's; only the half that would repeat the start is left off. A parser tries the time-only shape **first**: offered to the date branch, `#17.47.04` matches `#17` and leaves `.47.04` standing as tail, silently reading a time as the 17th of the month. |
| C10 | The **start** keeps the full canonical prefix (C5) and leads the name, so alphabetical order stays chronological and every parser still reads the start date and time unchanged. |
| C11 | **Both ends are tool-maintained.** Any run that adds, removes or retimes anything in the subtree recomputes the pair and renames the group. T7 — a folder named by a human is finished — protects the **description** in the tail, never the stamp. |
| C12 | A group sits under the month folder of its **start** (P5). If the earliest file in the subtree leaves and the start crosses into another month or year, the group moves with it — but never silently: a folder holding a fortnight of someone's life changing month is too large a surprise for a batch pass, so a tool moves it only under `--apply` and only after naming the group, the month folder it is in and the one it is bound for, and getting a yes. One prompt per group; a run that is refused reports and moves on, and P5 stands violated until a person says yes or moves it by hand. The date is still never invented (N6); it is read off the contents, which is the one thing a group's own name is made of. |
| C13 | A child's date MUST fall within the group's span ±1 day. A sub-event split near the day boundary can land on the neighbouring date; anything further is a violation. |
| C14 | Of the count letters (§2) only `d` — direct dated children — is ever written on a group. `i`/`v` cannot occur, C3 having removed them; `e`/`c`/`s`/`w` describe files a group does not hold. The one thing it may hold, a trip-wide track in `__GEOLOCATIONS` (C3a), is **not counted**: it would show up as `s`, and `s` exists to warn that files are hiding below the top level where a reviewer will not meet them. A track is not hiding. It is filed. |
| C16 | **A group nobody has named says so.** Its description comes from one of three places, in this order: a person (the group's own description, or the label it carried before it had children — never re-derived, T7); **agreement among its children**, when every direct dated child carries the same description, which invents nothing and is adopted verbatim; or, failing both, N11's `__TO_LABEL__` in the description slot. Anything short of unanimity — one child unnamed, or two disagreeing — is a name the tool would be making up, and N6's refusal to derive a date from contents is the same refusal one step over. The marker is deliberately **not sticky**: it is re-asked on every run, so a group picks up a name the moment its children agree on one or a person types one in. |
| C15a | The abbreviated ends `#27`, `#09-11` and `#2027-01-03`, with or without a `__HH.MM.SS` after them, are **legacy spellings** of C7 — read-old/write-new, the same rule as N5 and C15. They MUST still parse; none is written again. |
| C15 | `__CONTAINER__` is the **legacy spelling** of this marker. No tool ever wrote one — §3 proposed it and nothing implemented it — so the rename costs no folder on disk anything; a folder carries one only because a person typed it, or because a third party read this document at v0.8. It MUST still be **read** and converted; it MUST NOT be newly **written**, the same read-old/write-new rule as N5 and S5. |

```text
2026\
  07. July\
    2026-07-15_(Wed)__08.14.02#2026-07-16_(Thu)__21.40.55 - ____GROUP____(d=3) - Sopot weekend\
        2026-07-15_(Wed)__08.14.02 - morning beach\
            2026-07-15_(Wed)__08.14.02__f1.7__T1_180__L23.0.eq__I12__SG23U_HAS_RAW.jpg
            __EXIF\                          <- sidecar for the .jpg above it (X10)
            __RAW\
                2026-07-15_(Wed)__08.14.02__RAW__f1.7__…__SG23U.ARW
                __EXIF\                      <- sidecar for the RAW beside it (X11)
        2026-07-15_(Wed)__14.02.55#16.20.31 - ____GROUP____(d=1) - pier\
            2026-07-15_(Wed)__14.31.09 - the gulls\
        2026-07-16_(Thu)__09.10.44 - __TO_LABEL__
            __GEOLOCATIONS\                  <- the day's track, inside the day (C3)
        __EMPTY_SUBFOLDERS\                  <- sub-events this group has emptied (H2)
            2026-07-17_(Fri)__00.00.00 - __TO_SPLIT__(EMPTY)
    __EMPTY_SUBFOLDERS\                      <- days this MONTH has emptied (H2)
    2026-08-20_(Thu)__09.14.02#2026-08-27_(Thu)__18.31.50 - ____GROUP____(d=7) - Norway\
        2026-08-20_(Thu)__09.14.02 - flight and Bergen
        2026-08-21_(Fri)__07.30.11#2026-08-23_(Sun)__19.02.44 - ____GROUP____(d=3) - the fjords\
            2026-08-21_(Fri)__07.30.11 - Nærøyfjord
            2026-08-22_(Sat)__06.55.02 - Flåm
            2026-08-23_(Sun)__08.11.19 - the drive north
        2026-08-27_(Sat)__11.02.09 - going home
        __GEOLOCATIONS\                    <- the whole trip's track (C3a)
    2026-07-18_(Sat)__11.03.27 - __TO_SPLIT__(i=79_v=2_w=1)\
        2026-07-18_(Sat)__11.03.27__fNA__T---__LNA__I---s__SG23U.mp4
        __EXIF\                              <- stills and videos share it (V3)
        __VIDEOS_TO_RENAME\
            __TO_RENAME__VID_0034.mp4
            __EXIF\                          <- travels with the video (V8c)
```

### Implemented

Step 6 of `tools/restructure_archive.py` — "Mark and time the groups". It
maintains C1, C2, C6–C11, C14 and C16: the marker, the two stamps, the `d`
count and the description, rebuilt from the subtree on every run and renamed
where they disagree with it. `GROUP_MARKER`, the tail grammar, the `d` bracket
and the three readings C16 rests on — `folder_description`,
`shared_child_description` and `awaits_label` — live in
`src/pipeline_stages/grouping_names.py`; the `#` span end and its time live in
`src/pipeline_stages/stamps.py` (T8). The step reports what it named from
agreement and lists every group left carrying `__TO_LABEL__`, which is a
request to a person rather than a violation: a group with no name is a
conforming group.

C3 is **reported, never fixed**: media, loose files and taxonomy subfolders
inside a group are named with the rule they break and left where they are.
Moving them down is C4 and moving a group between month folders is C12 — both
settled rules since v1.0, and both the job of §7's fixing tool, which is not
built yet. Step 6 names them and says exactly that. The same goes for a day
that carries `__TO_SPLIT__` *and* has dated children *and* still has shots at
its top level: it is a group by C1 and a day awaiting the grouper at once, and
dropping either half would strand something.

**Why the span is written out and not computed.** Every other derived field in
this document is written into the name too — the counts, the weekday, the
group marker — for one reason: the archive is browsed by people in Explorer
and by tools that have not walked the subtree. A trip's dates are the first
thing a person wants from a folder they are looking at rather than opening, and
the second thing a checker wants before it decides whether to descend at all.

---

## 4. Subfolders — `S`

Inside a dated folder, exactly these are permitted. All optional.

| Folder | Holds | Written by |
| --- | --- | --- |
| `__TO_SHARE` | Queued for sharing — not yet sent | hand |
| `__3D` | Stereo / 3D captures (MPO etc.) | hand |
| `___OTHER` | Fits nowhere else — **three** leading underscores | hand |
| `__DUPLICATES` | Burst discards, unused brackets, accidental / low-res duplicates. Also the one subfolder permitted at the **year** level, where collision losers go — S7 | tool |
| `__EDITED` | Non-destructive edits and masters — `.xmp`, `.psd`, high-bit `.tif` | tool |
| `__EXIF` | `._exif` sidecars, JSON camera logs | tool |
| `__EXPORTED` | Full-resolution exports for print/archive | tool |
| `__GEOLOCATIONS` | `.gpx` tracks and other event geodata | tool |
| `__HASHES` | Content hashes / integrity records | tool |
| `__OCR` | Text recognised out of an image — `.OCR.txt`. See X15 | tool |
| `__PANORAMAS` | Panorama sources and stitches | hand |
| `__PEOPLE` | Per-person crops / selections | hand |
| `__PREVIEWS` | Camera thumbnails and low-res proxies — `.thm`, `.lrv`, `.THM.jpg`, `.PREVIEW.jpg`. See X6 | tool |
| `__PROCESSED` | Edits and derivatives of this event's shots, made outside the pipeline. Same contents as the root folder of that name (§0.1), already attributed to one event | hand |
| `__RAW` | RAW originals, untouched | tool |
| `__RAW_EXTRACTED_JPGS` | JPEGs extracted from a RAW for a shot that already has a camera JPEG | tool |
| `__RESIZED` | Downscaled derivatives for web, social, email | tool |
| `__SHARED` | Already shared | hand |
| `__VIDEOS_EXTRACTED` | Video extracted out of other media | tool |
| `__VIDEOS_TO_RENAME` | Videos that could not be dated — tagged `__TO_RENAME__` (V8) | tool |

| ID | Rule |
| --- | --- |
| S1 | The set is **closed**. Any other subfolder is a violation — except a dated child folder (§3), which is structure, not a violation. |
| S2 | Subfolders MUST NOT nest inside each other, with one exception: a folder holding media may hold its subjects' sidecar folders, `__EXIF`, `__PREVIEWS` and `__OCR` (X10–X15). So `__RAW\__EXIF\` is legal and `__RAW\__EDITED\` is not. |
| S3 | Folders marked *hand* are recognised and preserved but MUST NEVER be populated automatically. |
| S4 | A tool MUST read these names from §8, not restate them as literals. |
| S5 | **No video folder in the ordinary case.** A datable video is a representative at the top level (V1). `__VIDEOS` and `__EXTRACTED_VIDEOS` were an earlier arrangement: they are **read** — recognised case-insensitively as taxonomy folders so an existing Windows archive is not reported as malformed and its companions can still be reunited — and **never written**, the same read-old/write-new rule N5 applies to timestamps. The restructure migration drains `__VIDEOS` per V12; `__EXTRACTED_VIDEOS` remains only recognised. |
| S6 | `__PROCESSED` inside a dated folder is the **resting place a person chose** for derivatives the root `__PROCESSED` held (§0.1). It is recognised and preserved and, being *hand* (S3), never written to: D3 still routes what a tool can key automatically into `__EDITED`. Its files travel with their subject like any other subfolder's when an event is split. |
| S7 | **`__DUPLICATES` sits at the year level too** — `<YYYY>\__DUPLICATES`, beside the month folders (P6) — and that is where a tool parks a file that lost a name collision (F4, L3, and the placement rules of §6). One folder per year rather than one per event, because a collision loser is something a person has to look at and decide about, and a year's worth of them scattered across four hundred event folders is a review nobody performs. The in-event `__DUPLICATES` keeps the job the table describes — burst discards and unused brackets, put there deliberately, belonging to that event. Nothing migrates between the two: they answer different questions, and a tool MUST NOT drain one into the other. |

### Implemented

`src/pipeline_stages/taxonomy.py` is the single definition (T8/S4).
`default_config()` writes no `taxonomy` block, so there is nothing to keep in
step with it; `LEGACY_TAXONOMY` in the same module carries the two retired names
for S5. Videos are routed to the top level by `folder_sorting.py`.

S7 is implemented: `duplicates_folder` in `tools/restructure_archive.py` answers
"where does a collision loser go" with the `__DUPLICATES` of the **subject's own
year tree**, so a run spanning several years parks each year's losers under that
year rather than pooling them. Both callers that can meet a collision take it as
a parameter — companion placement (§6) and the legacy-container migration (L3) —
so there is one answer, not two. The folder is excluded from the next run's
index, or its contents would be re-reported as orphans forever.

### 4.1 Parking areas — `H`

A **parking area** is a named folder that sits **where dated folders sit** —
directly under a month folder, or inside a group beside its dated children —
and holds folders taken out of circulation rather than media of its own. It is
a sibling of what it takes, which is the whole of its placement rule: a day
emptied out of a month folder is parked in that month folder, a sub-event
emptied out of a group is parked in that group, and neither leaves the level it
was on.

It is not a taxonomy subfolder: those live *inside* an event folder and hold
that event's files. It is not a group either: a group is dated, described and
full of live events (§3), where a parking area is undated, machine-named, and
the place things go to stop being offered for review.

| ID | Rule |
| --- | --- |
| H1 | A parking area MUST carry no dated prefix, so a scan looking for dated folders neither matches it nor mistakes it for an event. A restructuring tool MUST NOT descend into one after it has normalized the parking areas: parked folders are records, not live events. |
| H2 | A parking area MAY appear at any level where a **dated folder** may appear — as a direct child of a month folder, or of a group (§3) — at most one per level, created on first use. It MUST NOT appear anywhere else, and in particular never inside a **leaf** dated folder or inside a taxonomy subfolder: those hold one event's files, and a parked folder is not one of them. |
| H3 | It holds **dated folders**, which keep their own names and go on obeying §2, plus legacy-container folders verified absolutely empty under L4. Moving a folder into one does not otherwise rename it. |
| H4 | The set is closed, as §4's is. Today there is exactly one: `__EMPTY_SUBFOLDERS`, for day folders emptied of every file — parked rather than offered to a grouper. |
| H5 | A parking area contains no loose files of its own and is never treated as a dated group. Its dated children are excluded from grouping, companion reconciliation and group-span calculation — so a group's span (C6) is computed as though its parking area were not there, and parking a folder never restates the span. |
| H6 | A parking area found where H2 does not allow one — inside a leaf dated folder, inside a taxonomy subfolder — is **hoisted to the nearest level above it that does**: the first month folder or group on the way up. Its entries are merged into that level's parking area, a name already taken gaining `_2`, `_3` … rather than being overwritten. Once every entry has moved and the shell is verified to hold nothing at all, the shell is removed (T1). An unreadable or non-empty shell is left exactly where it is and reported. |
| H7 | A parking area **above** the level it should be on — directly under a year folder, say — is reported and never moved. Pushing one down would mean deciding which month each folder in it belongs to, which is a different question from hoisting and nobody has asked it. |
| H8 | Parking the last dated child out of a group makes that group a leaf (C2), which makes its parking area misplaced under H2. The next run strips the marker and hoists the area; the two rules settle in that order, and a run that finds the intermediate state has not found a violation to be alarmed about. |

**Implemented** — `hoist_parking_areas` in `parking.py`, run before each
reconciliation pass by `tools/restructure_archive.py`. The same module owns
`parking_area_for`, the one answer to "where does this go", used by the grouper
stage and by the legacy-container migration alike (T8).

H4's own case — a day folder emptied of every file — is applied by
`park_empty_dated_folders` in `tools/restructure_archive.py`, in the same step
that marks it: the canonicaliser is what establishes that a folder holds no
file anywhere (N10a), so the folder is parked there and then rather than left
in the month for every later run to notice again.

**Empty means no files**, at any depth; subfolders below it are not files and
do not keep a folder out — they travel with it, which is what `f=N` in the
name is still counting after the move. **Every dated folder is a candidate**,
whatever it is called: marked, placeholdered, or named by a person. H4 is about
what a folder holds, and H3 parks it under its own name, so nothing a name
recorded is lost by moving it. Emptiness is re-read off the disk before
anything moves, never taken from the `EMPTY` bracket, and a name already taken
in the parking area gains N10a’s discriminator. A folder still holding a dated
child is left for the next run, which is H8.

### 4.2 Legacy containers — read, migrated, never written

Before every subfolder gained its `__` prefix the legacy CLI wrote a different
set, and an archive this old is still full of them. They are **recognised** so a
walk does not report them as unknown folders, and **migrated** where a modern
folder corresponds:

| Legacy container | Becomes | |
| --- | --- | --- |
| `##   RAWs   ##` | `__RAW` | migrated |
| `##   EXIFs   ##` | `__EXIF` | migrated |
| `old_EXIF` | — | reported; the sidecars in it were already judged stale |
| `##   UNSUPPORTED EXTENSIONS   ##` | — | reported |
| `##   EMPTY FILES   ##` | — | reported |
| `##   NOT_ENOUGH_INFO FILES   ##` | — | reported |
| `##   DUPLICATE_FILE_NAMES FILES   ##` | — | reported |

| ID | Rule |
| --- | --- |
| L1 | A legacy container MUST NOT be newly written. Same read-old/write-new rule as N5 and S5. |
| L2 | Migration is a **rename** where the modern folder does not exist, so it cannot half-finish; a **file-by-file move** where it does. |
| L3 | A name collision during the move is settled by **checksum**, never by overwriting: identical is parked `_DUPE_`, different `_DIFFERS_` (F4). |
| L4 | A container left **absolutely empty** — no file anywhere beneath it, checked and not assumed — is parked in the parking area **beside the dated folder it sat in** (H2: the nearest month folder or group above it), numbered `_2`, `_3` … when that name is taken. One still holding anything is left where it is and reported. |
| L5 | A container with **no modern equivalent** is never emptied automatically. Where its contents belong is a decision for a person. |

**Implemented** — `migrate_legacy_containers` in `companion_matching.py`, run by
the restructure tool. The names are read through `legacy_container_targets` in
`taxonomy.py`, which honours `config.json`'s `legacy.subfolders` (T8/S4). An
emptied container is parked only after a recursive file check returns empty.

---

### Settled — v1.0

The questions this section carried are answered, and each answer is a rule
above rather than a note here. They keep the numbers they were asked under, so
the gaps are real: 4 and 5 below were 4 and 5 in the draft, and 2 and 3 were
settled in earlier versions and struck then.

- **Q1 — where does a collision loser go?** At the **year** level — S7, P6. What
  companion placement already writes, admitted into the standard rather than
  migrated away from. A collision loser is a question for a person, and a
  year's worth of them in one folder is a review someone can actually sit down
  and do; the same files one-per-event are a review nobody performs. The
  in-event `__DUPLICATES` keeps its own, different job.
- **Q4 — where does a whole trip's `.gpx` go?** In the group's own
  `__GEOLOCATIONS` — C3a. It is the single exception to "a group holds no
  files", and it is drawn narrowly: geodata only, excluded from the span and
  the counts, never auto-populated. What made a group cheap to walk was that
  there is nothing in it to review, and a track does not change that. The
  alternatives both damaged something real — filing a fortnight under the day
  it started says something false, splitting it per day edits the recording to
  fit the folders.
- **Q5 — may the tool create the `__TO_LABEL__` child C4 calls for?** Yes — C4 —
  under `--apply` and after a prompt. What N6, D4 and V4 refuse is *invention*:
  a date deduced from a filename, a name deduced from contents. This child
  invents neither. Its day comes from N7 and its time from N3, and
  `__TO_LABEL__` is the refusal to name it. Prompting is what keeps a
  mechanical move from being a silent one.
- **Q6 — what happens when C12 moves a group across a month folder?** It moves —
  C12 — under `--apply` and after a prompt, one per group. P5 is kept, which
  the report-only alternative gave up on, and no fortnight of someone's life
  changes month unannounced, which is what made moving it automatically the
  wrong answer.

Settling is not implementing. Q1 is what the placement pass already does; Q4 is
a folder a person files into; Q5 and Q6 are obligations of §7's fixing tool,
which does not exist yet and reports in the meantime.

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
| F4 | Collision suffixes: `_DUPE_<md5>_<n>`, `_DIFFERS_<md5>_<n>`, `_LOWRES`. `_DUPE` is a byte-identical loser; `_DIFFERS` is one that claimed the same name with **different** bytes, which is a defect a person has to settle. Both are written by companion placement (§6), and by the legacy-container migration when it meets the same collision (L3). The loser is parked in the **year-level** `__DUPLICATES` (S7), never beside the file whose name it lost. |
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
| V12 | **Legacy `__VIDEOS` migration.** The restructure tool treats the folder name case-insensitively. A video whose filename already opens with a readable stamp moves one level up unchanged. Otherwise only intrinsic camera/container fields (`Date/Time Original`, `Media Create Date`, `Track Create Date`, `Create Date`) may supply the F-grammar timestamp; filesystem create/modify/access times never may (V4). If ExifTool cannot inspect the file, it is left and reported — failure to read is not proof that no timestamp exists. If inspection succeeds but yields no intrinsic capture time, V8 applies. Sidecars and previews move and are renamed with their subject (X5/X6). Once the legacy folder contains no file anywhere beneath it, it is parked in the `__EMPTY_SUBFOLDERS` beside the dated folder it sat in (L4/H2), preserving any empty directory structure. |

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

**To be implemented — the cleanup tool.** Expected to be the interactive
counterpart of the fixing tool (§7): it lists `w=N` folders, shows each unresolved
video with its anchors, takes the user's decision, and applies it under the same
T1–T8 obligations. Not yet designed.

**Legacy migration is implemented.** `legacy_videos.py`, called by reconciliation
in `tools/restructure_archive.py`, applies V12 before general companion placement.
It reads metadata through the shared `exiftool_sidecars.py` helper and uses the
same archive move, checksum, dry-run and journal boundaries as the other passes.

---

## 6. Sidecars — `X`

**Placement, in one line: a sidecar lives in `__EXIF` directly inside the folder
that holds its subject** — always exactly one level below the file it describes,
wherever that file has ended up. X10–X13 spell out what follows from that.

| ID | Rule |
| --- | --- |
| X1 | A sidecar keeps its subject's **full** name and appends its own extension: `shot.jpg._exif`, `clip.mp4._exif`. |
| X1a | Historical `._exif` names that omit the subject's extension (`shot._exif`) or differ only in extension case MUST still be **read**. They are matched case-insensitively by stem and rewritten to X1 using the subject's actual full name. If a JPEG and RAW share the stem, X10 location disambiguates them; more than one candidate at that location is reported, never guessed. |
| X2 | Therefore `Path.suffix` of a sidecar is `._exif`, never the media extension. That is what keeps sidecars out of media counts — match on the trailing extension, not by stripping it. |
| X3 | Therefore a sidecar carries its subject's capture time in its own name. A folder emptied of media can still be dated from what it left behind (N3). |
| X4 | **One sidecar per media file is the norm.** Any other ratio means a sidecar was orphaned when its image moved, or an image arrived without one — this is what `e` reports. |
| X5 | A tool renaming or moving media MUST carry its sidecars with it, renaming them per X1. Orphaning a sidecar is a defect, not a side effect. |
| X6 | **Thumbnails and previews are sidecars** — a camera `.thm`, a GoPro `.lrv` proxy, any generated preview. They follow X1 (`clip.mp4.thm`, `clip.mp4.lrv`), travel with their subject (X5), and live in **`__PREVIEWS`**. |
| X6a | A preview a tool **generates** rather than lifts off a camera is a JPEG, and names itself with a **compound suffix** — `clip.mp4.THM.jpg` for a thumbnail, `clip.mp4.PREVIEW.jpg` for a full-size one. The compound is what makes it self-identifying: `Path.suffix` alone reads `.jpg` and would count the file as media, which X7 forbids, so previews are matched on the **longest** trailing extension and the compound forms are tested before the plain ones. |
| X7 | A preview is **never** a representative and **never** counted as media: not at the top level, not in `i`/`v`. It is one more file below the top level, so it counts into `s` like any other. |
| X8 | A preview is **not** counted in `e`. `e` compares `._exif` sidecars against media (X4); folding previews in would break a ratio that is only meaningful one-to-one. |
| X9 | A subject may have several previews of different kinds. They are distinguished by their own extensions, never by mangling the subject name. |
| X10 | **A sidecar sits in `__EXIF` directly inside the folder holding its subject** — one level below the subject, never two, never in an `__EXIF` further up. Top-level media (stills and videos alike, V1) therefore share the dated folder's own `__EXIF`; media parked in a subfolder uses that subfolder's `__EXIF`. |
| X11 | It follows that **any folder holding media may hold an `__EXIF`** — `__RAW\__EXIF\`, `__VIDEOS_TO_RENAME\__EXIF\`. This is the single exception to S2, and it exists so that moving a folder carries its sidecars with it instead of stranding them: locality is what makes the move atomic. |
| X12 | The exception is **one level and sidecar folders only**. `__EXIF` holds nothing but sidecars — no media, no further subfolders — and no other subfolder may nest in any other. `__RAW\__EDITED\` stays a violation. |
| X13 | `__PREVIEWS` follows X10–X12 exactly: previews sit beside their subject's `__EXIF`, one level below the subject (`__VIDEOS_TO_RENAME\__PREVIEWS\`). |
| X14 | After X1/X1a reconciliation, a restructuring run MUST generate a sidecar for every RAW still lacking one, using the RAW's own metadata through the configured ExifTool. It writes the canonical X1 name and places it per X10. Generation obeys T2/T3: dry run reports it, and an existing destination is never overwritten. A RAW ExifTool cannot read is left unchanged and reported. |
| X15 | **Recognised text is a sidecar** and lives in **`__OCR`**, by X10's rule exactly — one level below its subject, in the folder that holds it. It follows X1 (`shot.png.OCR.txt`), travels with its subject (X5), and counts into `s`, never into `i`/`v` or `e`. It is not filed in `__EXIF`: that folder holds what a *camera* recorded, where OCR text is a later reading of the picture, regenerable and revisable as engines improve. Keeping the two apart means a stale `__OCR` can be discarded wholesale without touching a single piece of capture metadata. |

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

**Historical EXIF matching and RAW repair are implemented.**
`place_companions` reads stem-form and case-variant `._exif` names under X1a,
uses their X10 location to distinguish a same-stem JPEG from its RAW, and
renames the sidecar onto X1. The reconciliation passes in
`tools/restructure_archive.py` then generate any genuinely missing RAW
sidecars through ExifTool and place them in the RAW folder's own `__EXIF`.

**`__OCR` and generated previews — v0.13, migration in Screenshot Grouper.**
X6a and X15 were added for the tool that actually writes these files: the
screenshot grouper generates `.THM.jpg` / `.PREVIEW.jpg` frame caches for videos
and `.OCR.txt` for images, and had been writing all three beside their subject
in stem form, against F7 and X1. It now names them per X1, reads the historical
stem form under X1a, and places them per X10 — previews in `__PREVIEWS`, OCR
text in `__OCR`. Existing files are converted as they are next moved rather than
in a sweep, so an archive migrates under ordinary use; nothing is rewritten
merely to rename a regenerable cache.

The one thing X6a settles that the camera forms did not: a generated preview is
a JPEG, so `Path.suffix` reads `.jpg` and the X2 rule — match on the trailing
extension — would count it as media. Matching the *longest* trailing extension,
compound forms first, is what keeps X7 true for a file the standard now expects
tools to write.
---

## 7. Tool obligations — `T`

Any tool writing to the archive, first-party or third-party:

| ID | Rule |
| --- | --- |
| T1 | **No file and no non-empty directory is deleted.** Move, rename, report. A structural directory verified empty MAY be removed where a rule explicitly calls for it (H6); it carries no archive content to lose. |
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
| Month names | `src/constants/months.py` — `MONTH_FOLDERS` (re-exported by the legacy modules) |
| File checksum | `src/utils/checksums.py` — `file_md5` (a leaf: standard library only) |
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

4. ~~**`MONTH_FOLDERS`, twice**~~ — consolidated in
   `src/constants/months.py`, a dependency-free leaf module. Both the legacy
   CLI and the pipeline re-export that one mapping; parking lookup uses it too.

5. ~~**`file_md5`, four times**~~ — `core.py`, `common/common.py`,
   `companion_matching.default_checksum` and `legacy_videos._default_checksum`.
   One algorithm, three different chunk sizes: the harmless-looking kind of
   drift, where nothing breaks until one copy is changed and the others are
   not. `src/utils/checksums.py` holds the definition — a leaf importing only
   the standard library, so `companion_matching` can take it and stay the
   dependency-free module its docstring promises — and the other four names
   are aliases for it. `tests/test_t8_single_definition.py` asserts they are
   the same object, that the legacy CLI's spelling resolves to the same source
   file, and that nothing else under `src/` or `tools/` hashes a file of its
   own.

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

A fourth duplication is deliberate and is not a date regex. `grouping_names.py`
spells out the three stamp fragments `stamps.py` defines rather than importing
them, because it imports nothing from the project at all — which is what lets a
maintenance tool load it by file path, and importing `stamps` would pull the
package `__init__` in behind it. An accepted exception nobody was testing is
just drift with a docstring, so `tests/test_t8_single_definition.py` holds the
two spellings equal character for character, checks they read a table of sample
names identically, and fails if either module ever grows a project import —
that being the only thing making the copy legitimate.

### The fixing tool (to be implemented)

Reports, does not fix, by default (T3). Reports every directory below a month
folder that is neither a dated folder nor an allowed subfolder — including
anything nested inside a subfolder except a sidecar folder (S2, X11). Does not
flag dated children (S1).
Maintains the `____GROUP____` marker (C2) and the span stamps either side of it
(C11), and converts `__CONTAINER__` wherever it meets one (C15). Stays out of §0
roots. Exit codes `0` nothing to do, `1` changes pending or failures, `2` error
— matching `tools/canonicalise_timestamp_names.py`.

**Two obligations arrived with v1.0**, and each writes only under `--apply`, and
only after a prompt naming exactly what it is about to move and taking a yes:
gathering loose media out of a group into a `__TO_LABEL__` child (C4), and
moving a group whose start has crossed into another month folder (C12). One
prompt per group in both cases; a refusal is reported, not retried. It also
recognises the two placements v1.0 settled and **creates neither**: a group's
`__GEOLOCATIONS` (C3a), because which tracks span a whole group is a reading of
the tracks, and the year-level `__DUPLICATES` (S7), which belongs to the
placement pass that parks collision losers in it.

---

## 8. Machine-readable definitions

**Normative.** A conforming tool parses this block rather than the prose above;
the repo's central modules (§7) mirror it. Regexes are Python flavour, matching
against a single path component.

```yaml
standard: photo-archive
version: 1.0
status: settled

path:
  levels: [root, year, month, dated_folder, "dated_folder*", subfolder]
  year: '^\d{4}$'
  year_level_entries: [month_folder, "__DUPLICATES"]   # P6/S7 - there is no third kind
  year_level_duplicates_are_walked: false              # P6 - not a month folder, not descended into
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
  out_of_scope_root_entries: ["____INGEST_PIPELINE", "____TO_SORT", "__PROCESSED", "_Innych", "__LOGS"]
  migration_sources: {"__PROCESSED": derivatives}       # section 0.1
  opt_in_ingest_sources: {"_Innych": foreign_origin}    # section 0.2, never automatic
  tool_bookkeeping: {"__LOGS": run_journals}            # section 0.3, never reported as a violation

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
  read_folder_prefix: '^(\d{4})-(\d{2})-(\d{2})(?:[ _]+\([A-Za-z]{3}\))?(?:[ _]+(\d{2})\.(\d{2})\.(\d{2}))?(?:#(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})(?:__(\d{2})\.(\d{2})\.(\d{2}))?)?'
  # C6-C10: end of a group's span; groups = year?, month?, day, H?, M?, S?
  range_end: '#(?:(?:(\d{4})-)?(\d{2})-)?(\d{2})(?:__(\d{2})\.(\d{2})\.(\d{2}))?'
  range_end_forms: ["#DD__HH.MM.SS", "#MM-DD__HH.MM.SS", "#YYYY-MM-DD__HH.MM.SS"]
  # date fields omitted from the end are taken from the start; the time is never omitted
  range_end_applies_to: group_only
  range_end_required: true            # C6/C9 - on every group, single-day span included
  range_end_carries_weekday: false    # C8
  weekday_is_decorative: true
  day_boundary: "04.44.44"          # capture <= this belongs to the previous day
  day_boundary_config_key: day_boundary_time   # top level; "legacy" block still read
  derivable_from_contents: [time]   # never [date]

folder_tail:
  named:      ' - (?P<description>.+)$'
  group:      ' - ____GROUP____(?:\((?P<counts>d=\d+)\))?(?: - (?P<description>.+))?$'
  legacy_group: ' - __CONTAINER__(?:\((?P<counts>[divsew]=\d+(?:_[divsew]=\d+)*)\))?(?: - (?P<description>.+))?$'
  to_split:   ' - __TO_SPLIT__\((?:(?P<counts>[divsewf]=\d+(?:_[divsewf]=\d+)*)|(?:(?P<empty_counts>[divsewf]=\d+(?:_[divsewf]=\d+)*)_)?(?P<empty>EMPTY))\)(?:_(?P<discriminator>\d+))?$'
  to_label:   ' - __TO_LABEL__$'
  legacy_placeholder: ' - 1\. ######$'
  markers: ["____GROUP____", "__TO_SPLIT__", "__TO_LABEL__"]
  legacy_markers: ["__CONTAINER__"]   # C15/N13: read, converted, never written
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

group:
  marker: "____GROUP____"
  legacy_marker: "__CONTAINER__"      # C15
  required_when: has_dated_child
  marker_position: first_element_of_tail
  child_date_tolerance_days: 1        # C13, measured against the whole span
  start_time_from: whole_subtree_earliest_file    # C5
  end_time_from: whole_subtree_latest_file        # C8
  span_required: true                 # C6
  span_end_same_day:  '#(?P<time>\d{2}\.\d{2}\.\d{2})'      # C7/C9 - matched FIRST
  span_end_cross_day: '#(?P<date>\d{4}-\d{2}-\d{2})_\((?P<weekday>[A-Za-z]{3})\)__(?P<time>\d{2}\.\d{2}\.\d{2})'   # C7
  span_end_legacy: ['#DD', '#MM-DD', '#YYYY-MM-DD', "#<any of those>__HH.MM.SS"]   # C15a - read, never written
  span_maintained_by_tool: true       # C11 - recomputed on every run that touches the subtree
  description_from: [person, unanimous_child_description, "__TO_LABEL__"]   # C16, in order
  description_marker_is_not_a_name: "__TO_LABEL__"   # C16/N11 - re-asked every run, never protected by T7
  human_owns: [description]           # C11/T7 - the tail description, never the stamps
  month_folder_from: start            # C12
  month_folder_move:                  # C12 - settled v1.0
    performed_by_tool: true
    requires_apply: true
    prompts_per_group: true
    otherwise: report                 # P5 stands violated until a person acts
  count_letters_allowed: [d]          # C14
  contents:                           # C3 - closed set
    allowed: [dated_folder, group]
    media: false
    loose_files: false
    taxonomy_subfolders: ["__GEOLOCATIONS"]  # C3a - the only one, geodata only
    max_parking_areas: 1                     # C3
    max_geolocations: 1                      # C3a
  geolocations:                       # C3a
    holds: geodata                    # extensions.geodata; never media, never a subfolder
    auto_populated: false             # S3 - recognised and preserved, never written
    excluded_from: [span, counts]     # C14 - a track is filed, not hiding
    belongs_here_when: span_exceeds_any_single_dated_child
  loose_media_migration:              # C4 - migration only, runs once
    action: move_into_new_dated_child
    child_tail: " - __TO_LABEL__"
    child_day_from: day_boundary      # N7
    child_time_from: earliest_file    # N3
    companions_travel_with_media: true    # X10
    performed_by_tool: true           # C4 - settled v1.0
    requires_apply: true
    prompts_before_moving: true       # one prompt per group; refusal is reported
    otherwise: report

parking_areas:                        # section 4.1
  closed_set: ["__EMPTY_SUBFOLDERS"]
  dated_prefix: false                 # H1
  holds: [dated_folder, absolutely_empty_legacy_container]  # H3 / L4
  may_appear: any_level_a_dated_folder_may                  # H2
  may_appear_under: [month_folder, group]                   # H2 - and nowhere else
  max_per_level: 1                                          # H2
  traversal_boundary: true                                  # H1/H5
  excluded_from: [grouping, reconciliation, group_span]     # H5
  misplaced_migration:                                      # H6
    when: parent_is_neither_month_folder_nor_group
    action: merge_entries_into_nearest_allowed_level_above
    recursive: true
    collision: append_discriminator
    remove_source_when_verified_empty: true                 # T1
  above_its_level: report_never_move                        # H7 - e.g. under a year
  discriminator: '_<n>'               # L4

subfolders:
  closed_set: true
  also_allowed: dated_child_folder
  year_level_allowed: ["__DUPLICATES"]   # S7/P6 - collision losers, one per year tree
  year_level_migrates_to_event_level: false   # S7 - the two answer different questions
  may_nest: false
  may_nest_exception: ["__EXIF", "__PREVIEWS", "__OCR"]   # S2 / X11: sidecar folders, one level
  tool_written:
    - "__DUPLICATES"
    - "__EDITED"
    - "__EXIF"
    - "__EXPORTED"
    - "__GEOLOCATIONS"
    - "__HASHES"
    - "__OCR"
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
    - "__PROCESSED"                 # S6; the root folder of that name is §0.1
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
    parked_in: "<YYYY>/__DUPLICATES"  # S7 - one per year tree, not per event
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
  legacy_videos_migration:            # V12
    source_folder: "__VIDEOS"
    source_folder_match: case_insensitive
    stamped_name: move_one_level_up_unchanged
    unstamped_name_time_from: [Date/Time Original, Media Create Date, Track Create Date, Create Date]
    filesystem_times_allowed: false
    metadata_reader_failure: leave_and_report
    no_intrinsic_time: tag_and_move_per_V8
    companions_travel_with_it: true
    empty_source: park_below_month_per_L4

sidecars:
  extensions: ["._exif"]
  naming: "<full media filename><sidecar extension>"
  historical_naming_read: ["<media stem><sidecar extension>", "extension case variant"]  # X1a
  historical_match: case_insensitive_stem_then_x10_location
  historical_write: canonical_x1
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
    extensions: [".THM.jpg", ".PREVIEW.jpg", ".thm", ".lrv"]   # X6a: longest match first
    camera_extensions: [".thm", ".lrv"]        # lifted off the device
    generated_extensions: [".THM.jpg", ".PREVIEW.jpg"]   # X6a: compound, tool-written
    match_by: longest_trailing_extension       # X6a: ".jpg" alone would read as media
    naming: "<full media filename><preview extension>"
    counts_as: s                      # never i/v, never e
    may_be_representative: false
  ocr:                                # X15
    subfolder: "__OCR"
    extensions: [".OCR.txt"]
    naming: "<full media filename><ocr extension>"
    match_by: longest_trailing_extension
    counts_as: s                      # never i/v, never e
    may_be_representative: false
    separate_from_exif: true          # __EXIF is what a camera recorded
  missing_raw:                        # X14
    generated_by: configured_exiftool
    metadata_source: raw_itself
    naming: canonical_x1
    placement: x10
    overwrite: false
    dry_run_reports_only: true

extensions:
  lossy_images: [".jpg", ".jpeg"]
  other_images: [".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif"]
  raw_images:   [".arw", ".cr2", ".crw", ".dng", ".mpo", ".rw2"]
  videos:       [".mp4", ".mov", ".avi"]
  previews:     [".THM.jpg", ".PREVIEW.jpg", ".thm", ".lrv"]   # sidecars, not media — X6/X6a
  ocr:          [".OCR.txt"]          # sidecars, not media — X15
  geodata:      [".gpx"]

tool_obligations:
  never_delete_files_or_nonempty_directories: true
  may_remove_verified_empty_structural_directories: [nested_parking_area]
  rename_not_replace: true
  dry_run_default: true
  journal_applied_changes: true
  follow_reparse_points: false
  resolve_mapped_drive_to_unc: true
  long_path_prefix: '\\?\'
  human_named_folder_is_final: true
  prompts_before: [group_loose_media_migration, group_month_folder_move]   # C4/C12
  exit_codes: {clean: 0, pending_or_failed: 1, error: 2}
```

---

## 9. Amending

The names and the taxonomy are load-bearing — hundreds of thousands of files are
already on disk in this shape. An amendment is a change to this document **and** a
migration for the existing archive, together, never one alone. Bump `version` in
§8 with any normative change.

v1.0 closed the last of the open questions. From here a change is an
**amendment** — a decision being revisited, with a migration attached — not a
decision that was still pending. A rule that turns out to be wrong is amended in
the open, with the reasoning kept the way the *Settled* notes in §0.1 and §4
keep theirs: a rule whose argument has been deleted is one that gets re-argued
from scratch in a year.
