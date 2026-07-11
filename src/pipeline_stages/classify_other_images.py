import os

from src.core import \
    PipelineContext, \
    PipelineStage


class ClassifyOtherImagesStage(PipelineStage):
    def __init__(self):
        super().__init__(
            stage_id="classify-other-images",
            display_name="Classify Other Images",
            dependencies=("move-other-images",),
        )

    def execute(self, context: PipelineContext) -> PipelineContext:
        from src.other_image_classifier import \
            INFOGRAPHIC_FOLDER, \
            PHOTO_FOLDER, \
            TEXT_SCREENSHOT_FOLDER, \
            classify_other_images

        paths = context.config.get("paths", {})
        camera_uploads = paths.get("ingest", {}).get("camera_uploads") or paths.get("camera_uploads")
        classification_inputs = 0
        context.set_stage_stats(self.stage_id, inputs=0, outputs=0, errors=0)

        def update_progress(processed, pending):
            nonlocal classification_inputs
            classification_inputs = processed + pending
            context.counters["other_images_classification_processed"] = processed
            context.counters["other_images_classification_pending"] = pending
            context.set_stage_stats(
                self.stage_id,
                inputs=classification_inputs,
                outputs=processed,
            )
            context.log(f"Classifying other images: {processed} processed, {pending} pending")

        counts = classify_other_images(
            os.path.join(camera_uploads, "_Other images"),
            progress_callback=update_progress,
        )
        context.counters["other_image_photos"] += counts[PHOTO_FOLDER]
        context.counters["other_image_infographics"] += counts[INFOGRAPHIC_FOLDER]
        context.counters["other_image_text_screenshots"] += counts[TEXT_SCREENSHOT_FOLDER]
        classified_outputs = sum(counts.values())
        context.set_stage_stats(
            self.stage_id,
            inputs=classification_inputs,
            outputs=classified_outputs,
            errors=max(classification_inputs - classified_outputs, 0),
        )
        context.log(
            "Classified other images: "
            f"{counts[PHOTO_FOLDER]} photos, {counts[INFOGRAPHIC_FOLDER]} infographics, "
            f"{counts[TEXT_SCREENSHOT_FOLDER]} text screenshots"
        )
        return context
