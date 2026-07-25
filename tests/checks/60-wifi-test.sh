#!/bin/sh
# Requires: wifi
# Description: wlan0 is up and connected
#
# Deliberately checks the connection and not just the interface: the wifi
# driver binding is necessary but not sufficient, and a firmware that loads
# without associating is a regression class of its own on this SoC.

state=$(nmcli -t -f DEVICE,STATE device 2>/dev/null | grep '^wlan0:' | cut -d: -f2)
case "$state" in
connected)
	echo "PASS: wlan0 connected"
	exit 0
	;;
"")
	echo "FAIL: no wlan0 device - the wifi driver did not bind"
	exit 1
	;;
*)
	echo "FAIL: wlan0 is '$state', not connected"
	echo "      (pass --no-wifi if there is deliberately no network here)"
	exit 1
	;;
esac
