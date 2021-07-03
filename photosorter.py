import subprocess
import fnmatch
import os
import ntpath
import dateutil.parser  # import parse as dateutil_parser
import datetime
import csv

# import time
# import re
# import shutil

from exiftool_EXIF_extractor_config import *


pattern_name = "*.*"
crw_pattern = "*.CRW"
# jpg_pattern = "*.jpg"
exif_ext_str = "._exif"
duplicate_str = "__DUPL"

fail_counter = 0
critical_fail_counter = 0
duplicate_counter = 0

file_info_array = []
created_folders = []


# --------------   NOT USED FUNCTIONS   -----------------


# def read_CSV_data():

#     with open('eggs.csv', newline='') as csvfile:
#         spamreader = csv.reader(csvfile, delimiter=' ', quotechar='|')
#         for row in spamreader:
#             print(', '.join(row))


# --------------   USED FUNCTIONS   -----------------


def convert_CRW(file_name):
    """Will convert. file_name could a pattern too, like "*.CRW"."""

    irfanview_output = subprocess.check_call(
        [
            path_to_irfanview,
            os.path.abspath(os.path.join(
                full_path_of(CRW_conv_folder), file_name)),
            "/jpgq=96",
            "/convert=$D$N.jpg"
        ]
    )
    # subprocess.call(path)
    if irfanview_output:
        print len(irfanview_output), irfanview_output
    # print "\nconversion SUCCESS\n"


#  not used yet
def yield_pattern_matching_files_from_location(pattern, root):
    """Locate all files matching supplied filename pattern in and below    supplied root directory."""

    # for path, dirs, files in os.walk(os.path.abspath(root)):
    # for path, dirs, files in os.walk(os.path.abspath(root)):
    files = [f for f in os.listdir(
        root) if os.path.isfile(os.path.join(root, f))]
    for filename in fnmatch.filter(files, pattern):
        # if include_paths:
        yield (os.path.join(root, filename), filename)
        # else:
        # yield filename


def yield_image_files_from_location(root, include_paths):

    for file in os.listdir(root):

        if os.path.isfile(os.path.join(root, file)):

            filename, file_extension = os.path.splitext(file)

            filename = filename.lower()
            file_extension = file_extension.lower()

            if file_extension in supported_image_extensions:

                yield file

            elif file_extension in supported_non_image_extensions:

                pass

            else:
                print "  [ WARNING ] File_extension: " + file_extension + " not supported ( '" + file + "' ). File moved."
                # try:
                # print file
                # print full_path_of(problematic_folder)
                # print UNSUP_EXT_subfolder_name
                # print os.path.join(full_path_of(full_path_of(problematic_folder) + "\\" + UNSUP_EXT_subfolder_name))
                # print os.path.join(full_path_of(problematic_folder), UNSUP_EXT_subfolder_name, filename + file_extension)

                UNSUP_EXT_subfolder_name_full_path = os.path.join(full_path_of(
                    full_path_of(problematic_folder)), UNSUP_EXT_subfolder_name)
                if not os.path.exists(UNSUP_EXT_subfolder_name_full_path):
                    os.makedirs(UNSUP_EXT_subfolder_name_full_path)

                os.rename(
                    os.path.join(full_path_of(unsorted_folder), file),
                    os.path.join(full_path_of(problematic_folder),
                                 UNSUP_EXT_subfolder_name, filename + file_extension)
                )
                # except:
                # print "\n  Problem when moving not supported extension files (duplicate already exists?)"
                # raise ValueError("  file_extension: " + file_extension + " not supported ( '" + file + "'' )")


def get_filename_from_path(path):

    return ntpath.basename(path)  # .split(".")[0]


def convert_to_date_time(unformatted_image_datetime, time_too):

    # datetime_str = unformatted_image_datetime.replace(":", ".")
    # datetime_str = datetime_str[0:4] + "-" + datetime_str[5:7] + "-" + datetime_str[8:]
    # print datetime_str

    str_Y = unformatted_image_datetime[0:4]
    str_M = unformatted_image_datetime[5:7]
    str_D = unformatted_image_datetime[8:10]
    if time_too:
        str_H = unformatted_image_datetime[11:13]
        str_m = unformatted_image_datetime[14:16]
        str_S = unformatted_image_datetime[17:19]

    # print "\t", str_Y,
    # print ", ", str_M,
    # print ", ", str_D,
    # if time_too:
    #     print ", ", str_H,
    #     print ", ", str_m,
    #     print ", ", str_S

    # print (datetime_str[0:4])
    # print (datetime_str[5:7])
    # print (datetime_str[8:])

    # return datetime.datetime(year, month, day[, hour[, minute[, second[, microsecond[, tzinfo]]]]])

    if time_too:

        photo_datetime = datetime.datetime(

            int(str_Y),
            int(str_M),
            int(str_D),
            int(str_H),
            int(str_m),
            int(str_S)
        )

    else:

        photo_datetime = datetime.datetime(

            int(str_Y),
            int(str_M),
            int(str_D)
        )

    return photo_datetime


def reformat_timestring(timestring):

    timestring = timestring.replace(":", ".")

    timestring = timestring[0:4] + "-" + timestring[5:7] + "-" + timestring[8:]
    weekday = dateutil.parser.parse(timestring[:10]).strftime("%a")
    timestring = timestring.replace(" ", "_(" + weekday + ")_")

    # prevoious scheme example:
    # 2015-11-23_(Mon)_09.26.27__RAW__f4.0...T1_20..50mm1250.JPG
    # vs:
    # 2015-04-13_(Mon)_20.35.44__f2.7__T0.5__RAW__L98.5.eq__I50__G6__DUPL_(3).CRW

    # a = "2012-10-09"  # T19:00:55Z"
    # print dateutil.parser.parse(a), dateutil.parser.parse(a).weekday()
    # a = "2012-10-09 T19:00:55Z"
    # print dateutil.parser.parse(a), dateutil.parser.parse(a).strftime("%a")

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
        actual_f_length_string = focal_length_entry[0].split(" mm (35 mm")[0]
        # print actual_f_length_string
    focal_length_string = focal_length_string.replace(" ", "")
    return focal_length_string.replace("mm", "")


def extract_data_from_EXIF_file(exif_file, image_name):

    global file_info_array, fail_counter, critical_fail_counter

    # img_pathname = exif_file.name
    # print "::: " + get_filename_from_path(img_pathname), image_name

    camera_name = ""
    camera_symbol = ""
    image_info_object = {}
    unformatted_image_datetime = ""
    previous_critical_fail_counter = critical_fail_counter

    image_info_object["orig_full_file_name"] = image_name
    # image_info_object["orig_file_name"] = image_name.split(".")[0]
    image_info_object["orig_file_name"], image_info_object["orig_file_ext"] = os.path.splitext(
        image_name)

    # name example:
    # name_template = "2014-05-26_(Mon)_13.24.40__f2.2...T1_33..4.2mm125.jpg"

    for line in exif_file:

        if line.startswith('Camera Model Name'):

            # re.sub(pattern, repl, string, count=0, flags=0)
            # exif_entry = regex_trailing_line.sub("interfaceOpDataFile %s" % fileIn, line)
            camera_name = extract_value_of_EXIF_key(line)
            camera_symbol = get_camera_symbol(camera_name)

            image_info_object["camera_symbol"] = camera_symbol
            # print "\t camera_name: _" + camera_name + "_  symbol: " + camera_symbol

        if line.startswith('Date/Time Original'):

            unformatted_image_datetime = extract_value_of_EXIF_key(line)

        elif line.startswith('Aperture'):

            aperture = "f" + extract_value_of_EXIF_key(line)
            image_info_object["aperture"] = aperture
            # print "\t aperture: _" + aperture + "_"

        elif line.startswith('Exposure Time'):

            exposure_time = "T" + \
                reformat_exposure_time(extract_value_of_EXIF_key(line))
            image_info_object["exposure_time"] = exposure_time
            # print "\t exposure_time: _" + exposure_time + "_"

        elif line.startswith('ISO  '):

            iso = "I" + extract_value_of_EXIF_key(line)
            image_info_object["iso"] = iso
            # print "\t iso: _" + iso + "_"

        elif line.startswith('Focal Length'):

            focal_length = "L" + \
                reformat_focal_length(extract_value_of_EXIF_key(line))
            image_info_object["focal_length"] = focal_length
            # print "\t focal_length: _" + focal_length + "_"

    # some rescue operations
    missing_parts = []
    if "exposure_time" not in image_info_object.keys():
        # print "-------------------  exposure_time missing!  -------------------"
        missing_parts.append("exposure_time")
        image_info_object["exposure_time"] = "T---"
        fail_counter += 1
    if "iso" not in image_info_object.keys():
        # print "-------------------  ISO info is missing!  -------------------"
        missing_parts.append("iso")
        image_info_object["iso"] = "I---s"
        fail_counter += 1
    if "aperture" not in image_info_object.keys():
        # print "-------------------  aperture info is missing!  -------------------"
        missing_parts.append("aperture")
        fail_counter += 1
        critical_fail_counter += 1
    if "camera_symbol" not in image_info_object.keys():
        # print "-------------------  camera_symbol info is missing!  -------------------"
        missing_parts.append("camera_symbol")
        fail_counter += 1
        critical_fail_counter += 1
    if "focal_length" not in image_info_object.keys():
        # print "-------------------  focal_length info is missing!  -------------------"
        missing_parts.append("focal_length")
        fail_counter += 1
        critical_fail_counter += 1

    # move file if problematic
    if previous_critical_fail_counter < critical_fail_counter:
        print " *** PROBLEMATIC:  " + image_info_object["orig_file_name"] + image_info_object["orig_file_ext"] + ",  missing: " + ", ".join(missing_parts)
        # print(image_name)
        # print(os.path.join(full_path_of(problematic_folder)))
        # print(image_info_object["orig_file_name"])
        # print(image_info_object["orig_file_ext"])
        # print exif_file.name
        os.rename(
            os.path.join(full_path_of(unsorted_folder), image_name),
            os.path.join(full_path_of(problematic_folder),
                         image_info_object["orig_file_name"] + image_info_object["orig_file_ext"])
        )
        return False

    # process image date_time, apply timezone correction if necessary
    # image_date_time = convert_to_date_time(unformatted_image_datetime, True)
    image_datetime = apply_timezone_correction(
        unformatted_image_datetime, camera_symbol)
    image_info_object["image_datetime"] = reformat_timestring(image_datetime)

    file_info_array.append(image_info_object)

    return True


def full_path_of(folder_name):

    return os.path.join(root_folder_path, folder_name)


def rename_exif_file(exif_file_name, image_file_name):

    os.rename(exif_file_name, os.path.join(full_path_of(
        unsorted_folder), image_file_name + exif_ext_str))


def extract_value_of_EXIF_key(exif_entry):

    return exif_entry.split(": ", 1)[1].strip()


def fake_dict_keys_value(fake_dict, fake_key):

    # print len(fake_dict)
    for entry in fake_dict:

        if entry[0] == fake_key:

            return entry[1]

    return None


def get_camera_symbol(camera_name):

    cam_symb = fake_dict_keys_value(known_cameras_symbols, camera_name)

    if cam_symb is None:
        print "UNKNOWN camera encountered!"
        raise ValueError('UNKNOWN camera encountered (' + camera_name + ')')
    else:
        return cam_symb


def iterator_str(iterator):

    if iterator == 0:
        return ""
    else:
        return "_(" + str(iterator + 1) + ")"


def get_the_destination_path(file_name, file_ext, source_img_path, iterator=0):

    global duplicate_counter

    if file_ext.lower() in raw_image_extensions:
        if file_ext.lower() in special_raw_image_extensions:
            path_to_destination_photos = full_path_of(CRW_conv_folder)
        else:
            path_to_destination_photos = full_path_of(orig_raw_folder)
    else:
        path_to_destination_photos = full_path_of(orig_jpg_folder)

    destination_img_path = os.path.join(
        path_to_destination_photos, file_name + iterator_str(iterator) + file_ext)
    destination_exif_path = os.path.join(
        path_to_destination_photos, file_name + iterator_str(iterator) + exif_ext_str)

    # or os.path.exists(destination_exif_path):
    if os.path.exists(destination_img_path):

        # TODO:
        if os.path.exists(destination_img_path) and os.path.getsize(destination_img_path) == os.path.getsize(source_img_path):

            # when exifs existed on both sides, was giving this message
            # print ">>> the same size"
            duplicate_counter += 1
            if duplicate_str not in file_name:
                file_name = file_name + duplicate_str
                return get_the_destination_path(file_name, file_ext, source_img_path, 0)
            else:
                return get_the_destination_path(file_name, file_ext, source_img_path, (iterator + 1))

        destination_img_duplicate_path = os.path.join(
            path_to_destination_photos, file_name + iterator_str(iterator) + file_ext)

        if os.path.exists(destination_img_duplicate_path):
            print "####  file exists"

        return get_the_destination_path(file_name, file_ext, source_img_path, (iterator + 1))
    else:
        return (destination_img_path, destination_exif_path)


def get_one_day_before_folder_name(folder_name):

    date_time = convert_to_date_time(folder_name, False)

    d = date_time - datetime.timedelta(days=1)
    print("Original date = ", folder_name, ", shifted date = ", d)

    weekday = d.strftime("%a")
    d = str(d)

    return d[0:4] + "-" + d[5:7] + "-" + d[8:10] + "_(" + weekday


def create_date_folder(photo_name):
    """Create folder name like 2014-05-08_(Thu) - 1. ######"""

    global created_folders

    split_name = photo_name.split(")_")
    folder_name = split_name[0]
    photo_time = split_name[1].split("__f")[0]

    # verify_if_date_still_of_day_before:
    # 2016-05-29_(Sun)_15.50.33__f4.0__T1_128__L82.2q__I200__5D.CR2
    # print(int(photo_time[:2]))
    # print(int(photo_time[3:5]))
    # print(int(photo_time[6:8]))

    # 2014-05-29_(Sun)_03.50.33__f4.0__T1_128__L82.2q__I200__5D.CR2

    if int(photo_time[:2]) <= int(day_division_time[:2]):

        if int(photo_time[:2]) == int(day_division_time[:2]):

            if int(photo_time[3:5]) <= int(day_division_time[3:5]):

                if int(photo_time[3:5]) == int(day_division_time[3:5]):

                    if int(photo_time[6:8]) < int(day_division_time[6:8]):

                        folder_name = get_one_day_before_folder_name(
                            folder_name)
                else:
                    folder_name = get_one_day_before_folder_name(folder_name)
        else:
            folder_name = get_one_day_before_folder_name(folder_name)

    folder_name = folder_name + ") - 1. ######"

    folder_destination = os.path.join(full_path_of(ready_folder), folder_name)
    # check_if folder has been created
    if folder_name not in created_folders:

        if not os.path.exists(folder_destination):
            os.makedirs(folder_destination)
        created_folders.append(folder_name)

    return folder_destination


# -------  TASKS  --------------------------------------------------------------------------


def _TASK_verify_if_folders_exist(all_folders):

    global root_folder_path

    missing_folder_count = 0
    missing_folders = []
    for folder_name in all_folders:
        folder_full_path = full_path_of(folder_name)
        if not os.path.exists(folder_full_path):

            if missing_folder_count == 0:
                print "\n\n"

            print "  Folder missing: ", folder_name
            missing_folder_count += 1
            missing_folders.append(folder_name)

    if missing_folder_count:
        # print "\n  Missing folders count:", missing_folder_count, "\n"
        if len(missing_folders) == len(all_folders):
            print "\n  [ WARNING ] None of the required folders is present.\n"
            print "    The root folder path is:", root_folder_path
            print "    Current working directory is:", os.getcwd()
            answer = raw_input(
                "    Use the current working directory? (Enter=yes): ")
            if answer == "":
                root_folder_path = os.path.join(os.getcwd(), "__PROC_PHOTOS")
                print "\n  Will use the following path: ", root_folder_path, "\n"
            else:
                answer = raw_input(
                    "  Continue with original root folder path? (Enter=yes): ")
                if answer != "":
                    print "\n\tQuitting\n"
                    quit()

        for folder_name in missing_folders:
            os.makedirs(full_path_of(folder_name))
            print "  Folder '" + folder_name + "' created."

        print "\n\n"


def _TASK_generate_exif_files():
    """    Generate EXIF files."""
    # try:

    print "\n\n Initialising, extracting, creating EXIF files...\n"

    # http://stackoverflow.com/questions/36169571/python-subprocess-check-call-vs-check-output
    exiftool_output = subprocess.check_call(
        [
            exiftool_name,
            "-a",
            "-u",
            "-g1",
            # "-b",  # dump of the binary section
            "-w!",
            exif_ext_str,
            full_path_of(unsorted_folder)
            # + "' > '" + path_to_report + "'"
        ]
    )
    # subprocess.call(path)
    if exiftool_output:
        print len(exiftool_output), exiftool_output
    print "\n\tSUCCESS\n"

    # except:
    #     print "\nSome exiftool error happened!\n"
    #     raise ValueError("\nSome exiftool error happened!\n" + str(exiftool_output))
    # with open(path_to_report, "w") as report_file:
    # print "\nReport:\n\n" + report_file.read()


def _TASK_collect_info_from_EXIF_files():

    global file_info_array

    for image_file_name in yield_image_files_from_location(full_path_of(unsorted_folder), include_paths=True):

        exif_file_name = os.path.join(full_path_of(
            unsorted_folder), image_file_name[:-4] + exif_ext_str)
        with open(exif_file_name) as exif_file:

            extraction_success = extract_data_from_EXIF_file(
                exif_file, image_file_name)

        if extraction_success:
            rename_exif_file(exif_file_name, image_file_name)
        else:
            moved_exif_file_name = os.path.join(full_path_of(
                problematic_folder), image_file_name[:-4] + exif_ext_str)
            try:
                os.rename(
                    exif_file.name,
                    moved_exif_file_name
                )
            except:
                print "Problem when moving EXIF files"


def _TASK_rename_and_move_images_and_EXIF_files():

    print "\n\n Will process the results now.\n"

    for img_data in file_info_array:

        # print "\n ", len(img_data), img_data  # , len(image_file)

        original_full_file_name = img_data['orig_full_file_name']
        original_file_name = img_data['orig_file_name']
        original_file_ext = img_data['orig_file_ext']

        # add RAW file marker
        raw_marker = ""
        if original_file_ext.lower() in raw_image_extensions:
            raw_marker = raw_marker_str
            original_file_ext = original_file_ext.upper()
        else:
            original_file_ext = original_file_ext.lower()

        file_name = \
            img_data['image_datetime'] + "__" + \
            raw_marker + \
            img_data['aperture'] + "__" + \
            img_data['exposure_time'] + "__" + \
            img_data['focal_length'] + "__" + \
            img_data['iso'] + "__" + \
            img_data['camera_symbol']

        # print file_name + img_data["orig_file_ext"]

        source_img_path = os.path.join(full_path_of(
            unsorted_folder), original_full_file_name)
        destination_img_path, destination_exif_path = get_the_destination_path(
            file_name, original_file_ext, source_img_path, 0)

        try:
            os.rename(
                source_img_path,
                destination_img_path
            )
        except:
            print "DUPLICATE IMG - THIS SHOULDN'T HAVE HAPPENED"

        # now renaming EXIFs. they have original file extension as part of the file name
        try:
            os.rename(
                os.path.join(full_path_of(unsorted_folder),
                             original_file_name + original_file_ext + exif_ext_str),
                destination_exif_path
            )
        except:
            print "DUPLICATE EXIF OR FILE DOESN'T EXIST - THIS SHOULDN'T HAVE HAPPENED (?)"

    print
    # print file_info_array


def _TASK_convert_CRWs():

    for CRW_file in yield_pattern_matching_files_from_location(crw_pattern, full_path_of(CRW_conv_folder)):

        print(" converting: " + CRW_file[1])
        convert_CRW(CRW_file[1])

    # not a good idea, reult files are smaller than originals!
    # for CRW_file in yield_pattern_matching_files_from_location("*.cr2", full_path_of(CRW_conv_folder), False):
    #     print("converting:" + CRW_file)
    #     convert_CRW(CRW_file)


def _TASK_launch_dpviewer():

    print("\n Will launch DPViewer converter...")
    subprocess.check_call(
        [
            path_to_dpviewer,
            os.path.abspath(full_path_of(CRW_conv_folder))
        ]
    )


def _TASK_move_the_results():

    print "_TASK_move_the_results"

    global created_folders

    for result_folder in result_folders:

        for file_format in (supported_image_extensions + supported_non_image_extensions):
            # print(file_format)
            # yield_image_files_from_location(root, include_paths)
            for image_file_name in yield_pattern_matching_files_from_location("*" + file_format, full_path_of(result_folder)):

                # print("File destination: ", os.path.join(create_date_folder(image_file_name[1]), image_file_name[1]))

                if "._exif" in image_file_name[1]:
                    EXIF_folder_destination = os.path.join(
                        create_date_folder(image_file_name[1]), EXIF_subfolder_name)
                    # check_if folder has been created
                    if EXIF_folder_destination not in created_folders:

                        if not os.path.exists(EXIF_folder_destination):
                            os.makedirs(EXIF_folder_destination)

                    os.rename(
                        image_file_name[0],
                        os.path.join(EXIF_folder_destination,
                                     image_file_name[1])
                    )
                elif image_file_name[1][-4:].lower() in (raw_image_extensions + special_raw_image_extensions):
                    RAW_folder_destination = os.path.join(
                        create_date_folder(image_file_name[1]), RAW_subfolder_name)
                    # check_if folder has been created
                    if RAW_folder_destination not in created_folders:

                        if not os.path.exists(RAW_folder_destination):
                            os.makedirs(RAW_folder_destination)

                    os.rename(
                        image_file_name[0],
                        os.path.join(RAW_folder_destination,
                                     image_file_name[1])
                    )
                else:
                    os.rename(
                        image_file_name[0],
                        os.path.join(create_date_folder(
                            image_file_name[1]), image_file_name[1])
                    )


def _TASK_sort_the_results():

    return


def _TASK_show_stats():

    if (fail_counter > 0) or (duplicate_counter > 0):
        if fail_counter > 0:
            print("\n\tEncountered " + str(fail_counter) +
                  " problems with " + "some files")
        if critical_fail_counter > 0:
            print("\n\tEncountered " + str(critical_fail_counter) +
                  " CRITICAL problems with " + "some files")
        if duplicate_counter > 0:
            print("\n\tFound " + str(duplicate_counter) + " same-size files!")
        print "Files moved to 'PROBLEMATIC' folder"
    else:
        print("\n\tAll OK!")


def _TASK_display_extra_messages():

    print("\n    Extra messages:\n")
    print("\tCRW not extracted")
    print("\tMPO not extracted")


# -----------------------------------------------------------------------------------------


_TASK_verify_if_folders_exist(all_folders)
_TASK_generate_exif_files()
_TASK_collect_info_from_EXIF_files()
_TASK_rename_and_move_images_and_EXIF_files()
_TASK_convert_CRWs()
# would be good to launch this guy in a separate thread and monitor if closed:
_TASK_launch_dpviewer()
# print ("Didn't launch the dpviewer!")
_TASK_move_the_results()
_TASK_sort_the_results()
_TASK_show_stats()
_TASK_display_extra_messages()


# -----------------------------------------------------

# os.mkdir('H:\\__ Photos\\____Photos to be sorted\\[ Photo sorting process ]\\_NEW\\__PROC_PHOTOS\\1. Original CRW')
# os.mkdir('H:\__ Photos\____Photos to be sorted\[ Photo sorting process ]\_NEW\__PROC_PHOTOS\1. Original CRW')
# os.mkdir('H:\__ Photos\____Photos to be sorted\[ Photo sorting process ]\_NEW\__PROC_PHOTOS\\1. Original CRW')
# os.mkdir(r'H:\__ Photos\____Photos to be sorted\[ Photo sorting process ]\_NEW\__PROC_PHOTOS\1. Original CRW')
# os.mkdir('H:\__ Photos\____Photos to be sorted___##')

# create_date_folder("2014-05-29_(ORG)_03.50.33__f4.0__T1_128__L82.2q__I200__5D.CR2")
# create_date_folder("2016-03-01_(ORG)_04.44.43__f4.0__T1_128__L82.2q__I200__5D.CR2")
# create_date_folder("2016-03-01_(ORG)_04.44.44__f4.0__T1_128__L82.2q__I200__5D.CR2")
# create_date_folder("2016-05-01_(ORG)_15.50.33__f4.0__T1_128__L82.2q__I200__5D.CR2")
# create_date_folder("2016-07-19_(ORG)_02.50.33__f4.0__T1_128__L82.2q__I200__5D.CR2")
# create_date_folder("2016-07-19_(ORG)_05.50.33__f4.0__T1_128__L82.2q__I200__5D.CR2")

# -----------------------------------------------------------------------------------------
# raw_input("\n\nHIT ENTER\n\n")
# print "2014-05-26_(Mon)_13.24.40__f2.2...T1_33..4.2mm125.jpg"


# :::::::  OLD COMMENTS  :::::::

# \s*(.*)$             # comment
# regex_trailing_line = re.compile(r"(.*)[ \t]+$")
# print regex_trailing_line.sub("$1dz", "Dz", "dziendobry")
# print regex_trailing_line.sub("$1dz", "Dz", "dziendobry ")
# m = re.match(regex_trailing_line, "dzien    ")
# print len(m.group(1))


# for image_details in file_info_array:
# print image_details  #, file_info_array[image_details]
# exif_file = open(os.path.join(root_folder_path, image_file[:-4] + exif_ext_str))
# exif_file_contents = exif_file.read()
# print len(exif_file_contents)
# print
# # print exif_file_contents
# # print
# results = search_for_language_name_regex.findall(exif_file_contents)
# # results = search_camera_model_query.findall(exif_file_contents)
# print results
# if len(results) > 0:
#     for res in results:
#         print res
# exif_file.close()
