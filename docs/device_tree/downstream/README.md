# Downstream device trees

The 4.9 vendor device tree in two forms:

| | |
|---|---|
| [`UT/`](UT/) | as it **runs** — dumped off the phone booted into Ubuntu Touch |
| [`FP3/3.A.0136/`](FP3/3.A.0136/) | as Fairphone **publishes** it — the GPL sources for Fairphone OS 3.A.0136 |

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
| `/firmware/android/fstab/product` (+ `product` in `vbmeta parts`) | only vendor | the `product` partition |

Nine more properties differ, all of them written by the bootloader into the tree
it was handed: `/chosen` (`bootargs`, `kaslr-seed`, initrd range), `/memory`
(`reg` — the real 4 GB), and on `/` the `model` / `compatible` /
`qcom,board-id` / `qcom,pmic-name` rewrite. Nothing that describes hardware.

## Which Fairphone release does the running tree correspond to?

**None of them — and not because it is old.** The two differences above come from
Ubuntu Touch, not from an older Fairphone build:

| tree compared against the live dump | node mismatches | property mismatches |
|---|---|---|
| Fairphone 3.A.0136 (newest) | 1 + 1 | 5 nodes / 11 props |
| Fairphone 3.A.0107 (mid) | 1 + 1 | identical |
| Fairphone 3.A.0033 (oldest Android 10) | 1 + 1 | identical |
| Fairphone 2.A.0118 (newest Android 9) | 7 + 2 | 26 nodes / 40 props |
| **Ubuntu Touch's own kernel** | **0 + 0** | **3 nodes / 9 props — bootloader only** |

Every Android 10 release gives the *same* delta, so the delta does not date the
tree; going back to Android 9 makes it worse (it moves the audio amplifier to a
`tas2557`, drops `sar_sensor`, changes the ADSP nodes). The perfect match is the
Ubuntu Touch kernel itself, and its sources say why:

```
arch/arm64/boot/dts/qcom/msm8953.dtsi
	ramoops_mem: ramoops_mem@0 { compatible = "ramoops"; … }   ← added by LineageOS/UT
	//[TracyChui] Add product image and mount partition        ← Fairphone's block, commented out
```

So the phone boots the **DTB appended to the Ubuntu Touch kernel**, which is
Fairphone's Android 10 tree with those two edits — not the blob in the device's
`dtbo` partition, and not any stock release verbatim.

## Which vendor file is the FP3

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
# vendor sources → dtb → canonical dts
cpp -nostdinc -I../include -I. -undef -x assembler-with-cpp sdm632-mtp-s3.dts \
	| dtc -I dts -O dtb -o v.dtb
dtc -I dtb -O dts -s -o vendor.dts v.dtb

# the phone's flat blob → canonical dts
dtc -I dtb -O dts -s -o live.dts fdt.dtb
```

Do **not** `diff` those two directly: phandle numbering differs per build, so
almost every `clocks`, `iommus`, `pinctrl-0` and `remote-endpoint` looks changed
(352 nodes of noise). Compare structurally — match nodes by path, and treat two
cells as equal when both are phandles resolving to the same node path.
