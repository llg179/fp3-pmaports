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

☠️ The `media-ctl` step must also set the **sensor** pad, not just the CAMSS
ones, whenever anything has run the camera at another resolution first — a
libcamera or PipeWire session leaves the sensor at its preview size, and the
recipe above then fails the same `-EPIPE` as a cold boot does:

```sh
media-ctl -d /dev/media0 -V "'imx363 0-001a':0 [fmt:SRGGB10_1X10/4032x3024]"
```

☠️ **The pixel format is `pRAA`, not `RG10`**, and the `media-ctl` step is not
optional. Either mistake produces `VIDIOC_STREAMON returned -1 (Broken pipe)`
with nothing in dmesg, which reads exactly like a broken driver; both cost this
project weeks. See [`bringup/`](bringup/README.md#two-ways-to-make-streaming-fail-that-look-like-a-broken-driver).

## The flash

The PMI632's two flash channels are ganged into the single white LED next to the
rear lens, and it works as a torch: `/sys/class/leds/white:flash`, 600 mA total
across the two channels, `brightness` for torch and `flash_strobe` for a timed
flash. The bring-up and its numbers are in
[`../TODO.md`](../TODO.md#parked-the-pmi632-camera-flash--it-works-2026-08-03).

Two things to know before measuring anything about it:

* ☠️ **The phone has no battery ammeter.** `pmi632-battery` exposes no
  `current_now`, and with a cable attached the torch is fed from USB, so battery
  voltage does not droop either. The instrument that works is the PMIC's own USB
  input current ADC, `in_voltage_usb_in_i_uv_input`, with the states interleaved.
* **The camera is the honest instrument for "does it light".**
  [`../../userspace-camera/flash-check.py`](../../userspace-camera/flash-check.py)
  holds one capture open and switches the torch underneath it. Pointed at a matte
  surface a hand's width away it reads mean 15.8 unlit against 70.0 lit,
  repeatable to 0.09 over three passes.

`CONFIG_V4L2_FLASH_LED_CLASS` is off, so there is no `/dev/v4l-subdev` for the
flash and libcamera cannot fire it yet. Nor is the charger-side `FLASH_ACTIVE`
handshake implemented, which downstream uses around a full-current strobe; the
torch does not need it, a 2 A strobe may.

## The front camera

The Samsung S5K4H7 at `1-0010` identifies itself — `S5K4H7 detected, model ID
0x487b` — and does nothing else. Its driver registers no subdevice, so `cam -l`
still reports one camera. Why it stops there, and why that is a licence question
rather than an engineering one, is in
[`../FP3-TODO.md`](../FP3-TODO.md).

☠️ **The second CCI bus needs `cci1_default` in the board's `&cci` pinctrl-0.**
`msm8953.dtsi` muxes both buses; a board that overrides `pinctrl-0` to add its
own MCLK pin silently drops the other bus's pins with it. A bus with no pins
answers `-110` (transfer never completed), which is a different failure from
`-ENXIO` (nobody at that address) — worth reading carefully, because the rest of
the sensor's description can be perfectly correct while this is missing.

☠️ **`imx363 0-001a: Error reading reg 0x0016: -110` at boot is unrelated to
it.** It lands about 300 ms after the front sensor is detected and looks caused
by it; moving `s5k4h7.ko` aside and rebooting shows the same error without it.
The rear camera binds and captures normally regardless.

## The CSIPHY timer clock, and why the camera used to vanish

☠️ **`gcc_camss_csi0phytimer_clk status stuck at 'off'` was a wrong mux value
in mainline's `gcc-msm8953.c`, not a settle or a sequencing problem.** Fixed
2026-08-02 on `wip/7.1.3/camera`.

The three `csi*phytimer` RCGs placed `GPLL0_DIV2` at **source select 2**. No
other mux in the camera block does: every one of them puts it at 4 or 5, and
on `csi0` select 2 is not a listed source at all. Selecting a source the RCG
does not have leaves `CMD_RCGR` with `ROOT_OFF` set, so the branch never
starts and `clk_branch2_enable()` times out into `-EBUSY`.

Why it looked intermittent for months: only the **100 MHz** entry in
`ftbl_csi_phytimer_clk_src` comes from `GPLL0_DIV2`, and CAMSS picks it from
the sensor's link frequency. A 321 MHz link (the 1920x1080-ish preview modes)
lands on 100 MHz and could never stream; the full-resolution path lands on
200 MHz, comes from `GPLL0`, and always worked. Same phone, same boot, two
different answers depending on which mode the sensor was in.

| | with select 2 | with select 4 |
|---|---|---|
| `CMD_RCGR` | `0x80000000` — `ROOT_OFF` set | root on |
| `CBCR` | `0x80000001` — enabled, `CLK_OFF` never clears | running |
| capture runs | 0 of 9 | **9 of 9, across two boots, nothing in dmesg** |

Two explanations were tried and **disproven** before this one, both worth not
repeating: an immediate retry at the same rate (2026-07-26 — both attempts
fail, so it is not a settle), and GPLL0's output gates being closed
(2026-08-02 — `USER_CTL` reads `0x3`, opening all three to `0x7` changes
nothing).

☠️ **The failure did not stop at the camera.** A single `-EBUSY` wedges
WirePlumber's `CameraManager` thread, and from then on the whole session
manager is unresponsive — `wpctl status` hangs, `pw-dump` returns nothing with
status 0 — so the camera node disappears from PipeWire and every app reports
*no camera found*. Until the clock fix, the recovery was `systemctl --user
restart wireplumber`.

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

## Driving it by hand

Useful when something in the app path is suspect, because it takes every layer
above libcamera out of the picture:

☠️ **A stray `LIBCAMERA_SOFTISP_MODE=cpu` defeats the GPU debayer at runtime,
whatever the package was built with.** The variable is read from the *session*
environment, so a file in `/etc/environment.d/` silently forces every
session-launched process — `wireplumber` included, and therefore every camera
app — onto the CPU debayer, which **centre-crops**. The symptom is that the
saved picture shows a visibly wider scene than the viewfinder did.

How it was found, 2026-08-02, is worth keeping: the same `cam` binary logged
EGL from an interactive SSH session and no EGL at all when run as a
`systemd-run --user` unit. Same binary, same camera, different environment —
so the answer was in `diff <(systemd-run env) <(ssh env)`, not in the code.
`GL_RENDERER: FD506` in a process's log is the proof the GPU debayer is
actually in use; its absence is the tell.

☠️ **Which sizes can be streamed is not derivable, and the ladder is long.**
Measured on this camera, each size in its own process from idle: of the 47
sizes PipeWire advertises, everything below about 1.8 megapixels refuses with
`Failed to start streaming: Resource busy` — 160×120, 320×240, 400×240,
640×480, 800×600, 1024×768, 1280×720, 1280×1024, 1400×1050 and 1680×1050 —
while 1600×1200, 1920×1080 and 4032×3024 work. All three working sizes take
the **full 4032×3024 sensor mode** (`Input 4032x3024-RGGB-10-CSI2P` in the
log); the failing ones are the sizes for which the pipeline selects the
sensor's 1920×1080 mode.

☠️ **Setting a control the camera does not publish is not a no-op.** PipeWire
answers `set_param Spa:Enum:ParamId:Props: No such file or directory` and logs
it for every attempt. That happens by itself whenever the lens fails to
initialise, since libcamera then stops publishing the `Af*` controls entirely
while everything else keeps working — so an application must look a control up
before writing it.

☠️ **The `simple` pipeline handler takes the camera exclusively, and
`wireplumber` holds it.** `cam` then refuses with *"Pipeline handler in use by
another process"*, so a hand measurement needs
`systemctl --user stop wireplumber pipewire pipewire.socket` first — and the
same exclusivity is what wedges the focus lens when two clients overlap.

☠️ **`pipewiresrc` does not preroll from an SSH session** — the pipeline sits
in PAUSED and produces nothing, with no error. Measure through `cam`, which
talks to libcamera directly.

☠️ **A capture smaller than the sensor's own size fails** with
`Failed to start streaming: Resource busy`. `cam -C4` at full resolution works,
but a frame is 36 MB and the rootfs has ~200 MB free, so delete between runs.

```sh
# which node is the camera
pw-dump | grep -B5 'Video/Source'

# focus once (AfMode=Auto, then AfTrigger=Start), and watch the IPA react
pw-cli set-param <node> Props '{ 16777249: 1 }'
pw-cli set-param <node> Props '{ 16777254: 0 }'
journalctl --user -u wireplumber --since -1min | grep IPASoftAf
```

☠️ The IPA runs inside whichever process opened the camera — **wireplumber**,
not the application — so that is where its log goes. Looking for it in the
app's journal finds nothing and reads like "autofocus never ran".

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
| debayer | the **GPU** one (`GL_RENDERER: FD506`, Mesa 26.1.1). It has to be asked for: the aport needs `mesa-dev` and `-Dsoftisp-gpu=enabled`, without which libcamera silently falls back to the CPU debayer |
| frame rate | **~6 fps at 4032×3024, ~30 fps at 1920×1080** — the same on both debayers, so the limit is not the debayering |
| field of view | full, **on the GPU debayer only**. ☠️ The CPU debayer does not scale, it **centre-crops**: `window_.width = outputCfg.size.width` out of a 4032-wide sensor, so a 1920×1080 preview shows 48% of the width and 36% of the height — which looks exactly like a fixed ~3× zoom next to another phone |
| PipeWire | device `imx363 [libcamera]`, source *Built-in Back Camera*, offering a ladder of sizes from 160×120 up |
| controls offered | `Contrast`, `Gamma`, **`AfMode`, `AfTrigger`, `AfMetering`, `AfWindows`**, and with the manual-control patches **`ExposureTimeMode`, `ExposureTime`, `AnalogueGainMode`, `AnalogueGain`, `AwbEnable`, `ColourTemperature`** |
| what a control can be | the node describes itself — `pw-dump <node>` returns each control's libcamera name, type, bounds and, for the enumerated ones, its value labels. That is enough to build a user interface for a camera nobody wrote code for, and is how the app's manual controls are built |
| manual focus | **not offered.** `LensPosition` is defined in dioptres, so publishing it needs two actuator codes related to real distances; the module's own EEPROM (`bl24s64`, no driver) is where a vendor keeps them. Until then the lens can be focused but not *told a distance* — see [FP3-TODO 33j](../FP3-TODO.md) |
| autofocus | continuous by default; a scan is 19 measurements, so **~3.5 s at 1920×1080** and ~14 s at full resolution — statistics arrive once every four frames |
| autofocus, in daylight | **verified 2026-08-02**: repeated scans of a lit indoor scene settled at 385, 386, 387, 389, 391 and 394 with peak scores around 15 000. In the dark the same instrument scored ~1 300 and refused (`No focus peak … staying at`), which is the algorithm declining rather than guessing |
| reaching a control from an app | only by binding the PipeWire node directly. `pw-cli set-param <node> Props '{ 16777249: 1 }'` sets `AfMode`; the id is `SPA_PROP_START_CUSTOM` (0x1000000) plus libcamera's control id (`AfMode` 33, `AfTrigger` 38) |

Autofocus is ours: libcamera's `simple` IPA had no AF algorithm at all, so one
was written and is carried as [a patch](../../userspace-camera/libcamera/) on the
package. What it does, and how to check it, is in
[`bringup/`](bringup/README.md#autofocus-in-libcamera).

### The manual controls, measured

Measured 2026-08-02 on libcamera `99990.7.1-r8`, in a dark room, by asking the
IPA rather than the picture: `cam --metadata --script` reports what was
*actually used* for each frame, which is a verdict the scene's brightness
cannot spoil.

| asked for | reported back |
|---|---|
| automatic | 8783 µs at **11.9×** — the AGC's answer to a dark room |
| 2000 µs, gain 1 | **1996 µs**, 1.000 |
| 30000 µs, gain 1 | **29995 µs**, 1.000 |
| 8000 µs, gain 12 | **7984 µs**, 12.000 |
| **5000 µs, gain automatic** | **4999 µs held**, gain raised to **12.8×** |
| white balance 2800 K | `AwbEnable false`, `ColourTemperature 2800` |
| white balance 8000 K | `AwbEnable false`, `ColourTemperature 8000` |

The fifth row is the one worth having: with the exposure time pinned and the
gain left automatic, the AGC answered the dark room with gain alone and never
touched the exposure. That is the independence the two modes promise, and it
is the part a single "manual mode" flag would not have.

Requested times come back a few microseconds short — 2000 → 1996, 8000 → 7984
— because exposure is set in whole sensor lines, and a line is about 4.3 µs
here. That is quantisation, not error.

☠️ **A brightness measurement could not have decided this.** In the dark room
every frame averaged between 1.7 and 7.3 out of 255, and the differences
between settings were smaller than the noise. The metadata answers regardless
of the light; a picture-based check has to wait for a lit scene.

☠️ **Only `AfMode` and `AfTrigger` reach an application, and not through
GStreamer.** PipeWire's libcamera plugin maps controls to properties only for
`bool`, `int32` and `float`, and returns early for any array control
(`if (cid.isArray()) return nullptr;` in
`spa/plugins/libcamera/libcamera-source.cpp`), so `AfWindows` never arrives —
focusing on a *tapped point* still needs a change there
([FP3-TODO 33g](../FP3-TODO.md)). And `pipewiresrc` carries no camera controls
at all, so an application has to reach the node itself; the Snapshot patches run
`pw-cli set-param` on the `object.id` the GStreamer device already carries.
Binding the node in-process needs the `pipewire` Rust crate, whose bindgen step
does not survive cross compilation — see
[`userspace-camera/`](../../userspace-camera/README.md).

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

☠️ **The viewfinder dies after a couple of dozen resolution changes, and the
size it was asked for has nothing to do with it.** Measured 2026-08-03 on
`linux-fp3-7.1.3-r37` (`#38-fp3`) with libcamera 0.7.1 and `snapshot-50.0-r19`:

| what was driven | how far it got |
|---|---|
| Snapshot's viewfinder, on screen, one size per round | **24 sizes streamed, then the stream was gone** — and stayed gone at a size that had streamed a minute earlier |
| the same PipeWire node through `pipewiresrc ! fakesink`, no application, no screen | **40 reconfigurations across 7 sizes, every one delivered frames**, `dmesg` clean |
| `cam -c1 -C10 -s width=1920,height=1080` immediately after the viewfinder died | **30 fps, no errors** |

So the camera, the driver and the PipeWire node reconfigure fine; what does not
survive is the on-screen render path. `dmesg` shows the software ISP's GPU
debayer faulting on buffers that are no longer mapped — tens of thousands of
`*** gpu fault` / `Unhandled context fault` pairs from `1c48000.iommu-ctx`,
`adreno_fault_handler: … callbacks suppressed`. The faults start well before the
death, around the tenth reconfiguration, so they are not individually fatal;
they accumulate.

Two things follow. The first is that **"Could not play camera stream" is not a
size problem**, which is how it was first read: no size has yet been shown not
to stream. The second is that whatever reduces the number of reconfigurations
helps, which is why a photograph is worth taking at the preview's own size
rather than switching the source to the sensor's and back around every shot —
see the `photo-resolution` setting in
[`userspace-camera/`](../../userspace-camera/README.md).

☠️ **A screen blank during a reconfiguration is the aggravated case, not the
cause.** The first run of this measurement was unattended, the session's idle
timer fired five minutes in, and the stream died with the panel dark — which
looked like a clean explanation until the same death was reproduced with the
screen on throughout. Snapshot's idle inhibitor was contributing: it was
released whenever the viewfinder left `Ready`, which it does on every resolution
change, so the camera handed the idle timer a window each time it did anything.
Fixed in
[`snapshot/0011`](../../userspace-camera/snapshot/0011-camera-resolution-and-flash-focus.patch).
