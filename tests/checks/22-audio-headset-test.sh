#!/bin/sh
# Category: audio
# Requires: acoustic headset
# Description: a tone played on the speaker is heard by the headset mic
#
# Same acoustic method as 21, on the analogue headset input instead of the
# digital handset mic - so it exercises the ADC path rather than the DMIC one.
# Needs a headset actually plugged in, hence the extra requirement.

. "$DEVICE_DIR/lib/audio-state.sh"

fail=0
audio_grab

# Speaker out, headset mic in - the headset path from HiFi.conf.
audio_cset \
	'QUIN_MI2S_RX Audio Mixer MultiMedia1' 1 \
	'ADC MUX0' AMIC \
	'AMIC MUX0' ADC2 \
	'ADC2 Volume' 20 \
	'SLIM TX0 MUX' DEC0 \
	'AIF1_CAP Mixer SLIM TX0' 1 \
	'MultiMedia2 Mixer SLIMBUS_0_TX' 1 || fail=1

if [ "$fail" -ne 0 ]; then
	echo "FAIL: could not set the loopback routes"
	exit 1
fi

# alsabat plays a tone and FFTs what comes back; rc 0 means it found its own
# frequency in the capture.
out=$(alsabat -D "$AUDIO_CARD" -P hw:0,0 -C hw:0,1 -c 1 -r 48000 -F 1000 2>&1)
rc=$?

if [ "$rc" -eq 0 ]; then
	echo "PASS: 1 kHz tone played on the speaker was detected on the headset mic"
	exit 0
fi

echo "FAIL: acoustic loopback failed (alsabat rc=$rc)"
printf '%s\n' "$out" | tail -8 | sed 's/^/  /'
echo "      Before believing this, check the obvious: is the volume up, is the"
echo "      phone face-down on a soft surface, is the room quiet?"
exit 1
