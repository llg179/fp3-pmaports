# FP3 camera userspace tooling

> ⚠️ **AI-generated.** This page and the tooling it describes were written by
> Claude (Opus 5) working under the direction of Lajosházi, László Gergely, who
> reviewed every change and made or reviewed every measurement it rests on.

What the kernel side does and what is measured live in
[`../docs/camera/README.md`](../docs/camera/README.md); how it was found out is
in [`../docs/camera/bringup/README.md`](../docs/camera/bringup/README.md). This
directory holds the two tools that need a scene in front of the lens — which is
why they are not part of the `fp3-selftest` battery — and the patches that make
a camera app usable on this phone.

## The patches

Neither is a device quirk: both fix something missing for every device of their
kind, and both are written to be offered upstream.

| patch | what it adds |
|---|---|
| [`libcamera/0101-simple-autofocus.patch`](libcamera/0101-simple-autofocus.patch) | contrast-detection **autofocus** for libcamera's `simple` pipeline: a sharpness statistic in the software ISP's existing stats pass, accumulated into a 5×5 zone grid; an `Af` algorithm in the simple IPA; and the focus lens plumbed through the way the IPU3 handler does it. Publishes `AfMode`, `AfTrigger`, `AfMetering`, `AfWindows` |
| [`libcamera/imx363.yaml`](libcamera/imx363.yaml) | the tuning file that turns `Af` on for this sensor |
| [`snapshot/0001-camera-inhibit-idle-while-viewfinder-active.patch`](snapshot/0001-camera-inhibit-idle-while-viewfinder-active.patch) | keeps the screen from blanking while the viewfinder is open, not only while recording ([GNOME/snapshot!461](https://gitlab.gnome.org/GNOME/snapshot/-/merge_requests/461)) |
| [`snapshot/0002-camera-zoom.patch`](snapshot/0002-camera-zoom.patch) | **zoom** by pinch, scroll wheel or double tap, on `camerabin`'s own `zoom` property, so the saved picture is zoomed exactly as it was framed |
| [`snapshot/0003-camera-viewfinder-resolution.patch`](snapshot/0003-camera-viewfinder-resolution.patch) | takes the picture at the **sensor's resolution** and previews at a smaller one, switching the source between them for the shot — the way Megapixels does it — and drops the preview a step when fewer than 20 fps actually arrive |
| [`snapshot/0004-camera-tap-to-focus.patch`](snapshot/0004-camera-tap-to-focus.patch) | an **autofocus switch** in the preferences; with it off, one tap focuses and two focus and shoot. Reaches the control by binding the PipeWire node directly, because `pipewiresrc` carries no camera controls |

They are applied by the `libcamera` and `snapshot` aports in the pmaports
checkout; the copies here are the source of truth for this port.

The `libcamera` aport needs two more changes, which are not patches:
`mesa-dev` in `makedepends` and `-Dsoftisp-gpu=enabled` in `build()`. Without
them libcamera builds only the CPU debayer, which **centre-crops** instead of
scaling — a 1920×1080 preview then shows less than half the sensor's width, and
looks like a camera stuck at 3× zoom.

☠️ **After upgrading libcamera, restart the PipeWire stack.** A running
`wireplumber` holds the old library while the new IPA is loaded from disk, and
the mismatch shows up as *"no camera found"* in every app —
`systemctl --user restart wireplumber pipewire` fixes it.

## The tools

| tool | what it answers |
|---|---|
| [`focus-sweep.py`](focus-sweep.py) | does the lens move, and where in the control range this scene comes into focus — headless, prints numbers |
| [`focus-view.py`](focus-view.py) | what the lens is doing *right now*, to a human — a live viewfinder with a focus slider, the same sharpness number, and zoom |

Both open `/dev/video0` **exclusively**, so they cannot run at the same time as
each other or alongside a camera app.

## `focus-sweep.py`

Steps `V4L2_CID_FOCUS_ABSOLUTE` across a range and scores each position for
sharpness. Run it on the device, pointed at something with detail:

```sh
focus-sweep.py                                 # full range, 9 positions, 4 passes
focus-sweep.py --lo 280 --hi 480 --passes 6    # zoom in on the peak
focus-sweep.py --steps 17 --keep /tmp/sweep
```

A working actuator produces a curve with a single interior peak; it prints every
pass, the spread within each position and the drift between passes, so the
verdict can be checked instead of taken.

☠️ **Two properties of the method are load-bearing, and each one cost a
confidently wrong answer on this phone:**

- **One capture is held open for the whole run.** Restarting the stream per
  position resets auto-exposure and injects a settling transient as large as the
  effect being measured. That produced "the lens does not move" from a lens that
  moves.
- **The positions are visited in interleaved passes of alternating direction.**
  A single ordered walk confounds position with time, and anything drifting
  during the run comes out as a smooth curve that looks like one side of a peak.
  That produced "the lens moves" before it had been shown to.

Two things about the metric worth knowing before trusting a number from it:

- ☠️ **The gradient is taken between pixel *x* and *x+2*, never between
  neighbours.** The frames are raw Bayer, so adjacent pixels are different
  colour planes and their difference measures the scene's colour rather than the
  focus. That mistake produces a large, stable, entirely meaningless number.
- **Only the high byte of each pixel is used.** Frames arrive MIPI-packed
  (`pRAA`): four pixels in five bytes, the fifth holding their low bits.
  Dropping it costs two bits and buys a large speed-up on a 15 MB frame.

The lens subdev is found by looking for the control, never by device index — the
`/dev/v4l-subdev*` numbering moves between boots.

## `focus-view.py`

A viewfinder that owns the camera itself: a GTK4 window with a focus slider
(plus ±1/±10 buttons), the sharpness number the sweep uses printed live, a 1–16×
zoom by slider or pinch, a cheap demosaic and a rotate button.

```sh
# from an SSH session, so it survives the session closing
systemd-run --user --unit=focus-view /usr/bin/python3 ./focus-view.py
systemctl --user stop focus-view
```

It exists because the two other instruments each answered half the question: the
sweep measures well but shows nothing, so a null result is hard to trust, and a
camera app shows a picture but scales it down far enough to hide the change. The
focus effect on this phone was invisible at 1× and obvious at 8×.

What it is **not** is a camera app: it debayers by taking one 2×2 RGGB quad per
output pixel (half resolution, no interpolation), white-balances by grey world
and applies a fixed gamma. That is deliberately the cheapest correct pipeline
that still shows detail honestly — the picture a proper camera app produces goes
through libcamera's software ISP instead and will not match it.
