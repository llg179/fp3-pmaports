#!/bin/sh
# Category: camera
# Description: the lens actuator is described, bound, and exposes a focus control
#
# This is the structural half of the focus test. It needs no scene and no
# judgement, so it can run in the battery. The half it cannot cover - whether
# writing the control actually moves the lens - needs something to point the
# camera at, and lives in userspace-camera/focus-sweep.py.
#
# The three failures are kept apart for the same reason as in 40-camera-test:
# they send you to different places. A missing node means the wrong DTB is
# deployed; a node with no driver means the module was not built; a bound
# device with no control means the driver bound but registered nothing.

fail=0

# 1. Is the actuator described to the kernel?
# As with the sensor, the part number appears in the *value* of 'compatible'
# (onnn,lc898217xc), never in a node or property name.
if [ -d /proc/device-tree ]; then
	if grep -rla 'lc898217' /proc/device-tree/ 2>/dev/null | grep -q .; then
		echo "PASS: the live device tree describes the lc898217 actuator"
	else
		echo "FAIL: no lc898217 node in the live device tree"
		echo "      The running DTB does not describe the focus motor, so the"
		echo "      driver has nothing to bind to and logs nothing at all."
		echo "      Deploy the DTB from the kernel package you actually built."
		exit 1
	fi
fi

# 2. Did the driver bind? A lens entity in the media graph is the evidence.
if [ ! -e /dev/media0 ]; then
	echo "FAIL: no /dev/media0 - CAMSS did not probe"
	exit 1
fi

if media-ctl -d /dev/media0 -p 2>/dev/null | grep -q 'lc898217'; then
	echo "PASS: lc898217 lens entity present in the media graph"
else
	echo "FAIL: the actuator is in the device tree but not in the media graph"
	echo "      (module not built or probe failed - check dmesg for lc898217)"
	fail=1
fi

# 3. Does it expose the control that makes it useful?
# The subdev index moves between boots, so match on the control rather than on
# a device number.
found=""
for sd in /dev/v4l-subdev*; do
	[ -e "$sd" ] || continue
	if v4l2-ctl -d "$sd" -l 2>/dev/null | grep -q 'focus_absolute'; then
		found="$sd"
		break
	fi
done

if [ -n "$found" ]; then
	range=$(v4l2-ctl -d "$found" -l 2>/dev/null | grep 'focus_absolute')
	echo "PASS: focus_absolute on $found"
	echo "      $range"
else
	echo "FAIL: no subdev exposes focus_absolute"
	echo "      The driver bound but registered no control, or it is not bound."
	fail=1
fi

exit $fail
