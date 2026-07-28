# Ubuntu Touch kernel device tree (sources)

The device-tree sources of the kernel the phone actually boots under Ubuntu
Touch — the counterpart of the live dump one level up.

**This is the tree that matches the device.** Compiling `sdm632-mtp-s3.dts` from
here and comparing against the live blob gives **zero** node differences (1804
nodes each) and only the nine properties the bootloader fills in. See
[`../../README.md`](../../README.md) for the comparison and the method.

## Source

<https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632.git>,
branch `ubuntutouch`, at the state cloned for this port:

| | |
|---|---|
| DT comes from | `12d9b944cd41fd5399b833f0d5fc1e2c083020ba` (Lukas, 2023-11-30) — the branch tip when the shallow clone was made |
| local HEAD | `f81cdb87f418621f0df0f4a0aa8a5c65bfa29bb2`, our SLIMbus-framer debug commit on top; it does **not** touch the device tree |
| kernel | 4.9.218, `lineageos_FP3_defconfig` (LineageOS-derived, Android 10 era) |

Licence: GPL-2.0, as the kernel it is part of.

⚠️ Re-fetching `origin/ubuntutouch` today yields `6d508b49` (2021-08-05), whose
device tree is **older and does not match this device** — it compares like the
Android 9 Fairphone tree (7 extra nodes live, 25 nodes with property differences:
`tas2557` amplifier, `sar_sensor`, different ADSP nodes). If you re-clone, check
against the live dump before trusting it.

### `ubuntutouch` vs `master` in that repo

`master` is the untouched vendor import — `33e4fcc0f` *"Import
FP3-REL-2.A.0110-20200109.202458"* (Luca Weiss, 2020-02-20), i.e. Fairphone's
Android 9 sources. `ubuntutouch` is the porting branch on top of it.

For the whole `arch/arm64/boot/dts` tree, 13 files differ — but five of them
(both `dsi-hx83112b-*` panel files and the three `qg-batterydata-*` profiles)
are **whitespace-only**: `git diff -w` reports no change at all. The rest is:

| file | change |
|---|---|
| `msm8953.dtsi` | the `product` partition dropped — removed from `vbmeta parts` and the `fstab` node deleted |
| `pmi632.dtsi` | +50 lines of notification-LED tuning (`qcom,lut-patterns`, ramp step/pause/high-index on the three `lpg@` channels) |
| `msm8953-ext-codec-mtp.dts`, `sdm632-ext-audio-mtp.dtsi` | `&cdc_us_euro_sw` commented out |
| `apq8053-lat-concam.dtsi`, `apq8053-lite-dragon*.dts*`, `sdm632-rumi.dtsi` | `&spi_3` / `&blsp*_uart*` / `&blsp1_serial1` commented out — other boards, irrelevant here |

Built as this device's dtb (`sdm632-mtp-s3.dts`), only the first two reach it:
1799 nodes on `master` vs 1798 on `ubuntutouch`, the one node being
`/firmware/android/fstab/product`, plus 14 properties — `vbmeta parts` and the
LED ramp values. Note that the board file the FP3 is described by,
`sdm450-pmi632-mtp-s3.dtsi`, is **byte-identical** on the two branches.

Neither branch state matches the running device, though: `ramoops_mem` is absent
from both `master` and today's `ubuntutouch` tip, and present in the 2023 state
snapshotted here — which is the one the live dump agrees with.

## What is here

Same layout as Fairphone's snapshot, mirroring the kernel paths:

| path | contents |
|---|---|
| `arch/arm64/boot/dts/qcom/` | the complete qcom device tree — 938 files |
| `arch/arm64/boot/dts/Makefile` | the arm64 dts Makefile |
| `include/dt-bindings/` | the binding headers, so the snapshot is self-contained |

As in Fairphone's snapshot, `include/dt-bindings/input/linux-event-codes.h` is a
symlink in the kernel tree and is stored here as a regular file.

## How it differs from Fairphone's own sources

Two edits, both in `arch/arm64/boot/dts/qcom/msm8953.dtsi`, and both visible in
the running device:

```
ramoops_mem: ramoops_mem@0 { compatible = "ramoops"; … }   /* added */
//[TracyChui] Add product image and mount partition        /* Fairphone's block, commented out */
```

Everything else in the FP3's include chain is Fairphone's Android 10 tree — see
[`../../fairphone/3.A.0136/`](../../fairphone/3.A.0136/).

## Building it

From `arch/arm64/boot/dts/qcom/`:

```sh
cpp -nostdinc -I../../../../../include -I. -undef -x assembler-with-cpp sdm632-mtp-s3.dts \
	| dtc -I dts -O dtb -o /tmp/sdm632-mtp-s3.dtb
```

298 KB, warnings only.
