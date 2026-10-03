"""NAS harvest: take what was dropped into the NAS inbox, never endangering it.

The NAS inbox sits inside the only backup share, so the stage is built so that
no failure, wherever it happens, can lose a file that was on the NAS:

  * **Copy across the network, never move.** Each file is streamed into the
    local temp folder while the MD5 of the bytes read is computed, then re-read
    from local disk and compared, and the original's size and timestamp are
    checked unchanged. Only then is the copy renamed into the INBOX.
  * **Park the original by renaming it** -- within the same share, so the NAS
    does it in one step -- into a folder under ``__HARVESTED`` that this run
    has just created and that therefore holds nothing to collide with. The
    rename asks for no replace: on Windows the server itself refuses a taken
    name. There is no copy-and-delete fallback.
  * **Nothing on the NAS is ever deleted.** A file failing any check stays
    where it was and is reported. ``__HARVESTED`` is emptied by hand.
  * **A ledger** of every checksum delivered means a run that copied a file
    but died before parking it does not deliver it a second time.

Only an empty folder this run itself emptied is removed (``os.rmdir``, which
refuses a folder with anything left in it).
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    dont_move_folder_name, \
    file_md5
from src.pipeline_stages.provenance import \
    append_journal_record, \
    journal_dir
from src.utils.checksums import copy_with_md5
from src.utils.progress import \
    format_bytes, \
    format_count, \
    format_duration

STAGE_ID = "nas-harvest"
DEFAULT_SETTLE_SECONDS = 300
DEFAULT_HARVESTED_FOLDER = "__HARVESTED"
MANIFEST_NAME = "__harvest_manifest.jsonl"
LEDGER_NAME = "nas_harvest_ledger.jsonl"
PARTIAL_FOLDER = "nas_harvest"
PARTIAL_SUFFIX = ".partial"
# Never taken: Synology's own folders (@eaDir thumbnails, #recycle, #snapshot)
# and anything hidden. Left exactly where they are.
IGNORED_PREFIXES = ("@", "#", ".")
IGNORED_FILE_NAMES = {"thumbs.db", "desktop.ini"}


def nas_harvest_settings(config: dict) -> dict:
    settings = config.get("nas_harvest", {})
    return {
        "enabled": bool(settings.get("enabled", False)),
        "settle_seconds": float(settings.get("settle_seconds", DEFAULT_SETTLE_SECONDS)),
        "harvested_folder": settings.get("harvested_folder") or DEFAULT_HARVESTED_FOLDER,
    }


def nas_inbox_path(config: dict) -> Path | None:
    ingest = config.get("paths", {}).get("ingest", {})
    value = ingest.get("nas_inbox") if isinstance(ingest, dict) else None
    return Path(value) if isinstance(value, str) and value.strip() else None


def rename_no_replace(source: str | Path, target: str | Path) -> None:
    """Rename ``source`` to ``target``, refusing if ``target`` exists.

    On Windows ``os.rename`` is MoveFileEx without MOVEFILE_REPLACE_EXISTING;
    on a share that is an SMB rename with ReplaceIfExists off, so the server
    refuses a taken name with no gap between a check and the act. The check
    here only covers platforms whose rename replaces. No retry and no
    fallback: a refused rename leaves the file where it was.
    """
    if Path(target).exists():
        raise FileExistsError(f"{target} already exists; not renamed onto")
    os.rename(source, target)


def _is_ignored(name: str) -> bool:
    return name.startswith(IGNORED_PREFIXES) or name.lower() in IGNORED_FILE_NAMES


def _arrival_time(stat: os.stat_result) -> float:
    # A file copied onto the share keeps its old modification time, but its
    # creation time is when it landed; the later of the two says how recently
    # it was still being written.
    created = getattr(stat, "st_birthtime", stat.st_ctime)
    return max(stat.st_mtime, created)


def _overlaps(first: Path, second: Path) -> bool:
    # Path text only, no filesystem access: resolving a path on an asleep NAS
    # can stall for tens of seconds. Windows paths compare case-insensitively.
    first, second = Path(os.path.abspath(first)), Path(os.path.abspath(second))
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def is_nas_inbox(config: dict, inbox: str | Path) -> bool:
    """Is ``inbox`` the configured NAS inbox (or inside it, or around it)?

    The NAS inbox is only ever harvested -- copied out and processed locally.
    A run whose own INBOX is that folder would process the backup share in
    place, so the root chooser skips such a root and initialization refuses
    one outright.
    """
    nas = nas_inbox_path(config)
    return nas is not None and _overlaps(nas, Path(inbox))


class NasHarvestStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id=STAGE_ID,
            display_name="NAS Harvest",
            description=(
                "Copies what was dropped into the NAS inbox into the INBOX, checks every "
                "copy against its original, then parks the original under __HARVESTED "
                "on the NAS. Nothing on the NAS is overwritten or deleted."
            ),
            dependencies=("upload-harvest",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        settings = nas_harvest_settings(context.config)
        paths = context.config["paths"]
        source_root = nas_inbox_path(context.config)
        inbox = Path(paths["unsorted_folder"])

        if not settings["enabled"] or source_root is None:
            context.log("NAS harvest skipped: not enabled")
            return context
        if is_nas_inbox(context.config, inbox):
            context.log(f"NAS harvest skipped: {source_root} is this run's own INBOX")
            context.add_stage_note(self.stage_id, "NAS inbox is this run's INBOX; nothing harvested")
            return context
        if not source_root.is_dir():
            context.log(f"NAS harvest skipped: {source_root} is not reachable")
            context.add_stage_note(self.stage_id, "NAS inbox not reachable; nothing harvested")
            return context

        inbox.mkdir(parents=True, exist_ok=True)
        partials = Path(paths["temp_folder"]) / PARTIAL_FOLDER
        partials.mkdir(parents=True, exist_ok=True)
        self._clear_partials(partials)
        chunk_size = context.config.get("safety", {}).get("hash_chunk_size", 1024 * 1024)
        ledger_path = journal_dir(context.config) / LEDGER_NAME
        delivered_before = self._load_ledger(ledger_path)

        candidates, settling = self._scan(source_root, settings, context.config)
        reporter = context.progress(
            self.stage_id,
            "Copying from the NAS inbox",
            total=len(candidates),
            total_bytes=sum(stat.st_size for _path, _relative, stat in candidates),
        )
        harvest = _Harvest(
            context=context,
            source_root=source_root,
            harvest_root=source_root / settings["harvested_folder"],
            inbox=inbox,
            partials=partials,
            chunk_size=chunk_size,
            ledger_path=ledger_path,
            delivered_before=delivered_before,
            run_folder_factory=self._run_folder,
        )
        for index, (path, relative, stat) in enumerate(candidates):
            if context.abort_event.is_set():
                context.log("NAS harvest stopped: run aborted")
                break
            if not source_root.is_dir():
                context.log("NAS harvest stopped: the NAS inbox went away mid-run")
                break
            ok = harvest.take(path, relative, stat, index)
            reporter.advance(size_bytes=stat.st_size, errors=0 if ok else 1)
        reporter.finish()
        harvest.tidy_emptied_folders()

        # Only what actually landed in the INBOX, as upload-harvest does.
        watched = context.extend_snapshot(harvest.arrived, stage_id=self.stage_id)
        context.counters["nas_files_harvested"] += len(harvest.arrived)
        context.set_stage_stats(
            self.stage_id,
            inputs=len(candidates),
            outputs=len(harvest.arrived),
            errors=len(harvest.problems),
            parked=harvest.parked,
            settling=settling,
            watched=watched["files"],
            bytes=watched["bytes"],
        )
        context.log(
            f"NAS harvest: {format_count(len(harvest.arrived))} copied "
            f"({format_bytes(watched['bytes'])}), {format_count(harvest.parked)} parked"
            + (f" in {harvest.run_folder}" if harvest.run_folder else "")
        )
        if settling:
            minutes = max(1, -(-int(self.longest_wait) // 60))
            context.add_stage_note(
                self.stage_id,
                f"{format_count(settling)} file(s) arrived on the NAS less than "
                f"{format_duration(settings['settle_seconds'])} ago, so may still be being "
                f"written; left for the next run (all ready in about {minutes} min)",
            )
        for problem in harvest.problems:
            context.log(f"  left on the NAS: {problem}")
        if harvest.problems:
            context.add_stage_note(
                self.stage_id,
                f"{format_count(len(harvest.problems))} file(s) left on the NAS; see the log",
            )
        return context

    def _scan(self, source_root: Path, settings: dict, config: dict):
        """Finished files under the NAS inbox, and how many are still arriving."""
        excluded_top = {settings["harvested_folder"].lower(), dont_move_folder_name(config).lower()}
        now = time.time()
        self.longest_wait = 0.0
        candidates, settling = [], 0
        for folder, folders, files in os.walk(source_root):
            folder = Path(folder)
            at_top = folder == source_root
            folders[:] = sorted(
                name for name in folders
                if not _is_ignored(name) and not (at_top and name.lower() in excluded_top)
            )
            for name in sorted(files):
                if _is_ignored(name):
                    continue
                path = folder / name
                try:
                    stat = path.stat()
                except OSError:
                    continue
                wait = settings["settle_seconds"] - (now - _arrival_time(stat))
                if wait > 0:
                    settling += 1
                    self.longest_wait = max(self.longest_wait, wait)
                    continue
                candidates.append((path, path.relative_to(source_root), stat))
        return candidates, settling

    def _run_folder(self, harvest_root: Path, context: PipelineContext) -> Path:
        """This run's own parking folder -- created new, or not at all."""
        harvest_root.mkdir(exist_ok=True)
        folder = harvest_root / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{context.run_id[:8]}"
        folder.mkdir()     # exist_ok=False: a folder that exists is not ours
        return folder

    @staticmethod
    def _load_ledger(ledger_path: Path) -> set[str]:
        delivered = set()
        if not ledger_path.exists():
            return delivered
        with ledger_path.open("r", encoding="utf-8") as handler:
            for line in handler:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("event") == "delivered" and record.get("md5"):
                    delivered.add(record["md5"])
        return delivered

    @staticmethod
    def _clear_partials(partials: Path) -> None:
        # A leftover partial is never the only copy of anything: it reaches
        # the INBOX by one rename, after verification, so a crash leaves the
        # original on the NAS untouched.
        for leftover in partials.glob(f"*{PARTIAL_SUFFIX}"):
            _discard_partial(leftover, partials)


def _discard_partial(path: Path, partials: Path) -> None:
    """Remove one of this stage's own temp copies -- and nothing else."""
    if path.parent != partials or not path.name.endswith(PARTIAL_SUFFIX):
        raise ValueError(f"refusing to remove {path}: not a NAS-harvest partial")
    try:
        path.unlink()
    except OSError:
        pass


class _Harvest:
    """One run's worth of taking files: the per-file steps and what they found."""

    def __init__(self, context, source_root, harvest_root, inbox, partials, chunk_size,
                 ledger_path, delivered_before, run_folder_factory):
        self.context = context
        self.source_root = source_root
        self.harvest_root = harvest_root
        self.inbox = inbox
        self.partials = partials
        self.chunk_size = chunk_size
        self.ledger_path = ledger_path
        self.delivered_before = delivered_before
        self.run_folder_factory = run_folder_factory
        self.run_folder: Path | None = None
        self.run_folder_failed = False
        self.arrived: list[Path] = []
        self.parked = 0
        self.problems: list[str] = []
        self.emptied: set[Path] = set()

    def take(self, path: Path, relative: Path, stat: os.stat_result, index: int) -> bool:
        try:
            md5 = self._deliver(path, relative, stat, index)
        except OSError as error:
            self.problems.append(f"{relative}: copy failed ({error})")
            return False
        if md5 is None:
            return False
        return self._park(path, relative, md5, stat)

    def _deliver(self, path, relative, stat, index) -> str | None:
        """Make sure a verified copy is in (or went through) the INBOX.

        Returns the original's MD5 once its content is safely local, or None
        when the original must stay where it is.
        """
        target = self.inbox / relative
        if target.exists():
            # Either an earlier run copied it and died before parking, or
            # another file has the name. Only identical content counts as done.
            md5 = file_md5(path, self.chunk_size)
            if target.is_file() and file_md5(target, self.chunk_size) == md5:
                return md5
            self.problems.append(f"{relative}: a different file of that name is in the INBOX")
            return None

        partial = self.partials / f"{self.context.run_id[:8]}_{index}{PARTIAL_SUFFIX}"
        try:
            md5 = copy_with_md5(path, partial, self.chunk_size)
            after = path.stat()
            if (after.st_size, after.st_mtime) != (stat.st_size, stat.st_mtime):
                self.problems.append(f"{relative}: changed while it was being copied")
                return None
            if partial.stat().st_size != stat.st_size or file_md5(partial, self.chunk_size) != md5:
                self.problems.append(f"{relative}: the local copy did not match the original")
                return None
            if md5 in self.delivered_before:
                # Copied by an earlier run that died before parking it, and
                # since processed out of the INBOX: delivering it again would
                # put a duplicate through the pipeline.
                return md5
            os.utime(partial, (stat.st_atime, stat.st_mtime))
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                rename_no_replace(partial, target)
            except FileExistsError:
                self.problems.append(f"{relative}: a file of that name appeared in the INBOX")
                return None
        finally:
            if partial.exists():
                _discard_partial(partial, self.partials)

        self.arrived.append(target)
        self.delivered_before.add(md5)
        append_journal_record(self.ledger_path, {
            "event": "delivered",
            "md5": md5,
            "size": stat.st_size,
            "source": str(path),
            "local": str(target),
            "run_id": self.context.run_id,
            "at": datetime.now().isoformat(timespec="seconds"),
        })
        return md5

    def _park(self, path: Path, relative: Path, md5: str, stat: os.stat_result) -> bool:
        if self.run_folder is None and not self.run_folder_failed:
            try:
                self.run_folder = self.run_folder_factory(self.harvest_root, self.context)
            except OSError as error:
                self.run_folder_failed = True
                self.context.log(f"NAS harvest: could not create a parking folder ({error})")
        if self.run_folder is None:
            self.problems.append(f"{relative}: copied, but no parking folder; left in place")
            return False

        parked = self.run_folder / relative
        record = {
            "md5": md5,
            "size": stat.st_size,
            "from": str(path),
            "to": str(parked),
            "run_id": self.context.run_id,
            "at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            parked.parent.mkdir(parents=True, exist_ok=True)
            # Written before the rename, so a crash between the two still
            # leaves a record of what was about to happen.
            append_journal_record(self.run_folder / MANIFEST_NAME, {**record, "event": "parking"})
            rename_no_replace(path, parked)
        except OSError as error:
            self.problems.append(f"{relative}: copied, but not parked ({error})")
            return False
        append_journal_record(self.ledger_path, {**record, "event": "parked"})
        self.parked += 1
        if path.parent != self.source_root:
            self.emptied.add(path.parent)
        return True

    def tidy_emptied_folders(self) -> None:
        """Remove the inbox subfolders this run emptied, deepest first.

        ``os.rmdir`` refuses any folder with something left in it, so this
        cannot remove content -- only the empty shells of folders it drained.
        """
        folders = set()
        for folder in self.emptied:
            while folder != self.source_root and folder.is_relative_to(self.source_root):
                folders.add(folder)
                folder = folder.parent
        for folder in sorted(folders, key=lambda item: len(item.parts), reverse=True):
            try:
                os.rmdir(folder)
            except OSError:
                pass
