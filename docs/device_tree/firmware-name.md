# `firmware-name`: why the path stays

A review of the Fairphone 3 device tree asked for `firmware-name` to be reduced
to a bare file name, without the `qcom/msm8953/fairphone/fp3/` prefix. This page
is the answer, with the evidence, so the question does not have to be argued
twice.

> **AI-generated.** Researched and written by Claude (Opus 5) under the direction
> of Lajosházi, László Gergely. The firmware measurements below were taken from
> this phone; the upstream references are linked and can be checked.

**Short answer: the path is the current upstream convention, and the FP3 already
follows it exactly. No change.**

## What the FP3 has

```
&lpass          firmware-name = "qcom/msm8953/fairphone/fp3/adsp.mbn";
&mss_pil        firmware-name = "qcom/msm8953/fairphone/fp3/mba.mbn",
                                "qcom/msm8953/fairphone/fp3/modem.mbn";
&gpu_zap_shader firmware-name = "qcom/msm8953/fairphone/fp3/a506_zap.mbn";
&venus          firmware-name = "qcom/msm8953/fairphone/fp3/venus.mbn";
&wcnss          firmware-name = "qcom/msm8953/fairphone/fp3/wcnss.mbn";
&wcnss_iris     firmware-name = "qcom/msm8953/fairphone/fp3/WCNSS_qcom_wlan_nv.bin";
```

## What mainline has

The binding's own example, `qcom,sm6115-pas.yaml` in master:

```
firmware-name = "qcom/sm6115/adsp.mbn"
```

A merged board, `sdm845-oneplus-common.dtsi` in master:

| node | value |
|---|---|
| `&adsp_pas` | `qcom/sdm845/OnePlus/enchilada/adsp.mbn` |
| `&cdsp_pas` | `qcom/sdm845/OnePlus/enchilada/cdsp.mbn` |
| `&gpu_zap_shader` | `qcom/sdm845/OnePlus/enchilada/a630_zap.mbn` |
| `&mss_pil` | `qcom/sdm845/OnePlus/enchilada/mba.mbn`, `.../modem.mbn` |
| `&venus` | `qcom/sdm845/OnePlus/enchilada/venus.mbn` |

Same shape as the FP3's, board level included.

## Why a bare file name would not work

`qcom_q6v5_pas.c` in master takes the property verbatim. There is no path
derivation anywhere in the driver:

```c
fw_name = desc->firmware_name;
ret = of_property_read_string(pdev->dev.of_node, "firmware-name", &fw_name);
```

So `adsp.mbn` means `/lib/firmware/adsp.mbn`. Nothing installs there, and two
devices' firmware would collide on one name.

## The proposal the review is probably thinking of

There is a real series in this direction: **Dmitry Baryshkov, "arm64: qcom:
autodetect firmware paths"** (Linaro, May 2024). It does not shorten
`firmware-name` — it **removes it from the device tree entirely** and has the
kernel derive `qcom/<soc>/<board>/` by matching the root node's compatible
against a lookup table. The rationale is sound on its own terms:

> DT should describe the hardware, not the Linux-firmware locations.
> — Dmitry Baryshkov

The reception was mixed:

> I think I'm less keen on having a big lookup table in the kernel…
> — Bjorn Andersson

> To me this also looks like very over-engineered, can you elaborate more why
> this is needed?
> — Kalle Valo

And the decisive fact: **it is not in master**. The driver still reads the
property directly, and boards still carry full paths.

## Would the blobs actually collide?

Worth answering, because it is the question underneath the request. Measured on
this phone, by parsing the MBN signing metadata out of each image's hash
segment and reading the certificate chain:

| firmware | SW_ID | HW_ID | OEM_ID | MODEL_ID | signer |
|---|---|---|---|---|---|
| `adsp.mbn` | 04 | 0 | 0000 | 0000 | SecTools Test User |
| `modem.mbn` | 02 | 0 | 0000 | 0000 | SecTools Test User |
| `mba.mbn` | 01 | 0 | 0000 | 0000 | SecTools Test User |
| `wcnss.mbn` | 0D | 0 | 0000 | 0000 | SecTools Test User |
| `venus.mbn` | 0E | 0 | 0000 | 0000 | SecTools Test User |
| `a506_zap.mbn` | 14 | 0 | 0000 | 0000 | SecTools Test User |

The chain is `QPSA F4 TEST ROOT` → `QPSA F4 TEST CA` → a key labelled *"General
Use Test Key (for testing only)"*. `SW_ID` identifies the **subsystem**, not the
device. `HW_ID`, `OEM_ID` and `MODEL_ID` are all zero, so **nothing in the
signature binds these images to a Fairphone 3**.

Two things follow, and they point in opposite directions, so both are worth
stating:

* Cryptographically these would not be rejected on another msm8953 device that
  accepts the same keys. Signature-wise there is no collision to fear.
* That says nothing about the **content**. The ADSP image carries the OEM's
  audio and sensor tuning and the modem image its RF calibration, for a
  particular set of microphones, speakers, antennas and PMIC. Whether another
  vendor's blob is interchangeable was **not measured** — that would need a
  second device's firmware — and absence of evidence is not evidence here.

Even if two boards' blobs were identical, the device tree still could not say
so: the next board's certainly are not.

These are stock images, not something this port substituted. `adsp.mbn` is
byte-identical to the `adsp.mbn.stockbak` taken before any audio work
(`3ed6924da0017c5027cd78a0998bf8c3`). The test-key signing is how Fairphone
ships the device, which is consistent with its unlockable bootloader.

## The one thing worth changing

Not the path — the extension, and the FP3 is already on the right side of it.
Mainline recently moved its binding examples from `.mdt` to `.mbn`:

> All Qualcomm firmwares uploaded to linux-firmware are in MBN format, instead
> of split MDT.
> — *dt-bindings: remoteproc: qcom,sm6115-pas: Use recommended MBN firmware
> format in DTS example*

The FP3 uses `.mbn` throughout. Other msm8953 boards in the `msm8953-mainline`
fork still use `.mdt` for the zap shader; those are the dated ones.

## References

* [dt-bindings: remoteproc: qcom,sm6115-pas — Use recommended MBN firmware format](https://www.mail-archive.com/linux-kernel@vger.kernel.org/msg2584906.html)
* [Re: soc: qcom: add firmware name helper](https://www.mail-archive.com/linux-kernel@vger.kernel.org/msg2569256.html) — the Baryshkov proposal and the pushback
* [arm64: qcom: autodetect firmware paths](https://patchew.org/linux/20240521-qcom-firmware-name-v1-0-99a6d32b1e5e@linaro.org/20240521-qcom-firmware-name-v1-7-99a6d32b1e5e@linaro.org/)
* [`sdm845-oneplus-common.dtsi`](https://raw.githubusercontent.com/torvalds/linux/master/arch/arm64/boot/dts/qcom/sdm845-oneplus-common.dtsi)
* [`qcom_q6v5_pas.c`](https://raw.githubusercontent.com/torvalds/linux/master/drivers/remoteproc/qcom_q6v5_pas.c)
* [`tools/mbnid.py`](tools/mbnid.py) — the probe that produced the table above
