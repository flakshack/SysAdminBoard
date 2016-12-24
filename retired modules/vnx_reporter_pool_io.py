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
from collections import defaultdict



__author__ = 'scott@flakshack.com (Scott Vintinner)'


from credentials import VNX_REPORTER_USERNAME   # Login info now stored in credentials.py
from credentials import VNX_REPORTER_PASSWORD   # Login info now stored in credentials.py

#=================================SETTINGS======================================
VNX_REPORTER_WEBSERVER = "http://vnx-reporter:58080/VNX-MR"

# URLS for Storage Pools found by browsing to:
# All>>Systems>>Summary>>Array Summary>><Array Name>>>Block, <Array ID>>>Array Name>>Storage Pool>>Summary>>Storage Pools Performance>>APM00125137788, VMWare_DB_Pool>>Storage Pool IOPS
# Change the date range of the report to "realtime, last 15 minutes", then copy the URL for Export->CSV.

# From All>>Systems>>Details>>Block Systems (All Reports)>>Performance>>TopN & Exceptions>>TopN IOPS>>Storage Pools / RAID Groups
# =============Sample CSV File=================
# "Array","Storage Pool / RAID Group","Total Throughput (IO/s)"
# "VNXCS0","VMWare_DB_Pool","786.11370099149644374847412109375"
# "VNXCS0","DB_Log_Pool","375.515779879875481128692626953125"
# "VNXCS0","Exchange_Data_Pool","269.28121803700923919677734375"
# "VNXCS0","RecoverPoint_JRNL_Pool","61.3779788948595523834228515625"
# "VNXCS0","CIFS_Share_Pool","39.02574731595814228057861328125"
# "VNXCS0","CIFS_Replica_Pool","11.292803363292478024959564208984375"
# =============Sample CSV File=================

VNX_REPORT_URL = "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-t3a7d227d433f92f3-4a44114c-4786a14f-88274b27-92f494c-55ec0ee1-3c1260af&display=0&mode=srt&lower=0.0&upper=&type=3&period=0&durationType=l&duration=15m&itz=America%2FNew_York"

MAX_DATAPOINTS = 30
SAMPLE_INTERVAL = 120
GRAPH_TITLE = "EMC Pool IOPS"
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""
        self.datapoints = []



def output_message(message, detail):
    """This function will output an error message formatted in JSON to display on the SysAdminBoard app"""
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

        reply = browser.open(VNX_REPORT_URL)
        perf_data = reply.read()
        read_csv = csv.reader(StringIO.StringIO(perf_data))

        # The file lists several LUNs with a timestamp and IOPs count. Add up a total IOPS for the pool.
        timestamp = datetime.now()
        for row in read_csv:
            # The CSV module will parse each line into an array with the columns
            if len(row) > 1:  # Skip blank rows
                if row[0] == "VNXCS0":        # Skip any row without the correct array
                    pool = row[2]
                    pool = pool.replace("_Pool","")     # Remove the word _POOL from pool names
                    iops = int(float(row[11]))
                    vnx_monitor.datapoints.append({"pool":pool, "iops":iops, "timestamp":timestamp})


        # Each storage pool will be stored as dict with all the datapoints in this array
        statusbar_datasequences = []

        # Organize the datapoints by pool
        pool_datapoints = defaultdict(list)
        for datapoint in vnx_monitor.datapoints:
            title = datapoint['timestamp'].strftime("%H:%M")
            value = datapoint['iops']
            pool_datapoints[(datapoint['pool'])].append({"title": title, "value":value})
        # Format raw data as a dictionary for JSON consumption
        for pool in pool_datapoints:
            statusbar_datasequences.append({"title": pool, "datapoints": pool_datapoints[pool]})

        # If we already have the max number of datapoints, delete the oldest item.
        pool_count = len(pool_datapoints)   # we will delete one datapoint for each pool
        if len(vnx_monitor.datapoints) >= (MAX_DATAPOINTS * pool_count):
            for i in range(0,pool_count):
                del (vnx_monitor.datapoints[0])

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


# Sample Output:
# {"graph": {"datasequences": [{"datapoints": [{"value": 16, "title": "14:53"}, {"value": 16, "title": "14:54"}, {"value": 8, "title": "14:55"}, {"value": 7, "title": "14:56"}, {"value": 7, "title": "14:57"}, {"value": 7, "title": "14:58"}, {"value": 7, "title": "15:00"}, {"value": 5, "title": "15:01"}, {"value": 5, "title": "15:02"}, {"value": 5, "title": "15:03"}, {"value": 5, "title": "15:04"}, {"value": 16, "title": "15:05"}], "title": "CIFS_Replica_Pool"}, {"datapoints": [{"value": 487, "title": "14:54"}, {"value": 496, "title": "14:55"}, {"value": 418, "title": "14:56"}, {"value": 418, "title": "14:57"}, {"value": 418, "title": "14:58"}, {"value": 418, "title": "15:00"}, {"value": 329, "title": "15:01"}, {"value": 329, "title": "15:02"}, {"value": 329, "title": "15:03"}, {"value": 329, "title": "15:04"}, {"value": 462, "title": "15:05"}], "title": "DB_Log_Pool"}, {"datapoints": [{"value": 796, "title": "14:54"}, {"value": 805, "title": "14:55"}, {"value": 762, "title": "14:56"}, {"value": 762, "title": "14:57"}, {"value": 762, "title": "14:58"}, {"value": 762, "title": "15:00"}, {"value": 592, "title": "15:01"}, {"value": 592, "title": "15:02"}, {"value": 592, "title": "15:03"}, {"value": 592, "title": "15:04"}, {"value": 779, "title": "15:05"}], "title": "VMWare_DB_Pool"}, {"datapoints": [{"value": 300, "title": "14:54"}, {"value": 311, "title": "14:55"}, {"value": 254, "title": "14:56"}, {"value": 254, "title": "14:57"}, {"value": 254, "title": "14:58"}, {"value": 254, "title": "15:00"}, {"value": 209, "title": "15:01"}, {"value": 209, "title": "15:02"}, {"value": 209, "title": "15:03"}, {"value": 209, "title": "15:04"}, {"value": 267, "title": "15:05"}], "title": "Exchange_Data_Pool"}, {"datapoints": [{"value": 58, "title": "14:53"}, {"value": 58, "title": "14:54"}, {"value": 48, "title": "14:55"}, {"value": 55, "title": "14:56"}, {"value": 55, "title": "14:57"}, {"value": 55, "title": "14:58"}, {"value": 55, "title": "15:00"}, {"value": 46, "title": "15:01"}, {"value": 46, "title": "15:02"}, {"value": 46, "title": "15:03"}, {"value": 46, "title": "15:04"}, {"value": 82, "title": "15:05"}], "title": "CIFS_Share_Pool"}, {"datapoints": [{"value": 62, "title": "14:53"}, {"value": 62, "title": "14:54"}, {"value": 60, "title": "14:55"}, {"value": 61, "title": "14:56"}, {"value": 61, "title": "14:57"}, {"value": 61, "title": "14:58"}, {"value": 61, "title": "15:00"}, {"value": 56, "title": "15:01"}, {"value": 56, "title": "15:02"}, {"value": 56, "title": "15:03"}, {"value": 56, "title": "15:04"}, {"value": 61, "title": "15:05"}], "title": "RecoverPoint_JRNL_Pool"}], "refreshEveryNSeconds": 60, "type": "line", "title": "EMC VNX Storage Pool IOPS"}}
