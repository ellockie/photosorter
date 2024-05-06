import os
import sys
import time
import ntpath
import subprocess

from common.common import \
    convert_CRW, \
    create_missing_folders, \
    create_problematic_folders, \
    display_extra_messages, \
    display_task_stats, \
    display_total_time, \
    extract_data_from_exif_file_and_rename_original_image, \
    file_sizes_the_same, \
    format_extension, \
    full_path_of, \
    get_all_files_count, \
    get_file_name, \
    get_lowercase_extension, \
    get_raw_marker, \
    get_the_destination_path, \
    move_file_to_destination, \
    move_lossy_image_files, \
    print_header_footer, \
    redate_problematic_folder, \
    rename_exif_file, \
    show_issues_info, \
    tada, \
    yield_exif_files_from_location, \
    yield_image_files_from_location, \
    yield_pattern_matching_files_from_location
from constants.constants import \
    CAMERA_UPLOADS_PATH, \
    crw_pattern, \
    EXIF_EXTENSION, \
    EXIFTOOL_NAME, \
    EXTENSIONS_RAW_IMAGES, \
    EXTENSIONS_SPECIAL_RAW_IMAGES, \
    EXTENSIONS_SUPPORTED_IMAGES, \
    EXTENSIONS_SUPPORTED_NON_IMAGES, \
    FOLDER_ARW_CONV, \
    FOLDER_CR2_CONV, \
    FOLDER_CRW_CONV, \
    FOLDER_DNG_CONV, \
    FOLDER_MPO_CONV, \
    FOLDER_PROBLEMATIC_OLD_EXIF, \
    FOLDER_RW2_CONV, \
    FOLDER_UNSORTED, \
    FOLDER_UNSORTED_FULL_PATH, \
    FOLDERS_ALL, \
    FOLDERS_RESULT, \
    INDENT_SMALL, \
    NEWLINE_AND_INDENT_1_TAB, \
    PATH_TO_DPVIEWER, \
    PATH_TO_REPORT, \
    PATH_TO_SONY_CONVERTER, \
    SUBFOLDER_NAMES, \
    SUBROUTINE_LOG_INDENTATION, \
    TWO_NEWLINES
from common.globals import COUNTERS, file_info_array, FULL_PATH_SUBFOLDER, created_folders
from utils.decorators import print_current_task_name, display_timing
from move_other_images import move_other_images
from folder_sorter import folder_sorter
from utils.colorise import Colorise

print(Colorise.blue(f"\n Python executable used:  {sys.executable}"))
print(Colorise.blue(f" Current python version:  {sys.version}\n"))
assert sys.version.startswith("3."), "Error: Python 3 is required!"


#  Command line option(s):
#  - generate-exifs:   generate exif files (without asking)


# -------  TASKS  --------------------------------------------------------------------------


@print_current_task_name
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


@print_current_task_name
@display_timing
def _TASK_move_other_images():
    move_other_images()


@print_current_task_name
@display_timing
def _TASK_get_photos_from_uploads_folder():
    src_path = CAMERA_UPLOADS_PATH
    uploaded_images = [os.path.join(src_path, f) for f in os.listdir(src_path) if os.path.isfile(
        os.path.join(src_path, f)) and f.endswith(".jpg")]
    if len(uploaded_images) == 0:
        print(Colorise.blue(f"{SUBROUTINE_LOG_INDENTATION}No images or photos were found in the uploads folder."))
        return
    print(f"{SUBROUTINE_LOG_INDENTATION}Moving {len(uploaded_images)} images / videos found in the uploads folder")
    for img in uploaded_images:
        os.rename(img, os.path.join(FOLDER_UNSORTED_FULL_PATH, ntpath.basename(img)))


@print_current_task_name
@display_timing
def _TASK_move_old_exif_files():
    """ Generate EXIF files."""

    for exif_file_name in yield_pattern_matching_files_from_location(full_path_of(FOLDER_UNSORTED), "*._exif"):
        COUNTERS["MOVED_OLD_EXIFS"] += 1
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


@print_current_task_name
@display_timing
def _TASK_remove_empty_image_files():
    """Remove empty image files."""

    # This task needs to run before EXIF generation because probably empty files cause exiftool crash

    for image_file_name_with_path in yield_image_files_from_location(full_path_of(FOLDER_UNSORTED), include_paths=True):
        # image_file_name_only, image_file_extension = os.path.splitext(image_file_name_with_path)
        image_file_name = os.path.basename(image_file_name_with_path)
        if os.path.getsize(image_file_name_with_path) == 0:
            print((INDENT_SMALL + "Empty file: " + image_file_name))
            moved_empty_file_name_destination = os.path.join(
                FULL_PATH_SUBFOLDER["EMPTY_FILES"], image_file_name)
            try:
                os.rename(image_file_name_with_path,
                          moved_empty_file_name_destination)
                COUNTERS["PROBLEMATIC_FILES"] += 1
            except:
                print((INDENT_SMALL + "Problem when moving EMPTY image files"))
    # raw_input("Proceed? ")


@print_current_task_name
@display_timing
def _TASK_generate_exif_files():
    """ Generate EXIF files."""
    exiftool_output = "exiftool_output:NOT_POPULATED_YET"
    try:
        print((Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}======== EXIFTOOL: ======")))
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
            print(len(exiftool_output), exiftool_output)
        else:
            print(Colorise.blue(SUBROUTINE_LOG_INDENTATION + "( no exiftool report )"))
        print(Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}========================="))
    except:
        print(NEWLINE_AND_INDENT_1_TAB + "Some exiftool error happened!\n")
        with open(PATH_TO_REPORT, "w") as report_file:
            print(NEWLINE_AND_INDENT_1_TAB + "Report:" +
                  TWO_NEWLINES + report_file.read())
        raise ValueError(NEWLINE_AND_INDENT_1_TAB +
                         "Some exiftool error happened!\n" + str(exiftool_output))


@print_current_task_name
@display_timing
def _TASK_rename_exif_files():
    for exif_file_name in yield_exif_files_from_location(full_path_of(FOLDER_UNSORTED)):
        print(exif_file_name)


@print_current_task_name
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
            extraction_success = extract_data_from_exif_file_and_rename_original_image(
                exif_file_handler, image_file_name)
        if extraction_success:
            rename_exif_file(exif_file_name, image_file_name)
        else:
            # print("WARNING, will be problem with '.jpeg' (4-letter) extensions". probably solved)
            moved_exif_file_name = os.path.join(FULL_PATH_SUBFOLDER["NOT_ENOUGH_INFO"],
                                                os.path.splitext(image_file_name)[0] + EXIF_EXTENSION)
            try:
                os.rename(
                    exif_file_handler.name,
                    moved_exif_file_name
                )
            except:
                print((INDENT_SMALL + "Problem when moving EXIF files"))


@print_current_task_name
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


@print_current_task_name
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


@print_current_task_name
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


@print_current_task_name
@display_timing
def _TASK_launch_dpviewer():
    # if COUNTERS["ORIG_RAWS"] > 0:
    print((INDENT_SMALL + "Will launch DPViewer converter..."))
    subprocess.check_call(
        [
            PATH_TO_DPVIEWER,
            os.path.abspath(full_path_of(FOLDER_CR2_CONV))
        ]
    )
    # else:
    #     print(INDENT_SMALL + "No RAWs to process by DPViewer")


@print_current_task_name
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


@print_current_task_name
@display_timing
def _TASK_move_the_results():
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


@print_current_task_name
@display_timing
def _TASK_sort_the_resulting_folders():
    folder_sorter()


@print_current_task_name
@display_timing
def _TASK_show_stats():
    if COUNTERS["MOVED_OLD_EXIFS"] > 0:
        print((NEWLINE_AND_INDENT_1_TAB + "(Re)moved " +
               str(COUNTERS["MOVED_OLD_EXIFS"]) + " old EXIF files"))
    if COUNTERS["PROBLEMATIC_FILES"] > 0:
        print((NEWLINE_AND_INDENT_1_TAB +
               str(COUNTERS["PROBLEMATIC_FILES"]) + " problematic files"))
        redate_problematic_folder()
        redate_problematic_folder(False)
    if (COUNTERS["FAILS"] == COUNTERS["DUPLICATES"] == 0):
        print(f"{SUBROUTINE_LOG_INDENTATION}All OK!")
    else:
        show_issues_info()
    display_extra_messages()
    display_task_stats()


def main():
    print_header_footer()

    processing_start_time = time.time()
    _TASK_move_other_images()
    _TASK_get_photos_from_uploads_folder()
    _TASK_verify_if_folders_exist(FOLDERS_ALL)
    all_files_count = get_all_files_count()

    # print("Some tasks TEMPORARILY DISABLED, but should be ON!")

    generate_exifs = True
    # generate_exifs = ask_if_generate_exifs()
    _TASK_remove_empty_image_files()
    if generate_exifs:
        _TASK_move_old_exif_files()
        _TASK_generate_exif_files()
    # _TASK_rename_exif_files()  # only lists them atm. renaming actually takes place in the task below.
    # good idea to separate:
    _TASK_collect_info_from_EXIF_files()
    _TASK_rename_and_move_images_and_EXIF_files()
    _TASK_process_RAWs()
    _TASK_move_the_results()
    _TASK_sort_the_resulting_folders()
    _TASK_show_stats()

    display_total_time(processing_start_time, all_files_count)
    tada()

    print_header_footer()


if __name__ == "__main__":
    main()
    print(Colorise.yellow("\n\n\tTODO: Zaimplementowac licznik nienazwanych folderow i nowych, moze starych?"))
