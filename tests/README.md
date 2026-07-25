# fp3-selftest — functional regression battery

Run this after every kernel bump, so that "everything still works" is a
repeatable measurement instead of a memory.

The suite exists because of a specific near-miss: a missing DAPM route
(`SLIMBUS_0_RX` ← `SLIMBUS_0_RX Voice Mixer`) made the voice-call PCM impossible
to open, and nothing in a manual pass would have caught it — playback and
capture both still worked, only telephony was dead. `30-voice` encodes exactly
that regression so it cannot come back silently.

## Invocation

```sh
export FP3_PW=…            # device password — never stored in this repo
# (no PIN needed: the cold unlock is measured passively, you type it yourself)

# the canonical run
./tests/fp3-selftest --no-cable --no-bt

# the cold unlock is a three-step measurement, see below
./tests/fp3-selftest --arm-unlock          # then reboot, then unlock the phone
./tests/fp3-selftest --cold-unlock --only unlock

# before flashing a build, with no device involved at all
./tests/fp3-selftest --preflight-apk ~/…/linux-fp3-709-7.0.9-r4.apk
```

The battery takes several minutes and the suspend check drops the USB link, so
run it detached and poll the log rather than in one foreground call:

```sh
nohup ./tests/fp3-selftest --no-cable --no-bt > /tmp/selftest.log 2>&1 &
until grep -qE '^(PASS|FAIL) - ' /tmp/selftest.log; do sleep 15; done
```

## What each check proves

| check | proves |
|---|---|
| `01-identity` | the running kernel is the one you think you are testing — build stamp, package version, source commit, device model. Blocks everything else, and reports **all four** results rather than stopping at the first |
| `03-unlock-latency` | how long phosh takes to start on a cold unlock — and, once the session is pre-warmed, that it no longer starts at all |
| `05-modules` | required modules built; module tree matches the package; no hot-swap leftovers |
| `10-health` | no panic/oops/BUG/remoteproc crash; rootfs has room; no new failed units |
| `15-hwtest` | display, input devices, camera presence and vibrator against a recorded reference |
| `20-audio` | codec enumerated on SLIMbus, playback and capture PCMs open |
| `21/22-audio-*` | a tone on the speaker reaches the handset/headset mic (`--acoustic`) |
| `30-voice` | the VoiceMMode1 path routes and opens — **the regression this suite was built for** |
| `35-pulse` | userspace has a real sink and the handset mic — also proves the audio checks put the sound server back |
| `40-camera` | the sensor is not merely probed but linked into CAMSS |
| `50-charger` | the charger reports sane values **and current actually flows** |
| `60/65/70` | wifi connected, bluetooth powered, modem registered |
| `99-suspend` | suspend and RTC wake. Runs last and detached — resuming re-enumerates USB and drops the link every time |

## Rules the suite enforces

**Every failure blocks.** There is no xfail or TODO list. A subsystem that is
mid-bring-up fails until it works, and then goes green on its own. The camera is
in exactly that state today.

**An untested category cannot read as green.** `checks/CATEGORIES` lists the
`fp3-integration` topic categories, and the runner guards both directions: every
listed category must have a check, and every `fp3-7.0.9-*` branch on the fork
must be listed. If a check is skipped, its category is reported uncovered and
the run does not pass without `--allow-uncovered CAT`.

**The cold unlock cannot be measured over SSH.** Logging in as the user starts
the very `systemd --user` session whose cold start is being timed. So the probe
runs from a boot-time unit instead: `--arm-unlock`, reboot, unlock the phone with
nobody connected, then `--cold-unlock` judges the recorded trace.

## Adding a check

Drop a `NN-name-test.sh` in `checks/`. POSIX sh, exit code is the verdict,
output lines prefixed `PASS:`/`FAIL:`/`SKIP:` — the postmarketOS
`postmarketos-test` convention, so a check could move into a device `pmtest`
subpackage later without rewriting. Declare metadata in header comments:

```sh
# Category: voice      # counts towards topic-branch coverage
# Requires: modem      # skipped by --no-modem
# ColdPhase: unlock    # judges a trace recorded at the previous boot
# Detached: yes        # will drop the link; run detached and read the result file
```

The number decides the order, and the order is deliberate: cold checks early,
the audio block together, suspend last.

## Measured traps (do not rediscover these)

- **`aplay --dump-hw-params` always exits 1.** It aborts the open once it has
  printed the parameters, so its exit code is not an open/fail signal. Use a
  real one-second open of `/dev/zero` — that is silent and costs nothing.
- **The sound server holds the card**, and whether a second open gets EBUSY
  depends on whether the sink happens to be suspended at that instant. Any raw
  ALSA work must go through `audio_grab` in `lib/audio-state.sh`.
- **`amixer` needs `-D hw:0`.** ALSA's `default` device routes through
  PulseAudio, so once the sound server is stopped every plain `amixer` call dies
  with "Connection refused" — which looks exactly like a missing control and
  sends you hunting a kernel regression that is not there.
- **There is no `pulseaudio` systemd unit here**; the process calling itself
  pulseaudio is pipewire-pulse. Stop `wireplumber.service pipewire.service
  pipewire.socket`.
- **busybox `ps` has no `-C`.** Using it returns nothing silently, which made
  the sound-server detection report "not running" and skip the stop entirely.
- **`hwtest` needs root**, and its reference cannot live in `/tmp`:
  `fs.protected_regular` stops root writing over another user's file in a sticky
  directory. Installing it also pulls 13 packages and regenerates `/boot`.
- **The sudo prompt has no trailing newline**, so it prepends itself to the
  first line of output. Send it to `/dev/null`; filtering it with `grep` deletes
  that line *including* your own first line of output.

## Why not just use hwtest?

We measured it rather than assuming. It runs headless, `--verify` returns 1 on a
regression, and it covers framebuffer, DRM, camera presence, vibrator and every
input device — so `15-hwtest` uses it for exactly that slice instead of
reimplementing it. It does not cover audio function, the voice path, the modem,
wifi, bluetooth, the charger, kernel health, modules or identity, which is what
the rest of the checks are for.

## Baselines

`baseline/` holds the things a check compares against. `modules-required.txt` is
maintained **by hand** on purpose — auto-generating it from a build would defeat
its only job, which is noticing that something stopped being built.
`failed-units.txt` and `dmesg-allow.txt` are deliberate, reviewable exceptions:
every line is a fault we have decided to stop looking at, so an unjustified
entry can hide a real regression for months.

The `hwtest` reference lives on the device at
`/var/lib/fp3-selftest/hwtest-reference.ini`. Export it from a state you consider
good, then edit it so components that *should* work read `True` even if they are
broken today — otherwise the breakage becomes the baseline and stops being
reported.

## What the cold unlock actually is

Worth knowing before optimising it: on this device a cold unlock is not a
lockscreen being dismissed. phosh is not running at all. The phone sits at the
greetd/phrog greeter as uid 113, and authenticating starts an entire user
session from scratch. Of the ~15s a human perceives, roughly 7s is
authentication and session setup before phosh exists, and ~8.4s is phosh
starting up to idle (measured 2026-07-25).

`loginctl show-user fp3 -p Linger` is `no`, so nothing of the session exists
before login. That is the lever: pre-warm the session and the cold path stops
paying for it — at which point `03-unlock-latency` passes because phosh is
already running when you unlock, rather than because it started quickly.

### Rejected end markers

The "home screen is up" signal was chosen by measurement, not assumption:

- **phosh CPU time going quiet — chosen.** During startup its deltas run to tens
  or hundreds of jiffies per sample; at idle they are exactly +1. Sharp, passive,
  no tooling.
- **Queued `systemd --user` jobs — disqualified, and instructively so.** Asking
  for them with `systemctl -M user@ --user list-jobs` *starts the user manager*.
  The probe causes what it observes.
- **MDSS/DSI interrupts as a page-flip proxy — never settles.** The display keeps
  refreshing at ~15 interrupts per sample forever, so there is no quiet to find.

### Why there is no screenshot anywhere in this suite

Every capture path on this device fails: `grim`/wlr-screencopy gets "no supported
format found" from phoc, the gnome-shell Screenshot D-Bus method returns false,
`/dev/fb0` reads all-zero even with the display awake and rendering
(`bl_power=0`, `dpms=On`, `blank` stuck at 4 — fbdev emulation is not wired to
the compositor), and xdg-desktop-portal is interactive and needs a user session
the greeter does not have. Where UI evidence is needed, D-Bus object state is
the substitute — a `/org/gnome/Calls/window/N` object, for instance, is a claim
about what is on screen rather than a log line about what was logged.
