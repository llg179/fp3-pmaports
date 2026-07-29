# Rolling to a new kernel base

## The model this procedure moves

The layers and the category rule are on the
[front page](../README.md#the-branch-model); this is the part you only need when
a base actually changes.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who has run this procedure through the
> base changes it describes.

Worked across two real bases — `7.0.9` (retired, kept as history) and `7.1.3`
(current) — every branch reads off at a glance:

| role | `7.0.9` (previous) | `7.1.3` (current) |
|---|---|---|
| base (upstream fork) | `7.0.9/main` | `7.1.3/main` |
| work + fixes | `wip/7.0.9/{audio,voice,camera,charger}` | `wip/7.1.3/{audio,voice,camera,charger,sensor,debug}` |
| device build | `integration/7.0.9` | `integration/7.1.3` |
| LKML minimal series | — *(rolled straight into 7.1.3)* | `submit/7.1.3/{audio,voice,camera,charger}` |
| package `pkgver` | `7.0.9` | `7.1.3` |

`7.1.3` was brought up cleanly, so its `wip` and `submit` branches point at the
same commits; on a messier bump they diverge — `wip` carries the fix history,
`submit` the distilled series.

Two categories have no `submit` branch, for different reasons: `sensor` is not
distilled yet, and `debug` never will be — the watchdog-at-probe change is a
bring-up safety net, not upstream material. Both still obey the category rule,
so both must be rolled.

**Why `integration` is versioned.** A base bump breaks things — a rebased driver
that no longer applies cleanly, a renamed Kconfig symbol, a clock that changed
under it — and fixing them takes iterations of build → deploy → test. Keeping
`integration/<prev>` (and the package's previous `pkgver`) intact means the
device always has a **known-good kernel to fall back to** while the new base is
brought up. A single, mutable integration branch would destroy the working
version the moment the new base was checked out.

When `msm8953-mainline` cuts a new release — say `7.2.0/main` — this is the
whole procedure. Nothing here is renamed for the version; only the base segment
of the branches and the package `pkgver` change.

## Setting the checkouts up (once per machine)

Three trees are involved: the [kernel fork](https://github.com/llg179/linux),
this repo, and a postmarketOS build
environment. The kernel fork keeps upstream and our work on **separate
remotes** — `origin` is `msm8953-mainline` and is never pushed to, `fork` is
ours and is the only push target.

```sh
# the kernel: upstream as origin, our fork as fork
git clone https://github.com/msm8953-mainline/linux.git linux-fp3
cd linux-fp3
#   port 443, because plain SSH (22) stalls on some networks
git remote add fork ssh://git@ssh.github.com:443/llg179/linux.git
git fetch fork
cd ..

# this repo: the APKBUILD, the config, the userspace bits and the tests
git clone ssh://git@ssh.github.com:443/llg179/fp3-pmaports.git

# the build environment: pmbootstrap + a pmaports checkout it works out of
git clone https://gitlab.postmarketos.org/postmarketOS/pmbootstrap.git
git clone https://gitlab.postmarketos.org/postmarketOS/pmaports.git
./pmbootstrap/pmbootstrap.py init          # device fairphone-fp3, edge, aarch64

# the package lives in pmaports; this repo is its home, so mirror it in
mkdir -p pmaports/device/testing/linux-fp3
cp fp3-pmaports/linux-fp3/{APKBUILD,config-fp3.aarch64} \
   pmaports/device/testing/linux-fp3/
```

A wrapper keeps the config and work directory explicit, which matters once more
than one checkout exists on the machine:

```sh
cat > pmb <<'EOF'
#!/bin/bash
exec "$PWD/pmbootstrap/pmbootstrap.py" -c "$PWD/pmbootstrap_v3.cfg" -w "$PWD/work" "$@"
EOF
chmod +x pmb
```

Two traps worth knowing before the first fetch:

* **the base branch names contain a slash**, so `git fetch origin '7.2.0/main'`
  leaves the result in `FETCH_HEAD` and there is usually **no
  `origin/7.2.0/main` ref**. Resolve the SHA once (`git rev-parse FETCH_HEAD`)
  and branch from that; `git checkout -b … origin/7.2.0/main` fails, and if it
  is chained with `&&`-less commands the ones after it run on whatever branch
  you were already on.
* **a shallow clone lies about history.** `git log -- <path>` in a `depth=1`
  checkout returns one commit for every path, which looks like an answer. Clone
  in full, or query the API instead.

## The procedure

Everything from here runs **in the kernel checkout** unless a step says
otherwise; the two steps that touch the package say where they run.

```sh
cd linux-fp3

# 0. fetch the new base (see the slash trap above) and give it a local ref, so
#    the steps below can name it instead of carrying a SHA around
git fetch origin '7.2.0/main'
git branch -f 7.2.0/main FETCH_HEAD

# 1. rebase each category's work onto the new base -> wip/7.2.0/<category>
#    (start from the previous base's wip if it still exists, else its submit)
for cat in audio voice camera charger sensor debug; do
	#   sensor and debug have no submit branch - always start from their wip
	git checkout -b wip/7.2.0/$cat wip/7.1.3/$cat
	git rebase --onto 7.2.0/main 7.1.3/main wip/7.2.0/$cat
	#   resolve conflicts; the commit COUNT does not grow - a rebase replays
	#   the same minimal series, it does not add commits
	git push fork wip/7.2.0/$cat          # new branch, no force-push
done

# 2. build integration/7.2.0 = cherry-pick union of the wip branches
git checkout -B integration/7.2.0 7.2.0/main
git cherry-pick <wip/7.2.0/audio range> <voice> <camera> <charger> <sensor> <debug>
git push -f fork integration/7.2.0        # derived + disposable, force is fine

# 3. build the package - the ONLY version edit
#    linux-fp3/APKBUILD: pkgver=7.2.0, _commit=<integration/7.2.0 HEAD>
git push fork integration/7.2.0           # push BEFORE checksum (404 trap below)
( cd ../fp3-pmaports                      # <- the package, not the kernel
  $EDITOR linux-fp3/APKBUILD              #    pkgver + _commit, nothing else
  cp linux-fp3/APKBUILD ../pmaports/device/testing/linux-fp3/ )
cd .. && ./pmb checksum linux-fp3         # or pmbootstrap, if it is on PATH
./pmb build --arch aarch64 linux-fp3
cd linux-fp3

# 4. deploy KEEPING the last good kernel as a fallback boot entry, then test
#    (see docs/deploy/); the working integration/7.1.3 build stays bootable
( cd ../fp3-pmaports && tests/fp3-selftest )

# 5. fix the bump errors on wip/7.2.0/<category>, cherry-pick each onto
#    integration/7.2.0 (category rule), rebuild the package, redeploy, retest.
#    Loop until fp3-selftest is green.

# 6. everything works -> distil the minimal upstream series
#    (only the upstream-bound categories; debug never gets one)
for cat in audio voice camera charger; do
	git checkout -b submit/7.2.0/$cat wip/7.2.0/$cat
	#   squash/reorder to the minimal set, checkpatch each commit, keep the
	#   Assisted-by: trailer and NO Signed-off-by from the AI (see the
	#   msm8953-mainline-pr skill)
	git push fork submit/7.2.0/$cat
done

# 7. the new base is validated -> prune the old one
for cat in audio voice camera charger sensor debug; do
	git push fork --delete wip/7.1.3/$cat
done
for cat in audio voice camera charger; do
	git push fork --delete submit/7.1.3/$cat   # once its LKML business is done
done
git push fork --delete integration/7.1.3
```

**Steady state:** one live base. During a transition two bases coexist for a
while — useful, because the `7.1.3` series can stay under LKML review while
`7.2.0` is brought up beside it — then the old one is pruned.

**Posting to the LKML** is independent of this base-rolling. The device
integration rides `X.Y.Z/main`; a subsystem submission targets that subsystem's
`-next` tree instead. At post time, cut a throwaway branch from
`submit/<base>/<category>`, rebase it onto `sound/for-next` (audio/voice),
`media` (camera), `power-supply` (charger) or the SoC tree (dts), run
`checkpatch` / `get_maintainer` / `b4`, send, and drop the throwaway branch. The
series version (v1, v2, …) lives in the cover letter, not in a branch name.
