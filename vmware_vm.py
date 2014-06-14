#!/usr/bin/env python
"""vmware_vm - Exports JSON files with CPU and RAM data for VMware VMs



# Requires pysphere (VMware SDK for Python)
# https://code.google.com/p/pysphere/
# pip install -U pysphere

"""
from __future__ import division    # So division of integers will result in float

__author__ = 'forge@flakshack.com (Scott Vintinner)'




#=================================SETTINGS======================================
VCENTER_SERVER = "vcenter.yourcompany.com"
VCENTER_USERNAME = "domain\\username"
VCENTER_PASSWORD = "******"
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
MAX_VM_RESULTS = 11              # Number of VMs to get data (should match html file)
#===============================================================================

from pysphere import VIServer
# from pysphere import MORTypes, vi_performance_manager
import operator
import time
import json

server = VIServer()     # Global variable to hold server connection (so we only login once, not each run).


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        # Set the default empty values for all VMs
        vms = []
        for i in range(MAX_VM_RESULTS):
            vms.append({"name": "----", "status": 0, "cpu": [0, 0, 0, 0]})
        self.json = json.dumps({"vms": vms}, indent=4)


class VMwareVM:
    all_vms = []      # Static array containing all hosts

    def __init__(self, managed_object_reference, name):
        self.managed_object_reference = managed_object_reference
        self.name = name
        self.cpu_datapoints = []
        self.cpu_count = 1                      # Number of vCPUs
        self.host_cpu_mhz = 1.0                 # Host CPU speed
        self.heartbeat_status = 0
        self.relative_weight = 0.0
        self.__class__.all_vms.append(self)     # Add self to static array

    @classmethod
    def find_by_name(cls, managed_object_reference, name):
        for vm in cls.all_vms:
            if vm.name == name:
                return vm
        # if not found, create one and return it instead
        return VMwareVM(managed_object_reference, name)

    def update_relative_weight(self):
        """The relative weight is used to determine how much we want to see the data of this VM."""
        self.relative_weight = 1
        # Add up all of the historical cpu datapoints (higher CPU = more weight)
        for i in self.cpu_datapoints:
            self.relative_weight += i
        # Multiply by the status value (so VMs with red alarm have most weight)
        self.relative_weight *= (self.heartbeat_status * 10)


class VMwareHost:
    """In order to calculate CPU used percent for VMs, we need to know Mhz speed of Host.  We update this list
    to make our search faster"""
    all_hosts = []      # Static array containing all hosts

    def __init__(self, managed_object_reference, name, hz):
        self.managed_object_reference = managed_object_reference
        self.name = name
        self.cpu_mhz = int(hz / (1000 * 1000))         # CPU speed
        self.__class__.all_hosts.append(self)     # Add self to static array

    @classmethod
    def get_mhz_by_host(cls, managed_object_reference):
        for host in cls.all_hosts:
            if host.managed_object_reference == managed_object_reference:
                return host.cpu_mhz


def output_message(message):
    """Simple error handling to output message in JSON."""
    print message
    return json.dumps({"vms": [{"error": message}]}, indent=4)


def generate_json(vmware_monitor):
    """This is the main function. It will connect to the vCenter server, obtain perf data and output json"""

    global server

    if not server.is_connected():
        try:
            server.connect(VCENTER_SERVER, VCENTER_USERNAME, VCENTER_PASSWORD)
        except Exception as error:
            vmware_monitor.json = output_message("Error connecting to vCenter server" + error.message)
            return

    if server.is_connected():
        # First we want to grab a list of all the hosts so we can determine the clock speed of the CPUs
        # API:  HostSystem - https://pubs.vmware.com/vsphere-51/index.jsp#com.vmware.wssdk.apiref.doc/vim.HostSystem.html

        if len(VMwareVM.all_vms) == 0:
            query = [
                "name",
                "hardware.cpuInfo.hz"
            ]
            try:
                # Fast way of getting Host properties
                host_props = server._retrieve_properties_traversal(property_names=query, obj_type="HostSystem")
            except Exception as error:
                vmware_monitor.json = output_message("Error retrieving VMware Host data" + error.message)
                return
            else:
                for prop_set in host_props:
                    host_mor = prop_set.Obj                 # managed_object_reference
                    host_hz = 0
                    host_name = "Error"
                    # The properties aren't always returned in the order you expect, so we have to match them up
                    for i in range(len(prop_set.PropSet)):
                        if prop_set.PropSet[i].Name == "name":
                            host_name = prop_set.PropSet[i].Val
                        elif prop_set.PropSet[i].Name == "hardware.cpuInfo.hz":
                            host_hz = prop_set.PropSet[i].Val
                    # Create host object so we can find Mhz later (object is stored in class array all_hosts)
                    VMwareHost(host_mor, host_name, host_hz)


        # API:  VirtualMachine - https://pubs.vmware.com/vsphere-50/index.jsp#com.vmware.wssdk.apiref.doc_50/vim.VirtualMachine.html
        # summary.overallStatus: general "health" value: gray, green, red, yellow
        # summary.quickStats.overallCpuUsage: Amount of CPU actually granted to the VM in Mhz
        # summary.quickStats.staticCpuEntitlement: Max CPU possible for the VM in Mhz
        # summary.quickStats.guestMemoryUsage: Active memory usage of the VM in MB.
        # summary.quickStats.staticMemoryEntitlement: Max CPU possible for the VM in MB
        # config.hardware.numCPU:  Number of virtual CPUs present in this virtual machine.
        # runtime.host:  The host that is responsible for running a virtual machine.

        query = [
            "name",
            "summary.overallStatus",
            "summary.quickStats.overallCpuUsage",
            "config.hardware.numCPU",               # This number is vCPU
            "runtime.host"
        ]


        try:
            # Fast way of getting VM properties
            props = server._retrieve_properties_traversal(property_names=query, obj_type="VirtualMachine")
        except Exception as error:
            vmware_monitor.json = output_message("Error retrieving VMware VM data" + error.message)
            return
        else:

            for prop_set in props:
                mor = prop_set.Obj          # managed_object_reference
                vm_name = "Error"
                vm_status = 0
                vm_cpu = 0
                vm_cpu_count = 0
                vm_host_mor = None

                # The properties aren't always returned in the order you expect, so we have to match them up
                for i in range(len(prop_set.PropSet)):
                    if prop_set.PropSet[i].Name == "name":
                        vm_name = prop_set.PropSet[i].Val
                    elif prop_set.PropSet[i].Name == "summary.overallStatus":
                        vm_status = prop_set.PropSet[i].Val
                    elif prop_set.PropSet[i].Name == "summary.quickStats.overallCpuUsage":
                        vm_cpu = prop_set.PropSet[i].Val
                    elif prop_set.PropSet[i].Name == "config.hardware.numCPU":
                        vm_cpu_count = prop_set.PropSet[i].Val
                    elif prop_set.PropSet[i].Name == "runtime.host":
                        vm_host_mor = prop_set.PropSet[i].Val

                # Check to see if this VM is in our list or create one if not found
                vm = VMwareVM.find_by_name(mor, vm_name)
                if vm_status == "green":
                    vm.heartbeat_status = 1
                elif vm_status == "yellow":
                    vm.heartbeat_status = 2
                elif vm_status == "red":
                    vm.heartbeat_status = 3
                else:
                    vm.heartbeat_status = 0

                # Store the cpu data in the object
                if len(vm.cpu_datapoints) == 0:
                    vm.cpu_datapoints = [vm_cpu]
                else:
                    vm.cpu_datapoints.append(vm_cpu)
                # If we already have the max number of datapoints in our list, delete the oldest item
                if len(vm.cpu_datapoints) >= MAX_DATAPOINTS:
                    del(vm.cpu_datapoints[0])

                vm.host_cpu_mhz = VMwareHost.get_mhz_by_host(vm_host_mor)        # Get the host hz per CPU
                vm.cpu_count = vm_cpu_count
                # Update ranking value of this VM to determine if we should show it
                vm.update_relative_weight()

            # Once we have finished updating our VM data, grab the top MAX_VM_RESULTS and output the JSON
            # Sort by relative weight
            VMwareVM.all_vms.sort(key=operator.attrgetter('relative_weight'), reverse=True)

            vms = []
            for i in range(MAX_VM_RESULTS):
                vms.append({
                    "name": VMwareVM.all_vms[i].name,
                    "status": VMwareVM.all_vms[i].heartbeat_status,
                    "cpu": VMwareVM.all_vms[i].cpu_datapoints,
                    "cpu_count": VMwareVM.all_vms[i].cpu_count,
                    "host_cpu_mhz": VMwareVM.all_vms[i].host_cpu_mhz,
                })

            vmware_monitor.json = json.dumps({"vms": vms})

            if __debug__:
                print vmware_monitor.json





# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)