#!/usr/bin/env python
"""sample.py - This is a sample module to demonstrate the basic functionality of the SysAdminStatusBoard.
Running this python file by itself will produce a simple JSON data output.  When you launch this file
via the webserver.py script (along with sample.html), it will present a web page and an ajax interface
that you can load into the StatusBoard iPad App.

http://yourcomputer/sample
http://yourcomputer/sample/ajax

"""
from random import randint
import json
import time

__author__ = 'scott@flakshack.com (Scott Vintinner)'

#=================================SETTINGS======================================
SAMPLE_INTERVAL = 5
#===============================================================================

class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""


def output_message(message):
    """This function will output an error message formatted in JSON to display on the StatusBoard app"""
    output = json.dumps({"error": message}, indent=4)
    return output


def generate_json(sample_monitor):
    """This function will generate a single random number output the data"""

    random_number = randint(1, 100)  # Generate a random number from 1-100
    output = {"random_number": random_number}   # Create a dict with our data
    sample_monitor.json = json.dumps(output)    # Convert the dict into JSON

    if __debug__:
        print sample_monitor.json


# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)