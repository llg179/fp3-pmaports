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

Ten files, 2980 insertions — audio, camera and charger. The `sensor` and `debug`
categories are not in this table: the SMGR/QRTR sensor stack and the watchdog
change are written up in [`../sensors/README.md`](../sensors/README.md#provenance),
where the measurements that produced them are.

| file | Δ lines | whose code it is |
|---|---|---|
| `sound/soc/codecs/wcd9335.c` (+ `.h`) | +514 / +7 | the WCD9335 codec driver — **Srinivas Kandagatla** (Linaro), [`20aedafdf492`](https://github.com/torvalds/linux/commit/20aedafdf4926e7a957f8b302a18c8fb75c7e332) *"ASoC: wcd9335: add support to wcd9335 codec"*, 2019-01-28 |
| `sound/soc/qcom/apq8016_sbc.c` | +139 | the msm8916 machine driver — **Srinivas Kandagatla**, [`bdb052e81f62`](https://github.com/torvalds/linux/commit/bdb052e81f6236b4febb50ed74f79f770fa82cc5) *"ASoC: qcom: add apq8016 sound card support"*, 2015-06-10 |
| `sound/soc/qcom/qdsp6/q6voice-dai.c` | +19 | the Q6 Voice DAI — **not in Linus' tree**: **Stephan Gerhold** (2020-04-28), extended by **Vincent Knecht** (voice port controls, 2021) and **Otto Pflüger** (VoiceMMode1, 2023); carried by msm8953-mainline |
| `sound/soc/qcom/qdsp6/q6afe.c` | +30 | the AFE driver — **Srinivas Kandagatla**, [`7fa2d70f9766`](https://github.com/torvalds/linux/commit/7fa2d70f976657111a5ea4f3d16a738ddaa10c4f) *"ASoC: qdsp6: q6afe: Add q6afe driver"*, 2018-05-18 |
| `drivers/power/supply/qcom_smbx.c` | +688 / −34 | the SMB2 charger driver — **Casey Connolly** (Linaro); the file under this name since [`5ec53bcc7fce`](https://github.com/torvalds/linux/commit/5ec53bcc7fce6801977a0c125fb726d7b0e9102c), 2025-06-19 |
| `drivers/iio/adc/qcom-spmi-adc5.c` | +2 | the PMIC ADC5 driver — **Siddartha Mohanadoss**, [`e13d757279bb`](https://github.com/torvalds/linux/commit/e13d757279bb2c2fa32e5b578dd1cbcac4d51e21) *"iio: adc: Add QCOM SPMI PMIC5 ADC driver"*, 2018-08-02 |
| `drivers/media/i2c/imx363.c` (+ `Kconfig`, `Makefile`) | +1568 | **new file**, but not from nothing — it keeps `Copyright (C) 2018 Intel Corporation` from the Intel IMX3xx sensor driver it is structured on |

`drivers/slimbus/qcom-ngd-ctrl.c` and `drivers/remoteproc/qcom_q6v5_pas.c` used
to be in this list. Both changes were **reverted on 2026-07-29** after
measurement showed they did nothing; see
[the framer pair](#the-qdsp6ss-slimbus-framer-pair--removed) below.

## Provenance

The same three questions the [sensor stack](../sensors/README.md#provenance) is
sorted by: what is carried unchanged, what is somebody else's code that we
extended, and what did not exist before.

### Imported unchanged

**Nothing.** Unlike the sensor stack, which carries Yassine Oudjana's SMGR
series verbatim, every file above is an in-place change to code that was
already in the base. The one wholly new file, `imx363.c`, is not an import
either — see [New here](#new-here).

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
| IMX363 sensor | `imx363.c` | **Intel** — [`imx319.c`](https://github.com/torvalds/linux/blob/master/drivers/media/i2c/imx319.c) / [`imx355.c`](https://github.com/torvalds/linux/blob/master/drivers/media/i2c/imx355.c), 2018 | the probe/power/control skeleton and v4l2-cci register style are theirs, and the copyright line stays |

### New here

Written for this port; author Lajosházi, László Gergely with Claude.

| component | where | state |
|---|---|---|
| FP3 WCD9335 sound card + DMIC widgets | `apq8016_sbc.c` | working |
| IMX363 register programming and FP3 power sequence | `imx363.c` | sensor probes; streaming blocked on the CAMSS side |
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
| [`6f866f84b367`](https://github.com/llg179/linux/commit/6f866f84b36778c72031daec9af588495da6237d) | fix codec init: select the efuse sense state before enabling sensing, set `MCLK_CFG` bit 2 | **new** — found by comparing against the downstream Qualcomm sequence |
| [`44fbfd904873`](https://github.com/llg179/linux/commit/44fbfd90487329988f8577dd19f2789384e8ee01) | release the TX front-end hold after the ADC is up | **new** — `wcd9335_codec_enable_adc()` takes the hold and mainline never releases it, so the decimator returns exact zero. Nobody had noticed because nobody had captured audio on this codec in mainline |
| [`7c02495a3d85`](https://github.com/llg179/linux/commit/7c02495a3d85dc98ebc1b1d2986a5e2c32d501aa) | take mic-bias voltage and DMIC clock rate from the DT | the property names follow the existing WCD9335 binding; the FP3's values come from Fairphone's downstream `msm8953-audio.dtsi` |
| [`b07de6e52440`](https://github.com/llg179/linux/commit/b07de6e5244050318b4c20e99fe5e957e9a44f80) | MBHC headset jack detection | **revived from the 2018 MBHC series that was never merged** into mainline, adapted to this codec's measured behaviour (the insert/remove direction is a software toggle here, because `MECH_DETECT_TYPE` reads back unreliably) |
| [`2dfecc09f40c`](https://github.com/llg179/linux/commit/2dfecc09f40cabe61da33a13ca95564ba8f6010e) | debounce the MBHC button reports | **new** — measured on the phone: an unplug trips the button comparator 84 ms before mechanical detection notices, so unplugging headphones started the media player |
| [`d7bab8e0e4fe`](https://github.com/llg179/linux/commit/d7bab8e0e4fe97c6efba783e42f6e95d0fc772cc) | expose the `DEC0..DEC8` capture gains | **new** — the registers exist and mirror the RX ones exactly; the driver simply never exposed them, so capture level could not be set at all |

## Audio: the machine driver

[`09631218808a`](https://github.com/llg179/linux/commit/09631218808a257ad75d7feac3eca519d6e3896e) on `sound/soc/qcom/apq8016_sbc.c` adds a SLIMbus backend, the FP3
WCD9335 card definition and the digital-microphone DAPM widgets. The SLIMbus
backend follows how the existing WCD9335 machine drivers wire the codec; the card
itself is FP3-specific and **new**.

## Audio: the Q6 DSP side

* [`80dad2404f46`](https://github.com/llg179/linux/commit/80dad2404f4661188ed90c496e6118ddea5a7296) — `q6voice-dai.c`: wire the VoiceMMode1 / CS-Voice mixers to
  `SLIMBUS_0_RX/TX`, including the mixer → port output route. **New**, and it
  goes on top of a driver that is itself not upstream (Gerhold / Knecht /
  Pflüger, above). Without it a call could only use the MI2S speaker path.
* [`114c2f0a7300`](https://github.com/llg179/linux/commit/114c2f0a73001f0597965650f64d7ea0b4fa54af) + [`3221652e7fed`](https://github.com/llg179/linux/commit/3221652e7fed39fb555a351b31337d55787dc865) — `q6afe.c`: treat `ADSP_EALREADY` on
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

A new 1568-line driver, and the only file here that is entirely ours in
substance, with two acknowledgements:

* it is **structured on Intel's IMX3xx sensor drivers** (2018) and keeps their
  copyright line — the probe/power/control skeleton and the v4l2-cci register
  style come from there;
* the **register programming was reverse-engineered from the sensor as wired on
  the FP3** (same family as the Pixel 3a), together with the FP3-specific
  bring-up: MCLK-before-reset power sequence with settling delays, a chip-id read
  retry after power-up, and an I²C link warm-up on every `power_on()` to avoid
  stream-start timeouts.

## Charger: `qcom_smbx.c`

[`50e36a502e28`](https://github.com/llg179/linux/commit/50e36a502e28ae8726ca70dadf83ac8806d082fe) adds SMB5 (PMI632) support to Casey Connolly's SMB2 driver. The
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

Three further commits turn the charge current from a constant into something the
board describes, and add the two guards that made raising it defensible:

| commit | what it adds |
|---|---|
| [`51803fe941cb`](https://github.com/llg179/linux/commit/51803fe941cb825a5fe8d26e3d2a8a7374296758) | the hardware JEITA comparator thresholds and the per-soft-zone charge currents, from the device tree. The block was already *running* on the PMIC's generic defaults; this replaces them with the pack's characterised values, carried as raw ADC codes |
| [`5a736a69f51e`](https://github.com/llg179/linux/commit/5a736a69f51e3a473776cc9c1c5c8f4b51b9a2f5) | the fast-charge current as a `thermal_cooling_device`, so a thermal zone can throttle charging the way it throttles a CPU |
| [`20c8679e024c`](https://github.com/llg179/linux/commit/20c8679e024c384b38f66e9d07a612be9b911883) | `constant-charge-current-max-microamp` actually reaching the hardware, bounded by a new per-generation ceiling so the deliberate ~1 A cap survives where nobody has measured otherwise |

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

## Where each change is headed

Per the [branch model](../../README.md#the-branch-model), each of these lives on
a `wip/<base>/<category>` branch, is cherry-picked onto `integration/<base>`, and
is distilled into `submit/<base>/<category>` for the LKML. The device-tree half
of the same work is documented in
[`../device_tree/README.md`](../device_tree/README.md).
