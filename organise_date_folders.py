import os

from src.constants.constants import READY_PHOTOS_SOURCE_FOLDER_FULL_PATH, PHOTO_BASE_FOLDER, MONTH_FOLDERS, FOLDER_ORGANISER_WORKING_FOLDER
# from folder_sorter import ReadyPhotosFolderMover
from main import create_folders_subfolder


WORKING_FOLDER = "___WORKING_FOLDER"
TEST_DATE = "2018-10-01"
TEST_DATE = "2013-07-23"

print(READY_PHOTOS_SOURCE_FOLDER_FULL_PATH)
print(PHOTO_BASE_FOLDER)

def get_photo_monthly_folder_path(date_str):
    validate_date_format(date_str)
    year = date_str[0:4]
    month = date_str.split("-")[1]
    month_folder = MONTH_FOLDERS[month]
    return os.path.join(PHOTO_BASE_FOLDER, year, month_folder)

def validate_date_format(date_str):
    import re
    assert type(date_str) == str, "date is not a string: %r" % date_str
    assert re.compile("^\d{4}(-\d{2}){2}$").match(date_str), "date string should match the pattern ^\d{4}(-\d{2}){2}$ , but was: %r" % date_str

def get_matching_folders(parent_folder):
    matching_date_folders = []
    for folder_name in os.listdir(parent_folder):
        if folder_name.startswith(TEST_DATE):
            print(folder_name)
            matching_date_folders.append(os.path.join(parent_folder,folder_name))
    return matching_date_folders

def create_folder_if_not_exist(target_folder):
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)

def main():
    parent_folder_path = get_photo_monthly_folder_path(TEST_DATE)
    matching_ready_folders = get_matching_folders(parent_folder_path)
    create_folders_subfolder()
    for folder in matching_ready_folders:
        print(folder, FOLDER_ORGANISER_WORKING_FOLDER)
        print("Further code commented out")
        continue
        # # TODO: check if it should be inversed
        # if not os.path.isdir(destination_path):
        #     marker = " folder "
        #     self.folders_to_move.append({
        #         "source_path": source_path,
        #         "destination_path": destination_path,
        #     })
        # else:
        #     print FOLDER_ORGANISER_WORKING_FOLDER

main()
