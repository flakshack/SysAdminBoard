#!/usr/bin/env python
"""helpdesk_bycategory - Exports JSON files with data from Helpdesk

Requires mysql connector in python:  pip install mysql-connector-python

"""
from __future__ import division    # So division of integers will result in float

__author__ = 'forge@flakshack.com (Scott Vintinner)'




#=================================SETTINGS======================================
SAMPLE_INTERVAL = 120
MAX_RESULTS = 10              #
mysql_config = {
    'host': 'hostname.yourcompany.com',
    'database': 'workdesk',
    'user': 'workdesk_report',
    'password': '********'
}
#===============================================================================


import json
import datetime
import time
import mysql.connector
from mysql.connector import errorcode

# Current MYSQL doesn't support groupby in a subquery, so we have to break into 2 SQL statements

# SQL to grab top classes and count of tickets

#SELECT class, count(class)
#FROM calls
#WHERE category IN ("Helpdesk", "Application Support", "Network Services")
#AND track >= UNIX_TIMESTAMP('2014-05-8 00:00:00')
#GROUP BY class
#ORDER BY count(class) DESC
#LIMIT 10

# SQL to grab count of ticket responses for specified classes

#SELECT c.class, count(c.class)
#FROM calls c JOIN notes n ON c.id = n.call_id
#WHERE c.category IN ("Helpdesk", "Application Support", "Network Services")
#AND c.track >= UNIX_TIMESTAMP('2014-05-8 00:00:00')
#AND c.class IN ("VIEW")
#GROUP BY c.class
#ORDER BY count(c.class) DESC
#LIMIT 10


class MonitorJSON:
    """This is a simple class passed to Monitor threads so we can access the current JSON data in that thread"""
    def __init__(self):
        # Set the default empty values for all
        category_data = [{"category": "----", "tickets": 0, "responses": 0}]
        self.json = json.dumps({"categories": category_data})


def generate_json(hd_monitor):
    global total_tickets, cursor, conn
    fromdate = datetime.date.today() + datetime.timedelta(days=-7)

    category_data = []
    class_bytickets = []
    classes = []

    try:
        # This first query will pull out a list top categories by ticket count
        conn = mysql.connector.connect(**mysql_config)
        query = (
            "SELECT class, count(class) AS count FROM calls "
            "WHERE category IN ('Helpdesk', 'Application Support', 'Network Services') "
            "AND track >= UNIX_TIMESTAMP(%s) "
            "GROUP BY class "
            "ORDER BY count(class) DESC "
            "LIMIT %s "
        )
        cursor = conn.cursor()
        cursor.execute(query, (fromdate.isoformat(), MAX_RESULTS))
        for (hdclass, count) in cursor:
            class_bytickets.append([hdclass, count])
            classes.append(hdclass)

        classes_string = ','.join(['%s'] * MAX_RESULTS)     # Creates "%s, %s, %s, %s"

        query = (
            "SELECT c.class, count(c.class) "
            "FROM calls c JOIN notes n ON c.id = n.call_id "
            "WHERE c.category IN ('Helpdesk', 'Application Support', 'Network Services') "
            "AND c.track >= UNIX_TIMESTAMP(%s) "
            "AND c.class IN ( " + classes_string + ") "
            "GROUP BY c.class "
            "ORDER BY count(c.class) DESC "
        )
        query_parameters = [fromdate.isoformat()]
        for (item) in classes:
            query_parameters.append(item)

        cursor.execute(query, query_parameters)
        for (resp_class, resp_count) in cursor:
            for (tick_class, tick_count) in class_bytickets:
                if tick_class == resp_class:
                    category_data.append({"category": tick_class, "tickets": tick_count, "responses": resp_count})
                    break

        query = (
            "SELECT COUNT(*) "
            "FROM calls "
            "WHERE category IN ('Helpdesk', 'Application Support', 'Network Services') "
            "AND status = 'OPEN' "
            "AND track >= UNIX_TIMESTAMP(%s) "
        )
        cursor.execute(query, [fromdate.isoformat()])
        for (count) in cursor:
            total_tickets = count


    except mysql.connector.Error as err:
        print err
        hd_monitor.json = json.dumps({"categories": [{"error": err.msg}]})
    else:
        hd_monitor.json = json.dumps({"categories": category_data, "total": total_tickets})

    finally:
        cursor.close()
        conn.close()


    if __debug__:
        print hd_monitor.json


# If you run this module by itself, it will instantiate the MonitorJSON class and start an infinite loop printing data.
if __name__ == '__main__':
    monitor = MonitorJSON()
    while True:
        generate_json(monitor)
        # Wait X seconds for the next iteration
        time.sleep(SAMPLE_INTERVAL)