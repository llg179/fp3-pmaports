# Headset jack — how the current arrangement was arrived at

The settled description is in [`docs/audio/README.md`](../../README.md). This is
the record of what was tried on the way there, kept because most of it is
*negative* — whole approaches that look obviously right and do not work on this
codec. Without it the next attempt starts by rebuilding them.

## The problem as it presented itself

The reported jack state was sometimes inverted for a whole boot: audio routed to
headphones with nothing plugged in, the handset microphone used while a headset
was in the socket, the earpiece silent. Replugging did not fix it; rebooting
did, sometimes.

The cause was visible in the driver at a glance. The insert state is a count:

```c
wcd->jack_inserted = !wcd->jack_inserted;   /* once per L_DET interrupt */
```

A count has no way back to the truth. One interrupt missed or spurious and every
later report is inverted, permanently. So the obvious fix is to read the state
instead of counting it — and that is the approach the rest of this document
spends its length disproving.

## What the reference implementations do

Three working drivers solve the same problem and all three take the direction of
an edge from hardware.

`msm8916-wcd-analog`, which every other msm8953/msm8916 phone uses:

```c
if (snd_soc_component_read(component, CDC_A_MBHC_DET_CTL_1) &
                CDC_A_MBHC_DET_CTL_MECH_DET_TYPE_MASK)
        ins = true;
```

`wcd-mbhc-v2`, shared by `wcd934x`, `wcd937x`, `wcd938x`, `wcd939x` and
`pm4125`:

```c
detection_type = wcd_mbhc_read_field(mbhc, WCD_MBHC_MECH_DETECTION_TYPE);
wcd_mbhc_write_field(mbhc, WCD_MBHC_MECH_DETECTION_TYPE, !detection_type);
if (detection_type) { /* insertion */ }
```

`msm8916-wcd-analog` also has a second, independent answer: a board-level
jack-detect GPIO through `snd_soc_jack_add_gpios`, readable at any time. Neither
Qualcomm's msm8953 audio device tree nor this phone has such a line, so that
route is closed here — which is worth knowing before designing around it.

## Which bit is the plug status

The port had been reading `RESULT_3` bit 3 and calling it the plug status. Five
in-tree codecs of the same MBHC family map that register identically, and by
their field tables:

| bits | field |
|---|---|
| 0-2 | `BTN_RESULT` |
| 3 | `HS_COMP_RESULT` — headset comparator, an *electrical* result |
| 4 | `SWCH_LEVEL_REMOVE` — the *mechanical* plug status |
| 5 | `MIC_SCHMT_RESULT` |
| 6 | `HPHR_SCHMT_RESULT` |
| 7 | `HPHL_SCHMT_RESULT` |

So the driver was using the electrical comparator where the mechanical status
was meant. That looked like the whole explanation. It was not: neither bit
follows the socket on this codec.

## The measurements, in the order they were taken

The tool is [`../tools/jack-probe.py`](../tools/jack-probe.py), which samples
every MBHC register raw while a jack is plugged and pulled. It was rewritten
once, after the first version watched only the bit the driver already believed
in — a tool built around a belief cannot discover the belief is wrong.

**1. No register follows the socket.** Eight physical insert/remove cycles:
`RESULT_3` stayed at `0x08` and `ANA_MECH` did not move. A driver change
already written to read the register instead of counting was measured before it
shipped; it would have reported "unplugged" permanently.

**2. The read path was live, so the standing still was real.** Only six of the
sampled registers are live reads — `ANA_MECH`, `ANA_ELECT`, `ANA_ZDET` and
`RESULT_1..3` are in the driver's volatile list, the rest come from the regmap
cache and prove nothing. The path was validated with a known positive:
`ANA_MICB2` and `ANA_BIAS` move when the microphone bias is powered, in the same
log where `RESULT_3` did not.

**3. The plug-type polarity was wrong, and fixing it changed nothing.**
Qualcomm's device tree for this hardware class marks both jack switches normally
open; the port had left them at the normally-closed default. The properties were
added and verified to reach the codec (`ANA_MECH` `0x85` → `0x9d`). The same
eight-cycle measurement afterwards produced the same result: no status register
moves. The change is kept, because it is the correct description of the board,
but it is not a fix and is not credited as one.

**4. The boot value is correct, and no interrupt fires during boot.** Instrumenting
the seed showed `RESULT_3` reading `0x00` at probe with a plug in and `0x08`
with the socket empty — the right answer both ways. It works because the init
sequence puts the block in a known state and reads shortly after starting the
FSM.

**5. Ordinary use does not produce stray edges.** With the socket empty and
untouched: playback start/stop, capture start/stop, the full card-profile
off/on cycle a call performs, and the voice PCM opening and closing — zero
interrupts from all of them.

**6. Reading the register in the interrupt handler fails.** Replacing the count
with `ins = !(RESULT_3 & BIT(3))` produced five interrupts for ten physical
events, every one reading "out", and no insertion was ever reported.

**7. Re-running the detection first does not help either.** `RESULT_3` holds the
outcome of a completed detection rather than a live level, so the handler was
made to cycle `FSM_EN` and wait before reading. Same result: five interrupts for
ten events, and `stale` and `fresh` identical on every one.

## Why 6 and 7 fail — the loop that closes

The five-interrupts-for-ten-events signature is the tell. Removals were not
missed; they were never detected, because `MECH_DETECTION_TYPE` selects which
transition L_DET watches, the driver writes that bit from the insert state, and
the insert state was stuck at "out". Armed only for insertion, the block reports
only insertions.

The same dependency defeats the read:

> `RESULT_3` is not an absolute plug status. It reports whether the transition
> the block was **armed for** occurred — and the arming is written from the
> state one is trying to derive.

This also explains an earlier result that looked like success. A read-only sysfs
probe that cycled the FSM and sampled the outcome reported `IN` with a plug in
and `OUT` with the socket empty, three times each. It was not measuring the
socket: the counter was independently keeping `MECH` correct, so the probe was
reading back the counter's own output. The seed works for the same reason — the
init sequence, not a measurement, puts the block in a known state first.

## What this rules out

- Reading any MBHC register as an absolute plug status, with or without
  re-running the detection.
- Polling: an FSM cycle from outside the handler swallowed a real edge once, so
  a periodic poll would actively degrade detection.
- A board jack-detect GPIO: there is none.

An absolute source would have to be independent of `MECH_DETECTION_TYPE`, and
nothing available on this codec is.

## What is still open

The inversion that started this has never been reproduced deliberately. Boot,
clean plug cycles and codec power transitions are all measured clean, so
whatever produces the stray or missed edge happens somewhere not yet exercised —
most likely during a real call, where the modem and the voice path are also
active. The instrumentation for catching it passively is a `dev_info` in the
interrupt handler printing the registers and the uptime at each edge; with that
in place a single real call would show it.

## Instrumentation used

- [`../tools/jack-probe.py`](../tools/jack-probe.py) — samples every MBHC
  register raw against what the driver reports, from userspace.
- Two temporary `dev_info` lines in `wcd9335.c`, one at the seed and one per
  edge, printing the registers and the uptime. Not committed; they are cheap to
  restore from this description and should not live in the tree.
- [`read-result3-variant.patch`](read-result3-variant.patch) — the last of the
  read-based variants exactly as it was measured, with those two `dev_info`
  lines and the `IRQF_TRIGGER_FALLING` addition. It is kept because it is the
  artefact the "one event late" section was measured on, **not** because it
  works: it derives the post-edge state from a register that still holds the
  pre-edge one. Restore it to reproduce that measurement, not to fix the jack.

---

# Second round: what the register actually holds, and why the shared code cannot take us

The first round ended on "no MBHC register follows the socket, so the edge count
cannot be replaced". That conclusion was drawn from variants that all failed the
same way, and it was too strong. What follows corrects it.

## The register does hold the state - one event late

Instrumenting the interrupt handler to log `RESULT_3` on entry, with the working
counter left in place so there was something true to compare against, gave nine
edges over a deliberate insert/remove sequence:

| edge | state before the event | `RESULT_3` |
|---|---|---|
| 1 | OUT | `0x08` |
| 2 | IN | `0x00` |
| 3 | OUT | `0x08` |
| … | … | agreeing on all nine |

`RESULT_3` reports the **outcome of the last completed detection**, which is the
state as it was *before* the edge being handled. Nine out of nine.

That makes the correct derivation trivial, because an interrupt means the state
changed:

```c
ins = !!(read(RESULT_3) & BIT(3));   /* bit 3 = "was out" -> is now in */
```

Every variant built in the first round computed `!(...)` instead - the pre-edge
value used as the post-edge answer. Inverted on every edge, and since the arming
bit was written from the same value, the pair latched immediately. The three
failures, the `OUT,OUT,OUT / IN,IN,IN` pattern and the two results that looked
like success are all that one missing negation.

So the first round's conclusion stands only as: *the three variants tried were
wrong*. Whether the corrected polarity works has not been measured.

## The inversion, caught live

The same run ended with **nine** edges - an odd number - an empty socket, and the
driver reporting a headset present. One event went unpaired and the state stayed
inverted, which is the original complaint, reproduced with a log for the first
time.

## Debouncing is not the cause

The insert/remove debounce is programmed to 96 ms
(`PLUG_DETECT_CTL` = `0x86`, `INSREM_DBNC` = 6). Deliberately fast plug-unplug
pairs still produced **both** edges, 244 ms and 336 ms apart, against 2544 ms and
2368 ms for the slow control pairs. Nothing merges at the speed a hand can
manage, so lost events are not a debouncing artefact and lowering the timer would
not help.

## Two interrupts exist for the two directions, and are unused

The codec exposes five MBHC interrupts and this driver requests three:

```
WCD9335_IRQ_MBHC_SW_DET                  8   requested - mechanical, no direction
WCD9335_IRQ_MBHC_ELECT_INS_REM_DET       9   NOT requested - electrical removal
WCD9335_IRQ_MBHC_BUTTON_PRESS_DET       10   requested
WCD9335_IRQ_MBHC_BUTTON_RELEASE_DET     11   requested
WCD9335_IRQ_MBHC_ELECT_INS_REM_LEG_DET  12   NOT requested - electrical insertion
```

All five are wired into the regmap-irq chip already. The vendor driver binds the
two unused ones to separate handlers:

```c
.mbhc_sw_intr     = WCD9335_IRQ_MBHC_SW_DET,
.mbhc_hs_ins_intr = WCD9335_IRQ_MBHC_ELECT_INS_REM_LEG_DET,
.mbhc_hs_rem_intr = WCD9335_IRQ_MBHC_ELECT_INS_REM_DET,
```

so "one interrupt sets inserted, another sets removed" is the hardware's own
arrangement, not a workaround. The vendor keeps them masked outside the detection
phases, so whether they fire usefully on their own is untested here.

## There is no board jack-detect GPIO - now actually established

The earlier claim rested on grepping two source trees, neither of which would
necessarily carry a board-level line. The authoritative source is the shipped
firmware: 34 device tree blobs extracted from the stock `boot.img` and
`dtbo.img`, including the ones describing this phone (identified by the AW8898
amplifier and the Himax touchscreen), decompiled and searched. **No property
name containing "jack" anywhere**, and the only MBHC properties are the two
switch-type ones. The absence is real.

## Why the shared mainline implementation could not be adopted as it stood

`wcd-mbhc-v2.c` is in mainline, maintained, and used by five codecs, so wiring
`wcd9335` to it looks like the obvious answer. It is not, for one reason:

**mainline's copy implements only ADC-based detection.** `grep` for detection
entry points finds exactly one, `wcd_mbhc_adc_detect_plug_type()`, called
directly with no alternative. And the WCD9335 has **no MBHC ADC**: the vendor's
own field table for this codec defines **29** fields where mainline names 48,
and every missing one is either an ADC field, a moisture field or a headphone
ground switch.

The vendor tree that actually drives this codec has no seam either - in the
tasha-era `msm8952` trees `wcd-mbhc-v2.c` is a single 2284-line file that only
does comparator detection, because at that point there was nothing else to do.
The two-backend split appears later, once ADC-capable codecs arrive, and is
what 163 vendor trees carry today:

```
snd-soc-wcd-mbhc-y  := wcd-mbhc-v2.o          common core
                    += wcd-mbhc-adc.o          if CONFIG_..._ADC
                    += wcd-mbhc-legacy.o       if CONFIG_..._LEGACY
```

```c
struct wcd_mbhc_fn {
        irqreturn_t (*wcd_mbhc_hs_ins_irq)(int, void *);
        irqreturn_t (*wcd_mbhc_hs_rem_irq)(int, void *);
        void        (*wcd_mbhc_detect_plug_type)(struct wcd_mbhc *);
        bool        (*wcd_mbhc_detect_anc_plug_type)(struct wcd_mbhc *);
        void        (*wcd_cancel_hs_detect_plug)(struct wcd_mbhc *, struct work_struct *);
};
```

Mainline flattened that seam when the code was upstreamed, and correctly so:
every in-tree user was ADC-capable, and an indirection with a single
implementation is something review declines. Restoring it is not a fight with an
earlier decision - it is supplying the second user the decision was waiting for.

It also turned out that mainline never removed the *idea*, only the second
implementation. `enum wcd_mbhc_detect_logic` has named `WCD_DETECTION_LEGACY`
all along, and `mbhc->mbhc_detection_logic` was there too - written once with a
constant, read in exactly one place. The seam was a stub waiting for a user.

## The vendor's field table is the authority for what each bit means

Most of the guesswork in the first round is answered by a table that was
available all along: the vendor driver's `wcd_mbhc_registers[]` for this exact
codec, 36 entries of register plus mask.

```c
WCD_MBHC_REGISTER("WCD_MBHC_L_DET_EN",            WCD9335_ANA_MBHC_MECH, 0x80, 7, 0),
WCD_MBHC_REGISTER("WCD_MBHC_GND_DET_EN",          WCD9335_ANA_MBHC_MECH, 0x40, 6, 0),
WCD_MBHC_REGISTER("WCD_MBHC_MECH_DETECTION_TYPE", WCD9335_ANA_MBHC_MECH, 0x20, 5, 0),
WCD_MBHC_REGISTER("WCD_MBHC_MIC_CLAMP_CTL",       WCD9335_MBHC_PLUG_DETECT_CTL, 0x30, 4, 0),
```

It also settles a caveat hanging over every negative result in the first round.
Those were all measured under **this driver's** init sequence, which is a subset
of the vendor's: `GND_DET_EN` and `MIC_CLAMP_CTL` are never programmed here, and
the button current source is left permanently enabled. "The register does not
work on this codec" may yet turn out to be a statement about the configuration
rather than the hardware.

## Method notes worth keeping

- **A restore is not a restore until a checksum says so.** A module was staged in
  `/tmp` and re-installed from there across several reboots. `/tmp` does not
  survive a reboot; `install` failed silently; the command chain used `;` rather
  than `&&`, so the reboot happened anyway; and the device was declared restored
  twice while running the wrong module. One measurement was taken on it and had
  to be thrown away. Verify by md5 after installing *and* after booting.
- **When a person applies the stimulus, specify the spacing, not just the
  order.** "In, then out" five times produced five interrupts for ten movements,
  which was read as one direction never being detected. Unspecified timing meant
  a merged fast pair explained it equally well; the ambiguity was created by the
  instruction. Repeating it with five-second gaps ruled the timing out.
- **The stock firmware is a board description you can read.** Pulling the DTBs
  out of `boot.img`/`dtbo.img` and decompiling them takes a few minutes and
  answers hardware-presence questions that no source tree can.

---

# Outcome: the shared implementation, measured

The two rounds above end on "the count cannot be replaced by reading a
register". That conclusion stands for the register, and is beside the point for
the problem: the count was replaced by **not keeping one**. `wcd9335` now uses
the kernel's shared `wcd-mbhc-v2`, with a legacy comparator backend added to it
because this codec has no MBHC ADC.

## What the caveat was worth

Every negative result in both rounds carried the same footnote — they were all
measured under this port's own MBHC init, which is a subset of the vendor's. The
footnote turned out to be the whole story for at least one of them:

| socket | old init | shared init |
|---|---|---|
| empty | `RESULT_3 = 0x08` | `RESULT_3 = 0x10` |
| plug in | `RESULT_3 = 0x08` | `RESULT_3 = 0x00` |

The register that "does not follow the socket" follows it once the block is
programmed the way the vendor programs it. **This is not yet a usable absolute
status** — `MECH_DETECTION_TYPE` co-varies with it in every sample, which is the
same confound the second round identified — but "the hardware cannot do this" was
never a safe reading of the earlier data, and it was made anyway.

## Measured, ten physical movements

| stimulus | reported |
|---|---|
| empty socket at boot | nothing inserted |
| 4-pole headset | headphone **and** microphone |
| 3-pole headphone | headphone only |
| removal | nothing inserted |

Ten movements, ten interrupts, no loss. The plug type is decided by the
detection algorithm, not read off a bit: `RESULT_3` is `0x00` for both
accessories, and what separates them is the button-press comparator firing
continuously for the three-pole plug whose microphone pin is grounded.

## Two defects the measurement found in the new code

- **A plug cycle that names no type left an interrupt enable unpaid**, and the
  next detection tripped `Unbalanced enable for IRQ`. The `enable_irq()` was
  removed; it only refined extension-cable handling, and removal is detected
  mechanically anyway. Worth recording *why* it was there: the risk had been
  reasoned about before the run and dismissed with "the balance holds for the
  normal sequence" - which was true only of sequences where something gets
  reported.
- **The plug type can still be `INVALID` after the three-second loop**, because
  every path through the loop can end in a `continue`. Mainline's
  `wcd_mbhc_find_plug_and_report()` answers that with `WARN(1)`, while the
  downstream version it was ported from only logged, which is why the vendor code
  carries no guard.

## Method notes from this round

- **A failing instrument looks exactly like a quiet subject.** Two capture
  scripts reported nothing while the driver was working perfectly: one piped
  `evtest` into a loop, where block buffering held every line, and one polled
  with `sleep 0.2`, which the device's shell does not honour. Both were believed
  before the single direct read that contradicted them. Take one manual reading
  of the thing the harness is supposed to report before trusting a null result
  from it.
- **A shared implementation can require hardware plumbing the driver never
  needed.** Moving to `wcd-mbhc-v2` meant two headphone over-current interrupts
  that the codec has always had but this driver never mapped, and the shared code
  refuses to initialise without them.
- **An interrupt id is not an interrupt.** The other codecs resolve theirs with
  `regmap_irq_get_virq()` at probe; a static table of regmap-irq indices compiles,
  loads, and requests entirely different interrupts. Caught by reading a sibling
  driver rather than by testing - the failure would have looked like "the jack
  does not work".
