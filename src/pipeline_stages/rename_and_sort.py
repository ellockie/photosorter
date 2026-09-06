from pathlib import Path

from src.core import \
    CollisionDecision, \
    CollisionResult, \
    NameCollisionResolver, \
    PipelineContext, \
    PipelinePaused, \
    PipelineStage, \
    file_md5, \
    safe_delete, \
    safe_rename
from src.pipeline_stages.legacy import \
    legacy_filename
from src.pipeline_stages.provenance import \
    renamed_sidecar_path, \
    resolve_sidecar_target, \
    sidecar_candidates
from src.pipeline_stages.siblings import \
    DIMENSIONS_METADATA_KEY, \
    SUBSECOND_METADATA_KEY, \
    are_siblings, \
    family_counts, \
    next_ordinal_name, \
    occupant_names, \
    sibling_name, \
    subsecond_of_sidecar
from src.utils.dimensions import dimensions_of_sidecar


def unique_duplicate_path(path: Path, suffix: str, md5: str) -> Path:
    index = 1
    while True:
        candidate = path.with_name(f"{path.stem}{suffix}_{md5}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


class RenameAndSortStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="rename-and-sort",
            display_name="Rename and Sort",
            dependencies=("timezone-and-travel",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        resolver = NameCollisionResolver.from_context(context)
        renamed = 0
        skipped = 0
        exif_missing = 0
        # Which seconds hold more than one shot, counted over the whole batch
        # AND what is already on disk beside it, before a single file moves
        # (F9c). A fraction is only written where there is a sibling to tell
        # apart, and that cannot be decided one asset at a time: the third
        # shot in a second meets no name collision at all, because the first
        # two took fractions and left the plain name free.
        crowded = self._crowded_seconds(context)

        for asset in context.assets:
            source_path = asset.primary_path
            if not source_path.exists():
                skipped += 1
                continue
            if "image_datetime" not in asset.metadata:
                context.log(f"Rename skipped, EXIF metadata missing: {source_path.name}")
                exif_missing += 1
                skipped += 1
                continue
            new_name = legacy_filename(asset.metadata, source_path.suffix, context.config)
            if new_name in crowded:
                # Another shot claims this second, so the fraction earns its
                # place: it is what tells the two apart (F9). Where the camera
                # recorded none, the name stays plain and the pair is settled
                # further down, by F4 or by a person.
                new_name = sibling_name(
                    new_name, asset.metadata.get(SUBSECOND_METADATA_KEY))
            target_path = source_path.with_name(new_name)
            # The name now carries the sub-second, so a file already filed
            # under the fraction-less form of it is still the same shot's name
            # and still a collision (F9c). Missing that would file a re-ingested
            # copy of an already-archived photo a second time.
            occupied = self._occupied_target(source_path, new_name)
            if occupied is not None and occupied != source_path:
                # ``occupied`` is the file already holding this shot's name --
                # under the fraction-less form of it when the archive predates
                # F9c. It is what the arrival is compared against and, if it
                # loses, what gets renamed; the arrival's own name stays the
                # one generated from its EXIF.
                sibling_target = self._settle_as_siblings(
                    context, asset, source_path, occupied, target_path)
                if sibling_target is not None:
                    self._rename(asset, source_path, sibling_target)
                    renamed += 1
                    continue
                # Dimensions decide _LOWRES, not the byte ratio (F10):
                # a compressible exposure is not a low-resolution one.
                result = resolver.resolve(
                    occupied, source_path, context, self.stage_id,
                    existing_dimensions=self._occupant_dimensions(context, occupied),
                    candidate_dimensions=asset.metadata.get(DIMENSIONS_METADATA_KEY),
                )
                if result.decision == CollisionDecision.PROMPT:
                    # Ambiguous collision: only the user can call it. Block here
                    # until they do — for as long as that takes — then carry
                    # their choice into the same handling as an automatic one.
                    # Skipping (what this used to do) silently stranded the file
                    # in the inbox and made the answer they clicked a no-op.
                    result = self._resolve_by_prompt(context, result, source_path)
                    if result is None:
                        skipped += 1
                        continue
                if result.decision == CollisionDecision.SIBLINGS:
                    # A person recognised a burst no camera dated finely enough
                    # for F9a to prove. Neither file loses the name; the arrival
                    # is numbered from it.
                    self._rename(asset, source_path,
                                 self._sibling_ordinal_target(source_path, occupied))
                    renamed += 1
                    continue
                if result.decision == CollisionDecision.DISCARD_DUPLICATE:
                    # The image is a redundant duplicate: drop it AND its
                    # sidecars so they cannot be orphaned into __EXIF later.
                    for sidecar_path in list(asset.sidecars.values()):
                        if sidecar_path.exists():
                            safe_delete(sidecar_path)
                    safe_delete(source_path)
                    skipped += 1
                    continue
                # Every decision still standing here is a byte-difference:
                # identical files were discarded above, and two exposures were
                # settled as siblings. The loser is therefore a _DIFFERS, or a
                # _LOWRES when it is the smaller rendering of the two -- never a
                # _DUPE, which claims the two files are the same file (F4).
                loser_suffix = (
                    resolver.low_res_suffix
                    if result.reason == "significantly-smaller"
                    else resolver.differing_suffix
                )
                if result.decision == CollisionDecision.KEEP_CANDIDATE:
                    # The incoming file wins its own name; the file already
                    # there is renamed away using F4's <suffix>_<md5>_<n>
                    # grammar, off its own name rather than the arrival's.
                    existing_md5 = file_md5(occupied)
                    demoted_path = occupied.with_name(
                        f"{occupied.stem}{loser_suffix}_{existing_md5}_0{occupied.suffix}"
                    )
                    safe_rename(occupied, demoted_path)
                    self._retarget_collision_loser(context, occupied, demoted_path)
                else:
                    source_md5 = file_md5(source_path)
                    target_path = unique_duplicate_path(target_path, loser_suffix, source_md5)

            old_primary_name = source_path.name
            if target_path != source_path:
                safe_rename(source_path, target_path)
                asset.primary_path = target_path

            self._rename_sidecars(asset, old_primary_name, target_path.name)
            renamed += 1

        context.counters["renamed_assets"] = renamed
        context.counters["rename_skipped_assets"] = skipped
        context.set_stage_stats(
            self.stage_id,
            inputs=len(context.assets),
            outputs=renamed,
            errors=exif_missing,
        )
        context.log(f"Renamed {renamed} media assets and EXIF sidecars")
        return context

    def _crowded_seconds(self, context: PipelineContext) -> set:
        """The generated names that more than one file claims (F9c).

        Counted over both halves of the question at once: the assets this run
        is about to rename, and whatever already sits in the folder they are
        being renamed inside — a shot filed by an earlier run is a sibling of
        one arriving now just as much as two arriving together are.

        Keys are **bare** names, so a second is recognised as crowded however
        its files are currently spelled: a pair already carrying ``.633`` and
        ``.433`` still counts as two claims on the same second, which is what
        lets a third shot join them instead of taking the plain name.
        """
        names = []
        seen = set()
        for asset in context.assets:
            if "image_datetime" not in asset.metadata:
                continue
            names.append(legacy_filename(
                asset.metadata, asset.primary_path.suffix, context.config))
            seen.add(asset.primary_path)
        folders = {asset.primary_path.parent for asset in context.assets}
        for folder in folders:
            if not folder.is_dir():
                continue
            for path in folder.iterdir():
                # An asset's own current file is already counted above, under
                # the name it is about to take rather than the one it has.
                if path.is_file() and path not in seen:
                    names.append(path.name)
        return {name for name, count in family_counts(names).items() if count > 1}

    def _occupied_target(self, source_path: Path, new_name: str) -> Path | None:
        """The file already holding this shot's name, or None (F9c).

        Two names can be that file's: the one generated now, which carries the
        camera's sub-second, and the fraction-less form of it, which is what
        the same shot was called before F9c. Both are looked for, or a copy of
        a photo already in the archive would be given a name nothing there
        answers to and be filed all over again.
        """
        for candidate in occupant_names(new_name):
            path = source_path.with_name(candidate)
            if path.exists():
                return path
        return None

    def _settle_as_siblings(self, context: PipelineContext, asset, source_path: Path,
                            occupied: Path, target_path: Path) -> Path | None:
        """The name this asset takes as a sibling of ``occupied``, or None (F9).

        None means the two are not two exposures, and the collision resolver
        settles them as F4 says — this method makes no decision it cannot
        support with the camera's own metadata.

        **Both** files end up carrying their fraction, not just the arrival.
        A bare ``…20.43.52`` beside a ``…20.43.52.633`` sorts *after* it — "."
        precedes "_" — so leaving the occupant alone would file the pair in the
        wrong order in every viewer that sorts by name, which is the order the
        grouper GUI shows a day in. Naming both is also what makes them read as
        a pair rather than as a file and an exception to it.
        """
        if file_md5(source_path) == file_md5(occupied):
            return None                # a real duplicate; F4 owns it
        existing_subsecond = self._occupant_subsecond(context, occupied)
        candidate_subsecond = asset.metadata.get(SUBSECOND_METADATA_KEY)
        if not are_siblings(existing_subsecond, candidate_subsecond):
            return None
        self._rename_occupant(context, occupied,
                              sibling_name(occupied.name, existing_subsecond))
        # The arrival's own generated name already carries its fraction (F9c);
        # applying it again is a no-op, and doing so here keeps this correct
        # for a caller whose name somehow does not.
        return target_path.with_name(sibling_name(target_path.name, candidate_subsecond))

    def _sibling_ordinal_target(self, source_path: Path, target_path: Path) -> Path:
        """The name a person's ``siblings`` answer gives the arriving file (F9).

        Reached only when no camera recorded a fraction, so there is nothing
        true to write on the file already holding the name — it keeps it, and
        the arrival is numbered from it starting at 2.
        """
        folder = source_path.parent
        return source_path.with_name(
            next_ordinal_name(target_path.name, lambda name: (folder / name).exists()))

    def _rename(self, asset, source_path: Path, target_path: Path) -> None:
        """Move an asset onto its settled name, sidecars following (X5)."""
        old_primary_name = source_path.name
        safe_rename(source_path, target_path)
        asset.primary_path = target_path
        self._rename_sidecars(asset, old_primary_name, target_path.name)

    def _occupant_dimensions(self, context: PipelineContext,
                             occupant: Path) -> tuple[int, int] | None:
        """The pixel size of the file already holding the name, from its sidecar."""
        for sidecar in sidecar_candidates(occupant, context.config):
            if sidecar.exists():
                found = dimensions_of_sidecar(sidecar)
                if found is not None:
                    return found
        return None

    def _occupant_subsecond(self, context: PipelineContext, occupant: Path) -> str | None:
        """The fraction recorded for the file already holding the name.

        Read from its sidecar rather than from ``context.assets``: the occupant
        may be a file that was in the inbox before this run began, and so have
        no asset carrying its metadata.
        """
        for sidecar in sidecar_candidates(occupant, context.config):
            if sidecar.exists():
                found = subsecond_of_sidecar(sidecar)
                if found:
                    return found
        return None

    def _rename_occupant(self, context: PipelineContext, occupant: Path,
                         new_name: str) -> None:
        """Give the file already holding the contested name its own sibling name."""
        if new_name == occupant.name:
            return
        renamed_path = occupant.with_name(new_name)
        safe_rename(occupant, renamed_path)
        context.log(f"Sibling shots in one second: {occupant.name} -> {new_name}")
        for asset in context.assets:
            if asset.primary_path == occupant:
                asset.primary_path = renamed_path
                self._rename_sidecars(asset, occupant.name, new_name)
                return
        # Not a tracked asset — a file already sitting in the inbox when the run
        # started. Its sidecars still have to follow it (X5).
        for sidecar in sidecar_candidates(occupant, context.config):
            if sidecar.exists():
                safe_rename(sidecar, renamed_sidecar_path(sidecar, occupant.name, new_name))

    # The dashboard's name-collision buttons, mapped onto the same decisions the
    # resolver reaches on its own. "keep_existing" and "rename_candidate" are two
    # phrasings of one outcome: the incoming file keeps the loser's _DUPE grammar.
    _PROMPT_DECISIONS = {
        "keep_existing": CollisionDecision.RENAME_CANDIDATE,
        "rename_candidate": CollisionDecision.RENAME_CANDIDATE,
        "keep_candidate": CollisionDecision.KEEP_CANDIDATE,
        "discard_duplicate": CollisionDecision.DISCARD_DUPLICATE,
        # "these are two different shots" -- the answer F9a cannot reach on its
        # own when no camera recorded a sub-second (siblings.are_siblings).
        "siblings": CollisionDecision.SIBLINGS,
    }

    def _resolve_by_prompt(self, context: PipelineContext, result: CollisionResult,
                           source_path: Path) -> CollisionResult | None:
        """Turn an answered collision prompt into a decision, or None to skip.

        Blocks until the answer arrives. Outside the UI there is nobody to ask,
        so the historical behaviour — leave the file alone and report it — is the
        fallback, chosen explicitly rather than by timing out.
        """
        context.log(f"Name collision needs your decision: {source_path.name}")
        answer = context.await_prompt(result.prompt, auto_answer={"action": "skip"})
        action = str(answer.get("action", "skip"))

        if action == "cancel":
            raise PipelinePaused(f"Run cancelled at name collision: {source_path.name}")
        decision = self._PROMPT_DECISIONS.get(action)
        if decision is None:
            context.log(f"  left in place, no decision made: {source_path.name}")
            return None
        return CollisionResult(
            decision=decision,
            original=result.original,
            duplicate=result.duplicate,
            reason=f"user:{action}",
        )

    def _retarget_collision_loser(self, context: PipelineContext,
                                  old_path: Path, demoted_path: Path) -> None:
        # The demoted file may itself be a tracked asset (e.g. renamed earlier
        # in this run, or intaken already bearing the contested name). Its
        # primary_path must follow the _DUPE rename, or folder sorting skips
        # the asset and the file is stranded in the inbox.
        for asset in context.assets:
            if asset.primary_path == old_path:
                asset.primary_path = demoted_path
                self._rename_sidecars(asset, old_path.name, demoted_path.name)
                context.log(
                    f"Collision loser demoted: {old_path.name} -> {demoted_path.name}"
                )
                break

    def _rename_sidecars(self, asset, old_primary_name: str, new_primary_name: str) -> None:
        for name, sidecar_path in list(asset.sidecars.items()):
            if not sidecar_path.exists():
                continue
            desired = renamed_sidecar_path(sidecar_path, old_primary_name, new_primary_name)
            sidecar_target = resolve_sidecar_target(sidecar_path, desired)
            if sidecar_target is None:
                safe_delete(sidecar_path)
                del asset.sidecars[name]
                continue
            if sidecar_target != sidecar_path:
                safe_rename(sidecar_path, sidecar_target)
                asset.sidecars[name] = sidecar_target
