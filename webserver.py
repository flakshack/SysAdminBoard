#!/usr/bin/env python
"""webserver.py - This is the main script. It will launch a webserver and startup the other scripts in other threads.

Find the MODULES section below to enable or disable individual modules (ensure they work by executing them by
themselves first.

"""

# Be sure to use pip to install CherryPy and routes:
# pip install CherryPy
# pip install importlib
# pip install routes

import cherrypy
from cherrypy.lib.static import serve_file
from cherrypy.process.plugins import Daemonizer
import os
import importlib


class SysAdminBoardModule:
    """ This class will take the specified module name, import the module file and setup the callback functions
        with CherryPy to gather data.
    """
    all_modules = []      # Static array containing all modules

    def __init__(self, module_name):
        # Dynamically import the python module file
        self.module_name = module_name
        self.module = importlib.import_module(module_name, package=None)
        self.frequency = self.module.SAMPLE_INTERVAL
        self.data = self.module.MonitorJSON()            # Custom class to store the JSON data

        # Add a thread in CherryPy to execute our callback funciton
        cherrypy.process.plugins.Monitor(cherrypy.engine, self.callback_function, frequency=self.frequency).subscribe()

        # Rather than wait for the first CherryPy timer to trigger, we'll gather the first set of data now
        self.callback_function()

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
        #cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"     # Bypass Javascript security for testing only
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return self.data.json



class MyWebServer(object):
    """This is the main CherryPy WebServer class that defines the URLs available."""
    # The following HTML will be displayed if someone browses to this webserver directly.
    @cherrypy.expose
    def index(self, **params):
        html = """<html><head><title>SysAdminBoard Gadget Server</title></head><body>
            <p>This web server provides data to the <a href="http://panic.com/statusboard/">Panic StatusBoard</a> iPad app.</p>
            <p>Here is a list of available Gadgets and data sources:</p>"""

        for sb_module in SysAdminBoardModule.all_modules:
            html += '<a href="/' + sb_module.module_name + '?desktop">' + sb_module.module_name + '</a><br/>'
            html += '<a href="/' + sb_module.module_name + '/ajax">' + sb_module.module_name + ' Ajax Data</a><br/>'

        return html


#=====================================================================================================
#                                         MODULES
#=====================================================================================================
# Specify the modules you want to execute.  (put a # comment in front of modules to disable them).
SysAdminBoardModule('sample')
# SysAdminBoardModule('msexchange')
# SysAdminBoardModule('snmp_interface_1')
# SysAdminBoardModule('snmp_interface_2')
# SysAdminBoardModule('snmp_environmental_1')
# SysAdminBoardModule('tintri')
# SysAdminBoardModule('vmware_host')
# SysAdminBoardModule('vmware_view_host')
# SysAdminBoardModule('vmware_view_vm')
# SysAdminBoardModule('vmware_vm')
# SysAdminBoardModule('helpdesk_byuser')
# SysAdminBoardModule('helpdesk_bycategory')
# SysAdminBoardModule('vnx_reporter')
#=====================================================================================================
#
#=====================================================================================================

root = MyWebServer()

mapper = cherrypy.dispatch.RoutesDispatcher()  # Used to manually map URLs to functions in CherryPy

# Loop through all of the modules we've enabled and establish a CherryPy URL using the RoutesDispatcher.
# The URLs are based on the module name.  For example, if the module name is vmware_host, then the URLs will be:
# http://server/vmware_host and http://server/vmware_host/ajax
for sysadminboard_module in SysAdminBoardModule.all_modules:
    # The root URL:  http://server/
    mapper.connect("index", "/", controller=root, action='index')
    mapper.connect(sysadminboard_module.module_name, "/" + sysadminboard_module.module_name,
                   controller=sysadminboard_module, action='index')
    mapper.connect(sysadminboard_module.module_name + '/ajax', "/" + sysadminboard_module.module_name + '/ajax',
                   controller=sysadminboard_module, action='ajax')

# Here we define a location for non-python files
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, u"static")
CONFIG = {
    '/': {
        'request.dispatch': mapper,                             # use a dispatcher to assign URLs
    },
    '/static': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': STATIC_DIR
    },
}

#=================Disable this line when debugging==============
Daemonizer(cherrypy.engine).subscribe()                         # When we start, do it as a daemon process
#===============================================================

cherrypy.config.update({'server.socket_host': '0.0.0.0'})       # Listen on all local IPs (on port 8080)
cherrypy.tree.mount(root, '/', config=CONFIG)                   # Mount the app on the root
cherrypy.engine.start()                                         # Start the web server


