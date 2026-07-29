# FP3 userspace audio (pulseaudio)

The kernel work makes the WCD9335 codec play and capture; this is the userspace
half that makes it work through **pulseaudio**, so audio comes out of apps and
not just `aplay`/`arecord`. Verified end-to-end on postmarketOS 7.0.9 (phosh,
pulseaudio 17, alsa-lib 1.2.16): speaker playback and the built-in handset
microphone both work through pulseaudio, surviving a cold reboot.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who made every acoustic measurement the
> claims here rest on. How it was arrived at is in
> [`../docs/audio/bringup/`](../docs/audio/bringup/).

## What's here

```
ucm2/conf.d/Fairphone_3/Fairphone_3.conf   -> /usr/share/alsa/ucm2/conf.d/Fairphone_3/
ucm2/Fairphone/fp3/HiFi.conf               -> /usr/share/alsa/ucm2/Fairphone/fp3/
ucm2/Fairphone/fp3/VoiceCall.conf          -> /usr/share/alsa/ucm2/Fairphone/fp3/   (call routing; registered in the master conf)
pulse/90-fp3-mic.pa                         -> /etc/pulse/default.pa.d/
systemd/fp3-mic-select                      -> /usr/local/bin/
systemd/fp3-mic-select.service             -> /etc/systemd/system/   (systemctl enable)
udev/61-fp3-vibra.rules                    -> /etc/udev/rules.d/     (vibration permissions)
systemd/fp3-voiced                          -> /usr/local/bin/        (call audio daemon)
systemd/fp3-voiced.service                 -> /etc/systemd/system/   (systemctl enable, replaces q6voiced)
q6voiced-start-streams.patch                (not installed - a record, see the note in the file)
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

  - **jack detection had to be written first.** mainline WCD9335 has no MBHC
    at all; this port adds it, and only the `Headset Jack` control (and the
    matching input device) ever moves - `Mic Jack` and `Headphone Jack` are
    pins of the machine driver's jack that nothing reports into. During a call
    `fp3-voiced` follows the jack; for media capture the choice is still
    manual, see below.

  - **the mux must be changed while the capture is idle.** Re-applying the
    input mux while a capture stream is *live* does not re-run the ADC widget's
    power sequence, so the TX front-end hold is never released and the decimator
    stays at digital silence (register 0x613 stuck at 0x40). The pulse source is
    suspended between recordings, so setting the mux then and letting the next
    recording power the ADC up cleanly is what works.

So the mic is chosen with `fp3-mic-select handset|headset`, which sets the input
mux and remembers the choice; `fp3-mic-select.service` re-applies it at boot.
Both mics are verified working through pulseaudio this way (handset and headset
each pick up a 1 kHz speaker tone at a ~1000x bin ratio). Calls no longer need
this - the call daemon picks the input from the jack - but media capture still
does, because the mux may only be changed while the capture is idle.

## Status

| path | state |
|---|---|
| Speaker playback | works through pulseaudio (verified, cold-boot) |
| Earpiece / Headphones playback | routed and openable; separate card profiles |
| Handset microphone (DMIC0) | works through pulseaudio as `fp3-handset-mic` (verified) |
| Headset microphone (AMIC2) | works through pulseaudio, selected with `fp3-mic-select headset` (verified acoustically); no auto jack detection |
| Voice call | **works, verified with live calls** — earpiece + handset mic, headset + headset mic, and speakerphone (Quinary MI2S), with per-output volume, mute and the speakerphone button, and route changes in ~0.35 s. Driven by `fp3-voiced`, which takes the card from pulseaudio for the duration of the call and mirrors the volume onto the gain in the path |


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

2. **Something must drive the call.** `fp3-voiced` (in `systemd/`) does it: it
   watches ModemManager, applies the verb on `dialing`/`ringing-out`/`active`,
   opens *and starts* both legs of `hw:0,4`, and restores the HiFi verb when the
   call ends. It replaces `q6voiced` (`Conflicts=` in the unit) and does not use
   callaudiod, because callaudiod rejects this card outright with *"card has no
   usable source"* - our Voice Call profiles are sink-only, see above. A call
   driven by stock q6voiced + callaudiod is silent in both directions and leaves
   `q6voiced: Failed to open tx: Invalid argument` in the log: the routing was
   never applied, so the frontend had no backend.

3. **The voice PCM (`hw:0,4`) must be *started*, not just prepared.** Upstream
   `q6voiced` only opens + prepares it, so the ASoC frontend stays in the
   `prepare` state, DPCM never triggers the backends, and no codec/amplifier DAI
   ever starts. The playback direction additionally needs XRUN detection off
   (`stop_threshold = boundary`), because the voice PCM carries no data and the
   ALSA core refuses to start an empty playback stream (`-EPIPE`). `fp3-voiced`
   does both. (An earlier round patched upstream q6voiced instead; that aport is
   gone, but the patch is kept as `q6voiced-start-streams.patch` because the bug
   is not specific to this phone - see the note at the top of the file.)

   `q6voiced` itself stays installed either way: the device meta-package
   `soc-qcom-msm8953-modem` depends on it, so `apk del q6voiced` refuses. It is
   `disabled`, and `fp3-voiced.service` carries `Conflicts=q6voiced.service`, so
   nothing can start the two together.

4. **Nothing else may hold the card.** pulseaudio and callaudiod must not own
   `hw:0,4` while the call runs. `fp3-voiced` sets the card profile to `off`
   for the duration of the call and restores an available `HiFi` profile
   afterwards; merely suspending the streams is not enough, because any client
   that wants to play resumes them.

5. **Volume, mute and the speakerphone button** are applied by `fp3-voiced`:
   pulseaudio's sink volume is mirrored onto the control that is really in the
   path (`RX Volume` on speakerphone, `RX0`/`RX1`+`RX2 Mix Digital Volume`
   otherwise, each with its own range and its own remembered level), mute is
   the decimator gain `DEC0 Volume` - muting by re-routing kills this codec's
   capture path until the next reboot - and an output change is a full teardown
   and rebuild of the session.

Ground truth while debugging is the DPCM state file — both directions and both
backends must read `start`:

```sh
cat "/sys/kernel/debug/asoc/Fairphone 3/VoiceMMode1/state"
```

No ringtone on an incoming call is usually **not** an audio-path problem:
feedbackd ships a `quiet` profile on this image, which suppresses sound feedback
and leaves only vibration and the LED. Turn it on per user:

```sh
gsettings set org.sigxcpu.feedbackd profile 'full'
# verify: fbcli -E phone-incoming-call  should create a sink-input for ~4 s
```

There is no vibration either until `udev/61-fp3-vibra.rules` is installed:
feedbackd ships uaccess rules only for the vibrators it knows by name, and the
FP3's PMIC vibrator (`pm8xxx_vib_ffmemless`) is not among them, so the session
user cannot open it (`Failed to init vibra device: ... Permission denied`).

The ringtone itself comes from `sound-theme-freedesktop`
(`/usr/share/sounds/freedesktop/stereo/phone-incoming-call.oga`) and plays
through the ordinary HiFi sink - `fp3-voiced` only takes over when the call goes
`active`, so ringing is unaffected by the call routing.


### Headset detection, and what is still open

The codec reports the jack on two controls and only one of them moves here:

| control | meaning | on this board |
|---|---|---|
| `Headset Jack` | 4-pole plug, has a microphone | **the one that works** (codec MBHC) |
| `Headphone Jack` | 3-pole plug, no microphone | never fires - it is a pin of the machine driver's jack, which nothing reports into |
| `Mic Jack` | microphone-only accessory | same, never fires |

So every jack-aware UCM device names `Headset Jack`, and `fp3-voiced` reads the
codec's jack *input device* (`/dev/input/event*`, `SW_HEADPHONE_INSERT` /
`SW_MICROPHONE_INSERT`) rather than polling a mixer control. A
plugged jack means headset speaker plus headset microphone (AMIC2 on MIC BIAS2,
2.8 V - the built-in microphones are the digital DMIC0-3 instead).

**Open:** a 3-pole plug is also reported as `Headset Jack`, so the uplink would
be routed to a microphone that is not there. The classification belongs in the
codec's MBHC code, which already has a `SND_JACK_HEADPHONE` branch it never
reaches; deciding it needs the mic-bias load measurement. Until then, treat a
plugged jack as a headset.

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
