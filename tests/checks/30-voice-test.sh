#!/bin/sh
# Category: voice
# Description: the VoiceMMode1 call path can be routed and opened
#
# This is the check the whole suite was built around. A missing DAPM route
# ("SLIMBUS_0_RX" <- "SLIMBUS_0_RX Voice Mixer") made the voice PCM impossible
# to open, and nothing else in a functional pass would have noticed: playback
# and capture both still worked, only telephony was dead.
#
# Note that hw:0,4 legitimately fails to open with EINVAL until the voice
# routes are set - the ADSP needs a backend DAI enabled before it will
# instantiate the topology. So the check routes first and opens second; testing
# the open on its own would report a failure that means nothing.

. "$DEVICE_DIR/lib/audio-state.sh"

fail=0
audio_grab

# Where in the log we start caring, so two checks cannot eat each other's
# evidence the way `dmesg -c` would.
watermark=$(dmesg 2>/dev/null | wc -l)

# Earpiece downlink + handset mic uplink, straight from VoiceCall.conf.
audio_cset \
	'SLIMBUS_0_RX Voice Mixer VoiceMMode1' 1 \
	'SLIM RX0 MUX' AIF1_PB \
	'RX INT0_2 MUX' RX0 \
	'RX INT0 DEM MUX' CLSH_DSM_OUT \
	'RX0 Mix Digital Volume' 68 \
	'VoiceMMode1 Capture Mixer SLIMBUS_0_TX' 1 \
	'AIF1_CAP Mixer SLIM TX0' 1 \
	'SLIM TX0 MUX' DEC0 \
	'ADC MUX0' DMIC \
	'DMIC MUX0' DMIC0 || fail=1

# A real open (see 20-audio): --dump-hw-params always exits 1 by design.
if timeout 5 aplay -D hw:0,4 -d 1 -f S16_LE -r 48000 -c 1 /dev/zero >/dev/null 2>&1; then
	echo "PASS: voice downlink PCM hw:0,4 opens"
else
	echo "FAIL: voice downlink PCM hw:0,4 does not open with the voice routes set"
	fail=1
fi

if timeout 5 arecord -D hw:0,4 -d 1 -f S16_LE -r 48000 -c 1 /dev/null >/dev/null 2>&1; then
	echo "PASS: voice uplink PCM hw:0,4 opens"
else
	echo "FAIL: voice uplink PCM hw:0,4 does not open with the voice routes set"
	fail=1
fi

# The driver names the fault precisely, so look for its own words rather than
# inferring from the open failure alone.
slice=$(dmesg 2>/dev/null | tail -n "+$watermark")
for sig in 'no valid Playback path' 'no backend DAIs enabled for VoiceMMode1'; do
	if printf '%s\n' "$slice" | grep -qF "$sig"; then
		echo "FAIL: kernel reported: $sig"
		fail=1
	fi
done
[ "$fail" -eq 0 ] && echo "PASS: no voice routing faults in the kernel log"

exit $fail
