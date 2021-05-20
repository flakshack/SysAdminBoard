#!/usr/bin/env python
"""vmware_view_host - Exports JSON files with CPU and RAM data for VMware ESX hosts


# Requires VMware Python SDK: pyvmomi
# https://code.google.com/p/pysphere/
# pip install pyvmomi

"""

from credentials import VMWARE_VCENTER_USERNAME
from credentials import VMWARE_VCENTER_PASSWORD
import operator
import time
import json
import logging.config
from pyVim.connect import SmartConnect
from pchelper import collect_properties
from pchelper import get_container_view
import pyVmomi
import ssl

__author__ = 'scott@flakshack.com (Scott Vintinner)'


# =================================SETTINGS======================================
# VCenter Servers
VCENTER_SERVERS = [
    {"name": "view-vcenter", "username": VMWARE_VCENTER_USERNAME, "password": VMWARE_VCENTER_PASSWORD}
]
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
MAX_HOST_RESULTS = 8
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        host_data = [{"name": "----", "status": 0, "cpu": [0, 0, 0, 0], "ram": 0}]
        self.json = json.dumps({"hosts": host_data}, indent=4)
        self.vcenter_servers = VCENTER_SERVERS


class ESXHost:
    all_hosts = []      # Static array containing all hosts

    def __init__(self, managed_object_reference, name):
        self.managed_object_reference = managed_object_reference
        self.name = name
        self.status = 0
        self.cpu_datapoints = []
        self.ram = 0
        self.ram_percent = 0
        self.relative_weight = 1
        self.__class__.all_hosts.append(self)     # Add self to static array

    def update_relative_weight(self):
        """The relative weight is used to determine how much we want to see the data of this Host."""
        self.relative_weight = 1
        # Add up all of the historical cpu datapoints (higher CPU = more weight)
        for i in self.cpu_datapoints:
            self.relative_weight += i
        # Multiply by the status value (so VMs with red alarm have most weight)
        self.relative_weight *= (self.status * 10)

    @classmethod
    def find_by_name(cls, managed_object_reference, name):
        for host in cls.all_hosts:
            if host.name == name:
                return host
        # if not found, create one and return it instead
        return ESXHost(managed_object_reference, name)


def hostname_from_fqdn(fqdn):
    """Will take a fully qualified domain name and return only the hostname."""
    split_fqdn = fqdn.split('.', 1)       # Split fqdn at periods, but only bother doing first split
    return split_fqdn[0]


def connect_vcenter(vcenter_server, vcenter_username, vcenter_password):
    """This function will connect to the specified vCenter server."""
    logger = logging.getLogger(__name__)
    # Disable certificate verification otherwise it will error
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    ssl_context.verify_mode = ssl.CERT_NONE

    server_instance = None
    try:
        logger.debug("Connecting to: " + vcenter_server)
        server_instance = SmartConnect(host=vcenter_server, user=vcenter_username,
                                       pwd=vcenter_password, sslContext=ssl_context)
        server_instance._stub.connectionPoolTimeout = -1    # Turn the connection timeout off (default 900 sec)
    except Exception as error:
        logger.error("Error connecting to " + vcenter_server + str(error))

    return server_instance


def update_host_data(server):
    """This function is called to update the HOST data for the specified vcenter server"""
    logger = logging.getLogger(__name__)
    # API:  HostSystem -
    # https://pubs.vmware.com/vsphere-51/index.jsp#com.vmware.wssdk.apiref.doc/vim.HostSystem.html
    # summary.overallStatus: general "health" value: gray, green, red, yellow
    # summary.quickStats.overallCpuUsage: Aggregated CPU usage across all cores on the host in MHz.
    # summary.quickStats.overallMemoryUsage: Physical memory usage on the host in MB.
    # hardware.memorySize:  Total available RAM in bytes.

    try:
        # Fast way of getting Host properties using PropertyCollector
        # https://github.com/vmware/pyvmomi/blob/master/docs/vmodl/query/PropertyCollector.rst
        logger.debug("Getting PropertyCollector for " + server["name"])
        container_view = get_container_view(server["conn"], obj_type=[pyVmomi.vim.HostSystem])
        query = [
            "name",
            "summary.overallStatus",
            "summary.quickStats.overallCpuUsage",
            "summary.quickStats.overallMemoryUsage",
            "hardware.memorySize"
        ]
        props = collect_properties(server["conn"], container_view,
                                   pyVmomi.vim.HostSystem, query, include_mors=True)

    except Exception as error:
        logger.error("Error collecting VMware Host data from " + server["name"] + str(error))
        raise

    # Loop through all of the ESX servers in props
    for prop_set in props:
        host_mor = prop_set["obj"]                      # Managed object reference
        host_name = prop_set["name"]
        host_name = hostname_from_fqdn(host_name)       # trim out the domain name
        host_status = prop_set["summary.overallStatus"]
        host_cpu = prop_set["summary.quickStats.overallCpuUsage"]
        host_ram = prop_set["summary.quickStats.overallMemoryUsage"]
        host_ram_max = prop_set["hardware.memorySize"]
        host_ram_max = int(host_ram_max / 1024 / 1024)      # Convert to Megabytes to match overallMemoryUsage

        host_ram_percent = int((host_ram / host_ram_max) * 100)  # Calculate RAM percentage

        logger.debug(host_name + " RAM: " + str(host_ram_percent) + "% CPU: " + str(host_cpu))

        # Convert ram into Gigabytes and round to 1 decimal place
        host_ram = int(host_ram / 1024)

        # Find/Create this host in our list of hosts and update the object's data
        host = ESXHost.find_by_name(host_mor, host_name)

        if host_status == "green":
            host.status = 1
        elif host_status == "yellow":
            host.status = 2
        elif host_status == "red":
            host.status = 3
        else:
            host.status = 0

        # Add the raw data to the ESXHost object
        # For RAM datapoints, we want to do a bar graph, so only include the current value
        host.ram = host_ram
        host.ram_percent = host_ram_percent

        # For CPU datapoints, we want to do a line graph, so we need a history
        if len(host.cpu_datapoints) == 0:                # first time through, initialize the list
            host.cpu_datapoints = [host_cpu]
        else:
            host.cpu_datapoints.append(host_cpu)
        # If we already have the max number of datapoints in our list, delete the oldest item
        if len(host.cpu_datapoints) >= MAX_DATAPOINTS:
            del(host.cpu_datapoints[0])

        # Update ranking value of this Host to determine if we should show it
        host.update_relative_weight()


#
#
#
#
def generate_json(vmware_monitor):
    """This is the main function.  It will connect to the vCenter server, obtain perf data and output files"""
    logger = logging.getLogger("vmware_view_host")

    # Process each vcenter server
    for server in vmware_monitor.vcenter_servers:
        logger.debug("Starting " + server["name"])
        if "conn" not in server:
            logger.debug(server["name"] + " not currently connected.")
            server["conn"] = connect_vcenter(server["name"], server["username"], server["password"])

        if server["conn"] is None:
            logger.warning("Unable to connect to " + server["name"] + " will retry in " +
                           str(SAMPLE_INTERVAL) + " seconds.")
            vmware_monitor.json = json.dumps({"vms": [{"error": "Unable to connect to " + server["name"] +
                                                                " will retry in " + str(SAMPLE_INTERVAL) +
                                                                " seconds."}]}, indent=4)
            return vmware_monitor   # Could not connect so return

        # Final test if we're connected
        try:
            if server["conn"].content.sessionManager.currentSession:
                logger.debug("Connected to " + server["name"] + " at " +
                             str(server["conn"].content.sessionManager.currentSession.loginTime))
        except Exception as error:
            logger.error("Final test: Error connecting to " + server["name"] + str(error))
            vmware_monitor.json = json.dumps({"vms": [{"error": "Unable to connect to " + server["name"] +
                                                                " will retry in " + str(SAMPLE_INTERVAL) +
                                                                " seconds."}]}, indent=4)
            return vmware_monitor  # Could not connect so return

        # Update all the ESX host objects for the specified vCenter server
        try:
            update_host_data(server)
        except Exception as error:
            logger.error("Error updating data from " + server["name"] + str(error))
            vmware_monitor.json = json.dumps({"vms": [{"error": "Error updating data from " + server["name"] +
                                                                " will retry in " + str(SAMPLE_INTERVAL) +
                                                                " seconds."}]}, indent=4)
            return vmware_monitor

    # Sort by relative weight
    ESXHost.all_hosts.sort(key=operator.attrgetter('relative_weight'), reverse=True)

    # We have all the data we need, so format and set output
    host_data = []
    for i, host in enumerate(ESXHost.all_hosts):

        # Generate the data sequence
        host_data.append({
            "name": host.name,
            "status": host.status,
            "cpu": host.cpu_datapoints,
            "ram": host.ram,
            "ram_percent": host.ram_percent
        })

        if i >= (MAX_HOST_RESULTS - 1):   # Don't return more hosts than we need
            break

    vmware_monitor.json = json.dumps({"hosts": host_data})

    logger.debug(vmware_monitor.json)

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
