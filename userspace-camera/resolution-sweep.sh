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

if ! pgrep -x snapshot >/dev/null; then
	echo "Snapshot is not running - open it on the camera first" >&2
	exit 1
fi

sizes=$(cam -c1 -I 2>/dev/null | sed -n 's/^  - \([0-9]*x[0-9]*\)$/\1/p' | sort -u)
if [ -z "$sizes" ]; then
	echo "Could not read the camera's sizes from cam(1)" >&2
	exit 1
fi

# Prove the instrument before trusting it: nudge the resolution and require the
# viewfinder to say something about it. Without this the whole sweep can read an
# application that is not looking at a camera and call every size good.
probe_size=$(echo "$sizes" | head -1)
mark=$(date '+%Y-%m-%d %H:%M:%S')
sleep 1
gsettings set "$APP" "$KEY" "$probe_size"
sleep "$SETTLE"
if ! journal_since "$mark" | grep -qE "Preview at|Nothing arrives at"; then
	cat >&2 <<EOF
Snapshot logged nothing about $probe_size, so this sweep would measure silence.
Check that:
  * its window is on screen showing the viewfinder, not just the process alive
  * it was started with RUST_LOG=info in its environment
EOF
	exit 1
fi
echo "instrument checked: the viewfinder reports what it is asked for"
echo

: > "$OUT"
works=""
fails=""
unknown=""

for size in $sizes; do
	mark=$(date '+%Y-%m-%d %H:%M:%S')
	sleep 1
	gsettings set "$APP" "$KEY" "$size"
	sleep "$SETTLE"
	said=$(journal_since "$mark")

	if echo "$said" | grep -q "Nothing arrives at $size"; then
		verdict=fail
		fails="$fails $size"
	elif echo "$said" | grep -q "Preview at $size"; then
		verdict=ok
		works="$works $size"
	else
		verdict=unknown
		unknown="$unknown $size"
	fi
	printf '%s %s\n' "$size" "$verdict" >>"$OUT"
	printf '%-12s %s\n' "$size" "$verdict"
done

echo
echo "stream:  $(echo $works   | wc -w):$works"
echo "do not:  $(echo $fails   | wc -w):$fails"
echo "unknown: $(echo $unknown | wc -w):$unknown"
echo "written to $OUT"
[ -z "$unknown" ] || echo "an unknown is not a pass - the viewfinder said nothing either way" >&2
