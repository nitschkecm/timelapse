#!/usr/bin/python

import httplib
import httplib2
import os
import random
import sys
import time
import ephem
import datetime
import shutil
import RPi.GPIO as GPIO
import logging

from apiclient.discovery import build
from apiclient.errors import HttpError
from apiclient.http import MediaFileUpload
from oauth2client.client import flow_from_clientsecrets
from oauth2client.file import Storage
from oauth2client.tools import argparser, run_flow


# Explicitly tell the underlying HTTP transport library not to retry, since
# we are handling retry logic ourselves.
httplib2.RETRIES = 1

# Maximum number of times to retry before giving up.
MAX_RETRIES = 10

# Always retry when these exceptions are raised.
RETRIABLE_EXCEPTIONS = (httplib2.HttpLib2Error, IOError, httplib.NotConnected,
  httplib.IncompleteRead, httplib.ImproperConnectionState,
  httplib.CannotSendRequest, httplib.CannotSendHeader,
  httplib.ResponseNotReady, httplib.BadStatusLine)

# Always retry when an apiclient.errors.HttpError with one of these status
# codes is raised.
RETRIABLE_STATUS_CODES = [500, 502, 503, 504]

# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the Google Developers Console at
# https://cloud.google.com/console.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = "client_secrets.json"

# This OAuth 2.0 access scope allows an application to upload files to the
# authenticated user's YouTube channel, but doesn't allow other types of access.
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

# This variable defines a message to display if the CLIENT_SECRETS_FILE is
# missing.
MISSING_CLIENT_SECRETS_MESSAGE = """
WARNING: Please configure OAuth 2.0

To make this sample run you will need to populate the client_secrets.json file
found at:

   %s

with information from the Developers Console
https://cloud.google.com/console

For more information about the client_secrets.json file format, please visit:
https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
""" % os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   CLIENT_SECRETS_FILE))

VALID_PRIVACY_STATUSES = ("public", "private", "unlisted")
now = datetime.datetime.now()
initYear = "%04d" % (now.year)
initMonth = "%02d" % (now.month)
initDate = "%02d" % (now.day)
initHour = "%02d" % (now.hour)
initMins = "%02d" % (now.minute)

day = "%02d" % (now.day)
hour = "%02d" % (now.hour)
mins = "%02d" % (now.minute)


# If you run a local web server on Apache you could set this to /var/www/ to make them 
# accessible via web browser.
folderToSave = "/home/pi/test/timelapse_" + str(initYear) + str(initMonth) + str(initDate) + str(initHour)
os.mkdir(folderToSave)

AVI_FILENAME = str(folderToSave) + "/todays_video.avi"
MP4_FILENAME = str(folderToSave) + "/todays_video.mp4"
MP4_ARCHIVE = "/mnt/backup/orchids/todays_video.mp4"
JPG_ARCHIVE = "/mnt/backup/orchids/"

def get_authenticated_service(args):
  flow = flow_from_clientsecrets(CLIENT_SECRETS_FILE,
    scope=YOUTUBE_UPLOAD_SCOPE,
    message=MISSING_CLIENT_SECRETS_MESSAGE)

  storage = Storage("%s-oauth2.json" % sys.argv[0])
  credentials = storage.get()

  if credentials is None or credentials.invalid:
    credentials = run_flow(flow, storage, args)

  return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION,
    http=credentials.authorize(httplib2.Http()))

def initialize_upload(youtube, options):
  tags = None

  body=dict(
    snippet=dict(
      title="Orchids in Blossom Timelapse  "+datetime.datetime.today().strftime("%d-%m-%Y"),
      description="Orchids in Blossom",
      tags="",
      categoryId=""
    ),
    status=dict(
      privacyStatus=VALID_PRIVACY_STATUSES[0]
    )
  )

  # Call the API's videos.insert method to create and upload the video.
  insert_request = youtube.videos().insert(
    part=",".join(body.keys()),
    body=body,
    # The chunksize parameter specifies the size of each chunk of data, in
    # bytes, that will be uploaded at a time. Set a higher value for
    # reliable connections as fewer chunks lead to faster uploads. Set a lower
    # value for better recovery on less reliable connections.
    #
    # Setting "chunksize" equal to -1 in the code below means that the entire
    # file will be uploaded in a single HTTP request. (If the upload fails,
    # it will still be retried where it left off.) This is usually a best
    # practice, but if you're using Python older than 2.6 or if you're
    # running on App Engine, you should set the chunksize to something like
    # 1024 * 1024 (1 megabyte).
    media_body=MediaFileUpload(MP4_FILENAME, chunksize=-1, resumable=True)
  )

  resumable_upload(insert_request)

# This method implements an exponential backoff strategy to resume a
# failed upload.
def resumable_upload(insert_request):
  response = None
  error = None
  retry = 0
  while response is None:
    try:
      status, response = insert_request.next_chunk()
      if 'id' in response:
        print "Video id '%s' was successfully uploaded." % response['id']
      else:
        exit("The upload failed with an unexpected response: %s" % response)
    except HttpError, e:
      if e.resp.status in RETRIABLE_STATUS_CODES:
        error = "A retriable HTTP error %d occurred:\n%s" % (e.resp.status,
                                                             e.content)
      else:
        raise
    except RETRIABLE_EXCEPTIONS, e:
      error = "A retriable error occurred: %s" % e

    if error is not None:
      print error
      retry += 1
      if retry > MAX_RETRIES:
        exit("No longer attempting to retry.")

      max_sleep = 2 ** retry
      sleep_seconds = random.random() * max_sleep
      print "Sleeping %f seconds and then retrying..." % sleep_seconds
      time.sleep(sleep_seconds)

if __name__ == '__main__':
  args = argparser.parse_args()

  now = datetime.datetime.now()

  # Set up a log file to store activities for any checks.
  logging.basicConfig(filename=str(folderToSave) + ".log",level=logging.DEBUG)
  logging.debug(" R A S P I L A P S E C A M -- Started Log for " + str(folderToSave))
  logging.debug(" Support at http://fotosyn.com/timelapse/")
  
  here = ephem.Observer()

  here.lon, here.lat = '-3.87182', '40.47353'

  sunrise = here.next_rising(ephem.Sun())

  sunset = here.next_setting(ephem.Sun())

  time_before = datetime.timedelta(minutes=0)

  time_after = datetime.timedelta(minutes=45)

  sunrise = ephem.localtime(sunrise) - time_before

  sunset = ephem.localtime(sunset) + time_after

  video_length = (sunset - sunrise).total_seconds() * 1000

  total_time = int(video_length)

  # Set FileSerialNumber to 000X using four digits
  fileSerialNumber = str(initMonth)+ str(initDate)+"_Orchids%04d"
  #RECORD_COMMAND = "raspiyuv -h 1072 -w 1920 -t %(length)d -tl %(slice)d -o - | /home/pi/rpi-openmax-demos-master/rpi-encode-yuv > %(file)s"

  #print(RECORD_COMMAND % {"length": video_length, "slice": frame_time, "file": H264_FILENAME})

  sleep_time = (sunrise - now).total_seconds()

  print total_time
  print("Sleeping for %d seconds" % sleep_time)

  time.sleep(sleep_time)

  # Define the size of the image you wish to capture. 
  imgWidth = 2592 # Max = 2592 
  imgHeight = 1944 # Max = 1944
  print " ====================================== Saving file at " + hour + ":" + mins

  # Capture the image using raspistill. Set to capture with added sharpening, auto white balance and average metering mode
  # Change these settings where you see fit and to suit the conditions you are using the camera in
  print total_time 
  os.system("raspistill -w " + str(imgWidth) + " -h " + str(imgHeight) + " -o " + str(folderToSave) + "/" + str(fileSerialNumber) + ".jpg  -sh 40 -awb auto -mm average -v" + " -t " +str(total_time) + " -tl 60000")

  # Write out to log file
  logging.debug(' Image saved: ' + str(folderToSave) + "/" + str(fileSerialNumber) + "_" + str(hour) + str(mins) +  ".jpg")
  os.chdir(folderToSave)
  os.system("ls *.jpg  > stills.txt")
  os.system("mencoder -nosound -ovc lavc -lavcopts vcodec=mpeg4:aspect=16/9:vbitrate=8000000 -vf scale=1920:1080 -o todays_video.avi -mf type=jpeg:fps=24 mf://@stills.txt")
  os.system("MP4Box -fps 25 -add %(in_file)s %(out_file)s" % {"in_file": AVI_FILENAME, "out_file": MP4_FILENAME})

  if not os.path.exists(MP4_FILENAME):
    exit("No video to upload")

  youtube = get_authenticated_service(args)
  try:
    initialize_upload(youtube, args)
  except HttpError, e:
    print "An HTTP error %d occurred:\n%s" % (e.resp.status, e.content)

  os.remove(AVI_FILENAME)
  shutil.copyfile(MP4_FILENAME, MP4_ARCHIVE)
  for file in os.listdir(folderToSave):
    if file.endswith(".jpg"):
      shutil.move(folderToSave,JPG_ARCHIVE)  
  os.remove(MP4_FILENAME)

