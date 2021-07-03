
# path_to_exiftool_script = "_exiftool.bat"
exiftool_name = "exiftool"

path_to_irfanview = r"c:\_[SOFT] - Grafika\__Browsers, Viewers\IrfanView\i_view32.exe"
path_to_dpviewer = r"c:\Program Files (x86)\Canon\Digital Photo Professional\DPPViewer.exe"
testing_mode = True
testing_mode = False

if testing_mode:
    root_folder_path = "__TEST_folder"
else:
    root_folder_path = r"h:\__ Photos\____Photos to be sorted"
    # root_folder_path = r"v:\____Photos\nursery graduation photos"

# folder names
unsorted_folder = "____UNSORTED IMAGES"
problematic_folder = "__PROBLEMATIC"
problematic_old_EXIF_folder = "__PROBLEMATIC\old_EXIF"
ready_folder = "__READY"
CRW_conv_folder = "1. Original CRW"
orig_jpg_folder = "1. Original JPG"
orig_raw_folder = "1. Original RAW"
extracted_jpg_folder = "2. Extracted JPG"
timezone_corr_folder = "2. Ready for timezone correction"
sort_ready_folder = "3. Ready to be sorted"

UNSUP_EXT_subfolder_name = "##   UNSUPPORTED EXTENSIONS   ##"
INCOMPL_EXIF_subfolder_name = "##   INCOMPLETE EXIF   ##"
EMPTY_FILES_subfolder_name = "##   EMPTY FILES   ##"
NOT_ENOUGH_INFO_subfolder_name = "##   NOT_ENOUGH_INFO FILES   ##"
DUPLICATE_FILE_NAMES_subfolder_name = "##   DUPLICATE_FILE_NAMES FILES   ##"

RAW_subfolder_name = "##   RAWs   ##"
EXIF_subfolder_name = "##   EXIFs   ##"
ready_folder_decoration_string = ") - 1. ######"

result_folders = [CRW_conv_folder, orig_jpg_folder,
                  orig_raw_folder, sort_ready_folder, extracted_jpg_folder]

all_folders = result_folders + [unsorted_folder, problematic_folder,
                                ready_folder, timezone_corr_folder, problematic_old_EXIF_folder]


day_division_time = "04.44.44"


path_to_report = "RAPORT.txt"
raw_marker_str = "RAW__"


known_cameras_symbols = [

    ("Canon EOS 350D DIGITAL", "350D"),
    ("Canon EOS 650D", "650D"),
    ("Canon EOS 5D", "5D"),
    ("Canon EOS 5D Mark II", "5D2"),
    ("Canon EOS 5D Mark III", "5D3"),
    ("Canon EOS 5D Mark IV", "5D4"),
    ("Canon EOS 5DS", "5DS"),
    ("Canon EOS 6D", "6D"),
    ("Canon EOS 7D", "7D"),
    ("Canon PowerShot G6", "G6"),
    ("DSC-H50", "SH50"),
    ("DSC-HX7V", "SHX7"),
    ("E71", "NE71"),
    ("FinePix REAL 3D W3", "3DW3"),
    ("FinePix XP30", "XP30"),
    ("iDV", "3DAP"),
    ("GT-I9505", "S4"),
    ("HC-V700", "VID1"),
    ("iPhone 6", "iP6"),
    ("MX5", "MX5"),
    ("SM-N910F", "SGN4"),
    ("NIKON D300S", "ND300S"),
    ("NIKON D7000", "ND7K"),
    ("NIKON D700", "ND700"),
    ("NIKON D800", "ND800"),
    ("NIKON D5300", "ND5300"),
    ("ILCE-7", "ILC7"),
    ("ILCE-7R", "ILC7R"),
    ("SP-3000", "SP3K"),
    ("X-T2", "XT2"),
    ("Perfection V800/V850", "PRF8"),
    ("<KENOX S1050  / Samsung S1050>", "S1050"),
    ("DMC-FZ1000", "PF1K")
]

supported_image_extensions = [

    ".crw",
    ".cr2",
    ".dng",
    ".jpg",
    ".jpeg",
    ".thm",
    ".mpo"
]  # lowercase only

supported_non_image_extensions = [
    "._exif",
    ".txt_supported"
]  # lowercase only

raw_image_extensions = [

    ".crw",
    ".cr2",
    ".dng",
    ".mpo"
]

special_raw_image_extensions = [

    ".crw",
    ".mpo"
]
