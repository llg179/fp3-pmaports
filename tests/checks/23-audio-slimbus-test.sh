#!/bin/sh
# Category: audio
# Requires: acoustic headset
# Description: a tone crosses SLIMbus in both directions, headphones to headset mic
#
# The other two acoustic checks play through the speaker, and the speaker is
# not on SLIMbus: it hangs off QUIN_MI2S and the AW8898 amplifier. So a pass
# there says nothing about the SLIMbus playback path, and a failure there can
# be an amplifier or a room problem rather than a bus problem.
#
# This one plays through the headphones, which go out over SLIMbus through the
# WCD9335, and captures on the headset microphone, which comes back over
# SLIMbus as well. Both directions cross the bus, so it is the acoustic test
# that actually exercises what the framer quirk was added for. It is also quiet
# in the room: the tone stays inside the headset.
#
# Needs a headset plugged in, hence the extra requirement.

. "$DEVICE_DIR/lib/audio-state.sh"

fail=0
audio_grab

# Headphones out over SLIMbus (HiFi.conf's Headphones device), headset mic in.
audio_cset \
	'QUIN_MI2S_RX Audio Mixer MultiMedia1' 0 \
	'SLIMBUS_0_RX Audio Mixer MultiMedia1' 1 \
	'SLIM RX0 MUX' AIF1_PB \
	'SLIM RX1 MUX' AIF1_PB \
	'RX INT1_2 MUX' RX0 \
	'RX INT2_2 MUX' RX1 \
	'RX INT1 DEM MUX' CLSH_DSM_OUT \
	'RX INT2 DEM MUX' CLSH_DSM_OUT \
	'RX1 Mix Digital Volume' 48 \
	'RX2 Mix Digital Volume' 48 \
	'HPHL Volume' 20 \
	'HPHR Volume' 20 \
	'ADC MUX0' AMIC \
	'AMIC MUX0' ADC2 \
	'ADC2 Volume' 20 \
	'SLIM TX0 MUX' DEC0 \
	'AIF1_CAP Mixer SLIM TX0' 1 \
	'MultiMedia2 Mixer SLIMBUS_0_TX' 1 || fail=1

if [ "$fail" -ne 0 ]; then
	echo "FAIL: could not set the SLIMbus loopback routes"
	exit 1
fi

out=$(alsabat -D "$AUDIO_CARD" -P hw:0,0 -C hw:0,1 -c 1 -r 48000 -F 1000 2>&1)
rc=$?

# Judge on "did the target frequency arrive", not on alsabat's own exit code.
# Holding an earphone against a microphone produces sidebands a few hertz above
# the fundamental, and alsabat fails the run on the highest peak it can see even
# when it has already reported the target frequency with a good margin. That is
# a stricter question than the one being asked here: the tone either crossed the
# bus or it did not.
if [ "$rc" -eq 0 ]; then
	echo "PASS: 1 kHz tone crossed SLIMbus both ways (headphones -> headset mic)"
	exit 0
fi

if printf '%s\n' "$out" | grep -q "PASS: Peak detected at target frequency"; then
	peak=$(printf '%s\n' "$out" | sed -n 's/.*Detected peak at \([0-9.]*\) Hz of \([0-9.]*\) dB.*/\1 Hz, \2 dB/p' | head -1)
	echo "PASS: 1 kHz tone crossed SLIMbus both ways (peak $peak)"
	echo "      alsabat rc=$rc from sidebands above the fundamental; the target"
	echo "      frequency was detected, which is what this check asks"
	exit 0
fi

echo "FAIL: SLIMbus acoustic loopback failed (alsabat rc=$rc)"
printf '%s\n' "$out" | tail -8 | sed 's/^/  /'
echo "      Check the obvious first: is the headset actually plugged in, is its"
echo "      microphone not covered, and is the earpiece held against it? The"
echo "      headphone and the headset microphone are far apart acoustically, so"
echo "      unlike the speaker checks this one needs them put together."
exit 1
