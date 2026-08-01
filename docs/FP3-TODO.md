# Fairphone 3 (sdm632) mainline port — what is still open

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

This is the **by-branch view** of what is still open: which branch owns which
item, and whether it can be sent anywhere at all. The by-item view, with the
measurements and the reasoning behind each entry, is [`TODO.md`](TODO.md), and
that one is authoritative — this file only says *what is open, on which branch,
and where to read about it*. When the two disagree, `TODO.md` wins.

Until 2026-07-30 this file also shipped at the root of the kernel fork, on
`debug-int/<base>`. It was dropped there: the kernel tree carries kernel source,
and one file maintained in two repositories is one too many to keep honest.

The branch shape it describes:

```
integration/<base>   audio + voice + camera + charger + sensor
                     the pure cherry-pick sum of the upstream-bound categories,
                     so it stays a faithful mirror of what submit/* will carry
      |
      +-> debug-int/<base>   + the debug layer: one commit, the watchdog safety net
                             <- and this is the branch the linux-fp3 package builds
```

The package builds `debug-int/<base>` on purpose. The safety net has to be on the
phone — without the watchdog running from probe, a hang before userspace opens
`/dev/watchdog` leaves a device that has to be switched off by hand, and this one
is often not within arm's reach.

The branch layout itself (`wip/<base>/<category>` → `integration/<base>` →
`submit/<base>/<category>`, and the rule that a change must land on both its wip
branch and its integration) is defined in
[`fp3-pmaports/README.md`](https://github.com/llg179org/fp3-pmaports#the-branch-model);
the base-bump procedure is in
[`docs/rolling-a-new-base.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/rolling-a-new-base.md).

Hashes are deliberately absent except where a commit is being *cited* rather than
*tracked* — a head written into a file is wrong by the next push. Re-derive with:

```sh
git for-each-ref --format='%(refname:short) %(objectname:short=12)' \
  'refs/remotes/fork/wip/7.1.3/*' 'refs/remotes/fork/submit/7.1.3/*' \
  'refs/remotes/fork/integration/7.1.3' 'refs/remotes/fork/debug-int/7.1.3'
# note: there is no wip/<base>/debug - see "The `debug` layer" below
```

---

## Where the work can go at all

Read this before spending effort on "upstreaming" anything. All of it is
AI-assisted, and that closes two of the three doors:

| destination | AI-assisted work | verdict |
|---|---|---|
| postmarketOS (pmaports, wiki) | banned outright | closed |
| msm8953-mainline (GitHub PR) | "we don't merge AI assisted work" — maintainer, [issue #197](https://github.com/msm8953-mainline/linux/issues/197), 2026-07-25 | closed |
| mainline Linux (LKML) | permitted **with disclosure** | the only path |

So `submit/7.1.3/*` targets the subsystem lists, never a pull request here.
Upstream-bound commits carry `Assisted-by: Claude:<model-id>` and the AI must
**never** carry a `Signed-off-by` — only a human can certify the DCO.

## Does it even apply to a maintainer tree?

Measured by cherry-picking each group onto a detached head at the real
destination, not inferred from "the files exist upstream". Re-measured
**2026-07-31** against fresh bases: Mark Brown `sound/for-next` `b8f7ea37085e`,
Sebastian Reichel `linux-power-supply/for-next` `c57cb36f76eb`,
`torvalds/master` `6269cc6f52c6`. **22 of 27 commits applied clean**, 23 after
one one-hunk resolution.

| group | destination | result |
|---|---|---|
| charger driver + binding | `psy/for-next` | 6/6 clean |
| charger dts | mainline | 2/2 clean |
| charger `adc5` channel | mainline | 1/1 clean |
| sensor (`qmi_encdec`) | mainline | 1/1 clean |
| camera dts | mainline | 1/1 clean |
| camera driver | mainline | one `Kconfig` hunk; the second commit is clean once resolved |
| audio driver + binding | `sound/for-next` | 11/12 — only the machine driver conflicts, on item 8 |
| audio dts | mainline | conflicts — `&sound_card` does not exist |
| voice | `sound/for-next` | the file does not exist upstream |

Audio moved from "conflicts on patch 1" to eleven of twelve, because the binding
was written and the series regenerated. The camera's `Kconfig` conflict moved
from the IMX355 entry to `VIDEO_OV9282`; it follows whichever entry sits next to
ours, so the neighbour's name is not worth tracking.

☠️ Counted per commit, aborting each failure before trying the next, so a group's
figure is "how many of these apply" and not "how far the series gets". Where a
failure cascades the two differ sharply: the camera import creates `imx363.c` and
fails on `Kconfig`, after which the delta commit has no file to patch and the
group reads 0/2 when the truth is one trivial hunk.

Redo this after every base bump; it is the only thing that answers the question.

---

## Before anything is submitted

Cross-cutting, mostly `dtbs_check` fallout. Detail:
[`docs/TODO.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/TODO.md).

1. ~~**The camera needs `sony,imx363.yaml` and a MAINTAINERS entry.**~~ **Fixed
   2026-07-31**: binding, MAINTAINERS block and a third cleanup commit after the
   byte-identical import. The node had been **skipped silently** by `dtbs_check`
   for want of a binding; now checked, it adds nothing (44 → 45 errors, the one
   addition being item 5). Details in
   [`TODO.md`](TODO.md#open-before-anything-is-submitted).
2. ~~**Six undocumented codec properties** on the audio `slim217,1a0` node.~~
   **Fixed 2026-07-30**: the WCD9335 binding carries them, and the button
   thresholds were renamed to the family's
   `qcom,mbhc-buttons-vthreshold-microvolt`.
3. ~~**`divclk1` and `wcd-vout-1p8` must move out from under `soc@0`**~~ —
   **fixed 2026-07-30**, both are at the board root.
4. ~~**`wcd-intr-default-state` fails the `qcom,msm8953-pinctrl` schema.**~~
   **Fixed 2026-07-30** by dropping `input-enable`. Details for 2-4 in
   [`TODO.md`](TODO.md#open-before-anything-is-submitted).
5. **The battery node's four `qcom,*` properties.** `battery.yaml` has
   `additionalProperties: false` and zero vendor properties; the one JEITA
   precedent (`qcom,jeita-extended-temp-range`) sits on the *charger* node. There
   is a layering argument against the current placement too — see
   [`docs/charger/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/charger/README.md#where-these-properties-belong).
6. **`-ohm` → `-ohms`.** The canonical suffix is plural; `-microamp`/`-percent`
   are already right. Same cycle as 5, same properties.
7. **The camera driver's two-line `Kconfig` conflict** — the neighbouring IMX355
   entry gained a `select V4L2_CCI_I2C`. Trivial, but manual.
8. **The audio prerequisite is named and was posted:** Adam Skladowski,
   *MSM8953/MSM8976 ASoC support* v3, 8 patches, 2024-07-31, state `new`
   ([series 875540](https://patchwork.kernel.org/project/alsa-devel/list/?series=875540),
   cover `<20240731-msm8953-msm8976-asoc-v3-0-163f23c3a28d@gmail.com>`). We need
   1/8, 5/8 and 6/8: `qcom,msm8953-qdsp6-sndcard`, `msm8953_qdsp6_add_ops` and
   `use_ibit_clk` are all out-of-tree today, and so is the `&sound_card` label the
   DTS patch appends to. Declarable with `b4 prep --edit-deps`. Worth asking on
   alsa-devel whether it is still alive before building on it.
9. **Voice is not sendable as-is.** Prior art: Joel Selvaraj's
   `5a63debde2db` (2022-10-02, `sdm670-mainline/linux`) already contains the
   SLIMbus voice routing line for line, including the
   `{ "SLIMBUS_0_RX", NULL, "SLIMBUS_0_RX Voice Mixer" }` edge whose absence we
   booked as our own discovery — and it covers SLIMBUS_0 through 6, where we cover
   0. The `q6voice` driver was never posted to a list, so there is no message-id to
   cite and no upstream file to patch. The realistic move is to offer the
   SLIMBUS_0 work to that series' authors, not to send ours.
10. **Cover-letter disclosure** per `Documentation/process/generated-content.rst`:
    which tools, which prompts, which parts, and how it was tested.
11. ~~**Two more invented WCD9335 property names, with an inverted default.**~~
    **Fixed 2026-07-31**, and not by renaming them: the codec was moved onto the
    shared `wcd-mbhc-v2`, so it now calls the family's own
    `wcd_dt_parse_mbhc_data()` and the invented properties were deleted from the
    driver, the binding and the board file. Details in
    [`TODO.md`](TODO.md#open-before-anything-is-submitted).
12. ~~**The rebase table's two audio rows are stale.**~~ **Re-measured
    2026-07-31** against fresh bases, all nine rows, against the regenerated
    thirteen-patch series: audio is now 11/12. Table above.
13. ~~**`submit/7.1.3/audio` still carries the private MBHC implementation.**~~
    **Regenerated 2026-07-31** as thirteen single-domain patches, the shared-MBHC
    change split three ways; `aw8898` is excluded because it is not in Linus'
    tree. Item 12 is now the only thing standing between this series and a
    rebase measurement. Details in
    [`TODO.md`](TODO.md#open-before-anything-is-submitted).

---

## `wip/7.1.3/charger` — PMI632 SMB5

Fast charge, hardware JEITA, battery ID + thermistor, cooling device. All nine
commits of `submit/7.1.3/charger` apply clean, though to three different trees —
six to `psy/for-next`, two dts and one `adc5` channel to mainline. Gaps, in
[`docs/charger/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/charger/README.md#known-gaps):

11. **No high-voltage negotiation on the input side** — the port settles near
    1.9 A, just under the programmed 2 A. This is the next real feature here, and
    a piece of work in its own right.
12. **2 A has never been seen flowing.** Needs a wall charger, a low state of
    charge and a USB meter. Physical.
13. **The mismatch path has never run on hardware.** A DTB-only cycle with a
    deliberately wrong `qcom,batt-id-ohm = <50000>`; expected: the refusal message
    plus `0x1061` staying at `0x14`. Two DTB deploys, no kernel build, no flash.
14. **After a mismatch the previous boot's JEITA thresholds stay in the
    comparators**, not the PMIC defaults — a warm reboot does not reset the PMIC.
    The current limit is safe; the temperature limits are stale. Needs a
    characterised safe default.
15. **The DT can only describe one of the two packs** the FP3 ships (this one is
    Fuji). The ID is checked, so a wrong pack cannot be charged on the wrong
    limits — but it falls back to ~1 A, and the OCV curve is still read from the
    battery node even when the ID did not match. What is missing is the
    *selection*: a multi-`monitored-battery` binding mainline does not have.
16. **Half of the float-voltage story is untouched** — the `*_SL_FCV` bits are at
    their PMIC default; the scaling register is undocumented in every source
    available for this generation.
17. **Hardware JEITA gives one threshold per side; the downstream profile has five
    bands.** The 40–45 °C / 1500 mA step cannot be expressed. The full table would
    mean software JEITA — driven by the approximate temperature curve, which is
    the reason not to.
18. **The trip temperatures are a choice, not a measurement.** Nobody has charged
    this phone hard enough to find out which one it reaches.
19. **No step charging and no `auto-recharge-vbat-mv`** (downstream sets both,
    4300 mV). Worth adopting after the above.

## `wip/7.1.3/audio` — WCD9335 on SLIMbus

Playback, microphone, MBHC and the call path all work on the device. Blocked
upstream on item 8. How it works is in
[`docs/audio/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/audio/README.md),
how it was arrived at in
[`docs/audio/bringup/`](https://github.com/llg179org/fp3-pmaports/tree/main/docs/audio/bringup);
the gaps are here and only here:

20. **The intermittent first-use failure needs a new lead, not another
    workaround.** The QDSP6SS framer-poke suspicion was closed by measurement
    (A/B, 8 cold boots each side, no difference) and the pokes were reverted; see
    [`docs/audio/bringup/qdsp6ss-framer-poke.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/audio/bringup/qdsp6ss-framer-poke.md).
21. **The `21`/`22` acoustic selftest checks fail** at −12 dB and at 0 dB while the
    speaker path itself measures clean (999.76 Hz at 31.77 dB). Unexplained, and
    deliberately not filed as environmental.
22. **A stray `Quinary MI2S` backend can attach to the voice front end.**
23. ~~**The jack is treated as 3-pole**~~ — **fixed 2026-07-31.** The codec moved
    onto the shared `wcd-mbhc-v2` with a legacy comparator backend, and a 4-pole
    headset and a 3-pole headphone now report differently
    (`SW_MICROPHONE_INSERT` only for the headset). **No TX gain control is
    exposed for the call path** is still open.

## `wip/7.1.3/camera` — Sony IMX363

Three commits: a verbatim import, our power-path delta, the DT node. The driver
is **Joel Selvaraj's** (`sdm670-mainline/linux` MR !3, commit `5130bc702ea2`,
2024-08-15), archived byte-identically on `vendor/imx363-sdm670`; our measured
delta is +68/−21 on 1514 lines, roughly half comments, functionally four things in
the power path.

24. ~~**Streaming does not work end to end.**~~ **False, corrected 2026-08-01.**
    It streams: 15 240 960-byte frames, exactly 4032 x 3024 x 10 / 8, two
    consecutive frames differing, so it is live sensor data. The old finding was
    an artefact of asking for `RG10`, which this video node does not offer — the
    resulting `-EPIPE` from pipeline validation logs nothing and looks exactly
    like a broken driver. The correct format is **`pRAA`**. What is genuinely
    open is narrower: **nobody has checked the image is correct** (geometry,
    Bayer order, stride) against a known scene, and the link frequencies in the
    DT still disagree with the driver's mode tables. Details in
    [`docs/camera/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/camera/README.md).
25. **Parked: the PMI632 flash LED.** The node exists, but
    `leds-qcom-flash.c` subtype detection is unverified on this hardware and
    risks a probe failure until it is. Kept out of the tree for now.
33. **The focus actuator is at 0x0c and is not an LC898217.** ☠️ **This
    corrects the same item written earlier the same day.** `lc898217.c` plus its
    binding and MAINTAINERS entry landed 2026-08-01 and are worth keeping — the
    register map was read out of the board's vendor library
    `libactuator_lc898217xc.so` and validated against `libactuator_dw9714.so`,
    whose answer mainline's `dw9714.c` already states — but **the board DT node
    was removed again** (`wip/7.1.3/camera`), because it described hardware this
    phone does not have. Measured: with the actuator rail forced on and the
    sensor resumed so the camera IO rail is up, a **forced** scan of the CCI bus
    answers `0x0c 0x1a 0x50` and **nothing at 0x72**. ☠️ The scan must be forced
    (`I2C_SLAVE_FORCE`) or it silently skips every driver-claimed address —
    exactly the ones under investigation. Every `LC898*` in the vendor tree is at
    0x72 and every other family at 0x0c. ☠️ **Resolved later the same day, and
    the resolution is that both parts are real:** the vendor's
    `/vendor/etc/camera/camera_config.xml` pairs module `imx363` with
    `lc898217xc` and both second-source modules (`imx363_2nd`, `imx363pv_2nd`)
    with **`ak7374`** — Fairphone ships this phone two ways, exactly as it does
    with the battery pack. This phone has a second-source module, so `ak7374` it
    is; `dw9800` was never a candidate here, it belongs to a different module in
    the same file. Support is a chipdef plus a compatible in mainline's existing
    `ak7375.c` (register 0x00, 10 bits, shift 6, no standby), with the board node
    restored to point at it. The decode was re-validated against **two** known
    answers, `dw9714` and `ak7345`, after a four-byte base-offset error made
    every field decode to a plausible wrong value — see item 33b. ☠️ The
    downstream `value = 1023 - position` inversion excludes exactly `ak7374` and
    `dw9800`, so the polarity argument built on it does not apply to this board.
    Two side findings, both of
    which had looked like driver bugs: **the CCI bus does not work until the
    sensor's IO rail is up** (timeout `-110` versus `-ENXIO` tells "bus dead"
    from "nobody home"), and **a failed runtime-PM resume latches** into
    `runtime_status: error`, after which every resume returns `-EINVAL` and the
    subdev open fails several steps away from the real error — unbind/rebind
    clears it. Detail in
    [`docs/camera/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/camera/README.md#the-focus-actuator).
33a. **`lens-focus` is how a lens subdev joins the graph**, and it worked:
    `v4l2_async_register_subdev()` alone leaves the subdev unclaimed, with no
    devnode and no media entity, so the driver is bound and invisible at once.
    `imx363` registers via `v4l2_async_register_subdev_sensor()`, which parses
    `lens-focus`; adding the reference put the lens in the graph immediately. The
    `lens-focus: true` line stays in `sony,imx363.yaml` for whatever part turns
    out to be fitted.
33b. **A vendor-blob decode is only worth what its known-answer control is
    worth.** The actuator parameter structure starts at `.data + 0x04`, not at
    `.data`, and with that four-byte error every field still decoded to a
    plausible value — an I²C address, a bit width, a register number, none of
    them right. Nothing in the output looked wrong. What caught it was running
    the identical decode against parts mainline already documents: `dw9714`
    (0x0c, 10 bits, no register address, shift 4) and `ak7345` (0x0c, 9 bits,
    register 0x00, shift 7). Seven fields across two parts now agree, and the
    AK7374's own numbers satisfy the family invariant that position width plus
    shift fills a 16-bit word (9+7, 10+6, 12+4). **Do not accept a struct decode
    without at least one control whose answer is known independently**, and
    prefer two — the first control is what made the earlier LC898217 decode
    trustworthy, and it is what made this one repairable.
33c. **Still unmeasured: whether writing those registers moves the lens.** The
    part is identified and the driver written, but no capture has been scored at
    two focus positions yet. `userspace-camera/focus-sweep.py` is the instrument;
    a flat curve is an answer, not a broken run.

## `wip/7.1.3/sensor` — SMGR over QMI/QRTR

Accelerometer, gyroscope, magnetometer, proximity, ambient light. Only one commit
has been distilled — `soc: qcom: qmi: read QMI_DATA_LEN at its declared width` —
and that is the whole submittable set, not a backlog. Re-verified **2026-08-01**
against today's `torvalds/linux`: the `Fixes:` hash resolves with a matching
subject, the patch applies clean to the current `qmi_encdec.c`, and
`checkpatch --strict` is silent. ☠️ Everything else is **unsendable rather than
undone**: `smgr_accel.c`, `drivers/iio/common/qcom_smgr/` and `net/qrtr`'s bus
conversion all 404 against mainline, so ten of our eleven remaining commits and
both QRTR prerequisites patch files that do not exist upstream — **including the
mount-matrix fix of item 27, which otherwise looks like an ideal standalone
submission.** The reasoning, and the cheap check that settles it before any
distillation work, are in
[`docs/sensors/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/sensors/README.md#why-the-submit-series-is-one-patch).
Gaps, in
[`docs/sensors/README.md`](https://github.com/llg179org/fp3-pmaports/blob/main/docs/sensors/README.md#known-gaps):

26. ~~**The magnetometer is uncalibrated and its scale unverified**~~ — **both
    measured 2026-08-01.** Hard-iron `−0.63494 −0.69576 +0.71721` Gauss;
    soft-iron negligible (semi-axes within ±2%); and the scale is **correct** —
    the sphere's radius is 0.4865 G = 48.65 µT against an expected 48–50 µT for
    this latitude. The gap note said the two cannot be solved from each other,
    which is true one at a time and false for a full sphere, whose radius *is*
    the field strength. What is left is narrower: the driver exposes no
    `in_magn_*_calibbias`, so nothing can carry the offset, and it must not be
    hardcoded — it is per-unit and drifts.
27. ~~**The mount matrix is probably wrong**~~ — **fixed 2026-08-01**, and it was
    not merely wrong: the msm8996 value has **determinant −1**, so it was a
    reflection rather than a rotation and could not have suited any device. The
    new value is every one of those signs flipped. Measured from three
    orientations, and confirmed independently by the phone's own factory
    calibration, where the permutation between `/persist/sensors/accel_[xyz]`
    and registry keys 0–2 *is* this matrix.
28. ~~**Registry groups 20, 2691 and 3050 are zero-filled**, not real.~~
    **Corrected 2026-08-01 for group 20:** it is zero in this phone's own
    factory `sns.reg` as well, so `snsregd` serving zeros is serving the truth,
    not a stand-in. The factory calibrates the accelerometer, the proximity
    sensor and the ambient light sensor, and nothing else. **2691 and 3050 are
    still unmapped** and remain open.
28a. **The gyroscope and the magnetometer have no mount matrix at all** — only
    the accelerometer ever had one, and the magnetometer's does not follow from
    it, being a separate part.
29. **`snsregd.py` is still a Python stand-in** for upstream's C `sns-reg`; it
    should become an aport. (Userspace, tracked here because the driver depends on
    it.)

## `wip/7.1.3/voice` — q6voice / CS-Voice over SLIMbus

One commit. Working on the device; see item 9 for why it is not sendable.

## The `debug` layer — bring-up aids, never upstream-bound

One commit: the watchdog started at probe. Nothing here gets a `submit/` series,
ever, and it stays off `integration/7.1.3`.

**It is the only category with no `wip` branch.** `wip/7.1.3/debug` was retired on
2026-07-30 (kept as the tag `archive/wip-7.1.3-debug-final`) once the layer became
reproducible without it: every other category needs a `wip` branch because it
carries evolving work against a moving base, while this one is a fixed, additive
change that replays anywhere. It now lives as that one commit on
`debug-int/<base>` plus the payloads in `fp3-pmaports/docs/debug/files/`, and
those payloads are half of the storage rather than a copy — refresh them in the
same commit that changes the layer.

The watchdog commit is the one place in the tree where mixing `.dts` with `.c` is
allowed, and it uses that licence: it adds an undocumented `qcom,start-at-probe`
property. That would be fatal in a `submit/` series and is fine here; the reason
is written into the commit message, along with why there is deliberately no
`ramoops` node (tried at `0x8ee00000` and at `0xd0000000`; nothing survives a
reset on this device, so it would cost 2 MB and imply a post-mortem capability
that does not exist).

### Replaying the debug layer onto any branch

The safety net is worth having on any branch you are about to boot — an
experimental offshoot is exactly where an early hang is likely, and exactly where
nobody wants to walk to the phone. One command, from the target branch:

```sh
git am ../fp3-pmaports/docs/debug/files/0001-watchdog-*.patch
```

The step-by-step — preconditions with defined failure actions, a by-hand
reconstruction for when the patch stops applying, and verification in three
places — is `fp3-pmaports/docs/debug/create_debug.md`.

It applies clean everywhere because the board-side change is a **separate**
`sdm632-fairphone-fp3-debug.dtsi` plus one `#include` among the other includes.
That is not cosmetic: every other category appends its nodes to the *end* of
`sdm632-fairphone-fp3.dts`, so the earlier form — which appended there too —
collided with whichever of them was present. Measured 2026-07-30: the appended
form conflicted on `wip/7.1.3/audio` and on `integration/7.1.3` and applied clean
on `camera` and `charger`; the split form applies clean on all five wip branches
and on integration. Verified again by rebuilding the layer from the stored
payloads onto a fresh branch off `integration/7.1.3`: same tree object as
`debug-int/7.1.3`, same blob for every file it touches.

---

## Not kernel work, kept here so it is not lost

30. **The notification LED blinks forever after a missed call** (`rgb:status`, not
    the flash). The real bug is a missing `EndFeedback` call in whatever raised it
    — phosh or the call app; secondarily, a `fairphone,fp3.json` feedbackd theme
    is missing.
31. **Untested: the interconnect path for the SCM/crypto node.** Non-blocking;
    kept in case the ADSP-boot timing question reopens.
32. **The package now pins `debug-int/7.1.3`, not `integration/7.1.3`.** Two
    rewrites have moved out from under the old pin — the camera provenance and
    then the debug split — so `_commit` is reached only through
    `archive/integration-7.1.3-pre-camera-provenance` and
    `archive/integration-7.1.3-pre-debug-split`. Anything built from that pin has
    **no watchdog**, which is the practical reason to bump rather than a
    bookkeeping one.
    ☠️ GitHub serves a source tarball only while the commit is reachable from some
    ref, which is why those archive tags exist at all — check before trusting a
    pin:

    ```sh
    curl -sI -o /dev/null -w '%{http_code}\n' \
      "https://github.com/llg179org/linux/archive/<_commit>.tar.gz"   # 302, not 404
    ```

## The `vendor/*` and `archive/*` namespaces

Neither is a base and neither is ever pruned when a base is rolled.

- `vendor/imx363-sdm670`, `vendor/q6voice-sdm670` — **parentless snapshots** of
  third-party imports, made with `git commit-tree` and no `-p`, so the tree is
  byte-identical to the source without dragging in 71,541 unrelated commits.
  `git diff <snapshot> <source>` is empty, which is the check.
- `vendor/asoc-msm8953-base`, `vendor/q6voice-base` — tags, not branches: those
  commits are already in `7.1.3/main`, so they need a name, not a copy.
- `archive/*` — rewritten history kept reachable, so an old pin still resolves
  and its tarball still downloads.
