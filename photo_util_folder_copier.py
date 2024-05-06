import os

from fnmatch import filter
from os.path import normpath
from shutil import copytree  # from distutils.dir_util import copy_tree

from constants import PHOTO_SELECTION_COPIER, PHOTO_BASE_FOLDER


class FolderCopier(object):

    def __init__(self, folder_paths, destination, folder_parser, copy_only_jpg=False):
        self.source_folder_paths = sorted(folder_paths)
        self.destination = destination
        self.copy_only_jpg = copy_only_jpg
        self.folders_to_copy = []
        self.folder_parser = folder_parser

    def collect_folders_to_copy(self):
        folders_to_copy = []
        for major_folder in self.source_folder_paths:
            fp = self.folder_parser(major_folder)
            print("\n    " + str(len(fp.folders_to_copy)) + " folder(s) to copy")
            folders_to_copy = folders_to_copy + fp.folders_to_copy
        self.folders_to_copy = folders_to_copy

    def copy_folders(self):
        for folder in self.folders_to_copy:
            print("  Copying: " + folder)
            # print folder.replace(PHOTO_BASE_FOLDER, "")
            # target_folder_name = os.path.basename(os.path.normpath(folder))
            target_folder_name = self.destination + \
                folder.replace(PHOTO_BASE_FOLDER, "")
            # print("target_folder_name: " + target_folder_name)
            # print self.destination
            # print normpath(self.destination)
            # destination_path = os.path.join(normpath(self.destination), normpath(target_folder_name))
            destination_path = normpath(target_folder_name)
            # print("destination_path: " + destination_path)
            # print("destination_path: " + normpath(destination_path))
            if not os.path.isdir(destination_path):
                copytree(folder, destination_path,
                         ignore=self.include_patterns(include_patterns=PHOTO_SELECTION_COPIER["PATTERNS_TO_INCLUDE"],
                                                      ignore_patterns=PHOTO_SELECTION_COPIER["PATTERNS_TO_IGNORE"]))
                print("   - OK")
            else:
                print("   - ignored (folder already exists)")

    def include_patterns(self, include_patterns, ignore_patterns):
        """Factory function that can be used with copytree() ignore parameter.

        Arguments define a sequence of glob-style patterns
        that are used to specify what files to NOT ignore.
        Creates and returns a function that determines this for each directory
        in the file hierarchy rooted at the source directory when used with
        shutil.copytree().
        # sample usage:
        copytree(src_directory, dst_directory, ignore=include_patterns('*.sldasm', '*.sldprt'))
        """
        # print "include_patterns:"
        # print include_patterns
        # print "ignore_patterns:"
        # print ignore_patterns
        def _ignore_patterns(path, names):
            # print("\npath:")
            # print(path)
            # print("names:")
            # print(names)
            keep = set(
                name for pattern in include_patterns for name in filter(names, pattern))
            # print("keep:")
            # print(keep)
            ignore = set(name for pattern in ignore_patterns for name in filter(
                names, pattern) if name not in keep)
            # ignore = set(name for pattern in ignore_patterns for name in names if (
            #     (name not in keep and not isdir(join(path, name)))
            #     or
            #     (name in ignore_patterns)
            #     ))
            # print("ignore:")
            # print(ignore)
            # for name in names:
            # print "1:", name
            # print " 2:", name in keep
            # print " 3:", not isdir(join(path, name))
            # print " 4:", name in ignore_patterns
            # print " 5:", filter(ignore_patterns, name)
            # print "6:", filter(names, ignore_patterns)
            return ignore
        return _ignore_patterns
