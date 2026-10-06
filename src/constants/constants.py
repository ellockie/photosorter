import os
from os.path import join

assert (
    "PHOTO_BASE_FOLDER" in os.environ
    and os.environ["PHOTO_BASE_FOLDER"]
    and os.environ["PHOTO_BASE_FOLDER"] != ""
), "'PHOTO_BASE_FOLDER' environment variable is missing.\
    Set it with SETX ('https://ss64.com/nt/setx.html')"


# path_to_exiftool_script = "_exiftool.bat"
EXIFTOOL_NAME = "exiftool"

PATH_TO_IRFANVIEW = os.path.normpath(
    r"c:\_[SOFT] - Grafika\__Browsers, Viewers\IrfanView\i_view32.exe"
)
PATH_TO_DPVIEWER = os.path.normpath(
    r"c:\Program Files (x86)\Canon\Digital Photo Professional\DPPViewer.exe"
)
PATH_TO_SONY_CONVERTER = os.path.normpath(
    r"c:\Program Files\Sony\Imaging Edge Desktop\ied.exe"
)
TESTING_MODE = False

# folder names
PHOTO_BASE_FOLDER = os.environ["PHOTO_BASE_FOLDER"]

CAMERA_UPLOADS_PATH = os.path.normpath("c:/Users/luxxa/Dropbox/Camera Uploads")
FOLDER_TO_BE_SORTED = "____TO_SORT"
FOLDER_TO_BE_SORTED_FULL_PATH = join(PHOTO_BASE_FOLDER, FOLDER_TO_BE_SORTED)
PATHS = {
    "ROOT_FOLDER": FOLDER_TO_BE_SORTED_FULL_PATH,
}
if TESTING_MODE:
    PATHS["ROOT_FOLDER"] = "__TEST_folder"
FOLDER_UNSORTED = "____UNSORTED"
FOLDER_UNSORTED_FULL_PATH = join(PATHS["ROOT_FOLDER"], FOLDER_UNSORTED)
FOLDER_PROBLEMATIC = "__PROBLEMATIC"
FOLDER_PROBLEMATIC_OLD_EXIF = join("__PROBLEMATIC", "old_EXIF")
FOLDER_READY = "__READY"
READY_PHOTOS_SOURCE_FOLDER_FULL_PATH = join(
    PHOTO_BASE_FOLDER, FOLDER_TO_BE_SORTED, FOLDER_READY
)
FOLDER_ORGANISER_WORKING_FOLDER = join(
    READY_PHOTOS_SOURCE_FOLDER_FULL_PATH, "___WORKING_FOLDER"
)

# FOLDER_ORIG_RAW = "1. Original RAW"
FOLDER_CR2_CONV = "1. Original RAW_CR2"
FOLDER_CRW_CONV = "1. Original RAW_CRW"
FOLDER_MPO_CONV = "1. Original RAW_MPO"
FOLDER_ARW_CONV = "1. Original RAW_ARW"
FOLDER_RW2_CONV = "1. Original RAW_RW2"
FOLDER_DNG_CONV = "1. Original RAW_DNG"

FOLDER_ORIG_JPG = "1. Original JPG"

FOLDER_EXTRACTED_JPG = "2. Extracted JPG"
FOLDER_TIMEZONE_CORR = "2. Ready for timezone correction"
FOLDER_SORT_READY = "3. Ready to be sorted"

FOLDERS_RAW = [
    FOLDER_CR2_CONV,
    FOLDER_CRW_CONV,
    FOLDER_MPO_CONV,
    FOLDER_ARW_CONV,
    FOLDER_RW2_CONV,
    FOLDER_DNG_CONV,
]
FOLDERS_RESULT = FOLDERS_RAW + [
    FOLDER_ORIG_JPG,
    FOLDER_SORT_READY,
    FOLDER_EXTRACTED_JPG,
]
FOLDERS_ALL = FOLDERS_RESULT + [
    FOLDER_UNSORTED,
    FOLDER_PROBLEMATIC,
    FOLDER_READY,
    FOLDER_TIMEZONE_CORR,
    FOLDER_PROBLEMATIC_OLD_EXIF,
]

# Problematic subfolders
SUBFOLDER_UNSUPPORTED_EXT = "##   UNSUPPORTED EXTENSIONS   ##"
SUBFOLDER_EMPTY_FILES = "##   EMPTY FILES   ##"
SUBFOLDER_NOT_ENOUGH_INFO = "##   NOT_ENOUGH_INFO FILES   ##"
SUBFOLDER_DUPLICATE_FILE_NAMES = "##   DUPLICATE_FILE_NAMES FILES   ##"
# Unused?
SUBFOLDER_INCOMPL_EXIF = "##   INCOMPLETE EXIF   ##"

SUBFOLDER_NAMES = {
    "RAW": "##   RAWs   ##",
    "EXIF": "##   EXIFs   ##",
    "META": "[==   meta   ==]",
}
READY_FOLDER_DECORATION_STRING = ") - 1. ######"

DAY_DIVISION_TIME = "04.44.44"
PATH_TO_REPORT = "REPORT.txt"
RAW_MARKER_STR = "RAW__"
# The table lives in a leaf module so tools can read it (T8); re-exported here.
from src.constants.camera_symbols import KNOWN_CAMERAS_SYMBOLS  # noqa: E402,F401
MY_CAMERA_SYMBOLS = [
    "Canon PowerShot G6",
    "FC7303",
    "Galaxy S23 Ultra",
    "ILCE-5000",
    "ILCE-7RM2",
    "ILCE-7RM5",
    "SM-G965F",
    "SM-S9080",
]

EXTENSION_RAW_ARW = ".arw"
EXTENSION_RAW_CR2 = ".cr2"
EXTENSION_RAW_CRW = ".crw"
EXTENSION_RAW_DNG = ".dng"
EXTENSION_RAW_MPO = ".mpo"
EXTENSION_RAW_RW2 = ".rw2"

# lowercase only
EXTENSIONS_RAW_IMAGES = [
    EXTENSION_RAW_ARW,
    EXTENSION_RAW_CR2,
    EXTENSION_RAW_CRW,
    EXTENSION_RAW_DNG,
    EXTENSION_RAW_MPO,
    EXTENSION_RAW_RW2,
]
# lowercase only
EXTENSIONS_SPECIAL_RAW_IMAGES = [
    EXTENSION_RAW_CRW,
    EXTENSION_RAW_RW2,
    EXTENSION_RAW_MPO,
]
# lowercase only
EXTENSIONS_LOSSY_IMAGES = [
    ".jpg",
    ".jpeg",
    ".thm",
]
EXTENSIONS_SUPPORTED_IMAGES = EXTENSIONS_LOSSY_IMAGES + EXTENSIONS_RAW_IMAGES
EXIF_EXTENSION = "._exif"
# lowercase only
EXTENSIONS_SUPPORTED_NON_IMAGES = [EXIF_EXTENSION, ".txt_supported"]
RAW_EXTENSIONS__FOLDERS_MAP = {
    EXTENSION_RAW_ARW: FOLDER_ARW_CONV,
    EXTENSION_RAW_CRW: FOLDER_CRW_CONV,
    EXTENSION_RAW_CR2: FOLDER_CR2_CONV,
    EXTENSION_RAW_DNG: FOLDER_DNG_CONV,
    EXTENSION_RAW_MPO: FOLDER_MPO_CONV,
    EXTENSION_RAW_RW2: FOLDER_RW2_CONV,
}
PHOTO_SELECTION_COPIER = {
    "DESTINATION_LOCATION": "z:\\__shared_photos",
    "PATTERNS_TO_INCLUDE": [r"*.jpg", r"*.JPG"],
    "PATTERNS_TO_IGNORE": list(SUBFOLDER_NAMES.values())
    + [r"*__RAW", r"*\.cr2", r"*\.CR2"]
    + EXTENSIONS_RAW_IMAGES,
    "SHAREABLE_FOLDER_MARKER_FILE_NAME": "marker_ok_to_share",
    "SOURCE_PHOTO_FOLDER_PATHS": [
        PHOTO_BASE_FOLDER + r"\\2012\\",
        PHOTO_BASE_FOLDER + r"\\2013\\",
        PHOTO_BASE_FOLDER + r"\\2014\\",
        PHOTO_BASE_FOLDER + r"\\2015\\",
        PHOTO_BASE_FOLDER + r"\\2016\\",
        PHOTO_BASE_FOLDER + r"\\2017\\",
        PHOTO_BASE_FOLDER + r"\\2018\\",
    ],
}

# Month folder names live in one place (ARCHIVE_STANDARD.md P3/T8);
# re-exported here so the legacy CLI keeps importing them from where it
# always has.
from .months import MONTH_FOLDERS  # noqa: F401  (re-export)

INDENT_VERY_SMALL = "         "
INDENT_SMALL = "             "
INDENT_1_TAB = "\t"
INDENT_2_TABS = "\t\t"
NEWLINE_AND_INDENT_1_TAB = "\n\t"
NEWLINE_AND_INDENT_2_TABS = "\n\t\t"
TWO_NEWLINES = "\n\n"
SUBROUTINE_LOG_INDENTATION = " " * 20
pattern_name = "*.*"
crw_pattern = "*.CRW"
COMMAND_LINE_OPTION_GENERATE_EXIFS = "generate-exifs"
