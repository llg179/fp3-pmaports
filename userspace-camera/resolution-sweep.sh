#!/bin/sh
# Which viewfinder resolutions actually deliver frames, measured one at a time.
#
# A camera advertises sizes it cannot always stream. Asked for one of those the
# pipeline does not refuse - it accepts, delivers nothing, and posts an internal
# data stream error a moment later, which is what reaches the user as "Could not
# play camera stream". The only honest way to know which sizes are real is to
# ask for each and see whether pictures arrive.
#
# ☠️ Every round demands positive evidence from the application's own log, and
# a round that produces neither answer is reported as unknown rather than as a
# pass. The first version of this script did not, and reported all 47 sizes as
# working from an application that had never opened a camera at all: the check
# was reading an empty log and calling the silence a success.
#
# ☠️ The second version had the opposite failure, and it is the reason for the
# two guards below. It reported nine sizes as broken; all nine were simply the
# ones tried last. Five minutes into an unattended run the screen blanked, the
# software ISP's GPU debayer faulted on buffers that were no longer mapped -
# some 28000 unhandled IOMMU faults in under a minute - and the stream stopped
# for good. Every round after that was a failure at whatever size it happened to
# be holding, including sizes that had streamed earlier in the same run. So:
#
#   * the screen is checked every round, because a sweep measured behind a dark
#     screen is measuring the blanking, and
#   * a failure is never believed until a size known to stream is re-measured
#     immediately afterwards. If the control fails too, the stream is gone and
#     the sweep stops rather than attributing the death to the size in hand.
#
# Neither guard is optional: in a one-pass sweep the order and the input change
# together, and only a control measured *after* the failure separates them.
#
# Preconditions, all checked rather than assumed:
#   * Snapshot is running, on screen, showing the viewfinder. It has to be a
#     real window - an instance started over ssh with no display registers on
#     the bus, logs three lines and never opens the camera.
#   * It was started with RUST_LOG=info, or the lines this reads are not
#     emitted. `systemctl --user set-environment RUST_LOG=info` then restart it.
#
# Output is two lists on stdout, and a machine-readable one in $OUT.

set -u

APP=org.gnome.Snapshot
KEY=preview-resolution
SETTLE=${SETTLE:-6}          # PROBE_SECONDS is 3; leave room for the restart
OUT=${OUT:-/tmp/resolution-sweep.txt}

journal_since() {
	journalctl --user --since "$1" --no-pager 2>/dev/null | grep snapshot
}

# FB_BLANK_UNBLANK is 0; anything else means the panel is off, and a viewfinder
# behind a dark screen delivers nothing whatever size it was asked for.
screen_is_on() {
	for bl in /sys/class/backlight/*/bl_power; do
		[ "$(cat "$bl" 2>/dev/null)" = "0" ] && return 0
	done
	return 1
}

# Ask for one size and say what the viewfinder did with it: ok, fail, unknown.
measure() {
	mark=$(date '+%Y-%m-%d %H:%M:%S')
	sleep 1
	gsettings set "$APP" "$KEY" "$1"
	sleep "$SETTLE"
	said=$(journal_since "$mark")

	if echo "$said" | grep -q "Nothing arrives at $1"; then
		echo fail
	elif echo "$said" | grep -q "Preview at $1"; then
		echo ok
	else
		echo unknown
	fi
}

if ! pgrep -x snapshot >/dev/null; then
	echo "Snapshot is not running - open it on the camera first" >&2
	exit 1
fi

if ! screen_is_on; then
	echo "The screen is off; nothing measured here would mean anything" >&2
	exit 1
fi

# A sweep takes minutes and nobody touches the phone during it, so the session's
# own idle timer will blank the screen halfway through unless it is turned off.
saved_idle=$(gsettings get org.gnome.desktop.session idle-delay 2>/dev/null)
gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null
trap 'gsettings set org.gnome.desktop.session idle-delay ${saved_idle##* } 2>/dev/null' EXIT INT TERM

# ☠️ The size list comes from PipeWire, not from cam(1). `cam` opens the camera
# through libcamera directly, and the application under measurement is already
# holding it - so it fails with 'Resource busy' and prints no sizes at all,
# which an unguarded pipeline would turn into an empty sweep. PipeWire is
# already the owner, and publishes the same enumeration in its node parameters.
sizes=$(pw-dump 2>/dev/null |
	grep -o '"size": *{ *"width": *[0-9]*, *"height": *[0-9]*' |
	sed 's/.*width": *\([0-9]*\).*height": *\([0-9]*\)/\1x\2/' | sort -u)
if [ -z "$sizes" ]; then
	echo "Could not read the camera's sizes from pw-dump" >&2
	exit 1
fi

# Prove the instrument before trusting it: nudge the resolution and require the
# viewfinder to say something about it. Without this the whole sweep can read an
# application that is not looking at a camera and call every size good.
REFERENCE=${REFERENCE:-1920x1080}
if [ "$(measure "$REFERENCE")" != ok ]; then
	cat >&2 <<EOF
The viewfinder does not stream at $REFERENCE, so there is no control to measure
failures against and this sweep would be a list of unattributable failures.
Check that:
  * its window is on screen showing the viewfinder, not just the process alive
  * it was started with RUST_LOG=info in its environment
  * the stream has not already died - restarting the application clears that
EOF
	exit 1
fi
echo "instrument checked: the viewfinder streams at the control size $REFERENCE"
echo

: > "$OUT"
works=""
fails=""
unknown=""

for size in $sizes; do
	if ! screen_is_on; then
		echo "the screen went off - stopping rather than measuring the dark" >&2
		break
	fi

	verdict=$(measure "$size")

	# ☠️ A failure is a claim about this size only if the camera is still able
	# to stream at all. Re-measure the control before believing it.
	if [ "$verdict" = fail ] && [ "$(measure "$REFERENCE")" != ok ]; then
		echo "$size fail, and $REFERENCE fails now too: the stream is gone" >&2
		echo "everything from here on would be that, not the size" >&2
		break
	fi

	case $verdict in
	ok) works="$works $size" ;;
	fail) fails="$fails $size" ;;
	*) unknown="$unknown $size" ;;
	esac
	printf '%s %s\n' "$size" "$verdict" >>"$OUT"
	printf '%-12s %s\n' "$size" "$verdict"
done

echo
echo "stream:  $(echo $works   | wc -w):$works"
echo "do not:  $(echo $fails   | wc -w):$fails"
echo "unknown: $(echo $unknown | wc -w):$unknown"
echo "written to $OUT"
[ -z "$unknown" ] || echo "an unknown is not a pass - the viewfinder said nothing either way" >&2
