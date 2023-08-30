from __future__ import print_function

import datetime
import os.path
import calendar
import numpy as np
import re
import io

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/drive.readonly',
          'https://www.googleapis.com/auth/calendar.readonly',
          'https://www.googleapis.com/auth/drive.photos.readonly']
SAVE_PATH = os.path + "/Downloads"
CAL_ID = 'example@example.com'
MAX_RES = 100000000

RESULTS_DATETIME_MIN = datetime.datetime(
            2022, 9, 1, 0, 0, 0, 0).isoformat() + 'Z'
RESULTS_DATETIME_MAX = datetime.datetime(
            2022, 12, 31, 0, 0, 0, 0).isoformat() + 'Z'


def get_week_of_month(target_date: datetime,
                      first_day_of_week: int = 0) -> int:
    """Get the week of the month a given datetime falls into.

    Args:
        target_date (datetime): the date of which to find the week number
                                in month
        first_day_of_week (int, optional): First day of the week.
                                            Defaults to 0, representing monday.

    Returns:
        int: the week of the month that the date lies in as an integer
    """
    calendar.setfirstweekday(first_day_of_week)
    x = np.array(calendar.monthcalendar(target_date.year, target_date.month))
    week_of_month = np.where(x == target_date.day)[0][0] + 1
    return(week_of_month)


def get_subject(date: datetime) -> str:
    """
    Translate the day of the week into the Subject taught on that day.
    As the same subjects are taught on the same days, we can statically
    assign them

    Args:
        date (datetime): the date of the event we are trying to find the
        subject of

    Returns:
        str: the subject taught on the day of the date given
    """
    day = date.weekday()
    if (date < datetime.datetime(2016, 4, 1, 0, 0, 0, 0)):
        day_to_subject = {
            0: 'Unknown',
            1: 'Unknown',
            2: 'Unknown',
            3: 'Unknown',
            4: 'Unknown',
            5: 'Unknown',
            6: 'Unknown',
        }
    elif (date >= datetime.datetime(2016, 4, 1, 0, 0, 0, 0) and
          date < datetime.datetime(2017, 4, 1, 0, 0, 0, 0)):
        day_to_subject = {
            0: 'Maths',
            1: 'Arts',
            2: 'English',
            3: 'Science',
            4: 'Crafts',
            5: 'Unknown',
            6: 'Unknown',
        }
    elif (date >= datetime.datetime(2017, 4, 1, 0, 0, 0, 0) and
          date < datetime.datetime(2018, 4, 9, 0, 0, 0, 0)) or\
         (date >= datetime.datetime(2018, 7, 16, 0, 0, 0, 0) and
          date < datetime.datetime(2019, 4, 1, 0, 0, 0, 0)):
        day_to_subject = {
            0: 'Maths',
            1: 'English',
            2: 'Science',
            3: 'Social Studies',
            4: 'Arts and Crafts',
            5: 'Unknown',
            6: 'Unknown',
        }
    elif (date >= datetime.datetime(2018, 4, 9, 0, 0, 0, 0) and
          date < datetime.datetime(2018, 7, 16, 0, 0, 0, 0)):
        day_to_subject = {
            0: 'English',
            1: 'Science',
            2: 'Maths',
            3: 'Social Studies',
            4: 'Arts and Crafts',
            5: 'Unknown',
            6: 'Unknown',
        }
    elif (date >= datetime.datetime(2019, 4, 1, 0, 0, 0, 0) and
          date < datetime.datetime(2020, 1, 6, 0, 0, 0, 0)):
        day_to_subject = {
            0: 'Science',
            1: 'Maths',
            2: 'Social Studies',
            3: 'English',
            4: 'Arts and Crafts',
            5: 'Maths',
            6: 'Unknown',
        }
    else:
        day_to_subject = {
            0: 'Maths',
            1: 'Social Studies',
            2: 'Science',
            3: 'English',
            4: 'Arts and Crafts',
            5: 'Unknown',
            6: 'Unknown',
        }
    return day_to_subject[day]


def get_or_retrieve_creds(scopes: list) -> Credentials:
    """
    Based on the Google Calendar API demo.
    Get or create the token.json credentials file to return
    Google credentials.
    If it has been more than 7 days, andd you are getting a bad request
    invalid grant, delete the token.json - test users expire after 7 days
    Then run from command line to get the redirect and creds again

    Args:
        scopes (list): Scopes necessary for api actions

    Returns:
        Credentials: Credentials object to perform the api actions
    """

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', scopes)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Credentials have expired. Requesting new ones.")
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', scopes)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            print("Writing credentials file as token.json")
            token.write(creds.to_json())

    return creds


def get_calendar_events(from_date: datetime = datetime.datetime(
            1900, 1, 1, 0, 0, 0, 0).isoformat() + 'Z',
                        to_date: datetime = datetime.datetime(
            2100, 1, 1, 0, 0, 0, 0).isoformat() + 'Z',
                        maxResults: int = None,
                        calendar_id: str = 'primary') -> list:
    """
    Based on the Google Calendar API demo, this expands on it to retrieve
    events, and then assign the key details necessary to back them up in
    a folder structure, and to get any attatchments

    Args:
        from_date (datetime): The minimum date to check events from.
                             Defaults to 1/1/1990.
        to_date (datetime): The maximum date to check events until.
                             Defaults to 1/1/2100.
        maxResults (int, optional): The maximum number of events to
                                    retreive. Defaults to None.

    Returns:
        list: list of events with their year, month, subject, week, and
                attachments
    """
    # Get Credentials
    creds = get_or_retrieve_creds(SCOPES)

    my_events = []

    try:
        service = build('calendar', 'v3', credentials=creds)

        # Call the Calendar API
        events_result = service.events().list(calendarId=calendar_id,
                                              timeMin=from_date,
                                              timeMax=to_date,
                                              maxResults=maxResults,
                                              singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        if not events:
            print('No upcoming events found.')
            return

        # Prints the start and name of the next 10 events
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            start_date = re.search(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}", start).group()
            dt_start = datetime.datetime.strptime(start_date, "%Y-%m-%d")
            my_attachments = {}
            if 'attachments' in event:
                my_attachments = event['attachments']
            list_entry = {
                            "summary": event.get('summary', 'None'),
                            "description": event.get('description', 'None'),
                            "year": dt_start.year,
                            "month": dt_start.month,
                            "week_in_month": get_week_of_month(dt_start),
                            "subject": get_subject(dt_start),
                            'attachments': my_attachments
                        }

            my_events.append(list_entry)

    except HttpError as error:
        print('An error occurred: %s' % error)

    return my_events


def process_files(items_to_check: list):
    """
    Takes the calendar entries from get_calendar_events,
    loops through, checks for attachments, handles download
    of those files, then stores them in the correct file structure

    Args:
        items_to_check (list): List of calendar events
    """

    # Get credentials
    creds = get_or_retrieve_creds(SCOPES)

    # Look through items in calendar entries
    for item in items_to_check:
        # Create the file path in which the attachments will be stored
        path_mid = '/'.join([str(item['year']),
                            str(item['month']),
                            item['subject'],
                            str(item['week_in_month'])])
        crt_path = SAVE_PATH + path_mid
        if not os.path.exists(crt_path):
            os.makedirs(crt_path)

        # Create the description text file with the calendar event summary
        item_title = item['summary']
        item_title = re.sub(r'[\\/*?:"<>|]', "", item_title)
        with open(crt_path + '/' + f'Description - {item_title}.html',
                  'w', encoding='utf-8') as f:
            f.write(item['description'])

        # Loop through attachments, download them, and write them to file.
        if 'attachments' in item:
            for attachment in item['attachments']:
                # Normal and google workspace files handled with different
                # request method
                wrkspace_doc = False
                if 'mimeType' in attachment:
                    if 'application/vnd.google-apps' in attachment['mimeType']:
                        wrkspace_doc = True
                # Get file as binary
                my_file = download_file(creds, attachment, crt_path,
                                        wrkspace_doc)
                # Handle downloaded file
                clean_title = re.sub(r'[\\/*?:"<>|]', "", attachment['title'])
                if my_file is not None:
                    if wrkspace_doc:
                        file_path = crt_path + '/' + clean_title + '.pdf'
                    else:
                        file_path = crt_path + '/' + clean_title
                    with open(file_path, "wb") as binary_file:
                        # Write bytes to file
                        binary_file.write(my_file)
                else:
                    print(F'file could not be downloaded: {clean_title}')


def download_file(creds: Credentials, attachment: dict,
                  file_path: str,
                  wrkspace_doc: bool = False) -> bytes:
    """
    Based on the Google Drive API demo, this takes the fileID
    from the given attachment, and downloads the file as a byte

    Args:
        creds (Credentials): Google Credentials necessary for the download
        attachment (dict): the metadata of the file to be downloaded
        file_path (str): where the file will be saved
        wrkspace_doc (bool, optional): Flag for Google Workspace Document.
                                        These need to be treated differently to
                                        regular files. Defaults to False.

    Returns:
        bytes: the downloaded file as byte
    """
    try:
        # create drive api client
        service = build('drive', 'v3', credentials=creds)
        if 'fileId' not in attachment:
            with open(file_path + "/Download Errors.txt", "a") as file_object:
                file_object.write(f'No fileId found. attachment: {attachment}')
            my_file = None
            return
        file_id = attachment['fileId']
        # pylint: disable=maybe-no-member
        # Return the appropriate request depending on the Workspace File flag
        if wrkspace_doc:
            request = service.files().export_media(fileId=file_id,
                                                   mimeType='application/pdf')
        else:
            request = service.files().get_media(fileId=file_id)
        file_title = attachment['title']
        file = io.BytesIO()
        downloader = MediaIoBaseDownload(file, request)
        done = False
        # Download the file
        while done is False:
            status, done = downloader.next_chunk()
            print(F'Downloading {file_title}: {int(status.progress() * 100)}.')
        my_file = file.getvalue()

    except HttpError as error:
        print(F'An error occurred: {error}')
        # If a download error has occured, list the errored files in a text
        # file for posterity
        with open(file_path + "/Download Errors.txt", "a",
                  encoding='utf-8') as file_object:
            file_object.write(f'{error} attachment: {attachment}')
        my_file = None
    return my_file


if __name__ == '__main__':
    print('Process Calendar events')
    if RESULTS_DATETIME_MIN > RESULTS_DATETIME_MAX:
        print('Given dates are not set correctly.' /
              + f'From: {RESULTS_DATETIME_MIN}, To: {RESULTS_DATETIME_MAX}')
    my_cal_events = get_calendar_events(from_date=RESULTS_DATETIME_MIN,
                                        to_date=RESULTS_DATETIME_MAX,
                                        maxResults=MAX_RES,
                                        calendar_id=CAL_ID)

    print(f'Calendar events processed. {len(my_cal_events)} events found.')
    print('Processing calendar attachments')
    process_files(my_cal_events)
