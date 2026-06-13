from pathlib import Path

from src.core import \
    CollisionDecision, \
    NameCollisionResolver, \
    PipelineContext, \
    PipelineStage, \
    file_md5, \
    safe_delete, \
    safe_move
from src.pipeline_stages.provenance import \
    append_journal_record, \
    dont_move_folder, \
    extract_origin_label, \
    geodata_extensions, \
    journal_file, \
    load_journal_records, \
    renamed_sidecar_path, \
    resolve_sidecar_target, \
    sidecar_candidates


class FolderIntakeStage(PipelineStage):
    """Flattens subfolders found in the inbox into the inbox root.

    Each file's containing-folder name is recorded as an origin label in the
    run journal before the file moves, so the label survives crashes and can
    later name the final event folder. A top-level `__DONT_MOVE` folder is
    never touched.
    """

    def __init__(self):
        super().__init__(
            stage_id="folder-intake",
            display_name="Folder Intake",
            dependencies=("upload-harvest",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        inbox = Path(context.config["paths"]["unsorted_folder"])
        if not inbox.exists():
            context.log("Folder intake skipped: inbox does not exist")
            return context

        self._recover_journal(context)

        excluded = dont_move_folder(context.config)
        media_extensions = context.media_extensions()
        geodata = geodata_extensions(context.config)
        journal = journal_file(context.config, context.run_id)
        resolver = NameCollisionResolver.from_context(context)
        ingested = 0

        for top_level in sorted(inbox.iterdir()):
            if not top_level.is_dir() or top_level.name == excluded:
                continue
            for path in sorted(top_level.rglob("*")):
                if not path.is_file():
                    continue
                suffix = path.suffix.lower()
                label = extract_origin_label(path.parent.name)
                if suffix in media_extensions:
                    ingested += self._ingest_media(context, path, inbox, label, journal, resolver)
                elif suffix in geodata:
                    self._ingest_geodata(context, path, inbox, label, journal)
                # Other files (unsupported extensions, leftovers) stay in place.
            self._remove_empty_tree(top_level)

        context.counters["folder_intake_files"] += ingested
        context.log(f"Ingested {ingested} files from inbox subfolders")
        return context

    def _recover_journal(self, context: PipelineContext) -> None:
        for record in load_journal_records(context.config):
            if record.get("kind") == "geodata":
                if record not in context.geodata:
                    context.geodata.append(record)
            elif record.get("md5"):
                context.provenance.setdefault(record["md5"], record)

    def _ingest_media(self, context: PipelineContext, path: Path, inbox: Path,
                      label: str | None, journal: Path,
                      resolver: NameCollisionResolver) -> int:
        md5 = file_md5(path)
        record = {
            "kind": "media",
            "origin_path": str(path),
            "origin_folder": path.parent.name,
            "origin_label": label,
            "md5": md5,
        }
        append_journal_record(journal, record)
        context.provenance[md5] = record

        target = inbox / path.name
        if target.exists():
            result = resolver.resolve(target, path, context, self.stage_id)
            if result.decision == CollisionDecision.DISCARD_DUPLICATE:
                for sidecar in sidecar_candidates(path, context.config):
                    if sidecar.exists():
                        safe_delete(sidecar)
                safe_delete(path)
                return 0
            if result.decision == CollisionDecision.PROMPT:
                context.log(f"Folder intake paused for collision prompt: {path.name}")
                return 0
            if result.target_path:
                target = inbox / result.target_path.name

        sidecars = [
            sidecar
            for sidecar in sidecar_candidates(path, context.config)
            if sidecar.exists()
        ]
        safe_move(path, target)
        for sidecar in sidecars:
            desired = inbox / renamed_sidecar_path(sidecar, path.name, target.name).name
            sidecar_target = resolve_sidecar_target(sidecar, desired)
            if sidecar_target is None:
                safe_delete(sidecar)
                continue
            safe_move(sidecar, sidecar_target)
        return 1

    def _ingest_geodata(self, context: PipelineContext, path: Path, inbox: Path,
                        label: str | None, journal: Path) -> None:
        target = inbox / path.name
        index = 1
        while target.exists():
            target = inbox / f"{path.stem}_{index}{path.suffix}"
            index += 1
        record = {
            "kind": "geodata",
            "origin_path": str(path),
            "origin_folder": path.parent.name,
            "origin_label": label,
            "file_name": target.name,
        }
        append_journal_record(journal, record)
        context.geodata.append(record)
        safe_move(path, target)

    def _remove_empty_tree(self, folder: Path) -> None:
        for path in sorted(folder.rglob("*"), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()
