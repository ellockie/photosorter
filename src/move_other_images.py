import ntpath
import shutil
from os.path import isfile, join, normpath
from os import listdir
import sys

print("\n  ( Install correct exiftool wrapper via:  pip install git+https://github.com/smarnach/pyexiftool )")
# https://github.com/smarnach/pyexiftool
import exiftool

from constants.constants import CAMERA_UPLOADS_PATH, SUBROUTINE_LOG_INDENTATION

print("\n Python executable used:  {}".format(sys.executable))
print(" Current python version:  {}\n".format(sys.version))
assert sys.version.startswith("3."), "Error: Python 3 is required!"

MY_CAMERA_MODELS = ["SM-G965F", "SM-S9080"]
OTHER_IMAGES_FOLDER = "_Other images"
OTHER_FILES_FOLDER = "_Other files"
NOT_MOVEABLE_FILE = 'desktop.ini'

counter = {
    "PHOTOS": 0,
    "OTHER_IMAGES": 0,
    "OTHER_FILES": 0,
}


def get_jpgs(src_path):
    my_jpgs = [join(src_path, f) for f in listdir(src_path) if isfile(
        join(src_path, f)) and f.endswith(".jpg")]
    return my_jpgs


def get_other_files(src_path):
    other_files = [join(src_path, f) for f in listdir(src_path) if isfile(
        join(src_path, f)) and not f.endswith(".jpg") and not f.endswith(".mp4") and not f.endswith("desktop.ini")]
    return other_files


def get_filename_from_path(path):
    return ntpath.basename(path)


def process_jpgs(files, src_path):
    if len(files) == 0:
        return
    with exiftool.ExifTool() as et:
        metadata = et.get_metadata_batch(files)
    for d in metadata:
        if "EXIF:Model" in list(d.keys()) and d["EXIF:Model"] in MY_CAMERA_MODELS:
            counter["PHOTOS"] += 1
        else:
            msg = f"{SUBROUTINE_LOG_INDENTATION}Moved 'other' image:   {ntpath.basename(d['SourceFile'])}"
            dest = join(src_path, OTHER_IMAGES_FOLDER, get_filename_from_path(d["SourceFile"]))
            shutil.move(d["SourceFile"], dest)
            print(msg)
            counter["OTHER_IMAGES"] += 1


def process_other_files(files, src_path):
    for src_file_path in files:
        if NOT_MOVEABLE_FILE in src_file_path:
            continue
        try:
            dest = join(src_path, OTHER_FILES_FOLDER, get_filename_from_path(src_file_path))
            shutil.move(src_file_path, dest)
            print(f"{SUBROUTINE_LOG_INDENTATION}Moved 'other' file:    {ntpath.basename(dest)}")
            counter["OTHER_FILES"] += 1
        except Exception as e:
            print(("Could not move file: {}".format(src_file_path)))
            print(f"Error:\n============\n  {e}\n============")


def display_stats():
    print(f"{SUBROUTINE_LOG_INDENTATION}Files found in the uploads folder:")
    print(f"{SUBROUTINE_LOG_INDENTATION}                           Photos:  {counter['PHOTOS']}")
    print(f"{SUBROUTINE_LOG_INDENTATION}                     Other images:  {counter['OTHER_IMAGES']}")
    print(f"{SUBROUTINE_LOG_INDENTATION}                      Other files:  {counter['OTHER_FILES']}")


def move_other_images():
    src_path = CAMERA_UPLOADS_PATH
    src_path = normpath(src_path)
    jpg_files = get_jpgs(src_path)
    process_jpgs(jpg_files, src_path)
    other_files = get_other_files(src_path)
    process_other_files(other_files, src_path)
    display_stats()


if __name__ == "__main__":
    try:
        move_other_images()
    except Exception as e:
        print("\n\tError occurred:")
        print(e)
    input("\n\tHit Enter\n\n\t")
