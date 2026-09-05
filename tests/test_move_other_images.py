import os
from pathlib import Path

os.environ.setdefault("PHOTO_BASE_FOLDER", r"c:\__PHOTOS")

from src.move_other_images import \
    OTHER_FILES_FOLDER, \
    OTHER_IMAGES_FOLDER, \
    counter, \
    move_other_images
from src.other_image_classifier import \
    INFOGRAPHIC_FOLDER, \
    PHOTO_FOLDER, \
    TEXT_SCREENSHOT_FOLDER, \
    classify_other_images


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


def test_classify_other_images_uses_palette_and_text_layout(tmp_path):
    from PIL import Image, ImageDraw

    other_images = tmp_path / OTHER_IMAGES_FOLDER
    other_images.mkdir()

    photo = Image.effect_noise((160, 120), 100).convert("RGB")
    photo.save(other_images / "photo.png")

    infographic = Image.new("RGB", (160, 120), "white")
    infographic_draw = ImageDraw.Draw(infographic)
    infographic_draw.rectangle((0, 0, 79, 59), fill="red")
    infographic_draw.rectangle((80, 0, 159, 59), fill="blue")
    infographic_draw.rectangle((0, 60, 79, 119), fill="green")
    infographic.save(other_images / "infographic.png")

    text = Image.new("RGB", (160, 120), "white")
    text_draw = ImageDraw.Draw(text)
    for y in range(15, 105, 15):
        text_draw.rectangle((15, y, 145, y + 3), fill="black")
    text.save(other_images / "text.png")

    counts = classify_other_images(str(other_images))

    assert (other_images / PHOTO_FOLDER / "photo.png").exists()
    assert (other_images / INFOGRAPHIC_FOLDER / "infographic.png").exists()
    assert (other_images / TEXT_SCREENSHOT_FOLDER / "text.png").exists()
    assert counts == {
        PHOTO_FOLDER: 1,
        INFOGRAPHIC_FOLDER: 1,
        TEXT_SCREENSHOT_FOLDER: 1,
    }


def test_classify_other_images_recognises_low_contrast_black_and_white_photo(tmp_path):
    from PIL import Image

    image = Image.new("RGB", (160, 120))
    pixels = []
    for y in range(120):
        for x in range(160):
            tone = 70 + ((x * 3 + y * 5 + (x * y) % 29) % 100)
            pixels.append((tone, tone, tone))
    image.putdata(pixels)
    image_path = tmp_path / "black-and-white-photo.png"
    image.save(image_path)

    from src.other_image_classifier import classify_image

    assert classify_image(image_path) == PHOTO_FOLDER


def test_real_classifier_fixtures_match_expected_folders():
    from src.other_image_classifier import classify_image

    fixture_root = Path(__file__).parent / "fixtures" / "other_image_classifier"
    expected_folders = {
        "expected_photos": PHOTO_FOLDER,
        "expected_infographics": INFOGRAPHIC_FOLDER,
        "expected_text_screenshots": TEXT_SCREENSHOT_FOLDER,
    }
    image_extensions = {".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}

    for fixture_folder, expected_classification in expected_folders.items():
        for image_path in (fixture_root / fixture_folder).iterdir():
            if image_path.is_file() and image_path.suffix.lower() in image_extensions:
                assert classify_image(image_path) == expected_classification, image_path.name


def test_classify_other_images_reports_progress_every_ten_files(monkeypatch, tmp_path):
    import src.other_image_classifier as classifier

    other_images = tmp_path / OTHER_IMAGES_FOLDER
    other_images.mkdir()
    for number in range(11):
        (other_images / f"image-{number}.png").write_text("image", encoding="utf-8")

    monkeypatch.setattr(classifier, "classify_image", lambda path: PHOTO_FOLDER)
    updates = []

    classifier.classify_other_images(
        str(other_images),
        progress_callback=lambda processed, pending: updates.append((processed, pending)),
    )

    assert updates == [(0, 11), (10, 1), (11, 0)]
