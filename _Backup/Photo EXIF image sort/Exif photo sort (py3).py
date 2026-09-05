#!python3
from PIL import Image
from PIL.ExifTags import TAGS

img = Image.open("test2.jpg")
exif = img._getexif()
# decode exif using TAGS
print(exif)
print(exif, file=sys.stderr)