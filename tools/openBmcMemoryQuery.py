#!/usr/bin/python

import argparse
import cookielib
import ssl
import urllib2
import json

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Perform OpenBMC memory queries.")
    parser.add_argument("-n", "--hostname", action="store", type=str, dest="hostname", help="hostname")
    parser.add_argument("-u", "--user",     action="store", type=str, dest="user",     help="user")
    parser.add_argument("-p", "--password", action="store", type=str, dest="password", help="password")

    ns = parser.parse_args ()

    if not ns.hostname:
        parser.error ("missing --hostname")
    if not ns.user:
        parser.error ("missing --user")
    if not ns.password:
        parser.error ("missing --password")

    cj = cookielib.CookieJar()

    # Avoid the following:
    # urllib2.URLError: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed (_ssl.c:590)>
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    opener = urllib2.build_opener(urllib2.HTTPRedirectHandler(),
                                  urllib2.HTTPHandler(debuglevel=0),
                                  urllib2.HTTPSHandler(debuglevel=0, context=ctx),
                                  urllib2.HTTPCookieProcessor(cj))

    # Log in with a special URL and JSON data structure
    login_data = json.dumps({"data": [ ns.user, ns.password ]})
    req = urllib2.Request("https://%s/login" % (ns.hostname, ),
                          login_data,
                          headers={"Content-Type": "application/json"})
    response = opener.open(req)

    if response.code != 200:
        print sys.stderr, "Error: response code to login is not 200! (%d)" % (response.code, )
        sys.exit (1)

    # Enumerate the inventory of the system hardware
    req = urllib2.Request("https://%s/org/openbmc/inventory/system/enumerate" % (ns.hostname, ),
                          headers={"Content-Type": "application/json"})
    response = opener.open(req)

    if response.code != 200:
        print sys.stderr, "Error: response code to system enumerate is not 200! (%d)" % (response.code, )
        sys.exit (1)

    # Convert the html response into a JSON structure
    list_data = response.readlines ()
    data = "".join (list_data)
    jdata = json.loads (data)

    # Loop through the returned map items
    for (key, value) in jdata["data"].items():
        # We only care about dimm entries
        if key.find ("/dimm") == -1:
            continue

        # Avoid something like /org/openbmc/inventory/system/chassis/motherboard/dimm2/event
        if key.endswith ("/event"):
            continue

        # At this point, we have:
        # {u'fru_type': u'DIMM', u'fault': u'False', u'is_fru': 1, u'version': u'', u'present': u'True'}

        # We don't care about non-physical hardware
        if value["present"] == "False":
            continue
        # We don't care about faulty hardware
        if value["fault"] == "True":
            continue

        print key
        print value

#       import pdb
#       pdb.set_trace()
