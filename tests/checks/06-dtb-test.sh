#!/bin/sh
# Description: the booted device tree is the one the kernel package shipped
#
# The module tree already has this guard (05-modules, "module tree matches the
# installed package"). The device tree had none, and it is the easier of the two
# to get wrong, because a DTB is cheap to build from any checkout: the host
# `make qcom/<board>.dtb` takes seconds and writes a file that looks exactly as
# legitimate as the packaged one.
#
# It cost a session on 2026-08-01. A DTB built in a worktree parked on
# wip/<base>/camera was copied to /boot; that branch carries the base plus the
# camera commits and nothing else, so the deployed tree silently lost the audio,
# voice, charger, sensor and debug layers. The visible symptom was the battery
# reading 0% - not because the battery was flat (it was at 91% and charging) but
# because charger@1000 was absent, so no pmi632-battery power supply was ever
# created and there was nobody to ask. The deployed file had been md5-verified,
# but against the worktree it came from rather than against the package, so the
# check passed and proved nothing.
#
# Both directions of the same mistake are now covered:
#   this check          -> a hand-deployed DTB replaced the package's
#   40-camera, step 1   -> the package's DTB replaced a hand-deployed one
#                          (an apk operation fires the mkinitfs trigger)
#
# Two questions, deliberately separate. The md5 is the invariant; the marker
# nodes say *which* layer went missing, which is what turns "wrong DTB" into a
# one-line diagnosis instead of a decompile.

fail=0

# Which DTB does the bootloader actually load? Read it from extlinux rather
# than assuming the filename, so a renamed fdt cannot make this check inspect a
# file that nothing boots.
fdt=$(sed -n '/^label postmarketOS$/,/^$/p' /boot/extlinux/extlinux.conf 2>/dev/null |
	sed -n 's/^[[:space:]]*fdt[[:space:]]*//p' | head -1)
if [ -z "$fdt" ]; then
	echo "FAIL: no fdt line in the postmarketOS label of /boot/extlinux/extlinux.conf"
	echo "      cmd: sed -n '/^label postmarketOS\$/,/^\$/p' /boot/extlinux/extlinux.conf"
	exit 1
fi
booted="/boot${fdt}"
board=$(basename "$fdt")

if [ ! -r "$booted" ]; then
	echo "FAIL: extlinux boots $fdt but /boot$fdt does not exist"
	exit 1
fi

# 1. Does it match what the installed kernel package shipped?
#
# The package path is taken from the package itself, never hardcoded: apk is
# the only authority on which file it installed, and it is also the thing that
# names the version in the failure message.
pkg=$(apk info -L "${KERNEL_PKG:-linux-fp3}" 2>/dev/null | grep "/${board}\$" | head -1)
if [ -z "$pkg" ]; then
	echo "FAIL: ${KERNEL_PKG:-linux-fp3} installs no $board - cannot tell what the DTB should be"
	echo "      cmd: apk info -L ${KERNEL_PKG:-linux-fp3} | grep /$board\$"
	fail=1
else
	pkg="/$pkg"
	booted_sum=$(md5sum "$booted" | cut -d' ' -f1)
	pkg_sum=$(md5sum "$pkg" | cut -d' ' -f1)
	owner=$(apk info -W "$pkg" 2>/dev/null | sed 's/.*owned by //')
	if [ "$booted_sum" = "$pkg_sum" ]; then
		echo "PASS: booted DTB matches the installed package ($owner)"
	else
		echo "FAIL: the booted DTB is not the one $owner shipped"
		echo "      booted $booted  $booted_sum  ($(stat -c %s "$booted") bytes)"
		echo "      package $pkg  $pkg_sum  ($(stat -c %s "$pkg") bytes)"
		echo "      cmd: md5sum $booted $pkg"
		echo "      A DTB built by hand carries only the layers of the branch it"
		echo "      was built from. Deploy it from the package, or say out loud"
		echo "      which branch and which artifact this one came from and why."
		fail=1
	fi
fi

# 2. Which layers does the live tree actually describe?
#
# The md5 above is the real invariant; this is the readable half of it. A
# mismatch tells you the file is wrong, these tell you what stopped working -
# and they still catch the case where a DTB was flashed inside a boot.img and
# never touched /boot at all.
#
# Only layers that own a node are listed. Nothing is asserted for sensor
# (SMGR is a QMI/QRTR client of the ADSP, with no node of its own) or for debug
# (the watchdog-at-probe is a driver change), so this list stays honest rather
# than complete.
DT=/proc/device-tree
check_marker() { # layer, human-readable what, test-expression already run
	if [ "$3" = 0 ]; then
		echo "PASS: the live tree describes the $1 layer ($2)"
	else
		echo "FAIL: the live tree has no $2 - the $1 layer is missing from this DTB"
		return 1
	fi
}

[ -d "$DT/soc@0/spmi@200f000/pmic@2/charger@1000" ]
check_marker charger "charger@1000 under the PMI632" $? || fail=1

grep -qa 'simple-battery' "$DT/battery/compatible" 2>/dev/null
check_marker charger "battery node" $? || fail=1

[ -d "$DT/soc@0/slim-ngd@c140000/slim@1/codec@1,0" ]
check_marker audio "WCD9335 codec on the SLIMbus NGD" $? || fail=1

# The sensor node is named camera@<addr>; "imx363" is only in the *value* of
# its compatible property, so grep the contents (same reason as 40-camera).
grep -rlaq 'imx363' "$DT/" 2>/dev/null
check_marker camera "imx363 sensor node" $? || fail=1

exit $fail
