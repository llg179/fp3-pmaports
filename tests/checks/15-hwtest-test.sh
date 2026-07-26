#!/bin/sh
# Category: camera
# Description: hwtest reports no hardware regression against the reference
#
# hwtest (MartijnBraam) already does the tedious half of a hardware pass -
# framebuffer, DRM, camera presence, vibrator and every input device - and it
# has real regression semantics: --export once, --verify after each bump, exit 1
# when something that used to work no longer does. Reusing it beats
# reimplementing it, so this check only wires it up.
#
# Measured behaviour that shaped the code below:
#   - it needs root; as a normal user it dies on /dev/input/event5 with an
#     unhandled PermissionError
#   - the reference cannot live in /tmp: fs.protected_regular stops root from
#     writing over a file another user created in a sticky directory
#   - --verify returns 1 on a regression and 0 when clean
#
# Three components are deliberately skipped here, each covered better elsewhere
# or actively harmful to run in an automated pass:
#   - Camera: hwtest grabs a frame with ffmpeg, which trips the intermittent
#     msm8953 csi0phytimer clock-enable race (gcc_camss_csi0phytimer_clk stuck
#     at 'off', -EBUSY) on a cold/rapid open. The sensor itself works (libcamera
#     captures fine); 40-camera-test.sh validates the DT node, media graph and
#     the enabled link into CAMSS without the flaky frame-grab. See the camera
#     bring-up notes for the clock-lock analysis.
#   - Vibrator: hwtest drives it at full magnitude in a 1s-on/1s-off pattern,
#     which is loud enough to be a nuisance during an unattended run.
#   - Audio: covered end-to-end by 10-audio-loopback, 11-mic-headset,
#     20-voice-pcm and 30-pulse.
# Everything hwtest uniquely covers - framebuffer, DRM, the sensors, inputs,
# LEDs, temperature, pressure - is still verified.
HWTEST_SKIP="--skip Camera --skip Vibrator --skip Audio"

# The reference travels with the suite rather than living only on the device:
# it is a baseline like every other file in baseline/, so it should be
# versioned, reviewable in a diff, and not lost to a reinstall.
REF="$DEVICE_DIR/baseline/hwtest-reference.ini"

if ! command -v hwtest >/dev/null 2>&1; then
	echo "FAIL: hwtest is not installed (apk add hwtest)"
	exit 1
fi

if [ ! -f "$REF" ]; then
	echo "FAIL: no hwtest reference at $REF"
	echo "      Create one from a state you consider good:"
	echo "        hwtest --export tests/baseline/hwtest-reference.ini"
	echo "      and edit it so components that SHOULD work read True, even if"
	echo "      they are broken today - otherwise the breakage becomes the"
	echo "      baseline and stops being reported."
	exit 1
fi

out=$(hwtest --formatter MarkdownTable $HWTEST_SKIP --verify "$REF" 2>&1)
rc=$?

if [ "$rc" -eq 0 ]; then
	echo "PASS: hwtest matches the reference"
	exit 0
fi

echo "FAIL: hwtest reports a regression against $REF"
printf '%s\n' "$out" | sed 's/^/  /'
exit 1
