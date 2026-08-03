#!/bin/sh
# How many times can the camera stream be reconfigured before it stops working?
#
# "Could not play camera stream" was first read as a property of the *size* the
# viewfinder asked for: the camera advertises sizes it cannot deliver, so the
# fix would be to offer fewer of them. Measuring one size at a time in a running
# camera app said otherwise - the sizes that failed were the ones tried last,
# and once the camera had failed once it failed at every size afterwards,
# including sizes that had streamed a minute earlier in the same run. It is the
# number of reconfigurations that matters, not which sizes they were.
#
# ☠️ That first sweep is why this test exists and why it is shaped like this. It
# swept in one pass, in order, and reported nine sizes as broken. All nine were
# simply after the failure. A sweep in time order confounds the input with the
# order, and the only thing that separates them is a control that is re-measured
# *after* a failure - which is what `reference` does below.
#
# This needs no screen and no camera application: `pipewiresrc` reaches the same
# node an application would, so the whole measurement runs over ssh. That also
# rules the application out as the cause, since it is not running.
#
# Usage: stream-restart-test.sh [rounds]
# Output: a line per round, then the round at which the stream died.

set -u

ROUNDS=${1:-40}
BUFFERS=${BUFFERS:-10}
WAIT=${WAIT:-20}

node=$(pw-cli ls Node 2>/dev/null |
	awk '/^\tid [0-9]+, type PipeWire:Interface:Node/ { id = $2; sub(",", "", id) }
	     /media.role = "Camera"/ { print id; exit }')
if [ -z "$node" ]; then
	echo "No camera node in PipeWire" >&2
	exit 1
fi
echo "camera node: $node"

# A size known to stream, re-measured after every failure. Without it a failure
# cannot be told apart from a size the camera never supported.
reference=${REFERENCE:-1920x1080}

# Sizes to cycle through, chosen to span the range rather than to be exhaustive:
# the question here is how many reconfigurations survive, not which sizes do.
sizes=${SIZES:-"1920x1080 1280x720 640x480 2560x1440 800x600 3840x2160 320x240"}

try() {
	w=${1%x*}
	h=${1#*x}
	timeout "$WAIT" gst-launch-1.0 -q \
		pipewiresrc path="$node" num-buffers="$BUFFERS" \
		! "video/x-raw,width=$w,height=$h" \
		! fakesink sync=false >/dev/null 2>&1
}

round=0
died=""
while [ "$round" -lt "$ROUNDS" ]; do
	round=$((round + 1))
	size=$(echo "$sizes" | tr ' ' '\n' | sed -n "$(( (round - 1) % $(echo "$sizes" | wc -w) + 1 ))p")

	if try "$size"; then
		printf '%3d %-10s ok\n' "$round" "$size"
		continue
	fi

	# The control: the same stream at a size that has been streaming all along.
	# If that fails too, this is not the size - the stream itself is gone.
	if try "$reference"; then
		printf '%3d %-10s fail (reference %s still streams: this size)\n' \
			"$round" "$size" "$reference"
	else
		printf '%3d %-10s fail (reference %s dead too: the stream is gone)\n' \
			"$round" "$size" "$reference"
		died=$round
		break
	fi
done

echo
if [ -n "$died" ]; then
	echo "the stream stopped answering after $died reconfigurations"
	echo 'check dmesg for "gpu fault" - the software ISP debayers on the GPU'
else
	echo "survived $ROUNDS reconfigurations"
fi
