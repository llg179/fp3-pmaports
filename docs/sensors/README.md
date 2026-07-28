# Sensors

Everything about the FP3 sensors on pmOS mainline: why none of them work, what
was measured, how the existing upstream solution was found, and exactly what
this repository adds on top of it. Every capture and every tool referenced below
is checked in here, so none of the claims have to be taken on trust.

Status as of **2026-07-28**: **not working yet.** The blocker was identified and
one of its two layers was removed; the remaining layer is named in
[What is still missing](#what-is-still-missing). Nothing here is a shipping
feature — this page is the record of the investigation and of the integration
work that is under way.

## The short version

The FP3 has no sensor the AP can reach. Proximity, ALS and the IMU all hang off
the **SSC** (Snapdragon Sensor Core), a protected domain inside the ADSP with its
own I²C controllers; the factory device tree has zero sensor nodes, so there is
no bus to write a driver against. The only way in is the **Sensor Manager** QMI
service the SSC exposes — and it only comes up after the AP first serves it a
**Sensor Registry** (`SNS_REG`) service.

pmOS serves neither, so the SSC's sensor task stalls forever a few milliseconds
into its startup, and no sensor ever appears.

The userspace half of the stack is already complete and installed on the device
(phosh 0.55, `iio-sensor-proxy` 3.9, `calls`, `callaudiod`) — see
[The userspace side](#the-userspace-side). The missing piece is purely a sensor
source.

## Contents

| path | what it is |
|---|---|
| [`tools/`](tools/) | the instruments used to measure and to serve — see [Tools](#tools) |
| [`data/`](data/) | the registry, the group map, the service lists, and the factory `sns.reg` — see [Data](#data) |
| [`captures/`](captures/) | the raw ADSP F3 diag captures behind every number on this page — see [Captures](#captures) |

## Why nothing works: the measurements

All of these are live measurements on the device, not source reading. The
instrument is `tools/sensdiag.py`, which captures the ADSP's F3 debug log on
mainline (there is no `/dev/diag`; it binds `rpmsg_chrdev` to the ADSP's DIAG
channels by hand). Messages are identified by source line number — the strings
are stripped by QShrink, so `L307` means "line 307 of some sensor source file".

### 1. The sensor task starts, prints 12 messages, and stops

A cold boot produces exactly 12 `ss_id=53` (SENSORS) messages in 6.8 ms, then
silence. The same 12 messages, with the same arguments, appear on the working
Ubuntu Touch side — **the prologue is multiset-identical**. So the task is not
failing; it is *waiting*. On UT it resumes 3.68 s later; on pmOS it never does.

### 2. What it waits for is a QMI service, and the wake-up message names it

The first message of the UT resume is:

```
L307 [1, 271, 0]
```

`271` is `0x10F`, and on UT that service is owned by `sensors.qti` on node 1
(the AP), port 0x37 — see [`data/ut_servers.txt`](data/ut_servers.txt).
The arguments read as `(node, service, instance)`.

### 3. Publishing that service on pmOS wakes the task — proof by construction

Rather than capture the exchange on the oracle, the missing half was *created*:
`tools/snsreg.py` opens an `AF_QIPCRTR` socket and sends a `NEW_SERVER` control
packet. The mainline kernel carries the name service itself (`qrtr_ns`), so no
daemon is needed.

The moment the service is published, the sensor task wakes:

| | before | after |
|---|---|---|
| SENSORS messages | 12 | **131** |
| first message | — | `L307 [1, 271, 0]` — *identical to the oracle* |

Capture: [`captures/pmos_f3_wake.bin`](captures/pmos_f3_wake.bin). The whole
resume sequence (`L275`/`L286`/`L383`, then `L464`+`L2451` pairs over ids
3300–3329 and 2800) matches the oracle message for message.

### 4. Publishing more services peels off one error layer at a time

The `L1206` message that closes the sequence carries `1` on success and `0` on
failure — the cheapest pass/fail indicator in the whole trace.

| published | per-sensor result | closing `L1206` | capture |
|---|---|---|---|
| `0x10F` only | `L487 [-18]` ×31, `L581 [id,5]` ×30 | **`[0]` — failed** | [`pmos_f3_long.bin`](captures/pmos_f3_long.bin) |
| all 36 node-1 services, **one port** | `L173 [-2, 4]` ×31 | `[1]` | [`pmos_f3_multi.bin`](captures/pmos_f3_multi.bin) |
| all 36, **one port each** | none — all `L2451 [id, 2]` | **`[1]` — clean** | [`pmos_f3_ports.bin`](captures/pmos_f3_ports.bin) |

The last row is the important one: **the SSC's sensor init runs to completion on
pmOS with zero errors, all 31 sensor drivers initialised.** The topology matters
as much as the content — on the oracle every service sits on its own port, and
collapsing them onto one socket alone produced 31 failures.

### 5. The co-processor side is not at fault

The `ss_id=100` (rcinit) band carries plain text on both sides. Normalised and
diffed against the oracle, the ADSP's entire init sequence is **identical** —
including `qup_manager_init`, `i2cbsp_init`, `sysmon_sensors_user_init` and
`device open SENSORS`. The only differences are SSR notifications about other
subsystems (venus/wcnss/modem). Capture:
[`captures/pmos_f3_ssr_services.bin`](captures/pmos_f3_ssr_services.bin).

### 6. The node-7 "Sensor Manager" is a loopback stub

`qrtr-lookup` shows a `Sensor Manager service` (256) on node 7 with version 0,
instance 1 — not the `v1/instance 50` the oracle has on node 5. Sending five
different QMI message ids to it with `tools/qmiprobe.py` returned **the exact
bytes that were sent**, transaction id and all. It is a loopback echo, not the
service.

### 7. Two behaviours that make this easy to mismeasure

* **The wake-up is edge-triggered.** The task waits for `NEW_SERVER` to *arrive*;
  a service that is already published when the ADSP boots does not satisfy it —
  the task prints its prologue and stops, exactly as if nothing had been done.
  A boot-time unit that publishes before the ADSP comes up therefore achieves
  nothing.
* **It fires once per ADSP boot.** A second publish only produces `L307`. A warm
  SSR restarts the prologue but not the rest.

## How the existing solution was found

The investigation above reconstructed the protocol from scratch. It should have
started with a web search; it did not, and that cost most of a day. The search
that found everything, run after the fact:

> `SSC sensors mainline linux Qualcomm SMGR QMI postmarketOS proximity ADSP`

The top results — the [postmarketOS wiki page on the Snapdragon Sensor
Core](https://wiki.postmarketos.org/wiki/Qualcomm_Snapdragon_Sensor_Core) and
the LWN announcement [QRTR bus and Qualcomm Sensor Manager IIO
drivers](https://lwn.net/Articles/1016590/) — describe exactly this problem, and
state the ordering the measurements had just rediscovered:

> Before Sensor Manager becomes accessible, another service known as Sensor
> Registry needs to be provided by the AP, after which the remote processor will
> request data from it and then expose several services including Sensor Manager.

The follow-up search `Yassine Oudjana Qualcomm Sensor Manager IIO driver patch
series QRTR bus sensor registry server` located the code.

### What exists upstream

| component | what it does | where | revision |
|---|---|---|---|
| **`sns-reg`** | the AP-side Sensor Registry QMI server; emulates the Android sensor daemon | <https://gitlab.com/msm8996-mainline/sns-reg> | `4d238e5f0baba3fb77456fe2bffbf8e8f18a71a0` (2025-07-06, *"main: Set infinite poll timeout"*); tags `0.1` = `ad37ad305cde8b24544cb106215fec9ae4a2b135`, `0.0.1` = `739deb8799eaa3e0b7919b411fb77c505a04c781` |
| **`sns-reg-generator`** | converts a binary `sns.reg` into the plain-text registry the server reads | same repo | same |
| **QRTR bus + Sensor Manager IIO drivers** | turns QRTR into a bus and exposes SMGR sensors as IIO devices (accel, gyro, magnetometer, **proximity**, pressure) | branch `msm8996-staging-smgr` of <https://gitlab.com/msm8996-mainline/linux> | `30bb1314cc798f1df15e902ae53238de2b27bc90` |
| **pmaports packaging** | draft aports for the above | [pmaports MR !4118](https://gitlab.com/postmarketOS/pmaports/-/merge_requests/4118) | **draft, unmerged**; project archived |

Author: Yassine Oudjana. The LKML posting is
[PATCH v2 0/4](https://lkml.org/lkml/2025/7/17/895) (July 2025); as of this
writing the series is **not in mainline** — review was still on the
platform-device/auxbus question. **MSM8953 is explicitly in scope** (on this SoC
Sensor Manager is hosted by the ADSP, which is why our SMGR would appear on QRTR
node 5).

### The independent confirmation

`sns-reg`'s `qmi/sns_reg.h` contains:

```c
#define SNS_REG_QMI_SVC_ID       0x010f
#define SNS_REG_QMI_SVC_V1       2
#define SNS_REG_QMI_INS_ID       0
#define SNS_REG_GROUP_MSG_ID     0x4
```

The service id, version and instance are byte-for-byte what the measurements
above arrived at independently. The group ids in its `map.c` (3300…3329, 2800)
are exactly the ids our F3 trace shows in `L2451 [id, 2]`. Two independent
derivations agreeing on this much is the strongest evidence on this page.

The one thing the measurements had *not* found is `SNS_REG_GROUP_MSG_ID = 0x4`,
the request itself — which is precisely why the SSC never sent us anything:
the service was published but never *served*.

## What this repository adds

The upstream pieces do not run on the FP3 as they stand. The delta:

### 1. A device registry generated from the FP3's own calibration

The factory registry was read off the phone's `persist` partition (which pmOS
does not mount) and converted with the upstream generator:

```
mount -o ro /dev/disk/by-partlabel/persist /mnt/persist
./sns-reg-generator /mnt/persist/sensors/sns.reg > registry.conf
```

* [`data/sns.reg`](data/sns.reg) — the factory binary, 25 468 B, md5
  `30367ee6da871d9a65340532b2472a99`
* [`data/registry.conf`](data/registry.conf) — **1437 key/value pairs**, generated
  from it

The same directory carries the phone's factory calibration as plain files, which
the registry embeds: `ps_near=1570`, `ps_far=0`, `als_factor=1297`,
`accel_x=0.22`, `accel_y=-0.09`, `accel_z=-0.29`.

### 2. A Python re-implementation of the registry server

[`tools/snsregd.py`](tools/snsregd.py) — same protocol as `sns-reg`, same
licence (GPL-3.0-or-later), ~150 lines. Written because `sns-reg` is C + SCons +
libqrtr and would need a cross-toolchain or an aport before it could answer a
single request; the protocol is one message, so a Python server gets a live
answer in one step. The C daemon remains the packaged end state.

It publishes `0x10F` v2/instance 0 and answers `SNS_REG_GROUP` (`0x4`):
request `TLV 0x01 = u16 group id`; response `TLV 0x02 = u16 result`,
`TLV 0x03 = u16 group id`, `TLV 0x04 = u16 length + payload`, where the payload
is the group's keys concatenated little-endian.

### 3. The group map in a portable form

[`data/groups.txt`](data/groups.txt) — the 68 groups / 1516 keys of upstream's
`map.c`, extracted to one line per group (`gid key:len key:len …`) so the server
needs no C parsing. **Caveat:** this map was reverse-engineered on MSM8996. It has
not been validated against the FP3 yet; upstream ships `sns-reg-validator` for
exactly this, and any group the SSC asks for that is missing here will be
answered with a failure result.

### 4. The service gate list

[`data/gates.txt`](data/gates.txt) — the 22 node-1 services (besides `0x10F`)
that measurement 4 showed are needed for a clean init, published one per port by
`tools/snsreg.py`.

**This list is deliberately *not* the oracle's full set.** Four of the oracle's 36
(`14` rfs, `49` IPA, `52` DHMS, `4096` TFTP) are services **pmOS already
provides**. Publishing those shadows the real daemons, and withdrawing them on
exit **deletes the real daemons' registrations from the name service** — after
which the ADSP can no longer reach `tqftpserv` and sensor init cannot proceed.
[`data/node1_services.txt`](data/node1_services.txt) is the unfiltered oracle
list, kept for reference; `gates.txt` is the one to use.

## What is still missing

* **Sensor Manager never registers.** Even after a completely clean init
  (`L1206 [1]`, 31 drivers up), no `256 / v1 / instance 50` appears on node 5, so
  there is still no data path and therefore nothing for an IIO driver to read.
* **The SSC has not yet sent a single registry request.** With `snsregd.py`
  published and waiting, the request count stayed at zero across every run, so
  the server's response path is written but **unexercised**. Until one real
  `SNS_REG_GROUP` request is served, the group map and the registry values are
  untested.
* **Reproducibility regressed mid-session.** After the gate-list incident
  described above, the wake-up stopped reproducing even with the previously
  known-good configuration. A controlled SSR still shows the 12-message prologue,
  so the task and the instrument are both fine; the trigger conditions are not
  yet fully pinned down. Suspected: the edge-triggered wake has a narrow window
  relative to ADSP boot.
* **The kernel drivers are not ported.** `msm8996-staging-smgr` has to be rebased
  onto our 7.1.3 base.

## Will this bring up *all* the sensors?

No — and the honest breakdown matters:

| sensor | covered by the upstream IIO drivers? |
|---|---|
| proximity | **yes** — the goal here (in-call screen blanking) |
| accelerometer, gyroscope, magnetometer | **yes** |
| pressure | yes (the FP3 has no barometer, so moot) |
| ambient light | **not yet** — described upstream as "close to being implemented" |
| temperature | not yet |

So the immediate objective — proximity blanking the screen during a call — is in
scope. Automatic rotation would follow from the accelerometer. Ambient-light
(automatic brightness) needs driver work that does not exist yet anywhere.

Everything above is also conditional on the group map being right for this
device; a sensor whose registry group is mismapped will not come up even though
its driver exists.

## The userspace side

Already complete on the device — verified live, nothing to do here once a sensor
source exists:

```
phosh 0.55   iio-sensor-proxy 3.9 (+udev, +systemd)   calls 50.0   callaudiod
```

The chain is: an IIO proximity device with `in_proximity_nearlevel` (from the DT
property `proximity-near-level`) → udev tags it → `iio-sensor-proxy` exports
`net.hadess.SensorProxy` with `HasProximity`/`ProximityNear` → phosh claims
proximity during a call and powers the output off. Today `net.hadess.SensorProxy`
is absent from the bus because the only IIO devices are the two PMIC ADCs:

```
iio:device0 = 200f000.spmi:pmic@2:adc@3100
iio:device1 = 200f000.spmi:pmic@0:adc@3100
```

The missing `in_proximity_nearlevel` is a classic silent failure: the sensor
reads fine, `ProximityNear` never flips, and the screen never blanks.

## Tools

| file | what it does |
|---|---|
| [`tools/sensdiag.py`](tools/sensdiag.py) | ADSP F3 diag capture on mainline. Finds the ADSP remoteproc **by name** (the index moves between boots), binds `rpmsg_chrdev` to its DIAG channels, re-arms the F3 mask every 0.25 s and re-binds after an SSR. Optional `ssr` argument restarts the ADSP mid-capture |
| [`tools/parsef3.py`](tools/parsef3.py) | host-side parser for those captures: HDLC de-framing, message header, bounds-checked argument extraction |
| [`tools/snsreg.py`](tools/snsreg.py) | publishes a list of QMI services over QRTR, **one socket (= one port) per service**, and dumps everything that arrives, decoded as control or QMI |
| [`tools/snsregd.py`](tools/snsregd.py) | the Sensor Registry server itself (see above) |
| [`tools/qmiprobe.py`](tools/qmiprobe.py) | sends empty QMI requests to a `node:port` and prints the replies; used to unmask the node-7 loopback |

### Traps worth knowing before touching any of this

* **`QRTR_TYPE_*` is off by one from the obvious guess:** `DATA=0, HELLO=1,
  BYE=2, NEW_SERVER=3, DEL_SERVER=4`. Sending `2` tells the name service the
  whole node died, and it answers with `DEL_SERVER` for every server on it.
* **`bind()` accepts only the local node id** (1 here); anything else is
  `EINVAL`. An unbound socket already reports it via `getsockname()`.
* **A detached runner dies when the SSH session closes** — `nohup` and `setsid`
  both. One died immediately after `echo stop > .../remoteproc2/state` and left
  the ADSP **offline**. Use `systemd-run --unit=<name> --collect`.
* **A boot-armed instrument must not write to `/tmp`** — a later tmpfs mount
  hides everything written before it. And `remoteproc*` does not exist yet at
  `sysinit`; the instrument has to wait for it rather than exit.
* **Use `time.monotonic()`** — the wall clock jumps mid-boot, which silently
  truncates a capture to nothing.

## Data

| file | contents |
|---|---|
| [`data/sns.reg`](data/sns.reg) | the FP3's factory binary sensor registry, straight off `persist` |
| [`data/registry.conf`](data/registry.conf) | 1437 key/value pairs generated from it |
| [`data/groups.txt`](data/groups.txt) | 68 groups / 1516 keys, extracted from upstream `map.c` |
| [`data/gates.txt`](data/gates.txt) | the 22 node-1 services to publish alongside `0x10F` |
| [`data/node1_services.txt`](data/node1_services.txt) | the oracle's unfiltered 36 — reference only, see the warning above |
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
`/mnt/1TB/Fp3-Sailfish/fp3-sensors-oracle-20260728/` together with everything
above.

## Next steps

1. Get one real `SNS_REG_GROUP` request served — that is the gate everything else
   is behind. Requires pinning down the edge-triggered wake window.
2. Validate the group map against the FP3 (`sns-reg-validator`), fix what differs.
3. Confirm Sensor Manager registers on node 5 once the registry is actually served.
4. Port `msm8996-staging-smgr` onto the 7.1.3 base; package `sns-reg` proper as an
   aport, replacing `snsregd.py`.
5. Proximity through `iio-sensor-proxy` → in-call blanking, end to end.
