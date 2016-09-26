#!/usr/bin/python

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# Documentation:
#
# OpenBMC cheatsheet
# https://github.com/openbmc/docs/blob/master/cheatsheet.md
#
# OpenBMC REST API
# https://github.com/openbmc/docs/blob/master/rest-api.md
#
# OpenBMC DBUS API
# https://github.com/openbmc/docs/blob/master/dbus-interfaces.md
#

import argparse
import sys
import pdb
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import json

# Create a decorator pattern that maintains a registry
def makeRegistrar():
    registry = {}
    def registrar(func):
        registry[func.__name__] = func
        # normally a decorator returns a wrapped function, 
        # but here we return func unmodified, after registering it
        return func
    registrar.all = registry
    return registrar

# Create the decorator
command = makeRegistrar()

# Sadly a way to fit the line into 78 characters mainly
JSON_HEADERS = {"Content-Type": "application/json"}

def _login(session, args):
    # Log in with a special URL and JSON data structure
    login_data = json.dumps({"data": [ args.user, args.password ]})
    response = session.post ("https://%s/login" % (args.hostname, ),
                             data=login_data,
                             verify=False,
                             headers=JSON_HEADERS)

    if response.status_code != 200:
        err_str = ("Error: Response code to login is not 200!"
                   " (%d)" % (response.status_code, ))
        print >> sys.stderr, err_str
        return False

    return True

def _enumerate_org_openbmc(session, args, subpath):
    # Enumerate the inventory of the system's control hardware
    path = "org/openbmc"

    if subpath is None or subpath == "":
        # @BUG
        # url = "https://%s/%s/enumerate" % (args.hostname, path, )
        url = "https://%s/%s/" % (args.hostname, path, )
    else:
        url = "https://%s/%s/%s/enumerate" % (args.hostname, path, subpath, )

    response = session.get (url,
                            verify=False,
                            headers=JSON_HEADERS)

    if response.status_code != 200:
        err_str = ("Error: Response code to _enumerate_org_openbmc"
                   " enumerate is not 200! (%d)" % (response.status_code, ))
        print >> sys.stderr, err_str
        return None

    return response.json()["data"]

def _enumerate_org_openbmc_control(session, args):
    # Enumerate the inventory of the system's control hardware
    path = "org/openbmc/control"
    url = "https://%s/%s/enumerate" % (args.hostname, path, )
    response = session.get (url,
                            verify=False,
                            headers=JSON_HEADERS)

    if response.status_code != 200:
        err_str = ("Error: Response code to _enumerate_org_openbmc_control"
                   " enumerate is not 200! (%d)" % (response.status_code, ))
        print >> sys.stderr, err_str

        err_str = "Error: There is no /org/openbmc/control under /org/openbmc"
        print >> sys.stderr, err_str

        entries = _enumerate_org_openbmc(session,
                                         args,
                                         "")
        err_str = "Error: Entries are: %s" % (entries, )
        print >> sys.stderr, err_str

        return None

    mappings = {}
    filter_list = ["/power", "/chassis"]

    # Loop through the returned map items
    for (item_key, item_value) in response.json()["data"].items():
        # We only care about filter entries
        if not any(x in item_key for x in filter_list):
            continue

        if args.verbose:
            print "Found:"
            print item_key
            print item_value

        # Add the entry into our mappings
        for fltr in filter_list:
            idx = item_key.find(fltr)
            if idx > -1:
                # Get the identity (the rest of the string)
                ident = item_key[idx+len(fltr):]
                # Create a new map for the first time
                if not mappings.has_key(ident):
                    mappings[ident] = {}
                # Save both the full filename and map contents
                mappings[ident][fltr] = (item_key, item_value)

    return mappings

@command
def is_power(session, parser, args, subparsers = None):
    if subparsers is not None:
        parser_ispower = subparsers.add_parser("is_power")
        parser_ispower.add_argument("command",
                                    action="store",
                                    help="{on,off,?}")
        parser_ispower.set_defaults(func=is_power)
        return

    # Query /org/openbmc/control for power and chassis entries
    mappings = _enumerate_org_openbmc_control(session, args)
    if mappings is None:
        return False

    # Loop through the found power & chassis entries
    for (ident, ident_mappings) in mappings.items():

        # Grab our information back out of the mappings
        (power_url, power_mapping) = ident_mappings["/power"]
        (chassis_url, chassis_mapping) = ident_mappings["/chassis"]

        if args.verbose:
            msg = "Current state of %s is %s" % (power_url,
                                                 power_mapping["state"], )
            print msg

        if args.command.upper().lower() == "on":
            if power_mapping["state"] == 1:
                return True
            else:
                return False
        elif args.command.upper().lower() == "off":
            if power_mapping["state"] == 1:
                return False
            else:
                return True
        elif args.command.upper().lower() == "?":
            if power_mapping["state"] == 1:
                print "Power is on"
                return True
            else:
                print "Power is off"
                return True
        else:
            parser.error ("Unknown parameter %s" % (args.command, ))
            return False

@command
def set_power(session, parser, args, subparsers = None):
    if subparsers is not None:
        parser_set_power = subparsers.add_parser("set_power")
        parser_set_power.add_argument("command",
                                      action="store",
                                      help="{on,off}")
        parser_set_power.set_defaults(func=set_power)
        return

    # Query /org/openbmc/control for power and chassis entries
    mappings = _enumerate_org_openbmc_control(session, args)
    if mappings is None:
        return False

    # Loop through the found power & chassis entries
    for (ident, ident_mappings) in mappings.items():
        # { '/power':
        #     ( u'/org/openbmc/control/power0',
        #       {u'pgood': 1,
        #        u'poll_interval': 3000,
        #        u'pgood_timeout': 10,
        #        u'heatbeat': 0,
        #        u'state': 1
        #       }
        #     ),
        #   '/chassis':
        #     ( u'/org/openbmc/control/chassis0',
        #       {u'reboot': 0,
        #        u'uuid': u'24340d83aa784d858468993286b390a5'
        #       }
        #     )
        # }

        # Grab our information back out of the mappings
        (power_url, power_mapping) = ident_mappings["/power"]
        (chassis_url, chassis_mapping) = ident_mappings["/chassis"]

        if args.verbose:
            msg = "Current state of %s is %s" % (power_url,
                                                 power_mapping["state"], )
            print msg

#       pdb.set_trace()

        url = None
        jdata = None

        if args.command.upper().lower() == "on":
            if power_mapping["state"] == 0:
                msg = ("command 'power on' supplied and machine is off,"
                       " trying to call the powerOn method")
                print msg
                url = "https://%s%s/action/powerOn" % (args.hostname,
                                                       chassis_url, )
                jdata = json.dumps({"data": []})
            elif power_mapping["state"] == 1:
                msg = ("command 'power on' supplied and machine is on,"
                       " nothing to do")
                print msg
        elif args.command.upper().lower() == "off":
            if power_mapping["state"] == 0:
                msg = ("command 'power off' supplied and machine is off,"
                       " nothing to do")
                print msg
            elif power_mapping["state"] == 1:
                msg = ("command 'power off' supplied and machine in on,"
                       " trying to call the powerOff method")
                print msg
                url = "https://%s%s/action/powerOff" % (args.hostname,
                                                        chassis_url, )
                jdata = json.dumps({"data": []})
        else:
            parser.error ("Unknown parameter %s" % (args.command, ))
            return False

        if url is not None:
            if args.verbose:
                print "POST %s with %s" % (url, jdata, )

            response = session.post (url,
                                     data=jdata,
                                     verify=False,
                                     headers=JSON_HEADERS)

            if response.status_code != 200:
                err_str = ("Error: Response code to PUT is not 200!"
                           " (%d)" % (response.status_code, ))
                print >> sys.stderr, err_str
                return False

    return True

@command
def show_memory(session, parser, args, subparsers = None):
    if subparsers is not None:
        parser_show_memory = subparsers.add_parser("show_memory")
        parser_show_memory.set_defaults(func=show_memory)
        return

    path = "org/openbmc/inventory/system"
    url = "https://%s/%s/enumerate" % (args.hostname, path, )
    response = session.get (url,
                            verify=False,
                            headers=JSON_HEADERS)

    if response.status_code != 200:
        err_str = ("Error: Response code to system enumerate is not 200!"
                   " (%d)" % (response.status_code, ))
        print >> sys.stderr, err_str
        return False

    # Loop through the returned map items
    for (item_key, item_value) in response.json()["data"].items():
        # We only care about dimm entries
        if item_key.find ("/dimm") == -1:
            continue

        # Avoid something like /org/openbmc/inventory/system/chassis/motherboard/dimm2/event
        if item_key.endswith ("/event"):
            continue

        # @BUG
        # At this point, we have:
        # {u'Version': u'0x0000',
        #  u'Name': u'0x0b',
        #  u'Custom Field 8': u'',
        #  u'Custom Field 7': u'',
        #  u'Asset Tag': u'',
        #  u'Custom Field 5': u'',
        #  u'Custom Field 4': u'',
        #  u'Custom Field 3': u'',
        #  u'Custom Field 2': u'',
        #  u'Custom Field 1': u'',
        #  u'is_fru': 1,
        #  u'fru_type': u'DIMM',
        #  u'FRU File ID': u'',
        #  u'Serial Number': u'0x02bb58a7',
        #  u'Model Number': u'M393B2G70DB0-YK0  ',
        #  u'version': u'',
        #  u'Custom Field 6': u'',
        #  u'fault': u'False',
        #  u'present': u'True',
        #  u'Manufacturer': u'0xce80'
        # }
        # or:
        # {u'version': u'',
        #  u'is_fru': 1,
        #  u'fru_type': u'DIMM',
        #  u'fault': u'False',
        #  u'present': u'True'
        # }
        # depending if the system has been powered on before or not.

        # We don't care about non-physical hardware
        if item_value["present"] == "False":
            continue
        # We don't care about faulty hardware
        if item_value["fault"] == "True":
            continue
        # We need a model number
        if not item_value.has_key("Model Number"):
            continue

        print item_key
        print item_value

    return True

#@command
def _old_get_boot_progress(session, parser, args, subparsers = None):
    if subparsers is not None:
        parser_get_boot_process = subparsers.add_parser("get_boot_progress")
        parser_get_boot_process.set_defaults(func=_old_get_boot_progress)
        return

    path = "org/openbmc/sensors/host/BootProgress"
    url = "https://%s/%s" % (args.hostname, path, )
    response = session.get (url,
                            verify=False,
                            headers=JSON_HEADERS)
    if args.verbose:
        print "GET %s" % (url, )
    response = session.post (url,
                            verify=False,
                            data=jdata,
                            headers=JSON_HEADERS)

    if response.status_code != 200:
        err_str = ("Error: Response code to system enumerate is not 200!"
                   " (%d)" % (response.status_code, ))
        print >> sys.stderr, err_str
        return False

#   pdb.set_trace()

    progress = response.json()["data"]

    # {u'units': u'', u'value': u'Off', u'error': 0}

    print "Progress: %s" % (progress["value"], )

    return True

@command
def get_boot_progress(session, parser, args, subparsers = None):
    if subparsers is not None:
        parser_get_boot_process = subparsers.add_parser("get_boot_progress")
        parser_get_boot_process.set_defaults(func=get_boot_progress)
        return

    path = "org/openbmc/sensors/host/BootProgress/action/getValue"
    url = "https://%s/%s" % (args.hostname, path, )
    jdata = json.dumps({"data": []})
    if args.verbose:
        print "POST %s with %s" % (url, jdata, )
    response = session.post (url,
                            verify=False,
                            data=jdata,
                            headers=JSON_HEADERS)

    if response.status_code != 200:
        err_str = ("Error: Response code to system enumerate is not 200!"
                   " (%d)" % (response.status_code, ))
        print >> sys.stderr, err_str
        return False

#   pdb.set_trace()

    progress = response.json()["data"]

    # u'Off'

    print "Progress: %s" % (progress, )

    return True

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Perform OpenBMC operations.")
    parser.add_argument("-n",            # Sadly -h is already taken
                        "--hostname",
                        action="store",
                        type=str,
                        dest="hostname",
                        help="hostname")
    parser.add_argument("-u",
                        "--user",
                        action="store",
                        type=str,
                        dest="user",
                        help="user")
    parser.add_argument("-p",
                        "--password",
                        action="store",
                        type=str,
                        dest="password",
                        help="password")
    parser.add_argument("-v",
                        "--verbose",
                        action="store_true",
                        dest="verbose",
                        help="verbose")

    subparsers = parser.add_subparsers(help='sub-command help')

    # Tell all decorated functions that they need to setup their argparse
    # sub-section
    for func in command.all.values():
        func (None,       # We don't care about session
              parser,
              None,       # We don't have args yet
              subparsers) # Tell the function to setup for argparse

    # Finally parse the command line arguments
    args = parser.parse_args()

    # Make sure required arguments are present
    if not args.hostname:
        parser.error ("missing --hostname")
    if not args.user:
        parser.error ("missing --user")
    if not args.password:
        parser.error ("missing --password")

    # disable the following warning written to stdout:
    # InsecureRequestWarning: Unverified HTTPS request is being made.
    # Adding certificate verification is strongly advised.
    # See: https://urllib3.readthedocs.org/en/latest/security.html
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

    # Create a http session
    session = requests.Session()

    # Log into the host session
    if not _login(session, args):
        sys.exit(1)

    # Call the specified command with passed in args
    if not args.func(session, parser, args):
        sys.exit(2)
