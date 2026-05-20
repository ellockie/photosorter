#!python3
import time
import os,sys
from PIL import Image
from PIL.ExifTags import TAGS

for (k,v) in Image.open(sys.argv[1])._getexif().iteritems():
        print('%s = %s' % (TAGS.get(k), v))
		
time.sleep(2.5)    # pause for x seconds