# Kernel changes: what we touch, whose code it is, what is new

The counterpart of [`../device_tree/README.md`](../device_tree/README.md) for the
C code. Almost nothing here is a new driver: every file is somebody else's work
with a Fairphone 3 shaped hole filled in. This page says, per file, **where it
came from and from whom**, **what we added and what that was derived from**, and
**what genuinely did not exist before**.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who reviewed every change it describes.
> Where a file is somebody else's work, the table says so; where the assistant
> wrote it, the provenance line says that too.

Measured on `integration/7.1.3` against its base `v7.1.3-r0`. Everything in the
"what we add" column was developed with the assistance of
[Claude Code](https://www.anthropic.com/claude-code); how that is recorded in the
commits, and where the result may and may not go, is in the
[top-level README](../../README.md#ai-assisted-development).

## The files

Eleven files, 3168 insertions — audio, camera and charger. The `sensor` and
`debug` categories are not in this table: the SMGR/QRTR sensor stack and the
watchdog change are written up in
[`../sensors/README.md`](../sensors/README.md#provenance), where the measurements
that produced them are.

| file | Δ lines | whose code it is |
|---|---|---|
| `sound/soc/codecs/wcd9335.c` (+ `.h`) | +514 / +7 | the WCD9335 codec driver — **Srinivas Kandagatla** (Linaro), [`20aedafdf492`](https://github.com/torvalds/linux/commit/20aedafdf4926e7a957f8b302a18c8fb75c7e332) *"ASoC: wcd9335: add support to wcd9335 codec"*, 2019-01-28 |
| `sound/soc/qcom/apq8016_sbc.c` | +139 | the msm8916 machine driver — **Srinivas Kandagatla**, [`bdb052e81f62`](https://github.com/torvalds/linux/commit/bdb052e81f6236b4febb50ed74f79f770fa82cc5) *"ASoC: qcom: add apq8016 sound card support"*, 2015-06-10 |
| `sound/soc/qcom/qdsp6/q6voice-dai.c` | +19 | the Q6 Voice DAI — **not in Linus' tree**: **Stephan Gerhold** (2020-04-28), extended by **Vincent Knecht** (voice port controls, 2021) and **Otto Pflüger** (VoiceMMode1, 2023); carried by msm8953-mainline |
| `sound/soc/qcom/qdsp6/q6afe.c` | +30 | the AFE driver — **Srinivas Kandagatla**, [`7fa2d70f9766`](https://github.com/torvalds/linux/commit/7fa2d70f976657111a5ea4f3d16a738ddaa10c4f) *"ASoC: qdsp6: q6afe: Add q6afe driver"*, 2018-05-18 |
| `drivers/power/supply/qcom_smbx.c` | +802 / −34 | the SMB2 charger driver — **Casey Connolly** (Linaro); the file under this name since [`5ec53bcc7fce`](https://github.com/torvalds/linux/commit/5ec53bcc7fce6801977a0c125fb726d7b0e9102c), 2025-06-19 |
| `drivers/iio/adc/qcom-spmi-adc5.c` | +2 | the PMIC ADC5 driver — **Siddartha Mohanadoss**, [`e13d757279bb`](https://github.com/torvalds/linux/commit/e13d757279bb2c2fa32e5b578dd1cbcac4d51e21) *"iio: adc: Add QCOM SPMI PMIC5 ADC driver"*, 2018-08-02 |
| `drivers/media/i2c/imx363.c` (+ `Kconfig`, `Makefile`) | +1568 | **not ours** — taken from `panpanpanpan/linux`, branch `imx363wip`, where it was reverse-engineered for a Pixel-3a-family sensor; that file in turn keeps `Copyright (C) 2018 Intel Corporation` from the Intel IMX3xx driver it is structured on. See [Camera](#camera-imx363c) |
| `Documentation/devicetree/bindings/power/supply/qcom,pmi8998-charger.yaml` | +73 / −1 | the SMB2 charger binding — **Casey Connolly**, added with the driver; extended here for the PMI632 |

`drivers/slimbus/qcom-ngd-ctrl.c` and `drivers/remoteproc/qcom_q6v5_pas.c` used
to be in this list. Both changes were **reverted on 2026-07-29** after
measurement showed they did nothing; see
[the framer pair](#the-qdsp6ss-slimbus-framer-pair--removed) below.

## Provenance

The same three questions the [sensor stack](../sensors/README.md#provenance) is
sorted by: what is carried unchanged, what is somebody else's code that we
extended, and what did not exist before.

### Imported unchanged

**`drivers/media/i2c/imx363.c`** arrived as somebody else's file and was then
modified here, so it is an import first and an extension second — the same shape
as the sensor stack, which carries Yassine Oudjana's SMGR series. This was
**recorded wrongly on this page until 2026-07-30**, where it said the driver was
"entirely ours in substance"; see [Camera](#camera-imx363c).

Every other file above is an in-place change to code that was already in the
base.

### Imported and extended here

| component | file | whose code | what we added |
|---|---|---|---|
| WCD9335 codec | `wcd9335.c` | Srinivas Kandagatla, [`20aedafdf492`](https://github.com/torvalds/linux/commit/20aedafdf4926e7a957f8b302a18c8fb75c7e332) | init fix, TX front-end hold release, DT-driven mic bias and DMIC rate, MBHC jack detection, button debounce, capture gains |
| MBHC jack detection | `wcd9335.c` | Kandagatla's **[2018 MBHC series](https://lkml.iu.edu/hypermail/linux/kernel/1809.3/03254.html), which never merged** | revived onto today's driver and adapted to measured behaviour: the insert/remove direction is a software toggle here because `MECH_DETECT_TYPE` reads back unreliably |
| msm8916 machine driver | `apq8016_sbc.c` | Kandagatla, [`bdb052e81f62`](https://github.com/torvalds/linux/commit/bdb052e81f6236b4febb50ed74f79f770fa82cc5) | a SLIMbus backend, following how the existing WCD9335 machine drivers wire the codec |
| Q6 Voice DAI | `q6voice-dai.c` | Gerhold / Knecht / Pflüger — **not upstream**, carried by [msm8953-mainline](https://github.com/msm8953-mainline/linux/blob/v7.1.3-r0/sound/soc/qcom/qdsp6/q6voice-dai.c) | the VoiceMMode1 / CS-Voice mixer routes to `SLIMBUS_0_RX/TX`, including the mixer → port output edge |
| Q6 AFE | `q6afe.c` | Kandagatla, [`7fa2d70f9766`](https://github.com/torvalds/linux/commit/7fa2d70f976657111a5ea4f3d16a738ddaa10c4f) | `ADSP_EALREADY` on `AFE_PORT_CMD_DEVICE_START` treated as success |
| SMB2 charger | `qcom_smbx.c` | Casey Connolly, [`5ec53bcc7fce`](https://github.com/torvalds/linux/commit/5ec53bcc7fce6801977a0c125fb726d7b0e9102c) | the SMB5 variant abstraction, PMI632 support, `POWER_SUPPLY_PROP_TEMP` |
| PMIC ADC5 | `qcom-spmi-adc5.c` | Siddartha Mohanadoss, [`e13d757279bb`](https://github.com/torvalds/linux/commit/e13d757279bb2c2fa32e5b578dd1cbcac4d51e21) | the `BAT_THERM` channel table entry — the scaling curve it points at was already there |
| IMX363 sensor | `imx363.c` | **`panpanpanpan/linux:imx363wip`** (an sdm670-mainline merge request), reverse-engineered there; structured in turn on an **Intel** IMX3xx driver whose copyright line stays | the FP3 bring-up only: the I²C address, a chip-id retry with a 200 ms power-up delay, `vdig` at 1.175 V, MCLK before reset, and an I²C warm-up in `power_on()`. **The register tables came with the import** |

### New here

Written for this port; author Lajosházi, László Gergely with Claude.

| component | where | state |
|---|---|---|
| FP3 WCD9335 sound card + DMIC widgets | `apq8016_sbc.c` | working |
| IMX363 **power sequence and I²C bring-up** (not the register tables) | `imx363.c` | sensor probes; streaming blocked on the CAMSS side |
| Battery temperature | `qcom_smbx.c`, `qcom-spmi-adc5.c`, `pmi632.dtsi` | see [Battery temperature](#battery-temperature) |

### Fixes to pre-existing kernel code

| file | fix |
|---|---|
| `wcd9335.c` | `wcd9335_codec_enable_adc()` takes the TX front-end hold and mainline never releases it, so the decimator returns exact zero. Nobody had noticed because nobody had captured audio on this codec in mainline |
| `wcd9335.c` | the `DEC0..DEC8` capture gain registers exist and mirror the RX ones exactly; the driver simply never exposed them, so capture level could not be set at all |
| `q6afe.c` | `ADSP_EALREADY` became `-EINVAL`, which is unrecoverable in practice — nothing on the AP side can reset the ADSP's port state. Not FP3-specific: any two front ends sharing one backend hit it |
| `qcom-spmi-adc5.c` | `ADC5_BAT_THERM_100K_PU` was missing from the channel table, so a device tree referencing the battery thermistor was rejected at probe |

### Values taken from the vendor

Read out of Fairphone's published kernel source release. Its **device trees are
checked in here**, under
[`../device_tree/downstream/fairphone/3.A.0136/`](../device_tree/downstream/fairphone/3.A.0136/),
so those links stay valid whatever happens upstream. The **driver sources are
not** — for those the links point at
[UBports' publication of the same tree](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632),
which is the same 4.9 kernel with the Halium patches on top.

| what | source |
|---|---|
| mic-bias voltage, DMIC clock rate | downstream [`msm8953-audio.dtsi`](../device_tree/downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/msm8953-audio.dtsi) |
| the codec init sequence the fix was found against | downstream [`techpack/audio/asoc/codecs/wcd9335.c`](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632/-/blob/halium-10.0/techpack/audio/asoc/codecs/wcd9335.c) |
| SMB5 register offsets, current step, charge-status bit positions | downstream [`qpnp-smb2.c`](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632/-/blob/halium-10.0/drivers/power/supply/qcom/qpnp-smb2.c) / [`qpnp-smb5.c`](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632/-/blob/halium-10.0/drivers/power/supply/qcom/qpnp-smb5.c), [`smb5-reg.h`](https://gitlab.com/ubports/porting/community-ports/android10/fairphone/android_kernel_fairphone_sdm632/-/blob/halium-10.0/drivers/power/supply/qcom/smb5-reg.h) |
| PMI632 interrupt numbers and ADC channel assignment | downstream [`pmi632.dtsi`](../device_tree/downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/pmi632.dtsi) |
| `BAT_THERM` channel number, 100k pull-up, ratiometric calibration | downstream [`pmi632.dtsi`](../device_tree/downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/pmi632.dtsi), `chan@4a` |
| the OCV curve behind `capacity` | downstream [`qg-batterydata-Kayo-3000mah-Nov4th2019-pmi632.dtsi`](../device_tree/downstream/fairphone/3.A.0136/arch/arm64/boot/dts/qcom/qg-batterydata-Kayo-3000mah-Nov4th2019-pmi632.dtsi) |

## Audio: the WCD9335 codec

Six commits on `sound/soc/codecs/wcd9335.c`. Kandagatla's driver supports the
codec on MSM8996 boards; the FP3 is the first MSM8953 user, and capture never
worked on any of them.

| commit | what it does | where it comes from |
|---|---|---|
| [`b3a83765fa54`](https://github.com/llg179/linux/commit/b3a83765fa54) | fix codec init: select the efuse sense state before enabling sensing, set `MCLK_CFG` bit 2 | **new** — found by comparing against the downstream Qualcomm sequence |
| [`ad3bfc32011b`](https://github.com/llg179/linux/commit/ad3bfc32011b) | release the TX front-end hold after the ADC is up | **new** — `wcd9335_codec_enable_adc()` takes the hold and mainline never releases it, so the decimator returns exact zero. Nobody had noticed because nobody had captured audio on this codec in mainline |
| [`cb8efad0cd2a`](https://github.com/llg179/linux/commit/cb8efad0cd2a) | take mic-bias voltage and DMIC clock rate from the DT | the property names follow the existing WCD9335 binding; the FP3's values come from Fairphone's downstream `msm8953-audio.dtsi` |
| [`742ab5a8236a`](https://github.com/llg179/linux/commit/742ab5a8236a) | MBHC headset jack detection | **revived from the 2018 MBHC series that was never merged** into mainline, adapted to this codec's measured behaviour (the insert/remove direction is a software toggle here, because `MECH_DETECT_TYPE` reads back unreliably) |
| [`371b3fa4d85a`](https://github.com/llg179/linux/commit/371b3fa4d85a) | debounce the MBHC button reports | **new** — measured on the phone: an unplug trips the button comparator 84 ms before mechanical detection notices, so unplugging headphones started the media player |
| [`85e5cebf6dad`](https://github.com/llg179/linux/commit/85e5cebf6dad) | expose the `DEC0..DEC8` capture gains | **new** — the registers exist and mirror the RX ones exactly; the driver simply never exposed them, so capture level could not be set at all |

## Audio: the machine driver

[`35f5d0f76e5d`](https://github.com/llg179/linux/commit/35f5d0f76e5d) on `sound/soc/qcom/apq8016_sbc.c` adds a SLIMbus backend, the FP3
WCD9335 card definition and the digital-microphone DAPM widgets. The SLIMbus
backend follows how the existing WCD9335 machine drivers wire the codec; the card
itself is FP3-specific and **new**.

## Audio: the Q6 DSP side

* [`34f6f8bf16a6`](https://github.com/llg179/linux/commit/34f6f8bf16a6) — `q6voice-dai.c`: wire the VoiceMMode1 / CS-Voice mixers to
  `SLIMBUS_0_RX/TX`, including the mixer → port output route. **New**, and it
  goes on top of a driver that is itself not upstream (Gerhold / Knecht /
  Pflüger, above). Without it a call could only use the MI2S speaker path.
* [`867e40aa8ebd`](https://github.com/llg179/linux/commit/867e40aa8ebd) + [`6f5f64855a18`](https://github.com/llg179/linux/commit/6f5f64855a18) — `q6afe.c`: treat `ADSP_EALREADY` on
  `AFE_PORT_CMD_DEVICE_START` as success. **New**, and not FP3-specific: any two
  front ends sharing one backend hit it. Here a call and a media stream both use
  `SLIMBUS_0_RX`, the ADSP answers `ADSP_EALREADY`, and the driver turned that
  into `-EINVAL` — unrecoverable in practice, because nothing on the AP side can
  reset the ADSP's port state.

## The QDSP6SS SLIMbus framer pair — removed

Two commits used to clear QDSP6SS `0x0c20002c` bit 3, one in `qcom_q6v5_pas.c`
after `AUTH_AND_RESET` and one in `qcom-ngd-ctrl.c` before the capability
exchange, plus the `qcom,slim-framer-quirk-reg` device tree property that armed
the second. **All three are gone since 2026-07-29**, reverted after measurement
showed the codec comes up, and sound crosses SLIMbus in both directions,
without them — and that the PAS one never wrote anything in the first place
(`0x101->0x101`).

The whole story, including the log lines that read like faults and are not, is
in [`../audio/bringup/qdsp6ss-framer-poke.md`](../audio/bringup/qdsp6ss-framer-poke.md).

## Camera: `imx363.c`

**This section was wrong until 2026-07-30 and is the reason the camera series is
not submittable.** It used to say the driver was "the only file here that is
entirely ours in substance" and that "the register programming was
reverse-engineered from the sensor as wired on the FP3". Neither is true, and the
commit message on `submit/7.1.3/camera` still says the same thing.

What the evidence says. The file was **downloaded**, not written: this repo's own
bring-up notes name the source as `panpanpanpan/linux`, branch `imx363wip`, an
sdm670-mainline merge request carrying a reverse-engineered v4l2-cci driver of
1514 lines, produced against a Pixel-3a-family sensor. Ours is 1568 lines. That
file is itself structured on an Intel IMX3xx driver and keeps
`Copyright (C) 2018 Intel Corporation` plus the three Intel `MODULE_AUTHOR`
lines. And the register values are not measurements — the source says so itself,
in 95 `//` comments including:

```c
//Magical IMX363 Regs & Values - Found in downstream.
// basically frame length lines? from downstream
// present in imx258. not present in android downstream logs.
636000000ULL, // NOT SURE HOW TO FIND THIS VALUE
```

The last one is a link frequency the author could not account for. Related and
still open: the driver's two modes carry link frequencies that **disagree with
the DT's `link-frequencies`**, which is the deepest known problem in the camera
bring-up.

What actually is ours is the FP3 bring-up on top of that import:

* the I²C address — `0x1a`, not the `0x10` the imported driver assumed. The FP3
  straps SLASEL high; confirmed by reading `0x0016` and getting `0x0363` at
  `0x1a`;
* a chip-id read retry plus a 200 ms power-up delay;
* `regulator_set_voltage(vdig, 1175000)` — downstream asks for 1.175 V;
* MCLK before reset in the power sequence;
* an I²C link warm-up dummy read in `power_on()`, without which the first stream
  start times out.

**Before this goes anywhere:** the import needs to be its own commit, keeping the
original author, citing repo, branch, commit, author and date, with the five
changes above in a follow-up — the split
[the submission skill requires](../../README.md#ai-assisted-development). The
exact upstream file has **not** been retrieved (the merge request is on GitLab,
and a GitHub fetch of that path returns nothing), so **the size of our delta is
unmeasured**; establishing it is the first step, not an estimate.

## Charger: `qcom_smbx.c`

[`24e5c045b8fc`](https://github.com/llg179/linux/commit/24e5c045b8fc) adds SMB5 (PMI632) support to Casey Connolly's SMB2 driver. The
differences are described in the variant structure rather than open-coded: the
status register prefix (MISC `0x600` on SMB2, DCDC `0x100` on SMB5), the current
step (25 mA vs 50 mA), the charge-status bit positions, and the JEITA status
register, which SMB5 moved into `BATTERY_CHARGER_STATUS_7`.

**Where the numbers come from:** Qualcomm's downstream `qpnp-smb2` and
`qpnp-smb5` drivers, published in the Fairphone 3 kernel source release — the
same release checked in under
[`../device_tree/downstream/fairphone/3.A.0136/`](../device_tree/downstream/fairphone/3.A.0136/).
**New** is the variant abstraction and the PMI632 support itself; PMI632 also has
no coulomb-counting fuel gauge in mainline, so capacity comes from the OCV table
in the board's `simple-battery` node.

Six further commits turn the charge current from a constant into something the
board describes, add the two guards that made raising it defensible, and then
put each of those values at the layer that owns it:

| commit | what it adds |
|---|---|
| [`51803fe941cb`](https://github.com/llg179/linux/commit/51803fe941cb825a5fe8d26e3d2a8a7374296758) | the hardware JEITA comparator thresholds and the per-soft-zone charge currents. The block was already *running* on the PMIC's generic defaults; this replaces them with the pack's characterised values, carried as raw ADC codes |
| [`5a736a69f51e`](https://github.com/llg179/linux/commit/5a736a69f51e3a473776cc9c1c5c8f4b51b9a2f5) | the fast-charge current as a `thermal_cooling_device`, so a thermal zone can throttle charging the way it throttles a CPU |
| [`20c8679e024c`](https://github.com/llg179/linux/commit/20c8679e024c384b38f66e9d07a612be9b911883) | `constant-charge-current-max-microamp` actually reaching the hardware |
| [`5c8991aaa5b2`](https://github.com/llg179/linux/commit/5c8991aaa5b23ef39574c05021339274acbedc26) | **the ceiling on it becomes the PMIC's datasheet maximum** rather than a policy number. The previous commit had bounded the device tree with a new per-generation constant — 2 A on the PMI632, which is the rating of one Fairphone's battery, not of the chip — so every other PMI632 board would have been held to it |
| [`60afc91548aa`](https://github.com/llg179/linux/commit/60afc91548aa7edeb7c44ce710fcd966ccf3bc44) | the JEITA description read from the **battery** node instead of the charger's. Which temperatures a cell may be charged at is a property of the cell, and with it on the charger a board could not describe two packs |
| [`bac69263baf0`](https://github.com/llg179/linux/commit/bac69263baf0d24619d8aac20e1e3efe629cb828) | the battery ID verified before any of the battery's limits are applied, so a board that names one pack cannot silently charge the other to it |
| [`c8974511d585`](https://github.com/llg179/linux/commit/c8974511d585fa02a496797ddbb91fc395b0b801) | thermal mitigation clamps to the programmed current instead of refusing to probe above it — otherwise the outcome of the fallback above was a phone with no charger driver |
| [`dd590915e536`](https://github.com/llg179/linux/commit/dd590915e536) | the **binding**: `qcom,pmi632-charger` documented in the existing `qcom,pmi8998-charger.yaml` rather than a second file, together with the three optional io-channels, `qcom,thermal-mitigation`, `#cooling-cells` and `qcom,batt-id-pullup-ohm`. This closed the last `checkpatch` item on the submit series |
| [`76974ab78023`](https://github.com/llg179/linux/commit/76974ab78023) | the cooling-map nodes renamed to `map-charger-*`, because `thermal-zones.yaml` requires `^map[-a-zA-Z0-9]*$` and the original `charger-warm` failed `dtbs_check`. Nothing reads those names at runtime |

Why the result is 2 A and not the pack's rated 2.7 A, what the JEITA
compensation register can and cannot express, and the register-level
before/after are all on the charger page:
[**`../charger/README.md`**](../charger/README.md).

### Battery temperature

The pack thermistor sits on the same PMIC ADC as `VBAT_SNS`, so reporting a
temperature took one more channel — but the channel was unusable: `ADC5_BAT_THERM_100K_PU`
was missing from `qcom-spmi-adc5.c`'s channel table, so any device tree
referencing it was rejected at probe. Three commits: the ADC channel, the
`POWER_SUPPLY_PROP_TEMP` in `qcom_smbx.c` (optional, like `VBAT_SNS` — a board
that does not route the thermistor keeps a battery without a temperature), and
the PMI632 device-tree channel.

**The curve is approximate, and knowingly so.** The driver scales it with the
generic 100k pull-up thermistor table that mainline already uses for the AMUX
and GPIO thermistor channels. Fairphone's downstream kernel carries its *own*
table for this pack — the comment above it says as much: *"Fill the correct NTC
table for 8901 battery"*. Comparing the two, the tables agree exactly at 25 °C
and diverge with distance from it: about 1.5 °C high at 0 °C, 1 °C low at 40 °C,
2.5 °C low at 60 °C. Same 100 kΩ nominal thermistor, slightly different beta.
That is good enough to report a temperature and to notice a hot battery; it is
not good enough to drive a JEITA charging profile, and nothing here does.

**Measured on the phone**, `linux-fp3-7.1.3-r19` (`#20-fp3`). At idle the pack
reads 28.5 °C against a 37 °C PMIC die and 41 °C CPUs — the right order for a
lump of lithium inside a warm phone. That it is a live thermistor and not a
plausible constant was checked by driving all eight cores flat out and then
letting it cool:

| | battery | CPU0 |
|---|---|---|
| idle | 28.6 °C | 41 °C |
| 90 s of load | 30.2 °C | 74 °C |
| 4½ min of load | 34.4 °C | 80 °C |
| 6 min after load stopped | 31.6 °C | 37 °C |

The pack rises and falls monotonically, an order of magnitude more slowly than
the silicon, and lags it in both directions. `POWER_SUPPLY_PROP_TEMP` also gets
the battery a `pmi632-battery` thermal zone from the power supply core, so
userspace sees it the same way it sees `tsens`.

The regression check is [`51-battery-temp`](../../tests/checks/51-battery-temp-test.sh),
kept **separate from `50-charger`** on purpose: that one declares
`Requires: cable` and is skipped whole without one, while the thermistor is read
through the ADC whether anything is charging or not. Folding it in there would
have hidden the property in exactly the runs that do not plug the phone in.

## What the checkers say

Run on 2026-07-30, per submit branch. `checkpatch.pl --strict --git` over each
series, and `dtbs_check` with `dtschema` 2026.6 — the latter **as a differential**,
because the base tree fails it 44 times on its own (`opp-avg-kBps`, `qfprom`,
`gcc` power domains, `rpm-proc`). Only the errors this tree *adds* are ours:

| series | checkpatch | what `dtbs_check` blames on us |
|---|---|---|
| `charger` | **clean** (9 patches, 0/0/0) | the `battery` node's four `qcom,*` properties |
| `sensor` | **clean** (1 patch) | — |
| `voice` | **clean** (1 patch) | — |
| `audio` | 3 × `ENOTSUPP`, 2 × `slim217` — **both false**, see below | three: the codec node's six `qcom,*` properties; `divclk1` and `wcd-vout-1p8` needing `ranges` under `soc@0`; `wcd-intr-default-state` failing the pinctrl schema |
| `camera` | undocumented `sony,imx363` ×2, MAINTAINERS, 2 over-long lines, a missing blank line, `printk(KERN_INFO)` ×2 | — |
| (`debug`) | not submitted by design | `qcom,start-at-probe` — undocumented on purpose |

The two dismissed audio warnings, checked rather than assumed:

* **`ENOTSUPP`.** `snd_soc_dai_set_channel_map()` and `get_channel_map()` return
  exactly that (`sound/soc/soc-dai.c`), the base `apq8016_sbc.c` already compares
  against it twice, and six other qcom machine drivers do the same. Taking
  checkpatch's advice and switching to `EOPNOTSUPP` would break the comparison.
* **`slim217`.** Genuinely absent from `vendor-prefixes.yaml`, but four device
  trees already in Linus' tree use it (db820c, OnePlus 3/3T, Xiaomi, sdm845).
  A tree-wide gap, not something this port introduced.

What each of the remaining errors needs is listed in
[`../TODO.md`](../TODO.md#open-before-anything-is-submitted).

## Where each change is headed

Per the [branch model](../../README.md#the-branch-model), each of these lives on
a `wip/<base>/<category>` branch, is cherry-picked onto `integration/<base>`, and
is distilled into `submit/<base>/<category>` for the LKML. The device-tree half
of the same work is documented in
[`../device_tree/README.md`](../device_tree/README.md).

As of 2026-07-30 every `submit` branch has an end state **byte-identical** to its
`wip` branch, with one deliberate exception: `submit/7.1.3/sensor` carries **one**
of that category's twelve commits, for the reasons in
[`../sensors/README.md`](../sensors/README.md#why-the-submit-series-is-one-patch).
All five branches are based on the `v7.1.3-r0` release, so sending any of them
still means rebasing first — ASoC onto `sound/for-next`, device trees onto
mainline.
