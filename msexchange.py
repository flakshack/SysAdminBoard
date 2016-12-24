#!/usr/bin/env python
"""msexchange - This script will contact the pyPerfmon webservice on some Exchange servers to get perfmon data"""
import json
import time
from datetime import datetime
from urllib.request import urlopen
import logging.config

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
SAMPLE_INTERVAL = 60    # How often do we update the performance counter data
MAX_DATAPOINTS = 30     # How many datapoints to we keep
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.edge1_send_total = 0
        self.edge1_receive_total = 0
        self.edge1_previous_send_total = 0
        self.edge1_previous_receive_total = 0
        self.edge1_send_datapoints = []
        self.edge1_receive_datapoints = []
        self.edge2_send_total = 0
        self.edge2_receive_total = 0
        self.edge2_previous_send_total = 0
        self.edge2_previous_receive_total = 0
        self.edge2_send_datapoints = []
        self.edge2_receive_datapoints = []
        self.outlook1_rpc_avg_latency = []
        self.outlook1_rpc_active_users = []
        self.outlook1_rpc = 0
        self.outlook1_rpc_total = []
        self.outlook2_rpc_avg_latency = []
        self.outlook2_rpc_active_users = []
        self.outlook2_rpc_total = []
        self.outlook2_rpc = 0
        self.datetime = datetime(2000, 1, 1)

        self.json = json.dumps({
            "edge1_send_datapoints": [0],
            "edge1_receive_datapoints": [0],
            "edge1_send_total": "--",
            "edge1_receive_total": "--",
            "edge2_send_datapoints": [0],
            "edge2_receive_datapoints": [0],
            "edge2_send_total": "--",
            "edge2_receive_total": "--",
            "outlook1_rpc_avg_latency": [],
            "outlook1_rpc_active_users": [],
            "outlook1_rpc_total": [],
            "outlook2_rpc_avg_latency": [],
            "outlook2_rpc_active_users": [],
            "outlook2_rpc_total": []
        })


def generate_json(perf_monitor):
    """This function is a callback that is executed as a separate thread from the webserver"""
    logger = logging.getLogger("msexchange")

    # ====================EDGE1=====================
    try:
        response = urlopen('http://edge1:8001')
        html = (response.read()).decode('utf-8')
        logger.debug("edge1:" + html)
        data = json.loads(html)
    except Exception as error:
        logger.error("Error getting data from edge1: " + str(error))
        perf_monitor.json = json.dumps({"error": "Error with edge1: " + str(error)})
        return

    smtp_send_total = int(data["smtp_send_total"])
    smtp_receive_total = int(data["smtp_receive_total"])

    if perf_monitor.edge1_send_total == 0:        # If this is the first run, just set it to zero
        smtp_send_delta = 0
        smtp_receive_delta = 0
    else:
        # Calculate the delta by old total minus new total
        smtp_send_delta = smtp_send_total - perf_monitor.edge1_send_total
        smtp_receive_delta = smtp_receive_total - perf_monitor.edge1_receive_total

    # Add the delta to our datapoints lists
    perf_monitor.edge1_send_datapoints.append(smtp_send_delta)
    perf_monitor.edge1_receive_datapoints.append(smtp_receive_delta)

    # The Send/Recieve_Total counters are since last server reboot.  Instead of showing that total,
    # we start at 0 for the day, then reset each new day.
    if perf_monitor.datetime.date() != datetime.today().date():
        perf_monitor.edge1_send_total = 0
        perf_monitor.edge1_receive_total = 0
        perf_monitor.edge1_previous_send_total = smtp_send_total
        perf_monitor.edge1_previous_receive_total = smtp_receive_total
    else:            #
        perf_monitor.edge1_send_total = smtp_send_total - perf_monitor.edge1_previous_send_total
        perf_monitor.edge1_receive_total = smtp_receive_total - perf_monitor.edge1_previous_receive_total

    # If we've reached the max datapoints, delete the oldest
    if len(perf_monitor.edge1_send_datapoints) >= MAX_DATAPOINTS:
        del(perf_monitor.edge1_send_datapoints[0])
    if len(perf_monitor.edge1_receive_datapoints) >= MAX_DATAPOINTS:
        del(perf_monitor.edge1_receive_datapoints[0])

    # ====================EDGE2=====================
    try:
        response = urlopen('http://edge2:8001')
        html = (response.read()).decode('utf-8')
        logger.debug("edge2:" + html)
        data = json.loads(html)
    except Exception as error:
        logger.error("Error getting data from edge2: " + str(error))
        perf_monitor.json = json.dumps({"error": "Error with edge2: " + str(error)})
        return

    smtp_send_total = int(data["smtp_send_total"])
    smtp_receive_total = int(data["smtp_receive_total"])

    if perf_monitor.edge2_send_total == 0:        # If this is the first run, just set it to zero
        smtp_send_delta = 0
        smtp_receive_delta = 0
    else:
        # Calculate the delta by old total minus new total
        smtp_send_delta = smtp_send_total - perf_monitor.edge2_send_total
        smtp_receive_delta = smtp_receive_total - perf_monitor.edge2_receive_total

    # Add the delta to our datapoints lists
    perf_monitor.edge2_send_datapoints.append(smtp_send_delta)
    perf_monitor.edge2_receive_datapoints.append(smtp_receive_delta)

    # The Send/Recieve_Total counters are since last server reboot.  Instead of showing that total,
    # we start at 0 for the day, then reset each new day.
    if perf_monitor.datetime.date() != datetime.today().date():
        perf_monitor.edge2_send_total = 0
        perf_monitor.edge2_receive_total = 0
        perf_monitor.edge2_previous_send_total = smtp_send_total
        perf_monitor.edge2_previous_receive_total = smtp_receive_total
        perf_monitor.datetime = datetime.today()
    else:            #
        perf_monitor.edge2_send_total = smtp_send_total - perf_monitor.edge2_previous_send_total
        perf_monitor.edge2_receive_total = smtp_receive_total - perf_monitor.edge2_previous_receive_total

    # If we've reached the max datapoints, delete the oldest
    if len(perf_monitor.edge2_send_datapoints) >= MAX_DATAPOINTS:
        del(perf_monitor.edge2_send_datapoints[0])
    if len(perf_monitor.edge2_receive_datapoints) >= MAX_DATAPOINTS:
        del(perf_monitor.edge2_receive_datapoints[0])

    # CAS Perf Data Format: {"rpc_avg_latency": 7.0, "rpc_active_users": 22.0, "rpc_total": 30777797.0}
    # ====================OUTLOOK1=====================
    try:
        response = urlopen('http://outlook1:8002')
        html = (response.read()).decode('utf-8')
        logger.debug("outlook1:" + html)
        data = json.loads(html)
    except Exception as error:
        logger.error("Error getting data from outlook1: " + str(error))
        perf_monitor.json = json.dumps({"error": "Error with outlook1: " + str(error)})
        return

    # Add the datapoints
    perf_monitor.outlook1_rpc_active_users.append(int(data["rpc_active_users"]))
    perf_monitor.outlook1_rpc_avg_latency.append(int(data["rpc_avg_latency"]))

    # RPC count is a total, so convert it to deltas
    current_rpc_total = int(data["rpc_total"])
    if perf_monitor.outlook1_rpc == 0:
        perf_monitor.outlook1_rpc_total = [0]
        perf_monitor.outlook1_rpc = current_rpc_total
    else:
        rpc_delta = current_rpc_total - perf_monitor.outlook1_rpc
        perf_monitor.outlook1_rpc_total.append(rpc_delta)
        perf_monitor.outlook1_rpc = current_rpc_total

    # If we've reached the max datapoints, delete the oldest
    if len(perf_monitor.outlook1_rpc_active_users) >= MAX_DATAPOINTS:
        del(perf_monitor.outlook1_rpc_active_users[0])
        del(perf_monitor.outlook1_rpc_avg_latency[0])
        del(perf_monitor.outlook1_rpc_total[0])

    # ====================OUTLOOK2=====================
    try:
        response = urlopen('http://outlook2:8001')
        html = (response.read()).decode('utf-8')
        logger.debug("outlook2:" + html)
        data = json.loads(html)
    except Exception as error:
        logger.error("Error getting data from: outlook2: " + str(error))
        perf_monitor.json = json.dumps({"error": "Error with outlook2: " + str(error)})
        return

    # Add the datapoints
    perf_monitor.outlook2_rpc_active_users.append(int(data["rpc_active_users"]))
    perf_monitor.outlook2_rpc_avg_latency.append(int(data["rpc_avg_latency"]))

    # RPC count is a total, so convert it to deltas
    current_rpc_total = int(data["rpc_total"])
    if perf_monitor.outlook2_rpc == 0:
        perf_monitor.outlook2_rpc_total = [0]
        perf_monitor.outlook2_rpc = current_rpc_total
    else:
        rpc_delta = current_rpc_total - perf_monitor.outlook2_rpc
        perf_monitor.outlook2_rpc_total.append(rpc_delta)
        perf_monitor.outlook2_rpc = current_rpc_total

    # If we've reached the max datapoints, delete the oldest
    if len(perf_monitor.outlook2_rpc_active_users) >= MAX_DATAPOINTS:
        del(perf_monitor.outlook2_rpc_active_users[0])
        del(perf_monitor.outlook2_rpc_avg_latency[0])
        del(perf_monitor.outlook2_rpc_total[0])

    # Create the JSON string for output
    perf_monitor.json = json.dumps({
        "edge1_send_datapoints": perf_monitor.edge1_send_datapoints,
        "edge1_receive_datapoints": perf_monitor.edge1_receive_datapoints,
        "edge1_send_total": perf_monitor.edge1_send_total,
        "edge1_receive_total": perf_monitor.edge1_receive_total,
        "edge2_send_datapoints": perf_monitor.edge2_send_datapoints,
        "edge2_receive_datapoints": perf_monitor.edge2_receive_datapoints,
        "edge2_send_total": perf_monitor.edge2_send_total,
        "edge2_receive_total": perf_monitor.edge2_receive_total,
        "outlook1_rpc_avg_latency": perf_monitor.outlook1_rpc_avg_latency,
        "outlook1_rpc_active_users": perf_monitor.outlook1_rpc_active_users,
        "outlook1_rpc_total": perf_monitor.outlook1_rpc_total,
        "outlook2_rpc_avg_latency": perf_monitor.outlook2_rpc_avg_latency,
        "outlook2_rpc_active_users": perf_monitor.outlook2_rpc_active_users,
        "outlook2_rpc_total": perf_monitor.outlook2_rpc_total
    })

    logger.debug(perf_monitor.json)


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
