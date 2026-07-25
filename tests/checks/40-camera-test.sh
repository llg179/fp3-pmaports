#!/bin/sh
# Category: camera
# Description: the rear sensor is bound and wired into the CAMSS media graph
#
# hwtest already answers "is there a camera subdev", so this check answers the
# part it cannot: is the sensor actually linked into the pipeline. A sensor that
# probes but has no link to CAMSS looks healthy in every summary and produces no
# image - which is how a device-tree deploy going to the wrong DTB presents.

fail=0

if [ ! -e /dev/media0 ]; then
	echo "FAIL: no /dev/media0 - CAMSS did not probe"
	exit 1
fi

graph=$(media-ctl -d /dev/media0 -p 2>/dev/null)

if printf '%s\n' "$graph" | grep -q 'entity.*imx363'; then
	echo "PASS: imx363 subdev present in the media graph"
else
	echo "FAIL: no imx363 entity in the media graph"
	echo "      (sensor did not probe - check that the deployed DTB is the one"
	echo "       your package built, not a stale copy from the source tree)"
	fail=1
fi

# An entity with no enabled link is not reachable by any capture pipeline.
if printf '%s\n' "$graph" | grep -A4 'imx363' | grep -q '\[ENABLED'; then
	echo "PASS: imx363 has an enabled link into CAMSS"
else
	echo "FAIL: imx363 has no enabled link - the sensor is not wired to CAMSS"
	fail=1
fi

exit $fail
