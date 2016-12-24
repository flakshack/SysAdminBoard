#!/usr/bin/env python
"""snmp_interface: module called to generate SNMP monitoring data as JSON for display on the dashboard.

"""
from pysnmp.entity.rfc3413.oneliner import cmdgen
import time
import json
import logging.config
from credentials import SNMP_COMMUNITY

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
MAX_DATAPOINTS = 30
SAMPLE_INTERVAL = 60
GRAPH_TITLE = "Active PRI Lines"

# Cisco Voice Gateway Active Calls
# ISDN-MIB:isdnBearerOperStatus     1.3.6.1.2.1.10.20.1.2.1.1.2
# This is a table of all the PRI channels.  If the value is 4, there is an active call, so we will
# Run through the table to total the number of active calls.

# Enter the details for each SNMP counter.
# ip:  This is the IP address or resolvable host name
# community:  This is the SNMPv1 community that will grant access to read the OID (usually this is "public")
# oid:  This is the SNMP OID interface counter we'll be measuring.
# name:  This is the name of the device as it will appear on the graph
DEVICES = (
    {"ip": "cisco-clt-vg1", "community": SNMP_COMMUNITY, "oid": "1.3.6.1.2.1.10.20.1.2.1.1.2", "name": "CLT1"},
    {"ip": "cisco-clt-vg2", "community": SNMP_COMMUNITY, "oid": "1.3.6.1.2.1.10.20.1.2.1.1.2", "name": "CLT2"},
    {"ip": "cisco-rh-wan", "community": SNMP_COMMUNITY, "oid": "1.3.6.1.2.1.10.20.1.2.1.1.2", "name": "RH"},
    {"ip": "cisco-tri-wan", "community": SNMP_COMMUNITY, "oid": "1.3.6.1.2.1.10.20.1.2.1.1.2", "name": "TRI"}
)
# ================================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = output_message("Waiting " + str(SAMPLE_INTERVAL) + " seconds for first run", "")


class InterfaceDevice:
    all_devices = []    # Static array containing all devices

    def __init__(self, ip, community, oid, name):
        self.ip = ip
        self.community = community
        self.oid = oid
        self.name = name
        self.datapoints = []
        self.__class__.all_devices.append(self)     # Add self to static array


def get_snmp(device, community, snmp_oid):
    """This code will grab the contents of an SNMP table and count the instances of the value 4
    which represents active calls."""

    # Perform a synchronous SNMP GET
    cmd_gen = cmdgen.CommandGenerator()
    error_indication, error_status, error_index, var_binds = cmd_gen.bulkCmd(
        cmdgen.CommunityData(community), cmdgen.UdpTransportTarget((device, 161)), 0, 25, snmp_oid)

    snmp_value = None
    snmp_error = None

    if error_indication:                         # Check for SNMP errors
        snmp_error = str(error_indication)
    else:
        if error_status:
            snmp_error = error_status.prettyPrint()
        else:
            # This OID will return a table, so we will loop through the entries in the table
            snmp_value = 0
            for snmp_entry in var_binds:
                # Check if the value is 4 (active call) and increment the counter
                if int(snmp_entry[0][1]) == 4:
                    snmp_value += 1

    return snmp_value, snmp_error


def output_message(message, detail):
    """This function will output an error message formatted in JSON to display on the dashboard"""
    statusbar_output = {"graph": {"title": GRAPH_TITLE, "error": {"message": message, "detail": detail}}}
    output = json.dumps(statusbar_output)
    return output


def generate_json(snmp_monitor):
    """This function will take the device config and raw data (if any) from the snmp_monitor and output JSON data
    formatted for the StatusBar iPad App"""

    logger = logging.getLogger("snmp_interface_5")
    time_x_axis = time.strftime("%H:%M")         # Use the same time value for all samples per iteration
    statusbar_datasequences = []
    snmp_error = None

    logger.debug("SNMP generate_json started: " + time_x_axis)

    # Create a list of InterfaceDevices using the contants provided above
    if len(InterfaceDevice.all_devices) == 0:
        for device in DEVICES:
            InterfaceDevice(device["ip"], device["community"], device["oid"], device["name"])

    # Loop through each device, update the SNMP data
    for device in InterfaceDevice.all_devices:
        logger.debug(device.ip + " " + device.name + " " + device.oid)
        # Get the SNMP data
        try:
            snmp_value, snmp_error = get_snmp(device.ip, device.community, device.oid)
        except Exception as error:
            if not snmp_error:
                snmp_error = str(error)

        if snmp_error:
            logger.warning(snmp_error)
            break
        else:
            logger.debug("value:" + str(snmp_value))
            if len(device.datapoints) == 0:
                device.datapoints = [{"title": time_x_axis, "value": snmp_value}]
            else:
                device.datapoints.append({"title": time_x_axis, "value": snmp_value})
            # If we already have the max number of datapoints, delete the oldest item.
            if len(device.datapoints) >= MAX_DATAPOINTS:
                del(device.datapoints[0])

        # Generate the data sequence
        statusbar_datasequences.append({"title": device.name, "datapoints": device.datapoints})

        # Generate JSON output and assign to snmp_monitor object (for return back to caller module)
        statusbar_graph = {
            "title": GRAPH_TITLE, "type": "line",
            "refreshEveryNSeconds": SAMPLE_INTERVAL,
            "datasequences": statusbar_datasequences
        }
        statusbar_type = {"graph": statusbar_graph}
        snmp_monitor.json = json.dumps(statusbar_type)

    logger.debug(snmp_monitor.json)


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