import shutil
from os.path import isfile, join
from os import listdir
import sys
print("\n  ( Install correct exiftool wrapper via:  pip install git+https://github.com/smarnach/pyexiftool )")
# https://github.com/smarnach/pyexiftool
import exiftool


print("\n Python executable used:  {}".format(sys.executable))
print(" Current python version:  {}\n".format(sys.version))
assert sys.version.startswith("3."), "Error: Python 3 is required!"

mypath = '..'
MY_CAMERA_MODELS = ["SM-G965F", "SM-S9080"]
OTHER_IMAGES_FOLDER = "_Other images"
OTHER_FILES_FOLDER = "_Other files"
NOT_MOVEABLE_FILE = 'desktop.ini'

counter = {
    "MY_IMAGES": 0,
    "OTHER_IMAGES": 0,
    "OTHER_FILES": 0,
}


def get_jpgs():
    my_jpgs = ["../" + f for f in listdir(mypath) if isfile(
        join(mypath, f)) and f.endswith(".jpg")]
    print(("jpgs: " + str(len(my_jpgs))))
    return my_jpgs


def get_other_files():
    other_files = ["../" + f for f in listdir(mypath) if isfile(
        join(mypath, f)) and not f.endswith(".jpg") and not f.endswith(".mp4")]
    print(("other files: " + str(len(other_files))))
    return other_files


def process_jpgs(files):
    with exiftool.ExifTool() as et:
        metadata = et.get_metadata_batch(files)
    for d in metadata:
        if "EXIF:Model" in list(d.keys()) and d["EXIF:Model"] in MY_CAMERA_MODELS:
            # msg = "============== own image =============="
            counter["MY_IMAGES"] += 1
        else:
            msg = ":::::::::::: moving 'other' image: {} :::::::::::::::::".format(
                d["SourceFile"])
            shutil.move(d["SourceFile"], d["SourceFile"]
                        [:3] + '/' + OTHER_IMAGES_FOLDER + '/' + d["SourceFile"][3:])
            counter["OTHER_IMAGES"] += 1
            print(("{} {}".format(msg, d["SourceFile"])))
        # print(("{:40.40} {:40.40}".format(msg, d["SourceFile"])))


def process_other_files(files):
    for f in files:
        if NOT_MOVEABLE_FILE in f:
            continue
        msg = "[[[[[[[[[[[::::::::::::]]]]]]]]]]] Moving 'other' file: {}  [[[[[[[[[[[::::::::::::]]]]]]]]]]]"
        try:
            shutil.move(f, f[:3] + '/' + OTHER_FILES_FOLDER + '/' + f[3:])
            print((msg.format(f)))
            counter["OTHER_FILES"] += 1
        except Exception as e:
            print(("Could not move file: {}".format(f)))
            print("Error:")
            print("============")
            print(e)
            print("============")
        # print("{:50.50} {:40.40}".format(msg, f))


def display_stats(jpg_files, other_files):
    print(("\n\tThere were {} JPG files and {} 'other' files.".format(
        len(jpg_files), len(other_files))))

    print("\n\t   MY_IMAGES:  {}".format(counter["MY_IMAGES"]))
    print("\tOTHER_IMAGES:  {}".format(counter["OTHER_IMAGES"]))
    print("\t OTHER_FILES:  {}".format(counter["OTHER_FILES"]))


def move_other_images():
    jpg_files = get_jpgs()
    process_jpgs(jpg_files)
    other_files = get_other_files()
    process_other_files(other_files)
    display_stats(jpg_files, other_files)


if __name__ == "__main__":
    try:
        move_other_images()
    except Exception as e:
        print("\n\tError occurred:")
        print(e)
    input("\n\tHit Enter\n\n\t")
