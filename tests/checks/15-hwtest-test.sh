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

# hwtest's audio component plays a tone through the loudspeaker at full output,
# which is loud. Borrow the speaker level helpers so this check runs at half
# volume like the rest of the suite (see lib/audio-state.sh).
. "$DEVICE_DIR/lib/audio-state.sh"

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

speaker_half
out=$(hwtest --formatter MarkdownTable --verify "$REF" 2>&1)
rc=$?
speaker_restore

if [ "$rc" -eq 0 ]; then
	echo "PASS: hwtest matches the reference"
	exit 0
fi

echo "FAIL: hwtest reports a regression against $REF"
printf '%s\n' "$out" | sed 's/^/  /'
exit 1
