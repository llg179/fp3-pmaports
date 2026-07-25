#!/bin/sh
# Requires: modem
# Description: the modem is present and registered on a network
#
# Registration, not just presence: the voice checks and the incoming-call check
# both depend on it, and "modem enumerated but never registered" is the state
# that makes those fail for reasons that have nothing to do with audio.

if ! command -v mmcli >/dev/null 2>&1; then
	echo "FAIL: mmcli not installed"
	exit 1
fi

if ! mmcli -L 2>/dev/null | grep -q Modem; then
	echo "FAIL: ModemManager sees no modem"
	exit 1
fi
echo "PASS: modem enumerated"

state=$(mmcli -m 0 2>/dev/null | sed -n 's/.*state: *//p' | head -1 | tr -d "'")
case "$state" in
*registered* | *connected*)
	echo "PASS: modem state is $state"
	exit 0
	;;
*)
	echo "FAIL: modem state is '${state:-unknown}', not registered"
	echo "      (pass --no-modem if there is deliberately no SIM here)"
	exit 1
	;;
esac
