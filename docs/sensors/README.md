# FP3 sensors on pmOS mainline

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

Accelerometer, gyroscope, magnetometer and proximity on the Fairphone 3 under a
mainline kernel, through the Snapdragon Sensor Core.

## Why there is no I2C driver here

Every sensor on the FP3 hangs off the **SSC**, a protection domain inside the
ADSP with its own I2C controllers. The factory device tree has **no** sensor
nodes, so there is no bus for the AP to drive and nothing to write a normal
driver against. The only way in is the **Sensor Manager**, a QMI service the SSC
exposes over QRTR, and it does not start until userspace serves it the sensor
registry it asks for at boot.

So the port is three layers, and all three have to be present:

```
snsregd (AP, userspace)  --QMI 0x10F-->  SSC brings its sensors up
                                          |
qcom_smgr (AP, kernel)   <--QMI 256-----  Sensor Manager, node 5
   |
   +-- smgr_accel  smgr_gyro  smgr_mag  smgr_prox   -->  IIO  -->  iio-sensor-proxy  -->  phosh
```

## Provenance

### Imported unchanged

From the `msm8996-staging-smgr` branch of
[`msm8996-mainline/linux`](https://gitlab.com/msm8996-mainline/linux), applied
to the 7.1.3 base with `git am`, so the authorship stays intact. Not in
mainline; posted to the LKML as v2 in July 2025.

| component | file(s) | author |
|---|---|---|
| QRTR bus conversion | `net/qrtr/*` | Yassine Oudjana |
| QMI version/instance macro | `include/linux/soc/qcom/qmi.h` | Yassine Oudjana |
| Sensor Manager core | `drivers/iio/common/qcom_smgr/` | Yassine Oudjana |
| Accelerometer driver | `drivers/iio/accel/smgr_accel.c` | Yassine Oudjana |

### Imported and extended here

| component | what was added | why |
|---|---|---|
| Sensor Manager core | last-sample cache and `smgr_sensor_read_sample()` | the core delivered data only through an IIO buffer; `iio-sensor-proxy` has no buffered proximity driver and polls `in_proximity_raw` |
| Sensor Manager core | reports are started on first read and left running | starting and stopping a report per read kills this SSC — the first read returns a sample and the next fourteen time out |
| Sensor Manager core | every advertised data type is requested, and samples are routed by the report metadata | the core asked only for `SNS_SMGR_DATA_TYPE_PRIMARY`, which hides the second half of a combined part — here the ambient light sensor sharing a package with the proximity one |

### New here

Written for this port, modelled on `smgr_accel.c`; author Lajosházi, László
Gergely with Claude.

| component | file | state |
|---|---|---|
| Proximity + light driver | `drivers/iio/proximity/smgr_prox.c` | working, measured |
| Gyroscope driver | `drivers/iio/gyro/smgr_gyro.c` | working, scale measured |
| Magnetometer driver | `drivers/iio/magnetometer/smgr_mag.c` | responds; scale verified and hard-iron measured, but the driver exposes no `calibbias` to carry it |
| Registry server | [`../../userspace-sensors/snsregd.py`](../../userspace-sensors/snsregd.py) | Python stand-in for upstream's C `sns-reg`; should become an aport |
| Near-level udev rule | [`../../userspace-sensors/`](../../userspace-sensors/) | required before `iio-sensor-proxy` will use the sensor |
| Measurement tools | [`bringup/tools/`](bringup/tools/) | see [what ships, and what was only used to find it](#what-ships-and-what-was-only-used-to-find-it) |

### Fixes to pre-existing kernel code

| file | fix |
|---|---|
| `drivers/soc/qcom/qmi_encdec.c` | `qmi_encode()` read a `QMI_DATA_LEN` field four bytes wide whatever its declared width, so a `u8` length pulled in the bytes after it. Every sensor whose ID is non-zero was unreachable; the accelerometer worked only because its ID is 0. **Not a longstanding oversight — a regression**, see [below](#why-the-submit-series-is-one-patch) |
| `drivers/iio/accel/smgr_accel.c` pattern | `remove()` reads `platform_get_drvdata()`, which probe never set — copied into `smgr_prox.c` and fixed there; upstream has the same latent NULL dereference |
| `drivers/iio/common/qcom_smgr/smgr.c` | the loop that defaults each data type's sample rate to its maximum indexed `data_types[0]` every time instead of the loop variable, so a second data type would have been requested at a rate of zero |
| `drivers/watchdog/qcom-wdt.c`, `sdm632-fairphone-fp3.dts` | `qcom,start-at-probe`: the driver only armed a watchdog the bootloader had already started, and the FP3's has not, leaving no watchdog at all between kernel start and systemd. It came out of this bring-up but is its own category — written up in [`../debug/README.md`](../debug/README.md) |

### Data taken from the device or from upstream

| file | source |
|---|---|
| [`bringup/data/sns.reg`](bringup/data/sns.reg) | the phone's own factory registry, from `/persist/sensors/` |
| [`../../userspace-sensors/registry.conf`](../../userspace-sensors/registry.conf) | 1437 key/value pairs decoded from it |
| [`../../userspace-sensors/groups.txt`](../../userspace-sensors/groups.txt) | group map from upstream [`sns-reg`](https://gitlab.com/msm8996-mainline/sns-reg)'s `map.c` |
| `PROXIMITY_NEAR_LEVEL=1570` | the phone's factory `ps_near` calibration |

## Why the submit series is one patch

`wip/7.1.3/sensor` has twelve commits of ours on top of four of Yassine
Oudjana's. `submit/7.1.3/sensor` has **one**. Three reasons, in order of how hard
they are to get around:

1. **The imported base cannot carry a DCO.** The two `WIP:`-prefixed commits —
   the SMGR core and the accelerometer — have **no `Signed-off-by` at all**, not
   even their author's. Nobody but he can supply it, and everything of ours
   except the QMI fix lives in the files those two commits create.
2. **His series is in flight, and ahead of what we carry.** Patchwork has it as
   v2 of *"QRTR bus and Qualcomm Sensor Manager IIO drivers"*, posted 2025-07-10,
   state **`changes-requested`** on the IIO list, with Jonathan Cameron asking for
   `auxiliary_bus` and an error-handling rework. What this tree carries is the
   2023 snapshot. Sending our own series would be a competing submission of
   another person's driver.
3. **Some of our work may already be his.** The v1 cover letter says
   accelerometer, gyroscope, magnetometer, proximity **and pressure** are
   supported, and names light and temperature as what is missing. Our gyroscope
   and magnetometer drivers were written against the 2023 base and may duplicate
   his; the **ambient light channel is the part he lists as absent**, so that is
   where contributing to his thread has actual value.

What is left, and is genuinely submittable today, is the one commit that lives
outside his code: **`soc: qcom: qmi: read QMI_DATA_LEN at its declared width`**.

That patch got stronger on inspection. The bad line is not old: `git blame` on
today's `torvalds/linux` puts it at
[`fe099c387e06`](https://github.com/torvalds/linux/commit/fe099c387e06)
*"soc: qcom: preserve CPU endianness for QMI_DATA_LEN"* (Alexander Wilhelm,
`Reviewed-by:` Dmitry Baryshkov), which **removed** the narrow reads a May 2025
commit had added. Its stated premise is that *"QMI_DATA_LEN is always of type
`u32` on the host"* — and that is what the SMGR request disproves, since it
declares `u8 item_len`, which the encode path itself accounts for two lines
below:

```c
	data_len_sz = temp_ei->elem_size == sizeof(u8) ?
			sizeof(u8) : sizeof(u16);
```

So the patch is a regression fix and carries `Fixes: fe099c387e06`. The bad line
is live in mainline today — checked directly against `master`, not inferred — and
`get_maintainer.pl` puts the author of the regression on the Cc list. It builds
warning-free at `W=1` and `checkpatch --strict` is clean.

### A fourth reason, and it now covers the newest commit too

The mount-matrix fix of 2026-08-01 looks like an ideal standalone submission —
a self-contained correction of a value that is provably not a rotation. It has
nowhere to go, for a reason that applies to ten of our other eleven commits as
well and is worth stating as its own rule:

☠️ **The file it patches does not exist upstream.** `drivers/iio/accel/smgr_accel.c`,
`drivers/iio/common/qcom_smgr/` and `include/linux/iio/common/qcom_smgr.h` all
return 404 against `torvalds/linux` (checked 2026-08-01). A patch to a driver
that is not upstream has no destination at all — it is not "hard to rebase", it
is unsendable until the driver lands. The same is true of the two QRTR
prerequisites: `net/qrtr/` in mainline holds `af_qrtr.c`, `mhi.c`, `ns.c`,
`smd.c` and `tun.c`, and nothing named `bus`, so Yassine's QRTR-bus conversion
is not upstream either.

This is the check to run **before** distilling any submit series, because it is
cheap and it decides whether the work exists at all:

```sh
gh api "repos/torvalds/linux/contents/<path>" --jq '.size'   # 404 = nothing to send
```

### Re-verified 2026-08-01

The "applies clean to mainline" claim in the branch table was an assertion until
it was measured. It was measured by fetching today's `drivers/soc/qcom/qmi_encdec.c`
straight from `torvalds/linux` and running `git apply --check` against it, rather
than by trial-rebasing the local branch:

| check | result |
|---|---|
| `Fixes: fe099c387e06` resolves in `torvalds/linux` | yes, and the subject matches the one quoted |
| the patch applies to today's `qmi_encdec.c` | clean |
| `checkpatch --strict` | 0 errors, 0 warnings, 0 checks |

The commit message was rewrapped the same day (a sentence had been broken
mid-clause); the diff is byte-identical, and the pre-rewrap tip is kept as
`archive/submit-7.1.3-sensor-pre-rewrap`.

## Status

| sensor | IIO name | works | notes |
|---|---|---|---|
| accelerometer | `qcom-smgr-accel` | yes | \|v\| = 9.70 m/s²; every axis reaches ±1 g |
| gyroscope | `qcom-smgr-gyro` | yes | scale verified: a quarter turn integrates to 86.5° |
| magnetometer | `qcom-smgr-mag` | partly | follows rotation; scale verified and hard-iron measured, but nothing applies the offset yet |
| proximity | `qcom-smgr-prox-light` | yes | blanks the screen during a call through phosh |
| ambient light | `qcom-smgr-prox-light` | yes | same device, second data type; `in_illuminance_input` in lux |

☠️ The IIO device index moves between boots — the Sensor Manager registers each
device as its enumeration completes, so the accelerometer has been `iio:device2`
on one boot and `iio:device3` on the next. Match on `name`, never on the index.

## The proximity sensor is also the light sensor

`SINGLE_SENSOR_INFO` names sensor `0x28` **"EPL259x ALS/PS"** — one part behind
one window next to the earpiece, ALS and PS sharing it. It is the only sensor on
this device that declares **two** data types; the accelerometer, gyroscope and
magnetometer declare one each.

| data type | reading | channel |
|---|---|---|
| 0, primary | proximity | `in_proximity0_*` (buffer), `in_proximity_raw` |
| 1, secondary | ambient light | `in_illuminance_input`, in lux |

Samples are told apart by the report metadata, not by the order they arrive in:

```
metadata.val1 = (data_type << 16) | (sensor_id << 8) | 1
    0x00002801  proximity      0x00012801  ambient light
```

Only the primary data type is pushed into the IIO buffer, because a buffer's
scan layout is fixed per device and a light sample pushed into it would arrive
as a proximity one. The light channel is therefore read-only through sysfs,
which is what `iio-sensor-proxy` wants anyway.

### What the numbers mean

Measured with a hand over the sensor and then a torch shone into it, 60 samples
across four orders of magnitude:

| | |
|---|---|
| `values[0]` | illuminance in **lux**, Q16 fixed point — always a whole number of lux, so the low 16 bits are zero |
| `values[1]` | the raw ADC count behind it, at a steady **2.598 counts per lux** |
| covered | exactly **0**, not a low noise floor |
| dim room | 7 .. 24 lux |
| torch | rises to **25230 lux**, where the count reaches 65535 and **stops** — it saturates rather than rolling over |

Because the reading arrives in lux the channel is `IIO_CHAN_INFO_PROCESSED` and
carries no scale. The saturation ceiling means direct sunlight cannot be told
apart from a strong torch.

## Building and installing

Both are documented centrally, and neither is sensor-specific:

* **kernel config** — the `CONFIG_IIO_QCOM_SMGR*` symbols, with what they depend
  on and why they are useless without the userspace half:
  [`../kernel/config.md`](../kernel/config.md#the-sensor-symbols-come-as-a-set)
* **building and deploying** the kernel package:
  [`../deploy/README.md`](../deploy/README.md)
* **userspace** — the registry server, its data and the udev rule, all required:
  [`../../userspace-sensors/`](../../userspace-sensors/)

Without the registry server the SSC never starts its sensors and no IIO device
appears; without the udev rule the proximity device exists and
`iio-sensor-proxy` ignores it in silence. A kernel that has the symbols but
neither of those looks exactly like a kernel that was built without them.

## Testing

```
sudo python3 ../../userspace-sensors/sensortest.py accel 15     # tilt through all six faces
sudo python3 ../../userspace-sensors/sensortest.py gyro 15      # still, then a known rotation
sudo python3 ../../userspace-sensors/sensortest.py mag 15       # turn on a table
sudo python3 ../../userspace-sensors/sensortest.py prox 12      # cover and uncover
sudo python3 ../../userspace-sensors/sensortest.py light 20     # cover, then a torch
sudo monitor-sensor --proximity               # the phosh-facing path
```

For the gyroscope the tool also integrates the run, which turns a rotation of
known size into a scale check: a quarter circle has to come out near 90°.

## Known gaps

* ~~**The magnetometer is uncalibrated and its scale unverified.**~~ **Measured
  2026-08-01**, and the two did come out together — the sphere's radius *is* the
  field strength, so a full-sphere fit settles the scale as a by-product rather
  than needing it as an input. See [the calibration](#the-magnetometer-calibration)
  below. What is still open is that the driver exposes no
  `in_magn_*_calibbias`, so nothing can carry the offset yet.
* ~~**The mount matrix is probably wrong.**~~ **Fixed 2026-08-01**, and it was
  worse than "probably wrong": the msm8996 value has determinant −1, so it was a
  reflection and not a rotation at all. Measured from three orientations and
  confirmed against the phone's own factory calibration; see
  [the mount matrix](#the-mount-matrix).
* **The gyroscope and the magnetometer have no mount matrix at all** — only the
  accelerometer ever had one. The magnetometer's does not follow from the
  accelerometer's, since it is a separate part that can be placed differently.
* **Groups 2691 and 3050 have no key list**, so `snsregd` answers them with
  zeros. ☠️ **Group 20 is not one of them any more:** its bytes in this phone's
  own factory `sns.reg` are zero too, so serving zeros is serving the truth. The
  factory calibrates the accelerometer, the proximity sensor and the ambient
  light sensor — and nothing else. See
  [what the factory registry holds](#what-the-factory-registry-holds).
* **`snsregd.py` is still the Python stand-in** for upstream's C `sns-reg`,
  which should be packaged as an aport.

## The mount matrix

Measured 2026-08-01 on `linux-fp3-7.1.3-r30`. Three orientations, each held
still for at least eight seconds, read from the buffer in the **sensor** frame:

| held | x | y | z |
|---|---|---|---|
| flat, screen up | −0.247 | +0.304 | −9.705 |
| upright, top of the screen up | +9.669 | +0.649 | −0.417 |
| left edge down, right edge up | −0.332 | +10.129 | +0.890 |

Each has a different dominant axis, so the three of them fix the matrix. The
readings alone still allow two assignments, and the one that survives is the one
that is a **proper rotation** — the other has determinant −1:

```
	 0   1   0          the value now in smgr_accel.c
	 1   0   0
	 0   0  -1
```

The old msm8996 value was every one of those signs flipped, which is what made
it a reflection. The visible symptom was `iio-sensor-proxy` calling a
face-up phone `face-down`.

**It is confirmed independently**, and that is worth more than the measurement.
`/persist/sensors/` holds the factory line calibration as plain text, and the
registry holds the same three numbers in the Sensor Manager's frame:

| persist file | value | registry key | Q16 value |
|---|---|---|---|
| `accel_x` | 0.22 | 0 | −0.09 |
| `accel_y` | −0.09 | 1 | +0.22 |
| `accel_z` | −0.29 | 2 | +0.29 |

Key 0 is `accel_y`, key 1 is `accel_x`, key 2 is `−accel_z`. **That permutation
and sign change are exactly the matrix above**, arrived at with no reference to
the measurement.

☠️ Subtracting those factory biases also shrinks the disagreement between the
three orientations' magnitudes from 4.9 to 2.1 percentage points, so the
apparent "per-axis scale error" they show is mostly **offset**. The driver does
not apply them; `in_accel_*_calibbias` would be where they belong.

## The magnetometer calibration

Measured 2026-08-01, 10 426 samples over 210 s, 74 distinct orientations:

```
hard-iron offset (subtract):   -0.63494  -0.69576  +0.71721   Gauss
semi-axes:                      0.49599   0.47702   0.48673
                               +1.95%    -1.95%    +0.04%     about the mean
residual after correction:      rms 2.25%
```

Three results at once, which is the whole reason to do a full sphere rather
than a set of poses:

- **the hard-iron offset**, which is what the fit is for;
- **soft-iron is negligible** — the semi-axes agree to ±2%, so this is a sphere.
  A 3×3 correction is not needed, an offset is enough;
- **the scale is right.** The radius is 0.4865 Gauss = 48.65 µT, and the
  geomagnetic total field at this latitude is about 48–50 µT, so
  `in_magn_scale` is correct and does report Gauss as the IIO ABI requires. This
  is the point the old gap note said "cannot be solved from the other": true one
  at a time, but the sphere's radius *is* the field strength, so a full fit gives
  both. An exact figure would need the IGRF value for the measurement site.

☠️ **The offset is per-unit and drifts; it must not be hardcoded in the driver.**
Every FP3 would then be corrected for this one phone. It belongs in
`in_magn_*_calibbias` or in userspace.

### Getting a valid sphere is the hard part

The first attempt was done at a desk and produced a 24% residual, which the
ellipsoid fit did not improve on — the tell that the distortion was **not fixed
in the phone frame**, since a real hard/soft-iron model would have fitted it.

The probe that settles it is heading-free. Hold the phone flat: its z axis is
then vertical, so `mz` reads the *vertical* field component, which does not
change when the phone is spun on the spot. Same orientation, different times:

```
at a desk        mz = 0.786 .. 2.658    spread 1.872     a factor of 3.4
in a clear room  mz = 1.056 .. 1.185    spread 0.129
```

Do not use `|m|` in a fixed *gravity* cell for this — gravity pins the tilt but
not the heading, and the raw magnitude legitimately varies with heading because
of the very offset being solved for.

☠️ **Log the accelerometer at the same time.** Without it there is no way to ask
"same orientation?" at all, and a contaminated run looks exactly like a
badly-calibrated sensor. The tooling is `userspace-sensors/iiolog.py`.

## What the factory registry holds

`/persist/sensors/sns.reg` is 25 468 bytes; the group map taken from msm8996's
`sns-reg` accounts for 4051 of them, and the offsets drift because this phone
has groups the map does not list. That drift is measurable and locates them:
`ps_near` sits at byte 272 where the map predicts 73, so **199 unmapped bytes**
sit between group 10 and group 1040 — which is where group 20 must be.

Those bytes, and everything from byte 40 to byte 271, are **zero**. So the
factory data contains:

| | |
|---|---|
| accelerometer bias | `accel_x/y/z`, and registry group 0 keys 0–2 |
| proximity thresholds | `ps_near` = 1570, `ps_far` = 0 |
| ambient light factor | `als_factor` = 1297 |
| **magnetometer calibration** | **none** |
| **gyroscope calibration** | **none** |

Which is consistent with how Android treats them: the magnetometer's hard-iron
is estimated continuously at runtime and never written back, and gyro bias
likewise. **So the sphere measurement above cannot be replaced by downstream
data** — there is no downstream data to take.

Mount the partition read-only to look:

```sh
sudo mount -o ro /dev/disk/by-partlabel/persist /mnt/persist
```

## Will this bring up *all* the sensors?

No:

| sensor | covered by the upstream IIO drivers? |
|---|---|
| proximity | **yes** — the goal here (in-call blanking) |
| accelerometer, gyroscope, magnetometer | **yes** (auto-rotation follows) |
| pressure | yes (the FP3 has no barometer, so moot) |
| ambient light | **yes**, since this port — the second data type of the proximity device |
| temperature | **there is none here.** The SSC advertises four sensors and no thermometer; the gyroscope and magnetometer each declare a single data type, so none is hidden. The SoC and PMIC temperatures come from `tsens`, and the battery's from the PMIC ADC — [battery temperature](../kernel/README.md#battery-temperature) — so nothing is actually missing, it just is not the SSC's |

Everything above is conditional on the group map being correct for this device.

Nothing is missing on the temperature side any more. The **battery**
temperature — the one gap this page used to record — was never the sensor
stack's to fill: the pack thermistor hangs off the PMIC ADC, so it belongs to
the charger driver. It works since 2026-07-29, and how, plus why its curve is
accurate enough to read but not to charge by, is under
[**battery temperature**](../kernel/README.md#battery-temperature) in the kernel
page.

## The userspace side

Working live: phosh 0.55, `iio-sensor-proxy` 3.9, `calls` 50.0, `callaudiod`.

```
IIO proximity device --udev(PROXIMITY_NEAR_LEVEL)--> iio-sensor-proxy
      --net.hadess.SensorProxy (HasProximity / ProximityNear)--> phosh
```

Two things about this are worth knowing before debugging it:

* **`iio-sensor-proxy` has no buffered proximity driver.** Its proximity support
  is `iio-poll-proximity`, which polls `in_proximity_raw`; a buffer-only device
  is skipped without a word in the log. That is why the driver exposes a raw
  channel.
* **The near level can come from sysfs `in_proximity_nearlevel` or from a udev
  property `PROXIMITY_NEAR_LEVEL`**, and without either the proxy logs *"Found
  proximity sensor but no PROXIMITY_NEAR_LEVEL udev property"* and never
  reports. The device-tree route does not apply here — the device has no DT
  node, the Sensor Manager creates it — so
  [`userspace-sensors/`](../../userspace-sensors/) ships the udev rule.

☠️ `ProximityNear` on the bus stays `false` until a client **claims** the sensor;
the proxy does not poll otherwise. During a call phosh claims it. Reading the
property without a claim looks exactly like a dead sensor — use
`monitor-sensor --proximity`, which claims it.

**Blanking lags by about a second**, and that is the proxy's poll period, not
ours: tracing the driver's read function shows `iio-sensor-proxy` reading every
**701 ms**, while the kernel side follows a hand at 0.5 s sampling. The interval
is compiled in. **Decided (2026-07-29): leave it** — every other pmOS phone has
the same latency, and a local fork of a system package is not worth 500 ms.

## What ships, and what was only used to find it

Everything the phone needs is in
[`userspace-sensors/`](../../userspace-sensors/), next to the kernel package:

| file | what it does |
|---|---|
| [`snsregd.py`](../../userspace-sensors/snsregd.py) | the Sensor Registry server — without it the SSC never starts its sensors |
| [`snsregd.service`](../../userspace-sensors/snsregd.service) | keeps it running from boot |
| [`registry.conf`](../../userspace-sensors/registry.conf) | 1437 key/value pairs decoded from this phone's own `sns.reg` |
| [`groups.txt`](../../userspace-sensors/groups.txt) | 68 groups / 1516 keys, from upstream `sns-reg`'s `map.c` |
| [`90-fp3-proximity.rules`](../../userspace-sensors/90-fp3-proximity.rules) | the near level, without which `iio-sensor-proxy` ignores the sensor |
| [`sensortest.py`](../../userspace-sensors/sensortest.py) | reads any of the four sensors and prints per-axis ranges, so "it binds" can be told from "it measures"; for the gyroscope it also integrates the run, turning a known rotation into a scale check |
| [`proxcal.sh`](../../userspace-sensors/proxcal.sh) | prints `in_proximity_raw` once a second, so a hand over the earpiece shows up as two levels — the measurement behind `PROXIMITY_NEAR_LEVEL` |

The instruments that found all this — the ADSP F3 diag capture, the QRTR and QMI
probes, the SSC parameter sweeps — are not needed to run anything, and live with
the investigation in [`bringup/`](bringup/) along with the captures and the raw
service tables they produced:

| | |
|---|---|
| [`bringup/tools/`](bringup/tools/) | 14 probes and parsers |
| [`bringup/data/sns.reg`](bringup/data/sns.reg) | the factory binary registry this port decodes |
| [`bringup/data/`](bringup/data/) | service tables from both slots |
| [`bringup/captures/`](bringup/captures/) | the raw ADSP diag streams behind every number in the write-up |

## Pitfalls

* **`QRTR_TYPE_*` starts at 1:** `DATA=1, HELLO=2, BYE=3, NEW_SERVER=4,
  DEL_SERVER=5, DEL_CLIENT=6, RESUME_TX=7, EXIT=8, PING=9, NEW_LOOKUP=10,
  DEL_LOOKUP=11`. Take them from [`bringup/tools/qrtrconst.py`](bringup/tools/qrtrconst.py), never
  from memory — guessing them wrong is what invalidated steps 4–8 (see [the
  correction](bringup/README.md#correction-2026-07-28--every-publish-in-steps-48-was-a-bye)).
  Sending `3` where you meant `NEW_SERVER` tells the name service the whole node
  died, and it answers with `DEL_SERVER` for every server on it — a very
  reproducible effect that looks like a successful publish from the ADSP's side.
* **`rpmsg_char` must be loaded before any diag capture,** or `bind_diag()`
  silently binds nothing and the capture reports zero messages.
* **Check `tracing_on`, not just the per-event `enable`** — an unarmed ftrace
  buffer returns "no events", which reads as a negative result.
* **`bind()` accepts only the local node id** (1 here); anything else is `EINVAL`.
  An unbound socket already reports it via `getsockname()`.
* **A detached runner dies when the SSH session closes** — `nohup` and `setsid`
  both. One died immediately after `echo stop > .../remoteproc2/state` and left the
  ADSP **offline**. Use `systemd-run --unit=<name> --collect`.
* **Kill stuck units with `systemctl kill -s SIGKILL`, never `reboot -f`.** A
  `systemctl stop` on a wedged capture unit times out; forcing the reboot leaves an
  unclean rootfs and a phone that boots far enough to answer ping but never starts
  sshd. Recovery means booting the other slot and `e2fsck` — see below.
* **A boot-armed instrument must not write to `/tmp`** — a later tmpfs mount hides
  everything written before it. And `remoteproc*` does not exist yet at `sysinit`;
  wait for it rather than exiting.
* **Use `time.monotonic()`** — the wall clock jumps mid-boot, silently truncating a
  capture to nothing.

## The boot-hang safety net

Three times in one session the phone stopped mid-boot: the USB gadget enumerated
(so the kernel and initramfs ran) but the link never came up, no sshd, no adb, no
fastboot — only a physical power cycle got it back. That is fatal to unattended
work, so the net below was built. What each layer does, and what it does *not*:

| layer | catches | does not catch |
|---|---|---|
| `systemd-run --on-active=N --unit=deadman systemctl reboot`, cancelled with `systemctl stop deadman` | a wedge on a **running** system | anything before systemd — it never gets armed |
| `panic=10` on the cmdline | a kernel **panic** (measured: 69 s, then 40 s, unattended) | a hang. With `panic=10` active the phone still sat there, which is how we know these are hangs, not panics |
| SoC watchdog + `CONFIG_WATCHDOG_OPEN_TIMEOUT` | **a hung boot** | nothing else does |
| ~~ramoops~~ | **nothing on this device** — see below | — |

The watchdog is the only real fix. Mainline never described the FP3's watchdog,
so the kernel config had `# CONFIG_WATCHDOG is not set` and the SoC watchdog was
simply not there. The pieces:

* **DT**: `watchdog@b017000`, `compatible = "qcom,kpss-wdt"`, `clocks = <&sleep_clk>`
  — the same address the downstream tree drives, and nothing in `msm8953.dtsi`
  occupies it (nearest neighbours are `b011000` and `b018000`). The driver needs
  the clock; the interrupt is optional.
* **config**: `CONFIG_WATCHDOG=y`, `CONFIG_WATCHDOG_CORE=y`, `CONFIG_QCOM_WDT=y`,
  `CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED=y`, **`CONFIG_WATCHDOG_OPEN_TIMEOUT=300`**.
* **userspace**: `RuntimeWatchdogSec=20` in `/etc/systemd/system.conf.d/`, so a
  healthy boot takes ownership and the watchdog never bites in normal use.

**☠️ Two ways this net silently was not a net.** Both were found the hard way,
by a hang that it failed to recover:

1. **`RuntimeWatchdogSec=60` exceeds the hardware maximum.** systemd logs
   `Failed to set watchdog hardware timeout to 1min: Invalid argument` and leaves
   the watchdog **inactive**. 20 s arms it. Always check
   `/sys/class/watchdog/watchdog0/state`, never assume.
2. **`qcom_wdt` only marks the watchdog running if the *bootloader* left it
   running** — it sets `WDOG_HW_RUNNING` inside `if (qcom_wdt_is_running())` and
   does nothing otherwise. The FP3 bootloader leaves it disabled, so the core
   never armed the open deadline and there was **no watchdog at all between
   kernel start and systemd's open** — precisely the window an early hang falls
   into. A phone that hung there sat for over ten minutes and needed a button.

   The fix is a `qcom,start-at-probe` property and a small driver change that
   starts the watchdog when the bootloader did not:

   ```
   [    0.176047] qcom_wdt b017000.watchdog: started at probe (bootloader left it disabled)
   ```

   With that, `OPEN_TIMEOUT=300` covers the whole boot. The failure mode is
   itself safe: if systemd never takes over, the phone resets every 300 s, each
   reset decrements the A/B retry counter, and the bootloader eventually falls
   back to the Ubuntu Touch slot, which is reachable over wifi.

**ramoops does not work on this device — do not rely on it.** It was tried at
`0x8ee00000` and at `0xd0000000`; pstore registers and the console attaches
(`printk: legacy console [ramoops-1] enabled`), but **nothing survives**: not a
pmsg marker across a clean reboot, and not a `dmesg-ramoops` record after a real
`echo c > /proc/sysrq-trigger` panic. `/sys/fs/pstore/` is empty every time. Two
addresses on opposite sides of DRAM behaving identically points at the boot chain
losing RAM across reset, not at placement. The node was removed rather than left
to cost 2 MB and imply a post-mortem capability that is not there. **So after a
hang there is currently no way to read *why*** — only the watchdog's
`bootstatus` bit says *that* it was a watchdog reset. Real post-mortem on this
hardware needs the UART.

**☠️ Deploy order.** `apk add linux-fp3` **overwrites `/boot/*.dtb`** with the
package's copy and **regenerates `extlinux.conf`**, so the DT nodes and `panic=10`
must be laid down *after* the install, not before. Otherwise you believe the net
is in place and it is not.

## The investigation

[`bringup/README.md`](bringup/README.md) — how all of this was found, in
order, with the wrong turns left in.
