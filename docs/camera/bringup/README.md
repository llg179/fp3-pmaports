# Bringing up the FP3 rear camera

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The investigation behind [`../README.md`](../README.md), kept as a narrative:
what was believed at each step, what was measured, and what that forced us to
conclude — including, at length, the places where the belief was wrong and had
to be retracted twice. The reference material — what is wired, what streams, how
to check it — is in the README; this is the reasoning.

Nothing here is needed to use the camera.

> **Where things stand is deliberately not on this page.** What works today is in
> [`../README.md`](../README.md); what is still open is in
> [`../../TODO.md`](../../TODO.md) and
> [`../../FP3-TODO.md`](../../FP3-TODO.md). This is a record of how the current
> arrangement was arrived at, and it is **not** revised when the device changes —
> so read anything below as "what was true when it was measured", with the date
> the step carries.

## The four things that made the sensor probe

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

## Two ways to make streaming fail that look like a broken driver

Both produce `VIDIOC_STREAMON returned -1 (Broken pipe)` — `-EPIPE` out of media
pipeline validation — with **nothing in dmesg**, and both are caused entirely by
the request rather than by the hardware.

☠️ **Asking for `RG10` instead of `pRAA`.** The video node offers only the
*packed* 10-bit Bayer formats; `RG10` (unpacked) is not in its list, so
`v4l2-ctl` falls back to whatever the node already had and the node's format then
disagrees with the pads. This project recorded "streaming does not work end to
end" as a finding for weeks on the strength of it, and the first thing that
happened when it was re-measured with the right format string was that frames
came out.

☠️ **Not propagating the format along the CAMSS chain.** From a cold boot the
pads sit at `UYVY8_1X16/1920x1080` while the sensor is at
`SRGGB10_1X10/4032x3024`. The `media-ctl -V` step was missing from the recorded
capture command until 2026-08-01, so the command as written reproduced the same
symptom from a different cause. `focus-sweep.py` now does the propagation itself
rather than relying on anyone reading the page.

## The focus actuator

### It was at the wrong address, and both addresses are right

The device tree and this repository both said the actuator was an LC898217XC at
0x72, from the vendor blob, for weeks. The bus says otherwise. Measured on
hardware with the actuator rail forced on by a throwaway `regulator-always-on`
DTB and the sensor resumed through `/sys/bus/i2c/devices/0-001a/power/control`,
so the camera IO rail was up:

```
/dev/i2c-0: 0x0c 0x1a 0x50
```

0x1a is the sensor and 0x50 the module EEPROM. **Nothing acknowledges 0x72.**

☠️ **The scan has to be forced (`I2C_SLAVE_FORCE`).** A plain `I2C_SLAVE` scan is
refused with `EBUSY` for every address a driver has already claimed — which is
exactly the addresses under investigation. The first scan run this way listed
only `0x0c 0x50`, silently omitting both the sensor and the actuator address, and
that absence looks exactly like a result.

Two other things that scan settled, both of which had looked like driver bugs:

- **The CCI bus does not work until the sensor's IO rail is up.** With the sensor
  suspended, every transfer ends `i2c-qcom-cci: master 0 queue 0 timeout`
  (`-110`). Resume the sensor and the same transfer to an empty address returns
  `-ENXIO` instead. Timeout versus NACK is the difference between "the bus is
  dead" and "nobody is home", and only the second is a statement about the
  actuator.
- **A failed runtime-PM resume latches.** Once `lc898217_runtime_resume()`
  failed, the device sat in `power/runtime_status: error` and every later
  `pm_runtime_resume_and_get()` returned `-EINVAL` — so opening the subdev failed
  with `-EINVAL`, several steps removed from the real `-110`. Unbind and rebind
  the driver to clear it.

Then the reason, from the vendor's own camera configuration
(`/vendor/etc/camera/camera_config.xml`): **Fairphone ships this phone with two
different rear camera modules, and they do not carry the same actuator.**

| `SensorName` | `EepromName` | `ActuatorName` |
|---|---|---|
| `imx363` (added 2019-04) | `ofilm_imx363_bl24s64` | `lc898217xc` — 0x72 |
| `imx363_2nd` (added 2019-12) | `ofilm_imx363_bl24s64` | **`ak7374` — 0x0c** |
| `imx363pv_2nd` (added 2020-05) | `ofilm_imx363pv_bl24s64` | **`ak7374` — 0x0c** |

So the LC898217XC work was not wrong, it describes the *other* variant — the same
shape as the battery, where the FP3 ships two pack types and this one has the
Fuji. Both drivers are kept for that reason.

That also disposed of the `ak7374` vs `dw9800` question an earlier draft left
open: `dw9800` appears in `camera_config.xml` against a different module
entirely, so it was never a candidate for this board. And the downstream
inversion `value = 1023 - position`, which excludes exactly `ak7374` and
`dw9800`, does not apply here — the AK7374 takes the position straight.

### Reading a register map out of a vendor blob

☠️ **Qualcomm's downstream kernel does not contain the register map, and that is
the architecture rather than an omission.** Its device tree node is bare —
`compatible = "qcom,actuator"` plus a CCI master number, no slave address and no
registers — and `msm_actuator.c` is a generic engine that is *fed* the map from
userspace over `CFG_SET_ACTUATOR_INFO`. Grepping the whole downstream FP3 tree
for the part number returns exactly one hit, and it is an unrelated string in
`sound/pci/hda/patch_realtek.c`. Anyone looking for this in the kernel will find
nothing and conclude the wrong thing.

The map lives in the board's own Android vendor libraries
(`vendor/lib/libactuator_*.so`), as a C structure in `.data`. Reading that means
asserting a struct layout, so the assertion was **checked against known answers**
rather than assumed.

☠️ **The decoder was wrong before it was right, and only that control caught it.**
The structure starts at `.data + 0x04`, not at `.data`, and with that four-byte
error every field decoded to a plausible-looking wrong value — an I²C address, a
bit width, a register number, none of them right, and nothing in the output
looked odd. Running the identical decode against parts whose answers mainline
already states is what exposed it, and what confirms the fix:

| field | `dw9714` mainline / decoded | `ak7345` mainline / decoded |
|---|---|---|
| I²C address | 0x0c / **0x0c** | 0x0c / **0x0c** |
| position width | 10 bits / **10** | 9 bits / **9** |
| position register | none / **0xffff** | 0x00 / **0x00** |
| shift | 4 / **4** | 7 / **7** |

Seven fields across two parts, all matching, plus the DW9714's documented
power-up sequence (`0xEC=0xA3`, `0xA1=0x05`, `0xF2=0x08`, `0xDC=0x51`) recovered
by the same decode. The AK7374's own numbers then satisfy the invariant the whole
family obeys: position width plus shift makes a full 16-bit word (9+7, 10+6,
12+4).

The one number no control covers is the power-on delay. The AK7345's 20 ms is
used rather than the AK7375's 10 ms, because over-waiting costs 10 ms once per
power-on and under-waiting is a failed first transfer.

**Do not accept a struct decode without at least one control whose answer is
known independently**, and prefer two.

### ☠️ The measurement said "it moves", then "it does not", and both were wrong

The final answer, and the numbers behind it, are in
[`../README.md`](../README.md#the-focus-actuator). This is how they were reached,
because the two failures are about experiment design rather than about this
hardware and they generalise.

**Round one — "it moves".** Position 0 scored 250.06 against position 1023 at
206.09, with spreads near 2: a 20:1 signal, three times over. But **every round
measured 0 first and 1023 second**, and each capture restarted the stream, so
anything settling between the first and second capture of a round appears as a
position effect. Balancing the order (`0,1023 / 1023,0 / 0,1023 / 1023,0`)
separates them:

| grouping | means | difference |
|---|---|---|
| by **position** | 0 → 405.65, 1023 → 404.72 | **0.93** |
| by **capture order** | first → 405.57, second → 404.81 | **0.76** |

The same size. There was no position effect in that experiment, and the 44.0 was
an artifact of the design.

**Round two — "it does not move".** Two independent defects:

- **Every capture restarted the stream** (`v4l2-ctl` launches, takes four frames,
  exits). Each launch resets auto-exposure, and the settling transient that
  follows is as large as the effect being looked for.
- ☠️ **The A/B pair was 0 against 1023 — the two positions with the least
  contrast available.** The full sweep, once it was run properly, reads 387.3 at
  0 and 380.6 at 1023, a difference of 6.7, while the peak at 409 stands 48 above
  both. The response to this control is a **peak, not a ramp**, so the ends of
  travel are equally out of focus. An extremes-vs-extremes test is structurally
  blind to it — and it is exactly the test the "compare the two extremes"
  instinct produces.

A third, smaller bug lived in the same fallback: on a flat curve it compared the
sweep's *best and worst* positions, which are wherever the noise fell (once 511
and 716), so it tested the smallest movement available instead of the largest.

The two rules this earns, both now in the `fp3-kernel-test` skill:

- **choose the contrast pair from the shape of the response you expect**, not
  from the ends of the input range. A peaked response needs a sweep or a
  bracketing triple;
- **acquire once and vary the input inside the acquisition.** Re-arming the
  instrument per sample injects a transient that is correlated with the sample.

Holding one capture open and interleaving the passes turned the same hardware,
the same metric and the same scene into a 14:1 measurement.

A human check misled too, in the same direction: a slider driving the control
live, watched in the camera app, produced no visible change — because a focus
change is invisible in a preview scaled down far enough. The effect was obvious
the moment the same slider sat next to a viewfinder that could zoom to 8×. That
is why `focus-view.py` displays the metric as well as the picture.

### What was eliminated along the way

All measured rather than assumed, and all still true — this is the list that says
the driver side is complete:

| | |
|---|---|
| the writes reach the part | no I²C error, and the byte stream reflects them |
| the part is powered | `cam_af_2p85` and `cam_io_1p8` both `enabled`; TLMM 128 and 130 read `out high` |
| runtime PM is not cutting power | `runtime_status` stays `active` across writes and captures |
| the active-mode write happens | `ak7375_vcm_resume()` writes `reg_cont = mode_active` unconditionally — `has_standby` gates only the *suspend*-side write, which an earlier note here got wrong |
| nothing else fights us | with the camera app running, a written value is unchanged three seconds later, three times; there is no autofocus on this stack |
| the vendor does nothing more | its parameter block is fully decoded: ten register descriptors of which only the first is filled, and a single init write of `0x02 = 0x00`. The driver does exactly that and nothing is left over |

☠️ **A raw readback looks like confirmation and is not.** Writing 0, 256, 512 and
1023 and reading register 0x00 returns exactly `value << 6` every time. But a dump
of registers 0x00–0x0f shows each read starting with the *second byte of the
previous one* (`ffc0`, `c040`, `400e`, `0e60` …): the part ignores the
register-address write and streams bytes, so the reply cannot be told from an echo
of the last write. It shows the bytes arrive, not where they land. The sweep is
what actually confirms the map, and it does it through the lens.

### The LC898217XC, for the record

What the vendor blob says about the *other* module's actuator. Accurate about
that part; it does not describe this board.

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

One Fairphone-specific fact that exists in no datasheet: the board vendor's own
edit to `msm_actuator.c` rewrites the code as `1023 - position` for every actuator
except `ak7374` and `dw9800`, so it applies to this part. It corroborates the
10-bit width read out of the library — and its exclusion list is a second reason
the AK7374 takes the position straight.

`lc898217_position_to_code()` is the single place in that driver that decides
direction, and is marked as such. It mirrors the control, which is what V4L2's
"larger value is a closer focus" plus the vendor's inversion together imply — an
inference, never a measurement.

## The device tree binding was worth more than it looked

`sony,imx363.yaml` was written on 2026-07-31. Until it existed, `dtbs_check`
**skipped the camera node in silence** — a node whose `compatible` nothing
documents produces no output at all rather than being reported as unchecked, so
its clean result had never meant anything. Checked for the first time, the node
adds nothing: the board goes from the base's own 44 errors to 45, and the single
addition is the battery node that a separate open item already covers.

Two places where copying the nearest model would have been wrong are recorded in
[`../../TODO.md`](../../TODO.md#open-before-anything-is-submitted) item 1.

## The device tree can be overwritten under you

☠️ **Any `apk` operation can fire the mkinitfs trigger, which reinstalls
`/boot/<board>.dtb` from the package** and silently overwrites a hand-deployed
device tree. Installing an unrelated tool cost the camera exactly this way on
2026-07-25: the package predated the camera DT work, the sensor node vanished,
and the driver simply never probed — with no dmesg lines to find, which is what
makes it confusing. The guard for it is
[`tests/checks/06-dtb-test.sh`](../../../tests/checks/06-dtb-test.sh), which
compares the booted device tree against the *installed package* rather than
against the tree it was built from.

## Autofocus in libcamera

The kernel half of focus was finished on 2026-08-01: the actuator moves, and a
sweep finds the peak. What no application could do with that is *ask* for focus,
because libcamera's `simple` pipeline — the one this camera runs on — has no
autofocus at all. Measured before writing any of it: `ipa_soft_simple.so`
contained no focus symbol, the shipped `imx363.yaml` listed only
`BlackLevel`/`Awb`/`Adjust`/`Agc`, and `cam --list-controls` offered `Contrast`
and `Gamma`. Three pieces were missing, and each one is a different kind of
thing.

**A focus measure the ISP does not have.** The software ISP's statistics pass
already walks every fourth pixel of every other line, summing the colour
channels and filling a luminance histogram. Sharpness rides along in that pass —
the sum of squared differences between successive samples — so it costs no
extra memory traffic on a 15 MB frame. Two properties are load-bearing and both
were learned the expensive way on this phone: the difference is taken between
samples of the **same Bayer colour** (adjacent raw pixels differ by colour, not
by detail), and the value is **normalised by the square of the total luminance**,
because the AGC moves exposure and gain throughout a scan and an unnormalised
sum of squares scales with brightness.

**A search whose shape comes from the measurement.** The sweep says the response
is a single interior peak with long flat tails, about 12% of contrast between
peak and tail and 0.8% of spread within a position. That rules out the obvious
implementations: a hill climb that stops when the score falls settles on the
first wobble, and an A/B of the two ends of the range cannot see the peak
between them — that exact comparison had already produced a confident *"the lens
does not move"* the day before. So the scan is a fixed coarse ladder of twelve
positions across the whole range, then a finer ladder of seven around the best
of them, with no early exit.

**A way to reach the lens.** The IPU3 pipeline handler already had the shape:
the IPA emits the lens subdevice's controls and the pipeline handler applies
`V4L2_CID_FOCUS_ABSOLUTE`. The one deliberate difference is that the lens's
control range is passed to the IPA at `init()` rather than at `configure()`, so
that the AF controls are advertised only for a camera that has a lens — a camera
without one should not show an `AfMode` that cannot do anything.

The acceptance test was decided before the code ran: a scan must land near the
position the sweep found *independently*. It settles on **372** against the
sweep's **380**, from a coarse pass whose maximum is at 372 and a fine pass that
walks 279…465 around it.

### What it cost in time, and where that time goes

A scan is 19 measurements, and a measurement is one statistics frame. The
software ISP produces statistics once every four frames, so the scan takes as
long as 76 frames — **14 s at 4032×3024, 3.5 s at 1920×1080**. The frame rate is
the whole story: the software ISP sustains ~6 fps at full sensor resolution and
~30 fps at half. It is worth knowing which one an application is asking for
before blaming the search.

### Focus zones, and why a tap cannot reach them yet

Sharpness is accumulated into a 5×5 grid rather than one number, so that
`AfMetering`/`AfWindows` can point the score at the part of the frame a user
tapped. The grid is nearly free: every one of the five per-format line functions
takes one sample per two Bayer blocks, so the sample-index → zone-column mapping
is identical for all of them and is computed once in `setWindow()`.

☠️ **The control cannot reach an application, and libcamera is not where it
stops.** PipeWire's libcamera plugin maps a control to a property only for
`bool`, `int32` and `float`, and bails out of arrays first:

```cpp
	if (cid.isArray())
		return nullptr;
```
[`spa/plugins/libcamera/libcamera-source.cpp`]

`AfWindows` is an array of rectangles, so it is dropped before an app ever sees
it, while `AfMode` and `AfTrigger` — plain integers — come through and show up in
`pw-dump` as node properties. Tap-to-focus therefore needs a PipeWire change as
well as this one, and that is why the libcamera side was written to be ready for
it rather than waiting for it.

### Two clients at once wedge the lens until reboot

☠️ Opening the lens subdevice runtime-resumes the actuator over the CCI bus. Do
that while another libcamera client is tearing the camera down and the transfer
times out:

```
i2c-qcom-cci 1b0c000.cci: master 0 queue 0 timeout
ak7375 0-000c: ak7375_vcm_resume I2C failure: -110
```

Runtime PM then latches the failure, so **every later open returns `EINVAL`** for
the rest of the boot, libcamera logs *"Lens initialisation failed, lens
disabled"*, and autofocus quietly disappears while the camera goes on streaming
perfectly. It is not caused by autofocus — libcamera has always opened the lens
when it creates the camera — but autofocus is what makes its absence visible.

The characterisation that matters for anyone chasing it: sequential use never
reproduced it. Across two clean boots, four camera creations each, including one
after a streaming run, the lens came up every time; restarting the PipeWire stack
*while nothing else touched the camera* was also harmless. It took an overlap to
break it.
