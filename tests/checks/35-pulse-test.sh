#!/bin/sh
# Category: audio
# Description: the sound server exposes a real sink and the handset mic
#
# The raw ALSA checks prove the kernel side. This one proves userspace got
# there too: PulseAudio falling back to auto_null is the classic symptom of a
# card the server could not open, and it is invisible from the kernel side
# because every ALSA device still works perfectly.
#
# It runs after the audio block on purpose - it doubles as the proof that
# audio-state.sh really did put the sound server back.

fail=0

# Derive the session user; this has moved between a system greeter account and
# the ordinary user, so hardcoding a uid ages badly.
# busybox ps has no -C, so go via pgrep and /proc rather than a ps flag that
# silently produces nothing here.
suser=""
for p in pipewire pulseaudio; do
	pid=$(pgrep -x "$p" 2>/dev/null | head -1)
	if [ -n "$pid" ]; then
		suser=$(getent passwd "$(awk '/^Uid:/ {print $2}' "/proc/$pid/status")" | cut -d: -f1)
		break
	fi
done

if [ -z "$suser" ]; then
	echo "FAIL: no sound server running - if the audio checks ran before this"
	echo "      one, their restore did not put it back"
	exit 1
fi
uid=$(id -u "$suser" 2>/dev/null)
echo "PASS: sound server running as $suser (uid $uid)"

pa() {
	su "$suser" -c "XDG_RUNTIME_DIR=/run/user/$uid pactl $*" 2>/dev/null
}

sinks=$(pa list short sinks)
if printf '%s\n' "$sinks" | grep -qv 'auto_null' && printf '%s\n' "$sinks" | grep -q .; then
	echo "PASS: real sink present: $(printf '%s\n' "$sinks" | awk '{print $2}' | tr '\n' ' ')"
else
	echo "FAIL: only auto_null (or no sink) - the server could not open the card"
	fail=1
fi

sources=$(pa list short sources)
if printf '%s\n' "$sources" | grep -q 'fp3-handset-mic'; then
	echo "PASS: fp3-handset-mic source present"
else
	echo "FAIL: no fp3-handset-mic source - the mic drop-in did not load"
	echo "      available: $(printf '%s\n' "$sources" | awk '{print $2}' | tr '\n' ' ')"
	fail=1
fi

exit $fail
