#!/bin/sh
# ColdPhase: unlock
# Description: how long the cold unlock takes, and whether it matches the warm one
#
# Judges a trace recorded by lib/unlock-probe.py at the previous boot. It is a
# two-step check on purpose - arm, reboot, unlock, judge - because the
# measurement cannot be driven live: an SSH login starts the very systemd --user
# session whose cold start is being timed.
#
# What the number means, measured 2026-07-25. A cold unlock here is not a
# lockscreen being dismissed: phosh is not running at all. The device sits at
# the greetd/phrog greeter as uid 113, and authenticating starts an entire user
# session from scratch. Of the ~15s a human perceives, roughly 7s is
# authentication and session setup before phosh even exists, and ~8s is phosh
# starting up to idle. This check measures phosh's part, which is the part that
# a change to the port can move.
#
# The goal is to make the cold unlock behave like a warm one - the expensive
# work should happen before login rather than after it. That turns out to have a
# very clean test: if the session really is pre-warmed, phosh is ALREADY RUNNING
# when you unlock, so it is never born during the trace at all. So "phosh never
# started" is not an error here, it is the win condition. Until then, the number
# to drive down is how long phosh takes from birth to idle.

TRACE=${TRACE:-/var/log/fp3-selftest/cold-unlock.tsv}
BASELINE="$DEVICE_DIR/baseline/unlock.txt"

if [ ! -s "$TRACE" ]; then
	echo "FAIL: no cold-unlock trace at $TRACE"
	echo "      Record one:  fp3-selftest --arm-unlock, reboot, unlock, then rerun"
	exit 1
fi

# The probe writes "# phosh appeared at t=..., pid ..." when the shell is born.
birth=$(sed -n 's/^# phosh appeared at t=\([0-9.]*\).*/\1/p' "$TRACE" | head -1)

# phosh already running when the probe started = the session was pre-warmed
# before login. That is exactly the state this check exists to reach.
first_cpu=$(awk '!/^#/ { print $2; exit }' "$TRACE")
if [ -z "$birth" ] && [ "${first_cpu:--1}" -ge 0 ]; then
	echo "PASS: phosh was already running before the unlock - the session is"
	echo "      pre-warmed, so the cold path no longer pays for starting it"
	exit 0
fi

if [ -z "$birth" ]; then
	echo "FAIL: the trace saw neither a running phosh nor phosh starting."
	echo "      Was the phone actually unlocked while the probe was running?"
	exit 1
fi

# Quiet = the CPU delta stays at or below QUIET_DELTA for QUIET_RUN consecutive
# samples. During startup the deltas run to tens or hundreds of jiffies; at idle
# they are exactly 1, so the threshold is not delicate.
settle=$(awk -v birth="$birth" '
	/^#/ { next }
	{
		t = $1; cpu = $2
		if (cpu < 0) next
		if (prev != "") {
			d = cpu - prev
			if (d <= 2) { run++; if (run == 1) run_start = t }
			else        { run = 0 }
			if (run >= 20 && !done) { print run_start; done = 1; exit }
		}
		prev = cpu
	}
' "$TRACE")

if [ -z "$settle" ]; then
	echo "FAIL: phosh never went quiet within the trace - the session did not"
	echo "      finish starting up inside the recording window"
	exit 1
fi

cold=$(awk -v a="$birth" -v b="$settle" 'BEGIN { printf "%.1f", b - a }')
echo "PASS: cold unlock measured: phosh took ${cold}s from start to idle"

if [ ! -s "$BASELINE" ]; then
	echo "FAIL: no baseline at baseline/unlock.txt (today's measurement: ${cold}s)"
	exit 1
fi

COLD_MAX=$(sed -n 's/^COLD_MAX=//p' "$BASELINE" | head -1)

fail=0
if awk -v c="$cold" -v m="${COLD_MAX:-0}" 'BEGIN { exit !(c > m) }'; then
	echo "FAIL: cold unlock ${cold}s is over the ${COLD_MAX}s budget"
	fail=1
else
	echo "PASS: cold unlock ${cold}s is within the ${COLD_MAX}s budget"
fi

exit $fail
