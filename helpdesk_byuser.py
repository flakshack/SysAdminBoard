#!/usr/bin/env python
"""helpdesk_byuser - Exports JSON files with data from Helpdesk

Requires mysql connector in python:  pip install mysql-connector

"""
from credentials import WORKDESK_USER
from credentials import WORKDESK_PASSWORD
import json
import datetime
import time
import mysql.connector
import logging.config

__author__ = 'scott@flakshack.com (Scott Vintinner)'

# =================================SETTINGS======================================
SAMPLE_INTERVAL = 120
MAX_RESULTS = 10
mysql_config = {
    'host': 'workdesk',
    'database': 'workdesk',
    'user': WORKDESK_USER,
    'password': WORKDESK_PASSWORD
}
# ===============================================================================

# select * from calls
# where category in ("Helpdesk", "Application Support", "Network Services")
# and status = "OPEN"
# and track >= UNIX_TIMESTAMP('2014-05-15 00:00:00')
#


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        # Set the default empty values for all
        user_data = [{"name": "----", "count": 0}, {"name": "----", "count": 0}]
        self.json = json.dumps({"hosts": user_data}, indent=4)


def generate_json(helpdesk_monitor):
    logger = logging.getLogger("helpdesk_byuser")
    fromdate = datetime.date.today() + datetime.timedelta(days=-30)
    cursor = conn = None
    try:
        conn = mysql.connector.connect(**mysql_config)
        query = (
            "SELECT u.name, count(c.username) as count "
            "from calls c join users u on c.username=u.username "
            "WHERE category IN ('Helpdesk', 'Application Support', 'Network Services') "
            "AND track >= UNIX_TIMESTAMP(%s) "
            "GROUP BY c.username "
            "ORDER BY count(c.username) DESC "
            "LIMIT %s"
        )
        logger.debug("Query: " + query)
        cursor = conn.cursor()
        cursor.execute(query, (fromdate.isoformat(), MAX_RESULTS))

    except mysql.connector.Error as error:
        logger.error("MySQL Error:" + str(error))
        helpdesk_monitor.json = json.dumps({"users": [{"error": str(error)}]})
    else:
        user_data = []
        for (username, count) in cursor:
            user_data.append({"name": username, "count": count})

        helpdesk_monitor.json = json.dumps({"users": user_data})

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()

    logger.debug(helpdesk_monitor.json)


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
