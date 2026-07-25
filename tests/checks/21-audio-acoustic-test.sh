#!/bin/sh
# Category: audio
# Requires: acoustic
# Description: a tone played on the speaker is heard by the handset mic
#
# Opt-in, and deliberately not part of the default gate. The medium is the air
# in the room, so the result depends on the volume, on whether the phone is
# lying face-down, and on whether anyone is talking nearby - and it makes an
# audible noise every run. A gate that goes red for those reasons stops being
# believed within a fortnight, which is worse than not having it.
#
# When it does run it is the strongest audio evidence there is: a pass proves
# the entire chain, codec to speaker to microphone to codec, end to end.

. "$DEVICE_DIR/lib/audio-state.sh"

fail=0
audio_grab

# Speaker out, handset mic in - the same routes HiFi.conf uses.
audio_cset \
	'QUIN_MI2S_RX Audio Mixer MultiMedia1' 1 \
	'ADC MUX0' DMIC \
	'DMIC MUX0' DMIC0 \
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
	echo "PASS: 1 kHz tone played on the speaker was detected on the handset mic"
	exit 0
fi

echo "FAIL: acoustic loopback failed (alsabat rc=$rc)"
printf '%s\n' "$out" | tail -8 | sed 's/^/  /'
echo "      Before believing this, check the obvious: is the volume up, is the"
echo "      phone face-down on a soft surface, is the room quiet?"
exit 1
