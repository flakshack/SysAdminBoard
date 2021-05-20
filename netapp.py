#!/usr/bin/env python
"""

netapp - Uses the NetApp RestAPI to access NetApp data.

Docs: https://library.netapp.com/ecmdocs/ECMLP2856304/html/index.html
Examples: https://github.com/NetApp/ontap-rest-python/tree/master/examples/rest_api


"""
import json
import time
import logging.config
import base64
import requests
requests.packages.urllib3.disable_warnings()

from credentials import NETAPP_USER  # Login info now stored in credentials.py
from credentials import NETAPP_PASSWORD  # Login info now stored in credentials.py

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
NETAPP_URL = "https://netapp1/api"
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
# ===============================================================================


class NetAppData:
    """This class will contain all of the data gathered during processing"""
    def __init__(self):
        self.iops = []
        self.throughput = []
        self.latency = []
        self.node_status = "ERR"
        self.used = 0
        self.available = 0
        self.logical_used = 0
        self.saved = 0


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""
        self.session = None
        self.data = NetAppData()
        base64string = base64.encodebytes(
            ('%s:%s' % (NETAPP_USER, NETAPP_PASSWORD)).encode()
        ).decode().replace('\n', '')

        self.headers = {
            'authorization': "Basic %s" % base64string,
            'content-type': "application/json",
            'accept': "application/json"
        }


class NetAppRequestException(Exception):
    pass


def generate_json(netapp_monitor):
    """This function will connect to the NetApp RESTAPI, parse data and store the output in netapp_monitor.json"""

    logger = logging.getLogger("netapp")

    # Check if there is a working session and create a new one if it is not working
    if netapp_monitor.session is None:
        logger.debug("No existing REST API session, creating a new one.")
        # Create Session object that will allow us to issue commands without having to login each time
        netapp_monitor.session = requests.Session()
        netapp_monitor.session.headers.update({'content-type': 'application/json'})
        netapp_monitor.session.auth = (NETAPP_USER, NETAPP_PASSWORD)

    try:
        # ############ /cluster ###############
        logger.debug("Getting: " + NETAPP_URL + "/cluster?fields=metric")
        r = netapp_monitor.session.get(NETAPP_URL + "/cluster?fields=metric", verify=False)
        if r.status_code != 200:
            raise NetAppRequestException("Request error status: " + str(r.status_code) + " " + r.reason)
        cluster = r.json()  # Convert returned byte stream to json

        # IOPS/Throughput/Latency
        netapp_monitor.data.iops.append(cluster['metric']['iops']['total'])
        throughput = round((cluster['metric']['throughput']['total'])/1024/1024, 2)      # Convert from bytes to MB
        netapp_monitor.data.throughput.append(throughput)
        latency = round((cluster['metric']['latency']['total'])/1000,2)      # Convert from microseconds to milliseconds
        netapp_monitor.data.latency.append(latency)

        # Status
        netapp_monitor.data.node_status = cluster['metric']['status']

        # ############ /storage/cluster ###############
        logger.debug("Getting: " + NETAPP_URL + "/storage/cluster")
        r = netapp_monitor.session.get(NETAPP_URL + "/storage/cluster", verify=False)
        if r.status_code != 200:
            raise NetAppRequestException("Request error status: " + str(r.status_code) + " " + r.reason)
        storage = r.json()  # Convert returned byte stream to json

        # Status
        netapp_monitor.data.used = int(storage['block_storage']['used'] / (1024*1024*1024))
        netapp_monitor.data.available = int(storage['block_storage']['size'] / (1024*1024*1024))
        netapp_monitor.data.logical_used = int(storage['efficiency_without_snapshots']['logical_used'] / (1024 * 1024 * 1024))
        netapp_monitor.data.saved = int(storage['efficiency_without_snapshots']['savings'] / (1024 * 1024 * 1024))

        # If we already have the max number of datapoints in our list, delete the oldest item
        if len(netapp_monitor.data.iops) > MAX_DATAPOINTS:
            del(netapp_monitor.data.iops[0])
            del(netapp_monitor.data.latency[0])
            del(netapp_monitor.data.throughput[0])

        # Format our output as json under the stats name
        output = json.dumps({"stats": netapp_monitor.data.__dict__})

        # ====================================
        # Generate JSON output and assign to netapp_monitor object (for return back to caller module)
        netapp_monitor.json = output

        logger.debug(netapp_monitor.json)

    except Exception as error:
        logger.error("Error getting data from NetApp: " + str(error))
        netapp_monitor.json = json.dumps({"error": "Error getting data from NetApp"}, indent=4)
        netapp_monitor.session = None   # Reset HTTP session


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
