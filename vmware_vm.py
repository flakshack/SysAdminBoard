#!/usr/bin/env python
"""vmware_vm - Exports JSON files with CPU and RAM data for VMware VMs

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
VCENTER_SERVER = "vcenter"
VCENTER_USERNAME = VMWARE_VCENTER_USERNAME
VCENTER_PASSWORD = VMWARE_VCENTER_PASSWORD
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
MAX_VM_RESULTS = 11              # Number of VMs to get data (should match html file)
EXCLUDE_VM = ["NTNX"]            # VMs with any of the items in this list in their
#                                  name will be excluded from results (ex: "NTNX-123")
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        # Set the default empty values for all VMs
        vms = []
        for i in range(MAX_VM_RESULTS):
            vms.append({"name": "----", "status": 0, "cpu": [0, 0, 0, 0]})
        self.json = json.dumps({"vms": vms}, indent=4)
        self.conn = None     # Will store the connection object for vSphere


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
    to make our search faster.  It is stored as a static array to persist across calls to this module."""
    all_hosts = []      # Static array containing all hosts

    def __init__(self, managed_object_reference, name, hz):
        self.managed_object_reference = managed_object_reference
        self.name = name
        self.cpu_mhz = int(hz / (1000 * 1000))         # CPU speed
        self.__class__.all_hosts.append(self)           # Add self to static array

    @classmethod
    def get_mhz_by_host(cls, managed_object_reference):
        for host in cls.all_hosts:
            if host.managed_object_reference == managed_object_reference:
                return host.cpu_mhz


def connect_vcenter():
    """This function will connect to the specified vCenter server.  If it fails, it will retry"""
    logger = logging.getLogger(__name__)
    # Disable certificate verification otherwise it will error
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    ssl_context.verify_mode = ssl.CERT_NONE

    server_instance = None
    try:
        logger.debug("Connecting to: " + VCENTER_SERVER)
        server_instance = SmartConnect(host=VCENTER_SERVER, user=VCENTER_USERNAME,
                                       pwd=VCENTER_PASSWORD, sslContext=ssl_context)
        server_instance._stub.connectionPoolTimeout = -1    # Turn the connection timeout off (default 900 sec)
    except Exception as error:
        logger.error("Error connecting to " + VCENTER_SERVER + str(error))

    return server_instance


def generate_json(vmware_monitor):
    """This is the main function. It will connect to the vCenter server, obtain perf data and output json"""
    logger = logging.getLogger("vmware_vm")

    if vmware_monitor.conn is None:
        vmware_monitor.conn = connect_vcenter()     # Connect to vCenter server
        if vmware_monitor.conn is None:
            logger.warning("Unable to connect to " + VCENTER_SERVER + " will retry in " +
                           str(SAMPLE_INTERVAL) + " seconds.")
            vmware_monitor.json = json.dumps({"vms": [{"error": "Unable to connect to " + VCENTER_SERVER +
                                                            " will retry in " + str(SAMPLE_INTERVAL) +
                                                            " seconds."}]}, indent=4)
            return vmware_monitor   # Could not connect so return

    # Final test if we're connected
    try:
        if vmware_monitor.conn.content.sessionManager.currentSession:
            logger.debug("Connected to " + VCENTER_SERVER + " at " +
                        str(vmware_monitor.conn.content.sessionManager.currentSession.loginTime))
    except Exception as error:
        logger.error("Final test: Error connecting to " + VCENTER_SERVER + str(error))
        vmware_monitor.json = json.dumps({"vms": [{"error": "Unable to connect to " + VCENTER_SERVER +
                                                            " will retry in " + str(SAMPLE_INTERVAL) +
                                                            " seconds."}]}, indent=4)
        return vmware_monitor  # Could not connect so return

    #
    # ---------------------------------------------------------------------------------------------------------------
    #
    # First we want to grab a list of all the hosts so we can determine the clock speed of the CPUs
    # API:  HostSystem - https://pubs.vmware.com/vsphere-51/index.jsp#com.vmware.wssdk.apiref.doc/vim.HostSystem.html
    #
    # ---------------------------------------------------------------------------------------------------------------
    try:
        # Fast way of getting Host properties using PropertyCollector
        # https://github.com/vmware/pyvmomi/blob/master/docs/vmodl/query/PropertyCollector.rst

        logger.debug("Collecting properties for HostSystem")
        container_view = get_container_view(vmware_monitor.conn, obj_type=[pyVmomi.vim.HostSystem])
        query = ["name", "hardware.cpuInfo.hz"]
        host_props = collect_properties(vmware_monitor.conn, container_view,
                                        pyVmomi.vim.HostSystem, query, include_mors=True)

    except Exception as error:
        logger.error("Error collecting VMware Host data." + str(error))
        vmware_monitor.json = json.dumps({"vms": [{"error": "Error retrieving VMware Host data" +
                                                            str(error)}]}, indent=4)
        return vmware_monitor

    for prop_set in host_props:
        # The properties aren't always returned in the order you expect, so we have to match them up
        host_mor = prop_set["obj"]
        host_name = prop_set["name"]
        host_hz = prop_set["hardware.cpuInfo.hz"]
        logger.debug("Name: " + host_name + " cpuInfo.hz: " + str(host_hz))
        # Create host object so we can find Mhz later (object is stored in class array all_hosts)
        VMwareHost(host_mor, host_name, host_hz)

    # ---------------------------------------------------------------------------------------------------------------
    #
    #  Next we query for the VM stats we are looking for.
    #
    # ---------------------------------------------------------------------------------------------------------------
    # API:  VirtualMachine
    # https://pubs.vmware.com/vsphere-50/index.jsp#com.vmware.wssdk.apiref.doc_50/vim.VirtualMachine.html
    #
    # summary.overallStatus: general "health" value: gray, green, red, yellow
    # summary.quickStats.overallCpuUsage: Amount of CPU actually granted to the VM in Mhz
    # summary.quickStats.staticCpuEntitlement: Max CPU possible for the VM in Mhz
    # summary.quickStats.guestMemoryUsage: Active memory usage of the VM in MB.
    # summary.quickStats.staticMemoryEntitlement: Max CPU possible for the VM in MB
    # config.hardware.numCPU:  Number of virtual CPUs present in this virtual machine.
    # runtime.host:  The host that is responsible for running a virtual machine.

    try:
        # Fast way of getting VM properties using PropertyCollector
        # https://github.com/vmware/pyvmomi/blob/master/docs/vmodl/query/PropertyCollector.rst

        logger.debug("Collecting properties for VirtualMachine")
        container_view = get_container_view(vmware_monitor.conn, obj_type=[pyVmomi.vim.VirtualMachine])
        query = [
            "name",
            "summary.overallStatus",
            "summary.quickStats.overallCpuUsage",
            "config.hardware.numCPU",  # This number is vCPU
            "runtime.host"
        ]
        props = collect_properties(vmware_monitor.conn, container_view,
                                   pyVmomi.vim.VirtualMachine, query, include_mors=True)

    except Exception as error:
        logger.error("Error collecting VMware VirtualMachine data." + str(error))
        vmware_monitor.json = json.dumps({"vms": [{"error": "Error retrieving VMware VirtualMachine data" +
                                                            str(error)}]}, indent=4)
        return vmware_monitor

    # Loop through all of the VMs
    for prop_set in props:

        mor = prop_set["obj"]  # managed_object_reference
        vm_name = prop_set["name"]
        vm_status = prop_set["summary.overallStatus"]
        vm_cpu = prop_set["summary.quickStats.overallCpuUsage"]
        vm_cpu_count = prop_set["config.hardware.numCPU"]
        vm_host_mor = prop_set["runtime.host"]      # managed_object_reference for its host

        # Exclude any items by our list of search terms EXCLUDE_VM
        if any(substring in vm_name for substring in EXCLUDE_VM):
            logger.debug("Excluding: " + vm_name)
            continue
        else:
            logger.debug("VM: " + vm_name + " Status: " + str(vm_status) + " CPU: " + str(vm_cpu))

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
            del (vm.cpu_datapoints[0])

        vm.host_cpu_mhz = VMwareHost.get_mhz_by_host(vm_host_mor)  # Get the host hz per CPU
        vm.cpu_count = vm_cpu_count
        # Update ranking value of this VM to determine if we should show it
        vm.update_relative_weight()

    # Once we have finished updating our VM data, grab the top MAX_VM_RESULTS and output the JSON
    # Sort by relative weight
    VMwareVM.all_vms.sort(key=operator.attrgetter('relative_weight'), reverse=True)

    # If there are fewer VMs than we've asked it to display, fix the MAX_VM_RESULTS
    global MAX_VM_RESULTS
    if len(VMwareVM.all_vms) < MAX_VM_RESULTS:
        MAX_VM_RESULTS = len(VMwareVM.all_vms)

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

    logger.debug(vmware_monitor.json)

    return vmware_monitor


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
