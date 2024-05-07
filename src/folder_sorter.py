import os
import re
import shutil
import winsound
import pandas as pd

from utils.colorise import Colorise
from constants.constants import READY_PHOTOS_SOURCE_FOLDER_FULL_PATH, PHOTO_BASE_FOLDER, MONTH_FOLDERS, \
    SUBROUTINE_LOG_INDENTATION


class ReadyPhotosFolderMover(object):
    def __init__(self, source_folder, destination_base_folder):
        self.source_folder = source_folder
        self.all_folders = next(os.walk(READY_PHOTOS_SOURCE_FOLDER_FULL_PATH))[1]
        # self.all_folders = os.walk(READY_PHOTOS_SOURCE_FOLDER_FULL_PATH).next()[1]
        self.folders_to_move = []
        self.folders_with_contents_to_move = []
        self.destination_base_folder = destination_base_folder
        self.total_folders = 0
        self.existing_folders = 0
        self.moved_folders = 0
        self.problematic_folders = 0
        self.sub_subfolders_counts = {}

    def get_subfolders(self):
        for folder_name in [x for x in os.listdir(self.source_folder) if
                            os.path.isdir(os.path.join(self.source_folder, x))]:
            self.total_folders += 1
            match = re.search(r'^(\d{4})-(\d{2})-(\d{2})\D.*', folder_name)
            if not match:
                match_year_folder = re.search(r'^(\d{4})$', folder_name)
                if not match_year_folder:
                    print(f"{SUBROUTINE_LOG_INDENTATION} — {folder_name} [ IGNORED ]")
                    self.problematic_folders += 1
                continue
            year = match.group(1)
            month = match.group(2)
            source_path = os.path.join(self.source_folder, folder_name)
            destination_path = os.path.join(
                self.destination_base_folder, year, MONTH_FOLDERS[month], folder_name)
            if not os.path.isdir(destination_path):
                marker = " folder "
                self.folders_to_move.append({
                    "source_path": source_path,
                    "destination_path": destination_path,
                })
            else:
                marker = "contents"
                # print("  WARNING! Destination folder: '" + destination_path + "' exists! Will only move contents")
                self.existing_folders += 1
                self.folders_with_contents_to_move.append({
                    "source_path": source_path,
                    "destination_path": destination_path,
                })
            print(f"{SUBROUTINE_LOG_INDENTATION} — {str(source_path)}   >>   {marker}   >>   {str(destination_path)}")

    def get_sub_subfolder_counts(self):
        for photo_folder in self.all_folders:
            sub_subfolders = next(os.walk(os.path.join(
                READY_PHOTOS_SOURCE_FOLDER_FULL_PATH, photo_folder)))[1]
            # sub_subfolders = os.walk(os.path.join(
            #     READY_PHOTOS_SOURCE_FOLDER_FULL_PATH, photo_folder)).next()[1]
            for folder in sub_subfolders:
                if folder not in list(self.sub_subfolders_counts.keys()):
                    self.sub_subfolders_counts[str(folder)] = 1
                current_value = self.sub_subfolders_counts[str(folder)]
                self.sub_subfolders_counts[str(
                    folder)] = current_value + 1 if current_value else 1

    def show_ready_folder_stats(self):
        counter = 0
        not_named = 0
        folders = self.all_folders
        print(Colorise.yellow(f"\n{SUBROUTINE_LOG_INDENTATION}READY folder contents:\n"))
        for folder in folders:
            counter += 1
            if "######" in folder:
                not_named += 1
        # print(("    - folders: " + str(counter)))
        # print(("    - renamed: " + str(counter - not_named)))
        # print(("    - not_named: " + str(not_named)))

        self.print_folder_naming_stats(counter, not_named)
        self.print_folder_lists()

        print(f"\n{SUBROUTINE_LOG_INDENTATION}— sub-subfolders: {str(len(list(self.sub_subfolders_counts.keys())))}")
        # print(self.sub_subfolders_counts)

    def print_folder_naming_stats(self, counter, not_named):
        folder_data = {
            f'{SUBROUTINE_LOG_INDENTATION}  [ ENTITY ]': ['', f'{SUBROUTINE_LOG_INDENTATION}— folders:  ', f'{SUBROUTINE_LOG_INDENTATION}— renamed:  ', f'{SUBROUTINE_LOG_INDENTATION}— to rename:'],
            '[ VALUE ]': ['', str(counter), str(counter - not_named), str(not_named)]
        }
        df = pd.DataFrame(folder_data)
        print(df.to_string(index=False))

    def print_folder_lists(self):
        print("")
        month_folder_data = {
            f'{SUBROUTINE_LOG_INDENTATION}[ FOLDER NAME ]': [''],
            '[ COUNT ]': ['']
        }
        for folder_name in list(self.sub_subfolders_counts.keys()):
            # print(("\t\t" + folder_name + ":    \t" +
            #        str(self.sub_subfolders_counts[folder_name])))
            month_folder_data[f'{SUBROUTINE_LOG_INDENTATION}[ FOLDER NAME ]'].append(folder_name.ljust(14, " "))
            month_folder_data['[ COUNT ]'].append(str(self.sub_subfolders_counts[folder_name]))
        df = pd.DataFrame(month_folder_data)
        print(df.to_string(index=False))

    def move_folders(self):
        for folder in self.folders_to_move:
            if not os.path.isdir(folder["destination_path"]):
                print((folder["source_path"], folder["destination_path"]))
                shutil.move(folder["source_path"], folder["destination_path"])
                self.moved_folders += 1
                '''
                shutil.move(src, dst)
                Recursively move a file or directory (src) to another location (dst).

                If the destination is an existing directory, then src is moved inside that directory.
                If the destination already exists but is not a directory, it may be overwritten depending on os.rename() semantics.

                If the destination is on the current filesystem, then os.rename() is used.
                Otherwise, src is copied (using shutil.copy2()) to dst and then removed.

                New in version 2.3.

                exception shutil.Error
                This exception collects exceptions that are raised during a multi-file operation. For copytree(),
                the exception argument is a list of 3-tuples (srcname, dstname, exception).
                '''
            else:
                print(("  WARNING_2! Destination folder: '" +
                       folder["source_path"] + "' exists! Will not move it"))

    def move_individual_files(self):
        for folder in self.folders_with_contents_to_move:
            source_path = folder["source_path"]
            destination_path = folder["destination_path"]
            for root, dirs, files in os.walk(source_path):
                for file in files:
                    self.move_file(destination_path, file, root, source_path)
                # level = root.replace(folder, '').count(os.sep)
                # indent = '\t' * 1 * (level)
                # output_string = '{}{}/'.format(indent, os.path.basename(root))
                # print(output_string)
                # f_output.write(output_string + '\n')
                # subindent = '\t' * 1 * (level + 1)
                # output_string = '{}{}'.format(subindent, f)
                # print(output_string)
                # f_output.write(output_string + '\n')

    def move_file(self, destination_path, file, root, source_path):
        source_file_path = os.path.join(root, file)
        dest_file_path = source_file_path.replace(
            source_path, destination_path)
        print(("\n source_file_path:  " + source_file_path))
        print(("   dest_file_path:  " + dest_file_path))
        # dest_file_path = os.path.join(destination_path, file)
        if os.path.isfile(dest_file_path):
            print("     Already exists!")
        else:
            self.move_file_safely(dest_file_path, source_file_path)

    def move_file_safely(self, dest_file_path, source_file_path):
        dest_dir = os.path.dirname(dest_file_path)
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)
        os.rename(source_file_path, dest_file_path)

    def print_stats(self):
        print(Colorise.yellow(f"\n{SUBROUTINE_LOG_INDENTATION}Folders counts:"))
        print(Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}         Total:    ") + str(self.total_folders))
        print(Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}      Existing:    ") + str(self.existing_folders))
        print(Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}         Moved:    ") + str(self.moved_folders))
        print(Colorise.yellow(f"{SUBROUTINE_LOG_INDENTATION}   Problematic:    ") + str(self.problematic_folders))


def folder_sorter():
    src_path = READY_PHOTOS_SOURCE_FOLDER_FULL_PATH
    # src_path = "\\\\MMHH_Serv_1/PHOTO_BACKUP_2/SORTING_TEST"
    # src_path = "\\\\MMHH_Serv_1/PHOTO_BACKUP_2/__PHOTOS__SOURCE/__UNSORTED"

    # dest_base_folder = PHOTO_BASE_FOLDER  # perhaps the ideal location
    # dest_base_folder = "\\\\MMHH_Serv_1/PHOTO_BACKUP_2/SORTING_TEST"
    dest_base_folder = src_path

    # print(f"                     PHOTO_BASE_FOLDER:    {PHOTO_BASE_FOLDER}")
    print(Colorise.blue(f"{SUBROUTINE_LOG_INDENTATION}READY_PHOTOS_SOURCE_FOLDER_FULL_PATH:   {READY_PHOTOS_SOURCE_FOLDER_FULL_PATH}"))
    print(Colorise.blue(f"{SUBROUTINE_LOG_INDENTATION}                            src_path:   {src_path}"))
    print(Colorise.blue(f"{SUBROUTINE_LOG_INDENTATION}                    dest_base_folder:   {dest_base_folder}"))

    assert os.path.exists(src_path), "src_path: does not exist!"
    assert os.access(src_path, os.R_OK), "src_path: is not accessible!"
    assert os.path.exists(dest_base_folder), "dest_base_folder: does not exists!"
    assert os.access(dest_base_folder, os.R_OK), "dest_base_folder: is not accessible!"

    # answer = input(Colorise.yellow(
    #     "\n\tDo you want to proceed? (y/n): "))
    # if answer != "y":
    #     print("\n Quit\n")
    #     exit(0)

    print(Colorise.yellow(f"\n{SUBROUTINE_LOG_INDENTATION}Folders to move:\n"))
    folder_mover = ReadyPhotosFolderMover(
        source_folder=src_path, destination_base_folder=dest_base_folder)
    folder_mover.get_subfolders()
    folder_mover.get_sub_subfolder_counts()
    folder_mover.show_ready_folder_stats()

    winsound.Beep(4444, 444)
    print(f"\n\n{SUBROUTINE_LOG_INDENTATION}{str(len(folder_mover.folders_to_move))} folders to move")
    print(f"{SUBROUTINE_LOG_INDENTATION}{str(len(folder_mover.folders_with_contents_to_move))} folders with contents to move")
    # while True:
    #     answer = input(Colorise.red("\n\tDo you want to move files and folders? (y/n): "))
    #     if answer == "y" or answer == "n":
    #         break
    # if answer == "y":
    print(Colorise.yellow(f"\n{SUBROUTINE_LOG_INDENTATION}Moving:\n"))
    folder_mover.move_folders()
    folder_mover.move_individual_files()
    folder_mover.print_stats()


if __name__ == '__main__':
    folder_sorter()
