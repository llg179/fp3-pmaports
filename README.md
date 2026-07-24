# fp3-pmaports

The postmarketOS package that builds the Fairphone 3 test kernel — mainline
`msm8953` with the WCD9335 SLIMbus audio work and the Sony IMX363 rear camera.

Without this, the [kernel branches](https://github.com/llg179/linux) are only
source: nothing records which config was used, which symbols had to be turned
on by hand, or how the thing was actually built.

## What it builds

`linux-fp3-709` — kernel 7.0.9, sources pinned to a commit on the
`fp3-integration` branch of <https://github.com/llg179/linux>. The package
carries **no patches of its own**: to move it forward, push to the branch and
update `_commit`, so the package and the branch cannot drift apart.

That branch is `fp3-7.0.9-audio` (the audio series) plus nine IMX363 commits. If
you want audio without the camera, point `_commit` at `fp3-7.0.9-audio` instead.

Deployed states are tagged, so a snapshot stays reachable while the branch moves
on — e.g. `fp3-7.0.9-2026-07-24-camera+audio` is what this package built and what
was verified on the device that day.

## Building

```sh
git clone https://github.com/llg179/fp3-pmaports
cp -r fp3-pmaports/linux-fp3-709 <your-pmaports>/device/testing/

pmbootstrap checksum linux-fp3-709      # only needed if you changed _commit
pmbootstrap build linux-fp3-709
```

The source tarball is ~250 MB straight from GitHub, so the first fetch takes a
minute or two. A warm ccache rebuild is around four minutes.

Deploying: for a driver-only change, copy the `.ko` out of the built apk and
`depmod -a`; for a device-tree change, copy `boot/dtbs/qcom/sdm632-fairphone-fp3.dtb`
to `/boot` — extlinux loads the fdt separately, so no kernel flash is needed.

⚠️ Take the DTB from the **built package**, not from your source tree — a stale
locally-built DTB is an easy way to spend an hour debugging a device tree that
was never deployed.

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

## Related

* <https://github.com/llg179/linux> — the kernel: `fp3-7.0.9-audio` (the
  submittable audio series), `fp3-integration` (everything that runs on the
  device), plus a tag per deployed snapshot
* <https://github.com/llg179/Claude-skills-Fairphone3> — the method: bring-up
  notes, ground-truth techniques, and the guard-railed test loop

## License

GPL-2.0-only, matching the kernel it builds.
