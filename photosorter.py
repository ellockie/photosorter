import datetime
import os
import sys
import time
import winsound

import fnmatch
import inspect
import ntpath
import subprocess
import dateutil.parser  # import parse as dateutil_parser

# local imports
from colorise import Colorise
from photosorter_cfg import *
from folder_sorter import folder_sorter


print("\n Python executable used:  {}".format(sys.executable))
print(" Current python version:  {}\n".format(sys.version))
assert sys.version.startswith("3."), "Error: Python 3 is required!"

#  Command line option(s):
#  - generate-exifs:   generate exif files (without asking)


# TODO: move these to config file
pattern_name = "*.*"
crw_pattern = "*.CRW"
duplicate_str = "__DUPL"

fail_counter = 0
info_extraction_critical_fail_counter = 0
duplicate_counter = 0
orig_raw_counter = 0
moved_old_exif_counter = 0
problematic_files_counter = 0
task_counter = 0

file_info_array = []
created_folders = []

UNSUP_EXT_subfolder_full_path = None
EMPTY_FILES_subfolder_full_path = None
NOT_ENOUGH_INFO_subfolder_full_path = None
DUPLICATE_FILE_NAMES_subfolder_full_path = None
COMMAND_LINE_OPTION_GENERATE_EXIFS = "generate-exifs"


# --------------   FUNCTIONS   -----------------

def print_current_task_name_decorator(fn):
    def wrapper(*args, **kwargs):
        global task_counter
        task_counter += 1
        print_function_name(inspect.stack()[1][4][0], task_counter)
        result = fn(*args, **kwargs)
        return result

    return wrapper


def print_function_name(raw_stack_name, task_counter):
    fn_name = raw_stack_name.replace('_TASK_', '').strip()
    fn_name = fn_name.split(" = ")[1] if " = " in fn_name else fn_name
    fn_name = fn_name.replace('_', ' ')
    fn_name = fn_name.replace('()', ' ')
    fn_name = " TASK " + str(task_counter) + ":\t" + fn_name
    print((Colorise.green(fn_name)))


def display_timing(fn):
    """Outputs the time a function takes to execute."""

    def wrapper(*args, **kwargs):
        t = time.time()
        result = fn(*args, **kwargs)
        t_diff = time.time() - t
        if t_diff >= 0.01:
            print((Colorise.yellow(INDENT_2_TABS + "Execution time: ") +
                   str(round(t_diff, 2)) + Colorise.yellow(" s")))
        return result

    return wrapper


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


# def yield_any_files_from_location(root):
#     files = [f for f in os.listdir(root) if os.path.isfile(os.path.join(root, f))]
#     for filename in files:
#         yield (os.path.join(root, filename), filename)


def yield_exif_files_from_location(root):
    # TODO: use yield_pattern_matching_files_from_location() instead
    for exif_file in os.listdir(root):
        if os.path.isfile(os.path.join(root, exif_file)) and get_lowercase_extension(exif_file) == EXIF_EXTENSION:
            yield exif_file


def get_lowercase_extension(filename):
    return os.path.splitext(filename)[1].lower()


def yield_image_files_from_location(root, include_paths):
    global problematic_files_counter
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
                                     SUBFOLDER_UNSUP_EXT, filename + file_extension)
                    )
                    problematic_files_counter += 1
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


def extract_data_from_EXIF_file_and_rename_original_image(exif_file_handler, image_name):
    global file_info_array, fail_counter, info_extraction_critical_fail_counter

    camera_symbol = ""
    img = {}
    unformatted_image_datetime = ""
    previous_critical_fail_counter = info_extraction_critical_fail_counter

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
    # assert isinstance(fail_counter, int)
    missing_parts, fail_counter, info_extraction_critical_fail_counter = identify_missing_image_info(
        img, fail_counter, info_extraction_critical_fail_counter)

    # move file if problematic (new errors)
    if (info_extraction_critical_fail_counter > previous_critical_fail_counter):
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
    global problematic_files_counter
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
            os.path.join(NOT_ENOUGH_INFO_subfolder_full_path,
                         img_name + img_ext)
        )
        problematic_files_counter += 1


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


def identify_missing_image_info(img, fail_counter, info_extraction_critical_fail_counter):
    """Some rescue operations"""
    missing_parts = []
    if "exposure_time" not in list(img.keys()):
        missing_parts.append("exposure_time")
        img["exposure_time"] = "T---"
        fail_counter += 1
    if "iso" not in list(img.keys()):
        missing_parts.append("iso")
        img["iso"] = "I---s"
        fail_counter += 1
    if "aperture" not in list(img.keys()):
        missing_parts.append("aperture")
        fail_counter += 1
        info_extraction_critical_fail_counter += 1
    if "camera_symbol" not in list(img.keys()):
        missing_parts.append("camera_symbol")
        fail_counter += 1
        info_extraction_critical_fail_counter += 1
    if "focal_length" not in list(img.keys()):
        missing_parts.append("focal_length")
        fail_counter += 1
        info_extraction_critical_fail_counter += 1

    # fill missing info
    if len(missing_parts) == 1 and missing_parts[0] == 'aperture':
        img['aperture'] = 'fNA'
        missing_parts.clear()
        fail_counter -= 1
        info_extraction_critical_fail_counter -= 1
    if "focal_length" in list(img.keys()) and img["focal_length"] == "L0.0":
        img["focal_length"] = "LNA"

    return missing_parts, fail_counter, info_extraction_critical_fail_counter


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
    return os.path.join(ROOT_FOLDER_PATH, folder_name, trailing_part_1, trailing_part_2).rstrip('\\')


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
    global KNOWN_CAMERAS_SYMBOLS

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
    global duplicate_counter, orig_raw_counter

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
        #     orig_raw_counter += 1
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
            duplicate_counter += 1
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
    global created_folders

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


# -------  TASKS  --------------------------------------------------------------------------
# -------  TASKS  --------------------------------------------------------------------------
# -------  TASKS  --------------------------------------------------------------------------

# @print_current_task_name_decorator


@display_timing
def create_folders_subfolder(folder, subfolder):
    target_folder = full_path_of(full_path_of(folder), subfolder)
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
    return target_folder


@print_current_task_name_decorator
@display_timing
def create_missing_folders(all_folders, missing_folders):
    if len(missing_folders) == len(all_folders):
        print((NEWLINE_AND_INDENT_1_TAB +
               "[ WARNING ] None of the required folders is present.\n"))
        print((INDENT_SMALL + "The root folder path is:       " + ROOT_FOLDER_PATH))
        print((INDENT_SMALL + "Current working directory is:  " + os.getcwd()))
        # currently disabled:
        # ask_different_root_folder()
    for folder_name in missing_folders:
        os.makedirs(full_path_of(folder_name))
        print((INDENT_SMALL + "Folder '" + folder_name + "' created."))
    print(TWO_NEWLINES)


@print_current_task_name_decorator
@display_timing
def ask_different_root_folder():
    global ROOT_FOLDER_PATH
    answer = input(
        "\n    Use the current working directory? (Enter=yes): ")
    if answer == "":
        ROOT_FOLDER_PATH = os.path.join(os.getcwd(), "__PROC_PHOTOS")
        print((NEWLINE_AND_INDENT_1_TAB +
               "Will use the following path: " + ROOT_FOLDER_PATH + "\n"))
    else:
        answer = input(
            "\n  Continue with original root folder path? (Enter=yes): ")
        if answer != "":
            print((NEWLINE_AND_INDENT_1_TAB + "Quitting\n"))
            quit()


@print_current_task_name_decorator
@display_timing
def create_problematic_folders():
    global ROOT_FOLDER_PATH, UNSUP_EXT_subfolder_full_path, EMPTY_FILES_subfolder_full_path, \
        NOT_ENOUGH_INFO_subfolder_full_path, DUPLICATE_FILE_NAMES_subfolder_full_path

    UNSUP_EXT_subfolder_full_path = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_UNSUP_EXT)
    EMPTY_FILES_subfolder_full_path = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_EMPTY_FILES)
    NOT_ENOUGH_INFO_subfolder_full_path = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_NOT_ENOUGH_INFO)
    DUPLICATE_FILE_NAMES_subfolder_full_path = create_folders_subfolder(
        FOLDER_PROBLEMATIC, SUBFOLDER_DUPLICATE_FILE_NAMES)


@print_current_task_name_decorator
@display_timing
def _TASK_verify_if_folders_exist(all_folders):
    missing_folder_count = 0
    missing_folders = []
    for folder_name in all_folders:
        folder_full_path = full_path_of(folder_name)
        if not os.path.exists(folder_full_path):
            if missing_folder_count == 0:
                print(TWO_NEWLINES)
            print((INDENT_SMALL + "Folder missing: " + folder_name))
            missing_folder_count += 1
            missing_folders.append(folder_name)
    if missing_folder_count:
        create_missing_folders(all_folders, missing_folders)
    create_problematic_folders()


@print_current_task_name_decorator
@display_timing
def _TASK_move_old_exif_files():
    """ Generate EXIF files."""

    global moved_old_exif_counter

    for exif_file_name in yield_pattern_matching_files_from_location(full_path_of(FOLDER_UNSORTED), "*._exif"):
        moved_old_exif_counter += 1
        # print(exif_file_name, exif_file_name[0] + " " + exif_file_name[1])
        # moved_old_exif_src_file_name = full_path_of(FOLDER_UNSORTED, exif_file_name)
        moved_old_exif_dest_file_name = full_path_of(
            FOLDER_PROBLEMATIC_OLD_EXIF, exif_file_name[1])
        try:
            if os.path.exists(moved_old_exif_dest_file_name):
                if file_sizes_the_same(exif_file_name[0], moved_old_exif_dest_file_name):
                    os.remove(moved_old_exif_dest_file_name)
            os.rename(
                exif_file_name[0],
                moved_old_exif_dest_file_name
            )
        except:
            print((
                    INDENT_SMALL + "Problem when moving PRE-EXISTING EXIF files (2 files of the same sizes?)"))


@print_current_task_name_decorator
@display_timing
def _TASK_remove_empty_image_files():
    """Remove empty image files."""

    # This task needs to run before EXIF generation because probably empty files cause exiftool crash
    global file_info_array, problematic_files_counter

    for image_file_name_with_path in yield_image_files_from_location(full_path_of(FOLDER_UNSORTED), include_paths=True):
        # image_file_name_only, image_file_extension = os.path.splitext(image_file_name_with_path)
        image_file_name = os.path.basename(image_file_name_with_path)
        if os.path.getsize(image_file_name_with_path) == 0:
            print((INDENT_SMALL + "Empty file: " + image_file_name))
            moved_empty_file_name_destination = os.path.join(
                EMPTY_FILES_subfolder_full_path, image_file_name)
            try:
                os.rename(image_file_name_with_path,
                          moved_empty_file_name_destination)
                problematic_files_counter += 1
            except:
                print((INDENT_SMALL + "Problem when moving EMPTY image files"))
    # raw_input("Proceed? ")


@print_current_task_name_decorator
@display_timing
def _TASK_generate_exif_files():
    """ Generate EXIF files."""
    exiftool_output = "exiftool_output:NOT_POPULATED_YET"
    try:
        print((Colorise.yellow("   ======== EXIFTOOL: ======")))
        # http://stackoverflow.com/questions/36169571/python-subprocess-check-call-vs-check-output
        # subprocess.call(path)
        exiftool_output = subprocess.check_call(
            [
                # http://www.sno.phy.queensu.ca/~phil/exiftool/exiftool_pod.html
                EXIFTOOL_NAME,
                "-a",
                "-u",
                "-g1",
                # "-b",  # dump of the binary section
                "-w!",
                EXIF_EXTENSION,
                full_path_of(FOLDER_UNSORTED)
                # + "' > '" + PATH_TO_REPORT + "'"
            ]
        )
        if exiftool_output:
            print((len(exiftool_output), exiftool_output))
        else:
            print((INDENT_SMALL + "( no exiftool report )"))
        print((Colorise.yellow("   =========================")))
    except:
        print((NEWLINE_AND_INDENT_1_TAB + "Some exiftool error happened!\n"))
        with open(PATH_TO_REPORT, "w") as report_file:
            print((NEWLINE_AND_INDENT_1_TAB + "Report:" +
                   TWO_NEWLINES + report_file.read()))
        raise ValueError(NEWLINE_AND_INDENT_1_TAB +
                         "Some exiftool error happened!\n" + str(exiftool_output))


@print_current_task_name_decorator
@display_timing
def _TASK_rename_exif_files():
    for exif_file_name in yield_exif_files_from_location(full_path_of(FOLDER_UNSORTED)):
        print(exif_file_name)


@print_current_task_name_decorator
@display_timing
def _TASK_collect_info_from_EXIF_files():
    # global file_info_array

    # get filenames of images in unsorted folder
    for image_file_name in yield_image_files_from_location(full_path_of(FOLDER_UNSORTED), include_paths=False):
        image_file_name_only, image_file_extension = os.path.splitext(
            image_file_name)

        # print(Colorise.red(INDENT_SMALL + "WARNING: stopped treating EXTENSIONS_SPECIAL_RAW_IMAGES specially"))
        if image_file_extension in EXTENSIONS_SPECIAL_RAW_IMAGES:
            # these special RAW files should be manually procesed, but shouldn't stay here,
            # they should be moved to their dedicated folders and stay there
            print((
                    INDENT_SMALL + "Exif file belonging to special RAW    NOT   ignored (OK) - (check this logic)"))
            print(image_file_name)
            # continue
        # TODO: add handling for video files

        # exif_file_name = full_path_of(FOLDER_UNSORTED, image_file_name_only + image_file_extension +
        # EXIF_EXTENSION)
        exif_file_name = full_path_of(
            FOLDER_UNSORTED, image_file_name_only + EXIF_EXTENSION)
        if not os.path.exists(exif_file_name):
            # TIP: there could be file extension in exif file name!
            print((Colorise.red(INDENT_SMALL + "WARNING: EXIF was probably already moved! (") +
                   image_file_name + " > " + os.path.basename(exif_file_name) + Colorise.red("),")))
            continue

            # output:
            # *** PROBLEMATIC:  2015-02-07_(Sat)_12.02.50__RAW__f2.5__T1_20__L34.2.eq__I100__G6.CRW,
            #   missing: exposure_time, iso, aperture, camera_symbol, focal_length.
            #   Need to mark the original photo too!
            # WARNING: EXIF was probably already moved!
            # *** PROBLEMATIC:  2015-04-13_(Mon)_20.35.44__RAW__f2.7__T0.5__L98.5.eq__I50__G6.CRW,
            #   missing: exposure_time, iso, aperture, camera_symbol, focal_length.
            #   Need to mark the original photo too!
            # WARNING: EXIF was probably already moved!
            # *** PROBLEMATIC:  IMG_20130829_183126.jpg,  missing: exposure_time, iso, aperture, camera_symbol,
            #   focal_length.  Need to mark the original photo too!
            # *** PROBLEMATIC:  IMG_20130905_083633.jpg,  missing: exposure_time, iso, aperture, camera_symbol,
            #   focal_length.  Need to mark the original photo too!
            # *** PROBLEMATIC:  m_d57f053a01a512805857005949efe8af.jpg,  missing: exposure_time, iso, aperture,
            #   camera_symbol, focal_length.  Need to mark the original photo too!
            # *** PROBLEMATIC:  m_db7a3ffacfa13c5a9756779d51f5122b.jpg,  missing: exposure_time, iso, aperture,
            #   camera_symbol, focal_length.  Need to mark the original photo too!
        # possible encodings:
        # - utf8
        # - utf-16
        # - utf-16-le
        # - utf-16-be
        # - iso-8859-1
        # Try problematic file with http://www.mimastech.com/charset-detector-free-online-text-files-charset-detector/
        with open(exif_file_name, encoding="iso-8859-1") as exif_file_handler:
            extraction_success = extract_data_from_EXIF_file_and_rename_original_image(
                exif_file_handler, image_file_name)
        if extraction_success:
            rename_exif_file(exif_file_name, image_file_name)
        else:
            # print("WARNING, will be problem with '.jpeg' (4-letter) extensions". probably solved)
            moved_exif_file_name = os.path.join(NOT_ENOUGH_INFO_subfolder_full_path,
                                                os.path.splitext(image_file_name)[0] + EXIF_EXTENSION)
            try:
                os.rename(
                    exif_file_handler.name,
                    moved_exif_file_name
                )
            except:
                print((INDENT_SMALL + "Problem when moving EXIF files"))


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


@print_current_task_name_decorator
@display_timing
def _TASK_rename_and_move_images_and_EXIF_files():
    for img_data in file_info_array:
        original_full_file_name = img_data['orig_full_file_name']
        original_file_name = img_data['orig_file_name']
        original_file_ext = format_extension(img_data['orig_file_ext'])
        raw_marker = get_raw_marker(original_file_ext)
        file_name = get_file_name(img_data, raw_marker)
        source_img_path = full_path_of(
            FOLDER_UNSORTED, original_full_file_name)
        destination_img_path, destination_exif_path = \
            get_the_destination_path(
                file_name, original_file_ext, source_img_path, 0)

        try:
            os.rename(source_img_path, full_path_of(destination_img_path))
        except:
            print((Colorise.red(INDENT_SMALL +
                                "DUPLICATE IMG - THIS SHOULDN'T HAVE HAPPENED")))
            print((INDENT_SMALL + "  source_img_path: " + source_img_path))
            print((INDENT_SMALL + "  destination_img_path: " +
                   full_path_of(destination_img_path)))
        # now renaming EXIFs. they have original file extension as part of the file name
        try:
            os.rename(
                full_path_of(FOLDER_UNSORTED, original_file_name +
                             original_file_ext + EXIF_EXTENSION),
                full_path_of(destination_exif_path)
            )
        except:
            print((Colorise.red(
                INDENT_SMALL + "DUPLICATE EXIF OR FILE DOESN'T EXIST - THIS SHOULDN'T HAVE HAPPENED (?)")))
            print((INDENT_SMALL + "  source_exif_path: " + full_path_of(FOLDER_UNSORTED,
                                                                        original_file_name + original_file_ext + EXIF_EXTENSION)))
            print((INDENT_SMALL + "  destination_exif_path: " +
                   full_path_of(destination_exif_path)))


@print_current_task_name_decorator
@display_timing
def _TASK_process_RAWs():
    if len(os.listdir(full_path_of(FOLDER_CR2_CONV))):
        print((INDENT_SMALL +
               "FOLDER_CR2_CONV - non-empty, will launch dpviewer converter"))
        print((os.listdir(full_path_of(FOLDER_CR2_CONV))))
        _TASK_launch_dpviewer()
    if len(os.listdir(full_path_of(FOLDER_CRW_CONV))):
        print((INDENT_SMALL + "FOLDER_CRW_CONV - non-empty, will launch CRW converter"))
        print((os.listdir(full_path_of(FOLDER_CRW_CONV))))
        _TASK_convert_CRWs()
    if len(os.listdir(full_path_of(FOLDER_ARW_CONV))):
        print((INDENT_SMALL + "FOLDER_ARW_CONV - non-empty, will launch Sony converter"))
        print((os.listdir(full_path_of(FOLDER_ARW_CONV))))
        _TASK_launch_sony_converter()
    if len(os.listdir(full_path_of(FOLDER_MPO_CONV))):
        print((Colorise.bg_yellow(INDENT_SMALL +
                                  "FOLDER_MPO_CONV - non-empty, BUT converter not specified")))
        print((os.listdir(full_path_of(FOLDER_MPO_CONV))))
    if len(os.listdir(full_path_of(FOLDER_RW2_CONV))):
        print((Colorise.bg_yellow(INDENT_SMALL +
                                  "FOLDER_RW2_CONV - non-empty, BUT converter not specified")))
        print((os.listdir(full_path_of(FOLDER_RW2_CONV))))
    if len(os.listdir(full_path_of(FOLDER_DNG_CONV))):
        print((Colorise.bg_yellow(INDENT_SMALL +
                                  "FOLDER_DNG_CONV - non-empty, BUT converter not specified")))
        print((Colorise.bg_yellow(INDENT_SMALL + "CONVERSION FROM DNG NOT YET SUPPORTED!")))
        print((os.listdir(full_path_of(FOLDER_DNG_CONV))))


@print_current_task_name_decorator
@display_timing
def _TASK_convert_CRWs():
    # TODO: check if we can use lowercase (fnmatch is used), if so, use EXTENSION_RAW_CRW
    for CRW_file in yield_pattern_matching_files_from_location(full_path_of(FOLDER_CRW_CONV), crw_pattern):
        print((INDENT_SMALL + "converting: " + CRW_file[1]))
        # thr
        convert_CRW(CRW_file[1])
    # TODO:
    # not a good idea, result files are smaller than originals!
    # for CRW_file in yield_pattern_matching_files_from_location("*.cr2", full_path_of(FOLDER_CRW_CONV), False):
    #   print(INDENT_SMALL + "converting:" + CRW_file))
    #   convert_CRW(CRW_file)


@print_current_task_name_decorator
@display_timing
def _TASK_launch_dpviewer():
    # if orig_raw_counter > 0:
    print((INDENT_SMALL + "Will launch DPViewer converter..."))
    subprocess.check_call(
        [
            PATH_TO_DPVIEWER,
            os.path.abspath(full_path_of(FOLDER_CR2_CONV))
        ]
    )
    # else:
    #     print(INDENT_SMALL + "No RAWs to process by DPViewer")


@print_current_task_name_decorator
@display_timing
def _TASK_launch_sony_converter():
    print((INDENT_SMALL + "Will launch Sony converter..."))
    print(PATH_TO_SONY_CONVERTER)
    subprocess.check_call(
        [
            PATH_TO_SONY_CONVERTER,
            # os.path.abspath(full_path_of(FOLDER_ARW_CONV))
        ]
    )


@print_current_task_name_decorator
@display_timing
def _TASK_move_the_results():
    global created_folders

    for result_folder in FOLDERS_RESULT:
        for image_file_name in yield_pattern_matching_files_from_location(full_path_of(result_folder), ""):
            file_extension = get_lowercase_extension(image_file_name[1])
            if file_extension not in (EXTENSIONS_SUPPORTED_IMAGES + EXTENSIONS_SUPPORTED_NON_IMAGES):
                # ignore not recognised extensions
                continue
            if file_extension == EXIF_EXTENSION:
                move_file_to_destination(
                    created_folders, image_file_name, "EXIF", SUBFOLDER_NAMES["EXIF"])
            elif file_extension in EXTENSIONS_RAW_IMAGES:
                move_file_to_destination(
                    created_folders, image_file_name, "RAW", SUBFOLDER_NAMES["RAW"])
            else:
                move_lossy_image_files(image_file_name)


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
    global problematic_files_counter
    print((INDENT_SMALL + " Problem when sorting/moving PRE-EXISTING " +
           file_type + " file (will move): " + image_file_name[1]))
    try:
        os.rename(
            image_file_name[0],
            os.path.join(os.path.join(
                DUPLICATE_FILE_NAMES_subfolder_full_path, image_file_name[1]))
        )
        problematic_files_counter += 1
    except:
        print((Colorise.red(INDENT_2_TABS + "ERROR! File: ") + image_file_name[0] + Colorise.red(
            " already exists in PROBLEMATIC/DUPLICATE folder: " + DUPLICATE_FILE_NAMES_subfolder_full_path)))


@print_current_task_name_decorator
@display_timing
def _TASK_sort_the_results():
    folder_sorter()


@print_current_task_name_decorator
@display_timing
def _TASK_show_stats():
    if moved_old_exif_counter > 0:
        print((NEWLINE_AND_INDENT_1_TAB + "(Re)moved " +
               str(moved_old_exif_counter) + " old EXIF files"))
    if problematic_files_counter > 0:
        print((NEWLINE_AND_INDENT_1_TAB +
               str(problematic_files_counter) + " problematic files"))
        redate_problematic_folder()
        redate_problematic_folder(False)
    if (fail_counter == duplicate_counter == 0):
        print((INDENT_SMALL + "All OK!"))
    else:
        show_issues_info()
    display_extra_messages()
    display_task_stats()


def redate_problematic_folder(should_delete=True):
    """To mark the PROBLEMATIC folder as edited"""
    temporary_file_path = full_path_of(FOLDER_PROBLEMATIC, ".marker.temp")
    temporary_file = open(temporary_file_path, "w")
    temporary_file.write("problematic files: " +
                         str(problematic_files_counter))
    temporary_file.close()
    if os.path.exists(temporary_file_path) and should_delete:
        os.remove(temporary_file_path)


def show_issues_info():
    if fail_counter > 0:
        print((INDENT_SMALL + str(fail_counter) +
               " problems with " + "some files"))
    if info_extraction_critical_fail_counter > 0:
        print((INDENT_SMALL + str(info_extraction_critical_fail_counter) +
               " CRITICAL problems with " + "some files"))
        print((INDENT_SMALL + "Files moved to 'PROBLEMATIC' folder"))
    if duplicate_counter > 0:
        print((NEWLINE_AND_INDENT_1_TAB + "Found " +
               str(duplicate_counter) + " same-size files!"))


def display_extra_messages():
    print((Colorise.yellow(INDENT_SMALL + "CRW not extracted")))
    print((Colorise.yellow(INDENT_SMALL + "MPO not extracted")))
    print((Colorise.yellow(INDENT_SMALL + "RW2 not extracted")))


def display_task_stats():
    print((INDENT_SMALL + str(task_counter) + " tasks performed"))


def get_all_files_count():
    DIR = full_path_of(FOLDER_UNSORTED)
    return len([name for name in os.listdir(DIR) if os.path.isfile(os.path.join(DIR, name))])


def display_total_time(processing_start_time, all_files_count):
    processing_duration = time.time() - processing_start_time
    m, s = divmod(processing_duration, 60)
    h, m = divmod(m, 60)
    print((Colorise.yellow(NEWLINE_AND_INDENT_2_TABS +
                           "Total processing time: ") + "%d:%02d:%02d" % (h, m, s)))
    if all_files_count:
        print((Colorise.yellow(INDENT_2_TABS + "Time per photo: ") +
               str(round(processing_duration / all_files_count, 2)) + " s"))
    print((Colorise.yellow(INDENT_2_TABS +
                           "All files (photos + other): ") + str(all_files_count)))


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


def main():
    processing_start_time = time.time()
    _TASK_verify_if_folders_exist(FOLDERS_ALL)
    all_files_count = get_all_files_count()

    print(" -----------------------------------------------------------------------------------------")
    # print("Some tasks TEMPORARILY DISABLED, but should be ON!")

    generate_exifs = True
    # generate_exifs = ask_if_generate_exifs()
    print("Will generate exifs")
    _TASK_remove_empty_image_files()
    if generate_exifs:
        _TASK_move_old_exif_files()
        _TASK_generate_exif_files()
    # _TASK_rename_exif_files()  # only lists them atm. renaming actually takes place in the task below.
    #   good idea to separate:
    _TASK_collect_info_from_EXIF_files()
    _TASK_rename_and_move_images_and_EXIF_files()
    _TASK_process_RAWs()
    _TASK_move_the_results()
    _TASK_sort_the_results()
    _TASK_show_stats()

    display_total_time(processing_start_time, all_files_count)

    tada()

    print(" -----------------------------------------------------------------------------------------")


# -----------------------------------------------------------------------------------------
# :::::::  OLD COMMENTS  :::::::

# \s*(.*)$             # comment
# regex_trailing_line = re.compile(r"(.*)[ \t]+$")
# print(regex_trailing_line.sub("$1dz", "Dz", "dziendobry"))
# print(regex_trailing_line.sub("$1dz", "Dz", "dziendobry "))
# m = re.match(regex_trailing_line, "dzien    ")
# print(len(m.group(1)))


# for image_details in file_info_array:
# print(image_details  #, file_info_array[image_details])
# exif_file = open(os.path.join(ROOT_FOLDER_PATH, image_file[:-4] + EXIF_EXTENSION))
# exif_file_contents = exif_file.read()
# print(len(exif_file_contents))
# print
# # print(exif_file_contents)
# # print
# results = search_for_language_name_regex.findall(exif_file_contents)
# # results = search_camera_model_query.findall(exif_file_contents)
# print(results)
# if len(results) > 0:
#   for res in results:
#       print(res)
# exif_file.close()

if __name__ == "__main__":
    main()
    print("\n\n\tZaimplementowac licznik nienazwanych folderow i nowych, moze starych?")
