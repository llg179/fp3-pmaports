#!/bin/sh
# Category: audio
# Description: the codec card exists and its PCMs can be opened
#
# The non-acoustic core of the audio coverage, and the part that runs by
# default. It proves the SLIMbus codec enumerated and that playback and capture
# devices open - which is where a kernel regression shows up first. Whether
# sound is audible is the acoustic check's job, behind --acoustic, because an
# over-the-air measurement is too environment-dependent to gate a build on.

. "$DEVICE_DIR/lib/audio-state.sh"

fail=0

# The sound server keeps the card open, so a second open returns EBUSY - and
# whether it does depends on whether the sink happens to be suspended at that
# instant, which makes the result a coin flip. Take the card first.
audio_grab

card=$(cat /proc/asound/cards 2>/dev/null)
case "$card" in
*Fairphone*)
	echo "PASS: sound card present: $(printf '%s' "$card" | sed -n 's/.*- //p' | head -1)"
	;;
*)
	echo "FAIL: no Fairphone sound card in /proc/asound/cards"
	echo "      (SLIMbus codec did not enumerate - check dmesg for wcd9335)"
	exit 1
	;;
esac

# The codec is on SLIMbus; without a logical address the bus came up but never
# addressed the device, which is a different fault from "no card at all".
if [ -d /sys/bus/slimbus/devices ] && ls /sys/bus/slimbus/devices 2>/dev/null | grep -q .; then
	echo "PASS: SLIMbus device addressed: $(ls /sys/bus/slimbus/devices | tr '\n' ' ')"
else
	echo "FAIL: no addressed SLIMbus device - the framer did not come up"
	fail=1
fi

# A real one-second open, not --dump-hw-params: that flag deliberately aborts
# the open once it has printed the parameters, so it ALWAYS exits 1 and is
# useless as a pass/fail signal. Playing /dev/zero is silence, so a real open
# costs nothing and still exercises the whole DAPM path.
if timeout 5 aplay -D hw:0,0 -d 1 -f S16_LE -r 48000 -c 2 /dev/zero >/dev/null 2>&1; then
	echo "PASS: playback PCM hw:0,0 (MultiMedia1) opens"
else
	echo "FAIL: playback PCM hw:0,0 (MultiMedia1) does not open"
	fail=1
fi

if timeout 5 arecord -D hw:0,1 -d 1 -f S16_LE -r 48000 -c 1 /dev/null >/dev/null 2>&1; then
	echo "PASS: capture PCM hw:0,1 (MultiMedia2) opens"
else
	echo "FAIL: capture PCM hw:0,1 (MultiMedia2) does not open"
	fail=1
fi

exit $fail
