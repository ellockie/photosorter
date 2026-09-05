#!python2

import EXIF
import sys
import os

list = {}

for filename in sys.argv[1:]:
	try:
		imageFile=open(filename, 'rb')
	except:
		print "'%s': Cannot open for reading.\n" % filename
		continue

	# get the tags
	data = EXIF.process_file(imageFile, details=False, debug=False)
	if not data:
		print '%s: No EXIF data found' % filename
		continue

	date	 = data['Image DateTime']

	key = str(date)
	if key in list.keys():
		print '%s: Duplicate datestamp with %s' % (filename, list[key])
	list[key] = filename

	imageFile.close()

datestamps = list.keys()
datestamps.sort()
for datestamp in datestamps:
	suffix = os.path.splitext(list[datestamp])[1]
	newName = datestamp.replace(':', '_')
	newName = newName.replace(' ', '_')
	newName = "pic" + newName + suffix
	try:
		os.rename(list[datestamp], newName)
		print list[datestamp] + ' -> ' + newName
	except:
		print '%s: Could not rename' % list[datestamp]
		
