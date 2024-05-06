from constants.constants import PHOTO_SELECTION_COPIER
from photo_util_folder_copier import FolderCopier
from photo_util_folder_parser import FolderParser


def main():
    """Copy folders with a marker_ok_to_share marker in their .meta folder to the shared location"""

    print("\n ======= Parsing: =======\n")
    folder_copier = FolderCopier(folder_paths=PHOTO_SELECTION_COPIER["SOURCE_PHOTO_FOLDER_PATHS"],
                                 destination=PHOTO_SELECTION_COPIER["DESTINATION_LOCATION"],
                                 folder_parser=FolderParser,
                                 copy_only_jpg=True)
    folder_copier.collect_folders_to_copy()
    print("\n ======= Copying: =======\n")
    folder_copier.copy_folders()


if __name__ == '__main__':
    main()
