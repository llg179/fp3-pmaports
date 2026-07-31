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
