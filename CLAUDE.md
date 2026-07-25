# FP3 mainline port — repository map and working rules

Two repositories under `llg179` hold the Fairphone 3 (MSM8953/SDM632) mainline
port. Read this before changing either.

## The two repos

### `llg179/linux` — the kernel fork
A fork of upstream `msm8953-mainline/linux`. Upstream is remote `origin` and is
**never pushed to**. All FP3 work is published to remote `fork`
(`ssh://git@ssh.github.com:443/llg179/linux.git` — port 443, because plain SSH
port 22 stalls on this network).

Branches:

| branch | category | what it carries |
|---|---|---|
| `7.0.9/main` | base | tracks upstream 7.0.9; the base every topic branch forks from |
| `fp3-7.0.9-audio` | **audio** | WCD9335 SLIMbus codec: playback + microphone (codec routing, DAPM, pinmux, MBHC notes) |
| `fp3-7.0.9-voice` | **voice** | voice-call path: q6voice/q6cvp/q6cvs/q6mvm DAI, `q6voice-dai.c` routing (CS-Voice / VoiceMMode1 over SLIMbus) |
| `fp3-7.0.9-camera` | **camera** | IMX363 rear-camera bring-up |
| `fp3-7.0.9-charger` | **charger** | QCOM SMB2 (PMI632) charger: driver + DT |
| `fp3-integration` | (derived) | all categories combined; **this is what the kernel package builds** |

`fp3-integration` is a **linear branch built by cherry-picking** the topic-branch
commits (no merge commits). Every commit on a topic branch has a cherry-pick twin
on `fp3-integration`, and vice versa.

### `llg179/fp3-pmaports` — postmarketOS packaging + userspace (this repo)
Remote `origin` here **is** the user's repo, so pushing to `origin` is fine.

| path | what it is |
|---|---|
| `linux-fp3-709/` | the `linux-fp3-709` kernel APKBUILD, git-pinned to a `fp3-integration` commit via `_commit`. Mirror of `pmaports/device/testing/linux-fp3-709/`. |
| `userspace-audio/` | UCM (`ucm2/`), pulseaudio drop-ins, `fp3-mic-select`, voice-call config + helpers, install README |
| `README.md` | build + deploy instructions, branch table, the push-before-bump trap |

## The category rule (important)

**A change to `fp3-integration` must also land on the topic branch of its
category, and a change to a topic branch must be cherry-picked onto
`fp3-integration`.** The two must never diverge — integration is only ever the
sum of the topic branches. Concretely, for any kernel change:

1. Decide the category (audio / voice / camera / charger).
2. Commit it on that topic branch **and** cherry-pick it onto `fp3-integration`
   (order does not matter; both must end up with it).
3. Push both branches to `fork`.
4. Only then bump `_commit` in `linux-fp3-709/APKBUILD` to the new
   `fp3-integration` HEAD and `pkgrel`, run `pmbootstrap checksum`, and build.
   The APKBUILD fetches a GitHub tarball of `_commit`, so **the commit must be
   pushed before the checksum/build** or it fails with a 404.

### Where does the one-line `q6voice-dai.c` change go?
It adds the missing `{ "SLIMBUS_0_RX", NULL, "SLIMBUS_0_RX Voice Mixer" }` DAPM
route — that is the **voice-call** path, so it belongs on **`fp3-7.0.9-voice`**
(plus its cherry-pick twin on `fp3-integration`). It is *not* an
`fp3-7.0.9-audio` change: that branch is the codec/media audio (playback + mic),
while anything touching q6voice / CS-Voice / VoiceMMode1 / voice mixers is
`voice`.

## Authorship on every commit (both repos)
- Author: `Lajosházi, László Gergely <lajoshazilg@gmail.com>` with `Signed-off-by:`.
- Trailer: `Co-authored-by: Claude Opus 4.8 <noreply@anthropic.com>`.
- Kernel code comments are **English only** (public contribution).
