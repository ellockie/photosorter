import datetime
import fnmatch
import ntpath
import os
import subprocess
import sys
import time
import winsound
import dateutil.parser

from common.globals import COUNTERS, FULL_PATH_SUBFOLDER, created_folders, file_info_array
from constants.constants import \
    COMMAND_LINE_OPTION_GENERATE_EXIFS, \
    DAY_DIVISION_TIME, \
    duplicate_str, \
    EXIF_EXTENSION, \
    EXTENSION_RAW_ARW, \
    EXTENSION_RAW_CRW, \
    EXTENSION_RAW_DNG, \
    EXTENSION_RAW_MPO, \
    EXTENSION_RAW_RW2, \
    EXTENSIONS_RAW_IMAGES, \
    EXTENSIONS_SPECIAL_RAW_IMAGES, \
    EXTENSIONS_SUPPORTED_IMAGES, \
    EXTENSIONS_SUPPORTED_NON_IMAGES, \
    FOLDER_ARW_CONV, \
    FOLDER_CRW_CONV, \
    FOLDER_DNG_CONV, \
    FOLDER_MPO_CONV, \
    FOLDER_ORIG_JPG, \
    FOLDER_PROBLEMATIC, \
    FOLDER_READY, \
    FOLDER_RW2_CONV, \
    FOLDER_UNSORTED, \
    INDENT_2_TABS, \
    INDENT_SMALL, \
    INDENT_VERY_SMALL, \
    KNOWN_CAMERAS_SYMBOLS, \
    NEWLINE_AND_INDENT_1_TAB, \
    NEWLINE_AND_INDENT_2_TABS, \
    PATH_TO_IRFANVIEW, \
    PATHS, \
    RAW_EXTENSIONS__FOLDERS_MAP, \
    RAW_MARKER_STR, \
    READY_FOLDER_DECORATION_STRING, \
    SUBFOLDER_DUPLICATE_FILE_NAMES, \
    SUBFOLDER_EMPTY_FILES, \
    SUBFOLDER_NOT_ENOUGH_INFO, \
    SUBFOLDER_UNSUPPORTED_EXT, \
    SUBROUTINE_LOG_INDENTATION, \
    TWO_NEWLINES
from utils.colorise import Colorise
from utils.decorators import display_timing, print_current_task_name


# --------------   FUNCTIONS   -----------------


# def yield_any_files_from_location(root):
#     files = [f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))]
#     for filename in files:
#         yield (os.path.join(root, filename), filename)


def convert_CRW(file_name):
    """Will convert. file_name could a pattern too, like "*.CRW"."""

    irfanview_output = subprocess.check_call([
        PATH_TO_IRFANVIEW,
        os.path.abspath(full_path_of(FOLDER_CRW_CONV, file_name)),
        "/jpgq=96",
        "/convert=$D$N.jpg"
    ]
    )
    # subprocess.call(path)
    if irfanview_output:
        print((len(irfanview_output), irfanview_output))
    # print("\nconversion SUCCESS\n")


def yield_pattern_matching_files_from_location(root, pattern):
    """Locate all files matching supplied filename pattern in and below supplied root directory."""

    files = [f for f in os.listdir(
        root) if os.path.isfile(os.path.join(root, f))]
    for filename in fnmatch.filter(files, pattern) if pattern else files:
        # if include_paths:
        yield (os.path.join(root, filename), filename)


def yield_exif_files_from_location(root):
    # TODO: use yield_pattern_matching_files_from_location() instead
    for exif_file in os.listdir(root):
        if os.path.isfile(os.path.join(root, exif_file)) and get_lowercase_extension(exif_file) == EXIF_EXTENSION:
            yield exif_file


def get_lowercase_extension(filename):
    return os.path.splitext(filename)[1].lower()


def yield_image_files_from_location(root, include_paths):
    for image_file in os.listdir(root):
        if os.path.isfile(os.path.join(root, image_file)):
            filename, file_extension = os.path.splitext(image_file)
            filename = filename.lower()
            file_extension = file_extension.lower()
            if file_extension in EXTENSIONS_SUPPORTED_IMAGES:  # TODO: add support for videos, yield them too
                if include_paths:
                    # yield full pathname
                    yield os.path.join(root, image_file)
                else:
                    # yield just a filename with extension
                    yield image_file
            elif file_extension in EXTENSIONS_SUPPORTED_NON_IMAGES:
                pass
            else:
                print((INDENT_VERY_SMALL + "[ WARNING ] File_extension: " +
                       file_extension + " not supported ( '" + image_file + "' ). File moved."))
                try:
                    os.rename(
                        full_path_of(FOLDER_UNSORTED, image_file),
                        full_path_of(FOLDER_PROBLEMATIC,
                                     SUBFOLDER_UNSUPPORTED_EXT, filename + file_extension)
                    )
                    COUNTERS["PROBLEMATIC_FILES"] += 1
                except:
                    print(
                        INDENT_VERY_SMALL + "  Problem when moving not supported extension files (duplicate already exists?)\n")
                    # raise ValueError("  file_extension: " + file_extension + " not supported ( '" + image_file + "'' )")


def get_filename_from_path(path):
    return ntpath.basename(path)


def convert_to_date_time(unformatted_image_datetime, time_too):
    str_Y = unformatted_image_datetime[0:4]
    str_M = unformatted_image_datetime[5:7]
    str_D = unformatted_image_datetime[8:10]

    if not time_too:
        return datetime.datetime(int(str_Y), int(str_M), int(str_D))
    str_H = unformatted_image_datetime[11:13]
    str_m = unformatted_image_datetime[14:16]
    str_S = unformatted_image_datetime[17:19]
    return datetime.datetime(int(str_Y), int(str_M), int(str_D), int(str_H), int(str_m), int(str_S))
    # return datetime.datetime(year, month, day[, hour[, minute[, second[, microsecond[, tzinfo]]]]])


def reformat_timestring(timestring):
    timestring = timestring.replace(":", ".")
    timestring = timestring[0:4] + "-" + timestring[5:7] + "-" + timestring[8:]
    weekday = dateutil.parser.parse(timestring[:10]).strftime("%a")
    timestring = timestring.replace(" ", "_(" + weekday + ")_")

    # previous scheme example:
    # 2015-11-23_(Mon)_09.26.27__RAW__f4.0...T1_20..50mm1250.JPG
    # vs:
    # 2015-04-13_(Mon)_20.35.44__f2.7__T0.5__RAW__L98.5.eq__I50__G6__DUPL_(3).CRW

    # a = "2012-10-09"  # T19:00:55Z"
    # print(dateutil.parser.parse(a), dateutil.parser.parse(a).weekday())
    # a = "2012-10-09 T19:00:55Z"
    # print(dateutil.parser.parse(a), dateutil.parser.parse(a).strftime("%a"))

    timestring = timestring.split("+")[0]
    return timestring


def apply_timezone_correction(image_date, camera_symbol):
    return image_date


def reformat_exposure_time(exposure_time_string):
    return exposure_time_string.replace("/", "_")  # + "s"


def reformat_focal_length(focal_length_string):
    if "equivalent" in focal_length_string:
        focal_length_entry = focal_length_string.split("equivalent: ")
        focal_length_string = focal_length_entry[len(focal_length_entry) - 1]
        focal_length_string = focal_length_string.replace(")", ".eq")

        # actual_f_length_string = focal_length_entry[0].split(" mm (35 mm")[0]
        # print(actual_f_length_string)

    focal_length_string = focal_length_string.replace(" ", "")
    return focal_length_string.replace("mm", "")


def extract_data_from_exif_file_and_rename_original_image(exif_file_handler, image_name):
    camera_symbol = ""
    img = {}
    unformatted_image_datetime = ""
    previous_critical_fail_counter = COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"]

    img["orig_full_file_name"] = image_name
    img_name, img_ext = os.path.splitext(image_name)
    # name example:  name_template = "2014-05-26_(Mon)_13.24.40__f2.2...T1_33..4.2mm125.jpg"

    # try:
    camera_symbol, unformatted_image_datetime = extract_basic_info_from_EXIF(
        camera_symbol, exif_file_handler, img, unformatted_image_datetime)
    # except:
    #     print("ERROR extracting camera_symbol and unformatted_image_datetime. filename:")
    #     print(image_name)
    #     exit(1)
    # assert isinstance(COUNTERS["FAILS"], int)
    missing_parts = identify_missing_image_info(img)

    # move file if problematic (new errors)
    if COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"] > previous_critical_fail_counter:
        if img_ext == '.MPO':
            pass
        if img_ext == '.JPG' and camera_symbol == "N3DS":
            pass
        else:
            move_image_to_problematic_folder(image_name, img_ext, img_name, missing_parts)
            return False

    # process image date_time, apply timezone correction if necessary
    # image_date_time = convert_to_date_time(unformatted_image_datetime, True)
    image_datetime = apply_timezone_correction(
        unformatted_image_datetime, camera_symbol)
    img["image_datetime"] = reformat_timestring(image_datetime)
    img["orig_file_name"] = img_name
    img["orig_file_ext"] = img_ext
    file_info_array.append(img)

    return True


def move_image_to_problematic_folder(image_name, img_ext, img_name, missing_parts):
    print((Colorise.red(INDENT_SMALL + "*** PROBLEMATIC:  ") + Colorise.yellow(
        img_name) + img_ext + ",  missing: " + Colorise.yellow(", ".join(missing_parts)) +
           ".  (Need to mark the original photo too!)"))
    if img_ext.lower() in EXTENSIONS_SPECIAL_RAW_IMAGES:
        # 'special' raw, BUT also .MPO! need to handle that case
        target_folder = get_target_folder_for_extension(image_name, img_ext)
        os.rename(
            full_path_of(FOLDER_UNSORTED, image_name),
            full_path_of(target_folder, img_name + img_ext)
        )
    else:
        os.rename(
            full_path_of(FOLDER_UNSORTED, image_name),
            os.path.join(FULL_PATH_SUBFOLDER["NOT_ENOUGH_INFO"],
                         img_name + img_ext)
        )
        COUNTERS["PROBLEMATIC_FILES"] += 1


def get_target_folder_for_extension(image_name, img_ext):
    target_folder = ""
    print(image_name)
    if img_ext.lower() == EXTENSION_RAW_CRW:
        target_folder = FOLDER_CRW_CONV
    elif img_ext.lower() == EXTENSION_RAW_MPO:
        target_folder = FOLDER_MPO_CONV
    elif img_ext.lower() == EXTENSION_RAW_RW2:
        target_folder = FOLDER_RW2_CONV
    # TODO: the following don't exist in EXTENSIONS_SPECIAL_RAW_IMAGES!!!
    elif img_ext.lower() == EXTENSION_RAW_ARW:
        target_folder = FOLDER_ARW_CONV
    elif img_ext.lower() == EXTENSION_RAW_DNG:
        target_folder = FOLDER_DNG_CONV
    else:
        print(("Unrecognised extension:", img_ext))
    return target_folder


def identify_missing_image_info(img):
    """Some rescue operations"""
    missing_parts = []
    if "exposure_time" not in list(img.keys()):
        missing_parts.append("exposure_time")
        img["exposure_time"] = "T---"
        COUNTERS["FAILS"] += 1
    if "iso" not in list(img.keys()):
        missing_parts.append("iso")
        img["iso"] = "I---s"
        COUNTERS["FAILS"] += 1
    if "aperture" not in list(img.keys()):
        missing_parts.append("aperture")
        COUNTERS["FAILS"] += 1
        COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"] += 1
    if "camera_symbol" not in list(img.keys()):
        missing_parts.append("camera_symbol")
        COUNTERS["FAILS"] += 1
        COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"] += 1
    if "focal_length" not in list(img.keys()):
        missing_parts.append("focal_length")
        COUNTERS["FAILS"] += 1
        COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"] += 1

    # fill missing info
    if len(missing_parts) == 1 and missing_parts[0] == 'aperture':
        img['aperture'] = 'fNA'
        missing_parts.clear()
        COUNTERS["FAILS"] -= 1
        COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"] -= 1
    if "focal_length" in list(img.keys()) and img["focal_length"] == "L0.0":
        img["focal_length"] = "LNA"

    return missing_parts


def extract_basic_info_from_EXIF(camera_symbol, exif_file, img, unformatted_image_datetime):
    for line in exif_file:
        if line.startswith('Camera Model Name'):
            camera_name = extract_value_of_EXIF_key(line)
            camera_symbol = get_camera_symbol(camera_name, exif_file)
            img["camera_symbol"] = camera_symbol
        elif line.startswith('File Modification Date/Time'):
            unformatted_image_datetime = extract_value_of_EXIF_key(line)
        elif line.startswith('Date/Time Original'):
            unformatted_image_datetime = extract_value_of_EXIF_key(line)
        elif line.startswith('Aperture'):
            aperture = "f" + extract_value_of_EXIF_key(line)
            img["aperture"] = aperture
        elif line.startswith('Exposure Time'):
            exposure_time = "T" + \
                            reformat_exposure_time(extract_value_of_EXIF_key(line))
            img["exposure_time"] = exposure_time
        elif line.startswith('ISO  '):
            iso = "I" + extract_value_of_EXIF_key(line)
            img["iso"] = iso
        elif line.startswith('Focal Length'):
            focal_length = "L" + \
                           reformat_focal_length(extract_value_of_EXIF_key(line))
            img["focal_length"] = focal_length
            if "camera_symbol" in list(img.keys()):
                if img["camera_symbol"] == "NE71":
                    print((INDENT_SMALL + "NE71 - " +
                           str(float(float(reformat_focal_length(extract_value_of_EXIF_key(line)))))))
                elif img["camera_symbol"] == "SH50":
                    print((INDENT_SMALL + "SH50 - " +
                           str(float(reformat_focal_length(extract_value_of_EXIF_key(line))))))
            else:
                print((INDENT_SMALL + "NO CAMERA MODEL"))
        elif line.startswith("Focal Units"):
            print((Colorise.red(INDENT_SMALL + "TODO: try to use Focal Units information: ") +
                   extract_value_of_EXIF_key(line)))
    return camera_symbol, unformatted_image_datetime


def full_path_of(folder_name, trailing_part_1="", trailing_part_2=""):
    """
    :param folder_name:
    :param trailing_part_1:
    :param trailing_part_2:
    :return: merged path, with backslash removed
    """
    return os.path.join(PATHS["ROOT_FOLDER"], folder_name, trailing_part_1, trailing_part_2).rstrip('\\')


def rename_exif_file(exif_file_name, image_file_name):
    try:
        os.rename(exif_file_name, full_path_of(
            FOLDER_UNSORTED, image_file_name + EXIF_EXTENSION))
    except:
        print("exif moving ERROR")


def extract_value_of_EXIF_key(exif_entry):
    return exif_entry.split(": ", 1)[1].strip()


def fake_dict_keys_value(fake_dict, fake_key):
    for entry in fake_dict:
        if entry[0] == fake_key:
            return entry[1]
    return None


def get_camera_symbol(camera_name, exif_file):
    cam_symb = fake_dict_keys_value(KNOWN_CAMERAS_SYMBOLS, camera_name)

    if cam_symb is None:
        print((Colorise.red(INDENT_SMALL + "UNKNOWN camera encountered: ") +
               Colorise.yellow(camera_name)))
        print((INDENT_SMALL + " - EXIF file:  " + exif_file.name))
        winsound.Beep(4444, 4444)
        winsound.Beep(8444, 2222)
        new_camera_symbol = ""
        while not new_camera_symbol:
            new_camera_symbol = input(
                INDENT_SMALL + "Enter camera symbol: ")
            # raise ValueError('UNKNOWN camera encountered (' + camera_name + ')')
        print((Colorise.green(INDENT_SMALL + "Adding " + camera_name + " - " +
                              new_camera_symbol + " to the known list. Please hard-code it later!")))
        KNOWN_CAMERAS_SYMBOLS.append((camera_name, new_camera_symbol))
        write_camera_symbol_to_file(camera_name, new_camera_symbol)
        return new_camera_symbol
    else:
        return cam_symb


def write_camera_symbol_to_file(camera, new_camera_symbol):
    with open("photo_camera_symbols.txt", "a") as cameras_file:
        cameras_file.write(
            '    ("' + camera + '", "' + new_camera_symbol + '"),\n')


def iterator_str(iterator):
    if iterator == 0:
        return ""
    else:
        return "_(" + str(iterator + 1) + ")"


def get_the_destination_path(file_name, file_ext, source_img_path, iterator=0):
    # TODO: handle RAW paths one-by-one!
    if is_raw_file(file_ext):
        path_to_destination_photos = RAW_EXTENSIONS__FOLDERS_MAP[file_ext.lower(
        )]
        # if file_ext.lower() in EXTENSIONS_SPECIAL_RAW_IMAGES:
        #     path_to_destination_photos = full_path_of(FOLDER_CRW_CONV)
        # if file_ext.lower() == ".arw":
        #     path_to_destination_photos = full_path_of(FOLDER_ARW_CONV)
        # else:
        #     path_to_destination_photos = full_path_of(FOLDER_CRW_CONV)
        #     COUNTERS["ORIG_RAWS"] += 1
    else:
        path_to_destination_photos = full_path_of(FOLDER_ORIG_JPG)

    destination_img_path = os.path.join(
        path_to_destination_photos, file_name + iterator_str(iterator) + file_ext)
    destination_exif_path = os.path.join(
        path_to_destination_photos, file_name + iterator_str(iterator) + EXIF_EXTENSION)

    # or os.path.exists(destination_exif_path):
    if os.path.exists(destination_img_path):
        # TODO:
        if os.path.exists(destination_img_path) and os.path.getsize(destination_img_path) == \
                os.path.getsize(source_img_path):
            # when exifs existed on both sides, was giving this message
            # print(">>> the same size")
            COUNTERS["DUPLICATES"] += 1
            if duplicate_str not in file_name:
                file_name = file_name + duplicate_str
                return get_the_destination_path(file_name, file_ext, source_img_path, 0)
            else:
                return get_the_destination_path(file_name, file_ext, source_img_path, (iterator + 1))

        destination_img_duplicate_path = os.path.join(
            path_to_destination_photos, file_name + iterator_str(iterator) + file_ext)

        if os.path.exists(destination_img_duplicate_path):
            print((INDENT_SMALL + "Renaming an inter-second name:  " +
                   destination_img_duplicate_path))

        return get_the_destination_path(file_name, file_ext, source_img_path, (iterator + 1))
    else:
        return destination_img_path, destination_exif_path


def get_one_day_before_folder_name(folder_name):
    date_time = convert_to_date_time(folder_name, False)

    d = date_time - datetime.timedelta(days=1)
    print((INDENT_SMALL + "Shifting date: " +
           folder_name + "  -->  " + str(d)[:-9]))

    weekday = d.strftime("%a")
    d = str(d)

    return d[0:4] + "-" + d[5:7] + "-" + d[8:10] + "_(" + weekday


def create_date_folder(photo_name):
    """Create folder name like 2014-05-08_(Thu) - 1. ######."""

    assert ")_" in photo_name, f"Error: Wrong name:  '{photo_name}'"

    split_name = photo_name.split(")_")
    folder_name = split_name[0]
    try:
        photo_time = split_name[1].split("__f")[0]
    except:
        print((INDENT_SMALL + "Problem when splitting image name"))
        print(split_name)
        raise ValueError(split_name)

    if int(photo_time[:2]) <= int(DAY_DIVISION_TIME[:2]):
        if int(photo_time[:2]) == int(DAY_DIVISION_TIME[:2]):
            if int(photo_time[3:5]) <= int(DAY_DIVISION_TIME[3:5]):
                if int(photo_time[3:5]) == int(DAY_DIVISION_TIME[3:5]):
                    if int(photo_time[6:8]) < int(DAY_DIVISION_TIME[6:8]):
                        folder_name = get_one_day_before_folder_name(
                            folder_name[:-5])
                else:
                    folder_name = get_one_day_before_folder_name(
                        folder_name[:-5])
        else:
            folder_name = get_one_day_before_folder_name(folder_name[:-5])
    folder_name = folder_name + READY_FOLDER_DECORATION_STRING
    folder_destination = full_path_of(FOLDER_READY, folder_name)
    # check_if folder has been created
    if folder_name not in created_folders:
        if not os.path.exists(folder_destination):
            os.makedirs(folder_destination)
        created_folders.append(folder_name)
    return folder_destination


def file_sizes_the_same(file_1, file_2):
    if os.path.getsize(file_1) == os.path.getsize(file_2):
        return True
    else:
        print((INDENT_SMALL + "Sizes, file 1: ",
               file_1, os.path.getsize(file_1)))
        print((INDENT_SMALL + "Sizes, file 2: ",
               file_2, os.path.getsize(file_2)))
        return False


@display_timing
def create_folders_subfolder(folder, subfolder):
    target_folder = full_path_of(full_path_of(folder), subfolder)
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
    return target_folder


@print_current_task_name
@display_timing
def create_missing_folders(all_folders, missing_folders):
    if len(missing_folders) == len(all_folders):
        print((NEWLINE_AND_INDENT_1_TAB +
               "[ WARNING ] None of the required folders is present.\n"))
        print((INDENT_SMALL + "The root folder path is:       " + PATHS["ROOT_FOLDER"]))
        print((INDENT_SMALL + "Current working directory is:  " + os.getcwd()))
        # currently disabled:
        # ask_different_root_folder()
    for folder_name in missing_folders:
        os.makedirs(full_path_of(folder_name))
        print((INDENT_SMALL + "Folder '" + folder_name + "' created."))
    print(TWO_NEWLINES)


@print_current_task_name
@display_timing
def ask_different_root_folder():
    answer = input(
        "\n    Use the current working directory? (Enter=yes): ")
    if answer == "":
        PATHS["ROOT_FOLDER"] = os.path.join(os.getcwd(), "__PROC_PHOTOS")
        print((NEWLINE_AND_INDENT_1_TAB +
               "Will use the following path: " + PATHS["ROOT_FOLDER"] + "\n"))
    else:
        answer = input(
            "\n  Continue with original root folder path? (Enter=yes): ")
        if answer != "":
            print((NEWLINE_AND_INDENT_1_TAB + "Quitting\n"))
            quit()


@display_timing
def create_problematic_folders():
    FULL_PATH_SUBFOLDER["UNSUPPORTED_EXT"] = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_UNSUPPORTED_EXT)
    FULL_PATH_SUBFOLDER["EMPTY_FILES"] = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_EMPTY_FILES)
    FULL_PATH_SUBFOLDER["NOT_ENOUGH_INFO"] = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_NOT_ENOUGH_INFO)
    FULL_PATH_SUBFOLDER["DUPLICATE_FILE_NAMES"] = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_DUPLICATE_FILE_NAMES)


def is_raw_file(extension):
    return extension.lower() in EXTENSIONS_RAW_IMAGES


def format_extension(extension):
    is_raw = is_raw_file(extension)
    return extension.upper() if is_raw else extension.lower()


def get_raw_marker(extension):
    is_raw = is_raw_file(extension)
    return RAW_MARKER_STR if is_raw else ""


def get_file_name(img_data, raw_marker):
    file_name = \
        img_data['image_datetime'] + "__" + \
        raw_marker + \
        img_data.get('aperture', 'fNA') + "__" + \
        img_data['exposure_time'] + "__" + \
        img_data.get('focal_length', 'LNA') + "__" + \
        img_data.get('iso', 'INA') + "__" + \
        img_data['camera_symbol']
    return file_name


def move_lossy_image_files(image_file_name):
    assert ")_" in image_file_name[1], "Error: Wrong name:\n" + image_file_name
    try:
        os.rename(
            image_file_name[0],
            os.path.join(create_date_folder(
                image_file_name[1]), image_file_name[1])
        )
    except:
        move_duplicate_file(image_file_name, "LOSSY IMAGE")


def move_file_to_destination(created_folders, image_file_name, file_type_name, subfolder_name):
    destination_subfolder = os.path.join(
        create_date_folder(image_file_name[1]), subfolder_name)
    # check_if folder has been created
    if destination_subfolder not in created_folders:
        if not os.path.exists(destination_subfolder):
            os.makedirs(destination_subfolder)
    try:
        os.rename(
            image_file_name[0],
            os.path.join(destination_subfolder, image_file_name[1])
        )
    except:
        move_duplicate_file(image_file_name, file_type_name)


def move_duplicate_file(image_file_name, file_type):
    print(
        f"{SUBROUTINE_LOG_INDENTATION}Problem when sorting/moving PRE-EXISTING {file_type} file (will move): {image_file_name[1]}")
    try:
        os.rename(
            image_file_name[0],
            os.path.join(os.path.join(
                FULL_PATH_SUBFOLDER["DUPLICATE_FILE_NAMES"], image_file_name[1]))
        )
        COUNTERS["PROBLEMATIC_FILES"] += 1
    except:
        print((Colorise.red(INDENT_2_TABS + "ERROR! File: ") + image_file_name[0] + Colorise.red(
            " already exists in PROBLEMATIC/DUPLICATE folder: " + FULL_PATH_SUBFOLDER["DUPLICATE_FILE_NAMES"])))


def redate_problematic_folder(should_delete=True):
    """To mark the PROBLEMATIC folder as edited"""
    temporary_file_path = full_path_of(FOLDER_PROBLEMATIC, ".marker.temp")
    temporary_file = open(temporary_file_path, "w")
    temporary_file.write("problematic files: " +
                         str(COUNTERS["PROBLEMATIC_FILES"]))
    temporary_file.close()
    if os.path.exists(temporary_file_path) and should_delete:
        os.remove(temporary_file_path)


def show_issues_info():
    if COUNTERS["FAILS"] > 0:
        print(f"{SUBROUTINE_LOG_INDENTATION}{str(COUNTERS['FAILS'])} problems with some files")
    if COUNTERS["INFO_EXTRACTION_CRITICAL_FAILS"] > 0:
        print(f"{SUBROUTINE_LOG_INDENTATION}{str(COUNTERS['INFO_EXTRACTION_CRITICAL_FAILS'])} CRITICAL problems with some files")
        print(f"{SUBROUTINE_LOG_INDENTATION}Files moved to 'PROBLEMATIC' folder")
    if COUNTERS["DUPLICATES"] > 0:
        print(f"{NEWLINE_AND_INDENT_1_TAB}Found {str(COUNTERS['DUPLICATES'])} same-size files!")


def display_extra_messages():
    print(Colorise.red(f"{SUBROUTINE_LOG_INDENTATION}CRW not extracted"))
    print(Colorise.red(f"{SUBROUTINE_LOG_INDENTATION}MPO not extracted"))
    print(Colorise.red(f"{SUBROUTINE_LOG_INDENTATION}RW2 not extracted"))


def display_task_stats():
    print(f"\n{SUBROUTINE_LOG_INDENTATION}{str(COUNTERS['TASKS'])} tasks performed")


def get_all_files_count():
    DIR = full_path_of(FOLDER_UNSORTED)
    return len([name for name in os.listdir(DIR) if os.path.isfile(os.path.join(DIR, name))])


def display_total_time(processing_start_time, all_files_count):
    processing_duration = time.time() - processing_start_time
    m, s = divmod(processing_duration, 60)
    h, m = divmod(m, 60)
    print(Colorise.yellow(SUBROUTINE_LOG_INDENTATION +
                          "Total processing time: ") + "%d:%02d:%02d" % (h, m, s))
    if all_files_count:
        print((Colorise.yellow(SUBROUTINE_LOG_INDENTATION + "Time per photo: ") +
               str(round(processing_duration / all_files_count, 2)) + " s"))
    print(Colorise.yellow(SUBROUTINE_LOG_INDENTATION +
                          "All files (photos + other): ") + str(all_files_count))


def tada():
    winsound.Beep(888, 222)
    winsound.Beep(2222, 888)


def ask_if_generate_exifs():
    if len(sys.argv) == 2:
        option = sys.argv[1]
        print((" Command line option: " + option + "\n"))
        if option == COMMAND_LINE_OPTION_GENERATE_EXIFS:
            return True
    while True:
        winsound.Beep(4444, 444)
        answer = input(NEWLINE_AND_INDENT_1_TAB +
                       "Do you want to generate EXIF files? (y/n): ")
        if answer == "y":
            print("")
            return True
        elif answer == "n":
            print("")
            return False


def print_header_footer():
    str = "#" * 130
    print(Colorise.green(str))
