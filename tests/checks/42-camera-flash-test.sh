#!/bin/sh
# Category: camera
# Description: the PMI632 flash LED probes, and the torch really draws current
#
# Whether the LED emits light is the one thing this cannot see, so it is not
# what is measured here. Two things that can be measured stand in for it: the
# PMIC's own channel-enable and target-current registers have to show the
# hardware actually programmed, and the input current has to rise when the
# torch is switched on. A driver that returned success without touching the
# part would pass neither.
#
# ☠️ The battery is the wrong ammeter, twice over. pmi632-battery exposes no
# current_now at all - the charger driver does not implement the property - and
# with a cable attached the torch is fed from USB, so battery voltage does not
# droop even when the LED is at full current. Reading battery voltage said "no
# current flows" about a flash that was visibly lit. Use the PMIC's USB input
# current ADC, and interleave the states, because a single on/off pair is
# swamped by the noise on that channel.
#
# For an optical confirmation, which needs a scene and so cannot live in an
# unattended battery, see userspace-camera/flash-check.py: it holds one capture
# open and switches the torch underneath it.

fail=0
leds=/sys/class/leds
regs=/sys/kernel/debug/regmap/0-03/registers	# PMI632, second SPMI USID
usb_i=/sys/bus/iio/devices/iio:device1/in_voltage_usb_in_i_uv_input
usb_online=/sys/class/power_supply/pmi632-charger/online

# Register offsets inside the flash module at 0xd300, as decimal line numbers
# for the fixed 9-bytes-per-line debugfs format.
r_itarget0=54083	# 0xd343
r_itarget1=54084	# 0xd344
r_module_en=54086	# 0xd346
r_chan_en=54092		# 0xd34c

reg() {
	dd if="$regs" bs=9 skip="$1" count=1 2>/dev/null | cut -d' ' -f2
}

led=""
for l in "$leds"/*:flash; do
	[ -e "$l" ] && led=$l && break
done

if [ -z "$led" ]; then
	echo "FAIL: no flash LED classdev under $leds"
	echo "      cmd: dmesg | grep -i 'flash LED'"
	echo "      'subtype 0x5 is not yet supported' means the driver lacks the"
	echo "      PMI632 variant; nothing at all means CONFIG_LEDS_QCOM_FLASH is"
	echo "      not built or the pmi632 led-controller@d300 node is disabled."
	exit 1
fi
echo "PASS: flash LED classdev is $(basename "$led")"

max=$(cat "$led/max_brightness" 2>/dev/null || echo 0)
if [ "$max" -gt 0 ]; then
	echo "PASS: max_brightness $max"
else
	echo "FAIL: max_brightness reads '$max'"
	fail=1
fi

# The module must be off before we start, or the deltas below measure nothing.
echo 0 > "$led/brightness" 2>/dev/null
sleep 1
base_chan=$(reg $r_chan_en)

echo "$max" > "$led/brightness" 2>/dev/null
sleep 1
on_module=$(reg $r_module_en)
on_chan=$(reg $r_chan_en)
on_it0=$(reg $r_itarget0)
on_it1=$(reg $r_itarget1)

echo 0 > "$led/brightness" 2>/dev/null
sleep 1
off_chan=$(reg $r_chan_en)

# Both ganged channels have to come on: led-sources = <1>, <2> means chan_id 0
# and 1, so CHAN_EN bits 0 and 1. Anything less and the current is split wrong.
case "$on_chan" in
03) echo "PASS: CHAN_EN 0x$on_chan - both ganged channels enabled" ;;
*)  echo "FAIL: CHAN_EN 0x$on_chan with the torch on, expected 0x03"
    echo "      cmd: dd if=$regs bs=9 skip=$r_chan_en count=1"
    fail=1 ;;
esac

# MODULE_EN is bit 7 of 0xd346.
if [ "$((0x${on_module:-0} & 0x80))" -ne 0 ]; then
	echo "PASS: MODULE_EN set (0x$on_module)"
else
	echo "FAIL: MODULE_EN clear (0x$on_module) while the torch is on"
	fail=1
fi

# Non-zero target current on both channels. The value is the current in units
# of the torch resolution, so its exact size depends on led-max-microamp; that
# it is programmed at all is the claim here.
if [ "$((0x${on_it0:-0}))" -gt 0 ] && [ "$((0x${on_it1:-0}))" -gt 0 ]; then
	echo "PASS: ITARGET programmed on both channels (0x$on_it0, 0x$on_it1)"
else
	echo "FAIL: ITARGET 0x$on_it0 / 0x$on_it1 - a channel was left at zero"
	fail=1
fi

if [ "$off_chan" = "$base_chan" ]; then
	echo "PASS: CHAN_EN back to 0x$off_chan after switching off"
else
	echo "FAIL: CHAN_EN stuck at 0x$off_chan (was 0x$base_chan before)"
	fail=1
fi

# The electrical half. It needs the USB input, which is the only ammeter this
# phone has; on battery alone there is nothing to read, so say so rather than
# inventing a verdict.
if [ ! -r "$usb_i" ] || [ "$(cat $usb_online 2>/dev/null)" != "1" ]; then
	echo "SKIP: no USB input current to read - attach a cable for the"
	echo "      electrical half (pmi632-battery exposes no current_now)"
	exit $fail
fi

# Mean of several samples per state, and the states interleaved, because a
# single pair is inside the noise on this channel.
mean_usb_i() {
	_s=0
	for _i in 1 2 3 4 5 6; do
		_s=$((_s + $(cat "$usb_i")))
		sleep 1
	done
	echo $((_s / 6))
}

off_lo=""; off_hi=""; on_lo=""; on_hi=""
for _p in 1 2 3; do
	echo 0 > "$led/brightness"; sleep 2
	_off=$(mean_usb_i)
	echo "$max" > "$led/brightness"; sleep 2
	_on=$(mean_usb_i)
	echo "  pass $_p: off $_off, on $_on"
	[ -z "$off_hi" ] || [ "$_off" -gt "$off_hi" ] && off_hi=$_off
	[ -z "$on_lo" ] || [ "$_on" -lt "$on_lo" ] && on_lo=$_on
done
echo 0 > "$led/brightness"

# Separation, not a ratio: if the highest idle reading is still below the
# lowest lit one, no amount of drift explains it away.
if [ "$on_lo" -gt "$off_hi" ]; then
	echo "PASS: every torch-on mean above every torch-off one ($on_lo > $off_hi)"
else
	echo "FAIL: input current does not separate (on min $on_lo, off max $off_hi)"
	echo "      cmd: cat $usb_i"
	echo "      The registers above may still be programmed - that would mean"
	echo "      the module is enabled but no current reaches the LED."
	fail=1
fi

exit $fail
