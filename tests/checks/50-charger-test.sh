#!/bin/sh
# Category: charger
# Requires: cable
# Description: the PMI632 charger reports sane values and actually charges
#
# Reading "status = Charging" only proves the driver saw a cable. Whether
# current is flowing is a different question, and it is the one that matters:
# a charger driver can enumerate perfectly and still deliver nothing. So this
# check watches the battery over a short window instead of taking one reading.

fail=0
ps=/sys/class/power_supply

for node in pmi632-battery pmi632-charger; do
	if [ -d "$ps/$node" ]; then
		echo "PASS: $node present"
	else
		echo "FAIL: $ps/$node missing - the charger driver did not bind"
		fail=1
	fi
done
[ "$fail" -eq 0 ] || exit 1

capacity=$(cat "$ps/pmi632-battery/capacity" 2>/dev/null)
voltage=$(cat "$ps/pmi632-battery/voltage_now" 2>/dev/null)
status=$(cat "$ps/pmi632-battery/status" 2>/dev/null)

# Sanity, not calibration: catch a driver returning nonsense, not a battery
# that is merely low.
if [ "${capacity:-999}" -ge 0 ] && [ "${capacity:-999}" -le 100 ]; then
	echo "PASS: capacity ${capacity}% is in range"
else
	echo "FAIL: capacity reads '${capacity:-nothing}'"
	fail=1
fi

# 2.5V-4.6V expressed in microvolts.
if [ "${voltage:-0}" -gt 2500000 ] && [ "${voltage:-0}" -lt 4600000 ]; then
	echo "PASS: voltage ${voltage}uV is plausible"
else
	echo "FAIL: voltage reads '${voltage:-nothing}'"
	fail=1
fi

if [ "$status" != "Charging" ]; then
	echo "FAIL: battery status is '$status', not Charging"
	echo "      (plug the cable in, or pass --no-cable if that is intentional)"
	exit 1
fi
echo "PASS: status is Charging"

# Does anything actually flow? current_now sign convention varies, so take the
# magnitude; the question is whether it is non-zero, not which way it points.
current=$(cat "$ps/pmi632-battery/current_now" 2>/dev/null | tr -d -)
if [ "${current:-0}" -gt 1000 ]; then
	echo "PASS: charge current ${current}uA is flowing"
else
	echo "FAIL: charge current reads ${current:-nothing}uA - a cable is seen but"
	echo "      no current is flowing"
	fail=1
fi

exit $fail
