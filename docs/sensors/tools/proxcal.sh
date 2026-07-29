#!/bin/sh
# SPDX-License-Identifier: MIT
# proxcal.sh - read the proximity channel once a second so a hand over the
# earpiece can be seen in the numbers.
#
# This is the one measurement that cannot be made from here: it needs someone
# to cover the sensor. iio-sensor-proxy needs a PROXIMITY_NEAR_LEVEL to decide
# near from far, and which side of it is "near" is not obvious -- the SSC may
# report a distance (near = small) or a raw count (near = large). Run this,
# cover the top of the screen next to the earpiece for a few seconds, uncover
# it, and the two levels are in the output.
set -u
DEV=
for d in /sys/bus/iio/devices/iio:device*; do
	[ "$(cat "$d/name" 2>/dev/null)" = "qcom-smgr-prox-light" ] && DEV=$d
done
if [ -z "$DEV" ]; then
	echo "no qcom-smgr-prox-light device -- is the smgr_prox module loaded?" >&2
	exit 1
fi
if [ ! -e "$DEV/in_proximity_raw" ]; then
	echo "$DEV has no in_proximity_raw: this kernel predates the raw channel" >&2
	exit 1
fi

echo "reading $DEV/in_proximity_raw -- cover the earpiece, then uncover it"
N="${1:-40}"
i=0
while [ "$i" -lt "$N" ]; do
	printf '%3d  %s\n' "$i" "$(cat "$DEV/in_proximity_raw")"
	i=$((i + 1))
	sleep 1
done
