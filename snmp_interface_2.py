#!/usr/bin/env python
"""snmp_interface: module called to generate SNMP monitoring data formatted for use with StatusBoard iPad App



# How To Calculate Bandwidth Utilization Using SNMP
# http://www.cisco.com/en/US/tech/tk648/tk362/technologies_tech_note09186a008009496e.shtml
"""
from __future__ import division    # So division of integers will result in float
from pysnmp.entity.rfc3413.oneliner import cmdgen
import time
import json

__author__ = 'forge@flakshack.com (Scott Vintinner)'

# Simple HTTP Server for testing
# python -m SimpleHTTPServer 9000


#=================================SETTINGS======================================
MAX_DATAPOINTS = 30
SAMPLE_INTERVAL = 60
GRAPH_TITLE = "Bandwidth (Mbps)"

# Standard SNMP OIDs
# sysUpTime	    1.3.6.1.2.1.1.3.0    (this is hundreds of a second)
# 64-bit counters because 32-bit defaults rollover too quickly
# ifHCInOctets	1.3.6.1.2.1.31.1.1.1.6.interfacenumber
# ifHCOutOctets	1.3.6.1.2.1.31.1.1.1.10.interfacenumber


# Enter the details for each SNMP counter.
# ip:  This is the IP address or resolvable host name
# community:  This is the SNMPv1 community that will grant access to read the OID (usually this is "public")
# oid:  This is the SNMP OID interface counter we'll be measuring.
# uptime_oid:  This is the SNMP OID for the device's uptime (so we know what the time was when we measured the counter)
# name:  This is the name of the device as it will appear on the graph
DEVICES = (
    {"ip": "cisco-rh-wan", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.6.3", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "RH RX"},
    {"ip": "cisco-rh-wan", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.10.3", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "RH TX"},
    {"ip": "cisco-tri-wan", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.6.2", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "TRI RX"},
    {"ip": "cisco-tri-wan", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.10.2", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "TRI TX"},
    {"ip": "cisco-clt-asa1", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.6.2", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "INET RX"},
    {"ip": "cisco-clt-asa1", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.10.2", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "INET TX"},
    {"ip": "cisco-clt-wan", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.6.3", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "CLT TX"},
    {"ip": "cisco-clt-wan", "community": "public", "oid": "1.3.6.1.2.1.31.1.1.1.10.3", "uptime_oid": "1.3.6.1.2.1.1.3.0", "name": "CLT RX"}
)
#================================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = output_message("Waiting " + str(SAMPLE_INTERVAL) + " seconds for first run", "")


class InterfaceDevice:
    all_devices = []    # Static array containing all devices

    def __init__(self, ip, community, oid, uptime_oid, name):
        self.ip = ip
        self.community = community
        self.oid = oid
        self.uptime_oid = uptime_oid
        self.name = name
        self.snmp_data = []                 # Hold raw data
        self.datapoints = []                # Holds pretty data
        self.__class__.all_devices.append(self)     # Add self to static array


class SNMPDatapoint:
    def __init__(self, value, timeticks):
        self.value = value
        self.timeticks = timeticks



def get_snmp(device, community, snmp_oid, snmp_uptime_oid):
    """Returns the value of the specified snmp OID.
     Also gets the uptime (TimeTicks) so we know exactly when the sample was taken."""

    # Perform a synchronous SNMP GET
    cmd_gen = cmdgen.CommandGenerator()
    error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
        cmdgen.CommunityData(community), cmdgen.UdpTransportTarget((device, 161)), snmp_oid, snmp_uptime_oid
    )

    snmp_value = None
    snmp_error = None
    snmp_uptime_value = None

    if error_indication:                         # Check for SNMP errors
        snmp_error = str(error_indication)
    else:
        if error_status:
            snmp_error = error_status.prettyPrint()
        else:
            # varBinds are returned as SNMP objects, so convert to integers
            snmp_value = int(var_binds[0][1])
            snmp_uptime_value = int(var_binds[1][1])

    return snmp_value, snmp_uptime_value, snmp_error


def calculate_bps(current_sample_octets, current_sample_time, historical_sample_octets, historical_sample_time):
    """Calculate the bits-per-second based on the octets and timeticks (hundreths of a second)."""

    # When the SNMP counter reaches 18446744073709551615, it will rollover and reset to ZERO.
    # If this happens, we want to make sure we don't output a negative bps
    if current_sample_octets < historical_sample_octets:
        # If we reset to 0, add the max value of the octets counter
        current_sample_octets += 18446744073709551615

    delta = current_sample_octets - historical_sample_octets

    # SysUpTime is in TimeTicks (Hundreds of a second), so covert to seconds
    seconds_between_samples = (current_sample_time - historical_sample_time) / 100.0

    # Multiply octets by 8 to get bits
    bps = (delta * 8) / seconds_between_samples
    bps /= 1048576          # Convert to Mbps  (use 1024 for Kbps)
    bps = round(bps, 2)
    return bps


def output_message(message, detail):
    """This function will output an error message formatted in JSON to display on the StatusBoard app"""
    statusbar_output = {"graph": {"title": GRAPH_TITLE, "error": {"message": message, "detail": detail}}}
    output = json.dumps(statusbar_output)
    return output


def generate_json(snmp_monitor):
    """This function will take the device config and raw data (if any) from the snmp_monitor and output JSON data
    formatted for the StatusBar iPad App"""

    time_x_axis = time.strftime("%H:%M")         # Use the same time value for all samples per iteration
    statusbar_datasequences = []
    snmp_error = None

    if __debug__:
        print "SNMP generate_json started: " + time_x_axis

    # Create a list of InterfaceDevices using the contants provided above
    if len(InterfaceDevice.all_devices) == 0:
        for device in DEVICES:
            InterfaceDevice(device["ip"], device["community"], device["oid"], device["uptime_oid"], device["name"])

    # Loop through each device, update the SNMP data
    for device in InterfaceDevice.all_devices:

        # Get the SNMP data
        try:
            snmp_value, snmp_uptime_value, snmp_error = get_snmp(device.ip, device.community, device.oid, device.uptime_oid)
        except Exception as error:
            if not snmp_error:
                snmp_error = error.message

        if snmp_error:
            break
        else:
            # Add the raw SNMP data to a list
            if len(device.snmp_data) == 0:                # first time through, initialize the list
                device.snmp_data = [SNMPDatapoint(snmp_value, snmp_uptime_value)]
            else:
                device.snmp_data.append(SNMPDatapoint(snmp_value, snmp_uptime_value))
            # If we already have the max number of datapoints in our list, delete the oldest item
            if len(device.snmp_data) >= MAX_DATAPOINTS:
                del(device.snmp_data[0])

            # If we have at least 2 samples, calculate bps by comparing the last item with the second to last item
            if len(device.snmp_data) > 1:
                bps = calculate_bps(
                    device.snmp_data[-1].value,
                    device.snmp_data[-1].timeticks,
                    device.snmp_data[-2].value,
                    device.snmp_data[-2].timeticks
                )
                bps = round(bps, 2)
                if len(device.datapoints) == 0:
                    device.datapoints = [{"title": time_x_axis, "value": bps}]
                else:
                    device.datapoints.append({"title": time_x_axis, "value": bps})
                # If we already have the max number of datapoints, delete the oldest item.
                if len(device.datapoints) >= MAX_DATAPOINTS:
                    del(device.datapoints[0])

        # Generate the data sequence
        statusbar_datasequences.append({"title": device.name, "datapoints": device.datapoints})


    # If this is the first run through, show Initializing on iPad
    if snmp_error:
        # If we ran into an SNMP error, go ahead and write out the JSON file with the error
        snmp_monitor.json = output_message("Error retrieving SNMP data", snmp_error)

    elif len(InterfaceDevice.all_devices[-1].snmp_data) <= 2:
        snmp_monitor.json = output_message(
            "Initializing bandwidth dataset: " +
            str(SAMPLE_INTERVAL * (3 - len(InterfaceDevice.all_devices[-1].snmp_data))) +
            " seconds...", ""
        )
    else:
        # Generate JSON output and assign to snmp_monitor object (for return back to caller module)
        statusbar_graph = {
            "title": GRAPH_TITLE, "type": "line",
            "refreshEveryNSeconds": SAMPLE_INTERVAL,
            "datasequences": statusbar_datasequences
        }
        statusbar_type = {"graph": statusbar_graph}
        snmp_monitor.json = json.dumps(statusbar_type)

    if __debug__:
        print snmp_monitor.json



# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)