#!/usr/bin/env python
"""emc_vnx_reporter - Uses Mechanize to grab VNX perf data from a VNX Reporter web site.

The VNX Reporter web site has a CSV export on the main page that includes raw data for 6 hours with samples every
5 minutes.  We login to the



# Requires Mechanize
# pip install mechanize

"""
from __future__ import division    # So division of integers will result in float
from mechanize import Browser
import mechanize
import csv
import StringIO
import time
import json
from datetime import datetime



__author__ = 'scott@flakshack.com (Scott Vintinner)'


from credentials import VNX_REPORTER_USERNAME   # Login info now stored in credentials.py
from credentials import VNX_REPORTER_PASSWORD   # Login info now stored in credentials.py

#=================================SETTINGS======================================
VNX_REPORTER_WEBSERVER = "http://vnx-reporter:58080/VNX-MR"

# URLS for Storage Pools found by browsing to:
# All>>Systems>>Summary>>Array Summary>><Array Name>>>Block, <Array ID>>>Array Name>>Storage Pool>>Summary>>Storage Pools Performance>>APM00125137788, VMWare_DB_Pool>>Storage Pool IOPS
# Change the date range of the report to "realtime, last 15 minutes", then copy the URL for Export->CSV.

# =============Sample CSV File=================
#        #"All/Systems/Summary/Array Summary/VNXCS0/Block, APM00125137788/VNXCS0/Storage Pool/Summary/Storage Pools Performance/APM00125137788, VMWare_DB_Pool/Storage Pool IOPS"
#
#        #"Wednesday, December 24, 2014, from 8:59 AM to 9:14 AM, EST"
#
#
#        "Timestamp","LOGICAL UNIT NUMBER 138, IOPS"
#        "1419429450","209.02667045593262"
#        "1419429750","208.39051842689514"
#        "1419430050","260.0799992084503"
#
#        "Timestamp","LOGICAL UNIT NUMBER 136, IOPS"
#        "1419429450","28.999999523162842"
#        "1419429750","259.0604591369629"
#        "1419430050","34.46666669845581"
#
#        "Timestamp","LOGICAL UNIT NUMBER 104, IOPS"
#        "1419429450","50.75333395600319"
#        "1419429750","48.511627078056335"
#        "1419430050","48.17333263158798"
#
#        "Timestamp","LOGICAL UNIT NUMBER 105, IOPS"
#        "1419429450","51.03999960422516"
#        "1419429750","53.01723277568817"
#        "1419430050","37.333332538604736"
#
#        "Timestamp","LOGICAL UNIT NUMBER 106, IOPS"
#        "1419429450","40.34333336353302"
#        "1419429750","59.022502422332764"
#        "1419430050","65.84666639566422"
#
#        "Timestamp","Others"
#        "1419429450","253.97666573524475"
#        "1419429750","223.69741164613515"
#        "1419430050","250.17666354496032"
# =============Sample CSV File=================



STORAGE_POOLS = (
    {"name": "VMware", "url": "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-f2d4031b-344209fa-2ed56689-12c23473-baad54bd-71f0f1ce-e568d0be-280cc045&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"},
    {"name": "Exch", "url": "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-f2d4031b-344209fa-2ed56689-12c23473-baad54bd-71f0f1ce-2b0c9361-a33158e8&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"},
    {"name": "Logs", "url": "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-f2d4031b-344209fa-2ed56689-12c23473-baad54bd-71f0f1ce-26d1978c-3393bb6b&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"},
    {"name": "CIFS", "url": "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-f2d4031b-344209fa-2ed56689-12c23473-baad54bd-71f0f1ce-35f3533c-1ad4611b&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"},
    {"name": "CIFS-R", "url": "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-f2d4031b-344209fa-2ed56689-12c23473-baad54bd-71f0f1ce-b4f98203-46b024e2&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"},
    {"name": "RPA", "url": "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-f2d4031b-344209fa-2ed56689-12c23473-baad54bd-71f0f1ce-3210cece-e75b6a55&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"}

)
MAX_DATAPOINTS = 30
SAMPLE_INTERVAL = 60
GRAPH_TITLE = "EMC VNX Storage Pool IOPS"
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""


class StoragePoolDataset:
    all_pools = []    # Static array containing all storage pools

    def __init__(self, name, url):
        self.url = url
        self.name = name
        self.raw_data = []                       # Hold raw data
        self.datapoints = []                     # Holds data in dictionary format for statusboard processing
        self.__class__.all_pools.append(self)    # Add self to static array


class PoolDatapoint:
    def __init__(self, timestamp, value):
        self.value = value
        self.timestamp = timestamp


def output_message(message, detail):
    """This function will output an error message formatted in JSON to display on the StatusBoard app"""
    statusbar_output = {"graph": {"title": GRAPH_TITLE, "error": {"message": message, "detail": detail}}}
    output = json.dumps(statusbar_output)
    return output


def monkeypatch_mechanize():
    """Work-around for a mechanize 0.2.5 bug. See: https://github.com/jjlee/mechanize/pull/58"""
    if mechanize.__version__ < (0, 2, 6):
        from mechanize._form import SubmitControl, ScalarControl

        def __init__(self, type, name, attrs, index=None):
            ScalarControl.__init__(self, type, name, attrs, index)
            # IE5 defaults SUBMIT value to "Submit Query"; Firebird 0.6 leaves it
            # blank, Konqueror 3.1 defaults to "Submit".  HTML spec. doesn't seem
            # to define this.
            if self.value is None:
                if self.disabled:
                    self.disabled = False
                    self.value = ""
                    self.disabled = True
                else:
                    self.value = ""
            self.readonly = True

        SubmitControl.__init__ = __init__


# Mechanize cannot read forms when the submit button is disabled (as happens on this page).  To work around this
# issue, we apply the patch listed above.
monkeypatch_mechanize()


def generate_json(vnx_monitor):
    """This function will connect to the VNX web server, parse data and store the output in vnx_monitor.json"""
    try:
        # Create a list of StoragePoolDatasets using the contants provided above
        if len(StoragePoolDataset.all_pools) == 0:
            for pool in STORAGE_POOLS:
                StoragePoolDataset(pool["name"], pool["url"])

        # Create Mechanize browser
        browser = Browser()

        # Open the main VNX-Reporter login page and login
        browser.open(VNX_REPORTER_WEBSERVER)

        # Note that the login form doesn't have a name, but we locate it by ID
        for form in browser.forms():
            if form.attrs['id'] == 'login-form':
                browser.form = form
                break

        browser["j_username"] = VNX_REPORTER_USERNAME
        browser["j_password"] = VNX_REPORTER_PASSWORD
        browser.submit()

        #
        # Now that we are logged in, we can get the page we really want.
        #
        statusbar_datasequences = []
        # Get data for each storage pool
        for pool in StoragePoolDataset.all_pools:
            # Get the CSV file from the web server
            reply = browser.open(pool.url)
            perf_data = reply.read()

            # Use the CSV module to parse the data.
            read_csv = csv.reader(StringIO.StringIO(perf_data))

            # The file lists several LUNs with a timestamp and IOPs count. Add up a total IOPS for the pool.
            csv_datapoints = []
            for row in read_csv:
                # The CSV module will parse each line into an array
                if len(row) > 1:                # Skip blank rows
                    if row[0].isdigit():        # Skip any row where the first column isn't a number.
                        timestamp = int(row[0])
                        value = int(float(row[1]))
                        found = False
                        for csv_datapoint in csv_datapoints:
                            if csv_datapoint.timestamp == timestamp:
                                csv_datapoint.value += value
                                found = True
                                break
                        if not found:
                            csv_datapoints.append(PoolDatapoint(timestamp, value))

            # Merge the data we just received with our saved data, skipping any duplicate timestamps
            for csv_datapoint in csv_datapoints:
                # Check if it already exists in our pool data
                found = False
                for data in pool.raw_data:
                    if csv_datapoint.timestamp == data.timestamp:
                        found = True
                        break
                if not found:
                    pool.raw_data.append(csv_datapoint)


            # If we already have the max number of datapoints, delete the oldest item.
            if len(pool.raw_data) >= MAX_DATAPOINTS:
                del(pool.raw_data[0])

            # Format raw data as a dictionary for JSON consumption
            pool.datapoints = []
            for data in pool.raw_data:
                x_axis_time = datetime.fromtimestamp(data.timestamp)
                pool.datapoints.append({"title": x_axis_time.strftime("%I:%M"), "value": data.value})

            # Generate the data sequence
            statusbar_datasequences.append({"title": pool.name, "datapoints": pool.datapoints})

        # Generate JSON output and assign to snmp_monitor object (for return back to caller module)
        statusbar_graph = {
            "title": GRAPH_TITLE, "type": "line",
            "refreshEveryNSeconds": SAMPLE_INTERVAL,
            "datasequences": statusbar_datasequences
        }
        statusbar_type = {"graph": statusbar_graph}
        vnx_monitor.json = json.dumps(statusbar_type)

    except Exception as error:
        vnx_monitor.json= output_message("Error in VNX_Reporter_Pool_IO", error.message)

    if __debug__:
        print vnx_monitor.json



# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)