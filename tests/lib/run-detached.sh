#!/bin/sh
# Launch a check that will drop the SSH link, and make sure its verdict
# survives that.
#
# Usage: run-detached.sh <check-basename> <output-file>
#
# Everything here could be written inline in the runner's ssh command, and it
# was - but it needs single quotes inside the single quotes ssh_root already
# uses, and the result silently executed part of the command outside sudo. A
# file has no quoting problem.

set -u
check=$1
outfile=$2
dir=$(cd "$(dirname "$0")/.." && pwd)

. "$dir/env.sh"

# Write the verdict and flush it before the risky part can reset the link. A
# tee'd pipe would only hold what it happened to flush, so a device that
# re-enumerates mid-run truncates the file at an early line and loses exactly
# the result we came for.
{
	sh "$dir/checks/$check" 2>&1
	echo "__EXIT=$?"
} >"$outfile" 2>&1
sync
