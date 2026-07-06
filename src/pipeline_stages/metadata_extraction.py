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
            dependencies=("exiftool-batch",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        unsorted = Path(context.config["paths"]["unsorted_folder"])
        media_extensions = context.media_extensions()
        assets = []

        if not unsorted.exists():
            context.log("Metadata extraction skipped: unsorted folder does not exist")
            return context

        for path in unsorted.iterdir():
            if not path.is_file() or path.suffix.lower() not in media_extensions:
                continue
            asset = MediaAsset(path)
            exif_sidecar = path.with_name(path.name + "._exif")
            if exif_sidecar.exists():
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

        context.assets = assets
        context.counters["assets"] = len(assets)
        missing_exif = sum(1 for asset in assets if "image_datetime" not in asset.metadata)
        context.set_stage_stats(
            self.stage_id,
            inputs=len(assets),
            outputs=len(assets) - missing_exif,
            errors=missing_exif,
        )
        context.log(f"Discovered {len(assets)} media assets")
        if missing_exif:
            context.log(f"{missing_exif} assets have no EXIF sidecar datetime")
        return context
