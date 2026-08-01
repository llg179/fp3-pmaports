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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=9,
                    help='number of focus positions to try (default 9)')
    ap.add_argument('--video', default='/dev/video0')
    ap.add_argument('--subdev', help='lens subdev; found automatically if omitted')
    ap.add_argument('--keep', help='directory to keep the captured frames in')
    args = ap.parse_args()

    subdev = args.subdev or find_lens_subdev()
    if not subdev:
        raise SystemExit('no subdev exposes focus_absolute - is the driver bound?')

    lo, hi = focus_range(subdev)
    print('lens subdev %s, focus range %d..%d' % (subdev, lo, hi))
    print()
    print('%10s  %14s' % ('position', 'sharpness'))

    outdir = args.keep or tempfile.mkdtemp(prefix='focus-sweep.')
    os.makedirs(outdir, exist_ok=True)

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

    # A lens that does not move still varies a little between frames, from
    # sensor noise and from the scene. The threshold separates that from an
    # actuator that is actually sweeping through focus.
    if ratio < 1.2:
        print()
        print('FLAT: the metric barely changes across the range, so the lens is')
        print('      probably not moving. Check that the actuator supply is on')
        print('      and that the writes reach it (i2c errors in dmesg).')
        return 1

    interior = best[0] not in (lo, hi)
    print()
    if interior:
        print('PASS: the peak is inside the range, so the sweep crossed focus.')
    else:
        print('PARTIAL: the metric rises but peaks at the end of the range, so')
        print('         the scene is at or beyond the limit of travel. Repeat')
        print('         with the subject nearer the middle of the focus range')
        print('         before drawing a conclusion about direction.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
