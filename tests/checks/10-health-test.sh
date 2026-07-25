#!/bin/sh
# Description: the system booted cleanly and has room to work
#
# Deliberately narrow patterns. A broad grep (say, for "subsys") matches on a
# perfectly normal boot, and a check that cries wolf gets ignored - which is
# worse than not having it. Anything known-noisy goes in baseline/dmesg-allow.txt
# with a reason, so the allowlist stays reviewable.

fail=0

# Strip comments before use: grep -f would otherwise treat every comment line in
# the baseline as a pattern of its own.
allow=$(mktemp)
grep -v '^[[:space:]]*\(#\|$\)' "$DEVICE_DIR/baseline/dmesg-allow.txt" >"$allow" 2>/dev/null || true
units=$(mktemp)
grep -v '^[[:space:]]*\(#\|$\)' "$DEVICE_DIR/baseline/failed-units.txt" >"$units" 2>/dev/null || true
trap 'rm -f "$allow" "$units"' EXIT

hits=$(dmesg 2>/dev/null |
	grep -E 'Kernel panic|Oops|BUG:|rcu_sched self-detected|remoteproc.*(crash|fatal)' |
	{ [ -s "$allow" ] && grep -vFf "$allow" || cat; })
if [ -n "$hits" ]; then
	echo "FAIL: kernel log contains fault signatures:"
	printf '%s\n' "$hits" | sed 's/^/  /'
	fail=1
else
	echo "PASS: no panic/oops/BUG/remoteproc-crash in the kernel log"
fi

# Disk full has bitten this device twice: it aborts an apk upgrade halfway and
# leaves a version-skewed stack that then crashes somewhere unrelated.
used=$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ "${used:-100}" -ge 98 ]; then
	echo "FAIL: rootfs ${used}% full - an upgrade here would break mid-way"
	fail=1
else
	echo "PASS: rootfs ${used}% used"
fi

# The device runs degraded today; the point is that it does not get *more*
# degraded, so compare against the recorded set rather than against zero.
failed=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | sort)
newly=$(printf '%s\n' "$failed" | { [ -s "$units" ] && grep -vxFf "$units" || cat; } | grep . || true)
if [ -n "$newly" ]; then
	echo "FAIL: systemd units failed that are not in the baseline:"
	printf '%s\n' "$newly" | sed 's/^/  /'
	fail=1
else
	echo "PASS: no systemd unit failed outside the recorded baseline"
fi

exit $fail
