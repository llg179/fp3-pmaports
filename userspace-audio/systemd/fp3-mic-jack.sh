#!/bin/sh
# FP3 microphone jack switch: route the single capture source to the headset
# microphone (AMIC2) when a headset is plugged, otherwise to the built-in
# handset digital mic (DMIC0).
#
# It only touches the codec input mux on an actual jack transition - re-applying
# the mux while a capture stream is running glitches the decimator and silences
# it, so during normal use (volume changes etc. also wake alsactl monitor) the
# route is left untouched.
CARD=0
last=""

apply() {
	if amixer -c $CARD cget numid=70 2>/dev/null | grep -q 'values=on'; then
		state=headset
	else
		state=handset
	fi
	[ "$state" = "$last" ] && return
	last=$state
	if [ "$state" = headset ]; then
		amixer -c $CARD -q cset name='ADC MUX0' AMIC
		amixer -c $CARD -q cset name='AMIC MUX0' ADC2
		amixer -c $CARD -q cset name='ADC2 Volume' 20
	else
		amixer -c $CARD -q cset name='ADC MUX0' DMIC
		amixer -c $CARD -q cset name='DMIC MUX0' DMIC0
	fi
}

apply
alsactl monitor hw:$CARD 2>/dev/null | while read -r _; do
	apply
done
