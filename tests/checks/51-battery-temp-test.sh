#!/bin/sh
# Category: charger
# Description: the battery reports a temperature, and a believable one
#
# Deliberately separate from 50-charger, which declares "Requires: cable" and is
# therefore skipped whole when no cable is attached. Battery temperature needs
# no cable: the pack thermistor is read through the PMIC ADC whether anything is
# charging or not, so folding this in there would have hidden the property in
# exactly the runs that do not plug the phone in.

fail=0
ps=/sys/class/power_supply

temp=$(cat "$ps/pmi632-battery/temp" 2>/dev/null)
if [ -z "$temp" ]; then
	echo "FAIL: no battery temp - the bat_therm ADC channel is not wired up"
	echo "      (needs the BAT_THERM entry in the adc5 channel table, the"
	echo "       pmi632 channel@4a, and bat_therm in the charger io-channels)"
	exit 1
fi

# Sanity, not calibration: -10C to 60C in decidegrees.
if [ "$temp" -gt -100 ] && [ "$temp" -lt 600 ]; then
	echo "PASS: battery temperature $((temp / 10))C is in range"
else
	echo "FAIL: battery temperature reads '$temp' decidegrees"
	fail=1
fi

# A thermistor curve can be plausible and still be the wrong curve, and a
# constant is plausible too. At idle the pack sits inside the same phone as the
# PMIC that measures it, so a large gap points at the scaling.
for z in /sys/class/thermal/thermal_zone*; do
	[ "$(cat "$z/type" 2>/dev/null)" = "pmi632-thermal" ] || continue
	die=$(($(cat "$z/temp" 2>/dev/null || echo 0) / 100))
	delta=$((temp - die))
	[ "$delta" -lt 0 ] && delta=$((-delta))
	if [ "$delta" -lt 200 ]; then
		echo "PASS: within $((delta / 10))C of the PMIC die"
	else
		echo "FAIL: battery $((temp / 10))C vs PMIC die $((die / 10))C"
		echo "      - too far apart to be the same phone at idle"
		fail=1
	fi
	break
done

# The power supply core registers a thermal zone for any battery that reports a
# temperature, so this is also how the rest of the system sees it.
zone=""
for z in /sys/class/thermal/thermal_zone*; do
	[ "$(cat "$z/type" 2>/dev/null)" = "pmi632-battery" ] && zone=$z && break
done
if [ -n "$zone" ]; then
	echo "PASS: exposed as a thermal zone too ($(($(cat "$zone/temp") / 1000))C)"
else
	echo "FAIL: no pmi632-battery thermal zone"
	fail=1
fi

exit $fail
