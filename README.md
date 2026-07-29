# fp3-pmaports

The postmarketOS package that builds the Fairphone 3 mainline kernel — mainline
`msm8953` with the WCD9335 SLIMbus audio work, the Sony IMX363 rear camera and
the PMI632 charger.

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

`llg179/linux` is a **rolling forward-port** of Fairphone 3 support onto the
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

For a base `X.Y.Z` there are three layers, each base-relative:

| branch | layer | contents |
|---|---|---|
| `X.Y.Z/main` | base | the upstream `msm8953-mainline` release; not ours to rename, we just follow the newest |
| `wip/X.Y.Z/<category>` | work | the category's commits rebased onto the base, **plus the bump fixes** — messy, evolving history |
| `integration/X.Y.Z` | build | the cherry-pick union of the `wip/X.Y.Z/*` branches; **this is what the package builds**, and it is versioned so the last working `integration/<prev>` survives while the new base is still being fixed |
| `submit/X.Y.Z/<category>` | upstream | the **minimal** series distilled from `wip/X.Y.Z/<category>` — created only once everything works, ready to post to the LKML |

The four categories are always the same:

| category | what it adds |
|---|---|
| `audio` | WCD9335 over SLIMbus: playback, the four digital mics, headset (MBHC) jack detection |
| `voice` | call audio, by routing the voice mixers over SLIMbus |
| `camera` | the Sony IMX363 rear sensor |
| `charger` | the PMI632 charger, via `qcom_smbx` |

Reading it: "what runs on the phone" is always `integration/<pkgver>`; "what
goes to the kernel" is always `submit/<pkgver>/<category>`; the base version is
the only thing that changes.

**The category rule (version-free):** a change lands on `wip/X.Y.Z/<category>`
**and** is cherry-picked onto `integration/X.Y.Z` — the two never diverge,
integration is only ever the sum of the `wip` branches. `submit/X.Y.Z/<category>`
is regenerated from `wip` when the base is done; it is not edited by hand.

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

Thirteen files, in short: the WCD9335 codec and the `apq8016_sbc` machine driver
(Srinivas Kandagatla), the Q6 voice DAI (Stephan Gerhold, Vincent Knecht, Otto
Pflüger — not in Linus' tree) and `q6afe` (Kandagatla), the SLIMbus NGD
controller (Kandagatla) and the Hexagon PAS driver (Bjorn Andersson), the SMB2
charger driver (Casey Connolly), plus one new sensor driver structured on Intel's
IMX3xx drivers. **Everything this port adds on top was developed with the
assistance of [Claude Code](https://www.anthropic.com/claude-code)**, Anthropic's
generative-AI coding agent.

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
  plus bump fixes), `integration/<base>` (what the device runs), and
  `submit/<base>/<category>` (the minimal series for the LKML)
* <https://github.com/llg179/Claude-skills-Fairphone3> — the method: bring-up
  notes, ground-truth techniques, the guard-railed test loop, and the
  `msm8953-mainline-pr` skill for preparing a `submit` series
* [`docs/`](docs/README.md) — everything longer than this page: how the audio
  stack works, the device trees (ours plus both downstream references), the
  kernel changes file by file, the sensor bring-up, and the build / deploy /
  base-rolling runbooks
* [`docs/sensors/`](docs/sensors/) — the sensor (proximity/ALS/IMU) investigation:
  why nothing works, what was measured, the upstream Sensor Manager work this
  builds on, and what we add on top — **not working yet**, see the page

## Device tree

The board `.dtb` comes from five files; we touch **two**
(`sdm632-fairphone-fp3.dts`, `pmi632.dtsi`, +375/−4 lines in commit
[`ca289613`](https://github.com/llg179/linux/commit/ca2896133002d44daee935ac45a749dab641ef45)),
and 17 of the 20 upstream commits in the board file are in Linus' tree — the
SoC-level `msm8953.dtsi` much less so, which constrains what a
`submit/<base>/*` series may assume.

The trees themselves are checked in, with the full write-up — provenance,
genealogy, what each added node was derived from, and a node-by-node comparison
against Fairphone's published sources:
**[`docs/device_tree/README.md`](docs/device_tree/README.md)**.

## License

GPL-2.0-only, matching the kernel it builds.
