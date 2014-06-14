#!/usr/bin/env python
"""helpdesk_byuser - Exports JSON files with data from Helpdesk

Requires mysql connector in python:  pip install mysql-connector-python

"""
from __future__ import division    # So division of integers will result in float

__author__ = 'forge@flakshack.com (Scott Vintinner)'




#=================================SETTINGS======================================
SAMPLE_INTERVAL = 120
MAX_RESULTS = 10              #
mysql_config = {
    'host': 'workdesk.yourcompany.com',
    'database': 'workdesk',
    'user': 'workdesk_report',
    'password': '**********'
}
#===============================================================================


import json
import datetime
import time
import mysql.connector
from mysql.connector import errorcode



#select * from calls
#where category in ("Helpdesk", "Application Support", "Network Services")
#and status = "OPEN"
#and track >= UNIX_TIMESTAMP('2014-05-15 00:00:00')
#


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        # Set the default empty values for all
        user_data = [{"name": "----", "count": 0}, {"name": "----", "count": 0}]
        self.json = json.dumps({"hosts": user_data}, indent=4)


def generate_json(monitor):
    fromdate = datetime.date.today() + datetime.timedelta(days=-30)
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
        cursor = conn.cursor()
        cursor.execute(query, (fromdate.isoformat(), MAX_RESULTS))


    except mysql.connector.Error as err:
        print err
        monitor.json = json.dumps({"users": [{"error": err.message}]})
    else:
        user_data = []
        for (username, count) in cursor:
            user_data.append({"name": username, "count": count})

        monitor.json = json.dumps({"users": user_data})

    finally:
        cursor.close()
        conn.close()

    if __debug__:
        print monitor.json


# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)