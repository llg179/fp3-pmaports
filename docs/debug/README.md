# Debug: the safety net, and where the method lives

The `debug` category is the one part of this port that is **not** trying to make
the phone do something. It exists so that a bring-up session on a phone sitting
on a desk in another room does not end with a device that needs a thumb on a
button.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who ran the experiments it describes.

## The how-to is not here

**This page is status. The method is in the skills.** How to form a hardware
hypothesis, which instrument answers which question, how to run one change at a
time on a device you cannot afford to brick, how to recover a slot that will not
boot — all of that lives in
**[llg179/Claude-skills-Fairphone3](https://github.com/llg179/Claude-skills-Fairphone3/tree/main)**,
because it would still be true on a different phone.

| skill | what it covers |
|---|---|
| [`fp3-porting-debug`](https://github.com/llg179/Claude-skills-Fairphone3/tree/main/plugins/fp3/skills/fp3-porting-debug) | the umbrella method: hardware facts, the three OS tracks, how to acquire ground truth, the debugging techniques, and `references/archive/` — the dated investigation logs that answer *was this already tried* |
| [`fp3-kernel-test`](https://github.com/llg179/Claude-skills-Fairphone3/tree/main/plugins/fp3/skills/fp3-kernel-test) | the edit → build → deploy → capture loop for one kernel/DT/firmware change, with the brick-safety gates and the recovery recipes |

The **initial setup is described in the skills' own README**:
[installing the skills](https://github.com/llg179/Claude-skills-Fairphone3/tree/main#installing-the-skills),
[configuration](https://github.com/llg179/Claude-skills-Fairphone3/tree/main#configuration)
(nothing is hardcoded to one machine; `FP3_PW` and `FP3_SERIAL` are yours and
have no default), and
[installing the two OSes](https://github.com/llg179/Claude-skills-Fairphone3/tree/main#installing-the-two-oses)
— Ubuntu Touch on slot `_a` as the working-hardware oracle, postmarketOS on slot
`_b` as the mainline target, swapped with nothing but `fastboot set_active`.
That arrangement, not any single technique, is what makes the debugging in these
docs possible: every claim about mainline can be checked against the same
silicon running vendor code.

Building and deploying *this* package is a different question, and it is in
[`../deploy/README.md`](../deploy/README.md).

## What the category actually contains

One commit,
[`b7a6d32e`](https://github.com/llg179/linux/commit/b7a6d32eb9b954ce45d5630ba653b85d081b4ea8),
on `wip/<base>/debug` and cherry-picked into `integration/<base>` like any other
category. It will **never** get a `submit` series: a watchdog started at probe is
bring-up scaffolding, and the reason it is needed is specific to this
bootloader.

### The watchdog, started at probe

`drivers/watchdog/qcom-wdt.c` is Josh Cartwright's KPSS WDT driver. It only
takes ownership of the hardware when the bootloader already left it running —
Robert Marko's
[`8650d0f9e933`](https://github.com/torvalds/linux/commit/8650d0f9e9334f2e1c209f1e2ac8341f91e30d75)
sets `WDOG_HW_RUNNING` inside `if (qcom_wdt_is_running())` and does nothing
otherwise.

**The FP3's bootloader leaves it disabled.** So on this board the watchdog core
never pings anything and never arms the open deadline, and there is no watchdog
at all between the start of the kernel and the moment userspace opens
`/dev/watchdog`. That window is exactly where an early boot hang falls — and a
hang there leaves a phone that enumerates its USB gadget but never brings up the
link: no ssh, no adb, no fastboot, only a physical button press.

The change adds a `qcom,start-at-probe` property that starts the watchdog when
the bootloader did not, and sets it on the FP3. The register address
(`0xb017000`) and the 30 s bark come from Fairphone's own downstream device
tree. `CONFIG_WATCHDOG_OPEN_TIMEOUT=300` then covers the whole boot.

The property is undocumented, so `dtbs_check` reports it —
`watchdog@b017000 (qcom,kpss-wdt): Unevaluated properties are not allowed
('qcom,start-at-probe' was unexpected)`. That is expected and stays: this
category has no `submit` branch and never will, and the one commit in it mixes
`.dts` with `.c`, which upstream would not take either. It is the only error this
tree adds to `dtbs_check` that nobody intends to fix.

Confirmation that it took effect, at 0.18 s:

```
qcom_wdt b017000.watchdog: started at probe (bootloader left it disabled)
```

**The failure mode is safe, which is the point.** If userspace never takes over,
the SoC resets itself; each reset decrements the A/B retry counter, and after a
few the bootloader falls back to the other slot — which is the oracle. An
unattended hang recovers itself into a working system instead of waiting for
hands.

### What is deliberately absent: ramoops

There is **no `ramoops`/`pstore` node**, and that is a measured decision rather
than an omission. It was tried at `0x8ee00000` and again at `0xd0000000`, and
nothing survives a reset on this device: not a `pmsg` marker across a clean
reboot, not a dmesg record after a real panic (`echo c > /proc/sysrq-trigger`).

pstore registers and the console attaches — `printk: legacy console [ramoops-1]
enabled` — so the writes do happen. The RAM is simply gone by the time the next
kernel reads it, at either address, which points at the boot chain rather than
at the placement. Keeping the node would cost 2 MB and buy nothing.

**Post-mortem for an early hang on this hardware needs the UART, not pstore.**

## Related

* [`../deploy/README.md`](../deploy/README.md) — keeping the last working kernel
  bootable as a second `extlinux` entry, which is the everyday version of the
  same safety instinct
* [`../TODO.md`](../TODO.md) — what is known-broken and deliberately unfinished
* [`../../tests/`](../../tests/) — `fp3-selftest`, the functional regression
  battery that decides whether a new build is better or worse than the last one
