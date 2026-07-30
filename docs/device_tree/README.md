# Device tree

Everything about the FP3 device tree: the change this port makes, where its
content came from, and how much of the surrounding tree is upstream. The trees
themselves are checked in here, so none of the claims below have to be taken on
trust.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who reviewed it. The device trees checked
> in under `downstream/` are **not** ours and not generated — they are the
> vendor's and [UBports'](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632) published sources, unmodified.

| directory | contents | what it is | its README |
|---|---|---|---|
| [`before_update/`](before_update/) | [`sdm632-fairphone-fp3.dts`](before_update/sdm632-fairphone-fp3.dts) · [`pmi632.dtsi`](before_update/pmi632.dtsi) | the **upstream mainline** files exactly as the base ships them — what we had to touch | *(this page,* [below](#before--after)*)* |
| [`after_update/`](after_update/) | [`sdm632-fairphone-fp3.dts`](after_update/sdm632-fairphone-fp3.dts) · [`pmi632.dtsi`](after_update/pmi632.dtsi) | the same two files on `integration/<base>`, with our changes applied | *(idem)* |

☠️ `integration/<base>` deliberately excludes the `debug` layer, so these
snapshots do **not** show the watchdog node — that lives on `debug-int/<base>`, in
its own `sdm632-fairphone-fp3-debug.dtsi`, and is documented in
[`../debug/create_debug.md`](../debug/create_debug.md). Refreshed 2026-07-30
after the split; before it, `after_update/` carried the watchdog inline.
| [`downstream/`](downstream/) | — | the Android-era 4.9 tree, in the two forms below; where the values in the nodes we **add** come from | [README](downstream/README.md) — **compares the two**, and answers which Fairphone release the running tree is closest to |
| &nbsp;&nbsp;└ [`downstream/UT/`](downstream/UT/) | [`fp3-ubuntu-touch-live.dts`](downstream/UT/fp3-ubuntu-touch-live.dts) | the tree **as it runs**: dumped off the phone under Ubuntu Touch, fully resolved — ground truth for values | [README](downstream/UT/README.md) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ [`downstream/UT/kernel-dt/`](downstream/UT/kernel-dt/) | board file [`sdm632-mtp-s3.dts`](downstream/UT/kernel-dt/arch/arm64/boot/dts/qcom/sdm632-mtp-s3.dts) in [`…/dts/qcom/`](downstream/UT/kernel-dt/arch/arm64/boot/dts/qcom/) (938 files) + [`include/dt-bindings/`](downstream/UT/kernel-dt/include/dt-bindings/) | the **sources that dump was built from** — the UBports FP3 kernel's device tree (<https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632>, branch `ubuntutouch`); the only tree that reproduces the live one exactly | [README](downstream/UT/kernel-dt/README.md) |
| &nbsp;&nbsp;└ [`downstream/fairphone/`](downstream/fairphone/) | one directory per release | the vendor's own sources, **Fairphone** (<https://code.fairphone.com/projects/fairphone-3/gpl.html>) | — |
| &nbsp;&nbsp;&nbsp;&nbsp;└ [`downstream/fairphone/3.A.0136/`](downstream/fairphone/3.A.0136/) | board file [`sdm632-mtp-s3.dts`](downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/sdm632-mtp-s3.dts) in [`…/dts/qcom/`](downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/) (938 files) + [`include/dt-bindings/`](downstream/fairphone/3.A.0136/include/dt-bindings/) | the GPL sources of Fairphone OS **3.A.0136**, the last build for this phone | [README](downstream/fairphone/3.A.0136/README.md) |

## Review answers

| question | answer |
|---|---|
| [`firmware-name.md`](firmware-name.md) | why `firmware-name` keeps its `qcom/<soc>/<vendor>/<board>/` path, with the mainline references and the MBN signing identities measured off this phone |

In both source trees the phone is Qualcomm's `sdm632-mtp-s3` reference board;
that board file pulls in `sdm632.dtsi` → `msm8953.dtsi` and the
`sdm450-pmi632*` files from the same directory. Which file it is, and the
same-named SDM450 near-miss to avoid, is explained in
[`downstream/README.md`](downstream/README.md).

`before_update` → `after_update` is the change itself. Everything under
`downstream/` is reference material and has nothing to do with `before_update`,
which is plain upstream mainline.

## before / after

The two device-tree files the FP3 port modifies, in both states, so the change
can be read without a kernel checkout.

Provenance, as of this snapshot:

* base: `v7.1.3-r0` (tag in [`llg179/linux`](https://github.com/llg179/linux), the msm8953-mainline 7.1.3 release)
* ours: `integration/7.1.3` — seven commits touch the device tree, the bulk of it
  [`6749bae07da1`](https://github.com/llg179/linux/commit/6749bae07da17a2a9fffceaa4f78ec0d6c6353e8)
  *"FP3: integrated device tree (audio + charger + camera) for 7.1.3 testing"*
  (+375/−4); then
  [`b7a6d32e`](https://github.com/llg179/linux/commit/b7a6d32eb9b954ce45d5630ba653b85d081b4ea8)
  adds the watchdog node (+41),
  [`3b3043fe`](https://github.com/llg179/linux/commit/3b3043feab7c6f322c8543aab05f97fe8052dac0)
  removes the three framer-poke lines again,
  [`1f5b95d9`](https://github.com/llg179/linux/commit/1f5b95d9d62adb7b31644903d14bc3b8aa8c0f8c)
  adds the battery thermistor channel (+12/−2), and
  [`0eba8b8a`](https://github.com/llg179/linux/commit/0eba8b8a2f1f220fb6277724a7c553391020b979)
  raises the charge current to 2 A with the JEITA and thermal guards that go
  with it (+74/−6),
  [`da1591a6`](https://github.com/llg179/linux/commit/da1591a64116b91a809cd4f9df6caca7488dbc4a)
  corrects it to the pack this phone actually has, and
  [`0231f6b4`](https://github.com/llg179/linux/commit/0231f6b459175b8b9370d2fb7187abb7ce822b84)
  moves the battery's own properties onto the battery node and adds the ID
  resistor it should present

Both copies are byte-identical to the corresponding git blobs, so
`diff -u before_update/<file> after_update/<file>` reproduces our delta:
**+518 / −4 lines** across the two files.

### The files

| file | delta | what we add |
|---|---|---|
| `sdm632-fairphone-fp3.dts` | 537 → 1017 lines | the board changes: WCD9335 SLIMbus audio (`slimbam`, `slim_msm`, `tasha_ifd`, `wcd9335`, `divclk1_cdc`, `wcd_vout_1p8`, three pin-mux nodes, the `slim-playback` / `slim-capture` DAI links), the IMX363 rear camera (`camera@1a` plus the `&camss` port graph), the charger side (`fp3_battery` with the cell's ID resistor and JEITA description, `&pmi632_charger` with the board's pull-up and thermal-mitigation table, and a `cooling-maps` addition to the `pmi632-thermal` zone), and the `&watchdog` node with `qcom,start-at-probe` |
| `pmi632.dtsi` | 209 → 243 lines | the PMI632 charger node itself, the counterpart of the board-level `&pmi632_charger`, plus `channel@4a` and `channel@4b` — the battery thermistor and the battery-ID resistor the charger reads — and `#cooling-cells` on the charger node |

The other three files in the `#include` chain — `sdm632.dtsi`, `msm8953.dtsi`,
`pm8953.dtsi` — are **not** here because we do not touch them; the pin muxes our
audio path needs (`wcd_intr_default`, `cdc_reset_active` on `&tlmm`,
`tasha_mclk_default` on `&pm8953_gpios`) live in the board file as
`&`-references.

### What we took from where, and what is actually new

Almost none of the *values* in the added nodes are ours — they are read out of
the downstream 4.9 tree, which is why both copies of it are checked in here.
What is ours is the translation into mainline bindings and the composition. Per
block:

| block | numbers taken from | shape / binding taken from | what did not exist before |
|---|---|---|---|
| **audio** — WCD9335 over SLIMbus | Fairphone's published 4.9 sources ([`downstream/fairphone/3.A.0136/`](downstream/fairphone/3.A.0136/)): `msm8953.dtsi` (SLIMbus BAM `c104000`, NGD `c140000`), `msm8953-audio.dtsi` (the `slim217,1a0` device address, mic-bias voltages, DMIC clock), `msm8953-pinctrl.dtsi` (`cdc_reset`, `wcd_intr`, MCLK muxes) — Qualcomm BSP code as shipped by Fairphone | the existing **mainline** WCD9335 boards (DragonBoard 820c / MSM8996): codec binding and driver by **Srinivas Kandagatla** (`ASoC: wcd9335`, 2019) on his SLIMbus NGD controller (2018); binding conversion **Yassine Oudjana** (2022), node moved to the boards by **Krzysztof Kozlowski** (2023). We follow that shape, *not* downstream's `qcom,tasha-slim-pgd` | **the combination**: mainline had WCD9335 only on MSM8996, never on MSM8953. The NGD/BAM nodes at msm8953 addresses, `divclk1_cdc`, `wcd_vout_1p8`, the three pin-mux nodes, the MBHC button thresholds and the `slim-playback`/`slim-capture` DAI links are written here for the first time |
| **camera** — Sony IMX363 | Fairphone's `msm8953-camera-sensor-mtp.dtsi`: regulators, CCI wiring, power sequence. The I²C address `0x1a` is **not** from there — the FP3 straps SLASEL high, confirmed by probing the bus | the mainline **camss** graph binding (`port@0` / `csiphy0_ep`); it sits on **Luca Weiss'** groundwork in the board file — [`9e834e768d0b`](https://github.com/torvalds/linux/commit/9e834e768d0b2e9007cd6a5c778d2d8e3674e78f) camera fixed regulators and [`cfc22c2121cb`](https://github.com/torvalds/linux/commit/cfc22c2121cbf8bb75cb9a9993f13c17587ed55e) CCI + EEPROM, both in Linus' tree | the `camera@1a` node and the `&camss` port graph for this board — and the driver under it, which was **taken from Joel Selvaraj's [`5130bc702ea2`](https://gitlab.com/sdm670-mainline/linux/-/commit/5130bc702ea2efc53f6b652b4282067ee9ae7fd2)** on `sdm670-mainline/linux`, reverse-engineered there against a Pixel-3a-family sensor — see [`../kernel/README.md`](../kernel/README.md#camera-imx363c) |
| **charger** — PMI632 | the charger node's interrupt numbers and ADC channel assignment from Qualcomm's downstream `pmi632.dtsi` in the same release; the battery's cell parameters and OCV curve from Fairphone's own fuel-gauge profile `qg-batterydata-Kayo-3000mah-Nov4th2019-pmi632` — 3000 mAh, 4.39 V float, the 25 °C column of its `pc-temp-v1` table converted from 100 µV units | mainline `simple-battery` plus the `qcom_smbx` SMB5 binding | the SMB5 charger node in mainline's `pmi632.dtsi` (added disabled, as a PMIC-level description should be) and the board-level `&pmi632_charger` + `fp3_battery` that enable it. The charge current, the JEITA thresholds and the mitigation table are covered on the [charger page](../charger/README.md) |
| **sound card** | — | — | nothing: we *extend* `&sound_card` rather than rewrite it. The card itself is **Vldly's** [`5f0487e5a374`](https://github.com/llg179/linux/commit/5f0487e5a3748855721652afced36b2d1fe2bb25) (2022, msm8953-mainline only, not in Linus' tree) and the AW8898/MI2S speaker path on it is **Luca Weiss'** [`4fd8c23afa2e`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) + [`4335b0ae1eb6`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d) |

### What the charger side describes

The board's `&pmi632_charger` and `fp3_battery` nodes carry more than an enable:
the battery's cell parameters and OCV curve, the JEITA comparator thresholds as
raw ADC codes, the per-soft-zone charge currents, and the thermal mitigation
table — plus a `cooling-maps` addition to the PMIC's own temperature zone.

All of those values, where each came from and why the charge current settles at
2 A rather than the pack's rated 2.7 A, are on the charger page:
[**`../charger/README.md`**](../charger/README.md). The short version is that
two ceilings sit below the battery's rating — the JEITA compensation register
runs out of range above about 2.175 A, and without high-voltage negotiation the
USB port supplies about 1.9 A into the cell anyway.

**How to verify a change here.** Raise the current in steps — 1.0 → 1.5 → 2.0 A
— and at each step charge from a low state of charge on both a high-current wall
charger and a plain SDP port, watching a USB power meter against what the driver
reports, and the die and connector temperatures. `fp3-selftest` covers that the
charger works at all, not that it is safe at current.

Two things worth keeping straight when reading the above. First, the board file
we edit is **Luca Weiss'** work — he has carried the FP3 in mainline since
2022-02-20; our commits are entries in a 23-commit history (see
[Genealogy](#genealogy-of-the-board-file-23-commits-oldest-first)). Second,
several nodes we build on top of exist **only in msm8953-mainline**, not in
Linus' tree — the sound card above, [`e54a56452736`](https://github.com/llg179/linux/commit/e54a564527364e0f40cd71753dd68fe5baa3829d) hardware codec (**Sireesh
Kodali**), [`ccf0e0d540ba`](https://github.com/llg179/linux/commit/ccf0e0d540baf309e3dd6a4ff4f661773b871196) camss (**Vldly**) — which is why an upstream series
cannot assume they are there.

### Refreshing this snapshot after a base bump

From a [`llg179/linux`](https://github.com/llg179/linux) checkout, with `<base>` the new kernel base:

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
| `sdm632-fairphone-fp3.dts` | 925 | 23 | Luca Weiss' upstream FP3 board file (since 2022-02-20) **+ three commits of ours** ([`ca289613`](https://github.com/llg179/linux/commit/6749bae07da1) +358, the watchdog node +41, the framer-poke revert −3) |
| `pmi632.dtsi` | 240 | 7 | upstream PMI632 PMIC description ([`a1f0f2eb`](https://github.com/torvalds/linux/commit/a1f0f2ebb044c7248c3f30b98de0f151505bd4bd)) **+ two commits of ours** ([`ca289613`](https://github.com/llg179/linux/commit/6749bae07da1) +21 — the charger node; [`1f5b95d9`](https://github.com/llg179/linux/commit/1f5b95d9d62adb7b31644903d14bc3b8aa8c0f8c) +10 — the `BAT_THERM` channel) |
| `sdm632.dtsi` | 142 | 8 | upstream only — `msm8953.dtsi` plus the SDM632 CPU/rpmpd overrides; untouched |
| `msm8953.dtsi` | 3435 | 84 | upstream msm8953-mainline SoC file; untouched |
| `pm8953.dtsi` | 200 | 10 | upstream PM8953 PMIC file; untouched |

Note that the `wcd_intr_default` / `cdc_reset_active` (`&tlmm`) and
`tasha_mclk_default` (`&pm8953_gpios`) pin muxes live in the **board** file as
`&`-references, not in the SoC-level files — which is why the bottom three rows
stay untouched.

### Genealogy of the board file (23 commits, oldest first)

The "in mainline" column is the answer to `git merge-base --is-ancestor <sha>
torvalds/master`, and the release is `git describe --contains`. **17 of the 20
upstream commits are in Linus' tree**; three are carried only by
msm8953-mainline.

| commit | origin | in mainline |
|---|---|---|
| [`308b26cddb04`](https://github.com/torvalds/linux/commit/308b26cddb04afc7776de1cbbe07172eeccc7c98) initial dts for Fairphone 3 | Luca Weiss, 2022-02-20 | ✅ v5.18-rc1 |
| [`b08f5cbd69dc`](https://github.com/torvalds/linux/commit/b08f5cbd69dcd25f5ab2a0798fe3836a97a9d7c6), [`372698e8df26`](https://github.com/torvalds/linux/commit/372698e8df2619bf76b047c9a600d1f659d7868b) gpio-key / RPM-regulator node names | tree-wide dtschema alignment, not FP3-specific | ✅ v6.0-rc1, v6.2-rc1 |
| [`6d9a666d49bf`](https://github.com/torvalds/linux/commit/6d9a666d49bf57c6a176e5fcf1b39046ee6a728f) touchscreen · [`29dcf3c1a815`](https://github.com/torvalds/linux/commit/29dcf3c1a8159acdf56905c377a214381eda5a24) NFC · [`0c4f10917d22`](https://github.com/torvalds/linux/commit/0c4f10917d22e6f36080617bfe71de1ae854ee58) notification LED · [`5b006a82a2bb`](https://github.com/torvalds/linux/commit/5b006a82a2bbc0ce18bc6b084fc8d8d9cc110001) WiFi/BT · [`2dee68e77cb5`](https://github.com/torvalds/linux/commit/2dee68e77cb5322d7cfe44f3c84ff8ae2eaf4aee) **LPASS** · [`90053b1574f8`](https://github.com/torvalds/linux/commit/90053b1574f8cff3a3b53accc496246ad2e0aec3) USB-C · [`ffaa4b5d5d07`](https://github.com/torvalds/linux/commit/ffaa4b5d5d07aed600d82929d8862263ce341a71) vibrator | Luca Weiss, one commit per feature | ✅ v6.2-rc1 … v6.11-rc1 (LPASS + WiFi/BT in v6.8-rc1) |
| [`09a3840bcb72`](https://github.com/torvalds/linux/commit/09a3840bcb72bcd9b43cbffbb7dedccf85e6d558) status properties last · [`a4600b160eca`](https://github.com/torvalds/linux/commit/a4600b160eca7f889c4b4a370d42e4619fa5162a) newlines between regulators | pure style commits, no functional change | ✅ v6.16-rc1 |
| [`9ab813d5191f`](https://github.com/torvalds/linux/commit/9ab813d5191f61301dbaeaf8e82d21e689b080f4) adsp+wcnss firmware-name · [`d0c38cbe3556`](https://github.com/torvalds/linux/commit/d0c38cbe3556fea446b9350ec597a8e9c2cdaf36) modem · [`4ea55ecb4990`](https://github.com/torvalds/linux/commit/4ea55ecb4990aa4142ddae5f713289f4101f046f) display+GPU · [`9e834e768d0b`](https://github.com/torvalds/linux/commit/9e834e768d0b2e9007cd6a5c778d2d8e3674e78f) camera fixed regulators · [`cfc22c2121cb`](https://github.com/torvalds/linux/commit/cfc22c2121cbf8bb75cb9a9993f13c17587ed55e) CCI + EEPROM | Luca Weiss | ✅ v6.16-rc1 (first two), v6.18-rc1, v7.0-rc1 (last two) |
| [`4fd8c23afa2e`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) **AW8898 amplifier** | Luca Weiss, 2025-04-06 — the `FROMLIST v2` subject prefix says it plainly | ❌ **fork-only** — still not in Linus' tree, and no equivalent landed under another hash |
| [`4335b0ae1eb6`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d) enable speaker | Luca Weiss, 2023-04-18 — builds on the AW8898 node | ❌ **fork-only**, carried along with it |
| [`60f6f604cf3c`](https://github.com/llg179/linux/commit/60f6f604cf3cda9d50364804317538b26162c747) enable venus | Luca Weiss, 2026-05-06 — already present in the 7.0.9 base too, *not* something the 7.1.3 bump brought in | ❌ **fork-only** |
| **[`6749bae07da1`](https://github.com/llg179/linux/commit/6749bae07da1)** integrated DT (audio + charger + camera) | **ours**, 2026-07-25 | ❌ ours, see `submit/<base>/*` |
| **[`b7a6d32eb9b9`](https://github.com/llg179/linux/commit/b7a6d32eb9b954ce45d5630ba653b85d081b4ea8)** `&watchdog` with `qcom,start-at-probe` | **ours**, 2026-07-28 | ❌ ours, and deliberately not upstream-bound — it is the `debug` category |
| **[`3b3043feab7c`](https://github.com/llg179/linux/commit/3b3043feab7c)** revert the SLIMbus framer pokes | **ours**, 2026-07-29 | ❌ ours — drops the `qcom,slim-framer-quirk-reg` property `ca289613` had put on `slim_msm`, after measurement showed the codec comes up without the poke |

### What our commit adds, and what it was derived from

[`ca289613`](https://github.com/llg179/linux/commit/6749bae07da1) adds 375 of the board file's 925 lines, in four separable blocks:

| block | nodes | derived from |
|---|---|---|
| **audio** | `slimbam: dma-controller@c104000`, `slim_msm: slim-ngd@c140000`, `tasha_ifd: ifd@0,0`, `wcd9335: codec@1,0` (`slim217,1a0`), `divclk1_cdc` (gpio-gate-clock), `wcd_vout_1p8`, three pin-mux nodes, and the `slim-playback`/`slim-capture` DAI links inside `&sound_card` | addresses and wiring from the downstream 4.9 tree (`msm8953.dtsi`, `msm8953-audio.dtsi`, `msm8953-ext-codec-mtp.dts`); the **node shape and the `slim217,1a0` compatible follow the existing mainline WCD9335 boards** (DragonBoard 820c, OnePlus 3), not the downstream `qcom,tasha-slim-pgd` scheme |
| **camera** | `camera@1a` (`sony,imx363`) plus the `&camss` `port@0` / `csiphy0_ep` graph | downstream `msm8953-camera-sensor-*.dtsi` data, translated to the mainline camss graph binding; sits on top of Luca's [`9e834e76`](https://github.com/torvalds/linux/commit/9e834e768d0b2e9007cd6a5c778d2d8e3674e78f) + [`cfc22c21`](https://github.com/torvalds/linux/commit/cfc22c2121cbf8bb75cb9a9993f13c17587ed55e) regulator/CCI groundwork |
| **charger** | `&pmi632_charger` and `fp3_battery` (`simple-battery`) | the counterpart of the new charger node added to `pmi632.dtsi` |
| **sound card** | extends `&sound_card` rather than rewriting it | the base already carries the AW8898/MI2S speaker path ([`4fd8c23a`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) + [`4335b0ae`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d)) |

This one commit is **integration-only** — its own message says so, and the
per-subsystem split for upstream lives on the `submit/<base>/<category>`
branches, as of 2026-07-30:

| branch | its device-tree commit(s) |
|---|---|
| `submit/7.1.3/audio` | [`2b5fb30cd11e`](https://github.com/llg179/linux/commit/2b5fb30cd11e) *wire up WCD9335 audio* |
| `submit/7.1.3/camera` | [`0c7ea33fa5c5`](https://github.com/llg179/linux/commit/0c7ea33fa5c5) *add the rear IMX363 camera* |
| `submit/7.1.3/charger` | [`0b4b054b6d81`](https://github.com/llg179/linux/commit/0b4b054b6d81) *pmi632: add the SMB5 charger* + [`a800c7ec823a`](https://github.com/llg179/linux/commit/a800c7ec823a) *enable charging* |
| `submit/7.1.3/voice` | none — pure driver routing, which is correct |
| `submit/7.1.3/sensor` | none — and only one patch in total, for [these reasons](../sensors/README.md#why-the-submit-series-is-one-patch) |

☠️ These hashes move whenever a submit branch is regenerated, which is normal —
the branches are rebuilt from `wip`, not edited. Four links here pointed at an
earlier generation until 2026-07-30 and two of them had become unreachable
objects, i.e. dead links. The camera row moved **again** later the same day, when
the series was rebuilt around its import commit. Re-read them off the branch
rather than trusting the table:

```sh
git log --oneline --format='%h %s' 7.1.3/main..submit/7.1.3/<category> \
    -- 'arch/arm64/boot/dts/*'
```

### Validating the device tree

`dtbs_check` is worth running, and worth running as a **differential**: the 7.1.3
base fails it 44 times by itself, so an absolute count tells you nothing about
your own work.

```sh
pip install dtschema yamllint          # needs swig, libfdt-dev, python3-dev
make ARCH=arm64 CC=gcc HOSTCC=gcc CHECK_DTBS=y \
     qcom/sdm632-fairphone-fp3.dtb
```

Run it with the board files from the base checked out, run it again with this
branch's, and diff the two sorted lists. Measured on 2026-07-30, this tree adds
**six** errors, all listed with their fixes in
[`../TODO.md`](../TODO.md#open-before-anything-is-submitted): three belong to the
audio device tree, one to the charger's battery node, one to the `debug` category
which is never submitted anyway — and one, the cooling-map node names, was fixed
the same day.

Note that a node whose `compatible` nothing documents is **skipped silently**
rather than reported. That is why the charger node produced no errors before its
binding existed, and why a clean run is not by itself evidence that a node was
checked.

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
confirm they are line-for-line identical (392+/4− in the board file, 31+ in
`pmi632.dtsi`, as of 2026-07-29); that is what proves the rebase neither dropped
one of our hunks nor reverted an upstream one.

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
[`4fd8c23afa2e`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) (AW8898 amplifier), [`4335b0ae1eb6`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d) (enable speaker) and
[`60f6f604cf3c`](https://github.com/llg179/linux/commit/60f6f604cf3cda9d50364804317538b26162c747) (enable venus), and a subject search over `torvalds/master`
confirms none of them landed under a different hash either. The `FROMLIST v2`
prefix on [`4fd8c23afa2e`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) was therefore the correct signal, just not the only one.

The **SoC** file is a different story: 22 of the 84 `msm8953.dtsi` commits and 5
of the 8 `sdm632.dtsi` ones exist only in msm8953-mainline — including things our
work sits directly on top of, notably [`5f0487e5a374`](https://github.com/llg179/linux/commit/5f0487e5a3748855721652afced36b2d1fe2bb25) "add sound card" (we extend
`&sound_card`), [`e54a56452736`](https://github.com/llg179/linux/commit/e54a564527364e0f40cd71753dd68fe5baa3829d) hardware codec, [`ccf0e0d540ba`](https://github.com/llg179/linux/commit/ccf0e0d540baf309e3dd6a4ff4f661773b871196) camss, and
[`de3e8dc98213`](https://github.com/llg179/linux/commit/de3e8dc98213e4fcbd3d1ae30b1b1e8b71320143) "replace CS-Voice with VoiceMMode1" (the voice path). That is
worth keeping in mind when writing a `submit/<base>/*` series: an LKML patch may
not assume any of those nodes exist.
