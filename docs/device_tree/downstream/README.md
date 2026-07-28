# Downstream device tree (Ubuntu Touch / Halium, kernel 4.9)

`fp3-ubuntu-touch-live.dts` is the **complete, fully resolved** device tree the
Fairphone 3 actually runs under Ubuntu Touch — dumped from the live device, not
reconstructed from sources.

It is the reference the mainline nodes in `../before_update` → `../after_update`
were derived from: addresses, GPIO numbers, regulator names and clock wiring for
the WCD9335 SLIMbus codec, the camera, and the PMI632 charger all come from here.
Where the mainline binding differs from the downstream one, the mainline shape
wins (see the top-level [`README.md`](../../../README.md)); this file is the
ground truth for the *values*.

## Why a dump and not the kernel sources

The Ubuntu Touch kernel tree (`lineageos_FP3_defconfig`, 4.9.218) contains **no
FP3 board `.dts`** — nothing under `arch/arm64/boot/dts/qcom/` matches `fp3` or
`fairphone`. The board description ships as a prebuilt blob in the `dtbo`
partition and is picked at boot by index (`androidboot.dtb_idx=14
androidboot.dtbo_idx=14` on the kernel command line), so the only complete and
authoritative form of the FP3 downstream tree is what the running kernel
unflattened. Hence the dump. For the *upstream vendor* sources of the same
platform see [`../fp3/`](../fp3/).

Identifying marks in the tree, which is otherwise generic:

```
model         = "MTP S3"
compatible    = "qcom,sdm450"
qcom,pmic-name = "PMI632"
```

`MTP S3` is Fairphone reusing Qualcomm's reference-board naming; the PMI632 and
the `mdss_dsi_djn_hx83112b_1080p_cmd` panel in `/chosen/bootargs` are what pin
it to the FP3.

## How it was produced

From the host, with the device booted into Ubuntu Touch:

```sh
ut-ssh 'tar -C /sys/firmware/devicetree -czhf - base | base64 -w0' | base64 -d > dt.tgz
tar -xzf dt.tgz                       # -h/-czhf matters: /proc/device-tree is a symlink
dtc -I fs -O dts -o fp3-ubuntu-touch-live.dts base
```

`/sys/firmware/fdt` would be the flat blob, but it is `0400 root` and the
`phablet` account cannot `sudo` non-interactively; the `-I fs` route needs no
privileges and yields the same tree. `dtc` is not on the device — build it from
any kernel checkout (`scripts/dtc`, `bison`+`flex`, `-DNO_YAML`) or install
`device-tree-compiler`.

Kernel it was taken from: `4.9.218-perf-ubuntutouch+`, slot `_a`.

## One deliberate edit

The three `androidboot.*serialno=` values in `/chosen/bootargs` are replaced with
`REDACTED`. They identify one physical handset and have no technical bearing on
the device tree. Everything else — including the verity hashes and PARTUUIDs,
which are per-build rather than per-device — is verbatim. Re-run the commands
above if you need the unedited tree.
