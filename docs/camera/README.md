# FP3 rear camera on pmOS mainline

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The Sony IMX363 rear sensor on the Fairphone 3 under a mainline kernel: what is
wired, what has been measured to work, and what has not been established.

**Almost none of this is our code.** The driver is Joel Selvaraj's, imported and
then given a Fairphone 3 power sequence. Who wrote what, and how the delta was
measured, is in
[`../kernel/README.md`](../kernel/README.md#camera-imx363c) — that page is
authoritative on provenance and this one does not repeat it. Open items live in
[`../TODO.md`](../TODO.md) and [`../FP3-TODO.md`](../FP3-TODO.md).

## The shape of it

Two chips and one bus, none of them shared with anything else on the phone:

```
IMX363 @ CCI i2c-0 0x1a          the sensor: registers over Qualcomm's CCI
      |                          (an I2C master inside the camera block, not a
      |                           TLMM i2c controller)
      | 4 MIPI CSI-2 lanes
      v
CAMSS  csiphy0 -> csid0 -> ispif0 -> vfe0_rdi0 -> /dev/video0
```

Alongside the sensor on the same CCI bus sit a `belling,bl24s64` EEPROM at 0x50
holding the module's calibration, and an ON Semi LC898217XC voice-coil focus
motor at 0x72, which since 2026-08-01 has a driver — see
[The focus actuator](#the-focus-actuator) below.

The sensor is strapped to I²C address **0x1a** (SLASEL high on this board), is
mounted rotated 270°, and is described with `orientation = <1>` (world-facing).

Only the **RDI** path is wired: raw Bayer straight from the sensor to memory, no
`msm_vfe*_pix` entity in the graph. Debayering, white balance and everything else
is userspace's problem.

## What is measured to work

Measured 2026-08-01 on `linux-fp3-7.1.3-r30` (`#31-fp3`).

| | |
|---|---|
| sensor probes and identifies | at CCI 0-001a, entity 184 in the media graph |
| link into CAMSS | `imx363 → msm_csiphy0` **ENABLED, IMMUTABLE**; `csiphy0 → csid0` **ENABLED** |
| format negotiation | `SRGGB10_1X10/4032x3024` accepted by **every** pad from the sensor through `vfe0_rdi0` |
| **streaming** | `VIDIOC_STREAMON` succeeds and frames arrive |
| frame size | **15 240 960 bytes**, which is exactly 4032 × 3024 × 10 / 8 — packed 10-bit, no padding, no short frames |
| the data is live | two consecutive frames **differ**, so it is sensor output and not a canned pattern or a stale buffer |
| the data is an image | over a 200 kB sample: mean 46.3, min 0, max 255, 142 distinct byte values — a dark scene with real dynamic range, not a constant |

The capture, in full:

```sh
v4l2-ctl -d /dev/video0 \
  --set-fmt-video=width=4032,height=3024,pixelformat=pRAA \
  --stream-mmap=4 --stream-count=2 --stream-to=/tmp/f.raw
```

☠️ **The pixel format is `pRAA`, not `RG10`.** The video node offers only the
*packed* 10-bit Bayer formats; `RG10` (unpacked) is not in its list, and asking
for it makes `v4l2-ctl` fall back to whatever the node already had. The result is
a `VIDIOC_STREAMON returned -1 (Broken pipe)` — `-EPIPE` from media pipeline
validation, because the video node's format then does not match the pads. That
failure is produced entirely by the *request*, logs nothing in dmesg, and looks
exactly like a broken driver. It is worth stating plainly because this project
recorded "streaming does not work end to end" as a finding for weeks, and the
first thing that happened when it was re-measured with the right format string
was that frames came out.

## What is not established

- **That the image is correct.** Right size, live, non-constant — none of which
  says the geometry, the Bayer order or the line stride are right. Settling that
  needs a known scene: point the phone at something recognisable, debayer the
  raw frame on the host, and look at it. Nobody has done that.
- **Anything about exposure or gain control.** The V4L2 controls exist; whether
  they move the image has not been checked.
- **The two link frequencies in the device tree** (`636000000` and `321000000`)
  disagree with the values the driver's own mode tables carry. The source
  driver's author could not account for the first of them either — the comment
  in the imported file reads `// NOT SURE HOW TO FIND THIS VALUE`. Streaming
  works anyway, which means something is tolerating the mismatch rather than
  that the mismatch is harmless.
- **The EEPROM.** Described in the device tree, no driver bound, calibration
  unread.
- **Which way the focus motor travels.** See below — the driver exists, the
  direction is an inference.

## The four things that made it probe

The imported driver was written for the Pixel 3a, where the sensor rails come up
quickly. On this board they are switched through GPIO-driven regulators that
settle slowly, and the driver as imported never got past the chip-id read. All
four fixes are in the power path, and each is a *timing* fact about this board
rather than about the sensor:

1. **MCLK before reset.** INCK must be running and stable before XCLR is
   released. The import released reset first, and the sensor never booted.
2. **A 200 ms boot delay.** The sensor only ACKs on I²C about 150 ms after
   power-up here, so the import's ~10 ms wait always expired.
3. **An I²C warm-up with a bounded retry.** The first transaction after power-up
   still times out. Because `power_on()` runs on every runtime-PM resume and not
   only at probe, the timeout is absorbed there rather than handed to the caller
   — visible in dmesg on every boot as one `Error reading reg 0x0016: -110`,
   which is expected and not a fault. Without it the first streaming register
   writes time out and CAMSS never receives frames; the user-visible symptom was
   the viewfinder going blank after locking and unlocking the screen with the
   camera open.
4. **`vdig` pinned to 1.175 V.** It is a shared PMIC LDO that otherwise sits at
   its 0.975 V minimum, below what the IMX363 digital core needs. Failing to set
   it is a warning rather than an error, since a board that already supplies
   1.175 V does not need it.

## Checking it works

[`tests/checks/40-camera-test.sh`](../../tests/checks/40-camera-test.sh) tells
three failures apart, because they send you to completely different places:

| symptom | what it means |
|---|---|
| no `imx363` node in `/proc/device-tree` | you are running the wrong device tree |
| node present, driver absent | the module was not built or not loaded |
| bound but unlinked | the media graph is wrong |

☠️ The first is not hypothetical. **Any `apk` operation can fire the mkinitfs
trigger, which reinstalls `/boot/<board>.dtb` from the package** and silently
overwrites a hand-deployed device tree. Installing an unrelated tool cost the
camera exactly this way on 2026-07-25: the package predated the camera DT work,
the sensor node vanished, and the driver simply never probed — with no dmesg
lines to find, which is what makes it confusing.

The check stops at "bound and linked" and does not attempt a capture.

## The focus actuator

`lc898217.c`, its binding, its MAINTAINERS entry and the DT node landed
2026-08-01 and first ship in `linux-fp3-7.1.3-r31`.

### Where the register map came from, and why it is not a guess

☠️ **Qualcomm's downstream kernel does not contain the register map, and that is
the architecture rather than an omission.** Its device tree node is bare —
`compatible = "qcom,actuator"` plus a CCI master number, no slave address and no
registers — and `msm_actuator.c` is a generic engine that is *fed* the map from
userspace over `CFG_SET_ACTUATOR_INFO`. Grepping the whole downstream FP3 tree
for the part number returns exactly one hit, and it is an unrelated string in
`sound/pci/hda/patch_realtek.c`. Anyone looking for this in the kernel will find
nothing and conclude the wrong thing.

The map lives in the board's own Android vendor library,
`vendor/lib/libactuator_lc898217xc.so`, as a C structure in its `.data` section.
Reading that means asserting a struct layout, so the assertion was **checked
against a known answer** rather than assumed: the same decode applied to the
sibling `libactuator_dw9714.so` yields

| decoded from the blob | what mainline `dw9714.c` does |
|---|---|
| slave 7-bit 0x0c | 0x0c |
| 10-bit code | 10-bit DAC |
| register address 0xFFFF = none | raw two-byte write, no register |
| data shift 4 | `(data << 4) \| s` |
| hardware mask 0x0f | the low four bits are the slew-rate field |

— field for field. As a second, independent check the same decode recovers that
part's documented power-up sequence (`0xEC=0xA3`, `0xA1=0x05`, `0xF2=0x08`,
`0xDC=0x51`). Two known answers reproduced, so the layout holds.

### What it says about this part

| | |
|---|---|
| I²C address | **0x72** 7-bit (`0xE4` in the blob's 8-bit form) |
| bus | CCI master 0, shared with the IMX363 |
| speed | 400 kHz (`I2C_FAST_MODE`) |
| register address / data | 8-bit / 16-bit |
| position register | **0x84** |
| code | **10 bit**, right-aligned, shift 0 |
| power-up | **`0xE0 = 0x01`**, then ~10 ms |
| supply | `vreg_cam_af_2p85`, the GPIO-switched 2.85 V rail on TLMM 128 |

The 0x72 is worth noting twice: it was already written as a comment in our
device tree, and the blob confirms it from a completely separate direction.

One Fairphone-specific fact that exists in no datasheet — the board vendor's own
edit to `msm_actuator.c` rewrites the code as `1023 - position` for every
actuator except two others it names, so it applies to this one. It corroborates
the 10-bit width read out of the library.

### ☠️ What is not established

**Which physical direction a rising DAC code moves the lens.** Neither source
states it and neither can be made to. `lc898217_position_to_code()` is the single
place in the driver that decides it, and is marked as such. It currently mirrors
the control, which is what V4L2's "larger value is a closer focus" plus the
vendor's inversion together imply — an inference, not a measurement.

[`userspace-camera/focus-sweep.py`](../../userspace-camera/focus-sweep.py)
settles it without judgement: it steps the control across its range, captures a
frame at each position and scores the mean squared same-colour gradient over a
centred crop. A working actuator gives a single interior peak; a flat curve means
the lens never moved. Point the camera at something with detail, then

```sh
focus-sweep.py --steps 9
```

☠️ The gradient is taken between pixel *x* and *x+2*, never adjacent pixels: the
frames are raw Bayer, so neighbours are different colour planes and an adjacent
difference measures the scene's colour rather than the focus.

[`tests/checks/41-camera-focus.sh`](../../tests/checks/41-camera-focus.sh) covers
the half that needs no scene — node present, driver bound, control exposed.

## The device tree binding

`sony,imx363.yaml` was written on 2026-07-31, and writing it was worth more than
it looks. Until it existed, `dtbs_check` **skipped the camera node in silence** —
a node whose `compatible` nothing documents produces no output at all rather than
being reported as unchecked, so its clean result had never meant anything.
Checked for the first time, the node adds nothing: the board goes from the base's
own 44 errors to 45, and the single addition is the battery node that a separate
open item already covers.

Two places where copying the nearest model would have been wrong are recorded in
[`../TODO.md`](../TODO.md#open-before-anything-is-submitted) item 1.
