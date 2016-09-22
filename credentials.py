#!/usr/bin/env python
"""credentials - the login credentials for all of the modules are stored here and imported into each module.

Please be sure that you are using restricted accounts (preferably with read-only access) to your servers.

"""

__author__ = 'scott@flakshack.com (Scott Vintinner)'


# EMC VNX Reporter
VNX_REPORTER_USERNAME = "someuser"
VNX_REPORTER_PASSWORD = "somepassword"


# VMware
VMWARE_VCENTER_USERNAME = "somedomain\\someuser"
VMWARE_VCENTER_PASSWORD = "somepassword"


# SNMP Community String (Read-Only)
SNMP_COMMUNITY = "public"


# Tintri
TINTRI_USER = "someuser"
TINTRI_PASSWORD = "somepassword"


# Workdesk MySQL
WORKDESK_USER = 'someuser'
WORKDESK_PASSWORD = 'somepassword'

# Rubrik
RUBRIK_USER = 'someuser'
RUBRIK_PASSWORD = 'somepassword'
