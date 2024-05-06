import os
from src.constants.constants import FOLDER_READY, FOLDER_TO_BE_SORTED_FULL_PATH

root_folder_path = os.path.join(
    FOLDER_TO_BE_SORTED_FULL_PATH, "__READY", "2018-05-19_(Sat) - 1. ######")


def full_path_of(folder_name):
    return os.path.join(root_folder_path, folder_name)


def show_ready_folder_stats():
    counter = 0
    unnamed = 0
    folder_path = full_path_of(FOLDER_READY)
    print "WRONG PATH:", folder_path
    folders = os.walk(folder_path).next()[1]
    for folder in folders:
        counter += 1
        if "######" in folder:
            unnamed += 1
            # print folder
        else:
            print "  already renamed: ", folder
    print "\n", counter, "folders"
    print "renamed:", counter - unnamed
    print "unnamed:", unnamed


def main():
    show_ready_folder_stats()


if __name__ == '__main__':
    main()
