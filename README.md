# fp3-pmaports

The postmarketOS package that builds the Fairphone 3 mainline kernel — mainline
`msm8953` with the WCD9335 SLIMbus audio work, the Sony IMX363 rear camera and
the PMI632 charger.

Without this, the [kernel branches](https://github.com/llg179/linux) are only
source: nothing records which config was used, which symbols had to be turned
on by hand, or how the thing was actually built.

## The goal, and why the names have no version in them

`llg179/linux` is a **rolling forward-port** of Fairphone 3 support onto the
latest [`msm8953-mainline`](https://github.com/msm8953-mainline/linux) release
(`X.Y.Z/main`), kept moving from one kernel base to the next until the work
lands upstream on the LKML.

Because the base keeps changing, the kernel version is deliberately confined to
the **two places where it is genuinely the identity of something**:

* the base segment of a base-relative branch — `wip/7.1.3/audio`,
  `submit/7.1.3/audio`, `integration/7.1.3` — a patch series *is* "the series
  against 7.1.3", so the version belongs in the name, and the old ones are
  pruned once a base is retired; and
* the package `pkgver`.

Everything else — the package name `linux-fp3`, its flavor `fp3`, the config
`config-fp3.aarch64`, the test suite, the boot entries — carries **no version**.
Bumping `pkgver` is the single edit that moves the whole thing to a new kernel.

## The branch model

For a base `X.Y.Z` there are three layers, each base-relative:

| branch | layer | contents |
|---|---|---|
| `X.Y.Z/main` | base | the upstream `msm8953-mainline` release; not ours to rename, we just follow the newest |
| `wip/X.Y.Z/<category>` | work | the category's commits rebased onto the base, **plus the bump fixes** — messy, evolving history |
| `integration/X.Y.Z` | build | the cherry-pick union of the `wip/X.Y.Z/*` branches; **this is what the package builds**, and it is versioned so the last working `integration/<prev>` survives while the new base is still being fixed |
| `submit/X.Y.Z/<category>` | upstream | the **minimal** series distilled from `wip/X.Y.Z/<category>` — created only once everything works, ready to post to the LKML |

The four categories are always the same:

| category | what it adds |
|---|---|
| `audio` | WCD9335 over SLIMbus: playback, the four digital mics, headset (MBHC) jack detection |
| `voice` | call audio, by routing the voice mixers over SLIMbus |
| `camera` | the Sony IMX363 rear sensor |
| `charger` | the PMI632 charger, via `qcom_smbx` |

Worked across two real bases — `7.0.9` (retired, kept as history) and `7.1.3`
(current) — every branch reads off at a glance:

| role | `7.0.9` (previous) | `7.1.3` (current) |
|---|---|---|
| base (upstream fork) | `7.0.9/main` | `7.1.3/main` |
| work + fixes | `wip/7.0.9/{audio,voice,camera,charger}` | `wip/7.1.3/{audio,voice,camera,charger}` |
| device build | `integration/7.0.9` | `integration/7.1.3` |
| LKML minimal series | — *(rolled straight into 7.1.3)* | `submit/7.1.3/{audio,voice,camera,charger}` |
| package `pkgver` | `7.0.9` | `7.1.3` |

Reading it: "what runs on the phone" is always `integration/<pkgver>`; "what
goes to the kernel" is always `submit/<pkgver>/<category>`; the base version is
the only thing that changes. (`7.1.3` was brought up cleanly, so its `wip` and
`submit` branches point at the same commits; on a messier bump they diverge —
`wip` carries the fix history, `submit` the distilled series.)

**The category rule (version-free):** a change lands on `wip/X.Y.Z/<category>`
**and** is cherry-picked onto `integration/X.Y.Z` — the two never diverge,
integration is only ever the sum of the `wip` branches. `submit/X.Y.Z/<category>`
is regenerated from `wip` when the base is done; it is not edited by hand.

**Why `integration` is versioned.** A base bump breaks things — a rebased driver
that no longer applies cleanly, a renamed Kconfig symbol, a clock that changed
under it — and fixing them takes iterations of build → deploy → test. Keeping
`integration/<prev>` (and the package's previous `pkgver`) intact means the
device always has a **known-good kernel to fall back to** while the new base is
brought up. A single, mutable integration branch would destroy the working
version the moment the new base was checked out.

## Rolling to a new kernel base

When `msm8953-mainline` cuts a new release — say `7.2.0/main` — this is the
whole procedure. Nothing here is renamed for the version; only the base segment
of the branches and the package `pkgver` change.

```sh
# 0. fetch the new base
git fetch upstream 7.2.0/main

# 1. rebase each category's work onto the new base -> wip/7.2.0/<category>
#    (start from the previous base's wip if it still exists, else its submit)
for cat in audio voice camera charger; do
	git checkout -b wip/7.2.0/$cat submit/7.1.3/$cat
	git rebase --onto 7.2.0/main 7.1.3/main wip/7.2.0/$cat
	#   resolve conflicts; the commit COUNT does not grow - a rebase replays
	#   the same minimal series, it does not add commits
	git push fork wip/7.2.0/$cat          # new branch, no force-push
done

# 2. build integration/7.2.0 = cherry-pick union of the wip branches
git checkout -B integration/7.2.0 7.2.0/main
git cherry-pick <wip/7.2.0/audio range> <voice> <camera> <charger>
git push -f fork integration/7.2.0        # derived + disposable, force is fine

# 3. build the package - the ONLY version edit
#    linux-fp3/APKBUILD: pkgver=7.2.0, _commit=<integration/7.2.0 HEAD>
git push fork integration/7.2.0           # push BEFORE checksum (404 trap below)
pmbootstrap checksum linux-fp3
pmbootstrap build linux-fp3

# 4. deploy KEEPING the last good kernel as a fallback boot entry, then test
#    (see Deploying); the working integration/7.1.3 build stays bootable
tests/fp3-selftest

# 5. fix the bump errors on wip/7.2.0/<category>, cherry-pick each onto
#    integration/7.2.0 (category rule), rebuild the package, redeploy, retest.
#    Loop until fp3-selftest is green.

# 6. everything works -> distil the minimal upstream series
for cat in audio voice camera charger; do
	git checkout -b submit/7.2.0/$cat wip/7.2.0/$cat
	#   squash/reorder to the minimal set, checkpatch each commit, keep the
	#   Assisted-by: trailer and NO Signed-off-by from the AI (see the
	#   msm8953-mainline-pr skill)
	git push fork submit/7.2.0/$cat
done

# 7. the new base is validated -> prune the old one
for cat in audio voice camera charger; do
	git push fork --delete wip/7.1.3/$cat
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

## Building

```sh
git clone https://github.com/llg179/fp3-pmaports
cp -r fp3-pmaports/linux-fp3 <your-pmaports>/device/testing/

pmbootstrap checksum linux-fp3      # only needed if you changed _commit
pmbootstrap build linux-fp3
```

The source tarball is ~250 MB straight from GitHub, so the first fetch takes a
minute or two. A warm ccache rebuild is around four minutes; a new `_commit`
means a new source directory and therefore a cold ccache, which is 20–35.

⚠️ **Push `integration/<base>` before you bump `_commit`.** The package fetches
the tarball from GitHub, so a commit that only exists locally gives a 404 during
`pmbootstrap checksum`. If you skip the checksum step, the build fails one step
later with the far less helpful

```
ERROR: linux-fp3-<sha>.tar.gz is missing in checksums
```

which points at the checksums rather than at the missing push.

## Deploying

The built package lands in `~/.local/var/pmbootstrap/packages/edge/aarch64/`
(`$PMB_WORK/packages/...` if you moved the work dir). An apk is a gzipped tar,
so unpack it and take the pieces you need:

```sh
APK=~/.local/var/pmbootstrap/packages/edge/aarch64/linux-fp3-7.1.3-r0.apk
mkdir -p /tmp/apk && tar xzf "$APK" -C /tmp/apk

tar tzf "$APK" | grep q6voice-dai        # check the module is actually in there
```

**Device tree only** — extlinux loads the fdt separately, so no kernel flash and
no module rebuild is needed. Roughly a two-minute round trip:

```sh
scp /tmp/apk/boot/dtbs/qcom/sdm632-fairphone-fp3.dtb fp3@$FP3_DEV_IP:/tmp/
ssh fp3@$FP3_DEV_IP 'sudo cp /tmp/sdm632-fairphone-fp3.dtb /boot/ && sudo sync && sudo reboot'
```

**A driver change** — copy the module in beside the others and refresh the
dependency list:

```sh
KREL=$(ssh fp3@$FP3_DEV_IP uname -r)
scp /tmp/apk/lib/modules/$KREL/kernel/sound/soc/qcom/qdsp6/q6voice-dai.ko \
    fp3@$FP3_DEV_IP:/tmp/
ssh fp3@$FP3_DEV_IP "sudo cp /tmp/q6voice-dai.ko \
    /lib/modules/$KREL/kernel/sound/soc/qcom/qdsp6/ && sudo depmod -a && sudo reboot"
```

**A full kernel change on a new base** — install the whole apk, but keep the
working kernel bootable. Because every boot-critical driver is built **in** to
the image (`MMC_BLOCK`, `SDHCI_MSM`, `EXT4`, `F2FS` = `y`), the existing
initramfs boots any of these kernels, so a fallback is just a second set of boot
files and a second extlinux entry:

```sh
# on the device, before installing the new base:
cd /boot
sudo cp vmlinuz vmlinuz-fallback
sudo cp sdm632-fairphone-fp3.dtb sdm632-fairphone-fp3.dtb-fallback
# add a "postmarketOS-fallback" extlinux entry pointing at the -fallback files,
# keep "postmarketOS" (the current kernel) as default, then install the new apk.
# to test the new base, flip default to it and reboot; flip back when done.
```

⚠️ Take the DTB from the **built package**, not from your source tree — a stale
locally-built DTB is an easy way to spend an hour debugging a device tree that
was never deployed. The symptom is silent: the driver loads, the node it needs
simply is not there.

⚠️ The slot_b rootfs is 2.4 GB and normally sits around 90% full. At 100% the
graphical session does not come up at all, which looks like a kernel
regression and is not one — check `df -h /` before blaming the build.

## The config

`config-fp3.aarch64` is the postmarketOS `qcom-msm8953` config carried forward
to the current base. `prepare()` then turns on what that config misses:

| symbol | why |
|---|---|
| `CONFIG_SLIMBUS`, `CONFIG_SLIM_QCOM_NGD_CTRL`, `CONFIG_REGMAP_SLIMBUS` | the SLIMbus stack the codec lives on |
| `CONFIG_SND_SOC_WCD9335`, `CONFIG_SND_SOC_WCD_CLASSH` | the codec |
| `CONFIG_QCOM_BAM_DMA` | SLIMbus data path |
| `CONFIG_SND_SOC_AW8898` | speaker amplifier |
| `CONFIG_VIDEO_IMX363` | rear camera sensor |
| `CONFIG_DRM_PANEL_HIMAX_HX83112B` | the display panel |
| `CONFIG_CHARGER_QCOM_SMB2` | the PMI632 charger |

### The panel symbol is a trap worth knowing about

The panel driver was called `CONFIG_DRM_PANEL_FAIRPHONE_FP3_HX83112B` up to
6.13 and was renamed to `CONFIG_DRM_PANEL_HIMAX_HX83112B` afterwards. Carrying
a 6.13 config forward therefore leaves the panel driver **silently not built** —
`olddefconfig` drops the unknown symbol without a word, the build succeeds, and
the failure only shows up on the device as a compositor that loops on:

```
phoc-wlroots-CRITICAL: [backend/backend.c:245] Found 0 GPUs, cannot create backend
```

with no `/dev/dri` at all. A kernel bump can lose a feature without a single
build warning; **on every base bump, re-check that the symbols above still
exist** — this is exactly the kind of breakage step 5 of the rolling procedure
is there to catch.

## AI-assisted development

The WCD9335 SLIMbus audio work — playback, the digital microphones, the headset
(MBHC) jack detection and the voice-call routing — and the IMX363 and charger
work were developed with the assistance of
[Claude Code](https://www.anthropic.com/claude-code), Anthropic's generative-AI
coding agent. Every commit on this repository and on the `wip`/`integration`
branches records this in a `Co-authored-by: Claude` trailer; the `submit`
branches, which are meant for the kernel, instead carry the kernel's
`Assisted-by: Claude:<model>` trailer and **no** `Signed-off-by` from the AI.

Because of the AI assistance, **this code must not be submitted or upstreamed to
postmarketOS.** postmarketOS's
[AI policy](https://docs.postmarketos.org/policies-and-processes/development/ai-policy.html)
forbids the use of generative AI tools in the project — *"We forbid the use of
generative AI tools in postmarketOS"* — and specifically prohibits "submitting
contributions fully or in part created by generative AI tools". This repository
and the linked kernel branches are a personal fork for running mainline on the
Fairphone 3; they are deliberately kept out of the postmarketOS contribution
channels for this reason. The LKML, whose
[coding-assistants policy](https://www.kernel.org/doc/html/latest/process/coding-assistants.html)
allows disclosed AI assistance, is the one open upstream — which is what the
`submit/<base>/<category>` branches are for.

## Related

* <https://github.com/llg179/linux> — the kernel: `wip/<base>/<category>` (work
  plus bump fixes), `integration/<base>` (what the device runs), and
  `submit/<base>/<category>` (the minimal series for the LKML)
* <https://github.com/llg179/Claude-skills-Fairphone3> — the method: bring-up
  notes, ground-truth techniques, the guard-railed test loop, and the
  `msm8953-mainline-pr` skill for preparing a `submit` series

## License

GPL-2.0-only, matching the kernel it builds.
