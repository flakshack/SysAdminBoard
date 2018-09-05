#!/usr/bin/env python
"""nutanix_vm_svr - Uses Nutanix REST API to get summary of performance stats.

Requires requests
pip install requests

"""
import json
import time
import operator
import requests
import logging.config
from credentials import NUTANIX_USER  # Login info now stored in credentials.py
from credentials import NUTANIX_PASSWORD  # Login info now stored in credentials.py

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
NUTANIX_URL = "https://pri-svr:9440/PrismGateway/services/rest/v1/vms/"
# Note that I'm using a private API call from Nutanix to optimize data retrieval.
#   It might not work in future versions.
NUTANIX_PRIVATE_URL = "https://pri-svr:9440/PrismGateway/services/rest/v1/utils/entities"
SAMPLE_INTERVAL = 60
MAX_DATAPOINTS = 30
MAX_VM_RESULTS = 20              # Number of VMs to get data (should match html file)
EXCLUDE_VM = []                # VMs with any of the items in this list in their
#                                  name will be excluded from results (ex: "NTNX-123")
SORT_BY = "IOPS"                 # Results sort options: IOPS, THROUGHPUT, LATENCY
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = None
        self.session = None     # Will store the connection object for vSphere
        self.full_update_time = 0
        self.all_vms = []

    def find_by_vm_id(self, vm_id, vm_name='UNKNOWN'):
        for vm in self.all_vms:
            if vm.vm_id == vm_id:
                return vm
        # if not found, create one and return it instead
        self.all_vms.append(VMwareVM(vm_id, vm_name))
        return self.all_vms[-1]

    def remove_old_vms(self):
        """Every hour we check for VMs that aren't getting updated and remove them from our list"""
        for vm in self.all_vms:
            if (time.time() - vm.last_updated) > 3600:
                self.all_vms.remove(vm)

    def reset(self):
        self.session = None
        self.full_update_time = 0
        self.all_vms = []
        self.json = None


class VMwareVM:
    """Class to contain VM specific data"""
    def __init__(self, vm_id, vm_name):
        self.name = vm_name
        self.vm_id = vm_id
        self.iops = []
        self.throughput = []
        self.latency = []
        self.relative_weight = 0.0
        self.last_updated = 0

    def update_relative_weight(self):
        """The relative weight is used to determine how much we want to see the data of this VM."""
        self.relative_weight = 1

        # Determine which list we'll use to sort by
        sort_list = []
        if SORT_BY == "IOPS":
            sort_list = self.iops
        elif SORT_BY == "THROUGHPUT":
            sort_list = self.throughput
        elif SORT_BY == "LATENCY":
            sort_list = self.latency

        # Add up all of the historical counter datapoints (higher counter = more weight)
        for i in sort_list:
            self.relative_weight += i


class NutanixVMRequestException(Exception):
    pass


def generate_json(monitor):
    """
    This function will connect to the Nutanix cluster and retrieve performance data, which
    will be stored in json format in the json property.

    Note that the /vms/ API returns all of the VMs with all of the data.  As of now, it doesn't have
    a way to select which properties to return, so we just get all of them.  I decided that although this was
    not efficient, it is still better than requesting /vms/{vmid}/stat separately for each VM.
    """
    logger = logging.getLogger("nutanix_vm_svr")

    # Check if there is a working session and create a new one if it is not working
    if monitor.session is None:
        logger.debug("No existing REST API session, creating a new one.")
        # Create Session object that will allow us to issue commands without having to login each time
        monitor.session = requests.Session()
        monitor.session.headers.update({'content-type': 'application/json'})
        monitor.session.auth = (NUTANIX_USER, NUTANIX_PASSWORD)

    # The first run and every hour, remove old VMs and do a full refresh on the VMs list
    if time.time() - monitor.full_update_time > 3600:
        # Remove old VMs
        if monitor.full_update_time != 0:
            monitor.remove_old_vms()

        try:    # Try getting the vm data

            logger.debug("Getting: " + NUTANIX_URL)
            parameters = {'projection': 'BASIC_INFO',           # Only grab basic data, not all stats
                          'filterCriteria': 'power_state==on'}   # Only grab powered_on vms
            r = monitor.session.get(NUTANIX_URL, params=parameters, verify=False)

            if r.status_code != 200:
                raise NutanixVMRequestException("Request error status: " + str(r.status_code) + " " + r.reason)

            vm_basic_info = r.json()   # Read in data as JSON and save to our persistant monitor
            logger.debug("Retrieved BASIC_INFO data for " + str(len(vm_basic_info["entities"])) + " VMs")

            # Create VM objects for each VM and append to our array
            for entity in vm_basic_info["entities"]:
                vm_name = entity["vmName"]
                # Exclude any items by our list of search terms EXCLUDE_VM
                if any(substring in vm_name for substring in EXCLUDE_VM):
                    logger.debug("Excluding: " + vm_name)
                    continue
                # We're only interested in the last part of the entity vmID
                # ex: 00053d1a-c9d5-958b-0000-00000000dfb7::50274c0d-5e04-3442-b47b-1c35698e3035
                vm_id = ((entity["vmId"]).split('::'))[1]
                # Check to see if this VM is in our list and create one if not found
                monitor.find_by_vm_id(vm_id, vm_name)

            # Set the next full_update_time so we'll do this again in 1 hour
            monitor.full_update_time = time.time()

        except Exception as error:
            # If we couldn't connect, set the session object to None and try again next time
            monitor.reset()
            logger.error("Unable to get  " + NUTANIX_URL + "/vms/ " + str(error))
            monitor.json = json.dumps({"error": "Unable to get  " + NUTANIX_URL + "/vms/" + str(error)}, indent=4)
            return

    try:
        # Here we use the private API to grab only specific stats for all the VMs
        logger.debug("Getting: " + NUTANIX_PRIVATE_URL)
        parameters = {'entityType': 'vm',
                      'projection': 'hypervisor_num_iops,'
                                    'hypervisor_io_bandwidth_kBps,'
                                    'hypervisor_avg_io_latency_usecs',
                      'filterCriteria': 'power_state==on'}
        r = monitor.session.get(NUTANIX_PRIVATE_URL, params=parameters, verify=False)
        if r.status_code != 200:
            raise NutanixVMRequestException("Request error status: " + str(r.status_code) + " " + r.reason)

        all_vm_stats = r.json()      # Read in data as JSON
        logger.debug("Retrieved FULL data for " + str(len(all_vm_stats["entities"])) + " VMs")
    except Exception as error:
        # If we couldn't connect, set the session object to None and try again next time
        monitor.reset()
        logger.error("Unable to get  " + NUTANIX_PRIVATE_URL + "/vms/" + " " + str(error))
        monitor.json = json.dumps({"error": "Unable to get  " + NUTANIX_PRIVATE_URL +
                                            "/vms/" + " " + str(error)}, indent=4)
        return

    # Loop through all the VMs and update stats
    for entity in all_vm_stats["entities"]:
        # Get the VM object from our monitor list
        vm = monitor.find_by_vm_id(entity["id"])

        # Update the master stats with updated stats
        iops = int(entity["hypervisor_num_iops"])
        throughput = round((int(entity["hypervisor_io_bandwidth_kBps"])) / 1024, 2)  # Convert to MBps
        latency = round((int(entity["hypervisor_avg_io_latency_usecs"]) / 1000), 1)      # Convert to ms

        # Store the list data in the VM object
        if len(vm.iops) == 0:
            vm.iops = [iops]
            vm.throughput = [throughput]
            vm.latency = [latency]
        else:
            vm.iops.append(iops)
            vm.throughput.append(throughput)
            vm.latency.append(latency)
        # If we already have the max number of datapoints in our list, delete the oldest item
        if len(vm.iops) >= MAX_DATAPOINTS:
            del (vm.iops[0])
            del (vm.throughput[0])
            del (vm.latency[0])

        # Update ranking value of this VM to determine if we should show it
        vm.update_relative_weight()
        # Note the time when we updated this VM's stats
        vm.last_updated = time.time()

    # ---------------------
    # Sort by relative weight
    monitor.all_vms.sort(key=operator.attrgetter('relative_weight'), reverse=True)

    # If there are fewer VMs than we've asked it to display, fix the MAX_VM_RESULTS
    global MAX_VM_RESULTS
    if len(monitor.all_vms) < MAX_VM_RESULTS:
        MAX_VM_RESULTS = len(monitor.all_vms)

    # Once we have finished updating our VM data, grab the top MAX_VM_RESULTS and output the JSON
    output_vms = []
    for i in range(MAX_VM_RESULTS):
        output_vms.append({
            "name": monitor.all_vms[i].name,
            "iops": monitor.all_vms[i].iops,
            "throughput": monitor.all_vms[i].throughput,
            "latency": monitor.all_vms[i].latency
        })

    monitor.json = json.dumps({"vms": output_vms})

    logger.debug(monitor.json)

    return monitor


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
