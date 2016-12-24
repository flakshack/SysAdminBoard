#!/usr/bin/env python
"""rubrik - Uses Rubrik REST API to get summary of performance stats.


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


def get_rubrik_token(rubrik_monitor):
    """This function will create a request session and get a login token from the Rubrik"""
    body = {
        "userId": RUBRIK_USER,
        "password": RUBRIK_PASSWORD
    }
    headers = {'content-type': 'application/json'}

    logger = logging.getLogger(__name__)

    # Create Session object to persist JSESSIONID cookie (so the next requests to Rubrik will work)
    rubrik_monitor.session = requests.Session()

    try:
        # For all our requests, use the verify=False to ignore certificate errors
        r = rubrik_monitor.session.post(RUBRIK_URL + "/login", data=json.dumps(body), verify=False, headers=headers)
    except (requests.exceptions.Timeout,
            requests.exceptions.ConnectionError,
            requests.exceptions.HTTPError) as e:
        logger.warning("Error making request to " + RUBRIK_URL + "/login.")
        return None

    result = json.loads(r.text)
    if result["status"] == "Failure":
        rubrik_monitor.token = None
        raise RubrikNotConnectedException("Not connected to Rubrik: " + result["description"])
    else:
        rubrik_monitor.token = result["token"]

    return rubrik_monitor.token


def generate_json(rubrik_monitor):
    """This function will connect to the Rubrik web server, parse data and store the output in rubrik_monitor.json"""

    logger = logging.getLogger("rubrik")

    headers = {'content-type': 'application/json, charset=utf-8'}

    # The token stores the REST API credentials and is used for each call to the server.
    token = rubrik_monitor.token
    if token is None:
        token = get_rubrik_token(rubrik_monitor)
        if token is None:       # If still no token, just fail and come back in 60 seconds.
            rubrik_monitor.json = json.dumps({"error": "Error getting login token from Rubrik"}, indent=4)
            return

    try:
        # Summary Report
        r = rubrik_monitor.session.post(
            RUBRIK_URL + "/report/backupJobs/summary",
            data=json.dumps({"reportType": "daily"}),
            auth=HTTPBasicAuth(token, ''), verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /report/backupJobs/summary: " + r.text)
        rubrik_monitor.data.success_count = json.loads(r.text)["successCount"]
        rubrik_monitor.data.failure_count = json.loads(r.text)["failureCount"]
        rubrik_monitor.data.running_count = json.loads(r.text)["runningCount"]

        # Storage stats
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/stats/systemStorage", auth=HTTPBasicAuth(token, ''), verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /stats/systemStorage: " + r.text)
        # Grab the data and convert to gigabytes (rounding up)
        rubrik_monitor.data.total = int(json.loads(r.text)["total"] / (1000 * 1000 * 1000))
        rubrik_monitor.data.used = int(json.loads(r.text)["used"] / (1000 * 1000 * 1000))
        rubrik_monitor.data.available = int(json.loads(r.text)["available"] / (1000 * 1000 * 1000))

        # Average Storage Growth Per Day
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/stats/averageStorageGrowthPerDay", auth=HTTPBasicAuth(token, ''), verify=False,
            headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /stats/averageStorageGrowthPerDay: " + r.text)
        # Grab data and convert to gigabytes (rounding up)
        rubrik_monitor.data.avg_growth_per_day = int(json.loads(r.text)["bytes"] / (1000 * 1000 * 1000))

        # Physical Ingest per day (each stat covers a 24 hour day)
        # There is currently a bug in the API where the first element is always zero, so we call it for 3 days worth
        # so it will correctly return data.
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/stats/physicalIngestPerDay?range=-2day", auth=HTTPBasicAuth(token, ''), verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /stats/physicalIngestPerDay?range=-2day: " + r.text)
        # Grab data and convert to gigabytes (rounding up)
        rubrik_monitor.data.ingested_yesterday = int(json.loads(r.text)[-2]["stat"] / (1000 * 1000 * 1000))
        rubrik_monitor.data.ingested_today = int(json.loads(r.text)[-1]["stat"] / (1000 * 1000 * 1000))

        # Node Status
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/system/node/status", auth=HTTPBasicAuth(token, ''), verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /system/node/status: " + r.text)
        status_json = json.loads(r.text)
        system_status = "OK"
        for x in range(0, 3):
            if status_json[x]["status"] != "OK":
                system_status = status_json[x]["status"]
        rubrik_monitor.data.node_status = system_status

        # Current Streams
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/stats/streams", auth=HTTPBasicAuth(token, ''), verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /stats/streams: " + r.text)
        streams = json.loads(r.text)["count"]

        # IOPS/Throughput
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/system/io?range=-10sec", auth=HTTPBasicAuth(token, ''), verify=False, headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /system/io?range=-10sec: " + r.text)
        iops_reads = json.loads(r.text)["iops"]["readsPerSecond"][0]["stat"]
        iops_writes = json.loads(r.text)["iops"]["writesPerSecond"][0]["stat"]
        throughput_reads = json.loads(r.text)["ioThroughput"]["readBytePerSecond"][0]["stat"]
        throughput_writes = json.loads(r.text)["ioThroughput"]["writeBytePerSecond"][0]["stat"]
        # convert byte_reads from Bytes to Megabytes
        throughput_reads = int(throughput_reads / (1024 * 1024))  # Round up
        throughput_writes = int(throughput_writes / (1024 * 1024))  # Round up

        # PhysicalIngest (Live data)
        r = rubrik_monitor.session.get(
            RUBRIK_URL + "/stats/physicalIngest?range=-10sec", auth=HTTPBasicAuth(token, ''),
            verify=False,
            headers=headers)
        if r.status_code != 200:
            raise RubrikNotConnectedException("Error getting /stats/PhysicalIngest?range=-10sec " + r.text)
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
