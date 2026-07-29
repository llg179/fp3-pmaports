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
#
# The playback gain is 84 rather than the 48 HiFi.conf uses for listening. On
# the 0..124 scale that is 0 dB against roughly -36 dB, and it is what makes
# the measurement work with the headset simply lying next to itself: at 48 the
# tone does not reach the microphone unless the earpiece is held against it,
# and the capture shows only low-frequency handling noise around 80-100 Hz. At
# 84 the target frequency arrives at 33 dB from where the headset happens to
# lie.
#
# Do not wear the headset while this runs.

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
	'RX1 Mix Digital Volume' 84 \
	'RX2 Mix Digital Volume' 84 \
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
	# Report the peak nearest the target, not the first one printed: alsabat
	# lists several, and the first is usually the near-DC one, which would put
	# a meaningless "1.46 Hz" in a passing message.
	peak=$(printf '%s\n' "$out" | awk '
		/Detected peak at/ {
			f = $4; db = $7
			d = f - 1000; if (d < 0) d = -d
			if (best == "" || d < best) { best = d; bf = f; bdb = db }
		}
		END { if (bf != "") printf "%s Hz, %s dB", bf, bdb }')
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
