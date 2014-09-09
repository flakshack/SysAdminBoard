#!/usr/bin/env python
"""vmware_host - Exports JSON files with CPU and RAM data for VMware ESX hosts



# Requires pysphere (VMware SDK for Python)
# https://code.google.com/p/pysphere/
# pip install -U pysphere

"""
from __future__ import division    # So division of integers will result in float

__author__ = 'scott@flakshack.com (Scott Vintinner)'

from credentials import VMWARE_VCENTER_USERNAME
from credentials import VMWARE_VCENTER_PASSWORD


#=================================SETTINGS======================================
# VCenter Servers
VCENTER_SERVERS = [
    {"name": "vcenter.yourcompany.domain", "username": VMWARE_VCENTER_USERNAME, "password": VMWARE_VCENTER_PASSWORD},
    {"name": "hs-vcenter.yourcompany.domain", "username": VMWARE_VCENTER_USERNAME, "password": VMWARE_VCENTER_PASSWORD},
    {"name": "view-vcenter.yourcompany.domain", "username": VMWARE_VCENTER_USERNAME, "password": VMWARE_VCENTER_PASSWORD}
]
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
MAX_HOST_RESULTS = 11
#===============================================================================

from pysphere import VIServer
import operator
import json
import time


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        host_data = [{"name": "----", "status": 0, "cpu": [0, 0, 0, 0], "ram": 0}]
        self.json = json.dumps({"hosts": host_data}, indent=4)


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


def output_message(message):
    """Simple error handling to output message in JSON."""
    print message
    return json.dumps({"hosts": [{"error": message}]}, indent=4)


def update_host_data(server):
    """This function is called to update the HOST data for the specified vcenter server"""

    if server.is_connected():

        # API:  HostSystem - https://pubs.vmware.com/vsphere-51/index.jsp#com.vmware.wssdk.apiref.doc/vim.HostSystem.html
        # summary.overallStatus: general "health" value: gray, green, red, yellow
        # summary.quickStats.overallCpuUsage: Aggregated CPU usage across all cores on the host in MHz.
        # summary.quickStats.overallMemoryUsage: Physical memory usage on the host in MB.
        # hardware.memorySize:  Total available RAM in bytes.

        query = [
            "name",
            "summary.overallStatus",
            "summary.quickStats.overallCpuUsage",
            "summary.quickStats.overallMemoryUsage",
            "hardware.memorySize"
        ]

        # Fast way of getting Host properties
        props = server._retrieve_properties_traversal(property_names=query, obj_type="HostSystem")


        for prop_set in props:
            host_mor = prop_set.Obj          # managed_object_reference
            host_status = 0
            host_cpu = 0
            host_ram = 0
            host_ram_max = 1
            host_name = ""

            # The properties aren't always returned in the order you expect, so we have to match them up
            for i in range(len(prop_set.PropSet)):
                if prop_set.PropSet[i].Name == "name":
                    host_name = prop_set.PropSet[i].Val
                    host_name = hostname_from_fqdn(host_name)
                elif prop_set.PropSet[i].Name == "summary.overallStatus":
                    host_status = prop_set.PropSet[i].Val
                elif prop_set.PropSet[i].Name == "summary.quickStats.overallCpuUsage":
                    host_cpu = prop_set.PropSet[i].Val
                elif prop_set.PropSet[i].Name == "summary.quickStats.overallMemoryUsage":
                    host_ram = prop_set.PropSet[i].Val
                elif prop_set.PropSet[i].Name == "hardware.memorySize":
                    host_ram_max = prop_set.PropSet[i].Val
                    host_ram_max = int(host_ram_max / 1024 / 1024)      # Convert to Megabytes to match overallMemoryUsage

            # Calculate RAM percentage
            host_ram_percent = int((host_ram / host_ram_max) * 100)

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




def generate_json(vmware_monitor):
    """This is the main function.  It will connect to the vCenter server, obtain perf data and output files"""

    # Process each vcenter server
    for vcenter in VCENTER_SERVERS:
        if "server" not in vcenter:
            vcenter["server"] = VIServer()     # variable to hold server connection (so we only login once, not each run).

        if not vcenter["server"].is_connected():
            try:
                vcenter["server"].connect(vcenter["name"], vcenter["username"], vcenter["password"])
            except Exception as error:
                vmware_monitor.json = output_message("Error connecting to vCenter server: " +
                                                     vcenter["name"] + ' ' + error.message)
                return

        if vcenter["server"].is_connected():
            # Update all the ESX host objects for the specified vCenter server
            try:
                update_host_data(vcenter["server"])
            except Exception as error:
                vmware_monitor.json = output_message("Error retrieving VMware data:" + error.message)
                return


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

    if __debug__:
        print vmware_monitor.json






# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)