# Bringing up the FP3 sensors

The investigation behind [`../README.md`](../README.md), kept as a narrative:
what was believed at each step, what was measured, and what that forced us to
conclude — including the places where the belief was wrong and had to be
retracted. The reference material — what the port consists of, where each piece
came from, how to build and test it — is in the README; this is the reasoning,
and the instruments and raw data that produced it.

> **AI-generated.** Written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed it and performed every physical
> measurement it reports. The same applies to most of the code it describes —
> see the provenance table in [`../README.md`](../README.md#provenance) for who
> wrote what. Treat the reasoning as reviewed but not infallible: three
> conclusions in here were stated confidently and later retracted, and they are
> left in place, marked, because the retractions are the useful part.

Nothing here is needed to run the sensors. Everything that is, lives in
[`../../../userspace-sensors/`](../../../userspace-sensors/).

## The instruments

| file | what it does |
|---|---|
| [`tools/sensdiag.py`](tools/sensdiag.py) | ADSP F3 capture on mainline: locates the ADSP remoteproc by name, binds `rpmsg_chrdev` to its DIAG channels, re-arms the F3 mask every 0.25 s, re-binds after an SSR; optional `ssr` argument restarts the ADSP mid-capture |
| [`tools/parsef3.py`](tools/parsef3.py) | host-side parser: HDLC de-framing, message header, bounds-checked argument extraction |
| [`tools/snsreg.py`](tools/snsreg.py) | publishes a list of QMI services over QRTR, **one socket per service**, dumping everything that arrives |
| [`../../../userspace-sensors/snsregd.py`](../../../userspace-sensors/snsregd.py) | the Sensor Registry server |
| [`tools/qmiprobe.py`](tools/qmiprobe.py) | sends empty QMI requests to a `node:port` and prints replies |
| [`tools/qrtrconst.py`](tools/qrtrconst.py) | the QRTR control codes, transcribed from the kernel uapi header. **Import these; do not retype them** — see [the correction](#correction-2026-07-28--every-publish-in-steps-48-was-a-bye) |
| [`tools/qrtrls.py`](tools/qrtrls.py) | enumerates every QMI service the name service knows, by node. The one command that shows whether the sensor stack is up |
| [`../../../userspace-sensors/snsregd.service`](../../../userspace-sensors/snsregd.service) | systemd unit that keeps the registry server running from boot |
| [`tools/readaccel.py`](tools/readaccel.py) | reads the buffer-only accelerometer and prints m/s² and \|g\| — the physical sanity check that catches a wrong record size |
| [`tools/readprox.py`](tools/readprox.py) | the same for the proximity/light device |
| [`tools/smgrbuf.py`](tools/smgrbuf.py) | sends `SNS_SMGR_BUFFERING` by hand and sweeps its parameters, so a question costs a second instead of a 30-minute kernel build |
| [`tools/smgrind.py`](tools/smgrind.py) | asks for buffering on one sensor and prints the indications the SSC sends back — answers "is this data really from that sensor" from the wire |
| [`../../../userspace-sensors/sensortest.py`](../../../userspace-sensors/sensortest.py) | reads any of the four sensors and prints per-axis ranges, so "it binds" can be told from "it measures"; for the gyroscope it also integrates the run, which turns a known rotation into a scale check |
| [`../../../userspace-sensors/proxcal.sh`](../../../userspace-sensors/proxcal.sh) | prints `in_proximity_raw` once a second so a hand over the earpiece shows up as two levels — the measurement that decides `PROXIMITY_NEAR_LEVEL`, and the one that cannot be made remotely |
| [`tools/sensinfo.py`](tools/sensinfo.py) | asks the SSC what a sensor advertises (`ALL_SENSOR_INFO`, `SINGLE_SENSOR_INFO`) — data types, rates, vendor and part name. Ask this before asking for data |
| [`tools/smgrsweep.py`](tools/smgrsweep.py) | streams one sensor with the **driver's own** request parameters, data type as an argument, and counts indications. Use this rather than inventing a report rate: it is `sample_rate * 0xf000`, and a wrong one silently means "one report every two minutes" |

## Raw data

| file | contents |
|---|---|
| [`data/sns.reg`](data/sns.reg) | the FP3's factory binary sensor registry |
| [`../../../userspace-sensors/registry.conf`](../../../userspace-sensors/registry.conf) | 1437 key/value pairs generated from it |
| [`../../../userspace-sensors/groups.txt`](../../../userspace-sensors/groups.txt) | 68 groups / 1516 keys from upstream `map.c` |
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
* [`../../../userspace-sensors/registry.conf`](../../../userspace-sensors/registry.conf) — **1437 key/value pairs**

The same directory holds the factory calibration as plain files, which the
registry embeds: `ps_near=1570`, `ps_far=0`, `als_factor=1297`, `accel_x=0.22`,
`accel_y=-0.09`, `accel_z=-0.29`.

### A Python registry server

[`../../../userspace-sensors/snsregd.py`](../../../userspace-sensors/snsregd.py) — same protocol, same licence
(GPL-3.0-or-later), ~150 lines. `sns-reg` is C + SCons + libqrtr and would need a
cross-toolchain or an aport before answering a single request; the protocol is one
message, so this gets a live answer in one step. The C daemon is the packaged end
state.

Request `TLV 0x01 = u16 group id`; response `TLV 0x02 = u16 result`,
`TLV 0x03 = u16 group id`, `TLV 0x04 = u16 length + payload`, the payload being
the group's keys concatenated little-endian.

[`../../../userspace-sensors/groups.txt`](../../../userspace-sensors/groups.txt) carries upstream's 68 groups / 1516 keys in a
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

Userspace picks it up without any further work — `iio-sensor-proxy` answers

```
HasAccelerometer: true    AccelerometerTilt: 'face-down'
HasProximity:     false   HasAmbientLight:   false
```

so the layers above IIO were, as [step 0](#step-0--the-question-and-why-it-is-not-a-driver-question)
claimed, already in place and only ever waiting for a device.

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

## Step 11 — proximity binds, and then does not stream

The driver loads and the device appears:

```
/sys/bus/iio/devices/iio:device2 = qcom-smgr-accel
/sys/bus/iio/devices/iio:device3 = qcom-smgr-prox-light
```

with `in_proximity` and `in_illuminance` channels. But enabling its buffer fails:

```
smgr 5-10: Requesting buffering for sensor 0x28, report rate: 3072000, sample rate: 50
qmi_encode: Invalid data length
smgr 5-10: Failed to send buffering request: -22
smgr 5-10: Buffering request failed: 0x501
```

Read that carefully — the `0x501` is a red herring. It is the response to the
*teardown* IIO issues after the enable fails; the actual failure is `-22` from
**`qmi_encode`, before anything reaches the SSC**.

Two controls pin it down, and both say the SSC is innocent:

* **Hand-built requests work.** [`tools/smgrbuf.py`](tools/smgrbuf.py) sends
  `SNS_SMGR_BUFFERING` over QRTR with the wire format read off the driver's own
  `qmi_elem_info`. For sensor 0x28 **all 19 parameter combinations succeed**,
  including the driver's exact defaults. (The same sweep on the accelerometer
  returns `result=1 error=5` — i.e. `0x501` — only for `data_type=1`, which is
  how we know `0x501` means "no such data type on this sensor".)
* **The accelerometer at the proximity sensor's rate works.** Set
  `in_accel_sampling_frequency` to 50 and the driver sends
  `report rate: 3072000, sample rate: 50` — byte-identical numbers to the
  failing request — and gets `ack_nak 0`.

So the same struct, same rates, same QMI handle, encodes for one sensor and not
the other. One instrumented build settled it — printing the encoder's state at
the failing branch:

```
qmi_encode: Invalid data length: enc_level=1 data_type=9 tlv_type=0x4
            array_type=2 elem_len=2 elem_size=8 offset=10 data_len_value=2621441
```

`2621441` is `0x00280001`, and `0x28` is the proximity sensor's id. The array
length had eaten the sensor id.

**The bug is in the QMI core, not in the sensor driver.** `qmi_encode()` handles
a `QMI_DATA_LEN` element with

```c
memcpy(&data_len_value, buf_src, sizeof(u32));
```

— four bytes, whatever the field's declared width. The buffering request declares

```c
u8  item_len;
struct { u8 sensor_id; u8 data_type; u16 ...; } items[];
```

so the three bytes after `item_len` are one byte of padding and then the first
item's `sensor_id`. **For the accelerometer that id is 0, so the request encodes
correctly by luck.** For proximity it is `0x28`; the length becomes `0x00280001`,
fails the bounds check, and the request never leaves the AP. The gyroscope (id 10)
and magnetometer (id 20) would have failed the same way.

The fix reads the field at its declared width — the decode path already did, and
the bytes put on the wire are unchanged because `data_len_sz` is derived from
`elem_size` either way.

> **Lesson.** Everything pointed at "what is different about the proximity
> sensor", and the answer was that nothing is: the accelerometer is the special
> case, and it works only because its id happens to be zero. When one case works
> and one fails, it is worth asking which of the two is the accident.

> **Lesson.** The loudest error was not the error. `0x501` had a plausible story
> attached to it — "proximity is an on-change sensor, buffering is for streaming
> ones" — and that story would have led to writing a whole second QMI path. The
> `-22` two lines above it was the real failure, and one userspace probe was
> enough to show the SSC accepts what the driver is trying to send.

### With the fix: accepted, but one zero sample

The encoder fix works — the request now reaches the SSC and is accepted:

```
smgr 5-10: Requesting buffering for sensor 0x28, report rate: 3072000, sample rate: 50
smgr 5-10: Buffering response ack_nak 1
```

What it does *not* do yet is produce values. On a fresh boot, with only its own
buffer enabled, the proximity device delivers **exactly one sample, all zeros**,
and then nothing — including through 25 s of deliberately toggling the display
backlight to make light events. Listening on the wire with `smgrind.py` shows the
same thing from the SSC's side: one `0x22` indication carrying a zeroed sample,
then silence.

The accelerometer, measured the same way in the same boot, streams normally
(`z = -632470` raw, i.e. -9.69 m/s²), so the path is fine and this is specific to
this sensor.

That is consistent with an on-change sensor that has been armed but never
triggered — the EPL259x reports on threshold crossings, and the driver requests
`SNS_SMGR_DATA_TYPE_PRIMARY` at a fixed rate, which is the streaming model.
Whether it needs the secondary data type, a threshold set through a different
message, or simply a hand near the earpiece, is the next thing to measure.

**☠️ One measurement hazard found here:** hand-built QMI requests leave state
behind in the SSC. After a session of `smgrbuf.py`/`smgrind.py` probing, the
*accelerometer* also started returning zeros, which looked like a new bug and was
not — a reboot restored it. Reboot between probe sessions and real measurements.

### Step 12 — what the sensor itself says, and why nobody was reading it

Two things about the "one zero sample" turned out to be measurement artefacts of
my own, and one turned out to be real.

**First artefact: the report rate encoding.** The buffering request's
`report_rate` is not in Hz — the driver computes it as
`sample_rate * SMGR_REPORT_RATE_IN_HZ` with `SMGR_REPORT_RATE_IN_HZ = 0xf000`.
The first sweep sent `sample_rate * 100`, which in that encoding is one report
every two minutes, so the single indication it saw was just the initial one and
the sweep measured nothing at all. Redone with the driver's own numbers
(`report_rate = 3072000`, decimation 3, calibration 0xf), the accelerometer
gives **242 indications in 5 s** and proximity still gives exactly one.

So the SSC is healthy and the single sample is genuine, in the same boot,
against the same code path.

**What the sensor advertises.** `SINGLE_SENSOR_INFO` (msg `0x06`) is worth
asking before asking for data. On this phone:

| sensor | id | data types | max rate | supported rates |
|---|---|---|---|---|
| ICM20602 Accelerometer (InvenSense) | `0x00` | 1 | 50 | 10,15,20,25,40,50,100,125,200 |
| GYRO | `0x0a` | — | — | — |
| MAG | `0x14` | — | — | — |
| EPL259x ALS/PS (Eminent) | `0x28` | **2** | 50 | 1,5,10,20,30,40,50 |

The proximity sensor has **two data types where the accelerometer has one**, and
the core only ever asks for `SNS_SMGR_DATA_TYPE_PRIMARY`. The indication's
metadata says which one a sample came from: `val1` packs
`(data_type << 16) | (sensor_id << 8) | 1`, so `0x00012801` is sensor `0x28`
data type 1. Asking for data type 1 by hand did return a non-zero sample
(`0x00020000, 6, 0`) where data type 0 returns zeros — but not reproducibly, and
not at the driver's rate, so it is a lead and not yet a finding.

**The real one: nothing in userspace was ever going to read this device.**
`iio-sensor-proxy` has no buffered proximity driver at all — it polls
`in_proximity_raw`. Our device is buffer-only, so the proxy skipped it silently;
its log mentions only `iio:device2`, the accelerometer. Whatever the SSC does or
does not send, phosh could not have blanked the screen with it.

That is fixed in the driver rather than worked around: the Sensor Manager core
now keeps the last report per sensor and can start one on demand
(`smgr_sensor_read_sample()`), and `smgr_prox.c` exposes proximity as a raw
channel on top of it. An on-change sensor fits this better than the buffer
anyway — it answers immediately when a report is requested, which is exactly
what a poll needs.

Only proximity gets a raw channel. Which data type carries the light reading is
still open, and a fake `in_illuminance_raw` would have phosh dimming the screen
by a number of unknown provenance.

### Step 13 — proximity works, end to end

Measured with a hand over the earpiece, which is the one thing that could not
be done remotely. The sensor was never broken; it is on-change, and three
things had to be right before anything could see it.

**What the values mean.** Streaming the primary data type for 60 s while a hand
covered and uncovered the sensor, in a dark room:

| | `values[0]` | `values[1]` | `values[2]` |
|---|---|---|---|
| nothing near | `0` | 0..507 | 0 |
| hand over the earpiece | `65536` | 1713..2714 | 0 |

So `values[0]` is the SSC's own near/far decision as Q16 (`65536` = 1.0 = near)
and `values[1]` is a reflected-infrared count. The count *rises* when the sensor
is covered in a dark room, which is what settles it as infrared reflection
rather than ambient light. And the phone's factory calibration — `ps_near=1570`,
read out of `/persist` long before any of this — falls exactly between the two
measured ranges. Two independent sources agreeing.

**Why the raw channel reports the count and not the flag.** The flag is not
filled in on the first sample of a report. With a hand pressed on the sensor,
a one-shot read returned `flag=0` while the count read `13815`: a poll would
have answered "nothing near" with a hand on the phone. The count is live from
the first sample on.

**Why the report is never stopped.** Starting a report, taking a sample and
stopping it again is the tidy way to serve a raw read, and on this SSC it dies:
the first such read returned a sample and the next fourteen returned nothing at
all, until a reboot. Reads now start a report if none is running and leave it
running. An on-change sensor is quiet between changes anyway, so the stored
sample stays valid — and that is exactly what a poll wants.

**The result**, through the whole stack:

```
$ cat /sys/bus/iio/devices/iio:device5/in_proximity_raw
0                      # nothing near
1713                   # hand over the earpiece, 18 reads out of 18

$ sudo monitor-sensor --proximity
=== Has proximity sensor (near: 0)
    Proximity value changed: 1     # covered
    Proximity value changed: 0     # uncovered
    Proximity value changed: 1
```

The near level comes from a udev rule, since this device has no DT node to hang
`proximity-near-level` on — see [`userspace-sensors/`](../../../userspace-sensors/).

**The blanking lags by about a second, and that is upstream's poll period, not
ours.** Tracing the driver's read function shows `iio-sensor-proxy` reading the
sensor every **701 ms**:

```
611.739754  smgr_sensor_read_sample <-smgr_prox_read_raw
612.440757  smgr_sensor_read_sample <-smgr_prox_read_raw
613.141620  smgr_sensor_read_sample <-smgr_prox_read_raw
```

The kernel side is immediate — during the call, sampling at 0.5 s followed the
hand movements exactly. The interval is compiled into `iio-sensor-proxy`, so
shortening it means carrying a patched system package, and making the sensor
event-driven means an IIO event driver *and* a new proximity backend in
iio-sensor-proxy. **Decided (2026-07-29): leave it.** Every other pmOS phone
has the same latency; a local fork of a system package is not worth 500 ms.

☠️ `ProximityNear` on the bus stays `false` until a client **claims** the sensor;
`iio-sensor-proxy` does not poll otherwise. During a call phosh claims it. Reading
the property without a claim looks exactly like a broken sensor.

**Gyro and magnetometer bind too**, now that the QMI encoder no longer corrupts
requests for a non-zero sensor ID — `iio:device3 = qcom-smgr-mag`,
`iio:device4 = qcom-smgr-gyro`. Their scales are assumed rather than measured;
see the `TODO`s in the drivers.

### Step 14 — all four sensors, measured against physical reality

Binding a driver proves nothing about the numbers. Each sensor was moved by
hand while [`../../../userspace-sensors/sensortest.py`](../../../userspace-sensors/sensortest.py) read it, so that "the
driver works" means something.

| sensor | at rest | moved | verdict |
|---|---|---|---|
| accelerometer | \|v\| = 9.70 m/s², z = −9.7 | x −0.6…+9.7, y −11.3…+3.5, z −11.8…+4.5 | **passes** — every axis reaches ±1 g, so the three really are three directions |
| gyroscope | 0.01–0.04 rad/s bias | peaks to 25 rad/s | **passes, and the scale is now measured** |
| magnetometer | (0.35, −1.22, 0.36) | all axes swing, \|v\| 0.6…2.8 | **alive, uncalibrated** |
| proximity | 280…546 | 1636…2966 when covered | **passes** — 5 clean cover/uncover cycles |

**The gyroscope's scale is no longer an assumption.** It was taken from the
accelerometer's (Q16 in the sensor's SI unit) with a `TODO` next to it. Turning
the phone through a **quarter circle on a table** integrates the Z channel to
**86.5°** — 3.9% short of 90°, which is about what a hand-slid rotation and a
uniform-timestep integral cost. X and Y stayed under 10° during that turn, so
the axes are separate. The `TODO` is now a measurement.

**The magnetometer responds but cannot be trusted yet.** Its magnitude should be
constant under rotation and it is not (0.6 to 2.8), and the axes swing around
offset centres rather than zero — a large **hard-iron** offset from the phone's
own magnets, on top of a scale that is itself a guess. With both unknown at
once, neither can be solved from this data; a full-sphere fit is needed. As a
compass it needs the calibration userspace normally does.

☠️ **The device index moves between boots.** The Sensor Manager registers each
platform device as its enumeration completes, so the accelerometer has been
`iio:device2` on one boot and `iio:device3` on the next. Anything that hardcodes
an index is wrong by the next reboot — match on `name`, as `sensortest.py` and
the udev rule do.

### Does the sensor stack break audio? No — measured

Worth writing down because it looked like it did. After the proximity work the
phone went completely silent: `paplay`, canberra and feedbackd all reported
success, the sink was `RUNNING`, the mixers and DAPM were right, and the PCM was
open — but nothing came out. `dmesg` showed the WCD9335 unreachable over
SLIMbus (`TX timed out:MC:0x21`).

Comparing boots settled it. The fatal timeout appears **23 s into the boot**,
before any probing and long before the call, and the same kernel produced both
failing and working boots — one of the working ones with `snsregd` running and
publishing at the same second as in the failing ones:

| boot | fatal `MC:0x21` in the first 60 s | snsregd | audio |
|---|---|---|---|
| 20:32 | 2 | running | silent |
| 20:57 | 2 | running | silent |
| 20:59 (cold) | 0 | – | fine |
| 21:01 | 0 | – | fine |
| 21:17 | 0 | **running** | **fine** |

The bring-up is character-for-character identical in a good and a bad boot for
the first 15 s — including `capability exchange timed-out` and `Failed to get
logical address`, which appear in **every** boot and are therefore not the
fault. The two diverge at the first audio use: a bad boot answers with
`TX timed out:MC:0x21` on both `slim-ngd` and `wcd9335-slim` and stays mute for
the rest of the boot; a good one logs a harmless TX underflow. A single late
`MC:0x21` is survivable — a working boot has one at 725 s and audio kept going.

So it is an **intermittent SLIMbus channel-activation failure at the first audio
use**, of the same family as the old framer saga, and unrelated to the sensors.
Prime suspect: the two framer pokes that still run on every boot
(`QDSP6SS 0x101->0x101`, `slim-ngd 0x10b->0x103`) after being measured as
unnecessary. The test is a build without them and a failure-rate count over
several cold boots.

### The oops, and what the safety net did and did not catch

Binding a driver to the proximity device by hand hit a NULL dereference in
`smgr_prox_remove()`: it reads `platform_get_drvdata(pdev)`, which probe never
set — copied from `smgr_accel.c`, which has the same bug and never trips it
because nothing unbinds these devices in normal use. Fixed by setting the
drvdata in probe.

The oops itself was survivable; what followed was not. It left a kernel thread
wedged, so every later `sysfs` write to that driver blocked and the phone stopped
answering over USB. It did **not** need a power cycle in the end: the `systemctl
reboot` issued into the wedge reached "Shutting down", hung there, and the
**shutdown watchdog** (`RebootWatchdogSec=30`) reset the SoC. The phone came back
on its own about twenty minutes later.

So the net held — through the shutdown path. The gap it does have is narrower
than it first looked, but real:

> While the system is *running*, a partial wedge is not caught: systemd stays
> healthy enough to keep petting `/dev/watchdog`, so the runtime watchdog never
> bites. What saves you is attempting a reboot, because a hung shutdown *is*
> covered.

A liveness check on something that actually matters — the network coming up, say
— would close the running-system half. Note also that
`/sys/class/watchdog/watchdog0/bootstatus` reads `0` after such a reset on this
device, so it is not a usable "was this a watchdog reset?" indicator here.
