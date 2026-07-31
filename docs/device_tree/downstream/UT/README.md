# Ubuntu Touch downstream device tree (Halium, kernel 4.9)

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

| | |
|---|---|
| `fp3-ubuntu-touch-live.dts` | the tree **as it runs** — complete and fully resolved, dumped off the live device |
| [`kernel-dt/`](kernel-dt/) | the **sources** it was built from: the [UBports FP3 kernel](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632)'s device tree |

The two agree exactly: compiling `sdm632-mtp-s3.dts` from `kernel-dt/` gives the
live tree node for node, with only the nine properties the bootloader fills in
left over ([comparison](../README.md)).

This is where the *values* in our mainline nodes come from — the addresses, GPIO
numbers, regulator names and clock wiring for the WCD9335 SLIMbus codec, the
camera and the PMI632 charger. Note that this concerns only the nodes we **add**,
i.e. the `before_update` → `after_update` delta; `../../before_update/` itself is
plain upstream mainline and owes nothing to this tree. Where the downstream
binding disagrees with the mainline one, the mainline shape wins — see the
top-level [`README.md`](../../../../README.md).

For the same tree as the vendor publishes it see
[`../fairphone/`](../fairphone/), and for how closely the two agree,
[`../README.md`](../README.md).

## Why keep the dump at all

The [Ubuntu Touch kernel tree](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632)
(`lineageos_FP3_defconfig`, 4.9.218) contains **no FP3 board `.dts`** — nothing
under `arch/arm64/boot/dts/qcom/` matches `fp3` or `fairphone`. The phone is
Qualcomm's `sdm632-mtp-s3` reference board there, and
which blob the bootloader ends up handing the kernel (`androidboot.dtb_idx=14
androidboot.dtbo_idx=14` on the command line) is not something the sources tell
you. So the only complete and authoritative form of the FP3 downstream tree is
what the running kernel unflattened. Which sources it does correspond to is
answered in [`../README.md`](../README.md) — measured, not assumed.

Identifying marks in the tree, which is otherwise generic:

```
model          = "MTP S3"
compatible     = "qcom,sdm450"
qcom,msm-id    = <0x15d 0x00>     /* 349 = SDM632 */
qcom,pmic-name = "PMI632"
```

`MTP S3` is Qualcomm reference-board naming that Fairphone kept. Do not trust the
`compatible` string: it says `sdm450`, but `qcom,msm-id` 349 is **SDM632**, and
the tree matches Fairphone's `sdm632-mtp-s3.dts` — see the comparison one level
up.

## How it was produced

From the host, with the device booted into Ubuntu Touch:

```sh
ut-ssh 'tar -C /sys/firmware/devicetree -czhf - base | base64 -w0' | base64 -d > dt.tgz
tar -xzf dt.tgz                       # -h matters: /proc/device-tree is a symlink
dtc -I fs -O dts -o fp3-ubuntu-touch-live.dts base
```

`dtc` is not on the device — build it from any kernel checkout (`scripts/dtc`,
`bison`+`flex`, `-DNO_YAML`) or install `device-tree-compiler`.

The flat blob at `/sys/firmware/fdt` is `0400 root`, but `phablet` can `sudo`
with the device password (the same one as the postmarketOS side), so it can be
fetched directly as well:

```sh
ut-ssh 'echo <password> | sudo -S cat /sys/firmware/fdt | base64 -w0' | base64 -d > fdt.dtb
dtc -I dtb -O dts -s fdt.dtb
```

Both routes were run and cross-checked: the sorted `dts` of the flat blob and of
the `-I fs` tree are **byte-identical** (15 899 lines, zero diff), so the file
here is the real flattened tree and not an approximation of it.

Kernel it was taken from: `4.9.218-perf-ubuntutouch+`, slot `_a`.

## One deliberate edit

The three `androidboot.*serialno=` values in `/chosen/bootargs` are replaced with
`REDACTED`. They identify one physical handset and have no technical bearing on
the device tree. Everything else — including the verity hashes and PARTUUIDs,
which are per-build rather than per-device — is verbatim. Re-run the commands
above if you need the unedited tree.
