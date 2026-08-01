# FP3 rear camera on pmOS mainline

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The Sony IMX363 rear sensor and its focus actuator on the Fairphone 3 under a
mainline kernel: what is wired, and what has been measured to work.

| | |
|---|---|
| **provenance** — whose code each file is | [`../kernel/README.md`](../kernel/README.md#camera-imx363c) |
| **how it was brought up**, and the traps found on the way | [`bringup/README.md`](bringup/README.md) |
| **what is still open** | [`../TODO.md`](../TODO.md) and [`../FP3-TODO.md`](../FP3-TODO.md), items 1 and 33 |

## The shape of it

Three chips and one bus, none of them shared with anything else on the phone:

```
IMX363 @ CCI i2c-0 0x1a          the sensor: registers over Qualcomm's CCI
      |                          (an I2C master inside the camera block, not a
      |                           TLMM i2c controller)
      | 4 MIPI CSI-2 lanes
      v
CAMSS  csiphy0 -> csid0 -> ispif0 -> vfe0_rdi0 -> /dev/video0

AK7374 @ CCI i2c-0 0x0c          the focus motor, driven by mainline ak7375.c
bl24s64 @ CCI i2c-0 0x50         the module's calibration EEPROM (no driver)
```

The sensor is strapped to I²C address **0x1a** (SLASEL high on this board), is
mounted rotated 270°, and is described with `orientation = <1>` (world-facing).

Only the **RDI** path is wired: raw Bayer straight from the sensor to memory, no
`msm_vfe*_pix` entity in the graph. Debayering, white balance and everything else
is userspace's problem.

☠️ **The actuator is an AK7374 at 0x0c on this phone, and an LC898217XC at 0x72
on others** — Fairphone ships two different rear camera modules. Both drivers are
kept; the device tree describes the one this phone has, and the two variants are
not distinguishable from the device tree alone.

## What is measured to work

Sensor path measured 2026-08-01 on `linux-fp3-7.1.3-r30` (`#31-fp3`), focus on
`-r32` (`#33-fp3`).

| | |
|---|---|
| sensor probes and identifies | at CCI 0-001a, entity 184 in the media graph |
| link into CAMSS | `imx363 → msm_csiphy0` **ENABLED, IMMUTABLE**; `csiphy0 → csid0` **ENABLED** |
| format negotiation | `SRGGB10_1X10/4032x3024` accepted by **every** pad from the sensor through `vfe0_rdi0` |
| **streaming** | `VIDIOC_STREAMON` succeeds and frames arrive |
| frame size | **15 240 960 bytes**, exactly 4032 × 3024 × 10 / 8 — packed 10-bit, no padding, no short frames |
| the data is live | two consecutive frames **differ**, so it is sensor output and not a canned pattern or a stale buffer |
| **the lens moves** | sweeping `focus_absolute` gives a single interior peak: 428.7 at position 409 against 387.3 at 0 and 380.6 at 1023, with 3.4 of spread within a position and 1.3 of drift between passes |

The capture, in full — **and it needs the pipeline set up first**:

```sh
# From a cold boot the CAMSS pads sit at UYVY8_1X16/1920x1080 while the sensor
# is at SRGGB10_1X10/4032x3024, and STREAMON then fails -EPIPE. Propagate the
# sensor format down the chain before capturing anything.
for e in msm_csiphy0 msm_csid0 msm_ispif0 msm_vfe0_rdi0; do
  media-ctl -d /dev/media0 -V "'$e':0 [fmt:SRGGB10_1X10/4032x3024]"
done

v4l2-ctl -d /dev/video0 \
  --set-fmt-video=width=4032,height=3024,pixelformat=pRAA \
  --stream-mmap=4 --stream-count=2 --stream-to=/tmp/f.raw
```

☠️ **The pixel format is `pRAA`, not `RG10`**, and the `media-ctl` step is not
optional. Either mistake produces `VIDIOC_STREAMON returned -1 (Broken pipe)`
with nothing in dmesg, which reads exactly like a broken driver; both cost this
project weeks. See [`bringup/`](bringup/README.md#two-ways-to-make-streaming-fail-that-look-like-a-broken-driver).

## The focus actuator

| | |
|---|---|
| part | **AK7374**, mainline `ak7375.c` chipdef, `compatible = "asahi-kasei,ak7374"` |
| I²C address | **0x0c** on CCI master 0, shared with the sensor |
| position register | **0x00**, 10-bit code, left-aligned in the 16-bit word (shift 6) |
| standby | none; a single init write of `0x02 = 0x00` |
| supplies | `vdd` = `vreg_cam_af_2p85`, `vio` = `vreg_cam_io_1p8` |
| control | `V4L2_CID_FOCUS_ABSOLUTE`, `min=0 max=1023 step=1`, on the lens subdev |

The register map was read out of the vendor's own `libactuator_ak7374.so` and
validated against two parts mainline documents, then confirmed through the lens
by the sweep above. **Which physical direction a rising code moves the lens is
still an inference** — no position has been related to a subject distance.

## Checking it works

| check | covers |
|---|---|
| [`tests/checks/40-camera-test.sh`](../../tests/checks/40-camera-test.sh) | sensor node present, driver bound, media graph linked — three failures kept apart because they send you to different places |
| [`tests/checks/41-camera-focus-test.sh`](../../tests/checks/41-camera-focus-test.sh) | the actuator's structural half: node, lens entity, `focus_absolute` — no scene needed |
| [`tests/checks/06-dtb-test.sh`](../../tests/checks/06-dtb-test.sh) | that the booted device tree is the installed package's. ☠️ Any `apk` operation can reinstall `/boot/<board>.dtb` over a hand-deployed one, and the camera node then simply vanishes |

Neither camera check attempts a capture. The two tools that need a scene are in
[`userspace-camera/`](../../userspace-camera/README.md), and they open the video
node exclusively, so neither can run alongside a camera app:

| tool | what it is for |
|---|---|
| [`userspace-camera/focus-sweep.py`](../../userspace-camera/focus-sweep.py) | the measurement: one capture held open for the whole run, positions visited in interleaved passes of alternating direction, printing every pass plus the within-position spread and the drift |
| [`userspace-camera/focus-view.py`](../../userspace-camera/focus-view.py) | the human half: a live viewfinder with a focus slider, the same sharpness number, and a 1–16× zoom — the focus effect is invisible at 1× and obvious at 8× |

```sh
focus-sweep.py                                 # full range, 9 positions, 4 passes
focus-sweep.py --lo 280 --hi 480 --passes 6    # zoom in on the peak
systemd-run --user --unit=focus-view /usr/bin/python3 ./focus-view.py
```

☠️ Both properties of the sweep are load-bearing: a per-position capture and an
extremes-only A/B each produced a confidently wrong verdict on this phone. The
gradient is also taken between pixel *x* and *x+2*, never adjacent pixels — the
frames are raw Bayer, so neighbours are different colour planes.

## Through libcamera, which is what an app sees

Measured 2026-08-01 on `linux-fp3-7.1.3-r32` (`#33-fp3`) with libcamera 0.7.1,
**from a freshly booted phone**:

| | |
|---|---|
| enumeration | `cam -l` → `Internal back camera (/base/soc@0/cci@1b0c000/i2c-bus@0/camera@1a)` |
| pipeline handler | **`simple`**, with the **software ISP** — there is no qcom-camss handler and none is needed for the RDI-only path |
| tuning | [`imx363.yaml`](../../userspace-camera/libcamera/imx363.yaml): `BlackLevel 4096`, `Awb`, **`Af`**, `Adjust`, `Agc` |
| frame rate | **~6 fps at 4032×3024, ~30 fps at 2016×1512 and at 1920×1080** — the software ISP is the limit, and it scales, so the size an app asks for decides the preview's smoothness |
| PipeWire | device `imx363 [libcamera]`, source *Built-in Back Camera*, offering a ladder of sizes from 160×120 up |
| controls offered | `Contrast`, `Gamma`, **`AfMode`, `AfTrigger`, `AfMetering`, `AfWindows`** |

Autofocus is ours: libcamera's `simple` IPA had no AF algorithm at all, so one
was written and is carried as [a patch](../../userspace-camera/libcamera/) on the
package. What it does, and how to check it, is in
[`bringup/`](bringup/README.md#autofocus-in-libcamera).

☠️ **Only `AfMode` and `AfTrigger` reach an application.** PipeWire's libcamera
plugin maps controls to properties only for `bool`, `int32` and `float`, and
returns early for any array control (`if (cid.isArray()) return nullptr;` in
`spa/plugins/libcamera/libcamera-source.cpp`). `AfWindows` is an array of
rectangles, so tap-to-focus needs a PipeWire change as well — see
[FP3-TODO 33g](../FP3-TODO.md).

☠️ **Two libcamera clients at once can wedge the focus lens until reboot.**
Opening the lens subdevice runtime-resumes the actuator, and if that happens
while another client is tearing the camera down, the CCI transfer times out
(`ak7375 0-000c: ak7375_vcm_resume I2C failure: -110`). Runtime PM then latches
the error, so every later open returns `EINVAL`, libcamera logs *"Lens
initialisation failed, lens disabled"* and autofocus silently disappears while
the camera still streams. Sequential use is unaffected — measured
across two clean boots, four runs each. See [FP3-TODO 33f](../FP3-TODO.md).

☠️ **Unbinding and rebinding the lens driver breaks libcamera until the next
reboot.** Each bind leaves the previous ancillary media link behind, one of them
with a sink id of 0, and libcamera then refuses the whole media device with
`Failed to find MediaObject with id 0` — the camera disappears from every app,
with the actuator still working perfectly through V4L2. A reboot clears it.
