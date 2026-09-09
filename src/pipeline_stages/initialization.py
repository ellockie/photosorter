from pathlib import Path

from src.core import \
    PipelineContext, \
    PipelineStage, \
    dont_move_folder_name
from src.utils.progress import \
    format_bytes, \
    format_count


class InitializationStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="initialization",
            display_name="Initialization",
            description=(
                "Creates the pipeline folders if missing, then checksums every file "
                "waiting in the inbox so the run can prove at the end that none of them "
                "was lost. Reads every incoming byte, so it scales with intake size."
            ),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        paths = context.config.get("paths", {})
        created = []
        for key in ("root_folder", "unsorted_folder", "ready_folder", "temp_root"):
            value = paths.get(key)
            if not value:
                continue
            folder = Path(value)
            if not folder.exists():
                created.append(f"{key}={folder}")
            folder.mkdir(parents=True, exist_ok=True)
        context.log(
            f"Created {len(created)} missing folder(s): {', '.join(created)}"
            if created else "All pipeline folders already exist"
        )

        # Measured, not checksummed, and before the intake walk so the numbers
        # predate every stage. The pipeline may not touch these folders, so
        # what is wanted is proof it did not -- not their content.
        for folder, measured in context.snapshot_protected_folders().items():
            if measured["exists"] and measured["files"]:
                context.log(
                    f"Leaving {measured['files']} file(s) "
                    f"({format_bytes(measured['bytes'])}) untouched in {folder}"
                )

        inbox = paths.get("unsorted_folder")
        context.log(f"Checksumming everything waiting in {inbox}")
        tally = context.snapshot_inputs([inbox], stage_id=self.stage_id)

        # Files, not snapshot entries: byte-identical inputs share one entry,
        # so counting the snapshot reported 251 for a 600-file intake and made
        # the dashboard look like 349 files had already gone missing.
        context.counters["input_files"] = tally["files"]
        context.counters["input_checksums"] = tally["unique"]
        context.counters["input_bytes"] = tally["bytes"]
        context.counters["input_folders"] = len(tally["folders"])
        context.set_stage_stats(
            self.stage_id,
            inputs=tally["files"],
            outputs=tally["unique"],
            errors=0,
            bytes=tally["bytes"],
            folders=len(tally["folders"]),
            folders_created=len(created),
        )
        context.log(
            f"Intake: {format_count(tally['files'])} file(s), {format_bytes(tally['bytes'])}, "
            f"{format_count(tally['unique'])} distinct checksum(s)"
            + (f", from {format_count(len(tally['folders']))} folder(s)"
               if len(tally["folders"]) > 1 else "")
        )
        self._report_folders(context, tally["folders"])
        if tally["protected_skipped"]:
            # Said out loud so the intake count is never mistaken for "every
            # media file under the inbox" -- these are under it and excluded.
            note = (
                f"{format_count(tally['protected_skipped'])} file(s) in "
                f"{dont_move_folder_name(context.config)} excluded from the intake "
                "and from the safety check -- the pipeline never touches them"
            )
            context.counters["input_protected_skipped"] = tally["protected_skipped"]
            context.log(note)
            context.add_stage_note(self.stage_id, note)
        if tally["duplicates"]:
            # Not a fault -- byte-identical inputs share one snapshot entry --
            # but it explains why "files in" and "checksums to find" differ,
            # which otherwise reads like files went missing before the run began.
            note = (
                f"{format_count(tally['duplicates'])} incoming file(s) are byte-identical "
                "to another and share one checksum"
            )
            context.counters["input_duplicate_files"] = tally["duplicates"]
            context.log(note)
            context.add_stage_note(self.stage_id, note)
        if not tally["files"]:
            context.add_stage_note(self.stage_id, "inbox is empty, nothing to ingest")
        return context

    # Long enough to be worth capping: an intake of a hundred camera folders
    # would otherwise bury every other line the stage writes.
    MAX_FOLDERS_LISTED = 40

    def _report_folders(self, context: PipelineContext, folders: list[dict]) -> None:
        """Name the folders the intake came from, with what each contributed.

        Shown relative to the inbox, because the absolute prefix is the same
        on every line and the part that differs is the part worth reading.
        A subfolder is called out separately: files sitting loose in the inbox
        are the ordinary case, whereas a subfolder is a whole import that
        folder-intake will later flatten and take an origin label from.
        """
        if not folders:
            return
        if len(folders) == 1 and folders[0]["path"] == folders[0]["root"]:
            # A flat inbox: everything sat in the folder the stage already
            # named on the line above. Listing it again is one more line to
            # read and nothing more to learn.
            return
        context.log(f"Files came from {format_count(len(folders))} folder(s):")
        for entry in folders[:self.MAX_FOLDERS_LISTED]:
            context.log(
                f"  {self._folder_label(entry)}"
                f"  -- {format_count(entry['files'])} file(s), {format_bytes(entry['bytes'])}"
            )
        hidden = len(folders) - self.MAX_FOLDERS_LISTED
        if hidden > 0:
            context.log(f"  ... and {format_count(hidden)} more folder(s)")

        subfolders = [entry for entry in folders if entry["path"] != entry["root"]]
        if subfolders:
            carried = sum(entry["files"] for entry in subfolders)
            context.add_stage_note(
                self.stage_id,
                f"{format_count(carried)} file(s) arrived inside "
                f"{format_count(len(subfolders))} subfolder(s), whose names become origin labels",
            )

    @staticmethod
    def _folder_label(entry: dict) -> str:
        path, root = entry["path"], entry["root"]
        if path == root:
            # The inbox itself. Named, rather than shown as ".", so a reader
            # who has not memorised the layout still knows where that is.
            return f"{root}  (inbox root)"
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)
