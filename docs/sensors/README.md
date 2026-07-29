# FP3 sensors on pmOS mainline

Accelerometer, gyroscope, magnetometer and proximity on the Fairphone 3 under a
mainline kernel, through the Snapdragon Sensor Core.

> **AI-generated.** The drivers, tools and documentation in this directory were
> written by Claude (Opus 5) working under the direction of Lajosházi, László
> Gergely, who reviewed every change and made every physical measurement they
> rest on. Kernel commits carry `Co-authored-by: Claude`; anything prepared for
> the LKML carries `Assisted-by:` instead and never a `Signed-off-by` from the
> assistant, since only a human can certify the DCO.
>
> The investigation that produced all this — including three confident
> conclusions that had to be retracted — is a separate document:
> [`bringup/README.md`](bringup/README.md).

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
| Magnetometer driver | `drivers/iio/magnetometer/smgr_mag.c` | responds; scale and hard-iron offset both unknown |
| Registry server | [`../../userspace-sensors/snsregd.py`](../../userspace-sensors/snsregd.py) | Python stand-in for upstream's C `sns-reg`; should become an aport |
| Near-level udev rule | [`../../userspace-sensors/`](../../userspace-sensors/) | required before `iio-sensor-proxy` will use the sensor |
| Measurement tools | [`bringup/tools/`](bringup/tools/) | see [Tools](#tools) |

### Fixes to pre-existing kernel code

| file | fix |
|---|---|
| `drivers/soc/qcom/qmi_encdec.c` | `qmi_encode()` read a `QMI_DATA_LEN` field four bytes wide whatever its declared width, so a `u8` length pulled in the bytes after it. Every sensor whose ID is non-zero was unreachable; the accelerometer worked only because its ID is 0 |
| `drivers/iio/accel/smgr_accel.c` pattern | `remove()` reads `platform_get_drvdata()`, which probe never set — copied into `smgr_prox.c` and fixed there; upstream has the same latent NULL dereference |
| `drivers/iio/common/qcom_smgr/smgr.c` | the loop that defaults each data type's sample rate to its maximum indexed `data_types[0]` every time instead of the loop variable, so a second data type would have been requested at a rate of zero |
| `drivers/watchdog/qcom-wdt.c`, `sdm632-fairphone-fp3.dts` | `qcom,start-at-probe`: the driver only armed a watchdog the bootloader had already started, and the FP3's has not, leaving no watchdog at all between kernel start and systemd |

### Data taken from the device or from upstream

| file | source |
|---|---|
| [`bringup/data/sns.reg`](bringup/data/sns.reg) | the phone's own factory registry, from `/persist/sensors/` |
| [`../../userspace-sensors/registry.conf`](../../userspace-sensors/registry.conf) | 1437 key/value pairs decoded from it |
| [`../../userspace-sensors/groups.txt`](../../userspace-sensors/groups.txt) | group map from upstream [`sns-reg`](https://gitlab.com/msm8996-mainline/sns-reg)'s `map.c` |
| `PROXIMITY_NEAR_LEVEL=1570` | the phone's factory `ps_near` calibration |

## Status

| sensor | IIO name | works | notes |
|---|---|---|---|
| accelerometer | `qcom-smgr-accel` | yes | \|v\| = 9.70 m/s²; every axis reaches ±1 g |
| gyroscope | `qcom-smgr-gyro` | yes | scale verified: a quarter turn integrates to 86.5° |
| magnetometer | `qcom-smgr-mag` | partly | follows rotation, but hard-iron offset and scale are both unknown |
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

* **The magnetometer is uncalibrated and its scale unverified** — hard-iron
  offset and scale are both unknown, and one cannot be solved from the other
  without a full-sphere fit.
* **The mount matrix is probably wrong.** `smgr_accel.c` carries an msm8996
  matrix with a `TODO` next to it, and on the FP3 `iio-sensor-proxy` reports
  `AccelerometerTilt: face-down` for a phone reading `z = -9.69`. Whether that
  matches the physical orientation needs one deliberate check with the phone
  held screen-up; if it does not, the matrix needs an FP3 value.
* **Groups 20, 2691 and 3050 are zero-filled, not real.** The stack initialises,
  but whatever those groups configure is wrong. They need their real offsets in
  `sns.reg`, or their key lists.
* **`snsregd.py` is still the Python stand-in** for upstream's C `sns-reg`,
  which should be packaged as an aport.

## Will this bring up *all* the sensors?

No:

| sensor | covered by the upstream IIO drivers? |
|---|---|
| proximity | **yes** — the goal here (in-call blanking) |
| accelerometer, gyroscope, magnetometer | **yes** (auto-rotation follows) |
| pressure | yes (the FP3 has no barometer, so moot) |
| ambient light | **yes**, since this port — the second data type of the proximity device |
| temperature | **there is none.** The SSC advertises four sensors and no thermometer; the gyroscope and magnetometer each declare a single data type, so none is hidden. The SoC and PMIC temperatures come from `tsens` and already work |

Everything above is conditional on the group map being correct for this device.

What is still missing on the temperature side is the **battery** temperature:
`pmi632-battery` exposes no `temp` property. That is the charger driver's, not
the sensor stack's.

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
