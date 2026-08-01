#!/usr/bin/env python3
"""Sweep the lens actuator and score each position for sharpness.

This is the acceptance test for the focus driver. It answers two questions that
looking at a viewfinder cannot: whether the lens moves at all, and where in the
control range this scene comes into focus.

Run it on the device, pointed at a scene with detail at a known distance:

    focus-sweep.py                       # 9 positions, 4 interleaved passes
    focus-sweep.py --lo 300 --hi 460 --steps 9 --passes 6
    focus-sweep.py --keep /tmp/sweep

The metric is the mean squared gradient between same-colour neighbours over a
centred crop. Because the sensor delivers raw Bayer, neighbouring bytes are
different colour planes, so the gradient is taken between pixel x and x+2 -
comparing adjacent pixels would measure the colour difference of the scene
rather than the focus. Only the high byte of each pixel is used: the frame is
MIPI-packed 10-bit (pRAA), four pixels in five bytes with the fifth holding
their low bits, and dropping it costs two bits and buys a large speed-up on a
15 MB frame.

☠️ Two design decisions here exist because the naive version of this script
returned the wrong answer twice, in opposite directions, on this very phone.

**One stream for the whole sweep.** The first version started a fresh
`v4l2-ctl` capture at every position. Each restart resets auto-exposure and
injects a settling transient as large as the effect being measured, which
buried a real focus curve in noise and produced a confident "the lens does not
move". Here the stream is opened once and the focus changes underneath it.

**The positions are visited in interleaved passes, not once each in order.**
A single ordered walk confounds position with time: anything that drifts while
the sweep runs - exposure, temperature, the light in the room - comes out as a
smooth monotone curve that looks exactly like one side of a focus peak. That
produced a confident "the lens moves" from a lens that had not been shown to
move. Alternating the direction of successive passes cancels a linear drift and,
more usefully, *measures* it: the pass-to-pass table below tells you how much of
what you are seeing was time.
"""

import argparse
import os
import subprocess
import sys
import threading
import time

import numpy as np

WIDTH = 4032
HEIGHT = 3024
ROW_BYTES = WIDTH * 10 // 8
FRAME_BYTES = ROW_BYTES * HEIGHT

# A centred crop, in pixels. Scoring the whole frame is pointless: the subject
# is in the middle and the edges only add noise and seconds.
CROP_W = 1024
CROP_H = 768

# Column indices of the high byte of each pixel.
_cols = np.arange(ROW_BYTES)
HIGH_COLS = _cols[_cols % 5 != 4]

CAMSS_SINKS = ('msm_csiphy0', 'msm_csid0', 'msm_ispif0', 'msm_vfe0_rdi0')


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
                    '--set-ctrl', 'focus_absolute=%d' % value],
                   check=True, capture_output=True)


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


class Stream(threading.Thread):
    """One capture for the whole run, newest frame only.

    Python cannot keep up with the sensor, so a queue would build and every
    frame scored would belong to a focus position several changes old. Keeping
    only the newest frame, plus a monotonically increasing counter, lets a
    caller say "the next frame that starts after now" precisely.
    """

    daemon = True

    def __init__(self, video='/dev/video0'):
        super().__init__()
        self.proc = subprocess.Popen(
            ['v4l2-ctl', '-d', video,
             '--set-fmt-video=width=%d,height=%d,pixelformat=pRAA' % (WIDTH, HEIGHT),
             '--stream-mmap=3', '--stream-count=1000000', '--stream-to=-'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        self.latest = None
        self.count = 0
        self.lock = threading.Lock()
        self.dead = False

    def run(self):
        while True:
            buf = bytearray(FRAME_BYTES)
            view = memoryview(buf)
            got = 0
            while got < FRAME_BYTES:
                n = self.proc.stdout.readinto(view[got:])
                if not n:
                    with self.lock:
                        self.dead = True
                    return
                got += n
            with self.lock:
                self.latest = bytes(buf)
                self.count += 1

    def fresh(self, drop=3, timeout=10.0):
        """Return a frame that began after this call, having dropped `drop`.

        The frame in flight when the focus was written is a mixture of before
        and after, and the sensor pipeline holds a couple more behind it.
        """
        with self.lock:
            start = self.count
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self.lock:
                if self.dead:
                    raise SystemExit('the capture stopped - check dmesg and '
                                     'that nothing else holds /dev/video0')
                if self.count > start + drop and self.latest is not None:
                    return self.latest
            time.sleep(0.02)
        raise SystemExit('no frame within %.0fs - is the sensor streaming?' % timeout)

    def stop(self):
        self.proc.terminate()


def crop_of(frame):
    a = np.frombuffer(frame, np.uint8).reshape(HEIGHT, ROW_BYTES)
    x0 = (WIDTH - CROP_W) // 2
    y0 = (HEIGHT - CROP_H) // 2
    return a[y0:y0 + CROP_H][:, HIGH_COLS[x0:x0 + CROP_W]].astype(np.int16)


def sharpness(frame):
    """Mean squared same-colour gradient over a centred crop."""
    crop = crop_of(frame)
    d = crop[:, :-2] - crop[:, 2:]
    return float((d.astype(np.int32) ** 2).mean())


def scene_stats(frame):
    """Brightness spread of a centred crop: (mean, stddev, distinct values).

    A sharpness number is meaningless without this. Pointed at a dark desk the
    metric still wanders by a fifth from frame to frame, purely from sensor
    noise, and a threshold set below that reports a focus curve where there is
    none. Measured 2026-08-01 with the phone lying lens-down: mean 16.6,
    stddev 1.1, 13 distinct values out of 256 - and a peak-to-trough ratio of
    1.23x that had nothing to do with the lens.
    """
    crop = crop_of(frame).astype(np.uint8)
    return float(crop.mean()), float(crop.std()), int(np.unique(crop).size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=9,
                    help='number of focus positions to try (default 9)')
    ap.add_argument('--passes', type=int, default=4,
                    help='how many interleaved visits per position (default 4)')
    ap.add_argument('--lo', type=int, help='low end of the sweep (default: control min)')
    ap.add_argument('--hi', type=int, help='high end of the sweep (default: control max)')
    ap.add_argument('--drop', type=int, default=3,
                    help='frames to discard after each move (default 3)')
    ap.add_argument('--video', default='/dev/video0')
    ap.add_argument('--media', default='/dev/media0')
    ap.add_argument('--subdev', help='lens subdev; found automatically if omitted')
    ap.add_argument('--keep', help='directory to keep one frame per position in')
    args = ap.parse_args()

    subdev = args.subdev or find_lens_subdev()
    if not subdev:
        raise SystemExit('no subdev exposes focus_absolute - is the driver bound?')

    cmin, cmax = focus_range(subdev)
    lo = cmin if args.lo is None else args.lo
    hi = cmax if args.hi is None else args.hi
    if not cmin <= lo < hi <= cmax:
        raise SystemExit('--lo/--hi must lie inside %d..%d' % (cmin, cmax))
    print('lens subdev %s, control range %d..%d, sweeping %d..%d'
          % (subdev, cmin, cmax, lo, hi))

    setup_pipeline(args.media)
    if args.keep:
        os.makedirs(args.keep, exist_ok=True)

    stream = Stream(args.video)
    stream.start()
    try:
        # Is there anything to focus on? Ask before sweeping, not after: every
        # number below is a comparison between frames of this scene, so a scene
        # with no detail produces a full table of meaningless numbers that still
        # look like data.
        mean, std, distinct = scene_stats(stream.fresh(drop=6))
        print('scene: mean %.1f, stddev %.1f, %d distinct levels'
              % (mean, std, distinct))
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

        positions = [lo + (hi - lo) * i // (args.steps - 1)
                     for i in range(args.steps)] if args.steps > 1 else [lo]
        scores = {p: [] for p in positions}

        print()
        print('%10s' % 'position', end='')
        for k in range(args.passes):
            print('%12s' % ('pass %d' % (k + 1)), end='')
        print('%12s' % 'mean')

        for k in range(args.passes):
            # Alternate direction so a linear drift cancels between passes
            # instead of adding itself to the curve.
            order = positions if k % 2 == 0 else list(reversed(positions))
            for pos in order:
                set_focus(subdev, pos)
                frame = stream.fresh(drop=args.drop)
                scores[pos].append(sharpness(frame))
                if args.keep and k == 0:
                    with open(os.path.join(args.keep, 'pos-%04d.raw' % pos), 'wb') as f:
                        f.write(frame)

        for pos in positions:
            print('%10d' % pos, end='')
            for s in scores[pos]:
                print('%12.1f' % s, end='')
            print('%12.1f' % (sum(scores[pos]) / len(scores[pos])))
        sys.stdout.flush()
    finally:
        stream.stop()

    means = {p: sum(v) / len(v) for p, v in scores.items()}
    best = max(means, key=means.get)
    worst = min(means, key=means.get)
    # Spread within one position, across its repeat visits: this is the noise
    # floor of the whole experiment, drift included, measured rather than
    # assumed.
    within = max(max(v) - min(v) for v in scores.values())
    between = means[best] - means[worst]

    print()
    print('sharpest at %d (%.1f), flattest at %d (%.1f)'
          % (best, means[best], worst, means[worst]))
    print('between positions %.1f, worst spread within one position %.1f'
          % (between, within))

    # How much of the run was time rather than position? Each pass covers every
    # position, so the pass means differ only through drift.
    pass_means = [sum(scores[p][k] for p in positions) / len(positions)
                  for k in range(args.passes)]
    print('pass means ' + ' '.join('%.1f' % m for m in pass_means)
          + '  (spread %.1f - this part is time, not focus)'
          % (max(pass_means) - min(pass_means)))

    print()
    if means[worst] <= 0:
        raise SystemExit('a position scored zero - the capture is not an image')
    if between < 2 * within:
        print('FLAT: the difference between positions is not large compared to')
        print('      the spread within one, so this does not show the lens')
        print('      moving. If the whole sweep sits far from focus the curve is')
        print('      genuinely flat there - try --lo/--hi around a position that')
        print('      looks sharp in the viewfinder before concluding anything.')
        return 1

    # A real focus curve has shoulders: the positions either side of the peak
    # are also sharper than most. A noise spike stands alone.
    ordered = sorted(means.values())
    median = ordered[len(ordered) // 2]
    idx = positions.index(best)
    shoulders = [means[positions[i]] for i in (idx - 1, idx + 1)
                 if 0 <= i < len(positions)]
    if not all(s > median for s in shoulders):
        print('SPIKE: the sharpest position has no shoulders - its neighbours')
        print('       are no better than the middle of the run - so the peak is')
        print('       one odd position, not a focus curve.')
        return 1

    print('PASS: sharpness follows the position and comes back to the same value')
    print('      each time the position is revisited, so writing the control')
    print('      moves the lens. Peak-to-trough %.2fx over %d..%d.'
          % (means[best] / means[worst], lo, hi))
    if best in (lo, hi):
        print()
        print('PARTIAL: the peak is at the end of the swept range, so the true')
        print('         optimum may lie outside it. Re-run with --lo/--hi moved')
        print('         that way to bracket it.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
