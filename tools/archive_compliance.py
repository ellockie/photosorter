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
        self.parking = self.taxonomy.taxonomy_folder(self.config, "duplicates")
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
                # Tool bookkeeping: no rule in §1-§7 governs __LOGS, and a
                # conforming tool must not report what is in it (J2). It is
                # also the one child a year folder may have besides its month
                # folders (J1), so this skip is what keeps P3 honest.
                if self.tool.canonicalise.is_log_folder(entry.name):
                    continue
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
                # A year-level __DUPLICATES is where S7 used to put collision
                # losers. Read, never written (the N5 rule again): it is not
                # reported as a malformed year child, and nothing drains it --
                # where its contents belong is a decision for a person (L5).
                if folder.name.casefold() == self.parking.casefold():
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
        if mismarked_sibling(self, path) is not None:
            self.issue("F9", path,
                       "collision suffix on a second exposure, not a copy "
                       "(sub-second differs from the file it was named against)")
        elif mismarked_low_res(self, path) is not None:
            self.issue("F10", path,
                       "_LOWRES on a file that is not a smaller rendering "
                       "(same pixel dimensions as the file it was named against)")
        elif self.lone_fraction(path):
            self.issue("F9c", path,
                       "sub-second on a shot with no sibling in that second")
        elif top and is_low_res(self, path):
            self.issue("F7/F10", path,
                       "a downscale is a derivative: it belongs in "
                       + self.taxonomy.taxonomy_folder(self.config, "resized"))

    def lone_fraction(self, path):
        """F9c: a sub-second on a file that has nobody to be told apart from.

        The fraction is written to separate two shots in one second. Where the
        second holds only this one, it says nothing the plain stamp did not,
        and it comes off -- which is also how a name written by the brief
        version that put a fraction on everything is brought back into line.
        """
        if not self.media(path) or self.stamps.leading_subsecond(path.name) is None:
            return False
        wanted = self.tool.siblings.bare_name(path.name)
        _dirs, files = self.entries(path.parent)
        family = [one for one in files
                  if self.media(one) and self.tool.siblings.bare_name(one.name) == wanted]
        return len(family) < 2

    def dimensions(self, media_path):
        """The picture size recorded for a filed media file (F10)."""
        exif_folder = self.taxonomy.sidecar_subdir(media_path.parent, self.config)
        for extension in self.grouping.configured_extensions(
                self.config, "sidecars", self.grouping.DEFAULT_SIDECAR_EXTENSIONS):
            sidecar = exif_folder / (media_path.name + extension)
            if sidecar.is_file():
                found = self.tool.dimensions.dimensions_of_sidecar(
                    self.tool.extended_path(sidecar))
                if found is not None:
                    return found
        return None

    def subsecond(self, media_path):
        """The sub-second recorded for a filed media file, from its sidecar (X10).

        X1 names a sidecar after its subject's **full** name, and X10 puts it in
        the ``__EXIF`` directly inside the folder holding the subject, so the
        path is derived rather than searched for.
        """
        exif_folder = self.taxonomy.sidecar_subdir(media_path.parent, self.config)
        for extension in self.grouping.configured_extensions(
                self.config, "sidecars", self.grouping.DEFAULT_SIDECAR_EXTENSIONS):
            sidecar = exif_folder / (media_path.name + extension)
            if not sidecar.is_file():
                continue
            found = self.tool.siblings.subsecond_of_sidecar(
                self.tool.extended_path(sidecar))
            if found:
                return found
        return None


def report(inspection):
    for rule, path, reason in inspection.issues:
        inspection.run.report("warn", "%s %s: %s" % (rule, path, reason))
        inspection.run.flag("Archive standard", path, "%s: %s" % (rule, reason))
    inspection.run.report("ok", "Archive standard: %d outstanding finding(s)." % len(inspection.issues))
    inspection.run.journal.write("standard_check", findings=len(inspection.issues))
    return 1 if inspection.issues else 0


def check(tool, run):
    return report(Inspection(tool, run).scan())


def mismarked_sibling(inspection, path):
    """F9/PS-10: a collision suffix on a file that is a second exposure, not a copy.

    An earlier version of the pipeline settled *every* same-name collision with
    F4's ``_DUPE_<md5>_<n>``, including the one case that is not a collision at
    all: two shots taken inside one second, which generate one name because the
    name states the second and not the fraction. The result is a pair of files
    where one claims to be a byte-identical copy of the other and demonstrably
    is not.

    Returns ``(partner, this file's fraction, the partner's fraction)`` when
    the pair is provably two exposures, and None otherwise -- including for a
    genuine duplicate, for a ``_LOWRES`` (never matched: that is a claim about
    rendering), and for any pair whose cameras recorded no sub-second, where
    nothing here can tell a burst from one shot saved twice. Nothing is renamed
    on a guess.
    """
    loser = inspection.taxonomy.split_collision_suffix(path.name)
    if loser is None:
        return None
    partner = path.parent / loser.name
    if not partner.is_file():
        return None                    # the name it lost is not in this folder
    subsecond, partner_subsecond = inspection.subsecond(path), inspection.subsecond(partner)
    if not inspection.tool.siblings.are_siblings(partner_subsecond, subsecond):
        return None
    if inspection.tool.matching.default_checksum(inspection.tool.extended_path(path)) == \
            inspection.tool.matching.default_checksum(inspection.tool.extended_path(partner)):
        return None                    # identical bytes: the suffix was right
    return partner, subsecond, partner_subsecond


def is_low_res(inspection, path):
    """Does this name carry F4's ``_LOWRES``?"""
    parsed = inspection.taxonomy.split_collision_suffix(path.name)
    return parsed is not None and parsed.suffix == inspection.taxonomy.LOW_RES_SUFFIX


def mismarked_low_res(inspection, path):
    """F10: a ``_LOWRES`` that is not a smaller rendering of what it lost to.

    ``_LOWRES`` was written from the byte ratio alone before F10, so a file
    that merely compressed better than the one it collided with was filed as a
    lower resolution of it. Returns the partner when the claim is false --
    equal dimensions, or larger ones -- and None when it is true or cannot be
    checked. An unreadable pair is left alone: F10 refuses a guess in the same
    direction the naming rule does.
    """
    if not is_low_res(inspection, path):
        return None
    loser = inspection.taxonomy.split_collision_suffix(path.name)
    partner = path.parent / loser.name
    if not partner.is_file():
        return None
    dimensions, partner_dimensions = inspection.dimensions(path), inspection.dimensions(partner)
    if dimensions is None or partner_dimensions is None:
        return None
    if inspection.tool.dimensions.is_downscaled(partner_dimensions, dimensions):
        return None                    # the claim is true; leave it standing
    return partner


def low_res_repair_plan(inspection, path):
    """Rename a false ``_LOWRES`` to what it actually is (F10).

    ``_DIFFERS``: the two files claim one name and hold different bytes, which
    is all that can be said about them once resolution is ruled out. Which to
    keep stays a person's decision (F4) -- this only stops the name asserting
    something the pixels disprove. The checksum and index are carried across
    unchanged so the pair can still be matched up by eye.
    """
    if mismarked_low_res(inspection, path) is None:
        return []
    loser = inspection.taxonomy.split_collision_suffix(path.name)
    stem, suffix = Path(loser.name).stem, Path(loser.name).suffix
    wanted = inspection.taxonomy.differing_name(stem, loser.md5, loser.index, suffix)
    if wanted == path.name:
        return []
    moves = [(path, path.parent / wanted)]
    exif_folder = inspection.taxonomy.sidecar_subdir(path.parent, inspection.config)
    for extension in inspection.grouping.configured_extensions(
            inspection.config, "sidecars", inspection.grouping.DEFAULT_SIDECAR_EXTENSIONS):
        sidecar = exif_folder / (path.name + extension)
        if sidecar.is_file():
            moves.append((sidecar, exif_folder / (wanted + extension)))
    return moves


def resized_repair_plan(inspection, path):
    """Move a genuine downscale off the top level into ``__RESIZED`` (F7/F10)."""
    if not is_low_res(inspection, path) or mismarked_low_res(inspection, path) is not None:
        return []
    resized = inspection.taxonomy.taxonomy_subdir(path.parent, inspection.config, "resized")
    moves = [(path, resized / path.name)]
    exif_folder = inspection.taxonomy.sidecar_subdir(path.parent, inspection.config)
    resized_exif = inspection.taxonomy.sidecar_subdir(resized, inspection.config)
    for extension in inspection.grouping.configured_extensions(
            inspection.config, "sidecars", inspection.grouping.DEFAULT_SIDECAR_EXTENSIONS):
        sidecar = exif_folder / (path.name + extension)
        if sidecar.is_file():
            # X10: a sidecar sits in the __EXIF of the folder holding its
            # subject, so it moves into __RESIZED\__EXIF with it.
            moves.append((sidecar, resized_exif / (path.name + extension)))
    return moves


def lone_fraction_repair_plan(inspection, path):
    """Strip a sub-second that separates nothing (F9c), sidecars following."""
    if not inspection.lone_fraction(path):
        return []
    wanted = inspection.tool.siblings.bare_name(path.name)
    if wanted == path.name or (path.parent / wanted).exists():
        return []
    moves = [(path, path.parent / wanted)]
    exif_folder = inspection.taxonomy.sidecar_subdir(path.parent, inspection.config)
    for extension in inspection.grouping.configured_extensions(
            inspection.config, "sidecars", inspection.grouping.DEFAULT_SIDECAR_EXTENSIONS):
        sidecar = exif_folder / (path.name + extension)
        if sidecar.is_file():
            moves.append((sidecar, exif_folder / (wanted + extension)))
    return moves


def sibling_repair_plan(inspection, path):
    """The renames that turn one mismarked pair into two named exposures (F9).

    Both files move: the one carrying the false suffix, and the one it was
    named against, which takes its own fraction so the pair sorts in the order
    it was shot. Each sidecar follows its subject (X5), named per X1.
    """
    found = mismarked_sibling(inspection, path)
    if found is None:
        return []
    partner, subsecond, partner_subsecond = found
    loser = inspection.taxonomy.split_collision_suffix(path.name)
    moves = []
    for media, fraction in ((partner, partner_subsecond), (path, subsecond)):
        wanted = inspection.tool.siblings.sibling_name(loser.name, fraction)
        if wanted == media.name:
            continue
        moves.append((media, media.parent / wanted))
        exif_folder = inspection.taxonomy.sidecar_subdir(media.parent, inspection.config)
        for extension in inspection.grouping.configured_extensions(
                inspection.config, "sidecars", inspection.grouping.DEFAULT_SIDECAR_EXTENSIONS):
            sidecar = exif_folder / (media.name + extension)
            if sidecar.is_file():
                moves.append((sidecar, exif_folder / (wanted + extension)))
    return moves


# How many pairs the confirmation itself lists before it stops and points at
# the report above. The same reason ``STEP_VERDICT_ITEMS`` exists: a question
# nobody can see the end of is a question nobody reads to the end of.
SIBLING_PROMPT_ITEMS = 8


def repair_siblings(inspection, failures):
    """Rename every mismarked pair the scan found (F9). Dry run reports only.

    **One confirmation for the whole run**, not one per pair. A run covers a
    single year tree -- ``--year ALL`` is ``run_one_target`` in a loop, a fresh
    ``Run`` each time -- so one question per run is one question per year. That
    is the same judgement the network prompt already makes one level up: a
    prompt met seventy times in a row is a prompt somebody stops reading, and a
    confirmation that has been trained out of a person protects nothing.

    What is being approved is still shown in full. Every pair is reported
    above, move by move, before anything is asked; the question carries the
    counts, the year, and the first few pairs, and says where the rest is.
    """
    run = inspection.run
    # All three repairs share one question. To a person they are one finding —
    # "these collision names say something the files disprove" — and splitting
    # them would put the prompt count back up that a single question exists to
    # bring down.
    planners = {
        "F9": (sibling_repair_plan, "two exposures in one second, not duplicates"),
        "F10": (low_res_repair_plan, "_LOWRES on a file of the same dimensions"),
        "F7/F10": (resized_repair_plan, "a downscale belongs in __RESIZED"),
        "F9c": (lone_fraction_repair_plan, "a sub-second that separates nothing"),
    }
    plans = []
    for rule, path, _reason in list(inspection.issues):
        planner = planners.get(rule)
        if planner is None:
            continue
        try:
            moves = planner[0](inspection, path)
        except (OSError, ValueError) as error:
            failures.append((path, str(error)))
            run.report("warn", str(error))
            continue
        if moves:
            plans.append((path, moves, rule, planner[1]))
    if not plans:
        return

    for _path, moves, rule, headline in plans:
        run.report("warn", "%s %s:\n%s" % (rule, headline, sibling_move_details(moves)))
    if not run.apply:
        return
    if not run.confirm(sibling_confirmation(inspection, plans)):
        run.report("warn", "Not confirmed; %d collision name(s) left exactly as they are."
                   % len(plans))
        return

    for path, moves, rule, _headline in plans:
        # Rolled back a pair at a time. A pair that fails must not undo the
        # ones already renamed and journalled before it -- those are correct,
        # and re-reversing them would be a second unrequested rename.
        completed = []
        try:
            for source, target in moves:
                target.parent.mkdir(parents=True, exist_ok=True)
                checked_move(inspection, source, target, rule)
                completed.append((source, target))
        except OSError as error:
            for source, target in reversed(completed):
                try:
                    checked_move(inspection, target, source, rule + " rollback")
                except OSError as rollback_error:
                    failures.append((target, "%s rollback failed: %s" % (rule, rollback_error)))
            failures.append((path, str(error)))
            run.report("warn", str(error))


def sibling_move_details(moves):
    return "\n".join("    %s\n      -> %s" % (source, target)
                     for source, target in moves)


def sibling_confirmation(inspection, plans):
    """The single question the whole run's collision-name repairs are approved by."""
    files = sum(len(moves) for _, moves, _, _ in plans)
    trees = "\n    ".join(str(tree) for tree in inspection.run.trees)
    counts = {}
    for _path, _moves, rule, headline in plans:
        counts[(rule, headline)] = counts.get((rule, headline), 0) + 1
    summary = "\n".join("    %-7s %d x %s" % (rule, count, headline)
                        for (rule, headline), count in sorted(counts.items()))
    listed = "\n".join(
        "    %s\n      -> %s" % (moves[0][0].name, moves[0][1].name)
        for _path, moves, _rule, _headline in plans[:SIBLING_PROMPT_ITEMS])
    if len(plans) > SIBLING_PROMPT_ITEMS:
        listed += "\n    ... and %d more, each listed in full above." % (
            len(plans) - SIBLING_PROMPT_ITEMS)
    return (
        "%d collision name(s) say something the files themselves disprove:\n%s\n"
        "Repair them -- %d file(s) including sidecars -- under:\n    %s\n%s"
        % (len(plans), summary, files, trees, listed))


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
    # First: undo the names an earlier version wrote for pairs that were never
    # collisions (F9/PS-10). Doing it before the migrations means the rest of
    # this pass sees two properly named representatives rather than a file and
    # a thing calling itself a copy of it.
    repair_siblings(inspection, failures)
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
