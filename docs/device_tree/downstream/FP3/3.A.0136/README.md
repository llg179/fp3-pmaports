# Fairphone 3 vendor device tree — Fairphone OS 3.A.0136

The device-tree sources as Fairphone publishes them, unmodified, from the
official GPL release for **3.A.0136** (the last Fairphone OS build for the FP3,
Android 10 / "Q", kernel 4.9).

## Source

Downloaded from Fairphone's GPL page:
<https://code.fairphone.com/projects/fairphone-3/gpl.html>

| what | file | sha256 |
|---|---|---|
| kernel sources (this snapshot came from here) | [`FP3-REL-Q-3.A.0136-gms-7c69ec7e-kernel_source.txz`](https://storage.googleapis.com/fairphone-source/FP3/FP3-REL-Q-3.A.0136-gms-7c69ec7e-kernel_source.txz) | `90f65fc0c4d0d9add5352a4c9406f38491c6489a871bc66e0c1615396efc029d` |
| audio kernel (techpack, no DT) | [`…-audio-kernel_source.txz`](https://storage.googleapis.com/fairphone-source/FP3/FP3-REL-Q-3.A.0136-gms-7c69ec7e-audio-kernel_source.txz) | — |
| other GPL sources (Android userspace, no DT) | [`…-gpl_source.tgz`](https://storage.googleapis.com/fairphone-source/FP3/FP3-REL-Q-3.A.0136-gms-7c69ec7e-gpl_source.tgz) | `df9827464b81fcd813169847f21b0f45f3682a2788d90d5ec0f9df5c081999c4` |

The `gpl_source.tgz` contains no device tree at all — only `external/dtc`'s own
test fixtures match `*.dts`. The kernel `.txz` is the one that matters.

Licence: GPL-2.0, as the kernel it is part of.

## What is here

Paths mirror the kernel tree they were taken from, so a file can be found by its
upstream path:

| path | contents |
|---|---|
| `arch/arm64/boot/dts/qcom/` | the complete qcom device tree of the release — 938 files, every `.dts`/`.dtsi` and the `Makefile` rules that pair base dtbs with overlays |
| `arch/arm64/boot/dts/Makefile` | the arm64 dts Makefile |
| `include/dt-bindings/` | the binding headers the tree `#include`s, so the snapshot is self-contained |

Only the other SoC vendors' directories (`nvidia/`, `rockchip/`, …) were left
out — they are unrelated to this device.

One deviation from the tarball: `include/dt-bindings/input/linux-event-codes.h`
is a symlink to `include/uapi/linux/input-event-codes.h` in the kernel tree, and
is stored here as a regular file with that content, so the snapshot does not
point outside itself.

## Where the FP3 actually is in this tree

Fairphone did not add a board file named after the phone — the FP3 ships as
Qualcomm's **MTP S3** reference-board description, on the SDM632 base:

```
arch/arm64/boot/dts/qcom/sdm632-mtp-s3.dts
  ├── sdm632.dtsi                → msm8953.dtsi + sdm632 CPU / regulator / coresight
  ├── sdm450-pmi632.dtsi         → the PMI632 side (and the "qcom,sdm450" compatible)
  └── sdm450-pmi632-mtp-s3.dtsi  → the board itself, model = "MTP S3"
```

Compiling that file reproduces the tree the phone actually runs, node for node —
see the comparison in [`../../README.md`](../../README.md).

Beware the near-miss: the tree also contains `sdm450-mtp-s3-overlay.dts` with the
same `model = "MTP S3"`, which the `Makefile` pairs with `sdm450-pmi632.dtb`.
That is the SDM450 variant of the same board and it is **not** this phone — it
differs from the live tree in 167/190 nodes. The discriminator is
`qcom,msm-id`: the live tree reports `<0x15d>` = 349 = SDM632, not 338 = SDM450.
The `compatible = "qcom,sdm450"` string in the running tree is misleading; it
comes from the shared `sdm450-pmi632.dtsi`.

The files our mainline work was derived from:

| file | what we took from it |
|---|---|
| `msm8953.dtsi` | SLIMbus/BAM addresses (`c104000`, `c140000`), LPASS wiring |
| `msm8953-audio.dtsi`, `msm-audio-lpass.dtsi` | the WCD9335 ("tasha") codec and DAI-link description |
| `msm8953-ext-codec-mtp.dts` | the external-codec board variant |
| `msm8953-pinctrl.dtsi` | the codec pin muxes (`cdc_reset`, `wcd_intr`, MCLK) |
| `msm8953-camera-sensor-mtp.dtsi` | camera regulators, CCI wiring, sensor power sequences |
| `pmi632.dtsi`, `qg-batterydata-Fuji-3000mah-Jan22th2019-pmi632.dtsi` | charger and battery profile |

Note the downstream binding names (`qcom,tasha-slim-pgd` and friends) are **not**
what our mainline nodes use — we follow the mainline WCD9335 shape and take only
the *values* from here. See the top-level [`README.md`](../../../../../README.md).

## Verifying / rebuilding this snapshot

```sh
curl -O https://storage.googleapis.com/fairphone-source/FP3/FP3-REL-Q-3.A.0136-gms-7c69ec7e-kernel_source.txz
sha256sum FP3-REL-Q-3.A.0136-gms-7c69ec7e-kernel_source.txz   # see table above
tar -xJf FP3-REL-Q-3.A.0136-gms-7c69ec7e-kernel_source.txz ./arch/arm64/boot/dts ./include/dt-bindings
```

The snapshot is complete enough to compile on its own — from
`arch/arm64/boot/dts/qcom/`:

```sh
cpp -nostdinc -I../../../../../include -I. -undef -x assembler-with-cpp sdm632-mtp-s3.dts \
	| dtc -I dts -O dtb -o /tmp/sdm632-mtp-s3.dtb
```

which produces a 353 KB dtb with warnings only (the usual downstream
`unit address format` complaints), no errors.
