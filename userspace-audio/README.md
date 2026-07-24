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
ucm2/Fairphone/fp3/VoiceCall.conf          -> /usr/share/alsa/ucm2/Fairphone/fp3/   (call routing, not wired to pulse yet)
pulse/90-fp3-mic.pa                         -> /etc/pulse/default.pa.d/
systemd/fp3-mic-jack.sh                     -> /usr/local/bin/
systemd/fp3-mic-jack.service               -> /etc/systemd/system/   (systemctl enable --now)
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

### 3. re-applying a mux while capture runs glitches it silent

The headset microphone (AMIC2) and the handset mic (DMIC0) share the one capture
device, so they are swapped by jack detection rather than being two sources.
`fp3-mic-jack.service` watches `alsactl monitor` and flips `ADC MUX0` between
`DMIC`/`DMIC0` and `AMIC`/`ADC2` on the `Mic Jack` control. It only writes the
mux on an **actual jack transition** — re-applying the same mux while a capture
stream is live re-runs the decimator's DAPM and drops it to digital silence, so
the state is tracked and left alone during normal use.

## Status

| path | state |
|---|---|
| Speaker playback | works through pulseaudio (verified, cold-boot) |
| Earpiece / Headphones playback | routed and openable; separate card profiles |
| Handset microphone (DMIC0) | works through pulseaudio as `fp3-handset-mic` (verified) |
| Headset microphone (AMIC2) | jack-switch service deployed; route validated earlier with a plugged headset, acoustic confirmation still needs the headset |
| Voice call | `VoiceCall.conf` has the SLIMbus voice-mixer routing; pulseaudio cannot open the voice PCM (hw:0,4) as an ordinary profile, so wiring calls needs callaudiod + a real call — not yet done |

## Installing

```sh
sudo cp -r ucm2/* /usr/share/alsa/ucm2/
sudo install -m644 pulse/90-fp3-mic.pa      /etc/pulse/default.pa.d/
sudo install -m755 systemd/fp3-mic-jack.sh  /usr/local/bin/
sudo install -m644 systemd/fp3-mic-jack.service /etc/systemd/system/
sudo systemctl enable --now fp3-mic-jack.service
# restart the audio server (or reboot) to pick up the card profile
```

The card is matched by its longname "Fairphone 3" (the conf.d directory is
`Fairphone_3`), not by the short id "F3".
