from src.core import \
    PipelineContext, \
    PipelineStage


def load_legacy_move_other_images():
    from src.move_other_images import \
        counter, \
        move_other_images
    return move_other_images, counter


class MoveOtherImagesStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="move-other-images",
            display_name="Move Other Images",
            dependencies=("legacy-unsorted-migration",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        move_other_images, legacy_counter = load_legacy_move_other_images()
        extensions = context.config.get("extensions", {})
        paths = context.config.get("paths", {})

        for key in legacy_counter:
            legacy_counter[key] = 0

        move_other_images(
            src_path=paths.get("ingest", {}).get("camera_uploads") or paths.get("camera_uploads"),
            other_image_extensions=extensions.get("other_images", []),
            video_extensions=extensions.get("videos", []),
        )

        context.counters["camera_upload_photos"] += legacy_counter["PHOTOS"]
        context.counters["camera_upload_videos"] += legacy_counter["VIDEOS"]
        context.counters["other_images_moved"] += legacy_counter["OTHER_IMAGES"]
        context.counters["other_files_moved"] += legacy_counter["OTHER_FILES"]
        context.log(
            "Separated Camera Uploads: "
            f"{legacy_counter['PHOTOS']} camera photos, "
            f"{legacy_counter['VIDEOS']} videos, "
            f"{legacy_counter['OTHER_IMAGES']} other images, "
            f"{legacy_counter['OTHER_FILES']} other files"
        )
        return context
