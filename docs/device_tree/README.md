# Device tree

| directory | what it holds |
|---|---|
| `before_update/` | the **upstream mainline** files exactly as the base ships them — what we had to touch |
| `after_update/` | the same files on `integration/<base>`, with our changes applied |
| `downstream/UT/` | the **live** device tree dumped off the phone running Ubuntu Touch (kernel 4.9) — the resolved tree, ground truth for values, plus in `kernel-dt/` the sources it was built from |
| `downstream/fairphone/3.A.0136/` | the sources published by the **vendor, Fairphone**, from their official GPL release of Fairphone OS 3.A.0136 — <https://code.fairphone.com/projects/fairphone-3/gpl.html> |

The first two are the change itself. Those under `downstream/` are where the
content of the nodes we **add** came from — they have nothing to do with
`before_update/`, which is plain upstream mainline. Each directory has its own
README; [`downstream/README.md`](downstream/README.md) also compares the live
tree against Fairphone's published sources node by node.

## before / after

The two device-tree files the FP3 port modifies, in both states, so the change
can be read without a kernel checkout.

Provenance, as of this snapshot:

* base: `v7.1.3-r0` (tag in `llg179/linux`, the msm8953-mainline 7.1.3 release)
* ours: `integration/7.1.3` — the change itself is commit `ca2896133002`,
  *"FP3: integrated device tree (audio + charger + camera) for 7.1.3 testing"*

Both copies are byte-identical to the corresponding git blobs, so
`diff -u before_update/<file> after_update/<file>` reproduces our delta:
**+375 / −4 lines** across the two files.

## The files

| file | delta | what we add |
|---|---|---|
| `sdm632-fairphone-fp3.dts` | 537 → 887 lines | the board changes: WCD9335 SLIMbus audio (`slimbam`, `slim_msm`, `tasha_ifd`, `wcd9335`, `divclk1_cdc`, `wcd_vout_1p8`, three pin-mux nodes, the `slim-playback` / `slim-capture` DAI links), the IMX363 rear camera (`camera@1a` plus the `&camss` port graph), and the charger side (`&pmi632_charger`, `fp3_battery`) |
| `pmi632.dtsi` | 209 → 230 lines | the PMI632 charger node itself, the counterpart of the board-level `&pmi632_charger` |

The other three files in the `#include` chain — `sdm632.dtsi`, `msm8953.dtsi`,
`pm8953.dtsi` — are **not** here because we do not touch them; the pin muxes our
audio path needs (`wcd_intr_default`, `cdc_reset_active` on `&tlmm`,
`tasha_mclk_default` on `&pm8953_gpios`) live in the board file as
`&`-references. See the "Device tree provenance" section of the top-level
[`README.md`](../../README.md) for how much of each file is upstream and how the
snapshot is verified across a base bump.

## Refreshing this snapshot after a base bump

From a `llg179/linux` checkout, with `<base>` the new kernel base:

```sh
for f in sdm632-fairphone-fp3.dts pmi632.dtsi; do
	git show "v<base>-r0:arch/arm64/boot/dts/qcom/$f"        > before_update/$f
	git show "integration/<base>:arch/arm64/boot/dts/qcom/$f" > after_update/$f
done
```

Then update the base/commit references above. Do not hand-edit the files here —
they are a snapshot of the kernel tree, not a source of truth.
