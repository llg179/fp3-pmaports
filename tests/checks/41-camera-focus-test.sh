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
#
# ☠️ Nothing here names a single part. Fairphone ships this phone with two
# different rear camera modules and they do not carry the same actuator: the
# original takes an LC898217XC at 0x72, both second-source modules an AK7374 at
# 0x0c. A check hardcoded to either one reports a hardware difference as a
# failure. So the device-tree step accepts any actuator this port knows about,
# and the two steps after it ask the media graph and the control API - which do
# not care which part answered.

fail=0

# Compatibles this port can drive, as they appear in the *value* of the node's
# 'compatible' property. A part number never appears in a node or property
# *name*, so grep the contents.
known='lc898217|ak7374'

# 1. Is an actuator described to the kernel?
if [ -d /proc/device-tree ]; then
	found_dt=$(grep -rlaE "$known" /proc/device-tree/ 2>/dev/null | head -1)
	if [ -n "$found_dt" ]; then
		part=$(tr -d '\0' <"$found_dt" | grep -oE "$known" | head -1)
		echo "PASS: the live device tree describes the $part actuator"
	else
		echo "FAIL: no focus actuator node in the live device tree"
		echo "      The running DTB does not describe the focus motor, so the"
		echo "      driver has nothing to bind to and logs nothing at all."
		echo "      cmd: grep -rlaE '$known' /proc/device-tree/"
		echo "      Deploy the DTB from the kernel package you actually built"
		echo "      (see 06-dtb-test, which checks exactly that)."
		exit 1
	fi
fi

# 2. Did the driver bind? A lens entity in the media graph is the evidence.
if [ ! -e /dev/media0 ]; then
	echo "FAIL: no /dev/media0 - CAMSS did not probe"
	exit 1
fi

# Match on the entity's function rather than on a driver name: a lens is a lens
# whichever part is fitted.
if media-ctl -d /dev/media0 -p 2>/dev/null | grep -qi 'Lens'; then
	echo "PASS: a lens entity is present in the media graph"
else
	echo "FAIL: the actuator is in the device tree but not in the media graph"
	echo "      (module not built, or probe failed - check dmesg for the part)"
	echo "      cmd: media-ctl -d /dev/media0 -p | grep -i lens"
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
	echo "      cmd: for s in /dev/v4l-subdev*; do v4l2-ctl -d \$s -l; done"
	fail=1
fi

exit $fail
