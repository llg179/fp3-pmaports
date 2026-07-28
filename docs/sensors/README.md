# Sensors

Why no sensor works on the FP3 under pmOS mainline, and how far the fix has got.

This page is written as a **walkthrough of the investigation**: each step states
what was believed, what was measured, and what that forced us to conclude —
including the three places where the belief was wrong. Every capture and every
tool it refers to is checked in here, so nothing has to be taken on trust.

**Status (2026-07-29): the accelerometer reads 1 g.** After a one-line fix to a
QRTR control constant, the registry server works, the SSC brings up the real
hardware, and the ported IIO drivers deliver data:

```
      x        y        z     |g|
   -0.343    0.409   -9.685   9.700 m/s^2
   -0.348    0.425   -9.695   9.710 m/s^2
```

That is the first sensor reading on this port. Proximity is the next channel —
the SSC enumerates it, the driver for it is written but not yet measured. See
[step 10](#step-10--the-first-reading).

⚠️ Read [the correction](#correction-2026-07-28--every-publish-in-steps-48-was-a-bye)
before trusting steps 4–8: the control code used to publish a QMI service was
wrong throughout, so those runs announced a *node death* rather than a service.

| path | what it is |
|---|---|
| [`tools/`](tools/) | the instruments — see [Tools](#tools) |
| [`data/`](data/) | registry, group map, service lists, factory `sns.reg` — see [Data](#data) |
| [`captures/`](captures/) | the raw ADSP diag captures behind every number below |

---

## Correction (2026-07-28) — every "publish" in steps 4–8 was a BYE

The tools here published a QMI service by sending a QRTR control packet whose
`cmd` field they set from a hand-written constant table. That table was wrong.
The kernel's `include/uapi/linux/qrtr.h` says:

```c
enum qrtr_pkt_type {
	QRTR_TYPE_DATA		= 1,
	QRTR_TYPE_HELLO		= 2,
	QRTR_TYPE_BYE		= 3,
	QRTR_TYPE_NEW_SERVER	= 4,
	...
```

The enum starts at **1**, not 0. The tools used `3` for `NEW_SERVER` — which is
`BYE`. (An earlier round used `2`, was correctly spotted as wrong, and was
"fixed" to `3`: still wrong, by the same one.) So **not one service was ever
published**. Every run announced that our entire node had died.

That single fact explains, without any remaining mystery:

* **why zero `SNS_REG_GROUP` requests were ever served** — there was nothing to
  send them to;
* **why the wake looked edge-triggered and one-shot per ADSP boot** — a `BYE`
  forces the name service to tear down every server on the node and re-announce,
  which is an edge by construction, not a property of the sensor task;
* **why publishing the gate list "deleted the system's own daemons"** — it did,
  and not because four entries collided: one `BYE` kills *every* server on the
  node. The collision theory in [step 8](#the-gate-list-and-a-trap-that-cost-hours)
  was the right symptom with the wrong mechanism.

**What survives**, because it never depended on the control code:

* the F3/diag instrument and the whole read side of the trace;
* the reading of the wake message `L307 [1, 271, 0]` → service `0x10F`, and its
  byte-for-byte agreement with `sns-reg`'s `SNS_REG_QMI_SVC_ID`;
* the upstream survey in [step 7](#step-7--the-search-that-should-have-come-first);
* the registry extracted from this phone's own `sns.reg`;
* the co-processor-side elimination in [step 6](#step-6--rule-out-the-co-processor-side)
  (rcinit diff, node 7 loopback, `pd-mapper`).

**Already re-measured and gone: the gate list.** Every run since the fix has
published **`0x10F` and nothing else** — `qrtrls.py` shows node 1 carrying only
the system's own four services plus our `SNS_REG` — and the sensor stack still
comes up in full. The 31 "gates", the one-port-per-service rule and the trap
about colliding entries were all artifacts of the BYE: publishing 31 of them
meant sending 31 node-death announcements, which is why more of them "helped".
[`data/gates.txt`](data/gates.txt) is kept only as a record of the oracle's
service table; nothing needs it.

**What must be re-measured**, because it was produced by BYE traffic:

* the whole error-layer table in [step 5](#step-5--peel-the-error-layers-one-publish-at-a-time),
  including `L1206 [1]` and "31 drivers up";
* the ordering rule in [step 8](#the-wake-up-is-edge-triggered-and-ordering-decides-everything)
  — already contradicted: the SSC reads the registry the moment `0x10F` appears,
  with no SSR and no ordering to get right;
* "Sensor Manager never registers": **disproved** — see
  [step 9](#step-9--the-gate-opens-the-sensor-manager-registers);
* the error-layer table itself, which is the only item on this list still open.

Two further method notes from the same afternoon, because both produced
convincing-looking negatives:

* **`sensdiag.py` captured 0 messages because `rpmsg_char` was not loaded.**
  `bind_diag()` swallows the `OSError`, so a missing instrument is indistinguishable
  from a silent ADSP. `modprobe rpmsg_char` and assert the driver directory exists
  before trusting any empty capture.
* **`tracing_on` was `0`,** so an ftrace-based check of whether packets reached the
  name service returned an empty buffer — which read exactly like "the packets are
  being dropped". Enabling events is not enough; check `tracing_on`.

The codes now live in one place, [`tools/qrtrconst.py`](tools/qrtrconst.py),
transcribed from the kernel header, and the three tools import them.

> **Lesson.** A protocol constant is not a detail you may reconstruct from memory.
> Two independent "corrections" landed on two different wrong values, and both
> produced device behaviour interesting enough to build a week of theory on. The
> check that would have caught it on day one costs one command: read the header.
> And the deeper lesson — the wake-up *reproduced*, repeatedly, which is exactly
> what made it convincing. A reproducible effect proves your action does
> something, never that it does what you named it.

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

> ⚠️ **This whole step is invalid as written.** Every "published" row below was a
> `BYE`, not a service registration — see [the correction](#correction-2026-07-28--every-publish-in-steps-48-was-a-bye).
> The trace numbers are real; what produced them is not what the table claims. It
> is kept here because the re-measurement has to be diffed against it.

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

> ⚠️ **Invalid as written** — see [the correction](#correction-2026-07-28--every-publish-in-steps-48-was-a-bye).
> The ordering rule below is a faithful description of how *`BYE` traffic* behaves,
> which is why it reproduced so cleanly. Whether a real `NEW_SERVER` is also
> edge-triggered is now an open question, and the first thing to re-measure.

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

## Step 9 — the gate opens: the Sensor Manager registers

Fixing the control code changed everything within the hour. With a **real**
`NEW_SERVER`, the name service accepts the registration —

```
  1       271 0x010f    2     0  0x4018  SNS_REG
```

— and the SSC starts reading the registry **immediately, with no SSR at all**.
The requests arrived before the planned ADSP restart even ran, which settles the
ordering question: the sensor task had been parked waiting since boot, and a
genuine publish satisfies it. Everything about "edge-triggered, once per ADSP
boot" belonged to the BYE, not to this.

**1624 groups served in 90 s** — the first registry traffic in the whole
investigation. But the init still did not finish: three groups came back
forever.

```
43 × group 20      43 × group 2691      43 × group 3050
```

Those three are in **neither** of upstream's maps: not in the key map, and not
in the `group_map[]` binary map that gives a group's offset and size inside
`sns.reg`. Upstream answers `QMI_RESULT_FAILURE` for an unmapped group, and on
this phone that deadlocks the SSC: it re-requests and never proceeds. So an FP3
needs groups an msm8996 never had.

Rather than guess three offsets into a 25 KB blob, the cheapest experiment was
to answer **SUCCESS with a zero payload** (`snsregd.py`'s `ZEROFILL`, argv[3]) and
watch whether the retries stopped. They did — and the sensor framework came up:

| | before | after |
|---|---|---|
| QRTR services total | 49 | **74** |
| services on node 5 (SSC) | 6 | **32** |
| `256 / v1 / instance 50` | absent | **present, port 0x000a** |

That is exactly the Sensor Manager registration this page spent nine steps
saying never happens. It answers real QMI too — an empty request returns a
proper response, not an echo:

```
msg 0x0004 <- (5, 10): 02 0100 0400 0700  02 0400 0100 1100
                       ^RESPONSE          ^result=1 err=0x11 (MISSING_ARG)
```

`MISSING_ARG` is the correct complaint about an argument-less request. The
service is alive.

It survives a cold boot: with `snsregd` installed as a systemd unit, 32 sensor
services and the Sensor Manager are up on every boot with no manual step.

> **Lesson.** The deadlock was not in the protocol we had reverse-engineered but
> in the *failure* path of it. Upstream's `FAILURE` answer is correct on the
> hardware upstream has; here it is a hang. When a correct implementation stalls,
> look at what it does when it does not know something.

## Step 10 — the first reading

With the Sensor Manager registered, the rest was a port rather than an
investigation. Four commits from `msm8996-mainline/linux`
`msm8996-staging-smgr` (`30bb1314cc79`), all Yassine Oudjana's, apply to the
7.1.3 base unchanged:

| commit | what it does |
|---|---|
| net: qrtr: Turn QRTR into a bus | makes discovered QMI services bindable devices |
| net: qrtr: Define macro to convert QMI version and instance | |
| WIP: iio: Add Qualcomm Sensor Manager driver | the SMGR core: enumerates sensors, requests buffering, pushes samples to IIO |
| WIP: iio: accel: Add driver for SMGR accelerometers | |

They build clean on 7.1.3 — the `bus_type`, `uevent` and `devm_iio_kfifo_buffer_setup`
signatures all still match. On the device the bus creates ~70 devices, and the
core enumerates four sensors:

```
/sys/bus/platform/devices/qcom-smgr-accel.0
/sys/bus/platform/devices/qcom-smgr-gyro.10
/sys/bus/platform/devices/qcom-smgr-mag.20
/sys/bus/platform/devices/qcom-smgr-prox-light.40
```

`iio:device2` appears as `qcom-smgr-accel`. It is buffer-only — no `*_raw`
attributes — so a reading means enabling the scan elements and reading 24-byte
records from `/dev/iio:device2`: three s32 values, four bytes of padding, then a
64-bit timestamp. Scaled by `in_accel_scale`:

```
      x        y        z     |g|
   -0.343    0.409   -9.685   9.700 m/s^2
   -0.348    0.425   -9.695   9.710 m/s^2
   -0.329    0.425   -9.695   9.709 m/s^2
```

9.70 m/s² with the phone flat on a desk. **The chain works end to end**:
`snsregd` → SSC init → Sensor Manager on QRTR → QRTR bus → SMGR core →
`smgr_accel` → IIO.

### What the SSC is actually driving

The boot trace is no longer QShrink-stripped once the registry is served, and it
names the hardware:

* **`sns_dd_icm206xx.c`** — an InvenSense ICM-206xx IMU, taken through
  `chip_read_id`, soft reset, FSR, filter, FIFO, ODR and `chip_enable_sensor`.
* **`dd_epl259x.c`** — an EPL259x proximity + ambient light sensor:
  `set_psensor_intr_threshold`, `set_lsensor_intr_threshold`, `enable_pflag`,
  `enable_lflag`.
* `sns_sam_*` — the algorithm manager, reading gyro_cal and qmag_cal parameters
  out of the registry we serve.

1233 SENSORS messages on a boot, **zero error lines**. Compare that with the 12
messages and silence of [step 2](#step-2--the-task-is-not-failing-it-is-waiting).

### What is still missing

* **Proximity is written but unmeasured.** `qcom-smgr-prox-light` was enumerated
  and unbound, because upstream only has an accelerometer driver;
  `drivers/iio/proximity/smgr_prox.c` here binds it and exposes proximity and
  light channels. Which of the report's three u32 values is which is an
  assumption until someone puts a finger over the sensor.
* **Groups 20, 2691 and 3050 are zero-filled, not real.** The stack initialises,
  but whatever those groups configure is wrong. They need their real offsets in
  `sns.reg`, or their key lists.
* **Gyro and magnetometer have no driver** — both are enumerated and unbound.
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
| [`tools/qrtrconst.py`](tools/qrtrconst.py) | the QRTR control codes, transcribed from the kernel uapi header. **Import these; do not retype them** — see [the correction](#correction-2026-07-28--every-publish-in-steps-48-was-a-bye) |
| [`tools/qrtrls.py`](tools/qrtrls.py) | enumerates every QMI service the name service knows, by node. The one command that shows whether the sensor stack is up |
| [`tools/snsregd.service`](tools/snsregd.service) | systemd unit that keeps the registry server running from boot |

### Traps worth knowing before touching any of this

* **`QRTR_TYPE_*` starts at 1:** `DATA=1, HELLO=2, BYE=3, NEW_SERVER=4,
  DEL_SERVER=5, DEL_CLIENT=6, RESUME_TX=7, EXIT=8, PING=9, NEW_LOOKUP=10,
  DEL_LOOKUP=11`. Take them from [`tools/qrtrconst.py`](tools/qrtrconst.py), never
  from memory — guessing them wrong is what invalidated steps 4–8 (see [the
  correction](#correction-2026-07-28--every-publish-in-steps-48-was-a-bye)).
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

### The boot-hang safety net

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

1. **Measure proximity.** The driver is in; a finger over the sensor decides
   whether the value mapping is right.
2. **Proximity through `iio-sensor-proxy` → in-call blanking**, which is the
   original goal and the only step left after 1.
3. **Find the real content of groups 20, 2691 and 3050** — their offsets in
   `sns.reg`, or their key lists.
4. Drivers for the enumerated gyro and magnetometer.
5. Package upstream's C `sns-reg` as an aport, replacing `snsregd.py`.
