"""Deterministic local classification for non-camera images."""

from collections import Counter
import math
import os
import shutil

from PIL import Image, UnidentifiedImageError

from utils.colorise import Colorise


PHOTO_FOLDER = "_POTENTIAL_PHOTOS"
INFOGRAPHIC_FOLDER = "_POTENTIAL_INFOGRAPHICS"
TEXT_SCREENSHOT_FOLDER = "_POTENTIAL_TEXT_SCREENSHOTS"
CLASSIFICATION_FOLDERS = (PHOTO_FOLDER, INFOGRAPHIC_FOLDER, TEXT_SCREENSHOT_FOLDER)


def _tonal_statistics(pixels, width, height):
    total = len(pixels)
    if not pixels:
        return 0.0, 0.0, 1.0, 0.0

    greys = [round((red * .299) + (green * .587) + (blue * .114)) for red, green, blue in pixels]
    grey_levels = Counter(value >> 3 for value in greys)
    grey_entropy = -sum(
        (count / total) * math.log2(count / total)
        for count in grey_levels.values()
    ) / 5.0

    edges = flat_pairs = samples = 0
    for y in range(height):
        for x in range(width):
            position = y * width + x
            if x + 1 < width:
                difference = abs(greys[position] - greys[position + 1])
                samples += 1
                flat_pairs += difference <= 3
                edges += difference >= 24
            if y + 1 < height:
                difference = abs(greys[position] - greys[position + width])
                samples += 1
                flat_pairs += difference <= 3
                edges += difference >= 24
    busy_row_threshold = max(5, width // 25)
    busy_rows = sum(
        sum(
            abs(greys[(y * width) + x] - greys[(y * width) + x + 1]) >= 32
            for x in range(width - 1)
        ) >= busy_row_threshold
        for y in range(height)
    )
    return (
        grey_entropy,
        edges / max(samples, 1),
        flat_pairs / max(samples, 1),
        busy_rows / max(height, 1),
    )


def _image_statistics(image_path):
    """Return colour and texture statistics from a small RGB sample."""
    with Image.open(image_path) as source:
        image = source.convert("RGB")
        image.thumbnail((256, 256))
        width, height = image.size
        pixels = list(image.getdata())
        horizontal_margin = width // 5
        vertical_margin = height // 5
        centre = image.crop((
            horizontal_margin,
            vertical_margin,
            width - horizontal_margin,
            height - vertical_margin,
        ))
        centre_width, centre_height = centre.size
        centre_pixels = list(centre.getdata())

    if not pixels:
        return 0.0, 0.0, 1.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0

    colours = Counter((red >> 3, green >> 3, blue >> 3) for red, green, blue in pixels)
    total = len(pixels)
    entropy = -sum((count / total) * math.log2(count / total) for count in colours.values()) / 15.0
    saturation = sum((max(red, green, blue) - min(red, green, blue)) / max(max(red, green, blue), 1) for red, green, blue in pixels) / total
    dominant_share = max(colours.values()) / total

    grey_entropy, edge_density, flat_share, busy_row_share = _tonal_statistics(pixels, width, height)
    centre_grey_entropy, _, centre_flat_share, _ = _tonal_statistics(
        centre_pixels,
        centre_width,
        centre_height,
    )
    return (
        entropy,
        saturation,
        dominant_share,
        edge_density,
        grey_entropy,
        flat_share,
        busy_row_share,
        centre_grey_entropy,
        centre_flat_share,
    )


def classify_image(image_path):
    """Classify by palette richness and simple text-layout signals, without AI."""
    (
        entropy,
        saturation,
        dominant_share,
        edge_density,
        grey_entropy,
        flat_share,
        busy_row_share,
        centre_grey_entropy,
        centre_flat_share,
    ) = _image_statistics(image_path)

    # Photographs tend to have gradual edges, naturally textured regions, or a
    # tonally rich centre even when most of the frame is pure black or white.
    low_edge_photo = edge_density <= .065 and centre_grey_entropy >= .45
    natural_texture_photo = (
        entropy >= .24
        and dominant_share <= .20
        and flat_share <= .60
        and edge_density < .18
    )
    monochrome_photo = saturation <= .08 and centre_grey_entropy >= .75
    if low_edge_photo or natural_texture_photo or monochrome_photo:
        return PHOTO_FOLDER

    # Text captures have dense high-contrast rows or repeated glyphs over a
    # dominant flat background.  These branches also cover photographs of
    # documents and coloured chat/message screenshots without using OCR.
    dense_document = edge_density >= .30
    vivid_text_panel = entropy <= .10 and saturation >= .90
    coloured_text_background = dominant_share >= .80 and saturation >= .30
    monochrome_text_background = dominant_share >= .70 and flat_share < .82
    sparse_text_page = (
        entropy <= .20
        and .55 <= dominant_share < .70
        and busy_row_share < .50
    )
    sparse_monochrome_text = (
        entropy <= .06
        and dominant_share >= .80
        and busy_row_share <= .10
    )
    colourful_text_capture = edge_density >= .18 and saturation >= .30
    if (
        dense_document
        or vivid_text_panel
        or coloured_text_background
        or monochrome_text_background
        or sparse_text_page
        or sparse_monochrome_text
        or colourful_text_capture
    ):
        return TEXT_SCREENSHOT_FOLDER
    return INFOGRAPHIC_FOLDER


def classify_other_images(other_images_path, progress_callback=None, update_every=10):
    """Move unclassified images into content-type subfolders."""
    counts = {folder: 0 for folder in CLASSIFICATION_FOLDERS}
    if not os.path.isdir(other_images_path):
        return counts
    for folder in CLASSIFICATION_FOLDERS:
        os.makedirs(os.path.join(other_images_path, folder), exist_ok=True)
    entries = [entry for entry in os.scandir(other_images_path) if entry.is_file()]
    processed = 0
    if progress_callback:
        progress_callback(processed, len(entries))
    for entry in entries:
        try:
            destination_folder = classify_image(entry.path)
        except (OSError, UnidentifiedImageError):
            print(Colorise.yellow("  - could not classify image, leaving in place: " + entry.name))
        else:
            shutil.move(entry.path, os.path.join(other_images_path, destination_folder, entry.name))
            counts[destination_folder] += 1
            print("  - " + destination_folder + ": " + entry.name)
        processed += 1
        pending = len(entries) - processed
        if progress_callback and (processed % update_every == 0 or pending == 0):
            progress_callback(processed, pending)
    return counts
