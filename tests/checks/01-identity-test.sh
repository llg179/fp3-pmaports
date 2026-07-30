#!/bin/sh
# Description: the running kernel is the one we think we are testing
#
# This runs first and blocks everything else, because a green battery on the
# previous kernel proves nothing at all. It reports every mismatch it finds
# rather than stopping at the first: when the identity is wrong you want the
# whole picture in one look, not one clue per run.

fail=0
say() { echo "$1: $2"; }

# 1. Build stamp. The APKBUILD sets KBUILD_BUILD_VERSION="$((pkgrel + 1))-$_flavor",
#    so pkgrel 3 must show up as "#4-fp3" in uname -v. This is exact, cheap,
#    and impossible to fake by reinstalling userspace.
want_stamp="#$((EXP_PKGREL + 1))-$EXP_FLAVOR"
have_stamp=$(uname -v)
case "$have_stamp" in
*"$want_stamp"*) say PASS "build stamp $want_stamp" ;;
*)
	say FAIL "build stamp: expected '$want_stamp', running '$have_stamp'"
	fail=1
	;;
esac

# 2. Installed package version.
want_pkg="$KERNEL_PKG-$EXP_PKGVER-r$EXP_PKGREL"
have_pkg=$(apk info -v 2>/dev/null | grep "^$KERNEL_PKG-[0-9]" | head -1)
if [ "$have_pkg" = "$want_pkg" ]; then
	say PASS "installed package $have_pkg"
else
	say FAIL "package: expected '$want_pkg', installed '${have_pkg:-none}'"
	fail=1
fi

# 3. Source commit. pkgrel alone cannot tell two _commits apart, so the package
#    stamps the commit it was built from. An older package predates the stamp;
#    say so plainly instead of reporting a mismatch against nothing.
commit_file="/usr/share/kernel/$EXP_FLAVOR/fp3-commit"
if [ -f "$commit_file" ]; then
	have_commit=$(cat "$commit_file")
	if [ "$have_commit" = "$EXP_COMMIT" ]; then
		say PASS "source commit $(echo "$EXP_COMMIT" | cut -c1-12)"
	else
		say FAIL "source commit: expected $EXP_COMMIT, built from $have_commit"
		fail=1
	fi
else
	say FAIL "no $commit_file - this package predates the commit stamp, so the"
	say FAIL "  running kernel cannot be tied to a debug-int/<base> commit"
	fail=1
fi

# 4. Right device at all.
model=$(tr -d '\0' </proc/device-tree/model 2>/dev/null)
case "$model" in
*"Fairphone 3"*) say PASS "device is $model" ;;
*)
	say FAIL "device model is '${model:-unknown}', not a Fairphone 3"
	fail=1
	;;
esac

exit $fail
