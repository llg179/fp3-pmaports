# Kernel changes: what we touch, whose code it is, what is new

The counterpart of [`../device_tree/README.md`](../device_tree/README.md) for the
C code. Almost nothing here is a new driver: every file is somebody else's work
with a Fairphone 3 shaped hole filled in. This page says, per file, **where it
came from and from whom**, **what we added and what that was derived from**, and
**what genuinely did not exist before**.

Measured on `integration/7.1.3` against its base `v7.1.3-r0`. Everything in the
"what we add" column was developed with the assistance of
[Claude Code](https://www.anthropic.com/claude-code); how that is recorded in the
commits, and where the result may and may not go, is in the
[top-level README](../../README.md#ai-assisted-development).

## The files

Thirteen files, 3068 insertions:

| file | Δ lines | whose code it is |
|---|---|---|
| `sound/soc/codecs/wcd9335.c` (+ `.h`) | +525 / +7 | the WCD9335 codec driver — **Srinivas Kandagatla** (Linaro), `20aedafdf492` *"ASoC: wcd9335: add support to wcd9335 codec"*, 2019-01-28 |
| `sound/soc/qcom/apq8016_sbc.c` | +140 | the msm8916 machine driver — **Srinivas Kandagatla**, `bdb052e81f62` *"ASoC: qcom: add apq8016 sound card support"*, 2015-06-10 |
| `sound/soc/qcom/qdsp6/q6voice-dai.c` | +19 | the Q6 Voice DAI — **not in Linus' tree**: **Stephan Gerhold** (2020-04-28), extended by **Vincent Knecht** (voice port controls, 2021) and **Otto Pflüger** (VoiceMMode1, 2023); carried by msm8953-mainline |
| `sound/soc/qcom/qdsp6/q6afe.c` | +35 | the AFE driver — **Srinivas Kandagatla**, `7fa2d70f9766` *"ASoC: qdsp6: q6afe: Add q6afe driver"*, 2018-05-18 |
| `drivers/slimbus/qcom-ngd-ctrl.c` | +33 | the SLIMbus NGD controller — **Srinivas Kandagatla**, `917809e2280b`, 2018-06-19 |
| `drivers/remoteproc/qcom_q6v5_pas.c` | +41 | the Hexagon PAS driver — **Bjorn Andersson**, `9e004f97161d`, 2018-09-24; today mostly Sibi Sankar, Bjorn Andersson and Luca Weiss |
| `drivers/power/supply/qcom_smbx.c` | +363 | the SMB2 charger driver — **Casey Connolly** (Linaro); the file under this name since `5ec53bcc7fce`, 2025-06-19 |
| `drivers/media/i2c/imx363.c` (+ `Kconfig`, `Makefile`) | +1568 | **new file**, but not from nothing — it keeps `Copyright (C) 2018 Intel Corporation` from the Intel IMX3xx sensor driver it is structured on |

## Audio: the WCD9335 codec

Six commits on `sound/soc/codecs/wcd9335.c`. Kandagatla's driver supports the
codec on MSM8996 boards; the FP3 is the first MSM8953 user, and capture never
worked on any of them.

| commit | what it does | where it comes from |
|---|---|---|
| `6f866f84b367` | fix codec init: select the efuse sense state before enabling sensing, set `MCLK_CFG` bit 2 | **new** — found by comparing against the downstream Qualcomm sequence |
| `44fbfd904873` | release the TX front-end hold after the ADC is up | **new** — `wcd9335_codec_enable_adc()` takes the hold and mainline never releases it, so the decimator returns exact zero. Nobody had noticed because nobody had captured audio on this codec in mainline |
| `7c02495a3d85` | take mic-bias voltage and DMIC clock rate from the DT | the property names follow the existing WCD9335 binding; the FP3's values come from Fairphone's downstream `msm8953-audio.dtsi` |
| `b07de6e52440` | MBHC headset jack detection | **revived from the 2018 MBHC series that was never merged** into mainline, adapted to this codec's measured behaviour (the insert/remove direction is a software toggle here, because `MECH_DETECT_TYPE` reads back unreliably) |
| `2dfecc09f40c` | debounce the MBHC button reports | **new** — measured on the phone: an unplug trips the button comparator 84 ms before mechanical detection notices, so unplugging headphones started the media player |
| `d7bab8e0e4fe` | expose the `DEC0..DEC8` capture gains | **new** — the registers exist and mirror the RX ones exactly; the driver simply never exposed them, so capture level could not be set at all |

## Audio: the machine driver

`09631218808a` on `sound/soc/qcom/apq8016_sbc.c` adds a SLIMbus backend, the FP3
WCD9335 card definition and the digital-microphone DAPM widgets. The SLIMbus
backend follows how the existing WCD9335 machine drivers wire the codec; the card
itself is FP3-specific and **new**.

## Audio: the Q6 DSP side

* `80dad2404f46` — `q6voice-dai.c`: wire the VoiceMMode1 / CS-Voice mixers to
  `SLIMBUS_0_RX/TX`, including the mixer → port output route. **New**, and it
  goes on top of a driver that is itself not upstream (Gerhold / Knecht /
  Pflüger, above). Without it a call could only use the MI2S speaker path.
* `114c2f0a7300` + `3221652e7fed` — `q6afe.c`: treat `ADSP_EALREADY` on
  `AFE_PORT_CMD_DEVICE_START` as success. **New**, and not FP3-specific: any two
  front ends sharing one backend hit it. Here a call and a media stream both use
  `SLIMBUS_0_RX`, the ADSP answers `ADSP_EALREADY`, and the driver turned that
  into `-EINVAL` — unrecoverable in practice, because nothing on the AP side can
  reset the ADSP's port state.

## The QDSP6SS SLIMbus framer pair

* `6cd150e75fb7` — `qcom_q6v5_pas.c`: a msm8953 ADSP descriptor
  (`qcom,msm8953-adsp-pil`) that clears QDSP6SS `0x0c20002c` bit 3 after
  `AUTH_AND_RESET`, which the downstream PIL path does and the mainline PAS path
  does not.
* `36c939972197` — `qcom-ngd-ctrl.c`: clear the same bit again immediately
  before the capability exchange, since the ADSP re-sets it during its own init.

Both are **new**, and the starting point was a 2025 LKML thread on the same
register ([lkml.iu.edu](https://lkml.iu.edu/hypermail/linux/kernel/2502.1/00985.html)).

⚠️ Their necessity is **not settled**. As last measured (2026-07-26) the SLIMbus
chain came up identically with and without the pokes, one boot each; confirming
that over a few cold boots — and then dropping both commits — is outstanding.

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

`50e36a502e28` adds SMB5 (PMI632) support to Casey Connolly's SMB2 driver. The
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
in the board's `simple-battery` node. What that costs, and what raising the 1 A
charge cap would take, is in
[`../device_tree/README.md`](../device_tree/README.md#what-it-would-take-to-charge-at-full-current).

## Where each change is headed

Per the [branch model](../../README.md#the-branch-model), each of these lives on
a `wip/<base>/<category>` branch, is cherry-picked onto `integration/<base>`, and
is distilled into `submit/<base>/<category>` for the LKML. The device-tree half
of the same work is documented in
[`../device_tree/README.md`](../device_tree/README.md).
