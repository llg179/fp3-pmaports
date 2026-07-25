#!/bin/sh
# Category: camera
# Description: the rear sensor is in the device tree, bound, and wired to CAMSS
#
# Three distinct failures, deliberately told apart, because they send you to
# completely different places:
#
#   no sensor node in the live DT -> you are running the wrong device tree
#   node present, driver absent   -> the module was not built or not loaded
#   bound but unlinked            -> the media graph is wrong
#
# The first one is not hypothetical. Any apk operation can fire the mkinitfs
# trigger, which reinstalls /boot/<board>.dtb FROM THE PACKAGE - silently
# overwriting a hand-deployed device tree. Installing an unrelated tool cost the
# camera exactly this way on 2026-07-25: the package predated the camera DT
# work, so the sensor node vanished and the driver simply never probed. There
# are no dmesg lines to find in that state, which is what makes it confusing.

fail=0

# 1. Is the sensor even described to the kernel?
if [ -d /proc/device-tree ]; then
	if find /proc/device-tree -iname '*imx363*' 2>/dev/null | grep -q .; then
		echo "PASS: the live device tree describes the imx363 sensor"
	else
		echo "FAIL: no imx363 node in the live device tree"
		echo "      The running DTB does not describe the camera, so the driver"
		echo "      has nothing to bind to and will not log anything at all."
		echo "      Deploy the DTB from the kernel package you actually built"
		echo "      (an apk operation may have overwritten it via mkinitfs)."
		exit 1
	fi
fi

# 2. Did CAMSS come up?
if [ ! -e /dev/media0 ]; then
	echo "FAIL: no /dev/media0 - CAMSS did not probe"
	exit 1
fi

graph=$(media-ctl -d /dev/media0 -p 2>/dev/null)

if printf '%s\n' "$graph" | grep -q 'entity.*imx363'; then
	echo "PASS: imx363 subdev present in the media graph"
else
	echo "FAIL: the sensor is in the device tree but not in the media graph"
	echo "      (driver not loaded, or its probe failed - check dmesg for imx363)"
	fail=1
fi

# 3. An entity with no enabled link is not reachable by any capture pipeline.
if printf '%s\n' "$graph" | grep -A4 'imx363' | grep -q '\[ENABLED'; then
	echo "PASS: imx363 has an enabled link into CAMSS"
else
	echo "FAIL: imx363 has no enabled link - the sensor is not wired to CAMSS"
	fail=1
fi

exit $fail
