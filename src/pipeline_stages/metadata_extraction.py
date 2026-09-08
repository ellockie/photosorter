from pathlib import Path

from src.core import \
    MediaAsset, \
    PipelineContext, \
    PipelineStage, \
    file_md5
from src.pipeline_stages.legacy import \
    parse_legacy_exif_sidecar
from src.pipeline_stages.provenance import \
    sidecar_candidates


class MetadataExtractionStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="metadata-extraction",
            display_name="Metadata Extraction",
            description=(
                "Turns each INBOX file into an asset: parses its ._exif sidecar for "
                "capture time and camera, attaches companions, and checksums it. Reads "
                "every intake byte for the MD5."
            ),
            dependencies=("exiftool-batch",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        unsorted = Path(context.config["paths"]["unsorted_folder"])
        media_extensions = context.media_extensions()
        assets = []

        if not unsorted.exists():
            context.log("Metadata extraction skipped: unsorted folder does not exist")
            return context

        candidates = [
            path for path in unsorted.iterdir()
            if path.is_file() and path.suffix.lower() in media_extensions
        ]
        # Every file is re-read in full here for its MD5, so this loop is
        # disk-bound on the intake, not on the sidecar parsing.
        reporter = context.progress(
            self.stage_id,
            "Reading sidecars and checksumming",
            total=len(candidates),
            total_bytes=sum(self._size_of(path) for path in candidates),
        )
        sidecars_found = 0

        for path in candidates:
            asset = MediaAsset(path)
            exif_sidecar = path.with_name(path.name + "._exif")
            if exif_sidecar.exists():
                sidecars_found += 1
                asset.register_sidecar("exif", exif_sidecar)
                asset.metadata.update(parse_legacy_exif_sidecar(exif_sidecar, context.config))
            for sidecar in sidecar_candidates(path, context.config):
                if sidecar.exists() and sidecar != exif_sidecar:
                    asset.register_sidecar(sidecar.name, sidecar)
            asset.metadata["md5"] = file_md5(path)
            asset.metadata["size"] = path.stat().st_size
            asset.metadata["modified_at"] = path.stat().st_mtime
            provenance = context.provenance.get(asset.metadata["md5"])
            if provenance and provenance.get("origin_label"):
                asset.metadata["origin_label"] = provenance["origin_label"]
            assets.append(asset)
            reporter.advance(size_bytes=asset.metadata["size"], note=path.name)

        context.log(reporter.finish())
        context.assets = assets
        context.counters["assets"] = len(assets)
        missing_exif = sum(1 for asset in assets if "image_datetime" not in asset.metadata)
        cameras = sorted({
            asset.metadata.get("camera_symbol")
            for asset in assets
            if asset.metadata.get("camera_symbol")
        })
        context.set_stage_stats(
            self.stage_id,
            inputs=len(assets),
            outputs=len(assets) - missing_exif,
            errors=missing_exif,
            sidecars=sidecars_found,
            cameras=len(cameras),
        )
        context.log(
            f"Discovered {len(assets)} media asset(s); "
            f"{sidecars_found} had an EXIF sidecar"
        )
        if cameras:
            # Which cameras this intake came from is the fastest read on
            # whether the batch is what you thought you were importing.
            context.log(f"Cameras in this batch: {', '.join(cameras)}")
            context.add_stage_note(self.stage_id, f"cameras: {', '.join(cameras)}")
        if missing_exif:
            note = (
                f"{missing_exif} asset(s) have no EXIF capture time -- these cannot be "
                "renamed or dated and will end up in READY"
            )
            context.log(note)
            context.add_stage_note(self.stage_id, note)
        return context

    @staticmethod
    def _size_of(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0
