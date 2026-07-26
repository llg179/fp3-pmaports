#!/bin/sh
# Device-side helper: take exclusive control of the sound card, then give it
# back exactly as it was.
#
# Two problems it solves. First, the sound server holds the card, so a raw ALSA
# open fails with EBUSY. Second, a check that sets mixer controls and then dies
# halfway leaves the device muted or misrouted - so the restore runs from a trap
# and not from the happy path.
#
# Usage:
#   . "$DEVICE_DIR/lib/audio-state.sh"
#   audio_grab            # save state, stop the sound server
#   ... raw ALSA work ...
#   audio_release         # (also runs automatically on exit)

AUDIO_STATE_FILE=""
AUDIO_SERVER_USER=""
AUDIO_HELD=0

# Note: busybox ps has no -C, so match by pid. Using `ps -C` here silently
# returned nothing, which made this helper report "no sound server" and skip the
# stop entirely - the card then stayed busy and every raw ALSA open failed for a
# reason that looked like a kernel fault.
_audio_server_user() {
	# The server process itself: this is who owns and holds the card, so this is
	# who we ask systemd to stop in order to grab it. It runs under a system
	# greeter account or the ordinary user depending on session state - derive it
	# rather than hardcode it. (For *querying* pactl the working runtime dir may
	# belong to a different uid than the server process - see _audio_client_env.)
	for p in pipewire wireplumber pulseaudio; do
		_pid=$(pgrep -x "$p" 2>/dev/null | head -1)
		if [ -n "$_pid" ]; then
			awk '/^Uid:/ {print $2}' "/proc/$_pid/status" 2>/dev/null |
				while read -r _u; do getent passwd "$_u" | cut -d: -f1; done
			return
		fi
	done
}

# Print "<user> <uid>" for the runtime dir that actually talks to a live sound
# server. The server can run under the greeter (a low uid) while the logged-in
# user connects to it through /run/user/<their-uid>; querying the server
# process's own runtime dir then sees an empty session and reports a false "no
# sink / no mic". Probe every /run/user/* for one whose pactl exposes a real
# (non-auto_null) sink; callers use this for read-only pactl queries.
_audio_client_env() {
	# Don't pre-filter on a socket path: the working session's runtime dir does
	# not always contain a literal pulse/native file (pactl still reaches the
	# server), so a socket check wrongly skipped the logged-in user. Just try
	# pactl for every numeric-uid runtime dir and take the first that shows a
	# real sink. The glob sorts "10000" before "113", so the user wins over the
	# greeter when both reach a server.
	_fallback=""
	for _rt in /run/user/*; do
		[ -d "$_rt" ] || continue
		_u=${_rt##*/}
		case "$_u" in ''|*[!0-9]*) continue ;; esac
		_name=$(getent passwd "$_u" | cut -d: -f1)
		[ -n "$_name" ] || continue
		_sinks=$(su "$_name" -c "XDG_RUNTIME_DIR=$_rt pactl list short sinks" \
			2>/dev/null)
		printf '%s\n' "$_sinks" | grep -q . || continue
		[ -z "$_fallback" ] && _fallback="$_name $_u"
		if printf '%s\n' "$_sinks" | grep -v auto_null | grep -q .; then
			echo "$_name $_u"
			return
		fi
	done
	[ -n "$_fallback" ] && echo "$_fallback"
}

# Only the units that actually exist here: this session has pipewire.service,
# pipewire.socket and wireplumber.service. There is no pulseaudio unit - the
# process calling itself pulseaudio is pipewire-pulse - so asking systemd to
# stop pulseaudio.service just fails and leaves the card held.
AUDIO_UNITS="wireplumber.service pipewire.service pipewire.socket"

audio_grab() {
	AUDIO_STATE_FILE=$(mktemp /tmp/fp3-alsa-state.XXXXXX)
	alsactl store -f "$AUDIO_STATE_FILE" 2>/dev/null

	AUDIO_SERVER_USER=$(_audio_server_user)
	if [ -n "$AUDIO_SERVER_USER" ]; then
		# shellcheck disable=SC2086 # unit list must word-split
		systemctl -M "$AUDIO_SERVER_USER@" --user stop $AUDIO_UNITS 2>/dev/null
		# The socket unit restarts the daemon on demand, so give the stop a
		# moment to actually release the card before we open it.
		sleep 1
	fi
	AUDIO_HELD=1
	trap audio_release EXIT INT TERM
}

audio_release() {
	[ "$AUDIO_HELD" -eq 1 ] || return 0
	AUDIO_HELD=0

	[ -n "$AUDIO_STATE_FILE" ] && [ -s "$AUDIO_STATE_FILE" ] &&
		alsactl restore -f "$AUDIO_STATE_FILE" 2>/dev/null
	rm -f "$AUDIO_STATE_FILE"

	if [ -n "$AUDIO_SERVER_USER" ]; then
		# shellcheck disable=SC2086
		systemctl -M "$AUDIO_SERVER_USER@" --user start $AUDIO_UNITS 2>/dev/null
	fi
}

# The card has to be addressed as hw:0 explicitly. ALSA's "default" device is
# routed through PulseAudio here, so once audio_grab has stopped the sound
# server every plain `amixer` call dies with "Connection refused" - which looks
# exactly like "the control does not exist" and sends you hunting for a kernel
# regression that is not there.
AUDIO_CARD="${AUDIO_CARD:-hw:0}"

# Apply a list of control/value pairs, reporting any that do not exist. A
# missing control is a real finding - it usually means a DAPM widget or route
# disappeared from the kernel - so it is never silently ignored.
audio_cset() {
	_missing=0
	while [ $# -gt 0 ]; do
		if ! amixer -D "$AUDIO_CARD" -q cset "name=$1" "$2" >/dev/null 2>&1; then
			echo "FAIL: mixer control missing or unsettable: '$1' -> $2"
			_missing=1
		fi
		shift 2
	done
	return $_missing
}

# The FP3 loudspeaker is an AW8898 smart amp whose only level control is its own
# "RX Volume" (0..255 = -127.5..0 dB in 0.5 dB steps; 255 = 0 dB = full output,
# which is how it boots). A check that plays a tone through the speaker is
# therefore at full volume unless it says otherwise, which is needlessly loud.
# speaker_quiet lowers it by 12 dB (a quarter of the amplitude) for the duration
# of a check; that is clearly quieter yet still leaves the 1 kHz tone well above
# the acoustic-loopback detection margin, so the checks keep passing. Pair it
# with speaker_restore. Addressed on hw:0 directly so it works whether or not the
# sound server is running (see AUDIO_CARD note above). Tune QUIET if a different
# level is wanted - it is a plain 0..255 value.
AW8898_VOL_FULL=255
AW8898_VOL_QUIET=231		# 255 - 24 steps of 0.5 dB = -12 dB (quarter amplitude)

speaker_quiet() {
	amixer -D "$AUDIO_CARD" -q cset "name=RX Volume" "$AW8898_VOL_QUIET" \
		>/dev/null 2>&1
}

speaker_restore() {
	amixer -D "$AUDIO_CARD" -q cset "name=RX Volume" "$AW8898_VOL_FULL" \
		>/dev/null 2>&1
}
