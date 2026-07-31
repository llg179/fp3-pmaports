# Bringing up FP3 audio

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The investigation behind [`../README.md`](../README.md), kept as a narrative:
what was believed at each step, what was measured, and what that forced us to
conclude — including, at length, the places where the belief was wrong. The
reference material — what the audio port consists of, how the layers fit, how to
check it works — is in the README; this is the reasoning, and the instruments
and raw data that produced it.

Nothing here is needed to run audio. Everything that is, lives in
[`../../../userspace-audio/`](../../../userspace-audio/) and in the kernel
package.

> **Where things stand is deliberately not on this page.** What works today and
> how it fits together is in [`../README.md`](../README.md); what is still open
> is in [`../../TODO.md`](../../TODO.md) and
> [`../../FP3-TODO.md`](../../FP3-TODO.md). This is a record of how the current
> arrangement was arrived at, and it is **not** revised when the device changes —
> so read anything below as "what was true when it was measured", with the date
> the step carries.

## Contents

| | |
|---|---|
| [`qdsp6ss-framer-poke.md`](qdsp6ss-framer-poke.md) | the QDSP6SS register the kernel wrote on every boot to make the framer answer — what it was, why it looked necessary, and the measurement that retired it |
| [`tools/`](tools/) | the instruments below |
| [`data/`](data/) | register dumps taken from both operating systems on the same hardware |

## The instruments

These are period pieces, kept as they were used. Their working notes are in
Hungarian, unlike the rest of this repository: they were written during the
investigation, not for it, and rewriting them now would misrepresent what was
actually run.

| file | what it does |
|---|---|
| [`tools/pmic_gpio_out.py`](tools/pmic_gpio_out.py) | drives PM8953 GPIO1 through the gpio chardev and **holds it open** — the pin that carries the codec's 9.6 MHz master clock. Written to test whether the clock was reaching the codec at all, which turned out to be the whole question |
| [`tools/ngd_census.py`](tools/ngd_census.py) | read-only register census of the AP-side SLIMbus satellite (NGD1), for comparing a dead boot against a live one |
| [`tools/ngd_cfg_hold.py`](tools/ngd_cfg_hold.py) | holds `NGD_CFG.ENABLE`, written after the discovery that the bit **clears itself in hardware** |
| [`tools/frm_wakeup_pulse.py`](tools/frm_wakeup_pulse.py) | tries to force a superframe start from the AP side. It did not work, and the reason it could not is part of the story below |

## Raw data

| file | contents |
|---|---|
| [`data/ap-framer-read.txt`](data/ap-framer-read.txt) | the framer block read from the AP with the NGD force-resumed — the measurement that showed the registers were plainly AP-readable and an elaborate MMIO workaround had been unnecessary |
| `data/pmosdm_framer.bin` / `data/utdm_framer.bin` | the framer register block, dumped under postmarketOS and under Ubuntu Touch on the same phone |
| `data/pmosdm_lpasscc.bin` / `data/utdm_lpasscc.bin` | the LPASS clock controller block, same two-sided dump |
| `data/pmosdm_block2.bin` / `data/utdm_block2.bin` | a third block, same pairing |

The two-sided dumps are the shape the whole investigation took for weeks:
**the same hardware, one operating system where audio worked and one where it
did not, diffed register by register.** That method found real differences. It
did not find the answer, because the answer was not in any of these registers.

## The shape of it

The phone could ring and play through its loudspeaker. Its earpiece and both
microphones were silent — not broken, *silent*, and that distinction cost
weeks.

The loudspeaker is the reason. It hangs off QUIN_MI2S and an AW8898 amplifier,
a completely ordinary path. Everything else — earpiece, handset microphone,
headset microphone — goes through the WCD9335 codec on **SLIMbus**, a bus
essentially only Qualcomm uses, timed by a coprocessor running signed firmware,
clocked from a separate power management chip. When one layer of that quietly
does nothing, nothing complains: the bus comes up, the stream opens, the mixer
levels read correctly, and the recording is a file of the right size full of
zeros.

## The wrong turn, in public

Before the working fixes, the investigation produced a genuinely rigorous and
completely misdirected conclusion. It is worth stating first, because
everything after it is easier to read with the failure mode in mind.

An issue was opened on the mainline msm8953 tracker
([msm8953-mainline/linux#255](https://github.com/msm8953-mainline/linux/issues/255))
reporting that the codec's bus never comes up. The evidence in it is real: the
kernel-side requests proven byte-identical to the working vendor stack;
firmware, clocks and regulators compared two-sided; register programming
matched against a sister chip; the coprocessor's own internal logs pulled out
over a debug channel to show it boots fine and then declines to start the bus.
Having exhausted everything visible, it concluded that the remaining difference
was the interface never acquiring sync on the physical wires, and asked upstream
for the one thing no outsider has — Qualcomm's proprietary diagnostic captures
from a working boot.

That was wrong. The bus never acquired sync on the physical wires because **the
clock was never physically there**, for a reason one layer above everything the
investigation had been staring at. The final symptom, filed as evidence of an
intractable proprietary wall, is the textbook signature of a missing clock.

Nothing about that was sloppy. It reasoned hard, gathered real evidence, and
mistook *"I have exhausted my hypotheses"* for *"the answer is outside."*
**Confidence tracked the amount of work, not the distance to the truth.** The
issue is still open, a permanent public record of a very well-evidenced
argument for looking in the wrong place.

## Step 1 — the clock that never arrived

The codec's master clock comes from a PM8953 pin that has to be muxed into a
particular function. The device tree named its pin states `"active"` and
`"sleep"`. The pinctrl core applies only the state named `"default"` at probe.
There was no `"default"`, so the mux was never applied, and the clock never
physically reached the codec's MCLK pin.

In software the clock existed and was running — a clock provider, a consumer,
a rate, no error anywhere. In copper it was not there.

Two device tree faults, in order:

1. `pinctrl-names = "active", "sleep"` — no `"default"`, so nothing was applied;
2. renaming it to `"default"` was not enough on its own: the extra pin
   configuration made the state apply fail, which aborted the gate clock's
   probe.

The fix is `pinctrl-names = "default"` with a **bare mux** — `function = "func1"`
plus `power-source`, and no other pin configuration.

What ended the argument was not reasoning. It was a debugfs file:

```
pin 0 (gpio1): function func1   CLAIMED
```

and then the codec's own status register moving from dead to alive —
`EFUSE_STATUS 0x00 → 0x01`, zero RX overflows, the DAC drawing current. The
causal chain runs backwards cleanly: no func1 → no MCLK → efuse failure and
RX FIFO overflow → the chirping and the silence.

## Step 2 — a brake nobody released

Playback worked; capture still produced exact zero. Two independent faults, both
of the same kind: **something is applied and never unapplied, or requested and
never delivered.**

**The TX front-end hold.** `wcd9335_codec_enable_adc()` sets a hold on the input
stage in `PRE_PMU`. The vendor kernel releases it 300 ms later from a delayed
work item that never went upstream, so mainline sets it and never lets go. It
was visible live during a recording — register `0x0613` reading `0x40` — and the
decimator downstream produced exact zero.

There is a DAPM ordering trap in the fix. Releasing it from the decimator's
`POST_PMU` does not work: DAPM powers the mux widgets (sequence 5) *before* the
ADC widgets (sequence 9), so the release runs before the thing it is releasing
is up. The right place is the **ADC widget's `POST_PMU`**, and the event has to
be added to all six ADC widgets.

**The clock that was never routed to the microphones.** The `MCLK` DAPM supply
has no codec-internal route; the board has to draw it. Only `"RX_BIAS", "MCLK"`
existed, so the capture path had no clock. Two lines fixed it: `"AMIC2", "MCLK"`
and `"AMIC5", "MCLK"`.

And then, with all three faults fixed, the microphone still measured as nothing
— because `ADC2 Volume` sat at 0 and pushed the signal below the least
significant bit. **The fix was right and the measurement still said no.**

## Step 3 — the pattern, and what actually ended arguments

All three faults are the same shape, and none of them announces itself. That is
why the search went *downward* for so long, toward the proprietary bus and the
signed firmware: those look like where a hard problem lives. A pin state named
`"active"` instead of `"default"` does not look like anywhere.

What ended each argument was never reasoning — it was asking the hardware. A
status register reading `0x01` instead of `0x00`. A debugfs line confirming a
pin is claimed. One bit visibly stuck mid-recording.

The same applies to the measurements themselves. *"The headset microphone does
not work"* was true for a long time and then turned out to be an artefact of how
it was tested: changing the mux mid-stream skips the ADC power sequence. Set the
route **before** the stream, with the source suspended, and it reads `0x00` and
records at full level. A good deal of debugging is discovering you were holding
the instrument wrong.

## Step 4 — headset detection did not exist

Mainline's WCD9335 has **zero** jack detection. The input device exists and is
dead. The 2018 Kandagatla MBHC series was never merged, so it was ported — and
then adapted, because a straight port does not work on this board. Four things
had to be true at once:

1. **The codec creates its own jack.** The generic machine driver attaches the
   jack to the MI2S link (the AW8898), so the SLIMbus WCD9335 never receives one
   through `.set_jack` — proven by a diagnostic that never fired. The codec
   creates it in its own probe instead.
2. **Direction is a software toggle, not a register.** `RESULT_3` bit 3 reads 0
   throughout the active-detection window after an edge — including on removal,
   where it therefore looks like an insertion — and `MECH_DETECT_TYPE` is
   unreliable when read back. The handler flips a boolean on each edge and
   reports direction from that.
3. **`MECH_DETECT_TYPE` must be written on every edge anyway** — not for the
   direction but to **re-arm L_DET**, which detects one direction at a time.
   Without it, removal fires no interrupt at all and the driver sticks on
   "inserted".
4. **Seed the state at init** from the settled `RESULT_3` after a 300 ms wait,
   so a headset already plugged in at boot is handled.

Verified over 14 edges and 6 cycles without drift. Note which input device is
which: the codec's own jack is `event5`, created first in the probe; `event6` is
the dead machine-driver one.

**All four of those points were superseded on 2026-07-31, and the second one was
wrong.** The codec was moved onto the kernel's *shared* `wcd-mbhc-v2`, with a new
legacy comparator backend added to it because this codec has no MBHC ADC. Points
1 and 3 survive as facts about the hardware; point 2 does not — `MECH_DETECTION_TYPE`
is exactly what the shared code takes the direction from, and it is reliable.
Point 4 became unnecessary, because nothing stores an insert state any more.

The reason the earlier reading looked solid is worth keeping: **every one of
those measurements was taken under this port's own incomplete MBHC init.** With
the register setup the shared code performs, `RESULT_3` follows the socket
(`0x10` empty, `0x00` plugged) where before it sat at `0x08` either way. Two
rounds concluded "the hardware cannot do this" from an instrument that had never
been switched on properly. The full record, including what is still *not*
established about `RESULT_3`, is in [`jack/`](jack/) and the settled description
is in [`../README.md`](../README.md#the-headset-jack).

## Step 5 — call audio, and a week undone by one sentence

Call audio was declared, in permanent notes, to be blocked on a deep hole in
mainline support: *"the modem↔LPASS voice bridge does not work; not a weekend
fix; do not burn more paid calls on it."* The reasoning was long and the evidence
was live.

It was wrong, and what demolished it was the person holding the phone saying,
offhand, *"but calls used to work on the speaker."*

They had. **Every live test in that investigation had run over the earpiece —
the wrong path.** On speakerphone, `QUIN_MI2S_RX → AW8898`, the remote party's
voice comes out of the phone. The bridge was never dead.

What was actually true is narrower and fixable, and it took two more corrections
to reach:

* First correction: the theory that q6voice opens the AFE port directly without
  triggering the codec's SLIMbus DAI. Also wrong — with the `Voice Call` UCM verb
  applied, the whole chain builds, `q6voice → SLIMBUS_0_RX/TX → codec AIF1 →
  EAR/EAR PA` and `DMIC0 → SLIM TX0 → AIF1 CAP`, with zero kernel errors and no
  kernel fix. **The missing piece was userspace**: `VoiceCall.conf` was not
  installed, and the master config registered only the `HiFi` verb, so the verb
  was unreachable.
* Second: the daemon. Upstream `q6voiced` calls `open` + `set_params` +
  `prepare` and **never `snd_pcm_start`**, so the ASoC front end sits in
  `prepare` and DPCM never triggers the backends. And the playback leg cannot be
  started at all on its own — a voice PCM carries no data, and the ALSA core
  returns `-EPIPE` for an empty playback buffer unless `stop_threshold` is set to
  `boundary`.

With a patched `q6voiced` and the verb registered, all three paths work live:
earpiece with handset mic, headset with headset mic, and speakerphone.

The ground truth for debugging any of it is one file:

```
cat "/sys/kernel/debug/asoc/Fairphone 3/VoiceMMode1/state"
```

Both directions **and** the backend must read `State: start`.

## Step 6 — the framer pokes, kept for four days for no reason

The last thing to go was a workaround that had been in for four days. Its full
account is in [`qdsp6ss-framer-poke.md`](qdsp6ss-framer-poke.md); the short
version belongs here because it is the same lesson as everything above.

Two commits wrote QDSP6SS `0x0c20002c` bit 3 on every boot to make the SLIMbus
framer answer. They were written on 2026-07-25, when audio was silent and a 2025
LKML thread pointed at that exact register. Audio worked afterwards. They were
kept — not because either was shown to be the reason, but because they were
present when it started working.

Reverted on 2026-07-29, four days later: the PAS-side one **never wrote
anything** (`0x101 → 0x101`; by the time it runs the bit is already clear), and
with both removed the codec comes up and a 1 kHz tone crosses SLIMbus in both
directions across eight cold boots, identically to eight cold boots with them.

Four days is short, and that is the point rather than an excuse. The reasoning
that kept them — *it works now, and this was the last thing changed* — does not
get better with time; a workaround that survives its first week survives its
first year the same way.

## Traps worth carrying forward

| trap | what it looks like |
|---|---|
| **A half-configured raw mixer** | `ADSP_EALREADY` on AFE `DEVICE_START`, which reads as "audio broke". Always measure from a UCM verb, never from hand-set controls |
| **`kill -9` on a test harness** | skips the UCM `DisableSequence`, leaving the front end with two backends → `hw_params -22`. Set `_verb HiFi` before switching verbs |
| **A headset plugged in during an earpiece test** | the earpiece test looks silent because `EAR` is driven and `HPHL` is not |
| **Two sessions touching the card** | a parallel self-test run left both RX voice mixers at 1 and held the capture. Serialise anything that touches the card during a live call test |
| **Editing a UCM file under a running PulseAudio** | the sequences are read when the card loads; `pulseaudio -k` is mandatory afterwards |
| **The greeter's own PulseAudio** | while the screen is locked, `pactl` aimed at the user's runtime directory talks to an autospawned empty daemon — which looks exactly like "the card lost its sink" |
| **Raw `pkill` to take the card** | the sound server returns within seconds and reconfigures the mixer, so the measurement reports whatever it left behind. Use the suite's `audio_grab` |
| **Speaker checks are not SLIMbus checks** | `21-audio-acoustic` and `22-audio-headset` play through QUIN_MI2S and the AW8898. Only [`23-audio-slimbus`](../../../tests/checks/23-audio-slimbus-test.sh) crosses the bus, in both directions |
