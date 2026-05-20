from datetime import datetime, date, time


# Using datetime.combine()
d = date(2005, 7, 14)
t = time(12, 30)
print datetime.combine(d, t)  # datetime.datetime(2005, 7, 14, 12, 30)
# Using datetime.now() or datetime.utcnow()
print datetime.now()  # datetime.datetime(2007, 12, 6, 16, 29, 43, 79043)   # GMT +1
print datetime.utcnow()  # datetime.datetime(2007, 12, 6, 15, 29, 43, 79060)

"""
	EXIF:
		2015:04:13 20:35:44
	Python:
		2005-07-14 12:30:00
	File:
		2015-04-13_(Mon)_20.35.44
"""
