# Downstream device trees

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The 4.9 downstream device tree in two forms. "Downstream" here is the
Android-era tree the device shipped with, as opposed to the mainline one we
work on; the **vendor is Fairphone** (fairphone.com), who make this phone — the
FP3 being the third model in their FP1…FP5 line.

| | |
|---|---|
| [`UT/`](UT/) | as it **runs** — dumped off the phone booted into Ubuntu Touch |
| [`UT/kernel-dt/`](UT/kernel-dt/) | the **sources** that dump was built from — the [UBports FP3 kernel](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632)'s device tree |
| [`fairphone/3.A.0136/`](fairphone/3.A.0136/) | as the vendor **publishes** it — Fairphone's GPL sources for Fairphone OS 3.A.0136 |

Both are only reference material: they are where the *values* in the nodes we
**add** come from (addresses, GPIOs, supply and clock names). The
`../before_update/` files are plain upstream mainline and have nothing to do
with them.

## Are the two the same tree?

Yes. Out of **1804 nodes**, exactly two differ, and neither is a version
difference:

| difference | which side | what it is |
|---|---|---|
| `/reserved-memory/ramoops_mem@0` | only live | pstore/ramoops crash log buffer |
| `/firmware/android/fstab/product` (+ `product` in `vbmeta parts`) | only Fairphone | the `product` partition |

Nine more properties differ, all of them written by the bootloader into the tree
it was handed: `/chosen` (`bootargs`, `kaslr-seed`, initrd range), `/memory`
(`reg` — the real 4 GB), and on `/` the `model` / `compatible` /
`qcom,board-id` / `qcom,pmic-name` rewrite. Nothing that describes hardware.

## Which Fairphone release is the running tree closest to?

The question: the phone boots Ubuntu Touch from slot `_a`, and its device tree
can be dumped live. Fairphone publishes the sources of every Fairphone OS build
at <https://code.fairphone.com/projects/fairphone-3/gpl.html> — 3.A.0136 down to
2.A.0101. **Which of those releases does the dumped tree match?**

Answer: **all the Android 10 ones equally well, and none of them exactly.** Four
releases spanning the range were compiled and compared against the live dump:

| tree compiled and compared against the live dump | extra nodes (live + other side) | properties differing |
|---|---|---|
| Fairphone 3.A.0136 — newest | 1 + 1 | 5 nodes / 11 props |
| Fairphone 3.A.0107 — mid Android 10 | 1 + 1 | identical |
| Fairphone 3.A.0033 — oldest Android 10 | 1 + 1 | identical |
| Fairphone 2.A.0118 — newest Android 9 | 7 + 2 | 26 nodes / 40 props |
| **Ubuntu Touch's own kernel** ([`UT/kernel-dt/`](UT/kernel-dt/)) | **0 + 0** | **3 nodes / 9 props — bootloader only** |

Two things follow. First, **the residual difference does not date the tree**:
every Android 10 release, three years apart, produces the *same* delta, so it
cannot be used to pick one. (Going back to Android 9 does change the picture,
for the worse — a `tas2557` amplifier, no `sar_sensor`, different ADSP nodes.)

Second, the tree the phone runs is not a Fairphone release at all: it is the
**DTB built into the [Ubuntu Touch kernel](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632)**,
which matches perfectly. Its sources show the two edits exactly:

```
arch/arm64/boot/dts/qcom/msm8953.dtsi
	ramoops_mem: ramoops_mem@0 { compatible = "ramoops"; … }   ← added by the UT port
	//[TracyChui] Add product image and mount partition        ← Fairphone's block, disabled
```

So: Ubuntu Touch carries Fairphone's **Android 10** tree with those two changes.
Within Android 10 the sources are identical as far as this device is concerned,
which is why no single release stands out — and 3.A.0136, the newest, is
therefore the right one to keep here as the reference.

## Which `.dts` file inside Fairphone's sources describes the FP3

A different question from the one above: not *which release*, but *which file*
in the ~938-file `arch/arm64/boot/dts/qcom/` directory of any given release.

Not obvious. The live tree says `compatible = "qcom,sdm450"`, but `qcom,msm-id =
<0x15d>` is **349 = SDM632**. The match is `sdm632-mtp-s3.dts`:

```
sdm632-mtp-s3.dts
	├── sdm632.dtsi                → msm8953.dtsi + SDM632 CPU/regulator/coresight
	├── sdm450-pmi632.dtsi         → the PMI632 side (and that "qcom,sdm450" string)
	└── sdm450-pmi632-mtp-s3.dtsi  → the board, model = "MTP S3"
```

The near-miss to avoid is `sdm450-mtp-s3-overlay.dts` — same `model = "MTP S3"`,
paired by the `Makefile` with `sdm450-pmi632.dtb`, but it is the SDM450 variant
and differs from the live tree in 167/190 nodes.

## Reproducing the comparison

```sh
# Fairphone's sources → dtb → canonical dts
cpp -nostdinc -I../include -I. -undef -x assembler-with-cpp sdm632-mtp-s3.dts \
	| dtc -I dts -O dtb -o v.dtb
dtc -I dtb -O dts -s -o fairphone.dts v.dtb

# the phone's flat blob → canonical dts
dtc -I dtb -O dts -s -o live.dts fdt.dtb
```

Do **not** `diff` those two directly: phandle numbering differs per build, so
almost every `clocks`, `iommus`, `pinctrl-0` and `remote-endpoint` looks changed
(352 nodes of noise). Compare structurally — match nodes by path, and treat two
cells as equal when both are phandles resolving to the same node path.
