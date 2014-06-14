#!/usr/bin/env python
"""statusboard-snmp-environmental - Exports JSON file with SNMP data


Output data will look like this:

{"temperature": "75", "humidity": "50", "ups_load": "4.7", "runtime": "1:17"}

"""
from __future__ import division    # So division of integers will result in float

__author__ = 'forge@flakshack.com (Scott Vintinner)'

from pysnmp.entity.rfc3413.oneliner import cmdgen
import time
import json




# Simple HTTP Server for testing
# python -m SimpleHTTPServer 9000


#=================================SETTINGS======================================
SAMPLE_INTERVAL = 60
SNMP_COMMUNITY = "public"
#===============================================================================

class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = json.dumps(
            {
                "ups_load": "--",
                "runtime": "--",
                "temperature": "--",
                "hot_aisle": "--",
                "humidity": "--"
            }
            , indent=4
        )


def generate_json(snmp_monitor):
    """This function will take the device config and raw data (if any) from the snmp_monitor and output JSON data
    formatted for the StatusBar iPad App"""

    # Create the pysnmp SNMP CommandGenerator, used to get SNMP data
    cmd_gen = cmdgen.CommandGenerator()


    try:
        # ===============CLT NetBotz1 data
        error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
            cmdgen.CommunityData(SNMP_COMMUNITY),
            cmdgen.UdpTransportTarget(('10.4.50.235', 161)),
            "1.3.6.1.4.1.5528.100.4.1.1.1.9.636159851",     # Room Temp (Rack 4 Top)
            "1.3.6.1.4.1.5528.100.4.1.1.1.9.3031356659",    # Hot Aisle (HAC 2 Temp)
            "1.3.6.1.4.1.5528.100.4.1.2.1.8.1744856019"     # Humidity
        )

        if error_indication or error_status:
            clt_temperature = "XX"
            hot_aisle = "XX"
            clt_humidity = "XX"
        else:
            clt_temperature = int(var_binds[0][1])
            hot_aisle = int(var_binds[1][1])
            clt_humidity = int(var_binds[2][1])

        # ===============CLT NetBotz2 data
        error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
            cmdgen.CommunityData(SNMP_COMMUNITY),
            cmdgen.UdpTransportTarget(('10.4.50.236', 161)),
            "1.3.6.1.4.1.5528.100.4.1.1.1.9.2628357572",     # Cold Aisle (Rack 3 bottom Temp)
        )

        if error_indication or error_status:
            cold_aisle = "XX"
        else:
            cold_aisle = int(var_binds[0][1])


        # ============ CLT Symmetra data
        error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
            cmdgen.CommunityData(SNMP_COMMUNITY),
            cmdgen.UdpTransportTarget(("10.4.50.230", 161)),
            "1.3.6.1.4.1.318.1.1.1.2.2.3.0",                # UPS Runtime
            "1.3.6.1.4.1.318.1.1.1.9.3.3.1.7.1.1.1",        # UPS Load Phase 1
            "1.3.6.1.4.1.318.1.1.1.9.3.3.1.7.1.1.2",        # UPS Load Phase 2
            "1.3.6.1.4.1.318.1.1.1.9.3.3.1.7.1.1.3"         # UPS Load Phase 3
        )
        if error_indication or error_status:
            clt_runtime = "XX"
            clt_load = "XX"
        else:
            clt_runtime = int(var_binds[0][1]) / 100 / 60        # Convert TimeTicks to Seconds to minutes
            clt_runtime = int(clt_runtime)

            load_p1 = int(var_binds[1][1])
            load_p2 = int(var_binds[2][1])
            load_p3 = int(var_binds[3][1])

            clt_load = (load_p1 + load_p2 + load_p3) / 1000      # Convert to kVA
            clt_load = round(clt_load, 1)



        # ===============RH APC SMARTUPS  (Must be SNMPv1)
        error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
            cmdgen.CommunityData(SNMP_COMMUNITY, mpModel=0),       # mpModel=0 for SNMPv1
            cmdgen.UdpTransportTarget(("10.3.1.240", 161)),
            "1.3.6.1.4.1.318.1.1.10.1.3.3.1.4.1",               # Temperature
            "1.3.6.1.4.1.318.1.1.10.1.3.3.1.6.1",               # Humidity
            "1.3.6.1.4.1.318.1.1.1.4.2.3.0",                    # UPS Load Percent
            "1.3.6.1.4.1.318.1.1.1.2.2.3.0"                     # UPS Runtime
        )
        if error_indication or error_status:
            rh_temperature = "XX"
            rh_humidity = "XX"
            rh_load = "XX"
            rh_runtime = "XX"
        else:
            rh_temperature = int(var_binds[0][1])
            rh_humidity = int(var_binds[1][1])
            rh_load = int(var_binds[2][1])
            rh_runtime = int(var_binds[3][1]) / 100 / 60        # Convert TimeTicks to Seconds to minutes
            rh_runtime = int(rh_runtime)


        # ===============TRI APC SMARTUPS  (Must be SNMPv1)
        error_indication, error_status, error_index, var_binds = cmd_gen.getCmd(
            cmdgen.CommunityData(SNMP_COMMUNITY, mpModel=0),       # mpModel=0 for SNMPv1
            cmdgen.UdpTransportTarget(("10.10.1.13", 161)),
            "1.3.6.1.4.1.318.1.1.10.1.3.3.1.4.1",               # Temperature
            "1.3.6.1.4.1.318.1.1.10.1.3.3.1.6.1",               # Humidity
            "1.3.6.1.4.1.318.1.1.1.4.2.3.0",                    # UPS Load Percent
            "1.3.6.1.4.1.318.1.1.1.2.2.3.0"                     # UPS Runtime
        )
        if error_indication or error_status:
            tri_temperature = "XX"
            tri_humidity = "XX"
            tri_load = "XX"
            tri_runtime = "XX"
        else:
            tri_temperature = int(var_binds[0][1])
            tri_humidity = int(var_binds[1][1])
            tri_load = int(var_binds[2][1])
            tri_runtime = int(var_binds[3][1]) / 100 / 60        # Convert TimeTicks to Seconds to minutes
            tri_runtime = int(tri_runtime)


        # =========== Create Dictionary for JSON output
        snmp_data = {
            "cold_aisle": cold_aisle,
            "hot_aisle": hot_aisle,
            "clt_temp": clt_temperature,
            "clt_humidity": clt_humidity,
            "clt_load": clt_load,
            "clt_runtime": clt_runtime,
            "tri_temp": tri_temperature,
            "tri_humidity": tri_humidity,
            "tri_load": tri_load,
            "tri_runtime": tri_runtime,
            "rh_temp": rh_temperature,
            "rh_humidity": rh_humidity,
            "rh_load": rh_load,
            "rh_runtime": rh_runtime
        }

    except Exception as error:
        snmp_data = {"error": "There was a problem accessing SNMP data:" + error.message}

    snmp_monitor.json = json.dumps(snmp_data)

    if __debug__:
        print snmp_monitor.json

    return


# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)