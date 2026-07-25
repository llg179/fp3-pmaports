#!/bin/sh
# Description: the modules this port needs are built, installed and unmodified
#
# Three separate questions, deliberately not merged:
#   1. is every must-have module present?          (catches a silent config drop)
#   2. does the on-disk module tree match the apk? (catches a hand-swapped .ko)
#   3. are there leftover .orig/.bak files?        (catches an unfinished swap)
# Only (1) uses a hand-maintained list; (2) and (3) derive everything from the
# system, so they do not rot as the kernel gains and loses modules.

fail=0
moddir="/lib/modules/$(uname -r)"

# 1. must-have modules
missing=""
while read -r mod; do
	case "$mod" in '' | \#*) continue ;; esac
	find "$moddir" -name "$mod.ko*" 2>/dev/null | grep -q . || missing="$missing $mod"
done <"$DEVICE_DIR/baseline/modules-required.txt"
if [ -n "$missing" ]; then
	for m in $missing; do
		echo "FAIL: required module not built or not installed: $m"
	done
	fail=1
else
	echo "PASS: every required module is present"
fi

# 2. hand-modified package files under the module tree.
#    apk audit reports files that differ from what the package installed, which
#    is exactly what a hot-swapped .ko looks like. A swapped module is fine as a
#    deliberate experiment and fatal as an unnoticed leftover - either way the
#    run is not reproducible from the package, so say so.
modified=$(apk audit --system 2>/dev/null | awk '/lib\/modules\/.*\.ko/ {print $2}')
if [ -n "$modified" ]; then
	for m in $modified; do
		echo "FAIL: module differs from the installed package: /$m"
	done
	echo "FAIL: the running kernel is not reproducible from its package"
	fail=1
else
	echo "PASS: module tree matches the installed package"
fi

# 3. leftovers from a hot-swap
strays=$(find "$moddir" \( -name '*.orig' -o -name '*.bak' \) 2>/dev/null)
if [ -n "$strays" ]; then
	for s in $strays; do
		echo "FAIL: leftover from a module hot-swap: $s"
	done
	fail=1
else
	echo "PASS: no .orig/.bak leftovers in the module tree"
fi

exit $fail
