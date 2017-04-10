#!/usr/bin/env python
"""

rubrik - Uses Rubrik REST API to get summary of performance stats.

API Explorer:  https://rubrik/docs/v1
Internal API Explorer:  https://rubrik/docs/internal/playground

NOTE:  These REST API calls are now considered INTERNAL, so if history is any guide, you can 
expect them to break each time you upgrade. :-)

"""
import json
import time
import requests
import logging.config
from requests.auth import HTTPBasicAuth
from credentials import RUBRIK_USER  # Login info now stored in credentials.py
from credentials import RUBRIK_PASSWORD  # Login info now stored in credentials.py

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
RUBRIK_URL = "https://rubrik"
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
# ===============================================================================


class RubrikData:
    """This class will contain all of the data gathered during processing"""
    def __init__(self):
        self.iops = []
        self.throughput = []
        self.ingest = []
        self.streams = []
        self.success_count = 0
        self.failure_count = 0
        self.running_count = 0
        self.total = 0
        self.used = 0
        self.available = 0
        self.avg_growth_per_day = 0
        self.ingested_yesterday = 0
        self.ingested_today = 0
        self.node_status = "ERR"


class RubrikNotConnectedException(Exception):
    pass


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""
        self.session = None
        self.data = RubrikData()
        self.token = None
        self.detail_report_id = None


def get_rubrik_token(rubrik_monitor):
    """This function will create a request session and get a login session token from the Rubrik
       According to the docs the session token is valid for 3 hours after last use."""

    logger = logging.getLogger(__name__)

    # Create Session object to persist JSESSIONID cookie (so the next requests to Rubrik will work)
    rubrik_monitor.session = requests.Session()
    rubrik_monitor.session.headers.update({'content-type': 'application/json'})
    rubrik_monitor.session.auth = (RUBRIK_USER, RUBRIK_PASSWORD)

    try:
        # For all our requests, use the verify=False to ignore certificate errors
        r = rubrik_monitor.session.post(RUBRIK_URL + "/api/v1/session", verify=False)
    except (requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError) as e:
        logger.warning("Error making request to " + RUBRIK_URL + "/login.")
        return None

    result = json.loads(r.text)
    #
    # When successful, login call returns
    # {
    #     "id": "00000000-0000-0000-0000-000000000000",
    #     "userId": "00000000-0000-0000-0000-000000000000",
    #     "token": "00000000-0000-0000-0000-000000000000"
    # }
    # Otherwise it returns
    # {"errorType":"user_error","message":"Incorrect Username/Password","cause":null}
    #
    try:
        return result["token"]
    except KeyError:
        logger.error("Not connected to Rubrik: " + result["message"])
        return None


def generate_json(rubrik_monitor):
    """This function will connect to the Rubrik web server, parse data and store the output in rubrik_monitor.json"""

    logger = logging.getLogger("rubrik")

    # The token stores a session credential and is used for each call to the server.
    token = rubrik_monitor.token
    if token is None:
        token = rubrik_monitor.token = get_rubrik_token(rubrik_monitor)
        if token is None:       # If still no token, just fail and come back in 60 seconds.
            rubrik_monitor.json = json.dumps({"error": "Error getting login token from Rubrik"}, indent=4)
            return

    # Add the token to the authorization header.
    headers = {
                'content-type': 'application/json, charset=utf-8',
                'Authorization': 'Bearer ' + rubrik_monitor.token
               }

    try:
        # Summary Report
        # The report structure has changed.  First we must get the ID of the report we need
        detail_report_id = rubrik_monitor.detail_report_id
        if detail_report_id is None:
            endpoint = "/api/internal/report?report_type=Canned&search_text=Protection Tasks Details"
            r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
            if r.status_code != 200:
                raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
            detail_report_id = rubrik_monitor.detail_report_id = json.loads(r.text)["data"][0]["id"]

        # Now we call the report
        endpoint = "/api/internal/report/" + detail_report_id + "/chart?timezone_offset=0&chart_id=chart0"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + r.text)
        chart_data = json.loads(r.text)[0]["chartData"]
        for column in chart_data:
            if column["label"] == "Succeeded":
                rubrik_monitor.data.success_count = int(column["columnData"][0]["value"])
            if column["label"] == "Failed":
                rubrik_monitor.data.failure_count = int(column["columnData"][0]["value"])
            if column["label"] == "Running":
                rubrik_monitor.data.running_count = int(column["columnData"][0]["value"])

        # Storage stats
        # Note that "used" here includes system space.  We're more interested in snapshot space
        # so we'll get a used value in the next query.
        endpoint = "/api/internal/stats/system_storage"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        # Grab the data and convert to gigabytes (rounding up)
        rubrik_monitor.data.total = int(json.loads(r.text)["total"] / (1000 * 1000 * 1000))
        rubrik_monitor.data.available = int(json.loads(r.text)["available"] / (1000 * 1000 * 1000))

        # Snapshot stats
        # For some reason this value is returned as a string by the API.
        endpoint = "/api/internal/stats/snapshot_storage/physical"
        r = rubrik_monitor.session.get(
            RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        # Grab the data, convert from string and convert to gigabytes (rounding up)
        rubrik_monitor.data.used = int(int(json.loads(r.text)["value"]) / (1000 * 1000 * 1000))

        # Average Storage Growth Per Day
        endpoint = "/api/internal/stats/average_storage_growth_per_day"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        # Grab data and convert to gigabytes (rounding up)
        rubrik_monitor.data.avg_growth_per_day = int(json.loads(r.text)["bytes"] / (1000 * 1000 * 1000))

        # Physical Ingest per day (each stat covers a 24 hour day)
        # The values returned with -1day are different than when using -2day or higher (and they seem wrong)
        # So we pull in the values for -2day instead.
        endpoint = "/api/internal/stats/physical_ingest_per_day/time_series?range=-2day"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        # Grab data and convert to gigabytes (rounding up)
        rubrik_monitor.data.ingested_yesterday = int(json.loads(r.text)[-2]["stat"] / (1000 * 1000 * 1000))
        rubrik_monitor.data.ingested_today = int(json.loads(r.text)[-1]["stat"] / (1000 * 1000 * 1000))

        # Node Status
        endpoint = "/api/internal/cluster/me/node"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        status_json = json.loads(r.text)
        system_status = "OK"
        for x in range(0, status_json["total"]):
            if status_json["data"][x]["status"] != "OK":
                system_status = status_json["data"][x]["status"]
        rubrik_monitor.data.node_status = system_status

        # Current Streams
        endpoint = "/api/internal/stats/streams/count"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        streams = json.loads(r.text)["count"]

        # IOPS/Throughput
        endpoint = "/api/internal/cluster/me/io_stats?range=-10sec"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " +  endpoint + " " + r.text)
        iops_reads = json.loads(r.text)["iops"]["readsPerSecond"][0]["stat"]
        iops_writes = json.loads(r.text)["iops"]["writesPerSecond"][0]["stat"]
        throughput_reads = json.loads(r.text)["ioThroughput"]["readBytePerSecond"][0]["stat"]
        throughput_writes = json.loads(r.text)["ioThroughput"]["writeBytePerSecond"][0]["stat"]
        # convert byte_reads from Bytes to Megabytes
        throughput_reads = int(throughput_reads / (1024 * 1024))  # Round up
        throughput_writes = int(throughput_writes / (1024 * 1024))  # Round up

        # PhysicalIngest (Live data)
        endpoint = "/api/internal/stats/physical_ingest/time_series?range=-10sec"
        r = rubrik_monitor.session.get(RUBRIK_URL + endpoint, verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting " + endpoint + " " + r.text)
        ingest = json.loads(r.text)[0]["stat"]
        # convert byte_reads from Bytes to Megabytes
        ingest = int(ingest / (1024 * 1024))  # Round up

        # Save stat datapoints to our persistent monitor object
        rubrik_monitor.data.iops.append(iops_reads + iops_writes)
        rubrik_monitor.data.throughput.append(throughput_reads + throughput_writes)
        rubrik_monitor.data.ingest.append(ingest)
        rubrik_monitor.data.streams.append(streams)

        # If we already have the max number of datapoints in our list, delete the oldest item
        if len(rubrik_monitor.data.iops) > MAX_DATAPOINTS:
            del (rubrik_monitor.data.iops[0])
            del (rubrik_monitor.data.throughput[0])
            del (rubrik_monitor.data.ingest[0])
            del (rubrik_monitor.data.streams[0])

        # Format our output as json under the stats name
        output = json.dumps({"stats": rubrik_monitor.data.__dict__})

        # ====================================
        # Generate JSON output and assign to rubrik_monitor object (for return back to caller module)
        rubrik_monitor.json = output

        logger.debug(rubrik_monitor.json)

    except Exception as error:
        logger.error("Error getting data from Rubrik: " + str(error))
        rubrik_monitor.json = json.dumps({"error": "Error getting data from Rubrik"}, indent=4)
        rubrik_monitor.token = None     # Reset login
        rubrik_monitor.session = None   # Reset HTTP session



#
# ======================================================
# __main__
#
# If you run this module by itself, it will instantiate
# the MonitorJSON class and start an infinite loop
# printing data.
# ======================================================
#
if __name__ == '__main__':

    # When run by itself, we need to create the logger object (which is normally created in webserver.py)
    try:
        f = open("log_settings.json", 'rt')
        log_config = json.load(f)
        f.close()
        logging.config.dictConfig(log_config)
    except FileNotFoundError as e:
        print("Log configuration file not found: " + str(e))
        logging.basicConfig(level=logging.DEBUG)        # fallback to basic settings
    except json.decoder.JSONDecodeError as e:
        print("Error parsing logger config file: " + str(e))
        raise

    monitor = MonitorJSON()
    while True:
        main_logger = logging.getLogger(__name__)
        generate_json(monitor)
        # Wait X seconds for the next iteration
        main_logger.debug("Waiting for " + str(SAMPLE_INTERVAL) + " seconds")
        time.sleep(SAMPLE_INTERVAL)
