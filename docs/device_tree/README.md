# Device tree

Everything about the FP3 device tree: the change this port makes, where its
content came from, and how much of the surrounding tree is upstream. The trees
themselves are checked in here, so none of the claims below have to be taken on
trust.

| directory | contents | what it is | its README |
|---|---|---|---|
| [`before_update/`](before_update/) | [`sdm632-fairphone-fp3.dts`](before_update/sdm632-fairphone-fp3.dts) · [`pmi632.dtsi`](before_update/pmi632.dtsi) | the **upstream mainline** files exactly as the base ships them — what we had to touch | *(this page,* [below](#before--after)*)* |
| [`after_update/`](after_update/) | [`sdm632-fairphone-fp3.dts`](after_update/sdm632-fairphone-fp3.dts) · [`pmi632.dtsi`](after_update/pmi632.dtsi) | the same two files on `integration/<base>`, with our changes applied | *(idem)* |
| [`downstream/`](downstream/) | — | the Android-era 4.9 tree, in the two forms below; where the values in the nodes we **add** come from | [README](downstream/README.md) — **compares the two**, and answers which Fairphone release the running tree is closest to |
| &nbsp;&nbsp;└ [`downstream/UT/`](downstream/UT/) | [`fp3-ubuntu-touch-live.dts`](downstream/UT/fp3-ubuntu-touch-live.dts) | the tree **as it runs**: dumped off the phone under Ubuntu Touch, fully resolved — ground truth for values | [README](downstream/UT/README.md) |
| &nbsp;&nbsp;&nbsp;&nbsp;└ [`downstream/UT/kernel-dt/`](downstream/UT/kernel-dt/) | board file [`sdm632-mtp-s3.dts`](downstream/UT/kernel-dt/arch/arm64/boot/dts/qcom/sdm632-mtp-s3.dts) in [`…/dts/qcom/`](downstream/UT/kernel-dt/arch/arm64/boot/dts/qcom/) (938 files) + [`include/dt-bindings/`](downstream/UT/kernel-dt/include/dt-bindings/) | the **sources that dump was built from** — the UBports FP3 kernel's device tree (<https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632>, branch `ubuntutouch`); the only tree that reproduces the live one exactly | [README](downstream/UT/kernel-dt/README.md) |
| &nbsp;&nbsp;└ [`downstream/fairphone/`](downstream/fairphone/) | one directory per release | the vendor's own sources, **Fairphone** (<https://code.fairphone.com/projects/fairphone-3/gpl.html>) | — |
| &nbsp;&nbsp;&nbsp;&nbsp;└ [`downstream/fairphone/3.A.0136/`](downstream/fairphone/3.A.0136/) | board file [`sdm632-mtp-s3.dts`](downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/sdm632-mtp-s3.dts) in [`…/dts/qcom/`](downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/) (938 files) + [`include/dt-bindings/`](downstream/fairphone/3.A.0136/include/dt-bindings/) | the GPL sources of Fairphone OS **3.A.0136**, the last build for this phone | [README](downstream/fairphone/3.A.0136/README.md) |

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

* base: `v7.1.3-r0` (tag in `llg179/linux`, the msm8953-mainline 7.1.3 release)
* ours: `integration/7.1.3` — the change itself is commit [`ca2896133002`](https://github.com/llg179/linux/commit/ca2896133002d44daee935ac45a749dab641ef45),
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

### What we took from where, and what is actually new

Almost none of the *values* in the added nodes are ours — they are read out of
the downstream 4.9 tree, which is why both copies of it are checked in here.
What is ours is the translation into mainline bindings and the composition. Per
block:

| block | numbers taken from | shape / binding taken from | what did not exist before |
|---|---|---|---|
| **audio** — WCD9335 over SLIMbus | Fairphone's published 4.9 sources ([`downstream/fairphone/3.A.0136/`](downstream/fairphone/3.A.0136/)): `msm8953.dtsi` (SLIMbus BAM `c104000`, NGD `c140000`), `msm8953-audio.dtsi` (the `slim217,1a0` device address, mic-bias voltages, DMIC clock), `msm8953-pinctrl.dtsi` (`cdc_reset`, `wcd_intr`, MCLK muxes) — Qualcomm BSP code as shipped by Fairphone | the existing **mainline** WCD9335 boards (DragonBoard 820c / MSM8996): codec binding and driver by **Srinivas Kandagatla** (`ASoC: wcd9335`, 2019) on his SLIMbus NGD controller (2018); binding conversion **Yassine Oudjana** (2022), node moved to the boards by **Krzysztof Kozlowski** (2023). We follow that shape, *not* downstream's `qcom,tasha-slim-pgd` | **the combination**: mainline had WCD9335 only on MSM8996, never on MSM8953. The NGD/BAM nodes at msm8953 addresses, `divclk1_cdc`, `wcd_vout_1p8`, the three pin-mux nodes, the MBHC button thresholds and the `slim-playback`/`slim-capture` DAI links are written here for the first time |
| **camera** — Sony IMX363 | Fairphone's `msm8953-camera-sensor-mtp.dtsi`: regulators, CCI wiring, power sequence. The I²C address `0x1a` is **not** from there — the FP3 straps SLASEL high, confirmed by probing the bus | the mainline **camss** graph binding (`port@0` / `csiphy0_ep`); it sits on **Luca Weiss'** groundwork in the board file — [`9e834e768d0b`](https://github.com/torvalds/linux/commit/9e834e768d0b2e9007cd6a5c778d2d8e3674e78f) camera fixed regulators and [`cfc22c2121cb`](https://github.com/torvalds/linux/commit/cfc22c2121cbf8bb75cb9a9993f13c17587ed55e) CCI + EEPROM, both in Linus' tree | the `camera@1a` node and the `&camss` port graph for this board — and the driver under it, whose register programming was reverse-engineered on the FP3 (same sensor family as the Pixel 3a) |
| **charger** — PMI632 | the charger node's interrupt numbers and ADC channel assignment from Qualcomm's downstream `pmi632.dtsi` in the same release; the battery's cell parameters and OCV curve from Fairphone's own fuel-gauge profile `qg-batterydata-Kayo-3000mah-Nov4th2019-pmi632` — 3000 mAh, 4.39 V float, the 25 °C column of its `pc-temp-v1` table converted from 100 µV units | mainline `simple-battery` plus the `qcom_smbx` SMB5 binding | the SMB5 charger node in mainline's `pmi632.dtsi` (added disabled, as a PMIC-level description should be) and the board-level `&pmi632_charger` + `fp3_battery` that enable it. **Deliberate deviation:** charge current held at 1 A instead of downstream's 2.0–2.7 A until the thermal/JEITA side is exercised |
| **sound card** | — | — | nothing: we *extend* `&sound_card` rather than rewrite it. The card itself is **Vldly's** [`5f0487e5a374`](https://github.com/llg179/linux/commit/5f0487e5a3748855721652afced36b2d1fe2bb25) (2022, msm8953-mainline only, not in Linus' tree) and the AW8898/MI2S speaker path on it is **Luca Weiss'** [`4fd8c23afa2e`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) + [`4335b0ae1eb6`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d) |

### What it would take to charge at full current

The phone charges at **1 A** where Fairphone's own profile for this cell says
`qcom,fastchg-current-ma = <2700>`. That is not one conservative number in one
place — it is two independent caps plus three missing safety mechanisms.

**Where the 1 A actually comes from.** Not from our device tree. The
`qcom_smbx` driver writes the fast-charge current register at probe, from a
fixed table entry that exists for both charger variants:

```c
/*
 * This overrides all of the current limit options exposed to userspace
 * and prevents the device from pulling more than ~1A. This is done
 * to minimise potential fire hazard risks.
 */
{ .addr = FAST_CHARGE_CURRENT_CFG, … .val = 1000000 / CURRENT_SCALE_FACTOR },
```

Our `constant-charge-current-max-microamp = <1000000>` is, today,
**documentation only**: `power_supply_get_battery_info()` is called, but the
only field the driver applies to the hardware is `voltage_max_design_uv`, which
becomes the float voltage. Raising the DT number alone changes nothing.

**What has to be built, in order:**

| # | what | why it blocks the current |
|---|---|---|
| 1 | **Battery temperature.** Add the `BAT_THERM` channel to the charger node's `io-channels` (we currently read only `usbin_i`, `usbin_v`, `vbat`) and expose it — `POWER_SUPPLY_PROP_TEMP` and/or a thermal zone | nothing in the stack knows how hot the cell is, so nothing can back off. Everything below depends on this |
| 2 | **JEITA.** Program `JEITA_EN_CFG` (hard limit + the hot/cold float-voltage and charge-current slots). The driver already defines those bits and reads the JEITA *status* register for `POWER_SUPPLY_PROP_HEALTH` — nothing writes the *enable* | at 1 A a mis-charge at temperature is survivable; at 2.7 A it is what the safety margin was for. Downstream sets `qcom,sw-jeita-enable` |
| 3 | **Thermal mitigation.** Register the charger as a cooling device (`#cooling-cells = <2>`) and bind it to a thermal zone, mirroring downstream's `qcom,thermal-mitigation = <2000000 1500000 1000000 500000 …>` — plus its `qcom,hw-die-temp-mitigation` and `qcom,hw-connector-mitigation` | mainline has no path at all from "the phone is hot" to "charge slower" |
| 4 | **Let the DT set the current.** Program `FAST_CHARGE_CURRENT_CFG` from `constant-charge-current-max-microamp` instead of the constant, then raise the battery node to `2700000` | this is the actual change — but it is an edit to an upstream driver whose cap is deliberate (see the comment above), so it belongs *after* 1–3, and should be discussed with its author, **Casey Connolly** (Linaro) |
| 5 | **The input side.** A DCP gives 1.5 A at 5 V, so ≈1.9 A into a 3.8 V cell at best, even with the battery-side cap gone. Downstream reaches 2.7 A by negotiating a higher `Vbus` (QC); mainline `qcom_smbx` negotiates nothing | above ~1.5 A the ceiling stops being the charger and starts being the port |

Optional but worth copying once the above works: downstream's
`qcom,step-charging-enable` (taper near full) and `qcom,auto-recharge-vbat-mv =
<4300>`.

**How to verify.** Raise in steps — 1.0 → 1.5 → 2.0 → 2.7 A — and at each step
charge from a low state of charge on both a high-current wall charger and a
plain SDP port, watching a USB power meter against what the driver reports, and
the die/connector temperatures. `fp3-selftest` covers that the charger works at
all, not that it is safe at current.

Two things worth keeping straight when reading the above. First, the board file
we edit is **Luca Weiss'** work — he has carried the FP3 in mainline since
2022-02-20; our commit is one entry in a 21-commit history (see
[Genealogy](#genealogy-of-the-board-file-21-commits-oldest-first)). Second,
several nodes we build on top of exist **only in msm8953-mainline**, not in
Linus' tree — the sound card above, [`e54a56452736`](https://github.com/llg179/linux/commit/e54a564527364e0f40cd71753dd68fe5baa3829d) hardware codec (**Sireesh
Kodali**), [`ccf0e0d540ba`](https://github.com/llg179/linux/commit/ccf0e0d540baf309e3dd6a4ff4f661773b871196) camss (**Vldly**) — which is why an upstream series
cannot assume they are there.

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
| `sdm632-fairphone-fp3.dts` | 887 | 21 | Luca Weiss' upstream FP3 board file (since 2022-02-20) **+ one commit of ours** ([`ca289613`](https://github.com/llg179/linux/commit/ca2896133002d44daee935ac45a749dab641ef45), +358) |
| `pmi632.dtsi` | 230 | 6 | upstream PMI632 PMIC description ([`a1f0f2eb`](https://github.com/torvalds/linux/commit/a1f0f2ebb044c7248c3f30b98de0f151505bd4bd)) **+ one commit of ours** ([`ca289613`](https://github.com/llg179/linux/commit/ca2896133002d44daee935ac45a749dab641ef45), +21 — the charger node) |
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
| [`308b26cddb04`](https://github.com/torvalds/linux/commit/308b26cddb04afc7776de1cbbe07172eeccc7c98) initial dts for Fairphone 3 | Luca Weiss, 2022-02-20 | ✅ v5.18-rc1 |
| [`b08f5cbd69dc`](https://github.com/torvalds/linux/commit/b08f5cbd69dcd25f5ab2a0798fe3836a97a9d7c6), [`372698e8df26`](https://github.com/torvalds/linux/commit/372698e8df2619bf76b047c9a600d1f659d7868b) gpio-key / RPM-regulator node names | tree-wide dtschema alignment, not FP3-specific | ✅ v6.0-rc1, v6.2-rc1 |
| [`6d9a666d49bf`](https://github.com/torvalds/linux/commit/6d9a666d49bf57c6a176e5fcf1b39046ee6a728f) touchscreen · [`29dcf3c1a815`](https://github.com/torvalds/linux/commit/29dcf3c1a8159acdf56905c377a214381eda5a24) NFC · [`0c4f10917d22`](https://github.com/torvalds/linux/commit/0c4f10917d22e6f36080617bfe71de1ae854ee58) notification LED · [`5b006a82a2bb`](https://github.com/torvalds/linux/commit/5b006a82a2bbc0ce18bc6b084fc8d8d9cc110001) WiFi/BT · [`2dee68e77cb5`](https://github.com/torvalds/linux/commit/2dee68e77cb5322d7cfe44f3c84ff8ae2eaf4aee) **LPASS** · [`90053b1574f8`](https://github.com/torvalds/linux/commit/90053b1574f8cff3a3b53accc496246ad2e0aec3) USB-C · [`ffaa4b5d5d07`](https://github.com/torvalds/linux/commit/ffaa4b5d5d07aed600d82929d8862263ce341a71) vibrator | Luca Weiss, one commit per feature | ✅ v6.2-rc1 … v6.11-rc1 (LPASS + WiFi/BT in v6.8-rc1) |
| [`09a3840bcb72`](https://github.com/torvalds/linux/commit/09a3840bcb72bcd9b43cbffbb7dedccf85e6d558) status properties last · [`a4600b160eca`](https://github.com/torvalds/linux/commit/a4600b160eca7f889c4b4a370d42e4619fa5162a) newlines between regulators | pure style commits, no functional change | ✅ v6.16-rc1 |
| [`9ab813d5191f`](https://github.com/torvalds/linux/commit/9ab813d5191f61301dbaeaf8e82d21e689b080f4) adsp+wcnss firmware-name · [`d0c38cbe3556`](https://github.com/torvalds/linux/commit/d0c38cbe3556fea446b9350ec597a8e9c2cdaf36) modem · [`4ea55ecb4990`](https://github.com/torvalds/linux/commit/4ea55ecb4990aa4142ddae5f713289f4101f046f) display+GPU · [`9e834e768d0b`](https://github.com/torvalds/linux/commit/9e834e768d0b2e9007cd6a5c778d2d8e3674e78f) camera fixed regulators · [`cfc22c2121cb`](https://github.com/torvalds/linux/commit/cfc22c2121cbf8bb75cb9a9993f13c17587ed55e) CCI + EEPROM | Luca Weiss | ✅ v6.16-rc1 (first two), v6.18-rc1, v7.0-rc1 (last two) |
| [`4fd8c23afa2e`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) **AW8898 amplifier** | Luca Weiss, 2025-04-06 — the `FROMLIST v2` subject prefix says it plainly | ❌ **fork-only** — still not in Linus' tree, and no equivalent landed under another hash |
| [`4335b0ae1eb6`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d) enable speaker | Luca Weiss, 2023-04-18 — builds on the AW8898 node | ❌ **fork-only**, carried along with it |
| [`60f6f604cf3c`](https://github.com/llg179/linux/commit/60f6f604cf3cda9d50364804317538b26162c747) enable venus | Luca Weiss, 2026-05-06 — already present in the 7.0.9 base too, *not* something the 7.1.3 bump brought in | ❌ **fork-only** |
| **[`ca2896133002`](https://github.com/llg179/linux/commit/ca2896133002d44daee935ac45a749dab641ef45)** integrated DT (audio + charger + camera) | **ours**, 2026-07-25 | ❌ ours, see `submit/<base>/*` |

### What our commit adds, and what it was derived from

[`ca289613`](https://github.com/llg179/linux/commit/ca2896133002d44daee935ac45a749dab641ef45) adds 375 of the 887 lines, in four separable blocks:

| block | nodes | derived from |
|---|---|---|
| **audio** | `slimbam: dma-controller@c104000`, `slim_msm: slim-ngd@c140000`, `tasha_ifd: ifd@0,0`, `wcd9335: codec@1,0` (`slim217,1a0`), `divclk1_cdc` (gpio-gate-clock), `wcd_vout_1p8`, three pin-mux nodes, and the `slim-playback`/`slim-capture` DAI links inside `&sound_card` | addresses and wiring from the downstream 4.9 tree (`msm8953.dtsi`, `msm8953-audio.dtsi`, `msm8953-ext-codec-mtp.dts`); the **node shape and the `slim217,1a0` compatible follow the existing mainline WCD9335 boards** (DragonBoard 820c, OnePlus 3), not the downstream `qcom,tasha-slim-pgd` scheme |
| **camera** | `camera@1a` (`sony,imx363`) plus the `&camss` `port@0` / `csiphy0_ep` graph | downstream `msm8953-camera-sensor-*.dtsi` data, translated to the mainline camss graph binding; sits on top of Luca's [`9e834e76`](https://github.com/torvalds/linux/commit/9e834e768d0b2e9007cd6a5c778d2d8e3674e78f) + [`cfc22c21`](https://github.com/torvalds/linux/commit/cfc22c2121cbf8bb75cb9a9993f13c17587ed55e) regulator/CCI groundwork |
| **charger** | `&pmi632_charger` and `fp3_battery` (`simple-battery`) | the counterpart of the new charger node added to `pmi632.dtsi` |
| **sound card** | extends `&sound_card` rather than rewriting it | the base already carries the AW8898/MI2S speaker path ([`4fd8c23a`](https://github.com/llg179/linux/commit/4fd8c23afa2e1d907fd981c29dd35278c53c9ea5) + [`4335b0ae`](https://github.com/llg179/linux/commit/4335b0ae1eb6e9da37e2078f5affebb937b8e18d)) |

This one commit is **integration-only** — its own message says so, and the
per-subsystem split for upstream lives on the `submit/<base>/<category>`
branches: `submit/7.1.3/audio` ([`ef0d6d3d`](https://github.com/llg179/linux/commit/ef0d6d3d0c07dcf0b43e2bd421384fa226bc8083)), `submit/7.1.3/camera` ([`f42f8162`](https://github.com/llg179/linux/commit/f42f816276289031231a8708a87db3c461cf576d)),
`submit/7.1.3/charger` ([`5c0aa3dd`](https://github.com/llg179/linux/commit/5c0aa3dd9294dc20cf99f3ef516fd56b9dd0e8f3) + [`78bf6ee3`](https://github.com/llg179/linux/commit/78bf6ee3a350618eca88b2cd8adf60baf31b22dc)). `submit/7.1.3/voice` carries no
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
