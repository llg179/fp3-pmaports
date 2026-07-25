# fp3-pmaports

The postmarketOS package that builds the Fairphone 3 test kernel — mainline
`msm8953` with the WCD9335 SLIMbus audio work, the Sony IMX363 rear camera and
the PMI632 charger.

Without this, the [kernel branches](https://github.com/llg179/linux) are only
source: nothing records which config was used, which symbols had to be turned
on by hand, or how the thing was actually built.

## What it builds

`linux-fp3-709` — kernel 7.0.9, sources pinned to a commit on the
`fp3-integration` branch of <https://github.com/llg179/linux>. The package
carries **no patches of its own**: to move it forward, push to the branch and
update `_commit`, so the package and the branch cannot drift apart.

That branch is the union of four topic branches, each starting from the same
upstream base so that any one of them can be pointed at on its own — set
`_commit` to a commit on the branch you want:

| branch | what it adds |
|---|---|
| `fp3-7.0.9-audio` | WCD9335 over SLIMbus: playback, and the four built-in digital microphones |
| `fp3-7.0.9-camera` | the Sony IMX363 rear sensor |
| `fp3-7.0.9-charger` | the PMI632 charger, via `qcom_smbx` |
| `fp3-7.0.9-voice` | call audio, by routing the voice mixers over SLIMbus |

The audio series is the one written for submission; the camera commits are
still the working history and would need rewriting before they go anywhere.

Deployed states are tagged, so a snapshot stays reachable while the branch moves
on — e.g. `fp3-7.0.9-2026-07-24-camera+audio+charger` is what this package built
and what was verified on the device that day.

## Building

```sh
git clone https://github.com/llg179/fp3-pmaports
cp -r fp3-pmaports/linux-fp3-709 <your-pmaports>/device/testing/

pmbootstrap checksum linux-fp3-709      # only needed if you changed _commit
pmbootstrap build linux-fp3-709
```

The source tarball is ~250 MB straight from GitHub, so the first fetch takes a
minute or two. A warm ccache rebuild is around four minutes; a new `_commit`
means a new source directory and therefore a cold ccache, which is 20–35.

⚠️ **Push the branch before you bump `_commit`.** The package fetches the
tarball from GitHub, so a commit that only exists locally gives a 404 during
`pmbootstrap checksum`. If you skip the checksum step, the build fails one step
later with the far less helpful

```
ERROR: linux-fp3-709-<sha>.tar.gz is missing in checksums
```

which points at the checksums rather than at the missing push.

## Deploying

The built package lands in `~/.local/var/pmbootstrap/packages/edge/aarch64/`
(`$PMB_WORK/packages/...` if you moved the work dir). An apk is a gzipped tar,
so unpack it and take the pieces you need:

```sh
APK=~/.local/var/pmbootstrap/packages/edge/aarch64/linux-fp3-709-7.0.9-r2.apk
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

A full kernel change (vmlinuz, or a config change) means installing the whole
apk and reflashing boot — `pmbootstrap install` / `pmbootstrap flasher`.

⚠️ Take the DTB from the **built package**, not from your source tree — a stale
locally-built DTB is an easy way to spend an hour debugging a device tree that
was never deployed. The symptom is silent: the driver loads, the node it needs
simply is not there.

⚠️ The slot_b rootfs is 2.4 GB and normally sits around 93% full. At 100% the
graphical session does not come up at all, which looks like a kernel
regression and is not one — check `df -h /` before blaming the build.

## The config

`config-fp3-709.aarch64` is the postmarketOS `qcom-msm8953` config carried
forward to 7.0.9. `prepare()` then turns on what that config misses:

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
a 6.13 config forward to 7.x therefore leaves the panel driver **silently not
built** — `olddefconfig` drops the unknown symbol without a word, the build
succeeds, and the failure only shows up on the device as a compositor that
loops on:

```
phoc-wlroots-CRITICAL: [backend/backend.c:245] Found 0 GPUs, cannot create backend
```

with no `/dev/dri` at all. A kernel bump can lose a feature without a single
build warning; check that the symbols you rely on still exist.

## AI-assisted development

The WCD9335 SLIMbus audio work — playback, the digital microphones, the headset
(MBHC) jack detection and the voice-call routing — was developed with the
assistance of [Claude Code](https://www.anthropic.com/claude-code), Anthropic's
generative-AI coding agent. Every commit records this in a `Co-authored-by:
Claude` trailer.

Because of that, **this code must not be submitted or upstreamed to
postmarketOS.** postmarketOS's
[AI policy](https://docs.postmarketos.org/policies-and-processes/development/ai-policy.html)
forbids the use of generative AI tools in the project — *"We forbid the use of
generative AI tools in postmarketOS"* — and specifically prohibits "submitting
contributions fully or in part created by generative AI tools". This repository
and the linked kernel branches are a personal fork for running mainline on the
Fairphone 3; they are deliberately kept out of the postmarketOS contribution
channels for this reason.

## Related

* <https://github.com/llg179/linux> — the kernel: the four topic branches
  above, each on the same upstream base, `fp3-integration` (everything that
  runs on the device), plus a tag per deployed snapshot
* <https://github.com/llg179/Claude-skills-Fairphone3> — the method: bring-up
  notes, ground-truth techniques, and the guard-railed test loop

## License

GPL-2.0-only, matching the kernel it builds.
