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
import operator


__author__ = 'scott@flakshack.com (Scott Vintinner)'


from credentials import VNX_REPORTER_USERNAME   # Login info now stored in credentials.py
from credentials import VNX_REPORTER_PASSWORD   # Login info now stored in credentials.py

#=================================SETTINGS======================================
VNX_REPORTER_WEBSERVER = "http://vnx-reporter:58080/VNX-MR"
VNX_BLOCK_IO_CSV = "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-4a44114c-4786a14f-b36fc7de-4c614edb-4a3e733b-85cf6d&display=0&mode=nrx&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=2h&itz=America%2FNew_York"
VNX_BLOCK_READ_STR = '"Timestamp","Read IOPS (IO/s)"'
VNX_BLOCK_WRITE_STR = '"Timestamp","Write IOPS (IO/s)"'
VNX_FILE_IO_CSV = "http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-4a44114c-8f267c5c-70bffb61-2809341b-b53a5bb-b0b3e008-80928810&display=0&mode=stk&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=2h&itz=America%2FNew_York"
VNX_FILE_READ_STR = '"Timestamp","ReadRequests, server_2 (Nb/s)"'
VNX_FILE_WRITE_STR = '"Timestamp","WriteRequests, server_2 (Nb/s)"'
VNX_TOP_LUN_CSV = 'http://vnx-reporter:58080/VNX-MR/report.csv?report&select=0-1-c2b16891-3f6d1f89-49fa3b2c-a3b0f8f9-a541c5e5-4a3e733b-d777d0dd-11adc2b1-98a6d95&display=0&mode=srt&statistics=none&lower=0.0&upper=&type=3&period=0&durationType=l&duration=5m&itz=America%2FNew_York&amp;d-2692206-s=8&amp;d-2692206-o=1&amp;d-2692206-p=1'
VNX_TOP_LUN_START = '"Array","LUN","Availability (%)","Storage Group","Storage Pool","Storage Pool type","RAID Level","Capacity (GB)","IOPS","Bandwidth (MB/s)","Utilization (%)","Service Time (ms)","Response Time (ms)","Queue Length"'
TOP_LUNS_TO_RETURN = 6
SAMPLE_INTERVAL = 120
GRAPH_TITLE = "EMC VNX Operations per second"
#===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""


def output_message(message):
    """This function will output an error message formatted in JSON to display on the dashboard"""
    output = json.dumps({"error": message}, indent=4)
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

        # Now that we are logged in, we can get the page we really want:
        #
        #==========================BLOCK DATA==============================
        #
        reply = browser.open(VNX_BLOCK_IO_CSV)
        perf_data = reply.read()

        # The CSV has sections are delimited by a blank line and the following header

        # Find the location of each header
        read_start_location = perf_data.find(VNX_BLOCK_READ_STR)
        write_start_location = perf_data.find(VNX_BLOCK_WRITE_STR)
        # Split out the data
        if read_start_location > write_start_location:      # write section is first
            write_data = perf_data[write_start_location + len(VNX_BLOCK_WRITE_STR) + 1:read_start_location - 1]
            read_data = perf_data[read_start_location + len(VNX_BLOCK_READ_STR) + 1:]
        else:                                               # read section is first
            read_data = perf_data[read_start_location + len(VNX_BLOCK_READ_STR) + 1:write_start_location - 1]
            write_data = perf_data[write_start_location + len(VNX_BLOCK_WRITE_STR) + 1:]

        # Use the CSV module to parse the data.
        read_csv = csv.reader(StringIO.StringIO(read_data))

        datapoints = []
        for row in read_csv:
            if len(row) > 1:    # skip blank rows
                datapoints.append(int(float(row[1])))
            else:
                break

        output = {"block_read": datapoints}

        # Use the CSV module to parse the data.
        write_csv = csv.reader(StringIO.StringIO(write_data))
        datapoints = []
        for row in write_csv:
            if len(row) > 1:    # skip blank rows
                datapoints.append(int(float(row[1])))
            else:
                break
        output["block_write"] = datapoints



        #==========================FILE DATA==============================
        #
        reply = browser.open(VNX_FILE_IO_CSV)
        perf_data = reply.read()

        # The CSV has sections are delimited by a blank line and the following header

        # Find the location of each header
        read_start_location = perf_data.find(VNX_FILE_READ_STR)
        write_start_location = perf_data.find(VNX_FILE_WRITE_STR)
        # Split out the data
        if read_start_location > write_start_location:      # write section is first
            write_data = perf_data[write_start_location + len(VNX_FILE_WRITE_STR) + 1:read_start_location - 1]
            read_data = perf_data[read_start_location + len(VNX_FILE_READ_STR) + 1:]
        else:                                               # read section is first
            read_data = perf_data[read_start_location + len(VNX_FILE_READ_STR) + 1:write_start_location - 1]
            write_data = perf_data[write_start_location + len(VNX_FILE_WRITE_STR) + 1:]

        # Use the CSV module to parse the data.
        read_csv = csv.reader(StringIO.StringIO(read_data))

        datapoints = []
        for row in read_csv:
            if len(row) > 1:    # skip blank rows
                datapoints.append(int(float(row[1])))
            else:
                break
        output["file_read"] = datapoints

        # Use the CSV module to parse the data.
        write_csv = csv.reader(StringIO.StringIO(write_data))
        datapoints = []
        for row in write_csv:
            if len(row) > 1:    # skip blank rows
                datapoints.append(int(float(row[1])))
            else:
                break
        output["file_write"] = datapoints


        # ========================= TOP LUNS =============================
        reply = browser.open(VNX_TOP_LUN_CSV)
        raw_data = reply.read()

        start_location = raw_data.find(VNX_TOP_LUN_START)
        lun_data = raw_data[start_location + len(VNX_TOP_LUN_START) + 1:]                # Strip out the header and other garbage and just get the CSV
        lun_csv = csv.reader(StringIO.StringIO(lun_data))

        datapoints = []
        for row in lun_csv:
            if len(row) > 12:    # skip blank rows
                # If a LUN has recently been deleted it may show up in this list with blank values.
                try:
                    datapoints.append({
                        "name": row[1],
                        "iops": round(float(row[8]), 2),
                        "bandwidth": round(float(row[9]), 2),
                        "utilization": round(float(row[10]), 2),
                        "response_time": round(float(row[12]), 2)
                    })
                except Exception as error:
                    datapoints.append({
                        "name": row[1] + "Error",
                        "iops": 0,
                        "bandwidth": 0,
                        "utilization": 0,
                        "response_time": 0
                    })

        # Sort the datapoints by iops (instead of utilization)
        datapoints.sort(key=operator.itemgetter('iops'), reverse=True)
        # Remove all but the TOP_LUNS_TO_RETURN
        datapoints = datapoints[:TOP_LUNS_TO_RETURN]

        output["top_luns"] = datapoints


        # ====================================
        # Generate JSON output and assign to vnx_monitor object (for return back to caller module)
        vnx_monitor.json = json.dumps(output)

    except Exception as error:
        output_message(error.message)


    if __debug__:
        print vnx_monitor.json




# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)