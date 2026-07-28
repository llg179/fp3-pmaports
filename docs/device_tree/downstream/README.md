# Downstream device trees

The 4.9 vendor device tree in two forms — as it **runs** and as it is
**published** — because neither alone is sufficient: the running tree is
authoritative but has no names or comments, and the sources are readable but do
not tell you which of the 938 files the phone actually uses.

| directory | what it is |
|---|---|
| [`UT/`](UT/) | the live tree dumped off the phone booted into Ubuntu Touch (kernel 4.9.218) — flattened, fully resolved, bootloader edits included |
| [`FP3/3.A.0136/`](FP3/3.A.0136/) | the vendor sources from Fairphone's official GPL release for Fairphone OS 3.A.0136 |

Both describe the *downstream* hardware view. They are the origin of the values
in the nodes we **add** in `../before_update` → `../after_update`; the
`before_update` files themselves are plain upstream mainline and have no
relationship to anything here.

## UT ⇄ FP3: how much do they differ?

**They are the same tree.** Compiling the vendor sources and comparing the result
against the live dump leaves five nodes with differing properties and one extra
node on each side — out of 1804 nodes.

### Which vendor file is the FP3

Not obvious, and easy to get wrong. The live tree says `compatible =
"qcom,sdm450"`, but `qcom,msm-id = <0x15d>` is **349 = SDM632**, and only
`sdm632.dtsi` pulls in `sdm632-coresight.dtsi` — which is what makes the live
ETM unit addresses (`etm@61b3000`…) differ from the SDM450 ones
(`etm@61bc000`…). The match is:

```
arch/arm64/boot/dts/qcom/sdm632-mtp-s3.dts
  ├── sdm632.dtsi                    → msm8953.dtsi + sdm632 CPU/regulator/coresight
  ├── sdm450-pmi632.dtsi             → the PMI632 side (and the "qcom,sdm450" compatible)
  └── sdm450-pmi632-mtp-s3.dtsi      → the board itself (model = "MTP S3")
```

Taking the `sdm450-pmi632.dts` + `sdm450-mtp-s3-overlay.dtbo` pair instead — the
obvious reading of the `Makefile` — gives a tree that differs in 167/190 nodes.
It is the wrong SoC.

### The comparison

```sh
# vendor: sources → dtb → canonical dts
cpp -nostdinc -I../include -I. -undef -x assembler-with-cpp sdm632-mtp-s3.dts \
	| dtc -I dts -O dtb -o v632.dtb
dtc -I dtb -O dts -s -o v632.dts v632.dtb

# live: the phone's flat blob → canonical dts
dtc -I dtb -O dts -s -o live.dts fdt.dtb
```

A plain `diff` of the two is useless — phandle numbering differs between builds,
so nearly every `clocks`, `iommus`, `pinctrl-0` or `remote-endpoint` looks
changed. Compare structurally instead: match nodes by path, and treat two cells
as equal when both are phandles resolving to the same node path. On that basis:

| | |
|---|---|
| nodes | **1804 live / 1804 vendor**, 1803 in common |
| only live | `/reserved-memory/ramoops_mem@0` |
| only vendor | `/firmware/android/fstab/product` |
| nodes with differing properties | **5** (11 properties total) |

### Every difference, and why

| node | property | live | vendor | why |
|---|---|---|---|---|
| `/` | `model` | `MTP S3` | `Qualcomm Technologies, Inc. SDM632 + PMI632 MTP S3` | bootloader/dtbo rewrite |
| `/` | `compatible` | `qcom,sdm450` | `qcom,sdm632-mtp`, `qcom,sdm632`, `qcom,mtp` | ditto |
| `/` | `qcom,board-id` | absent | `<0x08 0x03>` | consumed by the bootloader when it selects the dtb |
| `/` | `qcom,pmic-name` | `PMI632` | absent | added by the bootloader |
| `/chosen` | `bootargs` | the full 1.5 kB Android command line | `kpti=0` | filled in at boot |
| `/chosen` | `kaslr-seed`, `linux,initrd-start`, `linux,initrd-end` | present | absent | filled in at boot |
| `/memory` | `reg` | `<0 0x10000000 0 0x70000000  0 0x80000000 0 0x80000000>` (4 GB) | `<0 0 0 0>` | filled in at boot |
| `/reserved-memory/mem_dump_region` | `size` | `<0x00 0x400000>` | `<0x400000>` | 2-cell vs 1-cell encoding of the same value |
| `/firmware/android/vbmeta` | `parts` | `vbmeta,boot,system,vendor,dtbo` | …`,product` | see below |
| `/reserved-memory/ramoops_mem@0` | (whole node) | present | — | pstore/ramoops, added downstream of the vendor sources |

Everything above the last two rows is the bootloader populating the tree it was
handed, i.e. not a difference in the description at all. That leaves exactly two
real ones:

* **`product` partition** — 3.A.0136 declares a `product` partition in
  `/firmware/android/fstab` and lists it in `vbmeta parts`; the tree running on
  this phone does not. The blob in the device's `dtb`/`dtbo` partition therefore
  is **not** the 3.A.0136 build — the firmware slot is on an earlier release.
* **`ramoops_mem@0`** — a pstore/ramoops carve-out that the published vendor
  sources do not contain.

So: the FP3 downstream device tree has been stable across releases, the vendor
sources describe the running hardware faithfully, and the two artefacts here can
be used interchangeably for looking up register addresses, GPIOs and supply
names — as long as you read the *values* from the live dump when they matter,
since it is the one that was really loaded.
