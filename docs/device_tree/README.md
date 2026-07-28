# Device tree

Everything about the FP3 device tree: the change this port makes, where its
content came from, and how much of the surrounding tree is upstream. The trees
themselves are checked in here, so none of the claims below have to be taken on
trust.

| directory | contents | what it is | its README |
|---|---|---|---|
| [`before_update/`](before_update/) | 2 files | the **upstream mainline** files exactly as the base ships them — what we had to touch | *(this page,* [below](#before--after)*)* |
| [`after_update/`](after_update/) | 2 files | the same two files on `integration/<base>`, with our changes applied | *(idem)* |
| [`downstream/`](downstream/) | — | the Android-era 4.9 tree, in the two forms below; where the values in the nodes we **add** come from | [README](downstream/README.md) — **compares the two**, and answers which Fairphone release the running tree is closest to |
| &nbsp;&nbsp;└ [`downstream/UT/`](downstream/UT/) | `fp3-ubuntu-touch-live.dts` | the tree **as it runs**: dumped off the phone under Ubuntu Touch, fully resolved — ground truth for values | [README](downstream/UT/README.md) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ [`downstream/UT/kernel-dt/`](downstream/UT/kernel-dt/) | `arch/arm64/boot/dts/qcom/` + `include/dt-bindings/` | the **sources that dump was built from** — the UBports FP3 kernel's device tree; the only tree that reproduces the live one exactly | [README](downstream/UT/kernel-dt/README.md) |
| &nbsp;&nbsp;└ [`downstream/fairphone/`](downstream/fairphone/) | one directory per release | the vendor's own sources, **Fairphone** (<https://code.fairphone.com/projects/fairphone-3/gpl.html>) | — |
| &nbsp;&nbsp;&nbsp;&nbsp;└ [`downstream/fairphone/3.A.0136/`](downstream/fairphone/3.A.0136/) | `arch/arm64/boot/dts/qcom/` + `include/dt-bindings/` | the GPL sources of Fairphone OS **3.A.0136**, the last build for this phone | [README](downstream/fairphone/3.A.0136/README.md) |

`before_update` → `after_update` is the change itself. Everything under
`downstream/` is reference material and has nothing to do with `before_update`,
which is plain upstream mainline.

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

### The files

| file | delta | what we add |
|---|---|---|
| `sdm632-fairphone-fp3.dts` | 537 → 887 lines | the board changes: WCD9335 SLIMbus audio (`slimbam`, `slim_msm`, `tasha_ifd`, `wcd9335`, `divclk1_cdc`, `wcd_vout_1p8`, three pin-mux nodes, the `slim-playback` / `slim-capture` DAI links), the IMX363 rear camera (`camera@1a` plus the `&camss` port graph), and the charger side (`&pmi632_charger`, `fp3_battery`) |
| `pmi632.dtsi` | 209 → 230 lines | the PMI632 charger node itself, the counterpart of the board-level `&pmi632_charger` |

The other three files in the `#include` chain — `sdm632.dtsi`, `msm8953.dtsi`,
`pm8953.dtsi` — are **not** here because we do not touch them; the pin muxes our
audio path needs (`wcd_intr_default`, `cdc_reset_active` on `&tlmm`,
`tasha_mclk_default` on `&pm8953_gpios`) live in the board file as
`&`-references.

### Refreshing this snapshot after a base bump

From a `llg179/linux` checkout, with `<base>` the new kernel base:

```sh
for f in sdm632-fairphone-fp3.dts pmi632.dtsi; do
	git show "v<base>-r0:arch/arm64/boot/dts/qcom/$f"        > before_update/$f
	git show "integration/<base>:arch/arm64/boot/dts/qcom/$f" > after_update/$f
done
```

Then update the base/commit references above. Do not hand-edit the files here —
they are a snapshot of the kernel tree, not a source of truth.

## Provenance

Which `.dts`/`.dtsi` files the FP3 device tree is actually built from, and where
each one came from. Measured on `integration/7.1.3`; the shape does not change
across a base bump, only the commit hashes do.

The board `.dtb` is assembled from **five** files through the `#include` chain,
and only **two** of them carry any of our work:

| file | lines | commits | where it comes from |
|---|---|---|---|
| `sdm632-fairphone-fp3.dts` | 887 | 21 | Luca Weiss' upstream FP3 board file (since 2022-02-20) **+ one commit of ours** (`ca289613`, +358) |
| `pmi632.dtsi` | 230 | 6 | upstream PMI632 PMIC description (`a1f0f2eb`) **+ one commit of ours** (`ca289613`, +21 — the charger node) |
| `sdm632.dtsi` | 142 | 8 | upstream only — `msm8953.dtsi` plus the SDM632 CPU/rpmpd overrides; untouched |
| `msm8953.dtsi` | 3435 | 84 | upstream msm8953-mainline SoC file; untouched |
| `pm8953.dtsi` | 200 | 10 | upstream PM8953 PMIC file; untouched |

Note that the `wcd_intr_default` / `cdc_reset_active` (`&tlmm`) and
`tasha_mclk_default` (`&pm8953_gpios`) pin muxes live in the **board** file as
`&`-references, not in the SoC-level files — which is why the bottom three rows
stay untouched.

### Genealogy of the board file (21 commits, oldest first)

The "in mainline" column is the answer to `git merge-base --is-ancestor <sha>
torvalds/master`, and the release is `git describe --contains`. **17 of the 20
upstream commits are in Linus' tree**; three are carried only by
msm8953-mainline.

| commit | origin | in mainline |
|---|---|---|
| `308b26cddb04` initial dts for Fairphone 3 | Luca Weiss, 2022-02-20 | ✅ v5.18-rc1 |
| `b08f5cbd69dc`, `372698e8df26` gpio-key / RPM-regulator node names | tree-wide dtschema alignment, not FP3-specific | ✅ v6.0-rc1, v6.2-rc1 |
| `6d9a666d49bf` touchscreen · `29dcf3c1a815` NFC · `0c4f10917d22` notification LED · `5b006a82a2bb` WiFi/BT · `2dee68e77cb5` **LPASS** · `90053b1574f8` USB-C · `ffaa4b5d5d07` vibrator | Luca Weiss, one commit per feature | ✅ v6.2-rc1 … v6.11-rc1 (LPASS + WiFi/BT in v6.8-rc1) |
| `09a3840bcb72` status properties last · `a4600b160eca` newlines between regulators | pure style commits, no functional change | ✅ v6.16-rc1 |
| `9ab813d5191f` adsp+wcnss firmware-name · `d0c38cbe3556` modem · `4ea55ecb4990` display+GPU · `9e834e768d0b` camera fixed regulators · `cfc22c2121cb` CCI + EEPROM | Luca Weiss | ✅ v6.16-rc1 (first two), v6.18-rc1, v7.0-rc1 (last two) |
| `4fd8c23afa2e` **AW8898 amplifier** | Luca Weiss, 2025-04-06 — the `FROMLIST v2` subject prefix says it plainly | ❌ **fork-only** — still not in Linus' tree, and no equivalent landed under another hash |
| `4335b0ae1eb6` enable speaker | Luca Weiss, 2023-04-18 — builds on the AW8898 node | ❌ **fork-only**, carried along with it |
| `60f6f604cf3c` enable venus | Luca Weiss, 2026-05-06 — already present in the 7.0.9 base too, *not* something the 7.1.3 bump brought in | ❌ **fork-only** |
| **`ca2896133002`** integrated DT (audio + charger + camera) | **ours**, 2026-07-25 | ❌ ours, see `submit/<base>/*` |

### What our commit adds, and what it was derived from

`ca289613` adds 375 of the 887 lines, in four separable blocks:

| block | nodes | derived from |
|---|---|---|
| **audio** | `slimbam: dma-controller@c104000`, `slim_msm: slim-ngd@c140000`, `tasha_ifd: ifd@0,0`, `wcd9335: codec@1,0` (`slim217,1a0`), `divclk1_cdc` (gpio-gate-clock), `wcd_vout_1p8`, three pin-mux nodes, and the `slim-playback`/`slim-capture` DAI links inside `&sound_card` | addresses and wiring from the downstream 4.9 tree (`msm8953.dtsi`, `msm8953-audio.dtsi`, `msm8953-ext-codec-mtp.dts`); the **node shape and the `slim217,1a0` compatible follow the existing mainline WCD9335 boards** (DragonBoard 820c, OnePlus 3), not the downstream `qcom,tasha-slim-pgd` scheme |
| **camera** | `camera@1a` (`sony,imx363`) plus the `&camss` `port@0` / `csiphy0_ep` graph | downstream `msm8953-camera-sensor-*.dtsi` data, translated to the mainline camss graph binding; sits on top of Luca's `9e834e76` + `cfc22c21` regulator/CCI groundwork |
| **charger** | `&pmi632_charger` and `fp3_battery` (`simple-battery`) | the counterpart of the new charger node added to `pmi632.dtsi` |
| **sound card** | extends `&sound_card` rather than rewriting it | the base already carries the AW8898/MI2S speaker path (`4fd8c23a` + `4335b0ae`) |

This one commit is **integration-only** — its own message says so, and the
per-subsystem split for upstream lives on the `submit/<base>/<category>`
branches: `submit/7.1.3/audio` (`ef0d6d3d`), `submit/7.1.3/camera` (`f42f8162`),
`submit/7.1.3/charger` (`5c0aa3dd` + `78bf6ee3`). `submit/7.1.3/voice` carries no
DTS at all — it is pure driver routing, which is correct.

### What a base bump does to the device tree (7.0.9 → 7.1.3, measured)

The commit hashes in the tables above change on every base bump, because
msm8953-mainline re-applies its series onto each new stable — so `git log
<oldbase>..<newbase>` prints the *entire* history and tells you nothing. Compare
**content**, not history:

```
git diff --stat <oldbase> <newbase> -- \
  arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3.dts \
  arch/arm64/boot/dts/qcom/{sdm632,msm8953,pm8953,pmi632}.dtsi
```

Across 7.0.9 → 7.1.3 that came out as **6+/6− in `msm8953.dtsi` and nothing
else** — the board file blob is bit-identical between the two bases — and the one
change is a pure dtschema label rename on the PM8953-internal PDM pin muxes
(`cdc_pdm_lines_act`/`_sus` → `cdc_pdm_lines_default`/`_sleep`, plus the
`comp_lines` and `lines_2` pairs). The FP3 board file references none of them
(our path is WCD9335 over SLIMbus, and the board file `/delete-property/`s the
PM8953 codec's `audio-routing` anyway), so nothing had to be carried over.

Two more checks worth repeating on the next bump, both of which came out clean
here: the `#include` chain still resolves to the same five files, and the
`dt-bindings` headers the board pulls in (`qcom,q6afe.h`, `q6asm.h`,
`q6voice.h`, the msm8953 interconnect/GCC/rpmpd ones) are unchanged. Finally,
diff *our own* delta on both bases — `git diff <oldbase> integration/<oldbase>`
vs `git diff <newbase> integration/<newbase>` for the two touched files — and
confirm they are line-for-line identical (358+/4− in the board file, 21+ in
`pmi632.dtsi`); that is what proves the rebase neither dropped one of our hunks
nor reverted an upstream one.

### How much of the device tree is actually mainline

Answering this needs the real history, so the working clone carries a `torvalds`
remote and full (un-shallowed) history:

```
git fetch --unshallow origin
git remote add torvalds https://github.com/torvalds/linux.git
git fetch torvalds
git commit-graph write --reachable   # or every ancestry query below crawls
```

Then, per file, split the commits by `git merge-base --is-ancestor <sha>
torvalds/master`:

| file | commits at `v7.1.3-r0` | in Linus' tree | msm8953-mainline only | fork delta vs `torvalds/master` |
|---|---|---|---|---|
| `sdm632-fairphone-fp3.dts` | 20 | 17 | **3** | +91 / −2 |
| `pmi632.dtsi` | 5 | 5 | 0 | +1 |
| `sdm632.dtsi` | 8 | 3 | 5 | +53 |
| `msm8953.dtsi` | 84 | 62 | **22** | +1001 / −49 |
| `pm8953.dtsi` | 10 | 6 | 4 | +72 |

So the FP3 **board** file is almost entirely upstream — the three exceptions are
`4fd8c23afa2e` (AW8898 amplifier), `4335b0ae1eb6` (enable speaker) and
`60f6f604cf3c` (enable venus), and a subject search over `torvalds/master`
confirms none of them landed under a different hash either. The `FROMLIST v2`
prefix on `4fd8c23afa2e` was therefore the correct signal, just not the only one.

The **SoC** file is a different story: 22 of the 84 `msm8953.dtsi` commits and 5
of the 8 `sdm632.dtsi` ones exist only in msm8953-mainline — including things our
work sits directly on top of, notably `5f0487e5a374` "add sound card" (we extend
`&sound_card`), `e54a56452736` hardware codec, `ccf0e0d540ba` camss, and
`de3e8dc98213` "replace CS-Voice with VoiceMMode1" (the voice path). That is
worth keeping in mind when writing a `submit/<base>/*` series: an LKML patch may
not assume any of those nodes exist.
