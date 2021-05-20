#!/usr/bin/env python
"""prtg_wan_1: module called query PRTG API for bandwidth statistics

NOTES:
* PRTG API is GET only and doesn't use sessions, so we pass the username and passhash on each connection.
* We're using the table.json function to retrieve multiple sensor values at once. We filter the results by
using a tag we've assigned to the sensors in PRTG called "statusboard_wan."

* The JSON output from this module is still formatted in the old iPad Statusboard app format:

{"graph":
    {"title": "WAN Bandwidth (mbps)", "type": "line", "refreshEveryNSeconds": 60,
    "datasequences": [
    {"title": "RAL",
        "datapoints": [{"title": "17:11", "value": 0.0}, {"title": "17:17", "value": 0.0}, ....
    {"title": "TRI",
        "datapoints": [{"title": "17:11", "value": 0.0}, {"title": "17:12", "value": 0.0}, ....

"""
import time
import json
import logging.config
import requests
from credentials import PRTG_USERNAME
from credentials import PRTG_PASSHASH
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
MAX_DATAPOINTS = 120
SAMPLE_INTERVAL = 15
GRAPH_TITLE = "WAN (mbps)"
PRTG_AUTH = "&username=" + PRTG_USERNAME + "&passhash=" + PRTG_PASSHASH
PRTG_URL = ("https://prtg/api/table.json?" +
            "content=sensors&columns=objid,lastvalue&filter_tags=@tag(statusboard_wan1)")

# #### PRTG SENSORS #####
# The sensors are retrieved by a tag filter, but we'll use this list to help name them.
# id:  This is the PRTG sensor ID (displayed on the sensor web page or URL)
# name:  This is the name of the device as it will appear on the graph
PRTG_SENSORS = (
    {"objid": 7472, "name": "CLT"},
    {"objid": 7766, "name": "TRI"},
    {"objid": 7297, "name": "RH"},
    {"objid": 7295, "name": "RAL"}
)

# ================================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = output_message("Loading...", "")


class PRTGSensor:
    """We create a single object of this class and store all our data in it."""
    all_sensors = []    # Static array containing all sensors

    def __init__(self, sensor_id, sensor_name):
        self.objid = sensor_id
        self.name = sensor_name
        self.datapoints = []                 # Hold raw values from PRTG
        self.__class__.all_sensors.append(self)     # Add self to static array


class PRTGPausedException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class PRTGRequestException(Exception):
    pass


def output_message(message, detail):
    """This function will output an error message formatted in JSON to display on the StatusBoard app"""
    statusbar_output = {"graph": {"title": GRAPH_TITLE, "error": {"message": message, "detail": detail}}}
    output = json.dumps(statusbar_output)
    return output


def generate_json(prtg_monitor):
    """This function will connect to the PRTG server API and store the output in prtg_monitor.json"""

    logger = logging.getLogger("prtg_interface_1")
    time_x_axis = time.strftime("%H:%M")  # The time that we'll add to the X axis of the chart

    # Create a list of PRTGSensors using the contants provided above (we'll store the data in this object)
    if len(PRTGSensor.all_sensors) == 0:    # This is only done once
        for sensor in PRTG_SENSORS:
            PRTGSensor(sensor["objid"], sensor["name"])

    try:
        # ############ PRTG API CALL ###############
        logger.debug("Getting: " + PRTG_URL)
        r = requests.get(PRTG_URL + PRTG_AUTH, verify=False)
        if r.status_code != 200:
            raise PRTGRequestException("Request error status: " + str(r.status_code) + " " + r.reason)
        api_data = r.json()  # Convert returned byte stream to json

        # Loop through our list of sensors, match the object id with the item returned by the API call
        # and add a datapoint to our array.
        for sensor in PRTGSensor.all_sensors:
            for api_sensor in api_data["sensors"]:
                if api_sensor['lastvalue'] == '-':
                    raise PRTGPausedException(sensor.name)
                if sensor.objid == api_sensor["objid"]:
                    # The lastvalue_raw field is the bps divided by 8.  It doesn't make any sense
                    # why they store it this way instead of just storing the bits.  Seriously, WTF?
                    # The conversion from raw to mbps is lastvalue_raw*8/(1000*1000)
                    # Note we're using SI (decimal) notation here because that is what PRTG uses.
                    mbps = round(((api_sensor["lastvalue_raw"])*8)/1000000, 2)  # Convert from PRTG raw to mbps
                    sensor.datapoints.append({"title": time_x_axis, "value": mbps})

                    # If we already have the max number of datapoints, delete the oldest item.
                    if len(sensor.datapoints) >= MAX_DATAPOINTS:
                        del(sensor.datapoints[0])

        # #### Format the JSON data that is expected by the javascript front-end #####
        statusbar_datasequences = []
        for sensor in PRTGSensor.all_sensors:
            statusbar_datasequences.append({"title": sensor.name, "datapoints": sensor.datapoints})

        statusbar_graph = {
            "title": GRAPH_TITLE, "type": "line",
            "refreshEveryNSeconds": SAMPLE_INTERVAL,
            "datasequences": statusbar_datasequences
        }
        statusbar_type = {"graph": statusbar_graph}
        prtg_monitor.json = json.dumps(statusbar_type)

    except PRTGPausedException as sensor_name:

        logger.error("PRTG sensor " + str(sensor_name) + " is paused")
        prtg_monitor.json = output_message("PRTG sensor " + str(sensor_name) + " is paused",'')
        PRTGSensor.all_sensors = []  # Reset the saved data

    except Exception as error:
        logger.error("Error getting data from PRTG: " + str(error))
        prtg_monitor.json = output_message("Error getting data from PRTG", str(error))
        PRTGSensor.all_sensors = []  # Reset the saved data

    logger.debug(prtg_monitor.json)


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
