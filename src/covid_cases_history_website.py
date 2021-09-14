from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from datetime import datetime
from pytz import timezone
from boto3.s3.transfer import TransferConfig
import boto3
import botocore
import requests
import json
import os

### --- start of constants and variables declaration --- ###
url = 'https://www.health.nsw.gov.au/Infectious/covid-19/Pages/stats-nsw.aspx'
headers = {'User-Agent': 'Mozilla/5.0'}
s3_transfer_config = TransferConfig(use_threads=False)

artefacts_s3_bucket = os.environ["ARTEFACTS_S3_BUCKET"]
artefacts_s3_key_prefix = os.environ["ARTEFACTS_S3_KEY_PREFIX"]
website_s3_bucket = os.environ["WEBSITE_S3_BUCKET"]
slack_webhook_url = os.environ["SLACK_WEBHOOK_URL"]

# files that contain case and vaccination information from previous runs
covid_cases_history_filename = artefacts_s3_key_prefix + '/covid_cases_history.csv'
covid_vaccination_history_filename = artefacts_s3_key_prefix + '/covid_vaccination_history.csv'
last_date_processed_filename = artefacts_s3_key_prefix + '/covid_cases_last_date.txt'

# files that will be used to create the final webpage
website_header_filename = './html/covid_cases_history_header.html'
website_footer_filename = './html/covid_cases_history_footer.html'
covid_vaccination_history_header_filename = './html/covid_vaccination_history_header.html'
website_filename = 'index.html'
error_filename   = 'error.html'

csv_delimiter = ';'  # this is the delimiter for csv files
my_timezone = 'Australia/Sydney' # timezone used for timestamps
### --- end of constants and variables declaration --- ###


def send_slack_message(slack_message):
    print('>>send_slack_message:slack_message:' + slack_message)

    slack_payload = {"text": slack_message}

    response = requests.post(slack_webhook_url, json.dumps(slack_payload))
    response_json = response.text
    print('>>send_slack_message:response after posting to slack:' + str(response_json))


def check_for_covid_cases_updates():

    s3 = boto3.resource('s3')
    last_date_processed = ''

    # check if we have information about the last covid-19 cases period that was processed.
    try:
        s3.Object(artefacts_s3_bucket, last_date_processed_filename).load()

        # file with period for last successful ingestion of data from NSW Government Health website exists, lets process it
        last_date_processed = s3.Object(artefacts_s3_bucket, last_date_processed_filename).get()[
            'Body'].read().decode('utf-8')
        print('>>last_date_processed file found. Period for last successful covid-19 cases processed:' +
              str(last_date_processed))

    except botocore.exceptions.ClientError as e:
        # no file with date for last successful ingestion of data from NSW Govt Health website exists, treat as if we are starting fresh
        print('>>last_date_processed file not found. Treating this as the first time that this function has been run.')

    # get the latest COVID-19 cases information from the NSW Government Health website.
    print('>>retrieving latest covid-19 cases information from ' + url)
    response = Request(url, headers=headers)
    webpage = urlopen(response).read()

    soup = BeautifulSoup(webpage, 'html.parser')

    report_period = soup.select_one('#maincontent > nav > h1').text.strip()
    report_period = report_period[report_period.find('- up to') + 2:]
    
    print('>>retrieved covid-19 cases information is for period:'+report_period)
    
    # check if the covid-19 cases history that was retrieved has been processed in previous AWS Lambda runs. If so, then ignore it otherwise process it
    
    if (report_period != last_date_processed):
        # the retrieved covid-19 case information is new, let's process it
        print('>>retrieved covid-19 case results are new -- processing it now')

        local_acquired_cases_known = soup.select_one('#known > ul > li:nth-child(1) > span.number').text.strip()
        local_acquired_cases_unknown = soup.select_one('#unknown > ul > li:nth-child(1) > span.number').text.strip()

        # lets combine the locally acquired known and unknown case numbers. Remove the thousandth separator in the numbers before casting.
        total_local_acquired_cases = int(local_acquired_cases_known.replace(',','')) + int(local_acquired_cases_unknown.replace(',',''))
        
        # to make things pretty (and consistent), add a thousandth separator to total_local_acquired_cases and then convert it to string
        total_local_acquired_cases = f'{total_local_acquired_cases:,}'

        interstate_acquired_cases = soup.select_one('#interstate > ul > li:nth-child(1) > span.number').text.strip()
        overseas_acquired_cases = soup.select_one('#overseas > ul > li:nth-child(1) > span.number').text.strip()
        total_cases = soup.select_one('#case > ul > li:nth-child(1) > span.number').text.strip()
        
        active_cases_local = soup.select_one('#ContentHtml1Zone2 > div:nth-child(1) > div').select_one('div.active-cases.calloutbox').select('.number')[0].text.strip()
        active_cases_interstate = soup.select_one('#ContentHtml1Zone2 > div:nth-child(1) > div').select_one('div.active-cases.calloutbox').select('.number')[1].text.strip()
        active_cases_overseas = soup.select_one('#ContentHtml1Zone2 > div:nth-child(1) > div').select_one('div.active-cases.calloutbox').select('.number')[2].text.strip()
        
        total_tests = soup.select_one('#testing > ul > li:nth-child(1) > span.number').text.strip()
        
        vaccination_first_dose = soup.select_one('#ContentHtml1Zone2 > div:nth-child(3) > div > table > tbody > tr:nth-child(2) > td:nth-child(2)').text.strip()
        vaccination_second_dose = soup.select_one('#ContentHtml1Zone2 > div:nth-child(3) > div > table > tbody > tr:nth-child(3) > td:nth-child(2)').text.strip()
        vaccination_total = soup.select_one('#ContentHtml1Zone2 > div:nth-child(3) > div > table > tbody > tr:nth-child(4) > td:nth-child(2)').text.strip()

        # create a local html file. This will be uploaded to the Amazon S3 bucket when done.
        local_website_file = open('/tmp/' + website_filename, 'w')

        # first add the header file to the html file
        header_file_handle = open(website_header_filename, 'r')
        local_website_file.write(header_file_handle.read())
        header_file_handle.close()

        # next add the latest covid-19 case details to the html file
        local_website_file.write('\n\t\t\t<tr>\n')
        local_website_file.write('\t\t\t\t<td> ' + report_period + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + total_local_acquired_cases + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + interstate_acquired_cases + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + overseas_acquired_cases + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + total_cases + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + active_cases_local + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + active_cases_interstate + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + active_cases_overseas + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + total_tests + ' </td>\n')
        local_website_file.write('\t\t\t</tr>')

        # next, check if there is any covid-19 case details from previous runs.
        try:
            s3.Object(artefacts_s3_bucket, covid_cases_history_filename).load()
            print('>>previous covid-19 cases file found. Adding it to html file')

            local_covid_cases_history_filename = '/tmp' + covid_cases_history_filename.replace(artefacts_s3_key_prefix,'')
            s3.Bucket(artefacts_s3_bucket).download_file(covid_cases_history_filename, local_covid_cases_history_filename, Config=s3_transfer_config)
            print('>>downloaded previous covid-19 case details: [' + artefacts_s3_bucket + ']' + covid_cases_history_filename + ' -> ' + local_covid_cases_history_filename)
            
            # add the previous covid-19 case details to local html file
            for line in reversed(list(open(local_covid_cases_history_filename, 'r'))):
                previous_covid_cases_history = line.split(csv_delimiter)
                print('>>previous covid-19 cases details:' + str(previous_covid_cases_history))

                local_website_file.write('\n\t\t\t<tr>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[0] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[1] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[2] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[3] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[4] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[5] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[6] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[7] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_cases_history[8] + ' </td>\n')
                local_website_file.write('\t\t\t</tr>')

        except botocore.exceptions.ClientError as e:
            # no previous covid-19 cases file found
            print('>>no previous covid-19 cases file found. Treating this as the first time that this function has been run.')

        local_website_file.write('\n\t\t</table>')
        local_website_file.write('\n\t\t<br>')

        # next, add vaccination details to the html file
        vaccination_history_header_file_handle = open(covid_vaccination_history_header_filename)
        local_website_file.write(vaccination_history_header_file_handle.read())
        vaccination_history_header_file_handle.close()

        # write the current vaccination details to html file
        local_website_file.write('\n\t\t\t<tr>\n')
        local_website_file.write('\t\t\t\t<td> ' + report_period + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + vaccination_first_dose + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + vaccination_second_dose + ' </td>\n')
        local_website_file.write('\t\t\t\t<td> ' + vaccination_total + ' </td>\n')

        # next, check if there is any vaccination details from previous runs
        try:
            s3.Object(artefacts_s3_bucket, covid_vaccination_history_filename).load()
            print('>>previous covid-19 vaccination file found. Adding it to html file')

            local_covid_vaccination_history_filename = '/tmp' + covid_vaccination_history_filename.replace(artefacts_s3_key_prefix,'')
            s3.Bucket(artefacts_s3_bucket).download_file(covid_vaccination_history_filename,local_covid_vaccination_history_filename, Config=s3_transfer_config)
            print('>>downloaded previous covid-19 vaccination details: [' + artefacts_s3_bucket + ']' + covid_vaccination_history_filename + ' -> ' + local_covid_vaccination_history_filename)
            
            # add the previous covid-19 vaccination details to the local html file
            for line in reversed(list(open(local_covid_vaccination_history_filename, 'r'))):
                previous_covid_vaccination_history = line.split(csv_delimiter)
                print('>>previous covid-19 vaccination details:' + str(previous_covid_vaccination_history))

                local_website_file.write('\n\t\t\t<tr>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_vaccination_history[0] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_vaccination_history[1] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_vaccination_history[2] + ' </td>\n')
                local_website_file.write('\t\t\t\t<td> ' + previous_covid_vaccination_history[3] + ' </td>\n')
        
        except botocore.exceptions.ClientError as e:
            # no file with covid vaccination history found
            print('>>no previous covid-19 vaccination file found. Treating this as the first time that this function has been run.')

        local_website_file.write('\n\t\t</table>')
        local_website_file.write('\n\t\t<br>')
        local_website_file.write('\n\t\t<br>')

        # add a timestamp to show that the html file was just updated
        time_now = datetime.now(timezone(my_timezone))
        time_now_str = time_now.strftime("%Y-%m-%d %H:%M:%S %Z%z")
        local_website_file.write('\n\t\tLast updated at ' + time_now_str)

        # finally, add the footer for the output file
        footer_file_handle = open(website_footer_filename, 'r')
        local_website_file.write('\n' + footer_file_handle.read())
        footer_file_handle.close()

        local_website_file.close()

        # upload the local website file to Amazon S3 bucket that is hosting the static website
        s3.Bucket(website_s3_bucket).upload_file('/tmp/' + website_filename, website_filename, ExtraArgs={'ContentType':'text/html'}, Config=s3_transfer_config)
        print('>>uploaded new html file to Amazon S3 bucket: /tmp/' + website_filename + ' -> [' + website_s3_bucket + ']' + website_filename)

        # check if the error html file exists in the Amazon S3 bucket, if not then upload it
        try:
            s3.Object(website_s3_bucket, error_filename).load()

        except botocore.exceptions.ClientError as e:
            s3.Bucket(website_s3_bucket).upload_file('./html/' + error_filename, error_filename, ExtraArgs={'ContentType':'text/html'}, Config=s3_transfer_config)
            print('>>error.html not found in Amazon S3 bucket. uploaded ./html/' + error_filename + ' -> [' + website_s3_bucket + ']' + error_filename)

        # write current covid case details to history file
        local_covid_cases_history_filename = '/tmp' + covid_cases_history_filename.replace(artefacts_s3_key_prefix,'')

        try:
            s3.Object(artefacts_s3_bucket, covid_cases_history_filename).load()
            print('>>previous covid-19 cases file found. Current data will be appended to it')
            s3.Bucket(artefacts_s3_bucket).download_file(covid_cases_history_filename, local_covid_cases_history_filename, Config=s3_transfer_config)
            print('>>downloaded previous covid-19 cases file [' + artefacts_s3_bucket + ']' + covid_cases_history_filename + ' -> ' + local_covid_cases_history_filename)
            
            # open local copy of previous covid-19 cases file in append mode
            covid_cases_history_file_handle = open(local_covid_cases_history_filename,'a')

        except botocore.exceptions.ClientError as e:
            # no previous covid-19 cases history file found, create a new file
            print('>>no previous covid-19 cases file found. New file will be created with current data')
            covid_cases_history_file_handle = open(local_covid_cases_history_filename, 'w')
           
        covid_cases_history_file_handle.write(report_period + csv_delimiter + total_local_acquired_cases + csv_delimiter + interstate_acquired_cases + 
                                                csv_delimiter + overseas_acquired_cases + csv_delimiter + total_cases + csv_delimiter + active_cases_local + 
                                                csv_delimiter + active_cases_interstate + csv_delimiter + active_cases_overseas + csv_delimiter + total_tests +
                                                '\n')
        covid_cases_history_file_handle.close()

        # upload the local covid-19 cases history file to artefacts s3 bucket
        s3.Bucket(artefacts_s3_bucket).upload_file(local_covid_cases_history_filename, covid_cases_history_filename, Config=s3_transfer_config)
        print('>>uploaded updated covid-19 cases file to artefacts Amazon S3 bucket: ' + local_covid_cases_history_filename + ' -> [' + artefacts_s3_bucket + ']' + covid_cases_history_filename)
        
        # write current vaccination details to history file
        local_covid_vaccination_history_filename = '/tmp' + covid_vaccination_history_filename.replace(artefacts_s3_key_prefix,'')

        try:
            s3.Object(artefacts_s3_bucket, covid_vaccination_history_filename).load()
            print('>>previous covid-19 vaccination file found. Current data will be appended to it')
            s3.Bucket(artefacts_s3_bucket).download_file(covid_vaccination_history_filename, local_covid_vaccination_history_filename, Config=s3_transfer_config)
            print('>>downloaded previous covid-19 vaccination file [' + artefacts_s3_bucket + ']' + covid_vaccination_history_filename + ' -> ' + local_covid_vaccination_history_filename)
            
            # open local copy of previous covid vaccination history file in append mode
            covid_vaccination_history_file_handle = open(local_covid_vaccination_history_filename, 'a')

        except botocore.exceptions.ClientError as e:
            # no previous covid vaccination history file found, create a new file
            print('>>no previous covid-19 vaccination file found. New file will be created with current data')
            covid_vaccination_history_file_handle = open(local_covid_vaccination_history_filename, 'w')

        covid_vaccination_history_file_handle.write(report_period + csv_delimiter + vaccination_first_dose + csv_delimiter + vaccination_second_dose +
                                            csv_delimiter + vaccination_total + '\n')
        covid_vaccination_history_file_handle.close()

        # upload the local covid-19 vaccination history file to artefacts s3 bucket
        s3.Bucket(artefacts_s3_bucket).upload_file(local_covid_vaccination_history_filename, covid_vaccination_history_filename, Config=s3_transfer_config)
        print('>>uploaded updated covid-19 vaccination file to artefacts Amazon S3 bucket: ' + local_covid_vaccination_history_filename + ' -> [' + artefacts_s3_bucket + ']' + covid_vaccination_history_filename)
        
        # update the last date processed file
        local_last_date_processed_filename = '/tmp' + last_date_processed_filename.replace(artefacts_s3_key_prefix,'')

        local_last_date_processed_file_handle = open(local_last_date_processed_filename, 'w')
        local_last_date_processed_file_handle.write(report_period)
        local_last_date_processed_file_handle.close()

        # upload the local last_date_processed file to s3 bucket
        response = s3.Bucket(artefacts_s3_bucket).upload_file(local_last_date_processed_filename, last_date_processed_filename, Config=s3_transfer_config)
        print('>>updated last_date_processed file [report period=' + report_period + ']' + local_last_date_processed_filename + ' -> [' + artefacts_s3_bucket + ']' + last_date_processed_filename)
        
        print('>>sending slack message to inform that website has been updated')
        send_slack_message('COVID-19 cases and vaccination history website has been updated with new information [' + report_period + '].')
        return 'new covid-19 cases and vaccination information found - website updated'
    else:
        print('>>retrieved covid-19 case details have already been processed in previous run - skipping')
        return 'no new covid-19 cases and vaccination information found'

def lambda_handler(event, context):
    status = check_for_covid_cases_updates()
    return {
        'statusCode': 200,
        'body': json.dumps(status)
    }





