import os

os.environ.setdefault("PHOTO_BASE_FOLDER", r"c:\__PHOTOS")

from src.main import \
    _TASK_move_result_exif_sidecar, \
    SUBFOLDER_NAMES


def test_legacy_result_move_carries_exif_sidecar_to_final_folder(tmp_path):
    staging_folder = tmp_path / "1. Original JPG"
    staging_exif_folder = staging_folder / SUBFOLDER_NAMES["EXIF"]
    destination_folder = tmp_path / "__READY" / "2026-05-14_(Thu) - 1. ######"
    staging_exif_folder.mkdir(parents=True)
    destination_folder.mkdir(parents=True)

    image_name = "2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50__I100__C6D.jpg"
    image_path = staging_folder / image_name
    sidecar_path = staging_exif_folder / "2026-05-14_(Thu)_10.30.00__f2.8__T1_250__L50__I100__C6D._exif"
    image_path.write_text("photo", encoding="utf-8")
    sidecar_path.write_text("exif", encoding="utf-8")

    _TASK_move_result_exif_sidecar((str(image_path), image_name), str(destination_folder))

    expected = destination_folder / SUBFOLDER_NAMES["EXIF"] / sidecar_path.name
    assert expected.read_text(encoding="utf-8") == "exif"
    assert not sidecar_path.exists()
