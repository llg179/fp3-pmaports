# FP3 camera userspace tooling

> ⚠️ **AI-generated.** This page and the tooling it describes were written by
> Claude (Opus 5) working under the direction of Lajosházi, László Gergely, who
> reviewed every change and made or reviewed every measurement it rests on.

What the kernel side does, what is measured and what is still open live in
[`../docs/camera/README.md`](../docs/camera/README.md). This directory holds only
the tools that need a scene in front of the lens, which is why they are not part
of the `fp3-selftest` battery.

| tool | what it answers |
|---|---|
| `focus-sweep.py` | does the lens actually move, and which end of the control range is near focus |

## `focus-sweep.py`

Steps `V4L2_CID_FOCUS_ABSOLUTE` across its range, captures a frame at each
position and scores it for sharpness. Run it on the device, pointed at something
with detail at a known distance:

```sh
focus-sweep.py                       # 9 positions over the full range
focus-sweep.py --steps 17 --keep /tmp/sweep
```

A working actuator produces a curve with a single interior peak. A flat curve
means the lens is not moving, which is a real possible outcome: the actuator's
direction and usable travel were read out of a vendor blob and have never been
confirmed against this hardware.

Two things about the metric worth knowing before trusting a number from it:

- ☠️ **The gradient is taken between pixel *x* and *x+2*, never between
  neighbours.** The frames are raw Bayer, so adjacent pixels are different
  colour planes and their difference measures the scene's colour rather than the
  focus. That mistake produces a large, stable, entirely meaningless number.
- **Only the high byte of each pixel is used.** Frames arrive MIPI-packed
  (`pRAA`): four pixels in five bytes, the fifth holding their low bits.
  Dropping it costs two bits and buys a tenfold speed-up, which matters when a
  frame is 15 MB and the scoring runs on the phone.

The lens subdev is found by looking for the control, never by device index — the
`/dev/v4l-subdev*` numbering moves between boots.
