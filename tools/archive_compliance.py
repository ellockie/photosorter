"""Archive-standard inspection and prompted migrations for restructure steps 7/8.

The front door supplies its existing path guards, grammars and journal. This
module never imports the application, and works on a bare Python interpreter.
Only fields not already owned by a central module are read from section 8.
"""

import ast
import importlib
import json
import datetime
import os
import re
import sys
from pathlib import Path


def standard_definitions(path):
    """Read the flat YAML fields this checker consumes, without a YAML dependency.

    This is deliberately a strict subset reader, not a general YAML parser.
    Unsupported or missing fields fail closed instead of supplying new rules.
    """
    text = Path(path).read_text(encoding="utf-8")
    block = re.search(r"```yaml\s*\n(.*?)```", text, re.S)
    if block is None:
        raise ValueError("ARCHIVE_STANDARD.md has no section 8 YAML block")
    sections = {}
    section = None
    for line in block.group(1).splitlines():
        header = re.fullmatch(r"([a-z_]+):\s*(?:#.*)?", line)
        if header:
            section = header.group(1)
            sections[section] = {}
        item = re.match(r"^  ([a-z_]+):\s*(.+)", line)
        if item and section:
            sections[section][item.group(1)] = item.group(2)

    def literal(section, key):
        # literal_eval accepts the quoted scalars and quoted flow lists used
        # here, including trailing YAML comments, without executing anything.
        return ast.literal_eval(sections[section][key])

    return {
        "geodata": {ext.casefold() for ext in literal("extensions", "geodata")},
        "boundary": literal("stamp", "day_boundary"),
    }


class Inspection:
    def __init__(self, tool, run):
        self.tool, self.run = tool, run
        self.config = tool.canonicalise._config()
        self.definitions = standard_definitions(tool.STANDARD_PATH)
        self.stamps = tool.canonicalise.stamps
        self.grouping = tool.canonicalise.grouping
        self.taxonomy = tool.taxonomy
        self.tax = {name.casefold() for name in self.taxonomy.taxonomy_dir_names(self.config)}
        self.sidecars = {name.casefold() for name in self.taxonomy.sidecar_dir_names(self.config)}
        self.legacy = {name.casefold() for name in self.taxonomy.legacy_container_names(self.config)}
        self.months = importlib.import_module("src.constants.months").MONTH_FOLDERS
        self.kinds = tool.matching.companion_kinds(self.config)
        self.images, self.videos = self.grouping.extension_sets(self.config)
        self.issues = []
        self.events = []

    def issue(self, rule, path, reason):
        item = (rule, Path(path), reason)
        if item not in self.issues:
            self.issues.append(item)

    def entries(self, folder):
        """No links are followed, including the starting directory itself (T4)."""
        if self.tool.path_is_reparse_point(folder):
            self.issue("T4", folder, "reparse point refused")
            return [], []
        directories, files = [], []
        try:
            with os.scandir(self.tool.extended_path(folder)) as scan:
                entries = sorted(scan, key=lambda item: item.name.casefold())
            for entry in entries:
                path = Path(folder) / entry.name
                if self.tool.canonicalise.is_reparse_point(entry):
                    self.issue("T4", path, "reparse point refused")
                elif entry.is_dir(follow_symlinks=False):
                    directories.append(path)
                elif entry.is_file(follow_symlinks=False):
                    files.append(path)
                else:
                    self.issue("T4", path, "unsupported filesystem entry")
        except OSError as error:
            self.issue("T4", folder, "cannot inspect: %s" % error)
        return directories, files

    def companion(self, path):
        return self.tool.matching._companion_kind(path.name, self.kinds)

    def media(self, path):
        return self.companion(path) is None and path.suffix.casefold() in self.images | self.videos

    def moment(self, path):
        return self.grouping.earliest_capture_time([path.name])

    def scan(self):
        for tree in self.run.trees:
            dirs, files = self.entries(tree)
            for path in files:
                self.issue("P6", path, "loose file at year level")
            for folder in dirs:
                if folder.name.casefold() == self.taxonomy.taxonomy_folder(self.config, "duplicates").casefold():
                    continue
                if folder.name not in self.months.values():
                    self.issue("H7" if self.tool.parking.is_parking_area(folder.name) else "P3", folder,
                               "year children must be canonical month folders or year duplicates")
                    continue
                self.structure(folder, "month", tree)
        # Read names after the traversal so an unreadable descendant cannot
        # supply a partial time or count (T4/N3).
        for folder, children, _ in self.events:
            if children or self.grouping.carries_group_marker(folder.name):
                continue
            if any(rule in ("T4", "N6") and (path == folder or folder in path.parents)
                   for rule, path, _ in self.issues):
                continue
            _, files = self.entries(folder)
            wanted = leaf_target(self, folder, files)
            if wanted != folder:
                self.issue("N3/N10", folder, "expected name: " + wanted.name)
        return self

    def structure(self, folder, kind, tree):
        dirs, files = self.entries(folder)
        dated = [path for path in dirs if self.stamps.day_prefix(path.name)]
        group = kind == "dated" and bool(dated)
        if kind == "dated":
            self.events.append((folder, dated, tree))
            parsed = self.stamps.split_dated_folder(folder.name)
            try:
                day = self.tool.date_of(parsed.date)
            except (ValueError, AttributeError):
                self.issue("N6", folder, "invalid date; never inferred from contents")
                day = None
            if day and folder.parent.name in self.months.values():
                if folder.parent.name != self.months[day.strftime("%m")] or tree.name != str(day.year):
                    self.issue("C12" if group else "P5", folder, "folder date disagrees with year/month placement")
            if group or self.grouping.carries_group_marker(folder.name):
                refused = []
                try:
                    target, reason, _ = self.tool.group_target_name(folder, dated, self.run, self.config, refused)
                    if target and target != folder.name:
                        self.issue("C11" if group else "C2", folder, "expected name: " + target)
                    elif reason:
                        self.issue("C11", folder, reason)
                except ValueError as error:
                    self.issue("N6", folder, str(error))
                for path, reason in refused:
                    self.issue("T4", path, reason)
            elif day:
                wanted = self.tool.canonicalise.canonical_name(folder.name)
                if wanted != folder.name:
                    self.issue("N1", folder, "expected canonical prefix: " + wanted)
            if group and not self.grouping.carries_group_marker(folder.name):
                self.issue("C1", folder, "dated children require a group marker")

        for path in files:
            if kind == "month":
                self.issue("P4", path, "loose file at month level")
            elif group:
                self.issue("C4" if self.media(path) else "C3", path, "group holds a loose file")
            else:
                self.check_file(path, top=True)
        for path in dirs:
            name = path.name.casefold()
            if path in dated:
                self.structure(path, "dated", tree)
            elif self.tool.parking.is_parking_area(path.name):
                if kind != "month" and not group:
                    self.issue("H2", path, "parking area inside a leaf")
                # H1/H5: records in parking areas are outside the active scan.
            elif name in self.tax or name in self.legacy:
                if kind == "month":
                    self.issue("P4", path, "taxonomy belongs inside a dated folder")
                if group and name != self.taxonomy.taxonomy_folder(self.config, "geolocations").casefold():
                    self.issue("C3", path, "group may only hold geolocations as taxonomy")
                if name in self.legacy:
                    self.issue("L2" if path.name in self.taxonomy.legacy_container_targets(self.config) else "L5",
                               path, "legacy container remains")
                self.subfolder(path, group_geodata=group and name == self.taxonomy.taxonomy_folder(self.config, "geolocations").casefold())
            else:
                self.issue("S1" if kind == "dated" else "P4", path, "unrecognised directory")
                self.unknown(path)

    def unknown(self, folder):
        dirs, _ = self.entries(folder)
        for path in dirs:
            if self.tool.parking.is_parking_area(path.name):
                self.issue("H2", path, "parking area below unrecognised structure")
                continue
            self.issue("S2", path, "directory nested below unrecognised structure")
            self.unknown(path)

    def subfolder(self, folder, nested=False, group_geodata=False):
        dirs, files = self.entries(folder)
        is_sidecar = folder.name.casefold() in self.sidecars
        for path in files:
            if group_geodata:
                if path.suffix.casefold() not in self.definitions["geodata"]:
                    self.issue("C3a", path, "group geolocations may contain geodata only")
            else:
                self.check_file(path, sidecar=is_sidecar)
        for path in dirs:
            if self.tool.parking.is_parking_area(path.name):
                self.issue("H2", path, "parking area inside taxonomy")
                continue
            if group_geodata or is_sidecar or nested or path.name.casefold() not in self.sidecars:
                self.issue("C3a" if group_geodata else "S2", path, "subfolder nesting is not permitted here")
            self.subfolder(path, nested=True, group_geodata=group_geodata)

    def check_file(self, path, top=False, sidecar=False):
        companion = self.companion(path)
        if companion:
            key, subject, _ = companion
            expected = self.taxonomy.taxonomy_folder(self.config, key)
            if path.parent.name.casefold() != expected.casefold():
                self.issue("X10", path, "companion belongs in " + expected)
            elif not (path.parent.parent / subject).is_file():
                self.issue("X1", path, "canonical subject is not directly above companion folder")
            return
        if sidecar:
            self.issue("X12", path, "non-sidecar in companion folder")
            return
        if not self.media(path):
            if top:
                self.issue("F7", path, "non-representative file at event top level")
            return
        tagged = path.name.startswith(self.tool.legacy_videos.TO_RENAME_PREFIX)
        waiting = path.parent.name.casefold() == self.taxonomy.taxonomy_folder(self.config, "videos_to_rename").casefold()
        if tagged or waiting:
            if not (tagged and waiting and path.suffix.casefold() in self.videos):
                self.issue("V8", path, "unresolved video requires both tag and waiting folder")
            else:
                self.issue("V9", path, "video awaits a real capture time")
            return
        if self.moment(path) is None:
            if path.parent.name.casefold() == self.taxonomy.taxonomy_folder(self.config, "edited").casefold():
                self.run.report("dim", "D5 unkeyed derivative (permitted): %s" % path)
            else:
                self.issue("F1", path, "no usable leading capture timestamp")
        raw = {ext.casefold() for ext in self.config.get("extensions", {}).get("raw_images", [])}
        if top and path.suffix.casefold() in raw:
            self.issue("F7", path, "RAW original belongs in its taxonomy folder")


def report(inspection):
    for rule, path, reason in inspection.issues:
        inspection.run.report("warn", "%s %s: %s" % (rule, path, reason))
        inspection.run.flag("Archive standard", path, "%s: %s" % (rule, reason))
    inspection.run.report("ok", "Archive standard: %d outstanding finding(s)." % len(inspection.issues))
    inspection.run.journal.write("standard_check", findings=len(inspection.issues))
    return 1 if inspection.issues else 0


def check(tool, run):
    return report(Inspection(tool, run).scan())


def leaf_target(inspection, folder, files):
    """Use the canonicaliser's counts/time while preserving a human's tail (T7)."""
    wanted = inspection.tool.canonicalise.plan_for(folder, files, inspection.run.grouping_settings)
    if wanted is None:
        return folder
    parsed = inspection.stamps.split_dated_folder(folder.name)
    renamed = inspection.stamps.split_dated_folder(wanted.name)
    if parsed and renamed and parsed.tail and not inspection.tool.placeholder_tail(folder.name, inspection.config):
        prefix = wanted.name[:-len(renamed.tail)] if renamed.tail else wanted.name
        wanted = wanted.with_name(prefix + parsed.tail)
    return wanted


def checked_move(inspection, source, target, rule):
    """Revalidate all ancestors immediately before a non-overwriting rename."""
    tool, run = inspection.tool, inspection.run
    source, target = Path(source), Path(target)
    for path in (source, target):
        for ancestor in (path, *path.parents):
            if os.path.lexists(tool.extended_path(ancestor)) and tool.path_is_reparse_point(ancestor):
                raise OSError("T4 reparse point refused: %s" % ancestor)
    if os.path.lexists(tool.extended_path(target)):
        raise FileExistsError("N4/T2 destination already exists: %s" % target)
    if source.is_dir():
        refused = []
        list(tool.canonicalise.walk_bottom_up(source, tool.path_key(source), refused))
        if refused:
            raise OSError("T4 cannot move an incompletely inspected directory: %s" % source)
    # Record intent before writing: failed journalling prevents any mutation.
    if run.journal.path is None:
        raise OSError("T3 applied migration requires a writable journal")
    run.journal.write("standard_move_intent", rule=rule, source=str(source), target=str(target))
    if run.journal.path is None:
        raise OSError("T3 could not write move journal")
    tool.archive_mover(run)(source, target)
    run.journal.write("standard_move", rule=rule, source=str(source), target=str(target), **{"from": str(source), "to": str(target)})


def loose_media_plan(inspection, folder):
    """C4: plan dated children and every unambiguously associated companion.

    Existing taxonomy directories move intact when all their subjects go into
    the same child. Otherwise leave the group unchanged: distributing an
    unkeyed derivative or choosing between two events would invent attribution.
    """
    dirs, files = inspection.entries(folder)
    media = [path for path in files if inspection.media(path)]
    if not media:
        return []
    legacy = importlib.import_module("src.pipeline_stages.legacy")
    days, subjects = {}, {}
    for path in media:
        moment = inspection.moment(path)
        if moment is None:
            raise ValueError("C4/V4 cannot date loose media: %s" % path)
        day = legacy.date_folder_datetime(moment, inspection.config).date()
        days.setdefault(day, []).append((path, moment))
        subjects[path.name.casefold()] = day
    children = {}
    for day, shots in days.items():
        earliest = min(moment for _, moment in shots)
        stamp = datetime.datetime.combine(day, earliest.time())
        children[day] = folder / (inspection.stamps.format_stamp(stamp) + inspection.grouping.LABEL_SEPARATOR + inspection.grouping.TO_LABEL_MARKER)
        if children[day].exists():
            raise ValueError("N4 proposed child already exists: %s" % children[day])
    raw_extensions = {ext.casefold() for ext in inspection.config.get("extensions", {}).get("raw_images", [])}
    raw_folder = inspection.taxonomy.taxonomy_folder(inspection.config, "raw")
    moves = [(path, (children[day] / raw_folder if path.suffix.casefold() in raw_extensions else children[day]) / path.name)
             for day, shots in days.items() for path, _ in shots]

    def destination_day(path):
        companion = inspection.companion(path)
        if companion and companion[1].casefold() in subjects:
            return subjects[companion[1].casefold()]
        key = inspection.tool.matching.shot_key(path.name)
        candidates = {day for name, day in subjects.items() if key and inspection.tool.matching.shot_key(name) == key}
        # Include existing child shots: a companion shared with one of those
        # must not be attributed to the newly gathered media by timestamp alone.
        if len(candidates) != 1:
            raise ValueError("C4/X5 companion has no unique destination: %s" % path)
        for child in dirs:
            if inspection.stamps.day_prefix(child.name):
                refused = []
                for _, child_files in inspection.tool.canonicalise.walk_bottom_up(child, inspection.tool.path_key(child), refused):
                    if any(inspection.media(other) and inspection.tool.matching.shot_key(other.name) == key for other in child_files):
                        raise ValueError("C4/X5 companion also matches an existing child: %s" % path)
                if refused:
                    raise ValueError("T4 cannot inspect existing child: %s" % child)
        return next(iter(candidates))

    for path in files:
        if path in media:
            continue
        companion = inspection.companion(path)
        if companion is None:
            raise ValueError("C3 unclassified loose file requires a person: %s" % path)
        day = destination_day(path)
        moves.append((path, children[day] / inspection.taxonomy.taxonomy_folder(inspection.config, companion[0]) / path.name))
    for directory in dirs:
        if directory.name.casefold() not in inspection.tax:
            continue
        if directory.name.casefold() == inspection.taxonomy.taxonomy_folder(inspection.config, "geolocations").casefold():
            continue
        destinations = {}
        refused = []
        for _, entries in inspection.tool.canonicalise.walk_bottom_up(directory, inspection.tool.path_key(directory), refused):
            destinations.update((path, destination_day(path)) for path in entries)
        if refused or not destinations:
            raise ValueError("C4 taxonomy folder cannot be attributed to a child: %s" % directory)
        first_day = min(destinations.values())
        relocated = children[first_day] / directory.name
        moves.append((directory, relocated))
        # Move the whole shell first, then redistribute the other days' files.
        # Even empty structural children survive, and no directory is deleted.
        for path, day in destinations.items():
            if day != first_day:
                relative = path.relative_to(directory)
                moves.append((relocated / relative, children[day] / directory.name / relative))
    targets = [inspection.tool.path_key(target) for _, target in moves]
    if len(set(targets)) != len(targets):
        raise ValueError("N4 migration has conflicting destinations")
    # Directories first so a loose sidecar cannot pre-create their target.
    return sorted(moves, key=lambda move: (not move[0].is_dir(), str(move[0])))


def fix(tool, run):
    inspection = Inspection(tool, run).scan()
    # Deepest first: moving a parent cannot invalidate a pending child path.
    failures = []
    resolve_videos(inspection, failures)
    for folder, children, tree in sorted(inspection.events, key=lambda item: len(item[0].parts), reverse=True):
        if not children:
            continue
        try:
            if any(rule == "T4" and (path == folder or folder in path.parents)
                   for rule, path, _ in inspection.issues):
                raise ValueError("T4 cannot migrate an incompletely inspected group: %s" % folder)
            moves = loose_media_plan(inspection, folder)
            if moves:
                details = "\n".join("    %s\n      -> %s" % move for move in moves)
                run.report("warn", "C4 gather loose media from %s:\n%s" % (folder, details))
                if run.apply and run.confirm("C4 move this group's files to the children shown above?\n%s" % details):
                    completed = []
                    try:
                        for source, target in moves:
                            checked_move(inspection, source, target, "C4")
                            completed.append((source, target))
                    except OSError:
                        for source, target in reversed(completed):
                            checked_move(inspection, target, source, "C4 rollback")
                        raise
            parsed = inspection.stamps.split_dated_folder(folder.name)
            day = tool.date_of(parsed.date)
            # N6 forbids deriving a replacement date. C12 changes the parent
            # to match the group's stated start, retaining its complete name.
            if folder.parent.name in inspection.months.values():
                destination = tree.parent / str(day.year) / inspection.months[day.strftime("%m")] / folder.name
                if tool.path_key(destination) != tool.path_key(folder):
                    run.report("warn", "C12 %s\n    -> %s" % (folder, destination))
                    if run.apply and run.confirm("C12 move this group?\n%s\n  -> %s" % (folder, destination)):
                        checked_move(inspection, folder, destination, "C12")
                        destination_tree = tree.parent / str(day.year)
                        if destination_tree not in run.trees:
                            run.trees.append(destination_tree)
        except (OSError, ValueError) as error:
            failures.append((folder, str(error)))
            run.report("warn", str(error))
    # The shared engines maintain markers and span names after the moves.
    # On a dry run these only report; on apply they use the same journal.
    repair_companions(inspection, failures)
    current = Inspection(tool, run).scan()
    for folder, children, _ in sorted(current.events, key=lambda item: len(item[0].parts), reverse=True):
        if children or current.grouping.carries_group_marker(folder.name):
            continue
        if any(rule in ("T4", "N6") and (path == folder or folder in path.parents)
               for rule, path, _ in current.issues):
            continue
        try:
            _, files = current.entries(folder)
            target = leaf_target(current, folder, files)
            if target != folder:
                run.report("warn", "N3/N10 %s\n    -> %s" % (folder, target))
                if run.apply:
                    checked_move(current, folder, target, "N3/N10")
        except (OSError, ValueError) as error:
            failures.append((folder, str(error)))
    marker_code = 1 if any(rule in ("T4", "N6") for rule, _, _ in current.issues) else tool.step_group_markers(run)
    final = Inspection(tool, run).scan()
    for folder, reason in failures:
        final.issue("T3", folder, reason)
    run.journal.write("standard_fix", applied=bool(run.apply), failures=len(failures))
    code = max(1 if marker_code else 0, report(final))
    if run.apply and code == 0:
        # Step 7 and the old group pass describe the pre-migration snapshot.
        # Only these findings were rechecked; preserve unrelated engine errors.
        run.issues[:] = [item for item in run.issues if item[1] not in ("Archive standard", tool.NON_COMPLIANT)]
    return code


def repair_companions(inspection, failures):
    """X5/X10: reuse the archive-wide engine after subjects moved in C4/V11."""
    tool, run = inspection.tool, inspection.run
    if any(rule == "T4" for rule, _, _ in inspection.issues):
        return
    def move(source, target):
        run.report("warn", "X10 %s\n    -> %s" % (source, target))
        if run.apply:
            checked_move(inspection, source, target, "X10")
        return Path(target)
    result = tool.matching.place_companions(
        run.trees, inspection.config,
        lambda folder: tool.duplicates_folder(folder, run, inspection.config),
        log=lambda message: run.report("dim", message), move=move,
        checksum=tool.archive_checksum(run), prune=False,
    )
    if result.errors:
        failures.append((run.target, "X10: %d companion moves failed" % result.errors))


def video_plan(inspection, video, captured):
    """V11: one plan includes the representative and all its local companions."""
    tool = inspection.tool
    legacy = importlib.import_module("src.pipeline_stages.legacy")
    event = video.parent.parent
    parsed = inspection.stamps.split_dated_folder(event.name)
    if parsed is None or legacy.date_folder_datetime(captured, inspection.config).date() != tool.date_of(parsed.date):
        raise ValueError("N7 supplied video time belongs to a different event day: %s" % video)
    metadata = legacy.parse_legacy_exif_text("", inspection.config)
    metadata["image_datetime"] = inspection.stamps.format_stamp(captured)
    name = legacy.legacy_filename(metadata, video.suffix, inspection.config)
    moves = [(video, event / name)]
    dirs, files = inspection.entries(video.parent)
    candidates = list(files)
    for directory in dirs:
        if directory.name.casefold() not in inspection.sidecars:
            raise ValueError("S2 unexpected folder in video waiting area: %s" % directory)
        nested, companions = inspection.entries(directory)
        if nested:
            raise ValueError("X12 nested folder in video companions: %s" % directory)
        candidates.extend(companions)
    original = video.name.removeprefix(tool.legacy_videos.TO_RENAME_PREFIX)
    subjects = {video.name.casefold(), video.stem.casefold(), original.casefold(), Path(original).stem.casefold()}
    spellings = inspection.grouping.companion_extension_spellings(inspection.config)
    for path in candidates:
        companion = inspection.companion(path)
        if companion is None or companion[1].casefold() not in subjects:
            continue
        key, subject, extension = companion
        # A historical stem shared by two waiting videos is not attributable.
        if any(other != video and inspection.media(other)
               and subject.casefold() in {other.name.casefold(), other.stem.casefold(),
                   other.name.removeprefix(tool.legacy_videos.TO_RENAME_PREFIX).casefold(),
                   Path(other.name.removeprefix(tool.legacy_videos.TO_RENAME_PREFIX)).stem.casefold()}
               for other in files):
            raise ValueError("X5 ambiguous video companion: %s" % path)
        moves.append((path, event / inspection.taxonomy.taxonomy_folder(inspection.config, key)
                      / (name + spellings[extension.casefold()])))
    keys = [tool.path_key(target) for _, target in moves]
    if len(keys) != len(set(keys)) or any(os.path.lexists(tool.extended_path(target)) for _, target in moves):
        raise ValueError("T2 video or companion destination already exists")
    return moves


def resolve_videos(inspection, failures):
    """Never interpolate: an explicit time or an interactive human decision (V4)."""
    tool, run = inspection.tool, inspection.run
    decisions = {}
    if run.video_times:
        decisions = json.loads(Path(run.video_times).read_text(encoding="utf-8"))
        if not isinstance(decisions, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in decisions.items()):
            raise ValueError("--video-times must map video paths to ISO datetime strings")
    pending = [path for rule, path, _ in inspection.issues if rule == "V9"]
    unknown = set(decisions) - {path.relative_to(run.target).as_posix() for path in pending}
    if unknown:
        raise ValueError("--video-times contains paths that are not unresolved videos in this run: " + ", ".join(sorted(unknown)))
    updated_events = set()
    for video in pending:
        try:
            if any(rule == "T4" and (path == video.parent or video.parent in path.parents)
                   for rule, path, _ in inspection.issues):
                raise ValueError("T4 cannot inspect every video companion: %s" % video)
            key = video.relative_to(run.target).as_posix()
            value = decisions.get(key)
            if value is None and run.apply and not run.assume_yes and sys.stdin and sys.stdin.isatty():
                _, anchors = inspection.entries(video.parent.parent)
                run.report("warn", "V9 %s\nDated anchors (no time is inferred):\n%s" %
                           (video, "\n".join(str(path) for path in anchors if inspection.moment(path))))
                try:
                    value = input("Real capture time YYYY-MM-DDTHH:MM:SS (blank leaves pending): ").strip()
                except (EOFError, KeyboardInterrupt):
                    value = None
            if not value:
                continue
            captured = datetime.datetime.fromisoformat(value)
            if captured.tzinfo is not None or captured.microsecond or value != captured.isoformat(timespec="seconds"):
                raise ValueError("V11 requires a complete local capture time: YYYY-MM-DDTHH:MM:SS")
            moves = video_plan(inspection, video, captured)
            details = "\n".join("    %s\n      -> %s" % move for move in moves)
            run.report("warn", "V11 resolve video:\n" + details)
            if not run.apply or not run.confirm("V11 apply this capture-time decision and companion moves?\n" + details):
                continue
            completed = []
            try:
                for source, target in moves:
                    checked_move(inspection, source, target, "V11")
                    completed.append((source, target))
            except OSError:
                # Restore the waiting state on a partial failure, without ever
                # replacing a file. Both forward and rollback moves are logged.
                for source, target in reversed(completed):
                    checked_move(inspection, target, source, "V11 rollback")
                raise
            updated_events.add(video.parent.parent)
        except (OSError, ValueError) as error:
            failures.append((video, str(error)))
    # Defer folder renames until every video has used its original path.
    for event in sorted(updated_events, key=lambda path: len(path.parts), reverse=True):
        try:
            _, files = inspection.entries(event)
            target = tool.canonicalise.plan_for(event, files, run.grouping_settings)
            if target:
                checked_move(inspection, event, target, "V9")
        except (OSError, ValueError) as error:
            failures.append((event, str(error)))
