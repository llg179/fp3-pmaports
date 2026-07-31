# How audio works on this device

What carries the sound, which piece configures what, and the rules the
arrangement has to obey. For the driver changes behind it see
[`../kernel/README.md`](../kernel/README.md); for the device-tree nodes,
[`../device_tree/README.md`](../device_tree/README.md).

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who made every acoustic measurement the
> claims here rest on. How the arrangement was found — including the
> conclusions that had to be retracted — is in
> [`bringup/`](bringup/).

This describes the setup that works today: what carries the sound, which piece
configures what, and the rules the arrangement has to obey. Media playback and
capture go one way through the stack, a phone call goes another; both are
described below.

## The hardware decides the shape of the software

```mermaid
flowchart LR
    subgraph SoC["MSM8953 SoC"]
        CPU["CPU<br/>(Linux)"]
        ADSP["ADSP / Q6<br/>audio DSP"]
        MODEM["modem<br/>processor"]
    end
    WCD["WCD9335 codec"]
    AW["AW8898 amp"]
    EAR(["earpiece"])
    HPH(["headset"])
    MIC(["DMIC0 / AMIC2"])
    SPK(["speaker"])

    CPU -- "APR messages<br/>(control only)" --> ADSP
    ADSP -- "SLIMbus<br/>(audio data)" --> WCD
    ADSP -- "MI2S<br/>(audio data)" --> AW
    ADSP <-- "voice stream" --> MODEM
    WCD --> EAR
    WCD --> HPH
    MIC --> WCD
    AW --> SPK
```

The single most important fact: **audio data does not flow through the CPU.**
The ADSP moves it between the codec, the amplifier and the modem. Linux only
sends control messages ("start AFE port 0x4000", "create a voice session with
this RX and TX port"). Everything else follows from that: Linux and the DSP each
keep their own state, and every piece below exists to keep the two in agreement.

The earpiece, the headset and every microphone hang off the **WCD9335 on
SLIMbus**; only the loudspeaker is elsewhere, on the **AW8898 over Quinary
MI2S**. So a call routed to the earpiece and the same call on speakerphone use
two different buses and two different volume controls.

## The layers

```mermaid
flowchart TD
    APP["gnome-calls · media apps"]
    MM["ModemManager<br/>call states (D-Bus signals)"]
    FBD["feedbackd<br/>ringtone · vibra"]
    VD["fp3-voiced<br/>(this repo)"]
    PA["PulseAudio<br/>profiles · mixing · volume"]
    JACK["headset jack<br/>input device (evdev)"]
    UCM["ALSA UCM<br/>HiFi.conf · VoiceCall.conf"]
    LIB["alsa-lib<br/>snd_pcm_* · mixer"]
    ASOC["ASoC core<br/>DAPM graph + DPCM FE/BE"]
    CODEC["wcd9335 codec driver"]
    Q6["q6afe · q6asm · q6routing · q6voice<br/>(APR proxies to the DSP)"]
    SLIM["slimbus · qcom-ngd-ctrl"]
    DSP["ADSP sessions<br/>AFE ports · MVM/CVP"]

    APP -- "call buttons<br/>(D-Bus)" --> VD
    APP --> MM
    APP --> PA
    MM -- "call state" --> VD
    JACK -- "plug events" --> VD
    PA -- "volume events" --> VD
    FBD --> PA
    VD -- "Voice Call verb" --> UCM
    VD -- "opens hw:0,4" --> LIB
    VD -- "gains · mute · card profile" --> CODEC
    PA --> UCM
    PA --> LIB
    UCM --> LIB
    LIB --> ASOC
    ASOC --> CODEC
    ASOC --> Q6
    CODEC --> SLIM
    CODEC -- "MBHC" --> JACK
    Q6 -. "APR" .-> DSP
    SLIM -. "bus" .-> DSP
```

**1. Bus drivers** (`slimbus`, `qcom-ngd-ctrl`). The physical SLIMbus link to the
codec: register access and channel allocation.

**2. Codec driver** (`wcd9335.c`). Everything inside the chip: which microphone
feeds which decimator, which interpolator drives which output, the gain
registers, and headset detection (MBHC). This is where mixer controls like
`RX0 Mix Digital Volume`, `DEC0 Volume` and `DMIC MUX0` come from, and where the
`Headset Jack` switch is reported — both as a mixer control and as an input
device that publishes plug events.

**3. DSP proxies** (`q6afe`, `q6asm`, `q6routing`, `q6voice`). These move no
audio. They send APR commands to the ADSP: start an AFE port, create a voice
session (MVM/CVP) bound to an RX and a TX port.

**4. ASoC core — two state machines.**

* **DAPM** is the widget graph. Mixer controls open and close edges; a path that
  is complete *and* has a running stream gets powered. Ground truth lives in
  `/sys/kernel/debug/asoc/<card>/<component>/dapm/*` (`EAR PA: On`).
* **DPCM** pairs frontends with backends. `hw:0,0` (MultiMedia1) and `hw:0,4`
  (VoiceMMode1) are frontends; `SLIMBUS_0_RX/TX` and `Quinary MI2S` are
  backends. Opening a frontend starts whichever backends the DAPM graph says are
  connected. Ground truth: `/sys/kernel/debug/asoc/<card>/VoiceMMode1/state`.

**5. ALSA in userspace.** `alsa-lib` provides `snd_pcm_*` and the mixer; **UCM**
turns dozens of mixer writes into named use cases (`HiFi`, `Voice Call`) and
devices (`Earpiece`, `Speaker`, `Headphones`, `Mic`, `Headset`). UCM only sets
controls — it starts nothing.

**6. PulseAudio.** Loads the card, turns UCM verbs into card profiles, creates
sinks and sources, mixes applications and applies volume. It owns everything
that is *not* a call: media, notifications, and the ringtone.

**7. The daemons above it.** ModemManager owns the call state machine;
gnome-calls presses the in-call buttons over D-Bus; feedbackd plays the ringtone
and drives the vibrator; **`fp3-voiced`** (this repo) owns the call audio.

## The two paths

**Media** is the ordinary one: an app plays into PulseAudio, PulseAudio mixes it
into the sink that the active UCM device describes, and the stream reaches the
codec (or the amplifier) through `hw:0,0`. Volume is applied by PulseAudio on
the `PlaybackVolume` control named by the UCM device.

**A call** never passes through PulseAudio at all — the audio goes
modem ↔ ADSP ↔ codec, and the CPU's only job is to set the routing up and hold
the voice frontend open. That is `fp3-voiced`:

```mermaid
sequenceDiagram
    participant MM as ModemManager
    participant VD as fp3-voiced
    participant PA as PulseAudio
    participant UCM as ALSA UCM
    participant K as kernel / ADSP

    MM->>VD: call state becomes active (D-Bus signal)
    VD->>PA: suspend streams, set the card profile to "off"
    VD->>UCM: set _verb "Voice Call" + _enadev <output> <mic>
    UCM->>K: mixer writes — codec routing, amp, voice mixers
    VD->>K: apply this output's own gain
    VD->>K: open hw:0,4 playback + capture, XRUN off, start both
    K-->>VD: DPCM: one backend per direction, both "start"
    Note over VD,K: in call: a button, a plug or a volume key<br/>rebuilds the session in ~0.35 s
    MM->>VD: call terminated
    VD->>UCM: back to the HiFi verb
    VD->>PA: restore an available HiFi profile
```

## The headset jack

Detection is done by the WCD9335's MBHC block. Nothing about it comes from
upstream: the pre-port `sdm632-fairphone-fp3.dts` described the AW8898
loudspeaker and no codec at all, so there is no mainline reference for a jack on
this phone and every setting here is this port's own.

**How it works.** The codec's L_DET block raises an interrupt when a plug moves
in the socket. The driver keeps an insert state, seeded at probe from
`ANA_MBHC_RESULT_3` bit 3 and flipped on each interrupt, and reports it as
`SW_HEADPHONE_INSERT`. Whether the accessory has a microphone is decided
separately, from the button-0 transient a mic contact produces while sliding
past the ground ring during insertion: press *and* release seen means a headset,
press alone means plain headphones. That decides `SW_MICROPHONE_INSERT`, and
`fp3-voiced` picks the call's output and input from the two.

**The plug switches are normally open.** Qualcomm's device tree for this
hardware class — an external tasha codec on Quinary MI2S, which is this phone —
sets `qcom,msm-mbhc-hphl-swh = <1>` and `qcom,msm-mbhc-gnd-swh = <1>`, against
`<0>` for boards using the PMIC-internal codec. The equivalent properties are
set here to match.

**What is measured to work**, over repeated physical insert/remove cycles with
both a 3-pole and a 4-pole accessory:

- the boot value is right in both directions — plugged in at boot reads plugged,
  empty reads empty;
- no interrupt is lost: every physical event produced exactly one;
- headphones and headsets are told apart correctly every time.

**The known weakness** is that the insert state is a count rather than a
reading, so a single missed or spurious interrupt would invert it for the rest
of the boot. That has been observed in ordinary use but never reproduced
deliberately — neither boot, nor clean plug cycles, nor audio activity that
cycles the codec's power produced a stray edge.

**The count can probably be replaced, but it has not been yet.** `RESULT_3`
holds the outcome of the last completed detection, which is the state as it was
*before* the edge being handled — measured, agreeing on all nine edges of a
deliberate sequence. An interrupt means the state changed, so the answer is the
inverse of that reading, and no stored state is needed. Three variants built on
reading it failed, all of them computing the value without that inversion; the
corrected form is untested. There is no board jack-detect GPIO to fall back on,
unlike the msm8916/msm8953 boards using the PMIC-internal codec — established
from the device trees in the stock firmware, not merely from source.

The route taken to that conclusion, including the hypotheses that were
disproven and the tool that settled them, is in
[`bringup/jack/`](bringup/jack/).

## What each piece in this repo contributes

| path | what it does |
|---|---|
| `userspace-audio/ucm2/Fairphone/fp3/HiFi.conf` | media use case: the sinks and sources PulseAudio exposes, with their `PlaybackVolume` controls and the jack each one follows |
| `userspace-audio/ucm2/Fairphone/fp3/VoiceCall.conf` | the call use case: codec routing per output (`Earpiece`, `Speaker`, `Headphones`) and per input (`Mic`, `Headset`), plus the voice mixers. Every output also **drops the other outputs' routes and gains**, and the capture devices deliberately have **no `CapturePCM`** — the call's uplink is not a PulseAudio source |
| `userspace-audio/ucm2/conf.d/Fairphone_3/Fairphone_3.conf` | registers both verbs — a verb that is not listed here does not exist as far as PulseAudio is concerned |
| `userspace-audio/systemd/fp3-voiced` (+ `.service`) | the call-audio daemon described above. Replaces `q6voiced` (`Conflicts=`), which neither applies the routing nor starts the streams — and which stays installed regardless, because the `soc-qcom-msm8953-modem` meta-package depends on it |
| `userspace-audio/systemd/fp3-mic-select` (+ `.service`) | picks the built-in microphone for media capture at boot |
| `userspace-audio/pulse/90-fp3-mic.pa` | PulseAudio drop-in for the capture side |
| `userspace-audio/udev/61-fp3-vibra.rules` | tags `pm8xxx_vib_ffmemless` so feedbackd may use it — without it an incoming call is silent *and* still |
| `userspace-audio/q6voiced-start-streams.patch` | not installed: the fix an earlier round made to postmarketOS's `q6voiced`, kept because the bug it describes is not specific to this phone |

## The rules this arrangement obeys

These are the constraints that make the difference between a working call and a
silent one; each is enforced somewhere in the code above.

1. **The voice path configures the AFE port first.** Whoever starts a shared AFE
   port configures it; a later start only answers `ADSP_EALREADY` and gets the
   first one's configuration. So PulseAudio is asked to let go of the card
   *before* the Voice Call verb is applied.
2. **PulseAudio gives the card up for the duration of the call.** Suspending its
   streams is not enough — a suspended sink is resumed by any client that wants
   to play — so the card profile goes to `off` and is restored afterwards. It
   must never be handed a Voice Call profile: its media sink would open on the
   call's own SLIMbus backend.
3. **Volume is mirrored, not delegated, and is per output.** Because of rule 2,
   `fp3-voiced` applies the level to the gain that is really in the path:
   `RX Volume` (AW8898) on speakerphone, `RX0 Mix Digital Volume` for the
   earpiece, `RX1`+`RX2` for headphones — each with its own range, since +26 dB
   is comfortable against the ear and painful inside it. Every output keeps its
   own level, so plugging a headset into a loud speakerphone call is safe.
4. **The playback leg starts with XRUN detection off.** The voice PCM carries no
   data, so the ALSA core refuses to start an empty playback stream unless
   `stop_threshold` is set to the buffer boundary. Without this the downlink is
   silent while everything else looks correct.
5. **Changing the output is a full teardown.** The ADSP binds the voice session
   to the RX port it was given at creation, so a speakerphone toggle or a jack
   event goes back to the `HiFi` verb and builds the session again — measured at
   0.31–0.34 s end to end.
6. **Each UCM device cleans up after the others.** `alsaucm` is a fresh process
   every time it runs, with no memory of the device enabled before, so a
   `DisableSequence` never runs across invocations. Enabling an output therefore
   zeroes the other outputs' routes *and* gains itself; without that the voice
   frontend ends up with two backends and `hw_params` fails with `-22`.
7. **The microphone follows the jack, not the output**, and **mute is a gain, not
   a route**. A headset stays the input even on speakerphone. Muting by taking
   the microphone out of the DAPM graph silences it permanently on this codec —
   measured: the level goes to exactly zero and stays there for the rest of the
   boot, through a fresh PCM open and a full re-apply of the routing. `DEC0
   Volume` (a kernel control this port adds) is reversible.
8. **Everything is restored on the way out** — the `HiFi` verb and a HiFi profile
   PulseAudio reports as *available* — and the same cleanup runs at startup and
   periodically while idle, because the user's PulseAudio only appears when the
   phone is unlocked and comes back with whatever profile it remembered.
9. **Nothing is polled that the system publishes.** The jack is an input device,
   ModemManager signals call state on the system bus, and PulseAudio publishes
   volume changes: the daemon watches all three and asks nothing until something
   moves. Idle cost is about 0.1% of a CPU.

## Checking it works

| what to look at | what it should say |
|---|---|
| `journalctl -u fp3-voiced -b` | the call state, `call audio up (<output> + <mic>)`, and a `dpcm:` snapshot every ten seconds |
| `/sys/kernel/debug/asoc/<card>/VoiceMMode1/state` | exactly one backend per direction, both `start` (`Quinary MI2S` on speakerphone, `SLIM Playback` otherwise) |
| `dmesg` | no `AFE enable ... failed` |
| `pactl list cards \| grep 'Active Profile'` | a `HiFi` profile whenever no call is up — never `off`, never `Voice Call` |
| `gsettings get org.sigxcpu.feedbackd profile` | `full` — `quiet` mutes the ringtone |
| `amixer -c 0 cget name='RX0 Mix Digital Volume'` | tracks the volume keys during an earpiece call |

## How it was arrived at

This page describes the working arrangement. How that arrangement was found —
what was believed at each step, what was measured, and the several confident
conclusions that had to be retracted — is a separate document:

* [`bringup/README.md`](bringup/README.md) — the narrative, with the
  instruments and the two-sided register dumps that produced it
* [`bringup/qdsp6ss-framer-poke.md`](bringup/qdsp6ss-framer-poke.md) — the
  QDSP6SS register the kernel wrote on every boot to make the SLIMbus framer
  answer, why it looked necessary, and the measurement that retired it
  (removed 2026-07-29)

After editing any UCM file, restart PulseAudio (`pulseaudio -k`) — it reads the
sequences when it loads the card, so a running instance still applies the old
ones. And note that while the screen is locked the *greeter* runs its own
PulseAudio: a `pactl` aimed at the user's runtime directory then talks to an
autospawned empty daemon, which looks exactly like "the card lost its sink".
