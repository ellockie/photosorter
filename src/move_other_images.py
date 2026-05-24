import ntpath
import os
import shutil
from os.path import isfile, join, normpath
from os import listdir
import sys

import exiftool

from utils.colorise import Colorise
from constants.constants import CAMERA_UPLOADS_PATH, SUBROUTINE_LOG_INDENTATION, MY_CAMERA_SYMBOLS

'''
    Install correct exiftool wrapper via:
        pip install git+https://github.com/smarnach/pyexiftool
    https://github.com/smarnach/pyexiftool
'''

print(Colorise.blue(f"\n Python executable used:  {sys.executable}"))
print(Colorise.blue(f" Current python version:  {sys.version}\n"))
assert sys.version.startswith("3."), "Error: Python 3 is required!"

OTHER_IMAGES_FOLDER = "_Other images"
OTHER_FILES_FOLDER = "_Other files"
NOT_MOVEABLE_FILE = 'desktop.ini'
DEFAULT_CAMERA_IMAGE_EXTENSIONS = (".jpg", ".jpeg")
DEFAULT_OTHER_IMAGE_EXTENSIONS = (".png", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".heic", ".heif")
DEFAULT_VIDEO_EXTENSIONS = (".mp4",)

counter = {
    "PHOTOS": 0,
    "VIDEOS": 0,
    "OTHER_IMAGES": 0,
    "OTHER_FILES": 0,
}


def get_jpgs(src_path):
    my_jpgs = [join(src_path, f) for f in listdir(src_path) if isfile(
        join(src_path, f)) and (f.lower().endswith(".jpg") or f.lower().endswith(".jpeg"))]
    return my_jpgs


def normalise_extensions(extensions):
    return tuple(
        extension.lower()
        for extension in extensions
    )


def get_videos(src_path, video_extensions=DEFAULT_VIDEO_EXTENSIONS):
    video_extensions = normalise_extensions(video_extensions)
    my_videos = [join(src_path, f) for f in listdir(src_path) if isfile(
        join(src_path, f)) and f.lower().endswith(video_extensions)]
    counter["VIDEOS"] = len(my_videos)


def get_other_image_files(src_path, other_image_extensions=DEFAULT_OTHER_IMAGE_EXTENSIONS):
    other_image_extensions = normalise_extensions(other_image_extensions)
    return [join(src_path, f) for f in listdir(src_path) if isfile(
        join(src_path, f)) and f.lower().endswith(other_image_extensions)]


def get_other_files(src_path, ignored_extensions=None):
    ignored_extensions = normalise_extensions(ignored_extensions or (
        DEFAULT_CAMERA_IMAGE_EXTENSIONS + DEFAULT_OTHER_IMAGE_EXTENSIONS + DEFAULT_VIDEO_EXTENSIONS
    ))
    other_files = [join(src_path, f) for f in listdir(src_path) if isfile(
        join(src_path, f)) and not f.lower().endswith(ignored_extensions) and not f.endswith("desktop.ini")]
    return other_files


def get_filename_from_path(path):
    return ntpath.basename(path)


def process_jpgs(files, src_path):
    # print(files)
    if len(files) == 0:
        return
    print(Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}Moving images:"))
    with exiftool.ExifTool() as et:
        metadata = et.get_metadata_batch(files)
    for d in metadata:
        if "EXIF:Model" in list(d.keys()) and d["EXIF:Model"] in MY_CAMERA_SYMBOLS:
            counter["PHOTOS"] += 1
        else:
            move_other_image(d, src_path)


def move_other_image(d, src_path):
    msg = f"{SUBROUTINE_LOG_INDENTATION} - 'other' image:   {ntpath.basename(d['SourceFile'])}"
    dest = join(src_path, OTHER_IMAGES_FOLDER, get_filename_from_path(d["SourceFile"]))
    shutil.move(d["SourceFile"], dest)
    print(msg)
    counter["OTHER_IMAGES"] += 1


def process_other_image_files(files, src_path):
    for src_file_path in files:
        dest = join(src_path, OTHER_IMAGES_FOLDER, get_filename_from_path(src_file_path))
        shutil.move(src_file_path, dest)
        print(f"{SUBROUTINE_LOG_INDENTATION} - 'other' image:   {ntpath.basename(dest)}")
        counter["OTHER_IMAGES"] += 1


def process_other_files(files, src_path):
    for src_file_path in files:
        if NOT_MOVEABLE_FILE in src_file_path:
            continue
        try:
            dest = join(src_path, OTHER_FILES_FOLDER, get_filename_from_path(src_file_path))
            shutil.move(src_file_path, dest)
            print(f"{SUBROUTINE_LOG_INDENTATION} - 'other' file:    {ntpath.basename(dest)}")
            counter["OTHER_FILES"] += 1
        except Exception as e:
            print(("Could not move file: {}".format(src_file_path)))
            print(f"Error:\n============\n  {e}\n============")


def display_stats():
    print(f"{SUBROUTINE_LOG_INDENTATION}Files found in the uploads folder:")
    print(f"{SUBROUTINE_LOG_INDENTATION}                 My camera photos:  {counter['PHOTOS']}")
    print(f"{SUBROUTINE_LOG_INDENTATION}                     Other images:  {counter['OTHER_IMAGES']}")
    print(f"{SUBROUTINE_LOG_INDENTATION}                      Other files:  {counter['OTHER_FILES']}")
    print(f"{SUBROUTINE_LOG_INDENTATION}                           Videos:  {counter['VIDEOS']}")


def move_other_images(
        src_path=CAMERA_UPLOADS_PATH,
        other_image_extensions=DEFAULT_OTHER_IMAGE_EXTENSIONS,
        video_extensions=DEFAULT_VIDEO_EXTENSIONS):
    src_path = normpath(src_path)
    os.makedirs(join(src_path, OTHER_IMAGES_FOLDER), exist_ok=True)
    os.makedirs(join(src_path, OTHER_FILES_FOLDER), exist_ok=True)
    jpg_files = get_jpgs(src_path)
    process_jpgs(jpg_files, src_path)
    other_image_files = get_other_image_files(src_path, other_image_extensions)
    process_other_image_files(other_image_files, src_path)
    ignored_extensions = DEFAULT_CAMERA_IMAGE_EXTENSIONS + tuple(other_image_extensions) + tuple(video_extensions)
    other_files = get_other_files(src_path, ignored_extensions)
    process_other_files(other_files, src_path)
    get_videos(src_path, video_extensions)
    display_stats()


if __name__ == "__main__":
    try:
        move_other_images()
    except Exception as e:
        print("\n\tError occurred:")
        print(e)
    input("\n\tHit Enter\n\n\t")
