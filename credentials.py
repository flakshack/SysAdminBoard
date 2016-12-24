#!/usr/bin/env python
"""credentials - the login credentials for all of the modules are stored here and imported into each module.

Please be sure that you are using restricted accounts (preferably with read-only access) to your servers.

"""

__author__ = 'scott@flakshack.com (Scott Vintinner)'



# VMware
VMWARE_VCENTER_USERNAME = "domain\\username"
VMWARE_VCENTER_PASSWORD = "yourpassword"


# SNMP Community String (Read-Only)
SNMP_COMMUNITY = "public"


# Tintri
TINTRI_USER = "youraccount"
TINTRI_PASSWORD = "yourpassword"


# Workdesk MySQL
WORKDESK_USER = 'youraccount'
WORKDESK_PASSWORD = 'yourpassword'

# Rubrik
RUBRIK_USER = 'youraccount'
RUBRIK_PASSWORD = 'yourpassword'

# Nutanix
NUTANIX_USER = 'youraccount'
NUTANIX_PASSWORD = 'yourpassword'
