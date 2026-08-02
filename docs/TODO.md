# Open items

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

Things that are known-broken, deliberately unfinished, or parked with enough
context to pick up later. Each entry says what was measured, not what was
guessed. Items that are already written up elsewhere are linked rather than
repeated.

## Open before anything is submitted

A red-team pass over the five `submit/7.1.3/*` branches on 2026-07-30 produced
this list. Everything here is measured — `checkpatch.pl --strict`, and
`dtbs_check` run against the base and against this tree so that only the errors
*we add* are counted (the base fails it 44 times on its own). The per-branch
summary is in [`kernel/README.md`](kernel/README.md#what-the-checkers-say).

~~**The camera series is the one that must not be sent as it stands.**~~ **Fixed
2026-07-30.** Its commit message claimed the driver was derived from `imx258.c`
with register tables read back from the sensor; both were false. The original was
found on GitLab (`sdm670-mainline/linux`, **Joel Selvaraj**, `5130bc702ea2`) and
fetched by SHA, the delta measured at **+68 / −21 on 1514 lines**, and the series
rebuilt as import → our change → device tree, with the original `Signed-off-by`
chain preserved. Details and the checkpatch split in
[`kernel/README.md`](kernel/README.md#camera-imx363c). The DCO chain turned out to
be **intact**, so the camera never had the sensor series' problem.

Then, in rough order of cost:

1. ~~**The camera has no binding and no MAINTAINERS entry.**~~ **Fixed
   2026-07-31.** `sony,imx363.yaml` is written, the MAINTAINERS block claims the
   driver, and the leftovers came out in a **third** commit after the import, so
   the imported commit stays byte-identical to Joel Selvaraj's original — that
   byte-identity is the only thing that makes our delta checkable.

   What the binding is worth is measurable, and the measurement is the point:
   until it existed, `dtbs_check` **skipped the camera node in silence**, because
   a node whose `compatible` nothing documents produces no output at all rather
   than being reported as unchecked. With the binding in place the node is
   checked for the first time and **adds nothing**: the board goes from the
   base's own 44 errors to 45, and the one addition is item 5's battery node,
   already known.

   Two places where copying `sony,imx258.yaml` would have been wrong. Its
   `data-lanes` pins the entries to 1..4; this driver only ever switches on *how
   many* there are, and 176 endpoints in mainline's arm64 device trees start
   their lane list at 0 — nearly every qcom board — so the value constraint would
   reject them for nothing. And imx258 leaves the supplies optional, where this
   driver takes all three with a plain `devm_regulator_bulk_get()`.

   The cleanup removed 97 lines: ninety-odd commented-out register writes, a
   dead 19.2 MHz input-clock path whose config table never existed, and two
   `printk(KERN_INFO)` calls. Two of those comments carried a **finding** rather
   than code — that a set of downstream writes, and a set taken from imx258,
   change nothing in the output — so they are kept as an ordinary comment.
   `checkpatch --strict` on the new patches: **0, 0 and 1**, the one being
   "does MAINTAINERS need updating?" which the next patch answers. The import's
   own 34 complaints are untouched on purpose.

2. ~~**The audio device tree adds six undocumented codec properties**~~ —
   `qcom,micbias{1..4}-microvolt`, `qcom,dmic-sample-rate`,
   `qcom,mbhc-vthreshold` on the `slim217,1a0` node. **Fixed 2026-07-30.** The
   WCD9335 binding now carries all of them, taking wording and limits from
   bindings that already describe the same hardware: the four mic-bias voltages
   verbatim from `qcom,wcd93xx-common.yaml`, the DMIC rate in the plain-uint32
   form the LPASS macro bindings use. The button thresholds were **renamed** on
   the way — `qcom,mbhc-vthreshold` in millivolts was this port's invention, and
   the rest of the family spells it
   `qcom,mbhc-buttons-vthreshold-microvolt` (wcd934x, wcd937x, wcd938x). The
   driver divides by 12500 instead of `(mV * 2) / 25`, so the value programmed
   into the BTNx field is unchanged. All six are disallowed on the SLIMbus
   interface device, where they mean nothing.
3. ~~**`divclk1` and `wcd-vout-1p8` sit under `soc@0`**~~, where `simple-bus`
   requires `ranges`. **Fixed 2026-07-30**: both moved to the root of the board
   file, and the regulator renamed to the `regulator-*` node-name form the file
   uses throughout.
4. ~~**`wcd-intr-default-state` fails the `qcom,msm8953-pinctrl` schema.**~~
   **Fixed 2026-07-30** by dropping `input-enable`, which
   `qcom,tlmm-common.yaml` disallows outright (`input-enable: false`): the TLMM
   input buffer is always on, so on this pin controller the property only ever
   cleared the output-enable bit, and gpio73 is put in input mode anyway when
   the codec's intr1 interrupt is requested. `sdm845-wcd9340.dtsi` describes the
   same codec interrupt without it.

   Items 2-4 were verified together rather than assumed: `dtbs_check` with
   `dtschema` 2026.6 reports **nothing** for the audio nodes now, on
   `wip/7.1.3/audio`, `integration/7.1.3` and `debug-int/7.1.3` alike, and
   sorted `dtc` decompiles of the board DTB before and after differ **only** in
   the two node moves, the dropped property and the renamed one.

   Confirmed on the device too, on `linux-fp3-7.1.3-r27`: the eight `BTN0..7`
   threshold registers read back **byte-identical** across the rename
   (`18 30 48 90 a0 a0 a0 a0`), the moved `divclk1` still claims the PM8953
   MCLK mux (`pin 0 (gpio1): divclk1 ... function func1`) and reaches
   `enable_count = 1` while playback runs over `SLIMBUS_0_RX`, and
   `23-audio-slimbus` passes with a headset plugged in — a 1 kHz tone crossing
   the bus in both directions, **999.76 Hz at 32.97 dB**. The jack still
   detects: `SW_HEADPHONE_INSERT` is active.
5. **The battery node's four `qcom,*` properties cannot stay there.**
   `battery.yaml` has `additionalProperties: false` and **zero** vendor-prefixed
   properties, so there is no precedent to follow; the JEITA precedent that does
   exist (`qcom,jeita-extended-temp-range` in `qcom,pm8941-charger.yaml`) is on
   the *charger* node. There is also a layering argument against the current
   placement, made in [`charger/README.md`](charger/README.md#where-these-properties-belong).
6. **`-ohm` should be `-ohms`.** The canonical unit suffix is plural
   (`qcom,batt-id-ohm`, `qcom,batt-id-pullup-ohm`); `-microamp` and `-percent`,
   which this work also uses, are already right. Worth doing in the same cycle as
   item 5, since it touches the same properties.
7. **Every branch is based on `v7.1.3-r0`.** Sending means rebasing first: ASoC
   onto `sound/for-next`, device trees onto mainline. Trial-rebased on
   2026-07-30, so this is no longer a guess: **11 of the 21 commits apply with no
   conflict**, the charger (9) and sensor (1) series entirely. Full table in
   [`kernel/README.md`](kernel/README.md#does-any-of-it-apply-to-a-maintainer-tree).
8. **The camera driver conflicts on two lines of `Kconfig`** — the neighbouring
   IMX355 entry gained `select V4L2_CCI_I2C` upstream. Trivial, but it has to be
   resolved by hand at rebase time.
9. **The audio series has a real prerequisite and it is stalled.**
   `qcom,msm8953-qdsp6-sndcard`, `msm8953_qdsp6_add_ops` and `use_ibit_clk` are
   not upstream; nor is the `&sound_card` label the audio DT patch attaches to.
   The functionality *was* posted — Adam Skladowski, *MSM8953/MSM8976 ASoC
   support* **v3**, 8 patches, 2024-07-31,
   [series 875540](https://patchwork.kernel.org/project/alsa-devel/list/?series=875540),
   still in state `new`. We need its patches 1/8, 5/8 and 6/8. Because it has a
   cover-letter message-id it can be declared as a dependency the way the kernel
   expects (`b4 prep --edit-deps`, or a `prerequisite-patch-id:` block) rather
   than silently assumed. Worth asking on the list whether it is still alive
   before building on it.
10. **The voice patch duplicates existing prior art and cannot be sent at all.**
    Joel Selvaraj's `5a63debde2db` (2022-10-02, `sdm670-mainline/linux`) already
    contains the same SLIMbus voice routing, line for line, and for SLIMBUS_0
    through SLIMBUS_6 rather than only SLIMBUS_0. Separately, `q6voice` has
    **never been posted to the LKML** — patchwork returns nothing for "q6voice"
    or "Q6 Voice" — so there is no message-id to depend on and the file does not
    exist upstream to patch. Archived as
    [`vendor/q6voice-sdm670`](https://github.com/llg179org/linux/tree/vendor/q6voice-sdm670);
    the realistic move is to offer the SLIMBUS_0 work to that series' authors
    rather than to send anything ourselves.
11. ~~**Two more WCD9335 properties are this port's invention, and their default
    is inverted.**~~ — `qcom,hphl-jack-type-normally-open` and
    `qcom,gnd-jack-type-normally-open`, against the family's
    `-normally-closed` spellings with the opposite default. **Fixed
    2026-07-31**, and the fix removed the question rather than answering it: the
    codec was moved onto the kernel's shared `wcd-mbhc-v2` (with a new legacy
    comparator backend, since this codec has no MBHC ADC), so it now calls the
    family's own `wcd_dt_parse_mbhc_data()`. Both invented names were deleted
    from the driver, from the binding and from the board file, and the board
    relies on the shared default — which is normally-open, the behaviour it
    already had. Verified with a headset on the device: a 4-pole headset, a
    3-pole headphone, the button and both removals all report correctly.
12. ~~**The measured rebase table no longer describes the audio series.**~~
    **Re-measured 2026-07-31**, all nine rows, against fresh bases
    (`broonie/for-next` `b8f7ea37085e`, `psy/for-next` `c57cb36f76eb`,
    `torvalds/master` `6269cc6f52c6`) and the regenerated thirteen-patch series:
    **22 of 27 commits apply with no conflict**, 23 after one one-hunk
    resolution. Audio went from "conflicts on the first patch" to **11/12** — the
    only conflict left is the machine driver, which is item 9's missing
    prerequisite and nothing else. Table in
    [`kernel/README.md`](kernel/README.md#does-any-of-it-apply-to-a-maintainer-tree).

    Two things the re-run corrected about the *method*, not the result. The
    camera's `Kconfig` conflict is no longer the IMX355 entry but `VIDEO_OV9282`:
    it lands on whichever entry sits next to ours, so naming the neighbour dates
    the note for nothing. And counting per commit while aborting each failure
    makes a cascade look like a catastrophe — the camera import fails on
    `Kconfig`, so the delta commit has no `imx363.c` to patch and the group reads
    **0/2** when the honest answer is one hunk, after which the second commit is
    clean.

13. ~~**`submit/7.1.3/audio` no longer matches the branch it is distilled
    from.**~~ **Regenerated 2026-07-31**, from thirteen commits: the binding, the
    machine driver, four wcd9335 fixes, q6afe, the OCP interrupts, the shared-MBHC
    work split three ways (function-table refactor with no functional change →
    legacy backend → the choice as a `wcd_mbhc_init()` parameter), the wcd9335
    conversion, and the device tree alone at the end. Every patch is
    single-domain; `checkpatch --strict` is clean apart from the two entries below
    that were checked and are not defects. The previous tip is the tag
    `archive/submit-7.1.3-audio-pre-mbhc-rework`.

    Three deliberate differences from `wip/7.1.3/audio`, none of them accidental:
    the `aw8898` `.prepare` fix is **excluded** (that driver is carried by
    msm8953-mainline and is not in Linus' tree, so it has no upstream destination
    in this series); the two q6afe commits are squashed into one; and the new
    `DEC*` volume controls are aligned to the open parenthesis while the
    pre-existing `RX*` ones above them are left exactly as mainline has them —
    the earlier series realigned those too, which is drive-by churn on code this
    work does not otherwise touch.

14. **Review feedback on the audio device tree — accepted in principle, not yet
    acted on.** An msm8953-mainline reviewer read the DTS commit
    (`2f76a315`, *wire up WCD9335 audio*) on 2026-08-02 and raised three things.
    Nothing below is implemented: each point needs the pro-and-contra written out
    and confirmed before anything is changed, because two of them touch the
    device tree the phone currently runs on.

    * **"Does it really have 6 digital mics?"** — no, and this one is already
      **measured**. The six-DMIC / AMIC1..6 block was transcribed from
      Fairphone's downstream `msm8953-audio.dtsi`, which is Qualcomm reference
      boilerplate: it also lists ANC headset mics, `Analog Mic6` and
      `SpkrLeft/Right IN`, none of which exist on this phone (the speaker is a
      single mono AW8898 on Quinary MI2S). Swept on the device with a 1 kHz tone
      from its own speaker, `DEC0` capture on `hw:0,1`, Goertzel at 1 kHz, three
      repeats per input:

      | input | 1 kHz bin | verdict |
      |---|---|---|
      | DMIC0 / DMIC1 | ~2200–2700 | live — bottom mic, next to the speaker |
      | DMIC2 / DMIC3 | ~520–630 | live — top mic, 5× quieter because it is further away |
      | DMIC4 / DMIC5 | exact 0 (3/3, every run) | not populated |
      | AMIC2, headset plugged in | 1437 | live — headset mic |
      | AMIC2, empty jack | 0.25 | noise floor only |
      | AMIC1, 3, 4, 5, 6 | exact 0 | not populated |

      The headset gives the positive control the first sweep lacked: AMIC2 moves
      from noise floor to 1437 while every other analog input stays at exact
      digital zero, so those zeroes are absence, not a broken measurement.
      `wcd9335_codec_enable_dmic()` maps DMIC0/1 → `CPE_SS_DMIC0_CTL`, DMIC2/3 →
      `DMIC1_CTL`, DMIC4/5 → `DMIC2_CTL`, i.e. three clk/data pad pairs of two
      channels each — so **two populated DMIC lines, which is exactly the two
      built-in mics the FP3 has**, and the odd slots are the same data line read
      on the other edge.

      Two corrections fall out of this. `"AMIC5", "MIC BIAS3"`, which the commit
      message describes as the handset mic, is **measurably wrong** — AMIC5 is
      dead and the built-in mic is DMIC0, which is also what
      `fp3-mic-select handset` uses. And `qcom,micbias4-microvolt` has nothing
      left to bias.

      ☠️ **Measurement trap for whoever redoes this:** individual captures
      occasionally return exact digital silence (the decimator power-sequencing
      quirk described in
      [`../userspace-audio/README.md`](../userspace-audio/README.md)), and on
      back-to-back mux changes the previous value leaks into the next reading —
      DMIC3 came out identical to DMIC2 in two separate sweeps. Repeat at least
      three times per input and do not conclude from a single run.

    * **"Only one other sdm632/sdm450 device tree defines `audio-routing`, and
      not with a list this long."** The comparison is against the wrong family
      and the answer is defensible: every other msm8953/sdm450 board drives the
      **PM8953 internal codec**, whose routes live in the codec driver, so three
      `AMIC → MIC BIAS` lines suffice. FP3 is the only msm8953 board with an
      external WCD9335 over SLIMbus, where `MCLK` and `MIC BIAS1..4` are
      `SND_SOC_DAPM_SUPPLY` widgets with no in-codec route, so the board has to
      pull them in. The precedent is on the msm8996 side —
      `msm8996-oneplus-common.dtsi` and `apq8096-db820c.dtsi`. The *length*,
      though, is only justified for the inputs that exist, so this point is
      settled by the DMIC pruning above rather than argued away.

    * **"The wcd9335 codec node looks weird too — any similar examples?"** Yes,
      and the node is near-verbatim from them: `msm8996-xiaomi-common.dtsi`
      (same `slim217,1a0` `codec@1,0`, `slim-ifc-dev`, `intr1`/`intr2`,
      `reset-gpios`, mclk + slimbus clocks, the `vdd-*` set, and a `divclk1`
      `gpio-gate-clock` even carrying the same `divclk1_cdc` label),
      `apq8096-db820c.dtsi`, `msm8996-oneplus-common.dtsi`,
      `msm8996pro-xiaomi-{natrium,scorpio}.dts`. Only the msm8953 addresses and
      the FP3 supply/GPIO/pinmux instantiations are new, because no msm8953
      board in-tree instantiates the SLIMbus NGD at all. **One genuine defect
      surfaced by the question:** on msm8996 the `slimbam` and `slim_msm` nodes
      live in the SoC `.dtsi` (`msm8996.dtsi`) and the board only writes
      `&slim_msm { ... }`; ours sit in the board `.dts` under `&soc`. They
      belong in `msm8953.dtsi`, status `disabled`, with the board enabling them
      and adding the codec child.

    The reviewer also confirmed the quinary DAI link is fine as it stands.

    **What a v2 would be**, once confirmed: cut `audio-routing` to `RX_BIAS`/
    `MCLK`, AMIC2 on MIC BIAS2, DMIC0 on MIC BIAS1 and DMIC2 on MIC BIAS3; drop
    `qcom,micbias4-microvolt`; move the NGD/BAM nodes to `msm8953.dtsi`. It
    touches `wip/7.1.3/audio`, `integration/7.1.3` and `debug-int/7.1.3`, and
    the mics have to be re-measured on the device afterwards, since the pruned
    routes are the ones that power the capture path. Open sub-question, not
    needed for the pruning but worth one test: which slot of each pad pair is
    the real capsule — covering one mic port and re-sweeping answers it.

15. **Review feedback on the audio *driver* commits — nothing implemented, each
    point needs confirming first.** The same reviewer read three commits of
    `wip/7.1.3/audio` on 2026-08-02 — `ca9aaa72` (mic bias and DMIC rate from
    the DT), `377269e4` (the TX front-end hold) and `254359e1` (MBHC jack
    detection) — and checking the comments turned up five more things we found
    ourselves. As in item 14, none of it is done, and each point is written with
    the argument against it, because three of them are cheaper to get wrong than
    to leave alone.

    One question the pass raised is **already answered**: *"where are
    `qcom,micbias1-microvolt` … and `qcom,dmic-sample-rate` defined? I can't see
    them in the bindings."* Item 2 above — the binding has carried all six since
    2026-07-30. What misleads a reader is that `wip/7.1.3/audio` is
    discovery-ordered, so there the driver commit precedes the binding commit; on
    `submit/7.1.3/audio` the binding is patch 1 of 13. Nothing to change, but the
    reply has to say so.

    * **A bare `BIT(2)` goes into `WCD9335_CODEC_RPM_CLK_MCLK_CFG`** in
      `wcd9335_codec_init()`, where every other field in this driver has a named
      macro in `wcd9335.h`. *Against naming it:* we cannot name it **truthfully**
      — there is no datasheet, and downstream has no name either, only an
      unnamed `tasha_codec_reg_defaults[]` entry (`{MCLK_CFG, 0x04, 0x04}`, and
      `0x05, 0x05` in the I²C variant, so the bit is independent of the MCLK
      rate). A confident invented name is the mistake of item 11 repeated. The
      honest options are a neutral name plus a comment saying the function is
      undocumented, or an A/B on the device to find out whether the write is
      needed at all — the commit claims garbled playback without it, and that
      claim is not backed by a recorded measurement. Two adjacent
      `regmap_update_bits()` on the same register should become one either way.
    * **The `0x20` written into the EFUSE sense-state field is a dead value.**
      `WCD9335_CHIP_TIER_CTRL_EFUSE_SSTATE_MASK` is `GENMASK(4, 1)` = `0x1e`, so
      `0x20 & 0x1e == 0`: the call clears bits 4:1 and does nothing else. That
      happens to be the intended "select state 0", but the constant reads as
      "set bit 5". Writing `0` is arithmetically identical, so **no device time
      is needed**. The oddity is inherited, not ours — downstream does the same
      `0x1E, 0x20` — so the only argument against is that it stops being a
      verbatim copy, which a comment covers. Cheapest item here.
    * **`WCD9335_CODEC_RPM_CLK_MCLK_CFG_12P288MHZ` is `BIT(0)`**, the same as
      `_9P6MHZ`; downstream writes `0x03,0x00` for 12.288 MHz, so it should be
      `0`. Pre-existing upstream, independent of this series, and a clean
      standalone patch. *Against:* the define is **unused**, so a maintainer may
      prefer deleting it to fixing it, and a patch found by reading rather than
      by measuring is easy to read as noise. Low priority, own submission cycle.
    * **The `usleep_range(1000, 1100)` before the TX-hold release has no cited
      source.** It runs per-ADC on every wcd9335 board. Downstream has no sleep
      at that site — its settle time came from the HPF delayed work's scheduling
      delay, which mainline dropped along with the release itself. *Against
      touching it:* removing it risks bringing back the silent capture this
      commit fixes, and proving that costs cold-boot A/B time on the device.
      Keeping it with a measured justification is an acceptable outcome; keeping
      it with none is not. The same commit message should also say why the
      release sits in the ADC widget's `POST_PMU` and not the decimator's — DAPM
      powers the decimator and its mux first, so the amic lookup there runs
      before the analog front end is up. Without that sentence the first review
      comment will be "move it to the decimator handler".
    * **The reviewer asked for a table instead of the `switch`** in
      `wcd9335_get_dmic_clk_val()`. Cheap, no functional change, and the six
      `WCD9335_DMIC_CLK_DIV_*` values are `0x0`–`0x5` in the same order as the
      dividers `{2, 3, 4, 6, 8, 16}`. *Against:* the `switch` is a deliberate
      copy of mainline `wcd934x_get_dmic_clk_val()` (`wcd934x.c`, same divider
      set, same fallback), and converting only ours ends the symmetry that makes
      folding both into one helper obvious later. Converting wcd934x too doubles
      the work on a driver **we cannot test**. Decide which, do not drift into it.
    * **The MBHC provenance needs checking, not patching.** `254359e1` links the
      v3 **cover letter** of Srinivas Kandagatla's 2018 WCD9335 series, which
      never mentions MBHC — hence the reviewer's "I cannot find references to
      the MBHC support dropped from the series". It is there: MBHC is patch
      11/13 in v3 and 11/14 in v4 (patchwork
      [10587057](https://patchwork.kernel.org/patch/10587057/), with its bindings
      patch [10587061](https://patchwork.kernel.org/patch/10587061/)), gone in v5
      (8 patches), and v6 — also 8 — is what was accepted, which is why mainline
      has never carried MBHC. But `254359e1` is a **superseded** commit: item 11
      replaced that private implementation with the shared `wcd-mbhc-v2`, and
      `f5759717`, the legacy comparator backend, cites only its OnePlus
      downstream source. So the open question is not the broken link, it is
      whether **anything** in `f5759717` derives from the 2018 patch. If it does,
      it must be cited; if it does not, adding the citation would be a false
      derivation claim — the camera mistake in mirror image. Answer it by reading,
      not by assuming either way.
    * **The TX-hold fix is codec-wide, and one other mainline board notices.**
      Mainline takes the hold in `wcd9335_codec_enable_adc()` and never releases
      it, so the change cannot regress anyone: it supplies a missing half. By
      inspection of the device trees — not measured, and it has to be worded that
      way — `msm8996-oneplus-common.dtsi` is the only other wcd9335 board wiring
      analog mics (AMIC2/4/5), so OnePlus 3/3T gain working analog capture, while
      `apq8096-db820c.dtsi` and the Xiaomi msm8996/msm8996pro boards declare no
      AMIC routes and their ADC widgets never power up. Worth stating in the
      cover letter and worth a Cc to the OnePlus 3 maintainers, who have hardware
      we do not. *Against:* a Cc invites a wait, and an unverified cross-board
      claim is worse than none — hence "by inspection".

    **Order, if any of it is confirmed:** the EFUSE constant first (no device
    time, no judgement call), then the DMIC table and the cover-letter wording,
    then the provenance read. The `BIT(2)` naming and the 1 ms sleep are last
    because both really want a measurement, not a decision.

Two things were checked and are **not** defects: the three `ENOTSUPP`
comparisons in the audio machine driver (the ASoC core returns exactly that, and
the base file plus six other qcom machine drivers compare against it), and the
undocumented `slim217` vendor prefix (absent from `vendor-prefixes.yaml`, but
already used by four device trees in Linus' tree).

## Licence and provenance

An audit on 2026-08-02 asked one question — *is anything in this work copied from
closed-source Android code, or otherwise carried under the wrong licence?* — and
walked all five `wip/7.1.3/*` categories, the SPDX header of every `.c`/`.h` they
touch, the authorship of every import commit, and the provenance tables in
[`kernel/README.md`](kernel/README.md#provenance) and
[`sensors/README.md`](sensors/README.md#provenance).

**The headline is negative: there is no closed-source Android driver in the fork
and no file carried under the wrong licence.** Every source file the five
categories touch is GPL-2.0 by SPDX — the single exception,
`scripts/mod/file2alias.c`, carries no SPDX line upstream either and this work
adds ten lines to it. No firmware blob is checked into either repository; the
ADSP, modem and WCNSS images stay on the phone's own partitions and are
referenced by name.

What the audit did find, in descending order of exposure. **None of it is acted
on**; each item needs its pro and contra written out and confirmed first, and the
first one is a legal judgement rather than a technical one.

1. **`drivers/media/i2c/lc898217.c` is the one part derived from closed
   source.** The actuator's whole register interface — slave address, address
   and data widths, position register, code width, power-up write — was read out
   of `libactuator_lc898217xc.so`, the proprietary vendor userspace library
   shipped with this board's Android firmware. There was no GPL source to take
   it from: Qualcomm's downstream keeps no register map in the kernel for this
   part at all (the node is a bare `qcom,actuator` with a CCI master number, and
   the generic engine in `msm_actuator.c` is fed the map from that library over
   an ioctl), and searching the downstream tree for the part number returns one
   hit, an unrelated string in `sound/pci/hda/patch_realtek.c`.

   In favour: what came out is a hardware register map for a **third-party ON
   Semiconductor part** — facts about hardware, not expression; it was read from
   the library's `.data` section rather than decompiled; and the decode was
   validated against a known answer (the same layout applied to
   `libactuator_dw9714.so` reproduces, field for field, what `dw9714.c` already
   does in-tree, and recovers that part's documented power-up sequence). The EU
   Software Directive's Article 6 interoperability exception and the US
   *Sega v. Accolade* / *Sony v. Connectix* line both point the same way, and the
   kernel takes reverse-engineered drivers routinely. The method is stated in the
   commit message rather than left implicit, which is the right shape.

   Against: any EULA on the firmware is a separate, contractual question that
   none of the above answers, and on the LKML this is the point a maintainer will
   ask about first. ☠️ **This is a decision for a human, not something to resolve
   by writing a better commit message.**

2. **The imported sensor base cannot carry a DCO.** `bc02a8f70f69` *WIP: iio:
   Add Qualcomm Sensor Manager driver* and `e4f194b29e8a` *WIP: iio: accel: …*
   are Yassine Oudjana's code and carry **no `Signed-off-by` at all**, not even
   his own. The licence is fine — GPL-2.0-only by SPDX — but the certification
   chain is not, and only he can supply it. His other two QRTR commits are
   properly signed off. Already the first of the three reasons
   `submit/7.1.3/sensor` is a single patch; see
   [`sensors/README.md`](sensors/README.md#why-the-submit-series-is-one-patch).

3. **Checked and clean, recorded so the question is not reopened.**
   `imx363.c` is Joel Selvaraj's reverse-engineering work under GPL-2.0, keeping
   `Copyright (C) 2018 Intel Corporation` from the driver it is structured on,
   and the import preserves the full chain (Joel → panpanpanpan → Richard Acayan
   → us). Every value taken from the vendor — DT addresses, mic-bias voltages,
   the DMIC rate, the JEITA thresholds, the actuator inversion in
   `msm_actuator.c` — comes from Fairphone's **published GPL kernel release**,
   the same licence as the files it lands in. `qcom_smbx.c`, `wcd9335.c`,
   `wcd-mbhc-v2.c`, `apq8016_sbc.c`, `q6afe.c` and `q6voice-dai.c` are all
   in-place extensions of GPL code that was already in the base.

4. **Four compliance gaps in this repository**, none in the kernel fork, all of
   them small:

   * There is **no `LICENSE` or `COPYING` file**. The
     [top-level README](../README.md#license) states GPL-2.0-only and nothing
     else does.
   * [`device_tree/downstream/fairphone/3.A.0136/`](device_tree/downstream/fairphone/3.A.0136/)
     redistributes 938 of Fairphone's GPL-2 device-tree files. Each one keeps its
     Linux Foundation copyright and GPLv2 notice — checked, not assumed — but
     **the licence text is not shipped alongside them**, which GPL-2 §1 asks for.
     Copying in a `COPYING` closes it.
   * [`sensors/bringup/data/sns.reg`](sensors/bringup/data/sns.reg) and the 1437
     pairs decoded from it in
     [`../userspace-sensors/registry.conf`](../userspace-sensors/registry.conf)
     are the phone's factory sensor registry — third-party vendor data, under no
     stated licence, in a public repository.
   * [`../userspace-sensors/groups.txt`](../userspace-sensors/groups.txt) is the
     group map taken from upstream
     [`sns-reg`](https://gitlab.com/msm8996-mainline/sns-reg)'s `map.c`, and
     **that project's licence is recorded nowhere here**.

   The libcamera and Snapshot changes are shipped as patches against their own
   upstreams, so they raise nothing.

Separately from licensing, the AI-authorship policy is already settled and needs
no work: local fork commits carry `Co-authored-by: Claude`, anything prepared for
the LKML carries `Assisted-by:` and never a `Signed-off-by` from the assistant.
That is also why the LKML is the only open destination — see
[`FP3-TODO.md`](FP3-TODO.md) and the top-level README.

## The notification LED blinks forever after a missed call

**Symptom:** after a missed call the LED keeps blinking; dismissing the
notification does not stop it.

It is **not** the camera flash — the phone exposes no flash or torch LED at all:

```
/sys/class/leds/ →  mmc0::   mmc1::   rgb:status
```

and the device tree contains no flash node (see the parked one below). What
blinks is `rgb:status`, the RGB status LED on the PMI632 LPG.

**Measured on the device:**

* `rgb:status` uses the `pattern` trigger with **`repeat = -1`** — repeat forever;
* feedbackd's `default.json` defines `phone-missed-call` as a `Led` feedback,
  `#00FFFF`, and `notification-missed-generic` as a blue one at frequency 500 —
  **neither carries a duration**, so the feedback runs until the client ends it;
* there is **no `fairphone,fp3.json` theme** installed (the FP5 has one, the FP3
  does not), so those generic rules are what apply.

**Immediate workaround:** `echo 0 | sudo tee /sys/class/leds/rgb:status/brightness`,
or restart feedbackd.

**Two things to do, in this order:**

1. Find out who fails to call `EndFeedback` when the notification is dismissed —
   phosh or the calls app. That is the actual bug; everything else limits the
   damage.
2. Ship a `fairphone,fp3.json` feedbackd theme that gives those LED feedbacks a
   bounded duration. It belongs next to the other userspace drop-ins this repo
   carries (`userspace-audio/udev`, `pulse`, `ucm2`).

## ~~Parked: the PMI632 camera flash~~ — it works, 2026-08-03

The parking reason was right and the fix was small. `leds-qcom-flash.c` accepts
three flash-module subtypes and refuses everything else with *"flash LED subtype
%#x is not yet supported"*; read over the SPMI regmap on the phone, the PMI632
module answers `0x18` in `FLASH_TYPE` and **`0x05`** in `FLASH_SUBTYPE`, which is
none of them. Enabling the node as it stood would have failed the probe exactly
as feared.

☠️ **The module is on the second USID, not the first.** `0xd300` reads back all
`XX` on `0-02` and the real values on `0-03`. The charger at `0x1000` on `0-02`
is the positive control that tells "wrong USID" from "the read path is broken".

It is the three-channel block with two channels bonded out, so the fix is a
fourth branch taking `mvflash_3ch_regs` with `max_channels = 2`. Measured with
the module idle, the live registers are that layout exactly — timers at
`0x40..0x42`, target currents at `0x43..0x45`, module enable `0x46`, current
resolution `0x47`, strobe `0x49..0x4b`, channel enable `0x4c`, torch clamp
`0xec` — which is also the map Qualcomm's downstream `qpnp-flash-led-v2` uses
for this PMIC, from the same code path as PMI8998 and PM8150, rejecting only
channel ids above 1. `CONFIG_LEDS_QCOM_FLASH` also had to be turned on; it was
not in the config at all.

Measured on `linux-fp3-7.1.3-r34` (`#35-fp3`), three ways, because the first
instrument lied:

| | |
|---|---|
| probe | `white:flash` under `/sys/class/leds`, nothing in dmesg |
| the hardware is programmed | `CHAN_EN 0x03` (both ganged channels), `MODULE_EN 0x80`, `ITARGET 0x3b` on both — 0x3b is 59, so (59+1) × 5 mA = 300 mA a channel, the 600 mA of `led-max-microamp` split in two |
| current flows | USB input ADC, three interleaved passes: off 74 437 / 87 737 / 76 729 against on 139 900 / 153 524 / 144 928 — no overlap |
| light comes out | the rear camera sees the scene go from mean 15.82, σ 0.81, 20 distinct values to mean 70.0, σ 34.4, ~240, repeatable to 0.09 across three passes |

☠️ **The battery is the wrong ammeter here, twice over,** and believing it
produced a confident "no current flows" about a flash that was visibly lit.
`pmi632-battery` exposes **no `current_now` at all** — the charger driver does
not implement the property — and the check's `|| echo 0` turned that missing
file into a reading of zero. Falling back to battery *voltage* droop was no
better: with a cable attached the torch is fed from USB, so the pack never sees
the load. The instrument that works is the PMIC's own USB input current ADC
(`in_voltage_usb_in_i_uv_input`), and it needs interleaved repeats — a single
on/off pair sits inside its noise. The positive control that would have caught
the second error early is cheap: eight busy loops drop battery `voltage_now` by
180 mV, so the channel *can* see a load of that size; the torch showing nothing
meant the path, not the light.

What is **not** carried over from downstream: on this PMIC the flash is fed by
the charger's boost, and downstream sets `POWER_SUPPLY_PROP_FLASH_ACTIVE` on the
charger around a strobe, via its own `schgm-flash` block at `0xA600`. Nothing in
mainline does that. It does not stop the torch — the charger's `VREG_OK` (bit 4
of `0xA607`) comes up on its own when the LED module is enabled, measured going
`0x00` → `0x36` — but the full 2 A strobe has not been tried and may well need
it. `FORCE_BOOST_CONTROL` at `0xA641` stays `0x00` throughout.

Checks: [`tests/checks/42-camera-flash-test.sh`](../tests/checks/42-camera-flash-test.sh)
for the registers and the current, and
[`userspace-camera/flash-check.py`](../userspace-camera/flash-check.py) for the
optical confirmation, which needs a scene and so cannot live in the unattended
battery.

Still open: the torch now appears under `/sys/class/leds`, which gives feedbackd
something new to blink — see the missed-call item above.
`CONFIG_V4L2_FLASH_LED_CLASS` is deliberately still off, so no
`/dev/v4l-subdev` exists for it and libcamera cannot drive the flash yet; that
was kept out so the bring-up measured one change.

## Untested: interconnect path for the SCM/crypto node

An idea from the SLIMbus framer investigation that was never confirmed:
downstream's `pil-tz` votes MASTER_SPS→EBI bandwidth around the PAS SCM calls,
while mainline's `qcom_scm_bw_enable()` is a no-op here because the `scm` node
carries no interconnect path. Adding one would make `bw_enable()` vote during
`pas_init_image` / `mem_setup` / `auth_and_reset`:

```dts
&scm {
	interconnects = <&pcnoc MAS_CRYPTO RPM_ALWAYS_TAG
			 &bimc SLV_EBI RPM_ALWAYS_TAG>;
	interconnect-names = "crypto-ddr";
};
```

The audio path works without it, so this is not a blocker — it is kept in case
ADSP boot timing ever needs revisiting.

## Settled: the two QDSP6SS framer pokes were not needed

Removed on 2026-07-29. `integration/<base>` used to carry two commits clearing
QDSP6SS `0x0c20002c` bit 3 — one in `qcom_q6v5_pas.c` after `AUTH_AND_RESET`,
one in `qcom-ngd-ctrl.c` before the capability exchange. Both are reverted,
along with the `qcom,slim-framer-quirk-reg` device tree property that armed the
second one (76 lines gone).

What settled it, on the same phone with the same protocol, one variable:

| | audio opens | tone across SLIMbus both ways | `MC:0x21` | codec |
|---|---|---|---|---|
| without the pokes | 8/8 cold boots | 8/8 | 8 | 1 |
| with the pokes | 8/8 cold boots | 8/8 | **8** | 1 |

Not a trace of a difference. Three things worth keeping from getting there:

* **The PAS poke never wrote anything.** Its own log line reads
  `QDSP6SS 0xc20002c 0x101->0x101` — by the time it runs, bit 3 is already
  clear. Only the SLIMbus one wrote (`0x10b->0x103`).
* **`MC:0x21` is not a fault signal.** It is `SLIM_USR_MC_DEF_ACT_CHAN`,
  "define and activate channel", from `qcom_slim_ngd_enable_stream()`. It
  appears eight times per boot **with and without** the pokes while audio works
  — the count tracks how many streams are started, not how many failed. Same for
  `MC:0xd` (`ADDR_QUERY`, which is why `Failed to get logical address` is
  followed 200 ms later by the codec answering) and `capability exchange
  timed-out`.
* **A boot with nobody logged in measures nothing.** The first version of this
  test counted `MC:0x21` in the kernel log and found none in twenty-five boots,
  because without a user session nothing starts audio and the log ends at
  twenty seconds. The metric has to open the audio path.

Reverting the PAS commit does **not** change which ADSP firmware is loaded: the
descriptor it added differed from the msm8996 one only in the firmware name and
the quirk register, and the FP3 device tree sets `firmware-name` on `&lpass`,
which the driver prefers. The `required-opps` CX-turbo idea that used to share
this experiment was already disproven separately —
`qcom_pas_pds_enable()` votes `INT_MAX` on every proxy power domain, measured
live as `cx_perf = 2147483647` for roughly 160 ms across the ADSP boot window,
so it was a no-op.

## Also open, written up elsewhere

* **Charging asks for 2 A**, where it used to be capped at 1 A, and the battery
  it asks on behalf of is now verified before its limits are applied. What is
  left, in order: the **mismatch path has never run on hardware** (a
  device-tree-only cycle with a deliberately wrong `qcom,batt-id-ohm` would
  measure it), **2 A has not been seen flowing** (needs a wall charger and a low
  state of charge), and the **input side** — without high-voltage negotiation the
  USB port supplies about 1.9 A into the cell. Still open beyond that: selection
  between the two packs the FP3 ships, which needs a binding for more than one
  `monitored-battery`; the float-voltage half of JEITA; step charging; and the
  thermal trip temperatures, which are a choice rather than a measurement. See
  [`charger/README.md`](charger/README.md).
* **Sensors work**, including proximity blanking during a call and ambient
  light. What is left there is calibration rather than bring-up: the
  magnetometer has an unknown hard-iron offset and scale, and the mount matrix
  is inherited from msm8996. See [`sensors/README.md`](sensors/README.md).
* **Camera streaming is not working end to end.** The sensor probes and its
  link into CAMSS enables; what remains is on the CAMSS side, not in the
  driver — see the `submit/<base>/camera` commit message. The one lead inside
  the driver is that its two modes carry link frequencies that disagree with the
  device tree's `link-frequencies`, and one of them is commented
  `// NOT SURE HOW TO FIND THIS VALUE` by its author.

## The package moved to `debug-int/7.1.3`

`linux-fp3/APKBUILD` pinned `_commit=c8974511d585` through two rewrites and ended
up unreachable from any branch: the camera-provenance rebuild on 2026-07-30 moved
it onto an archived lineage, and the debug split later the same day added a second
one. It was also, concretely, a kernel **without the watchdog** — the safety net
commit landed after it.

So on 2026-07-30 the pin moved to `debug-int/7.1.3` and `pkgrel` went to 23. That
is the branch the package builds from now on: `integration/<base>` plus the debug
layer, so what runs on the phone always carries the watchdog started at probe.
`integration/<base>` deliberately does not, because it is the branch that has to
keep matching the `submit` series.

Still open: **the build and the deploy.** `./pmb checksum` has run and the pin
resolves, but the package has not been rebuilt or installed, so the phone is still
running `linux-fp3-7.1.3-r22` — which is to say, still without a watchdog. That is
one build-and-flash cycle, and until it happens an early hang still needs a thumb
on the power button.

Both old tips are kept alive as tags —
`archive/integration-7.1.3-pre-camera-provenance` and
`archive/integration-7.1.3-pre-debug-split` — because GitHub serves a source
tarball only while its commit is reachable from some ref. Rewriting `integration`
without them would have left the pinned package un-buildable, a failure that
shows up much later than the change that caused it. The one-line check is in
[the branch model](../README.md#the-branch-model).
