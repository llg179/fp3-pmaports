# fp3-pmaports

The postmarketOS package that builds the Fairphone 3 mainline kernel — mainline
`msm8953` with the WCD9335 SLIMbus audio work, the Sony IMX363 rear camera, the
PMI632 charger and the sensors the SSC keeps behind a QMI service.

Without this, the [kernel branches](https://github.com/llg179/linux) are only
source: nothing records which config was used, which symbols had to be turned
on by hand, or how the thing was actually built.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who reviewed every change and made the
> measurements behind the numbers. Kernel commits carry `Co-authored-by:
> Claude`; anything prepared for the LKML carries `Assisted-by:` instead and
> never a `Signed-off-by` from the assistant, since only a human can certify
> the DCO.

## The goal, and why the names have no version in them

[`llg179/linux`](https://github.com/llg179/linux) is a **rolling forward-port**
of Fairphone 3 support onto the
latest [`msm8953-mainline`](https://github.com/msm8953-mainline/linux) release
(`X.Y.Z/main`), kept moving from one kernel base to the next until the work
lands upstream on the LKML.

Because the base keeps changing, the kernel version is deliberately confined to
the **two places where it is genuinely the identity of something**:

* the base segment of a base-relative branch — `wip/7.1.3/audio`,
  `submit/7.1.3/audio`, `integration/7.1.3` — a patch series *is* "the series
  against 7.1.3", so the version belongs in the name, and the old ones are
  pruned once a base is retired; and
* the package `pkgver`.

Everything else — the package name `linux-fp3`, its flavor `fp3`, the config
`config-fp3.aarch64`, the test suite, the boot entries — carries **no version**.
Bumping `pkgver` is the single edit that moves the whole thing to a new kernel.

## The branch model

For a base `X.Y.Z` there are four layers, each base-relative:

| branch | layer | contents |
|---|---|---|
| `X.Y.Z/main` | base | the upstream `msm8953-mainline` release; not ours to rename, we just follow the newest |
| `wip/X.Y.Z/<category>` | work | the category's commits rebased onto the base, **plus the bump fixes** — messy, evolving history |
| `integration/X.Y.Z` | build | the cherry-pick union of the **upstream-bound** `wip/X.Y.Z/*` branches — audio, voice, camera, charger, sensor. Versioned so the last working `integration/<prev>` survives while the new base is still being fixed |
| `debug-int/X.Y.Z` | build | `integration/X.Y.Z` plus the `debug` layer; **this is what the package builds** |
| `submit/X.Y.Z/<category>` | upstream | the **minimal** series distilled from `wip/X.Y.Z/<category>` — created only once everything works, ready to post to the LKML |

Replaying the debug layer onto any other branch — an experimental offshoot is
exactly where an early hang is likely — is one command from the target branch:

```sh
git am ../fp3-pmaports/docs/debug/files/0001-watchdog-qcom-optionally-start-the-watchdog-at-probe.patch
```

The step-by-step, including what to do when that patch stops applying, is
[`docs/debug/create_debug.md`](docs/debug/create_debug.md).

It applies clean because the debug board nodes live in their own
`sdm632-fairphone-fp3-debug.dtsi`, pulled in by a single `#include` among the
other includes. Every category appends to the *end* of
`sdm632-fairphone-fp3.dts`, so a debug block that appended there too collided
with whichever of them was present — measured 2026-07-30, the old form conflicted
on `audio` and on `integration` and applied clean on `camera` and `charger`,
while the split form applies clean on all five wip branches and on integration.

The last two are split for one reason each. `integration` stays free of the debug
layer so that it remains a faithful preview of what the `submit` branches carry —
it is the branch you compare against when you want to know whether the port and
the proposed series still say the same thing. `debug-int` is what gets flashed,
because the safety net has to be on the phone: without the watchdog running from
probe, a hang before userspace opens `/dev/watchdog` leaves a device that only a
physical button press recovers, and this one is usually not at arm's reach.

A category is one subsystem's worth of work — the unit a `submit` series is cut
from, where there is going to be one. There are six:

| category | what it adds | `submit` series |
|---|---|---|
| `audio` | WCD9335 over SLIMbus: playback, the four digital mics, headset (MBHC) jack detection | yes |
| `voice` | call audio, by routing the voice mixers over SLIMbus | yes |
| `camera` | the Sony IMX363 rear sensor | yes |
| `charger` | the PMI632 charger via `qcom_smbx`: the battery thermistor, hardware JEITA, thermal mitigation and a device-tree-driven charge current ([`docs/charger/`](docs/charger/README.md)) | yes |
| `sensor` | proximity, ambient light and the IMU, over the SSC's QMI Sensor Manager | **one patch of twelve** — the imported base cannot carry a DCO and its author's own series is in flight ([why](docs/sensors/README.md#why-the-submit-series-is-one-patch)) |
| `debug` | the bring-up safety net: the SoC watchdog started at probe, so a hung boot resets instead of waiting for hands ([`docs/debug/`](docs/debug/README.md)), and `FP3-TODO.md`, the kernel-side index of what is still open | never — deliberately not upstream material. **The only category with no `wip` branch:** it lives directly on `debug-int/<base>`, and is reproducible from [`docs/debug/files/`](docs/debug/files/) without any branch at all |

Reading it: "what runs on the phone" is always `debug-int/<pkgver>`; "what the
series will look like" is always `integration/<pkgver>`; "what goes to the
kernel" is always `submit/<pkgver>/<category>`; the base version is the only
thing that changes.

A `wip/<base>/<category>-debug` branch is something else again: an ephemeral
offshoot for one investigation, not a category, and not cherry-picked anywhere.
It is deleted when the investigation ends — and if any of its commits are worth
keeping reachable, tagged first, the way `archive/cx-turbo-disproven` keeps the
disproven CX-turbo experiment after `wip/7.1.3/audio-debug` was removed on
2026-07-30.

Two more namespaces exist on the kernel fork and neither is a base for anything:

* **`vendor/*`** — archival snapshots of third-party code this port imports or
  builds on, so that a provenance citation in a commit message still resolves
  when the original repository is gone. `vendor/imx363-sdm670` is the IMX363
  driver as Joel Selvaraj wrote it; `vendor/q6voice-sdm670` is the further
  developed q6voice stack from the same tree. Each is a **parentless snapshot**
  whose tree is byte-identical to the source commit's, because mirroring the real
  branch would have dragged 71 541 unrelated commits into this fork. The tags
  `vendor/asoc-msm8953-base` and `vendor/q6voice-base` do the same job for
  dependencies that already sit inside `7.1.3/main` — they name them, nothing
  more.
* **`archive/*`** tags — points in this port's own history kept reachable after a
  rewrite, either because a claim they contain was disproven or because something
  still points at them. `archive/integration-7.1.3-pre-camera-provenance` and
  `archive/integration-7.1.3-pre-debug-split` are the latter: each is a tip that
  an older `_commit` is only reachable through, and without them the package's
  pinned tarball would have become un-fetchable when `integration/7.1.3` was
  rewritten.

☠️ **Rewriting a published branch can break the package, silently and later.**
`linux-fp3/APKBUILD` fetches a GitHub tarball of an exact `_commit`, and GitHub
serves that only while the commit is reachable from *some* ref. Before any
force-push that rewrites `integration/<base>`, tag the old tip — then check the
pin still resolves:

```sh
curl -sI -o /dev/null -w '%{http_code}\n' \
  "https://github.com/llg179/linux/archive/<_commit>.tar.gz"     # 302, not 404
```

**The category rule (version-free):** a change lands on `wip/X.Y.Z/<category>`
**and** is cherry-picked onto `integration/X.Y.Z`. The two never diverge;
integration is only ever the sum of the `wip` branches that feed it. `debug` is
the exception in both halves: it has no `wip` branch, so a debug change is
committed straight onto `debug-int/X.Y.Z`, and the stored payloads under
[`docs/debug/files/`](docs/debug/files/) are refreshed in the same breath —
those, not a branch, are what make the layer reproducible. `submit/X.Y.Z/<category>` is regenerated from `wip` when the base is
done; it is not edited by hand.

☠️ *"Not edited by hand"* is the part that slips. Both the charger and the audio
series picked up `checkpatch --strict` fixes directly on their `submit` branch,
which left `wip` behind — so regenerating, which is how a submit branch is
*supposed* to be produced, would have silently dropped them. Both were carried
back on 2026-07-30, and the check is one command: `git diff wip/<base>/<cat>
submit/<base>/<cat>` must be empty.

The two-base worked example, how `wip` and `submit` diverge on a messy bump, and
why `integration` is versioned at all are in
[`docs/rolling-a-new-base.md`](docs/rolling-a-new-base.md#the-model-this-procedure-moves)
— that page is this model in motion.

## Rolling to a new kernel base

When `msm8953-mainline` cuts a new release, the whole procedure — setting the
three checkouts up, rebasing each `wip` branch, rebuilding `integration`, the
one place the version is edited, and pruning the old base — is in
**[`docs/rolling-a-new-base.md`](docs/rolling-a-new-base.md)**.

Two traps it opens with, because both cost an afternoon the first time: the base
branch names contain a slash, so `git fetch origin '7.2.0/main'` leaves you with
`FETCH_HEAD` and no `origin/7.2.0/main` ref; and a shallow clone answers
`git log -- <path>` with one commit for every path, which looks like an answer.


## Building and deploying

`pmbootstrap` builds the package, the `.apk` is copied to the phone and
installed, and the previous kernel stays bootable as a second `extlinux` entry
while the new one is tried — including the device-tree-only shortcut that needs
no kernel flash. All of it, with the fallback-entry setup and the recovery
paths, is in **[`docs/deploy/README.md`](docs/deploy/README.md)**.


## The config

`linux-fp3/config-fp3.aarch64`, what has to be on for this device, and the
symbol renames that silently drop a driver across a base bump:
**[`docs/kernel/config.md`](docs/kernel/config.md)**.

## AI-assisted development

### What was written here, and what it builds on

Almost nothing here is new code in isolation: every module is somebody else's
driver with a Fairphone 3 shaped hole filled in.
**[`docs/kernel/README.md`](docs/kernel/README.md)** says per file whose work it
is, what we added and what that was derived from, and what genuinely did not
exist before — the same treatment
[`docs/device_tree/README.md`](docs/device_tree/README.md) gives the `.dts`.

In short. Audio and charger are eleven files of other people's drivers with holes
filled in: the WCD9335 codec and the `apq8016_sbc` machine driver (Srinivas
Kandagatla), the Q6 voice DAI (Stephan Gerhold, Vincent Knecht, Otto Pflüger —
not in Linus' tree) and `q6afe` (Kandagatla), the SMB2 charger driver and its
binding (Casey Connolly), and the PMIC ADC5 driver (Siddartha Mohanadoss).
**The camera and the sensors are imports**, and that is the more delicate case:
the IMX363 driver is **Joel Selvaraj's**, reverse-engineered on
`sdm670-mainline/linux` against a Pixel-3a-family sensor, and the sensor stack is
Yassine Oudjana's QRTR-bus and Sensor Manager series — both **carried verbatim**
so the authorship survives. On top of the sensor import are three new drivers and
four fixes; on top of the camera import, four power-path changes (+68 / −21 on a
1514-line file) and nothing else. Both splits are spelled out per file —
[`docs/kernel/README.md`](docs/kernel/README.md#provenance) and
[`docs/sensors/README.md`](docs/sensors/README.md#provenance).

☠️ This page and the kernel page both **described the camera driver as
substantially ours until 2026-07-30**, and so did the commit message on
`submit/7.1.3/camera`. All three are corrected: the import is now
[its own commit](https://github.com/llg179/linux/commit/cda174905a83) authored by
Joel Selvaraj, carrying the original `Signed-off-by` chain, with our change on top
of it. It is worth knowing *why* it stood so long — the wrong claim was
self-consistent and nobody had tried to fetch the original file. The check that
broke it is cheap and should be routine: **get the upstream file and diff it.**
**Everything this port adds on top was developed with the assistance of
[Claude Code](https://www.anthropic.com/claude-code)**, Anthropic's generative-AI
coding agent.

### How the assistance is recorded

Every commit on this repository and on the `wip`/`integration` branches carries
a `Co-authored-by: Claude` trailer. The `submit` branches, which are meant for
the kernel, instead carry the kernel's `Assisted-by: Claude:<model>` trailer and
**no** `Signed-off-by` from the AI — a DCO sign-off is a human certification and
an AI cannot give one.

### Where it may and may not go

Because of the AI assistance, **this code must not be submitted or upstreamed to
postmarketOS.** postmarketOS's
[AI policy](https://docs.postmarketos.org/policies-and-processes/development/ai-policy.html)
forbids the use of generative AI tools in the project — *"We forbid the use of
generative AI tools in postmarketOS"* — and specifically prohibits "submitting
contributions fully or in part created by generative AI tools". This repository
and the linked kernel branches are a personal fork for running mainline on the
Fairphone 3; they are deliberately kept out of the postmarketOS contribution
channels for this reason. The LKML, whose
[coding-assistants policy](https://www.kernel.org/doc/html/latest/process/coding-assistants.html)
allows disclosed AI assistance, is the one open upstream — which is what the
`submit/<base>/<category>` branches are for.

## How audio works on this device

The hardware, the layers, the two paths a sound can take, and the rules the
arrangement obeys — playback, the microphones, headset detection and call audio:
**[`docs/audio/README.md`](docs/audio/README.md)**.


## Related

* <https://github.com/llg179/linux> — the kernel: `wip/<base>/<category>` (work
  plus bump fixes), `integration/<base>` (the upstream-bound sum),
  `debug-int/<base>` (what the device runs), and `submit/<base>/<category>` (the
  minimal series for the LKML). `FP3-TODO.md` on `debug-int/<base>` is the
  kernel-side index of what is still open
* <https://github.com/llg179/Claude-skills-Fairphone3> — the method: bring-up
  notes, ground-truth techniques, the guard-railed test loop, and the
  `msm8953-mainline-pr` skill for preparing a `submit` series
* [`docs/`](docs/README.md) — everything longer than this page: how the audio
  stack works, the device trees (ours plus both downstream references), the
  kernel changes file by file, the sensor bring-up, and the build / deploy /
  base-rolling runbooks
* [`docs/sensors/`](docs/sensors/) — the sensor (proximity / ambient light / IMU)
  bring-up: how the SSC hides them behind a QMI service, what was measured, the
  upstream Sensor Manager work this builds on and what we add — **working**, with
  the magnetometer's calibration still open
* [`docs/charger/`](docs/charger/) — charging: the JEITA and thermal guards that
  had to exist before the current could be raised, why the thresholds are raw
  ADC codes rather than degrees, and why the ceiling is the USB port

## Device tree

The board `.dtb` comes from five files; we touch **two**
(`sdm632-fairphone-fp3.dts`, `pmi632.dtsi`, +423/−4 lines, most of it the
integrated DT commit
[`ca289613`](https://github.com/llg179/linux/commit/6749bae07da1)),
and 17 of the 20 upstream commits in the board file are in Linus' tree — the
SoC-level `msm8953.dtsi` much less so, which constrains what a
`submit/<base>/*` series may assume.

The trees themselves are checked in, with the full write-up — provenance,
genealogy, what each added node was derived from, and a node-by-node comparison
against Fairphone's published sources:
**[`docs/device_tree/README.md`](docs/device_tree/README.md)**.

## License

GPL-2.0-only, matching the kernel it builds.
