# Documentation

The [top-level README](../README.md) says what this repository is, how the
branches are named and where the work may go. Everything longer than that lives
here.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who reviewed it. The same applies to almost
> everything it indexes; each page repeats the note so it survives being read
> on its own.

## How the device works

| page | what it answers |
|---|---|
| [`audio/`](audio/README.md) | how sound gets in and out: the hardware chain, the layers, the two paths (media and call), and the rules the arrangement obeys |
| [`device_tree/`](device_tree/README.md) | which `.dts`/`.dtsi` files the board is built from, what our one commit adds and where every value came from — with the trees themselves checked in, ours and both downstream references |
| [`kernel/`](kernel/README.md) | the thirteen C files we change: whose driver each one is, what we added on top and what genuinely did not exist before |
| [`sensors/`](sensors/README.md) | the proximity / ambient-light / IMU bring-up, which runs through the SSC and is not solved yet |

## What is still open

[`TODO.md`](TODO.md) — the known-broken and deliberately-unfinished list: the
notification LED that blinks forever after a missed call, the parked camera
flash node, and pointers to the items written up on the pages below.

## How to work on it

| page | what it answers |
|---|---|
| [`deploy/`](deploy/README.md) | building the package and getting it onto the phone, keeping the last working kernel bootable — including the device-tree-only shortcut |
| [`rolling-a-new-base.md`](rolling-a-new-base.md) | moving the whole port to a new `msm8953-mainline` release: the checkouts, the rebases, the one place the version is edited |
| [`kernel/config.md`](kernel/config.md) | what [`config-fp3.aarch64`](../linux-fp3/config-fp3.aarch64) turns on beyond the postmarketOS base, and the symbol renames that silently drop a driver across a base bump |

Two more places worth knowing about: [`../tests/`](../tests/) holds
`fp3-selftest`, the functional regression battery, and
[`../userspace-audio/`](../userspace-audio/) the UCM profiles, PulseAudio
drop-ins and call-audio helpers that the audio page describes.
