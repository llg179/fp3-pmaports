# Sensors

Why no sensor works on the FP3 under pmOS mainline, and how far the fix has got.

This page is written as a **walkthrough of the investigation**: each step states
what was believed, what was measured, and what that forced us to conclude —
including the three places where the belief was wrong. Every capture and every
tool it refers to is checked in here, so nothing has to be taken on trust.

**Status (2026-07-28): not working yet.** The blocker is understood and its first
layer is removed; [step 9](#step-9--what-is-still-missing) says exactly what is
left. Nothing here is a shipping feature.

| path | what it is |
|---|---|
| [`tools/`](tools/) | the instruments — see [Tools](#tools) |
| [`data/`](data/) | registry, group map, service lists, factory `sns.reg` — see [Data](#data) |
| [`captures/`](captures/) | the raw ADSP diag captures behind every number below |

---

## Step 0 — the question, and why it is not a driver question

The goal was ordinary: *make the proximity sensor blank the screen during a call.*
On phosh that needs four layers — an IIO proximity device, a `nearlevel`
threshold, `iio-sensor-proxy`, and phosh's in-call proximity claim. Layers 2–4
are **already installed and working** on this device (phosh 0.55,
`iio-sensor-proxy` 3.9, `calls` 50.0, `callaudiod`); see
[The userspace side](#the-userspace-side).

Layer 1 is the problem, and it is not a matter of writing an I²C driver. On the
FP3 every sensor hangs off the **SSC** — a protected domain inside the ADSP with
its own I²C controllers. The factory device tree has **zero** sensor nodes, so
there is no bus for the AP to drive. The only way in is the **Sensor Manager**
QMI service the SSC exposes. On pmOS that service never appears.

So the question became: why not?

## Step 1 — build an instrument where there wasn't supposed to be one

The SSC's own debug log (Qualcomm F3) is the only window into it. Downstream this
comes through `/dev/diag`, which mainline does not have — which is why earlier
rounds treated the SSC as unobservable.

It turned out the ADSP's DIAG channels *are* present on mainline, just unbound:
`modprobe rpmsg_char`, write `rpmsg_chrdev` into the channel's `driver_override`,
bind it, and the stream is there. That is [`tools/sensdiag.py`](tools/sensdiag.py).

Two details that cost a rerun each: the ADSP's remoteproc **index moves between
boots**, so it must be located by name; and an SSR destroys and recreates the
channels unbound, so the tool re-binds itself. Strings are stripped by QShrink, so
messages are identified by source line — `L307` means "line 307 of some sensor
source file".

## Step 2 — the task is not failing, it is waiting

A cold boot yields exactly **12** SENSORS messages in 6.8 ms, then silence. The
obvious reading was a crash, and the last message, `L635 (100000, 65534)`, looked
like an error code. Hypotheses were built on it for two rounds.

Then the same 12 messages were pulled off the working Ubuntu Touch side. They are
**multiset-identical** — same lines, same arguments, `L635` included. So `L635` is
a normal value, and the task is not dying; it is **blocking**. On UT it resumes
3.68 s later. On pmOS it never does.

> **Lesson.** An error hypothesis built on the broken side alone is worth very
> little. Compare the *beginning* of the working side, not just the end of the
> broken one.

## Step 3 — the wake-up message names what it is waiting for

The first message of the UT resume is:

```
L307 [1, 271, 0]
```

`271` is `0x10F`. In the oracle's QMI service table
([`data/ut_servers.txt`](data/ut_servers.txt)) that service sits on node 1 — the
AP — owned by `sensors.qti`. The three arguments read as `(node, service,
instance)`.

So the hypothesis: the SSC is waiting for an **AP-provided QMI service**, and
mainline provides nothing.

## Step 4 — test it by *becoming* the missing half

The obvious next instrument was to capture the QMI exchange on the oracle. The
cheaper and stronger move was to create the missing half on pmOS: publish service
`0x10F` ourselves and see what happens. The mainline kernel carries the QRTR name
service itself (`qrtr_ns`), so this needs one socket and one control packet —
[`tools/snsreg.py`](tools/snsreg.py).

The moment it is published, the task wakes:

| | before | after |
|---|---|---|
| SENSORS messages | 12 | **131** |
| first message | — | `L307 [1, 271, 0]` — *identical to the oracle* |

Capture: [`captures/pmos_f3_wake.bin`](captures/pmos_f3_wake.bin). The whole
resume — `L275`/`L286`/`L383`, then `L464`+`L2451` pairs across ids 3300–3329 and
2800 — matches the oracle message for message.

> **Lesson.** When the hypothesis is "X is missing", *supplying* X is both cheaper
> and better evidence than observing X on a working system.

## Step 5 — peel the error layers, one publish at a time

One service was not enough. The trace's closing message `L1206` carries `1` on
success and `0` on failure — the cheapest pass/fail indicator in the whole log —
and it said `0`.

| published | per-sensor result | `L1206` | capture |
|---|---|---|---|
| `0x10F` only | `L487 [-18]` ×31, `L581 [id,5]` ×30 | **`[0]` failed** | [`pmos_f3_long.bin`](captures/pmos_f3_long.bin) |
| all 36 of the oracle's node-1 services, **one port** | `L173 [-2, 4]` ×31 | `[1]` | [`pmos_f3_multi.bin`](captures/pmos_f3_multi.bin) |
| the same 36, **one port each** | none — all `L2451 [id, 2]` | **`[1]` clean** | [`pmos_f3_ports.bin`](captures/pmos_f3_ports.bin) |

The last row is the result: **the SSC's sensor init runs to completion on pmOS,
all 31 sensor drivers up, zero errors.**

Note what the middle row cost: publishing all 36 services on a *single socket*
produced 31 failures. On the oracle each service sits on its own port. **The
topology is part of the protocol** — copying a registration table means copying
its shape, not just its contents.

> **Lesson.** Error codes layer. Each fix reveals the next one; stopping at the
> first `L1206 [1]` would have looked like success.

## Step 6 — rule out the co-processor side

If the AP is now doing everything the oracle does, is the ADSP itself different?

The `ss_id=100` (rcinit) band carries plain text on both sides. Capturing it on
pmOS needs a controlled SSR — the F3 mask can only be armed after the DIAG channel
opens, so a cold boot always misses it. Normalised and diffed against the oracle,
the ADSP's init sequence is **identical**, `qup_manager_init`, `i2cbsp_init`,
`sysmon_sensors_user_init` and `device open SENSORS` included. The only
differences are SSR notices about other subsystems.

Capture: [`captures/pmos_f3_ssr_services.bin`](captures/pmos_f3_ssr_services.bin).

A side question closed at the same time: `qrtr-lookup` shows a `Sensor Manager`
service (256) on node 7, but at version 0 / instance 1 rather than the oracle's
v1/instance 50. Five different QMI message ids sent to it with
[`tools/qmiprobe.py`](tools/qmiprobe.py) came back as **the exact bytes sent**,
transaction id and all. It is a loopback echo, not the service.

## Step 7 — the search that should have come first

At this point the protocol had been reconstructed from scratch. One web search
would have supplied it on day one:

> `SSC sensors mainline linux Qualcomm SMGR QMI postmarketOS proximity ADSP`

The top hits — the [postmarketOS wiki page on the Snapdragon Sensor
Core](https://wiki.postmarketos.org/wiki/Qualcomm_Snapdragon_Sensor_Core) and the
LWN announcement of [QRTR bus and Qualcomm Sensor Manager IIO
drivers](https://lwn.net/Articles/1016590/) — describe this exact problem and
state the ordering the measurements had just rediscovered:

> Before Sensor Manager becomes accessible, another service known as Sensor
> Registry needs to be provided by the AP, after which the remote processor will
> request data from it and then expose several services including Sensor Manager.

The follow-up search `Yassine Oudjana Qualcomm Sensor Manager IIO driver patch
series QRTR bus sensor registry server` located the code.

### What exists upstream

| component | what it does | where | revision |
|---|---|---|---|
| **`sns-reg`** | the AP-side Sensor Registry QMI server; emulates the Android sensor daemon | <https://gitlab.com/msm8996-mainline/sns-reg> | `4d238e5f0baba3fb77456fe2bffbf8e8f18a71a0` (2025-07-06); tags `0.1` = `ad37ad305cde8b24544cb106215fec9ae4a2b135`, `0.0.1` = `739deb8799eaa3e0b7919b411fb77c505a04c781` |
| **`sns-reg-generator`** | converts a binary `sns.reg` into the plain-text registry the server reads | same repo | same |
| **QRTR bus + Sensor Manager IIO drivers** | QRTR becomes a bus; SMGR sensors become IIO devices (accel, gyro, magnetometer, **proximity**, pressure) | branch `msm8996-staging-smgr` of <https://gitlab.com/msm8996-mainline/linux> | `30bb1314cc798f1df15e902ae53238de2b27bc90` |
| **pmaports packaging** | draft aports for the above | [pmaports MR !4118](https://gitlab.com/postmarketOS/pmaports/-/merge_requests/4118) | **draft, unmerged**; project archived |

Author: Yassine Oudjana; LKML posting [PATCH v2
0/4](https://lkml.org/lkml/2025/7/17/895), July 2025, **not in mainline** —
review was still on the platform-device/auxbus question. **MSM8953 is explicitly
in scope**: on this SoC Sensor Manager is hosted by the ADSP, which is why ours
would appear on QRTR node 5.

### Where the two derivations agree — and where they don't

`sns-reg`'s `qmi/sns_reg.h`:

```c
#define SNS_REG_QMI_SVC_ID       0x010f
#define SNS_REG_QMI_SVC_V1       2
#define SNS_REG_QMI_INS_ID       0
#define SNS_REG_GROUP_MSG_ID     0x4
```

Service id, version and instance are byte-for-byte what step 4 arrived at
independently, and the group ids in its `map.c` (3300…3329, 2800) are exactly the
ids our trace shows in `L2451 [id, 2]`.

The one line the measurements had *not* produced is `SNS_REG_GROUP_MSG_ID = 0x4`
— the request itself. **That is precisely the gap**: the service was published
but never *served*, which is why the SSC never sent anything.

> **Lesson.** Search for prior art before reverse-engineering. And when you find
> it, diff it against your own model — the difference is the hole in your
> hypothesis.

## Step 8 — integrating it, and what the integration taught

### The registry, from this phone's own calibration

pmOS does not mount `persist`, where the factory registry lives:

```
mount -o ro /dev/disk/by-partlabel/persist /mnt/persist
./sns-reg-generator /mnt/persist/sensors/sns.reg > registry.conf
```

* [`data/sns.reg`](data/sns.reg) — 25 468 B, md5 `30367ee6da871d9a65340532b2472a99`
* [`data/registry.conf`](data/registry.conf) — **1437 key/value pairs**

The same directory holds the factory calibration as plain files, which the
registry embeds: `ps_near=1570`, `ps_far=0`, `als_factor=1297`, `accel_x=0.22`,
`accel_y=-0.09`, `accel_z=-0.29`.

### A Python registry server

[`tools/snsregd.py`](tools/snsregd.py) — same protocol, same licence
(GPL-3.0-or-later), ~150 lines. `sns-reg` is C + SCons + libqrtr and would need a
cross-toolchain or an aport before answering a single request; the protocol is one
message, so this gets a live answer in one step. The C daemon is the packaged end
state.

Request `TLV 0x01 = u16 group id`; response `TLV 0x02 = u16 result`,
`TLV 0x03 = u16 group id`, `TLV 0x04 = u16 length + payload`, the payload being
the group's keys concatenated little-endian.

[`data/groups.txt`](data/groups.txt) carries upstream's 68 groups / 1516 keys in a
form the server can read without parsing C. **Caveat:** that map was
reverse-engineered on MSM8996 and is **not yet validated for the FP3** — upstream
ships `sns-reg-validator` for exactly this.

### The gate list, and a trap that cost hours

[`data/gates.txt`](data/gates.txt) is the set of node-1 services to publish
*alongside* `0x10F`. It is deliberately **not** the oracle's full 36.

Four of the oracle's entries are services **pmOS already provides**, matching on
service *and* instance: `14/1` (rfs), `49/257` (IPA), `52/257` (DHMS) and
`4096/1` (the first TFTP instance — `4096/2…10` do *not* collide and must stay).
Publishing those shadows the real daemons, and withdrawing them on exit **deletes
the real daemons' registrations from the name service**. After that the ADSP
cannot reach `tqftpserv`, and sensor init cannot proceed.

This is what made a previously known-good measurement stop reproducing for the
rest of a session — and the wasted hours went into "what changed on the device?"
rather than into the actual problem.
[`data/node1_services.txt`](data/node1_services.txt) keeps the unfiltered oracle
list for reference only.

> **Lesson.** When a known-good measurement suddenly stops reproducing, suspect
> the side effects of your own previous runs before anything else. Diff the
> system-level registries against a fresh boot.

### The wake-up is edge-triggered, and ordering decides everything

Two behaviours make this very easy to mismeasure:

* **It fires once per ADSP boot.** A second publish yields only `L307`.
* **It is an edge, not a level.** The task waits for `NEW_SERVER` to *arrive*. A
  service already published when the ADSP boots does **not** satisfy it — the task
  prints its prologue and stops, exactly as if nothing had been done. A boot-time
  unit that publishes before the ADSP comes up therefore achieves nothing.

The working order, confirmed by a controlled A/B (79 SENSORS messages where the
previous attempts produced zero):

1. publish the gates and **leave them up**;
2. SSR the ADSP (or boot it) so the sensor task is freshly waiting;
3. publish `0x10F` **after** that, as a fresh event.

Publishing `0x10F` first, or together with the gates, produces nothing at all.

### A lead raised and killed the same hour

`pd-mapper` fails permanently on this device — `no pd maps available`, because
there are **zero `.jsn` PD maps** anywhere: not in `/lib/firmware`, not on
`vendor_a/b`, not on `modem_a/b` or `dsp_a/b`. Since `pd-mapper` provides the
servreg locator by which remote protection domains announce themselves — the SSC's
sensor PD among them — this looked like the missing piece.

It is not. The oracle's service table has **no servreg locator either** (services
64 and 66 are both absent from [`data/ut_servers.txt`](data/ut_servers.txt)), so
the working system does not use that path. Hypothesis closed in one offline check
against data already on disk.

## Step 9 — what is still missing

* **Sensor Manager never registers.** Even after a completely clean init
  (`L1206 [1]`, 31 drivers up), no `256 / v1 / instance 50` appears on node 5 — so
  there is still no data path, and nothing for an IIO driver to read.
* **Not one registry request has been served.** With `snsregd.py` published and
  waiting, the request count has stayed at zero in every run, so the server's
  response path is written but **unexercised**, and the group map and registry
  values are untested. This is the gate everything else is behind.
* **The kernel drivers are not ported** — `msm8996-staging-smgr` has to be rebased
  onto our 7.1.3 base.

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

Verified live; nothing to do here once a sensor source exists:

```
phosh 0.55   iio-sensor-proxy 3.9 (+udev, +systemd)   calls 50.0   callaudiod
```

The chain: an IIO proximity device with `in_proximity_nearlevel` (from the DT
property `proximity-near-level`) → udev tags it → `iio-sensor-proxy` exports
`net.hadess.SensorProxy` with `HasProximity`/`ProximityNear` → phosh claims
proximity during a call and powers the output off. Today `net.hadess.SensorProxy`
is absent from the bus, because the only IIO devices are the two PMIC ADCs:

```
iio:device0 = 200f000.spmi:pmic@2:adc@3100
iio:device1 = 200f000.spmi:pmic@0:adc@3100
```

A missing `in_proximity_nearlevel` is a classic silent failure: the sensor reads
fine, `ProximityNear` never flips, the screen never blanks.

## Tools

| file | what it does |
|---|---|
| [`tools/sensdiag.py`](tools/sensdiag.py) | ADSP F3 capture on mainline: locates the ADSP remoteproc by name, binds `rpmsg_chrdev` to its DIAG channels, re-arms the F3 mask every 0.25 s, re-binds after an SSR; optional `ssr` argument restarts the ADSP mid-capture |
| [`tools/parsef3.py`](tools/parsef3.py) | host-side parser: HDLC de-framing, message header, bounds-checked argument extraction |
| [`tools/snsreg.py`](tools/snsreg.py) | publishes a list of QMI services over QRTR, **one socket per service**, dumping everything that arrives |
| [`tools/snsregd.py`](tools/snsregd.py) | the Sensor Registry server |
| [`tools/qmiprobe.py`](tools/qmiprobe.py) | sends empty QMI requests to a `node:port` and prints replies |

### Traps worth knowing before touching any of this

* **`QRTR_TYPE_*` is off by one from the obvious guess:** `DATA=0, HELLO=1,
  BYE=2, NEW_SERVER=3, DEL_SERVER=4`. Sending `2` tells the name service the whole
  node died, and it answers with `DEL_SERVER` for every server on it.
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

### Recovering the rootfs from the other slot

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

1. Get one real `SNS_REG_GROUP` request served, using the ordering from step 8.
2. Validate the group map against the FP3 (`sns-reg-validator`); fix what differs.
3. Confirm Sensor Manager registers on node 5 once the registry is actually served.
4. Port `msm8996-staging-smgr` onto the 7.1.3 base; package `sns-reg` as an aport,
   replacing `snsregd.py`.
5. Proximity through `iio-sensor-proxy` → in-call blanking, end to end.
