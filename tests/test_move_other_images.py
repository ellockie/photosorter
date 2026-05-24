import os

os.environ.setdefault("PHOTO_BASE_FOLDER", r"c:\__PHOTOS")

from src.move_other_images import \
    OTHER_FILES_FOLDER, \
    OTHER_IMAGES_FOLDER, \
    counter, \
    move_other_images


def test_move_other_images_treats_configured_image_extensions_as_images(tmp_path):
    for key in counter:
        counter[key] = 0
    (tmp_path / "screenshot.png").write_text("png", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("txt", encoding="utf-8")
    (tmp_path / "clip.mov").write_text("mov", encoding="utf-8")

    move_other_images(
        src_path=str(tmp_path),
        other_image_extensions=[".png"],
        video_extensions=[".mp4", ".mov"],
    )

    assert (tmp_path / OTHER_IMAGES_FOLDER / "screenshot.png").exists()
    assert (tmp_path / OTHER_FILES_FOLDER / "notes.txt").exists()
    assert (tmp_path / "clip.mov").exists()
    assert counter["OTHER_IMAGES"] == 1
    assert counter["OTHER_FILES"] == 1
    assert counter["VIDEOS"] == 1


def test_move_other_images_moves_unknown_model_jpgs_to_other_images(monkeypatch, tmp_path):
    import src.move_other_images as move_other_images_module

    for key in counter:
        counter[key] = 0
    jpg = tmp_path / "valid-camera-photo.jpg"
    jpg.write_text("jpg", encoding="utf-8")

    class FakeExifTool:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get_metadata_batch(self, files):
            return [
                {
                    "SourceFile": files[0],
                    "EXIF:Model": "A real camera not yet in MY_CAMERA_SYMBOLS",
                }
            ]

    monkeypatch.setattr(move_other_images_module.exiftool, "ExifTool", FakeExifTool)

    move_other_images(
        src_path=str(tmp_path),
        other_image_extensions=[".png"],
        video_extensions=[".mp4"],
    )

    assert not jpg.exists()
    assert (tmp_path / OTHER_IMAGES_FOLDER / jpg.name).exists()
    assert counter["PHOTOS"] == 0
    assert counter["OTHER_IMAGES"] == 1
