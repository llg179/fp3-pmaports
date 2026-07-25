#!/bin/sh
# Requires: bt
# Description: the bluetooth controller is present and powered

if [ ! -d /sys/class/bluetooth/hci0 ]; then
	echo "FAIL: no hci0 - the bluetooth controller did not come up"
	exit 1
fi
echo "PASS: hci0 present"

# UP is in the flags of `hciconfig`-style output; bluetoothctl is what we have.
if bluetoothctl show 2>/dev/null | grep -q 'Powered: yes'; then
	echo "PASS: controller is powered"
	exit 0
fi
echo "FAIL: hci0 exists but is not powered"
exit 1
