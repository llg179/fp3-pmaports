# FP3 userspace audio (pulseaudio)

The kernel work makes the WCD9335 codec play and capture; this is the userspace
half that makes it work through **pulseaudio**, so audio comes out of apps and
not just `aplay`/`arecord`. Verified end-to-end on postmarketOS 7.0.9 (phosh,
pulseaudio 17, alsa-lib 1.2.16): speaker playback and the built-in handset
microphone both work through pulseaudio, surviving a cold reboot.

## What's here

```
ucm2/conf.d/Fairphone_3/Fairphone_3.conf   -> /usr/share/alsa/ucm2/conf.d/Fairphone_3/
ucm2/Fairphone/fp3/HiFi.conf               -> /usr/share/alsa/ucm2/Fairphone/fp3/
ucm2/Fairphone/fp3/VoiceCall.conf          -> /usr/share/alsa/ucm2/Fairphone/fp3/   (call routing; registered in the master conf)
pulse/90-fp3-mic.pa                         -> /etc/pulse/default.pa.d/
systemd/fp3-mic-select                      -> /usr/local/bin/
systemd/fp3-mic-select.service             -> /etc/systemd/system/   (systemctl enable)
```

## Why it is not just a UCM file

Three things about this card fight the obvious "one HiFi verb with Speaker,
Earpiece, Headphones, Mic and Headset devices" approach. Each was found the hard
way, so they are written down.

### 1. pulseaudio's UCM layer can only wrap PCM **device 0** on this card

pulseaudio opens a UCM device's PCM through an alsa-lib wrapper named
`_ucm0001.hw:<card>,<dev>`. On the FP3 card that wrapper resolves **only for
device 0**; for device 1 or 2 it fails with

```
(alsa-lib)pcm.c: Unknown PCM _ucm0001.hw:F3,1
```

even though `aplay -D hw:0,1` / `hw:0,2` open fine. A single capture (or second
playback) SectionDevice on device 1/2 therefore makes pulseaudio drop the whole
card ("Failed to find a working profile") and fall back to a null sink.

**Consequence for playback:** all three outputs are put on **MultiMedia1
(device 0)** and selected by the ADSP front-end mixer instead of by PCM number:
`QUIN_MI2S_RX` for the speaker (AW8898), `SLIMBUS_0_RX` for the codec earpiece /
headphones. pulseaudio exposes them as separate profiles on the one card.

**Consequence for capture:** capture (MultiMedia2, device 1) cannot be a UCM
device at all. It is exposed instead as a plain `module-alsa-source` on
`hw:0,1` (`pulse/90-fp3-mic.pa`), which opens the raw device happily. The codec
capture routing is set by the HiFi verb (see below).

### 2. a q6asm front-end PCM can't be opened until it is routed

pulseaudio probes a profile by opening the PCM after running only the **verb's**
EnableSequence — not the device's. A qdsp6 front-end (MultiMedia1) returns
`EINVAL` on open until a mixer routes it to a backend, so if the verb leaves
MultiMedia1 unrouted every probe fails. The verb therefore leaves MultiMedia1 on
the speaker backend (`QUIN_MI2S_RX Audio Mixer MultiMedia1 1`); each output
device then swaps the backend. The verb also pre-routes the handset mic
(`DMIC0 -> DEC0 -> SLIMBUS_0_TX`) so the `module-alsa-source` has signal.

### 3. the two mics are selected manually, and only while capture is idle

The headset microphone (AMIC2) and the built-in handset mic (DMIC0) share the
codec's decimator 0, so only one is active at a time. Two things stop this from
being automatic:

  - **jack detection does not work.** mainline WCD9335 has no working MBHC on
    this board, so the `Mic Jack` / `Headphone Jack` controls stay `off` even
    with a headset plugged. There is no event to switch on.

  - **the mux must be changed while the capture is idle.** Re-applying the
    input mux while a capture stream is *live* does not re-run the ADC widget's
    power sequence, so the TX front-end hold is never released and the decimator
    stays at digital silence (register 0x613 stuck at 0x40). The pulse source is
    suspended between recordings, so setting the mux then and letting the next
    recording power the ADC up cleanly is what works.

So the mic is chosen with `fp3-mic-select handset|headset`, which sets the input
mux and remembers the choice; `fp3-mic-select.service` re-applies it at boot.
Both mics are verified working through pulseaudio this way (handset and headset
each pick up a 1 kHz speaker tone at a ~1000x bin ratio). Wiring this to real
jack detection needs MBHC support in the wcd9335 driver, which mainline lacks.

## Status

| path | state |
|---|---|
| Speaker playback | works through pulseaudio (verified, cold-boot) |
| Earpiece / Headphones playback | routed and openable; separate card profiles |
| Handset microphone (DMIC0) | works through pulseaudio as `fp3-handset-mic` (verified) |
| Headset microphone (AMIC2) | works through pulseaudio, selected with `fp3-mic-select headset` (verified acoustically); no auto jack detection |
| Voice call | **works, verified with live calls** — earpiece + handset mic, headset + headset mic, and speakerphone (Quinary MI2S). Needs the `Voice Call` verb *and* the patched `q6voiced` (see below); pulseaudio still cannot own the voice PCM, callaudiod integration is the remaining piece |


## Voice calls (what actually makes them audible)

Live-call verified on postmarketOS with kernel `integration/7.1.3`. Three things
have to line up; miss any one and the call is silent:

1. **The `Voice Call` UCM verb must be installed *and registered*.** Shipping
   `VoiceCall.conf` is not enough — `ucm2/conf.d/Fairphone_3/Fairphone_3.conf`
   has to list it, otherwise `alsaucm set _verb "Voice Call"` cannot find it.

   ```sh
   alsaucm -c Fairphone_3 set _verb "Voice Call" set _enadev Earpiece   set _enadev Mic
   alsaucm -c Fairphone_3 set _verb "Voice Call" set _enadev Headphones set _enadev Headset
   alsaucm -c Fairphone_3 set _verb "Voice Call" set _enadev Speaker    set _enadev Mic
   ```

2. **The voice PCM (`hw:0,4`) must be *started*, not just prepared.** Upstream
   `q6voiced` only opens + prepares it, so the ASoC frontend stays in the
   `prepare` state, DPCM never triggers the backends, and no codec/amplifier DAI
   ever starts. The playback direction additionally needs XRUN detection off
   (`stop_threshold = boundary`), because the voice PCM carries no data and the
   ALSA core refuses to start an empty playback stream (`-EPIPE`). The patched
   package in `../q6voiced/` does both.

3. **Nothing else may hold the card.** pulseaudio and callaudiod must not own
   `hw:0,4` while the call runs.

Ground truth while debugging is the DPCM state file — both directions and both
backends must read `start`:

```sh
cat "/sys/kernel/debug/asoc/Fairphone 3/VoiceMMode1/state"
```

Traps that cost real debugging time:

* With a headset plugged in, an `Earpiece` test *sounds* silent — the codec
  routes to `EAR`/`EAR PA` while `HPHL` stays off. Check the DAPM widgets.
* Killing a test harness with `SIGKILL` skips the UCM `DisableSequence`, so the
  previous device stays in the graph. The next verb then gives the frontend two
  backends, `hw_params` fails with `-22`, and the AFE port reports
  `ADSP_EALREADY` — which looks exactly like "the downlink broke again". Reset
  with `alsaucm set _verb HiFi` first.

## Installing

```sh
sudo cp -r ucm2/* /usr/share/alsa/ucm2/
sudo install -m644 pulse/90-fp3-mic.pa          /etc/pulse/default.pa.d/
sudo install -m755 systemd/fp3-mic-select       /usr/local/bin/
sudo install -m644 systemd/fp3-mic-select.service /etc/systemd/system/
sudo systemctl enable fp3-mic-select.service
# restart the audio server (or reboot) to pick up the card profile
# pick the mic (remembered across reboots):
sudo fp3-mic-select handset   # or: headset
```

The card is matched by its longname "Fairphone 3" (the conf.d directory is
`Fairphone_3`), not by the short id "F3".
