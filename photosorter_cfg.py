import os
from os.path import join
from photosorter import full_path_of

assert "PHOTO_BASE_FOLDER" in os.environ \
    and os.environ["PHOTO_BASE_FOLDER"] \
    and os.environ["PHOTO_BASE_FOLDER"] != "", \
    "'PHOTO_BASE_FOLDER' environment variable is missing.\
    Set it with SETX ('https://ss64.com/nt/setx.html')"


# path_to_exiftool_script = "_exiftool.bat"
EXIFTOOL_NAME = "exiftool"

PATH_TO_IRFANVIEW = r"c:\_[SOFT] - Grafika\__Browsers, Viewers\IrfanView\i_view32.exe"
PATH_TO_DPVIEWER = r"c:\Program Files (x86)\Canon\Digital Photo Professional\DPPViewer.exe"
# PATH_TO_SONY_CONVERTER = r"f:\_[SOFT] - Grafika\__Cameras\Sony\Viewer.exe"
PATH_TO_SONY_CONVERTER = r"C:\Program Files\Sony\Imaging Edge\Viewer.exe"
TESTING_MODE = False

# folder names
PHOTO_BASE_FOLDER = os.environ['PHOTO_BASE_FOLDER']
FOLDER_TO_BE_SORTED = "____TO_SORT"
FOLDER_TO_BE_SORTED_FULL_PATH = join(PHOTO_BASE_FOLDER, FOLDER_TO_BE_SORTED)
if TESTING_MODE:
    ROOT_FOLDER_PATH = "__TEST_folder"
else:
    ROOT_FOLDER_PATH = FOLDER_TO_BE_SORTED_FULL_PATH
FOLDER_UNSORTED = "____UNSORTED"
FOLDER_PROBLEMATIC = "__PROBLEMATIC"
FOLDER_PROBLEMATIC_OLD_EXIF = join("__PROBLEMATIC", "old_EXIF")
FOLDER_READY = "__READY"
READY_PHOTOS_SOURCE_FOLDER_FULL_PATH = join(
    PHOTO_BASE_FOLDER, FOLDER_TO_BE_SORTED, FOLDER_READY)
FOLDER_ORGANISER_WORKING_FOLDER = join(
    READY_PHOTOS_SOURCE_FOLDER_FULL_PATH, "___WORKING_FOLDER")

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

FOLDERS_RAW = [FOLDER_CR2_CONV, FOLDER_CRW_CONV, FOLDER_MPO_CONV,
               FOLDER_ARW_CONV, FOLDER_RW2_CONV, FOLDER_DNG_CONV]
FOLDERS_RESULT = FOLDERS_RAW + [FOLDER_ORIG_JPG,
                                FOLDER_SORT_READY, FOLDER_EXTRACTED_JPG]
FOLDERS_ALL = FOLDERS_RESULT + [FOLDER_UNSORTED, FOLDER_PROBLEMATIC, FOLDER_READY, FOLDER_TIMEZONE_CORR,
                                FOLDER_PROBLEMATIC_OLD_EXIF, full_path_of(FOLDER_UNSORTED)]

# Problematic subfolders
SUBFOLDER_UNSUP_EXT = "##   UNSUPPORTED EXTENSIONS   ##"
SUBFOLDER_EMPTY_FILES = "##   EMPTY FILES   ##"
SUBFOLDER_NOT_ENOUGH_INFO = "##   NOT_ENOUGH_INFO FILES   ##"
SUBFOLDER_DUPLICATE_FILE_NAMES = "##   DUPLICATE_FILE_NAMES FILES   ##"
# Unused?
SUBFOLDER_INCOMPL_EXIF = "##   INCOMPLETE EXIF   ##"

SUBFOLDER_NAMES = {
    "RAW":  "##   RAWs   ##",
    "EXIF": "##   EXIFs   ##",
    "META": "[==   meta   ==]"
}
READY_FOLDER_DECORATION_STRING = ") - 1. ######"

FOLDERS_TO_CREATE = []

DAY_DIVISION_TIME = "04.44.44"
PATH_TO_REPORT = "RAPORT.txt"
RAW_MARKER_STR = "RAW__"
KNOWN_CAMERAS_SYMBOLS = [
    ("", "NOID"),
    ("<KENOX S1050  / Samsung S1050>", "S1050"),
    ("Canon EOS 1000D", "1000D"),
    ("Canon EOS 100D", "100D"),
    ("Canon EOS 100D", "100D"),
    ("Canon EOS 1100D", "1100D"),
    ("Canon EOS 350D DIGITAL", "350D"),
    ("Canon EOS 400D DIGITAL", "400D"),
    ("Canon EOS 40D", "40D"),
    ("Canon EOS 450D", "450D"),
    ("Canon EOS 500D", "500D"),
    ("Canon EOS 50D", "50D"),
    ("Canon EOS 550D", "550D"),
    ("Canon EOS 550D", "550D"),
    ("Canon EOS 5D Mark II", "5D2"),
    ("Canon EOS 5D Mark III", "5D3"),
    ("Canon EOS 5D Mark IV", "5D4"),
    ("Canon EOS 5D", "5D"),
    ("Canon EOS 5DS R", "5DSR"),
    ("Canon EOS 5DS", "5DS"),
    ("Canon EOS 600D", "600D"),
    ("Canon EOS 60D", "60D"),
    ("Canon EOS 650D", "650D"),
    ("Canon EOS 6D", "6D"),
    ("Canon EOS 70D", "70D"),
    ("Canon EOS 7D Mark II", "7D2"),
    ("Canon EOS 7D", "7D"),
    ("Canon EOS Kiss X7", "CKISX7"),
    ("Canon EOS Kiss X7", "CKISX7"),
    ("Canon EOS Kiss X7", "CKISX7"),
    ("Canon EOS M", "CM"),
    ("Canon EOS M", "CM"),
    ("Canon EOS M", "CM"),
    ("Canon EOS REBEL T1i", "REBT1i"),
    ("Canon EOS REBEL T2i", "REBT2i"),
    ("Canon EOS REBEL T3i", "REBT3i"),
    ("Canon EOS REBEL T3i", "REBT3i"),
    ("Canon EOS REBEL T4i", "REBT4i"),
    ("Canon EOS-1D Mark IV", "1DIV"),
    ("Canon EOS-1D X", "1DX"),
    ("Canon EOS-1D X", "1DX"),
    ("Canon EOS-1Ds Mark III", "1DsIII"),
    ("Canon PowerShot G1 X Mark II", "G1XII"),
    ("Canon PowerShot G6", "G6"),
    ("COOLPIX L840", "NCPL840"),
    ("COOLPIX L840", "NCPL840"),
    ("COOLPIX S9100", "NCPS91k"),
    ("DMC-FZ1000", "PF1K"),
    ("DMC-GF1", "PGF1"),
    ("DMC-GH3", "PGH3"),
    ("DSC-H50", "SH50"),
    ("DSC-HX7V", "SHX7"),
    ("DSC-RX100M2", "SRX1002"),
    ("DSC-RX100M2", "SRX1002"),
    ("E-M1", "EM1"),
    ("E-M5", "EM5"),
    ("E71", "NE71"),
    ("EZ Controller", "EZCtrl"),
    ("EZ Controller", "EZCtrl"),
    ("FC300X", "FC300X"),
    ("FinePix F770EXR", "FPF770"),
    ("FinePix REAL 3D W3", "3DW3"),
    ("FinePix XP30", "XP30"),
    ("GT-I5500", "SG5"),
    ("GT-I9505", "S4"),
    ("HC-V700", "VID1"),
    ("Hipsteroku", "HPR"),
    ("iDV", "3DAP"),
    ("ILCA-77M2", "ILCA-77M2"),
    ("ILCE-6000", "ILC6K"),
    ("ILCE-7", "ILC7"),
    ("ILCE-7M2", "ILC7M2"),
    ("ILCE-7R", "ILC7R"),
    ("ILCE-7RM2", "ILC7R2"),
    ("iPhone 4s", "iP4s"),
    ("iPhone 5", "iP5"),
    ("iPhone 5s", "iP5s"),
    ("iPhone 6", "iP6"),
    ("IQ260", "IQ260"),
    ("KODAK EASYSHARE C533 ZOOM DIGITAL CAMERA", "KDC533"),
    ("KODAK Z740 ZOOM DIGITAL CAMERA", "KDZ740"),
    ("LEICA M (Typ 240)", "LEIM"),
    ("Long Exposure Camera2", "LEC2"),
    ("MX5", "MX5"),
    ("NEX-3N", "NX3N"),
    ("NEX-5N", "NX5N"),
    ("NEX-5T", "NX5T"),
    ("NIKON 1 S1", "N1S1"),
    ("Nikon COOLSCAN V ED", "NCSV"),
    ("NIKON D3", "ND3"),
    ("NIKON D300", "ND300"),
    ("NIKON D300S", "ND300S"),
    ("NIKON D3100", "ND3100"),
    ("NIKON D3200", "ND3200"),
    ("NIKON D3300", "ND3300"),
    ("NIKON D3S", "ND3S"),
    ("NIKON D4", "ND4"),
    ("NIKON D40X", "ND40X"),
    ("NIKON D40X", "ND40X"),
    ("NIKON D4S", "ND4S"),
    ("NIKON D5100", "ND5100"),
    ("NIKON D5200", "ND5200"),
    ("NIKON D5300", "ND5300"),
    ("NIKON D5500", "ND5500"),
    ("NIKON D60", "ND60"),
    ("NIKON D600", "ND600"),
    ("NIKON D610", "ND610"),
    ("NIKON D700", "ND700"),
    ("NIKON D7000", "ND7K"),
    ("NIKON D7100", "ND7100"),
    ("NIKON D7200", "ND7200"),
    ("NIKON D750", "ND750"),
    ("NIKON D800", "ND800"),
    ("NIKON D800E", "ND800E"),
    ("NIKON D810", "ND810"),
    ("NIKON D90", "ND90"),
    ("NX30", "NX30"),
    ("PENTAX K-3 II", "PTK32"),
    ("PENTAX K-3", "PTK3"),
    ("PENTAX K-3", "PTK3"),
    ("PENTAX K-30", "PTK30"),
    ("PENTAX K-5 II s", "PTK5IIs"),
    ("PENTAX K-5", "PTK5"),
    ("Perfection V800/V850", "PRF8"),
    ("SIGMA dp1 Quattro", "Sdp14"),
    ("SLT-A58", "SLTA58"),
    ("SLT-A65V", "SLTA65V"),
    ("SLT-A77V", "SLTA77V"),
    ("SM-N910F", "SGN4"),
    ("SM-G965F", "SG9"),
    ("SM-T520", "SGTab10"),
    ("SP-3000", "SP3K"),
    ("SZ-10", "SZ10"),
    ("SZ-10", "SZ10"),
    ("Vignette for Android", "V4A"),
    ("VLUU L310W L313 M310W / Samsung L310W L313 M310W", "SLM31"),
    ("X-E1", "XE1"),
    ("X-E2", "XE2"),
    ("X-Pro1", "XPro1"),
    ("X-T1", "XT1"),
    ("X-T2", "XT2"),
    ("X100F", "X100F"),
    ("X100S", "X100S"),
    ("XT1095", "XT1095"),
]
MY_CAMERAS_SYMBOLS = [
    "ILCE-7RM2",
    "Canon PowerShot G6"
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
EXTENSIONS_SUPPORTED_NON_IMAGES = [
    EXIF_EXTENSION,
    ".txt_supported"
]
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
    "PATTERNS_TO_IGNORE": list(SUBFOLDER_NAMES.values()) + [r"*__RAW", r"*\.cr2", r"*\.CR2"] + EXTENSIONS_RAW_IMAGES,
    "SHAREABLE_FOLDER_MARKER_FILE_NAME": "marker_ok_to_share",
    "SOURCE_PHOTO_FOLDER_PATHS": [
        PHOTO_BASE_FOLDER + r"\\2012\\",
        PHOTO_BASE_FOLDER + r"\\2013\\",
        PHOTO_BASE_FOLDER + r"\\2014\\",
        PHOTO_BASE_FOLDER + r"\\2015\\",
        PHOTO_BASE_FOLDER + r"\\2016\\",
        PHOTO_BASE_FOLDER + r"\\2017\\",
        PHOTO_BASE_FOLDER + r"\\2018\\",
    ]
}

MONTH_FOLDERS = {
    "01": "01. January",
    "02": "02. February",
    "03": "03. March",
    "04": "04. April",
    "05": "05. May",
    "06": "06. June",
    "07": "07. July",
    "08": "08. August",
    "09": "09. September",
    "10": "10. October",
    "11": "11. November",
    "12": "12. December"
}

INDENT_VERY_SMALL = "         "
INDENT_SMALL = "             "
INDENT_1_TAB = "\t"
INDENT_2_TABS = "\t\t"
NEWLINE_AND_INDENT_1_TAB = "\n\t"
NEWLINE_AND_INDENT_2_TABS = "\n\t\t"
TWO_NEWLINES = "\n\n"
