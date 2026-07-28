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
Android 9 vendor tree (7 extra nodes live, 25 nodes with property differences:
`tas2557` amplifier, `sar_sensor`, different ADSP nodes). If you re-clone, check
against the live dump before trusting it.

## What is here

Same layout as the vendor snapshot, mirroring the kernel paths:

| path | contents |
|---|---|
| `arch/arm64/boot/dts/qcom/` | the complete qcom device tree — 938 files |
| `arch/arm64/boot/dts/Makefile` | the arm64 dts Makefile |
| `include/dt-bindings/` | the binding headers, so the snapshot is self-contained |

As in the vendor snapshot, `include/dt-bindings/input/linux-event-codes.h` is a
symlink in the kernel tree and is stored here as a regular file.

## How it differs from Fairphone's own sources

Two edits, both in `arch/arm64/boot/dts/qcom/msm8953.dtsi`, and both visible in
the running device:

```
ramoops_mem: ramoops_mem@0 { compatible = "ramoops"; … }   /* added */
//[TracyChui] Add product image and mount partition        /* Fairphone's block, commented out */
```

Everything else in the FP3's include chain is Fairphone's Android 10 tree — see
[`../../FP3/3.A.0136/`](../../FP3/3.A.0136/).

## Building it

From `arch/arm64/boot/dts/qcom/`:

```sh
cpp -nostdinc -I../../../../../include -I. -undef -x assembler-with-cpp sdm632-mtp-s3.dts \
	| dtc -I dts -O dtb -o /tmp/sdm632-mtp-s3.dtb
```

298 KB, warnings only.
