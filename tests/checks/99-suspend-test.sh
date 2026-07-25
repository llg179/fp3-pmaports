#!/bin/sh
# Detached: yes
# Description: the system suspends and wakes on an RTC alarm
#
# Runs last, and runs detached, because resuming re-enumerates USB and drops
# the CDC-NCM link every time. Driving this over a live SSH session would kill
# the measurement at the moment it matters, so the check writes its verdict to
# the rootfs and the runner reconnects afterwards to read it.
#
# Based on postmarketos-test's 90-suspend-test.sh, kept close to it on purpose:
# if this ever moves into a device-pmtest subpackage it should look familiar.

SLEEP_TIME=6

if [ ! -e /sys/class/rtc/rtc0/wakealarm ]; then
	echo "FAIL: no RTC wakealarm - nothing can wake the device from suspend"
	exit 1
fi

before=$(cat /sys/class/rtc/rtc0/since_epoch)
target=$((before + SLEEP_TIME))

# Clear any stale alarm first: a leftover one in the past makes the write
# succeed and the wake never happen.
echo 0 >/sys/class/rtc/rtc0/wakealarm
echo "$target" >/sys/class/rtc/rtc0/wakealarm

sync
echo mem >/sys/power/state

after=$(cat /sys/class/rtc/rtc0/since_epoch)
if [ "$after" -lt "$target" ]; then
	echo "FAIL: the system never suspended (woke at $after, alarm was $target)"
	exit 1
fi
echo "PASS: suspended and resumed on the RTC alarm after ${SLEEP_TIME}s"

# The other failure mode is not coming back at all, which shows up as the
# runner failing to reconnect rather than as a line here.
exit 0
