import os

from photosorter_cfg import SUBFOLDER_NAMES, PHOTO_SELECTION_COPIER


class FolderParser(object):
    def __init__(self, folder):
        print("\n Major folder:  " + folder + "\n")
        self.folder = folder
        self.subfolders = self.get_subfolders()
        self.metafolders = self.create_metafolders()
        self.folders_to_copy = self.get_folders_to_copy()

    def get_subfolders(self):
        counter = 0
        unnamed = 0
        subfolders = []
        for month_folder in [x for x in os.listdir(self.folder) if os.path.isdir(os.path.join(self.folder, x))]:
            counter += 1
            print("    " + month_folder + ":")
            subfolders, counter = self.parse_folder_contents(
                subfolders, month_folder, counter, unnamed)
        print("\n    folders: " + str(counter) + ":")
        print("     - renamed: " + str(counter - unnamed))
        print("     - not renamed: " + str(unnamed) + "\n")
        return subfolders

    def parse_folder_contents(self, subfolders, month_folder, counter, unnamed):
        for folder in os.listdir(os.path.join(self.folder, month_folder)):
            folder_path = os.path.join(self.folder, month_folder, folder)
            if os.path.isdir(folder_path):
                subfolders.append(folder_path)
                if "######" in folder:
                    unnamed += 1
                    print("\t" + folder)
                else:
                    print("\talready renamed: " + folder)
        return subfolders, counter

    def create_metafolders(self):
        metafolders = []
        for folder in self.subfolders:
            meta_path = os.path.join(folder, SUBFOLDER_NAMES["META"])
            if not os.path.isdir(meta_path):
                os.mkdir(meta_path)
                print("\t\t" + SUBFOLDER_NAMES["META"] + " folder created")
            metafolders.append(meta_path)
        return metafolders

    def get_folders_to_copy(self):
        folders_to_copy = []
        for metafolder in self.metafolders:
            copy_marker_path = os.path.join(
                metafolder, PHOTO_SELECTION_COPIER["SHAREABLE_FOLDER_MARKER_FILE_NAME"])
            if os.path.isfile(copy_marker_path):
                folders_to_copy.append(os.path.dirname(metafolder))
                print("\tWill copy: " + copy_marker_path)
        return folders_to_copy
