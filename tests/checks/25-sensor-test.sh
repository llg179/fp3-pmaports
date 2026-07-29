#!/bin/sh
# Category: sensor
# Description: the SSC sensors enumerate and their readings are readable
#
# The sensors do not hang off a bus the AP can drive - they live inside the
# ADSP's Sensor Core, and nothing appears until userspace has served the sensor
# registry over QMI. So this check has to prove three separate things, because
# each of them fails in a way that looks exactly like the others from the
# outside: the registry server runs, the kernel bound a driver to every sensor
# the SSC advertises, and the readings can actually be read.
#
# What it deliberately does not check is whether the numbers are physically
# right - that needs someone to tilt the phone, cover the sensor and shine a
# light into it. userspace-sensors/sensortest.py does that interactively.

fail=0

# Without the registry server the SSC never starts its sensors and every check
# below fails with no IIO device at all - a very confusing symptom if the cause
# is not named first.
if systemctl is-active --quiet snsregd 2>/dev/null; then
	echo "PASS: snsregd (sensor registry server) is running"
else
	echo "FAIL: snsregd is not running - the SSC will not start its sensors"
	echo "      (see userspace-sensors/ for the install steps)"
	fail=1
fi

# Match on name, never on index: the Sensor Manager registers each device as
# its QMI enumeration completes, so iio:deviceN moves between boots.
find_iio() {
	for d in /sys/bus/iio/devices/iio:device*; do
		[ -r "$d/name" ] || continue
		if [ "$(cat "$d/name")" = "$1" ]; then
			printf '%s' "$d"
			return 0
		fi
	done
	return 1
}

for s in qcom-smgr-accel qcom-smgr-gyro qcom-smgr-mag qcom-smgr-prox-light; do
	if find_iio "$s" >/dev/null; then
		echo "PASS: $s bound ($(find_iio "$s"))"
	else
		echo "FAIL: $s has no IIO device - driver missing or SSC did not enumerate it"
		fail=1
	fi
done

prox=$(find_iio qcom-smgr-prox-light)
if [ -n "$prox" ]; then
	# Proximity and ambient light are two data types of one part, so a
	# failure on one and not the other means the sample routing is wrong
	# rather than the sensor being dead.
	if v=$(cat "$prox/in_proximity_raw" 2>/dev/null) && [ -n "$v" ]; then
		echo "PASS: in_proximity_raw reads ($v counts)"
	else
		echo "FAIL: in_proximity_raw unreadable - iio-sensor-proxy polls this"
		fail=1
	fi

	# Distinguish "the channel is not there" from "the read failed": the
	# first is a kernel that never asked for the secondary data type, the
	# second is a sensor that has not reported yet. They need different
	# fixes and look identical if the check only reports "unreadable".
	if [ ! -e "$prox/in_illuminance_input" ]; then
		echo "FAIL: no in_illuminance_input channel - the secondary data"
		echo "      type of the EPL259x is not being requested"
		fail=1
	elif v=$(cat "$prox/in_illuminance_input" 2>&1) && [ -n "$v" ]; then
		echo "PASS: in_illuminance_input reads ($v lux)"
	else
		echo "FAIL: in_illuminance_input present but the read failed: $v"
		echo "      (the light half has not reported since the report began)"
		fail=1
	fi
fi

# The udev property is what makes iio-sensor-proxy use the proximity sensor at
# all; without it the device exists and the proxy ignores it in silence.
if busctl --system get-property net.hadess.SensorProxy /net/hadess/SensorProxy \
	net.hadess.SensorProxy HasProximity 2>/dev/null | grep -q true; then
	echo "PASS: iio-sensor-proxy reports HasProximity (in-call blanking works)"
else
	echo "FAIL: iio-sensor-proxy does not see a proximity sensor"
	echo "      (PROXIMITY_NEAR_LEVEL udev rule missing?)"
	fail=1
fi

if busctl --system get-property net.hadess.SensorProxy /net/hadess/SensorProxy \
	net.hadess.SensorProxy HasAmbientLight 2>/dev/null | grep -q true; then
	echo "PASS: iio-sensor-proxy reports HasAmbientLight"
else
	echo "FAIL: iio-sensor-proxy does not see an ambient light sensor"
	fail=1
fi

exit $fail
