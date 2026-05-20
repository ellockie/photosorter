
# path_to_exiftool_script = "_exiftool.bat"
exiftool_name = "exiftool"

path_to_irfanview = r"c:\_[SOFT] - Grafika\__Browsers, Viewers\IrfanView\i_view32.exe"
path_to_dpviewer = r"c:\Program Files (x86)\Canon\Digital Photo Professional\DPPViewer.exe"
testing_mode = False
testing_mode = True

if testing_mode:
	root_folder_path = "__TEST_folder"
else:
	root_folder_path = r"h:\__ Photos\____Photos to be sorted"
	# root_folder_path = r"v:\____Photos\nursery graduation photos"

# folder names
unsorted_folder =		"__UNSORTED IMAGES"
problematic_folder =	"__PROBLEMATIC"
ready_folder =			"__READY"
CRW_conv_folder =		"1. Original CRW"
orig_jpg_folder =		"1. Original JPG"
orig_raw_folder =		"1. Original RAW"
extracted_jpg_folder =	"2. Extracted JPG"
timezone_corr_folder =	"2. Ready for timezone correction"
sort_ready_folder =		"3. Ready to be sorted"

UNSUP_EXT_subfolder_name = "##   UNSUPPORTED EXTENSIONS   ##"
INCOMPL_EXIF_subfolder_name = "##   INCOMPLETE EXIF   ##"
RAW_subfolder_name = "##   RAWs   ##"
EXIF_subfolder_name = "##   EXIFs   ##"

result_folders = [CRW_conv_folder, orig_jpg_folder, orig_raw_folder, sort_ready_folder, extracted_jpg_folder]

all_folders = result_folders + [unsorted_folder, problematic_folder, ready_folder, timezone_corr_folder]


day_division_time = "04.44.44"


path_to_report = "RAPORT.txt"
raw_marker_str = "RAW__"


known_cameras_symbols = [

	("Canon PowerShot G6", "G6"),
	("GT-I9505", "S4"),
	("Canon EOS 5D", "5D"),
	("DSC-H50", "SH50"),
	("FinePix REAL 3D W3", "3DW3"),
	("E71", "NE71"),
	("iPhone 6", "iP6")
]

supported_image_extensions = [

	".crw",
	".cr2",
	".dng",
	".jpg",
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
