#!/bin/sh
# Host-side helpers shared by the fp3-selftest runner.
#
# Every device command goes through ssh_run/ssh_root here, so the connection
# conventions (password auth only, sudo prompt discarded) live in exactly one
# place. See tests/README.md for why each convention exists.

FP3_HOST="${FP3_HOST:-172.16.42.1}"
FP3_USER="${FP3_USER:-fp3}"
FP3_PW="${FP3_PW:-}"
FP3_PIN="${FP3_PIN:-}"

SSH_OPTS="-o PreferredAuthentications=password -o PubkeyAuthentication=no
	-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null
	-o LogLevel=ERROR -o ConnectTimeout=10"

# Run a command on the device as the normal user.
ssh_run() {
	# shellcheck disable=SC2086 # SSH_OPTS must word-split
	sshpass -p "$FP3_PW" ssh $SSH_OPTS "$FP3_USER@$FP3_HOST" "$@"
}

# Run a command on the device as root.
#
# The sudo prompt has no trailing newline, so it prepends itself to the first
# line of output. Filtering it with grep would therefore delete that line
# *including* the command's own first line of output - which looks like the
# command produced nothing while still exiting 0. Send it to /dev/null instead.
# The inner 2>&1 keeps the command's own stderr, which the outer redirect
# would otherwise swallow along with the prompt.
ssh_root() {
	ssh_run "echo '$FP3_PW' | sudo -S sh -c '$* 2>&1' 2>/dev/null"
}

ssh_copy() {
	# shellcheck disable=SC2086
	sshpass -p "$FP3_PW" scp $SSH_OPTS -r "$1" "$FP3_USER@$FP3_HOST:$2"
}

ssh_fetch() {
	# shellcheck disable=SC2086
	sshpass -p "$FP3_PW" scp $SSH_OPTS "$FP3_USER@$FP3_HOST:$1" "$2"
}

device_reachable() {
	ssh_run true >/dev/null 2>&1
}

# Wait for the device to come back after a link drop. The CDC-NCM link on this
# device re-enumerates unpredictably (and always across a suspend/resume), so
# any step that can drop it is followed by this rather than by a single retry.
wait_for_device() {
	_deadline=$(( $(date +%s) + ${1:-120} ))
	while [ "$(date +%s)" -lt "$_deadline" ]; do
		device_reachable && return 0
		sleep 3
	done
	return 1
}

# --- check metadata -------------------------------------------------------
# Checks declare their own requirements in header comments so the runner never
# holds a second, drift-prone copy of that knowledge:
#
#   # Category: voice          -> counts towards fp3-integration topic coverage
#   # Requires: modem call     -> skipped when --no-modem / --no-call is given
#   # ColdPhase: call          -> needs a fresh boot in that cold phase
#
check_meta() {
	sed -n "s/^# $2: *//p" "$1" | head -1
}

log_line() {
	printf '%s\n' "$*" | tee -a "$RUN_LOG"
}
