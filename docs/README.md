# Documentation

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The [top-level README](../README.md) says what this repository is, how the
branches are named and where the work may go. Everything longer than that lives
here.

## How the device works

| page | what it answers |
|---|---|
| [`audio/`](audio/README.md) | how sound gets in and out: the hardware chain, the layers, the two paths (media and call), and the rules the arrangement obeys |
| [`device_tree/`](device_tree/README.md) | which `.dts`/`.dtsi` files the board is built from, what our one commit adds and where every value came from — with the trees themselves checked in, ours and both downstream references |
| [`kernel/`](kernel/README.md) | the eleven files we change: whose driver each one is, what we added on top and what genuinely did not exist before — plus what every checker says about the submit series |
| [`camera/`](camera/README.md) | the Sony IMX363 rear sensor and its AK7374 focus motor: what is wired, what streams, how to check it — with the investigation in [`camera/bringup/`](camera/bringup/README.md) |
| [`charger/`](charger/README.md) | the PMI632 charger: what makes it charge, the JEITA and thermal guards that let it charge harder, and why the ceiling is the USB port rather than the battery |
| [`sensors/`](sensors/README.md) | the proximity / ambient-light / IMU bring-up, which runs through the SSC — working, with calibration left |
| [`debug/`](debug/README.md) | the bring-up safety net: the watchdog started at probe, why there is no ramoops, and where the debugging *method* lives — with [`debug/create_debug.md`](debug/create_debug.md), the step-by-step for building that safety net onto any branch from scratch |

## What is still open

Two lists, on different axes, and it is worth knowing which one you want:

* [`TODO.md`](TODO.md) — **the authoritative one**, organised by item: what was
  measured, what is parked and why, plus the settled questions kept as a record
  so nobody re-investigates them. Items already written up on a subsystem page
  are linked rather than repeated.
* [`FP3-TODO.md`](FP3-TODO.md) — the same ground organised **by branch**: which
  branch owns which open item, where the work may be sent at all, which series
  applies to which maintainer tree, and the `vendor/*` / `archive/*` namespaces.
  It flattens back in what `TODO.md` links out, so read it when the question is
  *"what is the state of this branch"* rather than *"what is left to do"*. When
  the two disagree, `TODO.md` wins.

Both live here and nowhere else. Until 2026-07-30 `FP3-TODO.md` also shipped at
the root of the kernel fork, as a byte-identical copy kept in sync by hand; it
was dropped there because the kernel tree should carry kernel source, and one
file in two repositories is one file too many to keep honest.

## How to work on it

| page | what it answers |
|---|---|
| [`deploy/`](deploy/README.md) | building the package and getting it onto the phone, keeping the last working kernel bootable — including the device-tree-only shortcut |
| [`rolling-a-new-base.md`](rolling-a-new-base.md) | moving the whole port to a new `msm8953-mainline` release: the checkouts, the rebases, the one place the version is edited |
| [`moving-to-the-org.md`](moving-to-the-org.md) | transferring the three repositories to another GitHub owner: the order that avoids a broken window, and the five references that are not merely prose |
| [`kernel/config.md`](kernel/config.md) | what [`config-fp3.aarch64`](../linux-fp3/config-fp3.aarch64) turns on beyond the postmarketOS base, and the symbol renames that silently drop a driver across a base bump |

Two more places worth knowing about: [`../tests/`](../tests/) holds
`fp3-selftest`, the functional regression battery, and
[`../userspace-audio/`](../userspace-audio/) the UCM profiles, PulseAudio
drop-ins and call-audio helpers that the audio page describes.

## What is deliberately not here

**Method.** How to form a hardware hypothesis, which instrument answers which
question, the brick-safety rules, the traps that cost a build cycle — those live
in the [FP3 skills](https://github.com/llg179org/Claude-skills-Fairphone3), because
they outlive this device. These pages answer *what is true now*; the skills
answer *how to find out*, and their `references/archive/` keeps the dated
investigation logs that answer *was this already tried*.

The split has a test. **Would it be wrong next month?** Then it is status, and it
belongs here. **Would it still be true on a different phone?** Then it is method,
and it belongs in the skill.
