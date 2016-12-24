#!/usr/bin/env python
"""nutanix_1 - Uses Nutanix REST API to get summary of performance stats.

Requires requests
pip install requests

"""
import json
import time
import requests
import logging.config
from credentials import NUTANIX_USER  # Login info now stored in credentials.py
from credentials import NUTANIX_PASSWORD  # Login info now stored in credentials.py

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
NUTANIX_URL = "https://pri-svr:9440/PrismGateway/services/rest/v1"
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
# ===============================================================================


class NutanixRequestException(Exception):
    pass


class NutanixData:
    """This class will contain all of the data gathered during processing"""
    def __init__(self):
        self.cluster_name = ""
        self.iops = []
        self.throughput = []
        self.latency = []
        self.replication = []
        self.usage_gbytes = 0
        self.capacity_gbytes = 0
        self.cpu_percent = []
        self.ram_percent = []


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""
        self.session = None
        self.data = NutanixData()


def generate_json(monitor):
    """
    This function will connect to the Nutanix cluster and retrieve performance data, which
    will be stored in json format in the json property.
    """

    logger = logging.getLogger("nutanix_1")
    # Really don't need to hear about connections being brought up again after server has closed it
    logging.getLogger("requests.packages.urllib3.connectionpool").setLevel(logging.WARNING)

    # Check if there is a working session and create a new one if it is not working
    if monitor.session is None:
        logger.debug("No existing REST API session, creating a new one.")
        # Create Session object that will allow us to issue commands without having to login each time
        monitor.session = requests.Session()
        monitor.session.headers.update({'content-type': 'application/json'})
        monitor.session.auth = (NUTANIX_USER, NUTANIX_PASSWORD)

    try:    # Try getting the cluster data
        logger.debug("Getting: " + NUTANIX_URL + "/cluster/")
        r = monitor.session.get(NUTANIX_URL + "/cluster/", verify=False)
        if r.status_code != 200:
            raise NutanixRequestException("Request error status: " + str(r.status_code) + " " + r.reason)
    except Exception as error:
        # If we couldn't connect, set the session object to None and try again next time
        logger.error("Unable to get  " + NUTANIX_URL + "/cluster/" + " " + str(error))
        monitor.json = json.dumps({"error": "Unable to get  " + NUTANIX_URL + "/cluster/" +
                                            " " + str(error)}, indent=4)
        monitor.session = None
        return

    cluster = r.json()       # Convert returned byte stream to json

    logger.debug("Data successfully collected from " + cluster["name"])
    iops = int(cluster["stats"]["controller_num_iops"])
    latency = round((int(cluster["stats"]["controller_avg_io_latency_usecs"])) / 1000, 2)  # convert to ms
    throughput = round((int(cluster["stats"]["controller_io_bandwidth_kBps"])) / 1024, 2)  # to MBps
    replication = int((int(cluster["stats"]["replication_transmitted_bandwidth_kBps"])) / 1024 * 8)  # to Mbps
    usage_gbytes = int(int(cluster["usageStats"]["storage.usage_bytes"]) / 1024 / 1024 / 1024)  # to GiB
    capacity_gbytes = int(int(cluster["usageStats"]["storage.capacity_bytes"]) / 1024 / 1024 / 1024)  # to GiB
    cpu_percent = round((int(cluster["stats"]["hypervisor_cpu_usage_ppm"])) / 10000, 2)   # convert to 2 digit percent
    ram_percent = round((int(cluster["stats"]["hypervisor_memory_usage_ppm"])) / 10000, 2)  # convert to 2 digit percent

    # To keep historical data, we store some values in an array
    monitor.data.cluster_name = cluster["name"]
    monitor.data.cpu_percent.append(cpu_percent)
    monitor.data.ram_percent.append(ram_percent)
    monitor.data.iops.append(iops)
    monitor.data.throughput.append(throughput)
    monitor.data.latency.append(latency)
    monitor.data.replication.append(replication)

    monitor.data.usage_gbytes = usage_gbytes
    monitor.data.capacity_gbytes = capacity_gbytes

    # If we already have the max number of datapoints in our list, delete the oldest item
    if len(monitor.data.iops) > MAX_DATAPOINTS:
        logger.debug("MAX_DATAPOINTS of " + str(MAX_DATAPOINTS) + " hit, removing oldest datapoints.")
        del (monitor.data.iops[0])
        del (monitor.data.throughput[0])
        del (monitor.data.latency[0])
        del (monitor.data.replication[0])
        del (monitor.data.cpu_percent[0])
        del (monitor.data.ram_percent[0])
#
    # Format our output as json under the stats name
    output = json.dumps({"stats": monitor.data.__dict__})

    # ====================================
    # Generate JSON output and assign to nutanix_monitor object (for return back to caller module)
    monitor.json = output

    logger.debug(monitor.json)


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

    test_monitor = MonitorJSON()
    while True:
        main_logger = logging.getLogger(__name__)
        generate_json(test_monitor)

        # Wait X seconds for the next iteration
        main_logger.debug("Waiting for " + str(SAMPLE_INTERVAL) + " seconds")
        time.sleep(SAMPLE_INTERVAL)
