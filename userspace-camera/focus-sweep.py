#!/usr/bin/env python3
"""Sweep the lens actuator and score each position for sharpness.

This is the acceptance test for the focus driver. It answers two questions that
looking at a viewfinder cannot: whether the lens moves at all, and which end of
the control range is which.

Run it on the device, pointed at a scene with detail at a known distance:

    focus-sweep.py                       # 9 positions over the full range
    focus-sweep.py --steps 17 --keep /tmp/sweep

The metric is the mean squared gradient between same-colour neighbours. Because
the sensor delivers raw Bayer, neighbouring bytes are different colour planes,
so the gradient is taken between pixel x and x+2 - comparing adjacent pixels
would measure the colour difference of the scene rather than the focus.

Only the high byte of each pixel is used. The frame arrives as MIPI-packed
10-bit (pRAA): four pixels in five bytes, the first four bytes being the top
eight bits of each pixel and the fifth their low bits. Dropping the fifth byte
costs two bits of precision and buys a tenfold speed-up, which matters because a
frame is 15 MB and this runs on the phone.

A working actuator gives a curve with a single interior peak. A flat curve means
the lens is not moving - which is a real possible outcome here, because the
register map driving it was read out of a vendor blob and, while the decode was
validated against two parts whose answers mainline already states, nothing has
yet confirmed that writing those registers moves this board's lens. That is the
question this script exists to answer, so treat a flat curve as an answer and
not as a broken measurement.
"""

import argparse
import os
import subprocess
import sys
import tempfile

WIDTH = 4032
HEIGHT = 3024
FRAME_BYTES = WIDTH * HEIGHT * 10 // 8

# A centred crop, in packed-pixel units. Scoring the whole frame is pointless:
# the subject is in the middle and the edges only add noise and seconds.
CROP_W = 1024
CROP_H = 768


def find_lens_subdev():
    """Return the subdev that carries V4L2_CID_FOCUS_ABSOLUTE.

    The index moves between boots, so it is never hardcoded - the control is
    what identifies the device.
    """
    for entry in sorted(os.listdir('/dev')):
        if not entry.startswith('v4l-subdev'):
            continue
        path = '/dev/' + entry
        try:
            out = subprocess.run(['v4l2-ctl', '-d', path, '-l'],
                                 capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.SubprocessError):
            continue
        if 'focus_absolute' in out:
            return path
    return None


def focus_range(subdev):
    out = subprocess.run(['v4l2-ctl', '-d', subdev, '-l'],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        if 'focus_absolute' in line:
            lo = hi = None
            for field in line.split():
                if field.startswith('min='):
                    lo = int(field[4:])
                elif field.startswith('max='):
                    hi = int(field[4:])
            if lo is not None and hi is not None:
                return lo, hi
    raise SystemExit('focus_absolute has no min/max - is this the right subdev?')


def set_focus(subdev, value):
    subprocess.run(['v4l2-ctl', '-d', subdev,
                    '--set-ctrl', 'focus_absolute=%d' % value], check=True)


CAMSS_SINKS = ('msm_csiphy0', 'msm_csid0', 'msm_ispif0', 'msm_vfe0_rdi0')


def setup_pipeline(media='/dev/media0'):
    """Propagate the sensor's format along the CAMSS chain.

    From a cold boot the CAMSS pads sit at their default UYVY8_1X16/1920x1080
    while the sensor is at SRGGB10_1X10/4032x3024, so pipeline validation
    rejects STREAMON with -EPIPE. The failure logs nothing, mentions no format,
    and reads as a broken driver - it is worth doing this unconditionally
    rather than documenting the symptom.
    """
    fmt = '[fmt:SRGGB10_1X10/%dx%d]' % (WIDTH, HEIGHT)
    for entity in CAMSS_SINKS:
        subprocess.run(['media-ctl', '-d', media, '-V', "'%s':0 %s" % (entity, fmt)],
                       check=True, capture_output=True)


def capture(path, video):
    """Grab frames, keeping the last one.

    The first frames after a focus change are still in flight from before it,
    so several are taken and only the last is scored.
    """
    subprocess.run(
        ['v4l2-ctl', '-d', video,
         '--set-fmt-video=width=%d,height=%d,pixelformat=pRAA' % (WIDTH, HEIGHT),
         '--stream-mmap=4', '--stream-count=4', '--stream-to=' + path],
        check=True, capture_output=True)

    size = os.path.getsize(path)
    if size < FRAME_BYTES:
        raise SystemExit('short capture: %d bytes, expected at least %d'
                         % (size, FRAME_BYTES))
    return size


def sharpness(path):
    """Mean squared same-colour gradient over a centred crop of the last frame."""
    with open(path, 'rb') as f:
        f.seek(os.path.getsize(path) - FRAME_BYTES)
        frame = f.read(FRAME_BYTES)

    row_bytes = WIDTH * 10 // 8
    x0 = (WIDTH - CROP_W) // 2
    y0 = (HEIGHT - CROP_H) // 2

    total = 0
    count = 0
    for y in range(y0, y0 + CROP_H):
        base = y * row_bytes
        # Walk the row in groups of five bytes = four pixels, keeping the four
        # high bytes and dropping the shared low-bit byte.
        start = base + (x0 // 4) * 5
        end = base + ((x0 + CROP_W) // 4) * 5
        chunk = frame[start:end]
        pixels = bytearray()
        for i in range(0, len(chunk) - 4, 5):
            pixels += chunk[i:i + 4]
        for i in range(len(pixels) - 2):
            d = pixels[i] - pixels[i + 2]
            total += d * d
            count += 1

    return total / count if count else 0.0


def scene_stats(path):
    """Brightness spread of a centred crop: (mean, stddev, distinct values).

    A sharpness number is meaningless without this. Pointed at a dark desk the
    metric still wanders by a fifth from frame to frame, purely from sensor
    noise, and a threshold set below that reports a focus curve where there is
    none. Measured 2026-08-01 with the phone lying lens-down: mean 16.6,
    stddev 1.1, 13 distinct values out of 256 - and a peak-to-trough ratio of
    1.23x that had nothing to do with the lens.
    """
    with open(path, 'rb') as f:
        f.seek(os.path.getsize(path) - FRAME_BYTES)
        frame = f.read(FRAME_BYTES)

    row_bytes = WIDTH * 10 // 8
    x0 = (WIDTH - CROP_W) // 2
    y0 = (HEIGHT - CROP_H) // 2

    pixels = bytearray()
    for y in range(y0, y0 + CROP_H, 4):
        base = y * row_bytes
        chunk = frame[base + (x0 // 4) * 5: base + ((x0 + CROP_W) // 4) * 5]
        for i in range(0, len(chunk) - 4, 5):
            pixels += chunk[i:i + 4]

    if not pixels:
        return 0.0, 0.0, 0
    mean = sum(pixels) / len(pixels)
    var = sum((p - mean) ** 2 for p in pixels) / len(pixels)
    return mean, var ** 0.5, len(set(pixels))


def confirm_by_repetition(subdev, args, a, b, outdir, rounds=3):
    """Alternate between two positions several times and see if the metric follows.

    A magnitude threshold cannot tell a weak real effect from noise, because
    both are small. Repetition can: if the difference between two positions is
    large compared to the spread *within* each position, and it survives being
    revisited, then it is caused by the position and not by anything drifting.

    This also disposes of the trap that made the plain sweep ambiguous. The
    sweep walks the positions in time order, so a lens that never moves while
    the exposure settles produces a smooth monotone curve that looks exactly
    like one side of a focus peak. Interleaving separates the two: drift stays
    monotone in time, a real effect flips back and forth with the position.
    """
    print('%10s  %14s' % ('position', 'sharpness'))
    scores = {a: [], b: []}
    path = os.path.join(outdir, 'ab.raw')
    for _ in range(rounds):
        for pos in (a, b):
            set_focus(subdev, pos)
            capture(path, args.video)
            s = sharpness(path)
            scores[pos].append(s)
            print('%10d  %14.2f' % (pos, s))
            sys.stdout.flush()
    if not args.keep and os.path.exists(path):
        os.unlink(path)

    print()
    spread = 0.0
    for pos in (a, b):
        v = scores[pos]
        r = max(v) - min(v)
        spread = max(spread, r)
        print('position %4d: mean %.2f, spread %.2f over %d visits'
              % (pos, sum(v) / len(v), r, len(v)))
    gap = abs(sum(scores[a]) / rounds - sum(scores[b]) / rounds)
    print('difference between positions %.2f, worst spread within one %.2f'
          % (gap, spread))

    print()
    if spread > 0 and gap > 5 * spread:
        print('PASS: the metric follows the position and returns to the same')
        print('      value each time it comes back, so writing the control does')
        print('      move the lens. The sweep is shallow because the subject is')
        print('      near the end of travel - point the camera further away to')
        print('      see an actual peak.')
        return 0
    print('FLAT: the difference between positions is not large compared to the')
    print('      spread within one, so this does not show the lens moving.')
    print('      Check the actuator supply and look for i2c errors in dmesg.')
    return 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=9,
                    help='number of focus positions to try (default 9)')
    ap.add_argument('--video', default='/dev/video0')
    ap.add_argument('--media', default='/dev/media0')
    ap.add_argument('--subdev', help='lens subdev; found automatically if omitted')
    ap.add_argument('--keep', help='directory to keep the captured frames in')
    args = ap.parse_args()

    subdev = args.subdev or find_lens_subdev()
    if not subdev:
        raise SystemExit('no subdev exposes focus_absolute - is the driver bound?')

    lo, hi = focus_range(subdev)
    print('lens subdev %s, focus range %d..%d' % (subdev, lo, hi))

    setup_pipeline(args.media)

    outdir = args.keep or tempfile.mkdtemp(prefix='focus-sweep.')
    os.makedirs(outdir, exist_ok=True)

    # Is there anything to focus on? Ask before sweeping, not after: every
    # number below is a comparison between frames of this scene, so a scene
    # with no detail produces a full table of meaningless numbers that still
    # look like data.
    probe = os.path.join(outdir, 'probe.raw')
    capture(probe, args.video)
    mean, std, distinct = scene_stats(probe)
    print('scene: mean %.1f, stddev %.1f, %d distinct levels' % (mean, std, distinct))
    if not args.keep:
        os.unlink(probe)
    if std < 8.0 or distinct < 32:
        print()
        print('NO SCENE: the frame is nearly featureless, so nothing here can')
        print('          measure focus. Point the camera at something with')
        print('          detail and contrast - printed text at arm\'s length is')
        print('          ideal - in decent light, and run this again.')
        print('          (A dark desk measured mean 16.6, stddev 1.1,')
        print('          13 levels; that run still produced a plausible-looking')
        print('          table and a 1.23x "peak".)')
        return 2

    print()
    print('%10s  %14s' % ('position', 'sharpness'))

    results = []
    for i in range(args.steps):
        pos = lo + (hi - lo) * i // (args.steps - 1) if args.steps > 1 else lo
        set_focus(subdev, pos)

        path = os.path.join(outdir, 'pos-%04d.raw' % pos)
        capture(path, args.video)
        score = sharpness(path)
        if not args.keep:
            os.unlink(path)

        results.append((pos, score))
        print('%10d  %14.2f' % (pos, score))
        sys.stdout.flush()

    print()
    best = max(results, key=lambda r: r[1])
    worst = min(results, key=lambda r: r[1])
    print('sharpest at position %d (%.2f), flattest at %d (%.2f)'
          % (best[0], best[1], worst[0], worst[1]))

    if worst[1] == 0:
        raise SystemExit('a frame scored exactly zero - the capture is not an image')

    ratio = best[1] / worst[1]
    print('peak-to-trough ratio %.2fx' % ratio)

    # A lens that does not move still varies from frame to frame. Measured on a
    # featureless dark scene: 1.23x, entirely from sensor noise. The bar is set
    # well clear of that rather than just above it, because a verdict that a
    # noisy run can reach is worse than no verdict.
    if ratio < 2.0:
        print()
        print('The sweep alone is inconclusive: it changes less across the')
        print('whole range than a still scene changes on its own (a featureless')
        print('frame measured 1.23x). Repeating the two extremes instead.')
        print()
        # ☠️ The extremes of *travel*, not the best and worst of the sweep. On a
        # flat curve those two are wherever the noise happened to fall - once
        # measured as 511 and 716, so the retry compared the smallest movement
        # available instead of the largest, and concluded the lens was still.
        return confirm_by_repetition(subdev, args, lo, hi, outdir)

    # A real focus curve has shoulders: the positions either side of the peak
    # are also sharper than most. A noise spike stands alone. Without this a
    # single outlier anywhere in the sweep passes as "focus".
    order = sorted(r[1] for r in results)
    median = order[len(order) // 2]
    idx = results.index(best)
    shoulders = [results[i][1] for i in (idx - 1, idx + 1) if 0 <= i < len(results)]
    if not all(s > median for s in shoulders):
        print()
        print('SPIKE: the sharpest position has no shoulders - its neighbours')
        print('       are no better than the middle of the run - so the peak is')
        print('       one odd frame, not a focus curve. Re-run before believing')
        print('       it; if it repeats at the same position, it is real.')
        return 1

    interior = best[0] not in (lo, hi)
    print()
    if interior:
        print('PASS: the peak is inside the range and has shoulders, so the')
        print('      sweep crossed focus.')
    else:
        print('PARTIAL: the metric rises but peaks at the end of the range, so')
        print('         the scene is at or beyond the limit of travel. Repeat')
        print('         with the subject nearer the middle of the focus range')
        print('         before drawing a conclusion about direction.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
