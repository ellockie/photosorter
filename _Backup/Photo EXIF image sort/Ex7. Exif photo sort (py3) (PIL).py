#!python3
import time
import os,sys
from PIL import Image
from PIL.ExifTags import TAGS

img = Image.open('test.jpg')
exif_data = img._getexif()


print(exif_data)
print("...")
print('%s = %s' % (TAGS.get(k), v))