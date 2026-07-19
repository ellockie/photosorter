from src.core import \
    PipelineOrchestrator, \
    PipelineStage, \
    SafetyValidationStage
from src.pipeline_stages.exiftool_batch import ExiftoolBatchStage
from src.pipeline_stages.convert_crws import ConvertCrwsStage
from src.pipeline_stages.classify_other_images import ClassifyOtherImagesStage
from src.pipeline_stages.folder_intake import FolderIntakeStage
from src.pipeline_stages.display_extra_messages import DisplayExtraMessagesStage
from src.pipeline_stages.empty_file_quarantine import EmptyFileQuarantineStage
from src.pipeline_stages.folder_sorting import FolderSortingStage
from src.pipeline_stages.initialization import InitializationStage
from src.pipeline_stages.legacy_unsorted_migration import LegacyUnsortedMigrationStage
from src.pipeline_stages.metadata_extraction import MetadataExtractionStage
from src.pipeline_stages.launch_dpviewer import LaunchDpviewerStage
from src.pipeline_stages.move_results import MoveResultsStage
from src.pipeline_stages.move_other_images import MoveOtherImagesStage
from src.pipeline_stages.raw_staged_conversion import RawStagedConversionStage
from src.pipeline_stages.rename_and_sort import RenameAndSortStage
from src.pipeline_stages.screenshot_grouping import ScreenshotGroupingStage
from src.pipeline_stages.show_stats import ShowStatsStage
from src.pipeline_stages.stale_exif_relocation import StaleExifRelocationStage
from src.pipeline_stages.timezone_and_travel import TimezoneAndTravelStage
from src.pipeline_stages.upload_harvest import UploadHarvestStage


def build_default_stages() -> list[PipelineStage]:
    safety_stage = SafetyValidationStage()
    safety_stage.dependencies = ("display-extra-messages",)
    return [
        InitializationStage(),
        LegacyUnsortedMigrationStage(),
        MoveOtherImagesStage(),
        ClassifyOtherImagesStage(),
        UploadHarvestStage(),
        FolderIntakeStage(),
        StaleExifRelocationStage(),
        EmptyFileQuarantineStage(),
        ExiftoolBatchStage(),
        MetadataExtractionStage(),
        TimezoneAndTravelStage(),
        RenameAndSortStage(),
        ConvertCrwsStage(),
        LaunchDpviewerStage(),
        RawStagedConversionStage(),
        MoveResultsStage(),
        FolderSortingStage(),
        ScreenshotGroupingStage(),
        ShowStatsStage(),
        DisplayExtraMessagesStage(),
        safety_stage,
    ]


def build_default_orchestrator(mode=None) -> PipelineOrchestrator:
    kwargs = {}
    if mode is not None:
        kwargs["mode"] = mode
    return PipelineOrchestrator(build_default_stages(), **kwargs)
