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
> [`sensor_fix_blog.md`](sensor_fix_blog.md).

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

### New here

Written for this port, modelled on `smgr_accel.c`; author Lajosházi, László
Gergely with Claude.

| component | file | state |
|---|---|---|
| Proximity + light driver | `drivers/iio/proximity/smgr_prox.c` | working, measured |
| Gyroscope driver | `drivers/iio/gyro/smgr_gyro.c` | working, scale measured |
| Magnetometer driver | `drivers/iio/magnetometer/smgr_mag.c` | responds; scale and hard-iron offset both unknown |
| Registry server | [`tools/snsregd.py`](tools/snsregd.py) | Python stand-in for upstream's C `sns-reg`; should become an aport |
| Near-level udev rule | [`../../userspace-sensors/`](../../userspace-sensors/) | required before `iio-sensor-proxy` will use the sensor |
| Measurement tools | [`tools/`](tools/) | see [Tools](#tools) |

### Fixes to pre-existing kernel code

| file | fix |
|---|---|
| `drivers/soc/qcom/qmi_encdec.c` | `qmi_encode()` read a `QMI_DATA_LEN` field four bytes wide whatever its declared width, so a `u8` length pulled in the bytes after it. Every sensor whose ID is non-zero was unreachable; the accelerometer worked only because its ID is 0 |
| `drivers/iio/accel/smgr_accel.c` pattern | `remove()` reads `platform_get_drvdata()`, which probe never set — copied into `smgr_prox.c` and fixed there; upstream has the same latent NULL dereference |
| `drivers/watchdog/qcom-wdt.c`, `sdm632-fairphone-fp3.dts` | `qcom,start-at-probe`: the driver only armed a watchdog the bootloader had already started, and the FP3's has not, leaving no watchdog at all between kernel start and systemd |

### Data taken from the device or from upstream

| file | source |
|---|---|
| [`data/sns.reg`](data/sns.reg) | the phone's own factory registry, from `/persist/sensors/` |
| [`data/registry.conf`](data/registry.conf) | 1437 key/value pairs decoded from it |
| [`data/groups.txt`](data/groups.txt) | group map from upstream [`sns-reg`](https://gitlab.com/msm8996-mainline/sns-reg)'s `map.c` |
| `PROXIMITY_NEAR_LEVEL=1570` | the phone's factory `ps_near` calibration |

## Status

| sensor | IIO name | works | notes |
|---|---|---|---|
| accelerometer | `qcom-smgr-accel` | yes | \|v\| = 9.70 m/s²; every axis reaches ±1 g |
| gyroscope | `qcom-smgr-gyro` | yes | scale verified: a quarter turn integrates to 86.5° |
| magnetometer | `qcom-smgr-mag` | partly | follows rotation, but hard-iron offset and scale are both unknown |
| proximity | `qcom-smgr-prox-light` | yes | blanks the screen during a call through phosh |
| ambient light | — | no | lives in a second data type the core never requests |

☠️ The IIO device index moves between boots — the Sensor Manager registers each
device as its enumeration completes, so the accelerometer has been `iio:device2`
on one boot and `iio:device3` on the next. Match on `name`, never on the index.

## Building and installing

The kernel side is in the `linux-fp3` package; the sensor commits live on
`wip/<base>/sensor` and are cherry-picked onto `integration/<base>`. Config:

```
CONFIG_IIO_QCOM_SMGR=m
CONFIG_IIO_QCOM_SMGR_ACCEL=m
CONFIG_IIO_QCOM_SMGR_PROX=m
CONFIG_IIO_QCOM_SMGR_GYRO=m
CONFIG_IIO_QCOM_SMGR_MAG=m
```

Userspace, both required:

```
sudo install -m755 tools/snsregd.py /usr/local/bin/
sudo install -m644 tools/snsregd.service /etc/systemd/system/
sudo mkdir -p /etc/sns-reg.d && sudo cp data/registry.conf data/groups.txt /etc/sns-reg.d/
sudo systemctl enable --now snsregd

sudo install -m644 ../../userspace-sensors/90-fp3-proximity.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger --subsystem-match=iio
```

Without `snsregd` the SSC never brings its sensors up and no IIO device appears.
Without the udev rule the proximity device exists and `iio-sensor-proxy` ignores
it in silence.

## Testing

```
sudo python3 tools/sensortest.py accel 15     # tilt through all six faces
sudo python3 tools/sensortest.py gyro 15      # still, then a known rotation
sudo python3 tools/sensortest.py mag 15       # turn on a table
sudo python3 tools/sensortest.py prox 12      # cover and uncover
sudo monitor-sensor --proximity               # the phosh-facing path
```

For the gyroscope the tool also integrates the run, which turns a rotation of
known size into a scale check: a quarter circle has to come out near 90°.

## Known gaps

* **Ambient light is still missing.** The proximity sensor advertises a second
  data type that the core never requests, and that is where the light reading
  has to be — the primary type's third value is always zero. Reaching it means
  teaching the core to ask for more than one data type per sensor, and telling
  the samples apart by the `(data_type << 16) | (sensor_id << 8) | 1` field in
  the report metadata.
* **The magnetometer is uncalibrated and its scale unverified** — hard-iron
  offset and scale are both unknown, and one cannot be solved from the other
  without a full-sphere fit.
* **The mount matrix is probably wrong.** `smgr_accel.c` carries an msm8996
  matrix with a `TODO` next to it, and on the FP3 `iio-sensor-proxy` reports
  `AccelerometerTilt: face-down` for a phone reading `z = -9.69`. Whether that
  matches the physical orientation needs one deliberate check with the phone
  held screen-up; if it does not, the matrix needs an FP3 value.
* **Audio fails at the first use in some boots** — an intermittent SLIMbus
  channel activation failure, not caused by the sensor stack (measured), with
  the leftover framer pokes as the prime suspect.
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
| ambient light | **not yet** — upstream calls it "close to being implemented" |
| temperature | not yet |

Automatic brightness therefore stays out of reach for now. Everything above is
also conditional on the group map being correct for this device.

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

## Tools

| file | what it does |
|---|---|
| [`tools/sensdiag.py`](tools/sensdiag.py) | ADSP F3 capture on mainline: locates the ADSP remoteproc by name, binds `rpmsg_chrdev` to its DIAG channels, re-arms the F3 mask every 0.25 s, re-binds after an SSR; optional `ssr` argument restarts the ADSP mid-capture |
| [`tools/parsef3.py`](tools/parsef3.py) | host-side parser: HDLC de-framing, message header, bounds-checked argument extraction |
| [`tools/snsreg.py`](tools/snsreg.py) | publishes a list of QMI services over QRTR, **one socket per service**, dumping everything that arrives |
| [`tools/snsregd.py`](tools/snsregd.py) | the Sensor Registry server |
| [`tools/qmiprobe.py`](tools/qmiprobe.py) | sends empty QMI requests to a `node:port` and prints replies |
| [`tools/qrtrconst.py`](tools/qrtrconst.py) | the QRTR control codes, transcribed from the kernel uapi header. **Import these; do not retype them** — see [the correction](sensor_fix_blog.md#correction-2026-07-28--every-publish-in-steps-48-was-a-bye) |
| [`tools/qrtrls.py`](tools/qrtrls.py) | enumerates every QMI service the name service knows, by node. The one command that shows whether the sensor stack is up |
| [`tools/snsregd.service`](tools/snsregd.service) | systemd unit that keeps the registry server running from boot |
| [`tools/readaccel.py`](tools/readaccel.py) | reads the buffer-only accelerometer and prints m/s² and \|g\| — the physical sanity check that catches a wrong record size |
| [`tools/readprox.py`](tools/readprox.py) | the same for the proximity/light device |
| [`tools/smgrbuf.py`](tools/smgrbuf.py) | sends `SNS_SMGR_BUFFERING` by hand and sweeps its parameters, so a question costs a second instead of a 30-minute kernel build |
| [`tools/smgrind.py`](tools/smgrind.py) | asks for buffering on one sensor and prints the indications the SSC sends back — answers "is this data really from that sensor" from the wire |
| [`tools/sensortest.py`](tools/sensortest.py) | reads any of the four sensors and prints per-axis ranges, so "it binds" can be told from "it measures"; for the gyroscope it also integrates the run, which turns a known rotation into a scale check |
| [`tools/proxcal.sh`](tools/proxcal.sh) | prints `in_proximity_raw` once a second so a hand over the earpiece shows up as two levels — the measurement that decides `PROXIMITY_NEAR_LEVEL`, and the one that cannot be made remotely |
| [`tools/sensinfo.py`](tools/sensinfo.py) | asks the SSC what a sensor advertises (`ALL_SENSOR_INFO`, `SINGLE_SENSOR_INFO`) — data types, rates, vendor and part name. Ask this before asking for data |
| [`tools/smgrsweep.py`](tools/smgrsweep.py) | streams one sensor with the **driver's own** request parameters, data type as an argument, and counts indications. Use this rather than inventing a report rate: it is `sample_rate * 0xf000`, and a wrong one silently means "one report every two minutes" |

## Pitfalls

* **`QRTR_TYPE_*` starts at 1:** `DATA=1, HELLO=2, BYE=3, NEW_SERVER=4,
  DEL_SERVER=5, DEL_CLIENT=6, RESUME_TX=7, EXIT=8, PING=9, NEW_LOOKUP=10,
  DEL_LOOKUP=11`. Take them from [`tools/qrtrconst.py`](tools/qrtrconst.py), never
  from memory — guessing them wrong is what invalidated steps 4–8 (see [the
  correction](sensor_fix_blog.md#correction-2026-07-28--every-publish-in-steps-48-was-a-bye)).
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

## Recovering the rootfs from the other slot

The pmOS root lives inside `system_b` in its own DOS table, so it is reachable
from the Ubuntu Touch slot without flashing:

```
fastboot set_active a          # boot UT
losetup -P /dev/loopN /dev/mmcblk0p31
e2fsck -f -y /dev/loopNp1      # pmOS_boot  (ext2)
e2fsck -f -y /dev/loopNp2      # pmOS_root  (ext4)
fastboot set_active b          # back to pmOS
```

Done once here after a forced reboot, and it found real damage: journal recovery,
two extent-tree optimisations, wrong free block and inode counts, and a stuck
`orphan_present` flag.

## Data

| file | contents |
|---|---|
| [`data/sns.reg`](data/sns.reg) | the FP3's factory binary sensor registry |
| [`data/registry.conf`](data/registry.conf) | 1437 key/value pairs generated from it |
| [`data/groups.txt`](data/groups.txt) | 68 groups / 1516 keys from upstream `map.c` |
| [`data/gates.txt`](data/gates.txt) | the node-1 services to publish alongside `0x10F` |
| [`data/node1_services.txt`](data/node1_services.txt) | the oracle's unfiltered 36 — reference only, see the collision warning |
| [`data/ut_servers.txt`](data/ut_servers.txt) | the full QMI service table dumped from Ubuntu Touch |

## Captures

Raw ADSP F3 diag streams; parse with `tools/parsef3.py`.

| file | what it shows |
|---|---|
| [`captures/pmos_f3_wake.bin`](captures/pmos_f3_wake.bin) | the sensor task waking on the `0x10F` publish |
| [`captures/pmos_f3_long.bin`](captures/pmos_f3_long.bin) | `0x10F` alone → `L487 [-18]` ×31, `L1206 [0]` |
| [`captures/pmos_f3_multi.bin`](captures/pmos_f3_multi.bin) | 36 services on one port → `L173 [-2]` ×31 |
| [`captures/pmos_f3_ports.bin`](captures/pmos_f3_ports.bin) | **the clean run** — zero errors, `L1206 [1]` |
| [`captures/pmos_f3_ssr_services.bin`](captures/pmos_f3_ssr_services.bin) | an SSR with services present; carries the rcinit text used for the oracle diff |

The Ubuntu Touch reference capture (`ut_f3_boot.bin`, 13 MB, 82 211 messages) is
not checked in for size; it lives in the working directory
`/mnt/1TB/Fp3-Sailfish/fp3-sensors-oracle-20260728/` with everything else.

## Next steps

1. **Ambient light** — teach the Sensor Manager core to request more than one
   data type per sensor, and split the reports by the data type in the metadata.
2. **Calibrate the magnetometer** — a full-sphere fit to separate the hard-iron
   offset from the scale, and a heading check against a known direction.
3. **The mount matrix** — check `AccelerometerTilt` against the phone's physical
   orientation and replace the inherited msm8996 matrix if it does not match.
4. **The intermittent SLIMbus audio failure** — build without the two leftover
   framer pokes and count the failure rate over several cold boots.
5. **Find the real content of groups 20, 2691 and 3050**, which are zero-filled.
6. **Package upstream's C `sns-reg` as an aport**, replacing `snsregd.py`.

## The investigation

[`sensor_fix_blog.md`](sensor_fix_blog.md) — how all of this was found, in
order, with the wrong turns left in.
