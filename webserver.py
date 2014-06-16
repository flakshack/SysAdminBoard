#!/usr/bin/env python
"""webserver.py - This is the main script. It will launch a webserver and startup the other scripts in other threads."""


# pip install CherryPy

import cherrypy
from cherrypy.lib.static import serve_file
from cherrypy.process.plugins import Daemonizer
import os
import msexchange
import snmp_interface_1
import snmp_interface_2
import snmp_environmental_1
import vmware_host
import vmware_view_host
import vmware_view_vm
import vmware_vm
import helpdesk_byuser
import helpdesk_bycategory
import vnx_reporter


# Here we define a location for non-python files
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, u"static")
CONFIG = {
    '/static': {
        'tools.staticdir.on': True,
        'tools.staticdir.dir': STATIC_DIR
    }
}


class MyWebServer(object):
    """This is the main CherryPy WebServer class that defines the URLs available."""
    # / - root
    @cherrypy.expose
    def index(self):
        html = """<html><head><title>SysAdminBoard Gadget Server</title></head><body>
            This web server provides data to the StatusBoard iPad app.<br/>
            For testing, try visiting these pages:<br/>
            <a href="http://sysadminboard.yourcompany.local/static/vmhost.html?desktop">http://sysadminboard.yourcompany.local/static/vmhost.html?desktop</a><br/>
            <a href="http://sysadminboard.yourcompany.local/static/vm.html?desktop">http://sysadminboard.yourcompany.local/static/vm.html?desktop</a><br/>
            <a href="http://sysadminboard.yourcompany.local/static/vnx.html?desktop">http://sysadminboard.yourcompany.local/static/vnx.html?desktop</a><br/>
             <a href="http://sysadminboard.yourcompany.local/static/env1.html?desktop">http://sysadminboard.yourcompany.local/static/env1.html?desktop</a><br/>
             <a href="http://sysadminboard.yourcompany.local/static/exch.html?desktop">http://sysadminboard.yourcompany.local/static/exch.html?desktop</a><br/>
            </body></html>
        """
        return html

    @cherrypy.expose
    def env1(self):
        return serve_file(os.path.join(STATIC_DIR, 'env1.html'))

    @cherrypy.expose
    def env1_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        #cherrypy.response.headers["Access-Control-Allow-Origin"] = "*"     # Bypass Javascript security for testing only
        return snmp_environmental_1_data.json

    @cherrypy.expose
    def hd_byuser(self):
        return serve_file(os.path.join(STATIC_DIR, 'hd_byuser.html'))

    @cherrypy.expose
    def hd_byuser_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return hd_byuser_data.json

    @cherrypy.expose
    def hd_bycategory(self):
        return serve_file(os.path.join(STATIC_DIR, 'hd_bycategory.html'))

    @cherrypy.expose
    def hd_bycategory_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return hd_bycategory_data.json

    @cherrypy.expose
    def host(self):
        return serve_file(os.path.join(STATIC_DIR, 'vmhost.html'))

    @cherrypy.expose
    def host_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return vmware_host_data.json

    @cherrypy.expose
    def exch(self):
        return serve_file(os.path.join(STATIC_DIR, 'exch.html'))

    @cherrypy.expose
    def exch_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return exch_data.json

    @cherrypy.expose
    def view_host(self):
        return serve_file(os.path.join(STATIC_DIR, 'view_host.html'))

    @cherrypy.expose
    def view_host_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return vmware_view_host_data.json

    @cherrypy.expose
    def view_vm(self):
        return serve_file(os.path.join(STATIC_DIR, 'view_vm.html'))

    @cherrypy.expose
    def view_vm_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return vmware_view_vm_data.json

    @cherrypy.expose
    def vm(self):
        return serve_file(os.path.join(STATIC_DIR, 'vm.html'))

    @cherrypy.expose
    def vm_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return vmware_vm_data.json

    @cherrypy.expose
    def vnx(self):
        return serve_file(os.path.join(STATIC_DIR, 'vnx.html'))

    @cherrypy.expose
    def vnx_ajax(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return vnx_data.json

    @cherrypy.expose
    def wan1(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return snmp_interface_1_data.json

    @cherrypy.expose
    def wan2(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return snmp_interface_2_data.json



#=======================Callback Functions==========================
# Each of these functions creates a separate thread that is run every "frequency" seconds by cherrypy to
# update the json data on the variable passed to it.

def exch_callback():
    global exch_data
    msexchange.generate_json(exch_data)


def snmp_interface_1_callback():
    global snmp_interface_1_data
    snmp_interface_1.generate_json(snmp_interface_1_data)


def snmp_interface_2_callback():
    global snmp_interface_2_data
    snmp_interface_2.generate_json(snmp_interface_2_data)


def snmp_environmental_1_callback():
    global snmp_environmental_1_data
    snmp_environmental_1.generate_json(snmp_environmental_1_data)


def vmware_host_callback():
    global vmware_host_data
    vmware_host.generate_json(vmware_host_data)


def vmware_vm_callback():
    global vmware_vm_data
    vmware_vm.generate_json(vmware_vm_data)


def vmware_view_host_callback():
    global vmware_view_host_data
    vmware_view_host.generate_json(vmware_view_host_data)


def vmware_view_vm_callback():
    global vmware_view_vm_data
    vmware_view_vm.generate_json(vmware_view_vm_data)


def vnx_reporter_callback():
    global vnx_data
    vnx_reporter.generate_json(vnx_data)


def hd_byuser_callback():
    global hd_byuser_data
    helpdesk_byuser.generate_json(hd_byuser_data)


def hd_bycategory_callback():
    global hd_bycategory_data
    helpdesk_bycategory.generate_json(hd_bycategory_data)





#==========================Register Callback Functions==========================
# In this section, we create a global variable to hold data for each module and then register the callback function
# with the CherryPy engine so that each module will be launched in a separate thread.

#========= Exchange Perfmon Counters =========
exch_data = msexchange.MonitorJSON()
frequency = msexchange.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, exch_callback, frequency=frequency).subscribe()

#========= SNMP Interface 1 =========
snmp_interface_1_data = snmp_interface_1.MonitorJSON()
frequency = snmp_interface_1.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, snmp_interface_1_callback, frequency=frequency).subscribe()

#========= SNMP Interface 2 =========
snmp_interface_2_data = snmp_interface_2.MonitorJSON()
frequency = snmp_interface_2.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, snmp_interface_2_callback, frequency=frequency).subscribe()

#========= SNMP Environmental 1 =========
snmp_environmental_1_data = snmp_environmental_1.MonitorJSON()
frequency = snmp_environmental_1.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, snmp_environmental_1_callback, frequency=frequency).subscribe()

#========= VMware Host ==============
vmware_host_data = vmware_host.MonitorJSON()
frequency = vmware_host.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, vmware_host_callback, frequency=frequency).subscribe()

#========= VMware VM ==============
vmware_vm_data = vmware_vm.MonitorJSON()
frequency = vmware_vm.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, vmware_vm_callback, frequency=frequency).subscribe()

#========= VMware View Host ==============
vmware_view_host_data = vmware_view_host.MonitorJSON()
frequency = vmware_view_host.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, vmware_view_host_callback, frequency=frequency).subscribe()

#========= VMware View VM ==============
vmware_view_vm_data = vmware_view_vm.MonitorJSON()
frequency = vmware_view_vm.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, vmware_view_vm_callback, frequency=frequency).subscribe()

#========= EMC VNX ==============
vnx_data = vnx_reporter.MonitorJSON()
frequency = vnx_reporter.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, vnx_reporter_callback, frequency=frequency).subscribe()

#========= Helpdesk ByUser ==============
hd_byuser_data = helpdesk_byuser.MonitorJSON()
frequency = helpdesk_byuser.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, hd_byuser_callback, frequency=frequency).subscribe()

#========= Helpdesk ByCategory ==============
hd_bycategory_data = helpdesk_bycategory.MonitorJSON()
frequency = helpdesk_bycategory.SAMPLE_INTERVAL
cherrypy.process.plugins.Monitor(cherrypy.engine, hd_bycategory_callback, frequency=frequency).subscribe()






# Callback functions won't run until after first FREQUENCY, so run them once now
exch_callback()
snmp_environmental_1_callback()
snmp_interface_1_callback()
snmp_interface_2_callback()
vmware_host_callback()
vmware_vm_callback()
vmware_view_host_callback()
vmware_view_vm_callback()
vnx_reporter_callback()
hd_byuser_callback()
hd_bycategory_callback()

Daemonizer(cherrypy.engine).subscribe()                         # When we start, do it as a daemon process
cherrypy.config.update({'server.socket_host': '0.0.0.0'})       # Listen on all local IPs (default is 8080)
cherrypy.tree.mount(MyWebServer(), '/', config=CONFIG)          # Mount the app on the root
cherrypy.engine.start()                                         # Start the web server


