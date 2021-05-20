#!/usr/bin/env python
"""webserver.py - This is the main script. It will launch a webserver and startup the other scripts in other threads.

Find the MODULES section below to enable or disable individual modules (ensure they work by executing them by
themselves first.

"""

# Be sure to use pip to install CherryPy and routes:
# pip install CherryPy
# pip install routes

import cherrypy
from cherrypy.lib.static import serve_file
import os
import json
import logging.config
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning


class SysAdminBoardModule:
    """ This class will take the specified module name, import the module file and setup the callback functions
        with CherryPy to gather data.
    """
    all_modules = []      # Static array containing all modules

    def __init__(self, module_name):
        logger = logging.getLogger("SysAdminBoardModule")
        # Dynamically import the python module file
        self.module_name = module_name
        logger.info("Importing module: " + module_name)
        self.module = __import__(module_name)
        self.frequency = self.module.SAMPLE_INTERVAL
        self.data = self.module.MonitorJSON()            # Custom class to store the JSON data

        # Add a thread in CherryPy to execute our callback funciton
        logger.debug("Creating callback function for:  " + module_name)
        cherrypy.process.plugins.Monitor(cherrypy.engine, self.callback_function, frequency=self.frequency).subscribe()

        # Rather than wait for the first CherryPy timer to trigger, we'll gather the first set of data now
        logger.debug("First run of: " + module_name)
        try:
            self.callback_function()
        except Exception as error:
            # No matter what exception we hit here, we don't want this to stop other modules from running.
            logger.error("Error setting callback function " + str(error))
            pass

        self.__class__.all_modules.append(self)     # Add self to static array

    # Define the callback function that CherryPy will call every interval to gather data
    def callback_function(self):
        self.module.generate_json(self.data)

    # Define a web URL to return the static file (named with module_name.html)
    @cherrypy.expose
    def index(self, **params):
        return serve_file(os.path.join(STATIC_DIR, self.module_name + '.html'))

    # Define a web URL to return the ajax json data
    @cherrypy.expose
    def ajax(self, **params):
        # cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"  # Bypass Javascript security for testing only
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return self.data.json.encode('utf8')            # In Python3 data has to be utf8 encoded


class MyWebServer(object):
    """This is the main CherryPy WebServer class that defines the URLs available."""
    # The following HTML will be displayed if someone browses to this webserver directly.
    @cherrypy.expose
    def index(self, **params):
        hostname=cherrypy.request.headers['Host']
        html = """<html><head><title>SysAdminBoard</title></head><body>
            <p>See: <a href="https://github.com/flakshack/SysAdminBoard">https://github.com/flakshack/SysAdminBoard</a>
            </p>
            <p><h2>Available Dashboards</h2></p>
            <ul><li><a href="/static/1920x1080.html">http://""" + hostname + """/static/1920x1080.html</a></li>
            <li><a href="/static/1080x1920.html">http://""" + hostname + """/static/1080x1920.html</a></li>
            <li><a href="/static/ns1.html">http://""" + hostname + """/static/ns1.html</a></li>
            <li><a href="/static/ns2.html">http://""" + hostname + """/static/ns2.html</a></li>
            </ul>
            
            <p>Here is a list of active modules and data sources:</p>"""

        for sb_module in SysAdminBoardModule.all_modules:
            html += '<a href="/' + sb_module.module_name + '?desktop">' + sb_module.module_name + '</a><br/>'
            html += '<a href="/' + sb_module.module_name + '/ajax">' + sb_module.module_name + ' Ajax Data</a><br/>'

        return html

# =================MAIN==============

# Setup logging to capture errors
# When run by itself, we need to create the logger object (which is normally created in webserver.py)
try:
    f = open("log_settings.json", 'rt')
    log_config = json.load(f)
    f.close()
    logging.config.dictConfig(log_config)
except FileNotFoundError as e:
    print("Log configuration file not found: " + str(e))
    logging.basicConfig(level=logging.DEBUG)  # fallback to basic settings
except json.decoder.JSONDecodeError as e:
    print("Error parsing logger config file: " + str(e))
    raise

logger = logging.getLogger("SysAdminBoard Main")

logger.warn("Disabling SSL certificate verification log messages")
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


# =====================================================================================================
#
#
#                                          MODULES
#
#
#  ====================================================================================================
# Specify the modules you want to execute.  (put a # comment in front of modules to disable them).

SysAdminBoardModule('sample')
# SysAdminBoardModule('msexchange')
# SysAdminBoardModule('snmp_interface_1')
# SysAdminBoardModule('snmp_interface_2')
# SysAdminBoardModule('snmp_interface_3')
# SysAdminBoardModule('snmp_interface_4')
# SysAdminBoardModule('snmp_interface_5')
# SysAdminBoardModule('snmp_interface_6')
# SysAdminBoardModule('snmp_environmental_1')
# SysAdminBoardModule('prtg_channel_1')
# SysAdminBoardModule('prtg_interface_1')
# SysAdminBoardModule('prtg_interface_2')
# SysAdminBoardModule('tintri')
# SysAdminBoardModule('rubrik')
# SysAdminBoardModule('vmware_host')
# SysAdminBoardModule('vmware_view_host')
# SysAdminBoardModule('vmware_view_vm')
# SysAdminBoardModule('vmware_vm')
# SysAdminBoardModule('nutanix_vdi')
# SysAdminBoardModule('nutanix_svr')
# SysAdminBoardModule('nutanix_vm_vdi')
# SysAdminBoardModule('nutanix_vm_svr')
# SysAdminBoardModule('nutanix_svr_vm_cpu_ready')
# SysAdminBoardModule('nutanix_vdi_vm_cpu_ready')
# SysAdminBoardModule('vmware_vm_nutanix_cvm_vdi')
# SysAdminBoardModule('vmware_vm_nutanix_cvm_svr')
# SysAdminBoardModule('netapp')


# =====================================================================================================
#
# =====================================================================================================

root = MyWebServer()

mapper = cherrypy.dispatch.RoutesDispatcher()  # Used to manually map URLs to functions in CherryPy

# Loop through all of the modules we've enabled and establish a CherryPy URL using the RoutesDispatcher.
# The URLs are based on the module name.  For example, if the module name is vmware_host, then the URLs will be:
# http://server/vmware_host and http://server/vmware_host/ajax

for sysadminboard_module in SysAdminBoardModule.all_modules:
    logger.debug("Mapping module: " + sysadminboard_module.module_name + " to webserver routes / & /ajax")
    # The root URL:  http://server/
    mapper.connect("index", "/", controller=root, action='index')
    mapper.connect(sysadminboard_module.module_name, "/" + sysadminboard_module.module_name,
                   controller=sysadminboard_module, action='index')
    mapper.connect(sysadminboard_module.module_name + '/ajax', "/" + sysadminboard_module.module_name + '/ajax',
                   controller=sysadminboard_module, action='ajax')

# Here we define a location for non-python files
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")
CONFIG = {
    '/': {
        'request.dispatch': mapper,                             # use a dispatcher to assign URLs
    },
    '/static': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': STATIC_DIR,
        'tools.expires.on': True,
        'tools.expires.secs': 3600  # expire in an hour
    },
    '/favicon.ico': {
        'tools.staticfile.on': True,
        'tools.staticfile.filename': '/opt/sysadminboard/static/favicon.ico'
    }
}

# ===============================================================
logger.info("Starting up SysAdminBoard web server...")
cherrypy.log.access_log.propagate = False                        # Disable access logging
cherrypy.config.update({'server.socket_host': '0.0.0.0'})       # Listen on all local IPs (on port 8080)
cherrypy.tree.mount(root, '/', config=CONFIG)                   # Mount the app on the root
cherrypy.engine.start()                                         # Start the web server
