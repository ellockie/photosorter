#!python3
import time
import os,sys
from PIL import Image
from PIL.ExifTags import TAGS

imageDir = "_Images\\"

testImage = 'testRAW.cr2'
testImage = 'testRAW.jpg'
testImage = 'testRAW_small.jpg'
testImage = 'test.jpg'
testImage = 'test2.jpg'
testImage = 'test3-fullEXIF.jpg'
testImage = 'CRW_2003.thm.jpg'
testImage = 'CRW_1950_1.jpg'
testImage = 'CRW_1950.CRW'

print("")

def get_exif(fn):
    ret = {}
    i = Image.open(fn)
    info = i._getexif()
    for tag, value in info.items():
        decoded = TAGS.get(tag, tag)
        ret[decoded] = value
    return ret

print("")

with open(imageDir+testImage+".EXIF", "w") as f_exif_tags:
	exif_data = get_exif(imageDir+testImage)
	
	'''
	#	List of the available keys
	print("  exif_data.keys():")
	print(exif_data.keys())
	print("")
	'''
	
	#	Does the ExposureTime tag exist?
	print("Does the ExposureTime tag exist?")
	print('ExposureTime' in exif_data)
	print("")
	
	#	Print ExposureTime tag's value
	print('ExposureTime value:', exif_data['ExposureTime'])
	print('Exposure time:', exif_data['ExposureTime'][0]/exif_data['ExposureTime'][1],"s")
	print("")
	print("")
	
	#	Print all the available keys and their values
	print("  All the available keys and their values:")
	print("")
	for key in exif_data:
		print(key, " = ", exif_data[key])
		f_exif_tags.write(key+":\n\t\t\t\t"+str(exif_data[key])+"\n")
		#f_exif_tags.write(":\n")


#	2013-04-28_(Sun)_12.26.59__RAW__f14.1...T1_80..71mm160.JPG

'''
ANOTHER EXAMPLE:
from PIL import Image
img = Image.open('img.jpg')
exif_data = img._getexif()

This should give you a dictionary indexed by EXIF numeric tags. If you want the dictionary indexed by the actual EXIF tag name strings, try something like:

exif = {
    PIL.ExifTags.TAGS[k]: v
    for k, v in img._getexif().items()
    if k in PIL.ExifTags.TAGS
}
'''

time.sleep(2.5)    # pause for x seconds