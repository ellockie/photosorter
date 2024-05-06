#!python2
import time
import os
import sys
from PIL import Image
from PIL.ExifTags import TAGS
import math

#import datetime
from datetime import datetime

# Required modules for folder traversing (maybe not all)
import os
import shutil
from os.path import join, getsize
import errno

#imageDir = "_Images\\"
#imageDir = os.getcwd()

testImage = 'testRAW.cr2'
testImage = 'testRAW.jpg'
testImage = 'testRAW_small.jpg'
testImage = 'test.jpg'
testImage = 'test2.jpg'
testImage = 'test3-fullEXIF.jpg'

HDR_SUBFOLDER = "~~    HDR    ~~\\"


#root_folder = '_Images'
root_folder = os.getcwd()
imageDir = root_folder + "\\"
# localRAWSubfolerName = '##  RAWs  ##\\'

#errorCount = 0

# Function for getting files from a folder


def fetchFiles(pathToFolder, flag, keyWord):
    '''
    fetchFiles() requires three arguments: pathToFolder, flag and keyWord

    flag must be 'STARTS_WITH' or 'ENDS_WITH'
    keyWord is a string to search the file's name

    Be careful, the keyWord is case sensitive and must be exact

    Example: fetchFiles('/Documents/Photos/','ENDS_WITH','.JPG')

    returns: _pathToFiles and _fileNames
    '''

    _pathToFiles = []
    _fileNames = []
    _folderNames = []
    _captureTimes = []

    for dirPath, dirNames, fileNames in os.walk(pathToFolder):
        if flag == 'ENDS_WITH':
            selectedPath = [os.path.join(dirPath, item)
                            for item in fileNames if item.endswith(keyWord)]
            _pathToFiles.extend(selectedPath)

            selectedFolder = [
                dirPath for item in fileNames if item.endswith(keyWord)]
            _folderNames.extend(selectedFolder)

            selectedFile = [
                item for item in fileNames if item.endswith(keyWord)]
            _fileNames.extend(selectedFile)

        elif flag == 'STARTS_WITH':
            selectedPath = [os.path.join(dirPath, item)
                            for item in fileNames if item.startswith(keyWord)]
            _pathToFiles.extend(selectedPath)

            selectedFile = [
                item for item in fileNames if item.startswith(keyWord)]
            _fileNames.extend(selectedFile)

        else:
            print fetchFiles.__doc__
            break

        # Try to remove empty entries if none of the required files are in directory
        try:
            _pathToFiles.remove('')
            _imageFiles.remove('')
        except ValueError:
            pass

        # Warn if nothing was found in the given path
        '''
        if selectedFile == []: 
            print 'No files with given parameters were found in:\n', dirPath, '\n'
        '''

    print ' ', len(_fileNames), '\t', keyWord, ' files were found in searched ', pathToFolder, ' folder'

    return _pathToFiles, _fileNames, _folderNames, _captureTimes


def get_immediate_subdirectories(a_dir):
    return [name for name in os.listdir(a_dir) if os.path.isdir(os.path.join(a_dir, name))]


def get_exif(fn):
    ret = {}
    i = Image.open(fn)
    info = i._getexif()
    for tag, value in info.items():
        decoded = TAGS.get(tag, tag)
        ret[decoded] = value
    return ret


def unix_time(dt):
    epoch = datetime.utcfromtimestamp(0)
    delta = dt - epoch
    return delta.total_seconds()


def unix_time_millis(dt):
    return unix_time(dt) * 1000.0


def moveHDRCluster(clusterfile1, clusterfile2, clusterfile3):
    # define target RAW directory, create if needed
    #targetHDRdirectory = os.path.join(HDR_SUBFOLDER, localRAWSubfolerName)
    if not os.path.exists(imageDir + HDR_SUBFOLDER):
        os.makedirs(imageDir + HDR_SUBFOLDER)

    targetClusterFileName = imageDir + HDR_SUBFOLDER + clusterfile1
    print 'Cluster  file name: ', targetClusterFileName
    # move the cluster file
    if not os.path.isfile(targetClusterFileName):
        # print 'Cluster  file name: ', targetClusterFileName
        shutil.move(imageDir + clusterfile1, targetClusterFileName)
        print 'Cluster  moved!  -  ' + clusterfile1 + ''
    else:
        if clusterfile1 == targetClusterFileName:
            # print '   ###  The Cluster file already exists in target location'
            existsCount = existsCount + 1
        else:
            print '   ###  Error: Could not move the Cluster file'
            #errorCount = errorCount + 1

    targetClusterFileName = imageDir + HDR_SUBFOLDER + clusterfile2
    print 'Cluster  file name: ', targetClusterFileName
    # move the cluster file
    if not os.path.isfile(targetClusterFileName):
        # print 'Cluster  file name: ', targetClusterFileName
        shutil.move(imageDir + clusterfile2, targetClusterFileName)
        print 'Cluster  moved!  -  ' + clusterfile2 + ''
    else:
        if clusterfile2 == targetClusterFileName:
            # print '   ###  The Cluster file already exists in target location'
            existsCount = existsCount + 1
        else:
            print '   ###  Error: Could not move the Cluster file'
            #errorCount = errorCount + 1

    targetClusterFileName = imageDir + HDR_SUBFOLDER + clusterfile3
    print 'Cluster  file name: ', targetClusterFileName
    # move the cluster file
    if not os.path.isfile(targetClusterFileName):
        # print 'Cluster  file name: ', targetClusterFileName
        shutil.move(imageDir + clusterfile3, targetClusterFileName)
        print 'Cluster  moved!  -  ' + clusterfile3 + ''
    else:
        if clusterfile3 == targetClusterFileName:
            # print '   ###  The Cluster file already exists in target location'
            existsCount = existsCount + 1
        else:
            print '   ###  Error: Could not move the Cluster file'
            #errorCount = errorCount + 1


print "---------------------------------------------------------------------------"
print

images_list = [[], [], [], []]
result_JPG = fetchFiles(root_folder, 'ENDS_WITH', '.JPG')
result_JPG_smallCaps = fetchFiles(root_folder, 'ENDS_WITH', '.jpg')
images_list[0] = result_JPG[0] + result_JPG_smallCaps[0]
images_list[1] = result_JPG[1] + result_JPG_smallCaps[1]
images_list[2] = result_JPG[2] + result_JPG_smallCaps[2]

print
print
print images_list[0][0]
print
print images_list[1][0]
print
print images_list[2][0]

capture_time = []
previous_aperture_value = "NAN"
previous_exposure_log_time = "NAN"
previous_capture_time = "NAN"
previous_1_file_name = "NAN"
cluster_member_count = 0
file_output_string = 'File list:'
cluster_marker = ""
not_a_cluster_marker = ""

with open(imageDir+"__HDR CLUSTER LIST"+".txt", "w") as f_cluster_list:
    for current_image_FileName in images_list[1]:
        print "## FileName:   >", imageDir+current_image_FileName, "<"
        exif_data = get_exif(imageDir+current_image_FileName)

        file_output_string = current_image_FileName + "\t> "
        '''
        #    Print list of the available keys
        print("  exif_data.keys():")
        print(exif_data.keys())
        print("")
        '''

        #    Does the ExposureTime tag exist?
        #    print "Does the ExposureTime tag exist?",'ExposureTime' in exif_data

        if 'ExposureTime' in exif_data:
            #    Print ExposureTime tag's value
            #    print'ExposureTime value:', exif_data['ExposureTime']
            current_aperture_value = exif_data['ApertureValue'][0]
            print "current_aperture_value:", current_aperture_value
            print "previous_aperture_value:", previous_aperture_value
            current_capture_time = exif_data['DateTimeOriginal']
            capture_time.append(current_capture_time)
            images_list[3].append(current_capture_time)
            time_component_0 = float(exif_data['ExposureTime'][0])
            time_component_1 = float(exif_data['ExposureTime'][1])
            time_value = time_component_0 / time_component_1

            print'Exposure time:', exif_data['ExposureTime'], "=", time_value, "s", 'rounded: %s' % float('%.2g' % time_value), "s"

            exposure_log_time = math.log(time_value, 2)
            #    print'Exposure time log2:', exposure_log_time,"s"
            if previous_exposure_log_time == "NAN":
                print "NAN"
            else:
                log_exp_time_difference = exposure_log_time - previous_exposure_log_time
                rounded_log_exp_time_difference_str = round(
                    log_exp_time_difference, 1)
                print "Difference in exposure time:", rounded_log_exp_time_difference_str, "~EV (", log_exp_time_difference, ")"
                if rounded_log_exp_time_difference_str <= 0:
                    file_output_string = file_output_string + "<" + \
                        str(rounded_log_exp_time_difference_str)
                else:
                    file_output_string = file_output_string + "< " + \
                        str(rounded_log_exp_time_difference_str)
            previous_exposure_log_time = exposure_log_time

            file_output_string = file_output_string + \
                " (cl." + str(cluster_member_count) + ") "
            if previous_capture_time == "NAN":
                print "NAN"
                cluster_member_count = 1
            else:
                print " previous_capture_time:", previous_capture_time
                print " current_capture_time: ", current_capture_time

                dt1 = datetime.strptime(
                    previous_capture_time, '%Y:%m:%d %H:%M:%S')
                dt2 = datetime.strptime(
                    current_capture_time, '%Y:%m:%d %H:%M:%S')
                capture_time_difference = (dt2 - dt1).total_seconds()
                print " Difference in capture times:", capture_time_difference, "s"
                file_output_string = file_output_string + \
                    " / " + str(capture_time_difference) + "s >"

                #    Capture time difference check
                if math.fabs(capture_time_difference) > 120:
                    print "  #####  NOT THE SAME CLUSTER  #####"
                    # file_output_string = file_output_string + " \t##### NEW? (long interval)"
                    cluster_member_count = 0
                    not_a_cluster_marker = "\n NEW (too long interval)\n\n"

                #    Aperture value check
                if previous_aperture_value != current_aperture_value:
                    print "  #####  DIFFERENT APERTURE  #####"
                    # file_output_string = file_output_string + " \t@@@@ NEW (different aperture)"
                    cluster_member_count = 0
                    not_a_cluster_marker = "\n NEW (different aperture)\n\n"

                    with open(imageDir+previous_1_file_name+"__DIFFERENT APERTURE"+".txt", "w") as f_singlet:
                        f_singlet.write("DIFFERENT APERTURE here!")

                if cluster_member_count == 0:
                    print "NEW?"
                    file_output_string = file_output_string + \
                        " \t\t#### NEW? (soon after prev.)"
                    cluster_member_count = 1
                elif cluster_member_count == 1 and round(log_exp_time_difference, 0) == -2.0:
                    print "@  THE SAME CLUSTER?"
                    file_output_string = file_output_string + " \tTHE SAME CLUSTER?"
                    cluster_member_count = 2
                elif cluster_member_count == 2 and round(log_exp_time_difference, 0) == 4.0:
                    print "@  THE SAME CLUSTER!"
                    file_output_string = file_output_string + " \t!! CLUSTER !!"
                    cluster_member_count = 0
                    moveHDRCluster(previous_0_file_name,
                                   previous_1_file_name, current_image_FileName)
                    cluster_marker = "\n NEW (there was a cluster)\n\n"
                elif cluster_member_count == 2 and round(log_exp_time_difference, 0) == -2.0:
                    # and str(rounded_log_exp_time_difference_str) == -2.0
                    print "@  THE SAME CLUSTER?"
                    file_output_string = file_output_string + " \tTHE SAME CLUSTER?"
                    cluster_member_count = 2
                else:
                    print "Unexpected condition!"
                    file_output_string = file_output_string + \
                        " \t\t#### NEW? ------------ Unexpected condition before! Singlet? (cl." + str(
                            cluster_member_count) + ")"
                    with open(imageDir+previous_1_file_name+"__SINGLET"+".txt", "w") as f_singlet:
                        f_singlet.write("Looks like a singlet here!")
                    cluster_member_count = 1

                #    Warning when the same time
                if capture_time_difference == 0:
                    file_output_string = file_output_string + "   WARNING! The same time!"

                # Debugging:
                # print round(log_exp_time_difference,0)
                # print cluster_member_count
                # print "Difference in capture time:", (current_capture_time - previous_capture_time).total_seconds(), "s"
            print

            previous_aperture_value = current_aperture_value
            previous_capture_time = current_capture_time

            f_cluster_list.write(not_a_cluster_marker + file_output_string +
                                 " (cl." + str(cluster_member_count) + ") " "\n" + cluster_marker)
            cluster_marker = ""
            not_a_cluster_marker = ""

            if cluster_member_count == 0:
                f_cluster_list.write("\n")

            '''
            #   Optional:
            #    Write EXIF data into a file
            with open(imageDir+current_image_FileName+".EXIF.txt", "w") as f_exif_tags:
                for key in exif_data:
                    #    print(key, " = ", exif_data[key])
                    f_exif_tags.write(key+":\n\t\t\t\t"+str(exif_data[key])+"\n")
                    #f_exif_tags.write(":\n")
            '''
        else:
            print "The ExposureTime tag doesn't exist!"

        previous_0_file_name = previous_1_file_name
        previous_1_file_name = current_image_FileName

print "\n\n"


print "datetime.now():", datetime.now()

example = u'2013-10-20T00:41:32.000Z'
# print datetime.strptime(example, '%Y-%m-%dT%H:%M:%S.%fZ')
print
dt1 = datetime.strptime("2014-10-25 18:32:06", '%Y-%m-%d %H:%M:%S')
dt2 = datetime.strptime("2014-10-25 18:32:18", '%Y-%m-%d %H:%M:%S')
'''
Template:
2014-10-09_(Thu)_17.04.53__RAW__f8.0...T1_3..105mm100.JPG
'''
print "capture_time[0]:", capture_time[0]
dt1 = datetime.strptime(images_list[3][0], '%Y:%m:%d %H:%M:%S')
dt2 = datetime.strptime(images_list[3][2], '%Y:%m:%d %H:%M:%S')
print "difference in seconds:", (dt2 - dt1).total_seconds()
print "difference in miliseconds:", unix_time_millis(dt2)-unix_time_millis(dt1)
print "__"
print "NOTES: Next challenge is how to determine which file was first"
print "But on the other hand if they are this close to each other (<1s), it means they are in the same cluster"
print "We need to convert date/time into one value, to be able to determine time interval after taking into account exposure times"
print "Find problematic photos and test them."


# time.sleep(2.5)    # pause for x seconds
