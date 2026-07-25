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

# Query the runtime dir that actually reaches a live server, not the server
# process's own uid: the server can run under the greeter while the logged-in
# user talks to it through /run/user/<their uid>. Asking the greeter's empty
# session reported a false "no sink / no mic" while everything worked in the
# user's session.
. "$DEVICE_DIR/lib/audio-state.sh"
# shellcheck disable=SC2046 # want the two fields word-split into $1 $2
set -- $(_audio_client_env)
suser=$1
uid=$2

if [ -z "$suser" ]; then
	echo "FAIL: no reachable sound-server session - if the audio checks ran"
	echo "      before this one, their restore did not put it back"
	exit 1
fi
echo "PASS: sound-server session as $suser (uid $uid)"

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
