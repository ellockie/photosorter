# Safely restructuring the archive on the NAS backup drive

Written 2026-10-06. Plan only; nothing has been run against the NAS.

## What `tools/restructure_archive.py` already does

- Dry run unless `--apply` is passed.
- Refuses a target that does not look like an archive (`--force-target` overrides).
- Resolves a mapped drive letter to its UNC path once, up front.
- Never follows reparse points (junctions, symlinks, mount points).
- Moves companions with `os.rename` only, never `os.replace`, so it never overwrites (T2).
- Asks before writing to a network target; refuses to apply with no terminal unless `--yes`.
- `--year ALL` runs each year as its own run, with its own journal, oldest first.

## Where it falls short

1. **Undo only covers renames.** The canonicaliser journal is replayable with `--undo`.
   The grouper step (step 3) is not undoable. Step 0 re-times shots, which changes names.
   Whether step 0 and the reconciliation moves are journaled well enough to reverse is
   not confirmed.
2. **No independent record of file counts.** The June 2026 loss (see the data-loss
   incident note) was only dated afterwards by diffing `reconcile` counts. The grouper's
   file operations are never journaled.
3. **It runs over SMB.** Many small renames are slow, and a dropped connection or a
   sleeping NAS mid-run leaves a half-applied year.
4. **The NAS is the backup.** If it holds the only copy of some photos, a bug is
   unrecoverable unless a second copy or snapshot exists first.

## Recommended sequence

### 0. Make a restore point first (non-negotiable)

- Take a NAS snapshot (Btrfs/ZFS, e.g. Synology Snapshot Replication) of the archive
  share. A snapshot rolls back renames *and* grouper moves.
- If the NAS cannot snapshot, make a cold copy to another disk first. Not a sync: a
  sync would propagate the damage.
- Keep that copy until the restructure has been verified for a while.

### 1. Record a baseline before changing anything

- Per year, write a manifest: relative path, size, mtime, and MD5 (at least on media).
- Record the folder, media and sidecar counts, which is what `reconcile` reports.
- Store it off the NAS so it cannot be damaged along with the archive.

### 2. Rehearse on a copy

- Copy one small year (with groups, sidecars and video) to a local disk.
- Run `--year YYYY --apply` there and read the journal.
- Run `--undo` and confirm the tree matches the baseline byte for byte. This proves
  the undo path works.

### 3. Dry-run the real archive and read the output

```bash
_restructure_archive.bat "\\NAS\PhotoBackup" --year ALL
```

Skim the planned renames and moves for anything surprising before applying.

### 4. Apply one year at a time, oldest and smallest first

```bash
_restructure_archive.bat "\\NAS\PhotoBackup" --year 2019 --apply
```

- Do not use `--yes` or `--year ALL --apply` until two or three years have gone cleanly.
- After each year, re-run the manifest. The media count must be unchanged, and the only
  differences must be paths. Moved files' hashes must match.
- Take a fresh snapshot after each verified year, so a later failure never costs
  earlier work.

### 5. Reduce NAS-specific risk while it runs

- Disable NAS sleep and hibernation; do not run over Wi-Fi.
- Run from a wired machine, with nothing else writing to the share (no ingest pipeline,
  no Dropbox, no sync clients).
- Keep the first runs interactive, without `--yes`. Step 3 opens the grouper GUI.

### 6. Leave steps 7 and 8 alone

`AGENTS.md` says they are placeholders. An unenforced rule is not licence to fix a live
archive in passing.

## Gaps worth building

- A **manifest and verify** tool (step 1, plus the check after each year); small and
  stdlib-only like the rest of `tools/`.
- A **pre-flight guard** that refuses `--apply` on a network target unless a baseline
  manifest and a snapshot marker exist.
- **Journaling for the grouper's file operations**, closing the hole from the June
  incident.

## Open question

Does the NAS support snapshots? That decides whether step 0 is a snapshot or a cold copy.
