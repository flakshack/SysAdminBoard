#!/usr/bin/env python
"""sample.py - This is a sample module to demonstrate the basic functionality of the SysAdminBoard.
Running this python file by itself will produce a simple JSON data output.  When you launch this file
via the webserver.py script (along with sample.html), it will present a web page and an ajax interface at:

http://yourcomputer/sample
http://yourcomputer/sample/ajax

"""
from random import randint
import json
import time
import logging.config

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
SAMPLE_INTERVAL = 5
# ===============================================================================


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        self.json = ""


def generate_json(sample_monitor):
    """This function will generate a single random number output the data"""
    logger = logging.getLogger(__name__)

    random_number = randint(1, 100)  # Generate a random number from 1-100
    output = {"random_number": random_number}   # Create a dict with our data
    sample_monitor.json = json.dumps(output)    # Convert the dict into JSON

    logger.debug(sample_monitor.json)


#
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
        main_logger.info("Waiting for " + str(SAMPLE_INTERVAL) + " seconds")
        time.sleep(SAMPLE_INTERVAL)
