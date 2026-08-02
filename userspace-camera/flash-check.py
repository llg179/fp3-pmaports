#!/usr/bin/env python3
"""Confirm the camera flash optically, with the rear camera as the instrument.

The electrical measurements say current flows and the PMIC registers say the
module is enabled, but neither of those sees light. This does: it holds one
capture open, switches the torch on and off underneath it, and compares the
brightness of a centred crop.

Two things it deliberately does, both learned the hard way on this phone:

  * the capture is opened once and the torch varied inside it. Restarting the
    stream per sample injects a transient the size of the signal.
  * the states are interleaved - off, on, off, on - so a drift in the scene
    (someone moving, the room changing) separates from the effect instead of
    being read as one.

Point the camera at something close and matte, a hand's width away, and run it.
A scene the torch cannot reach will honestly report no difference.
"""

import argparse
import importlib.util
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent


def load_sweep():
    """Reuse focus-sweep.py rather than copying its pipeline setup."""
    path = HERE / 'focus-sweep.py'
    spec = importlib.util.spec_from_file_location('focus_sweep', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--led', default='/sys/class/leds/white:flash')
    ap.add_argument('--passes', type=int, default=3)
    ap.add_argument('--settle', type=float, default=1.5,
                    help='seconds to wait after switching the torch')
    ap.add_argument('--video', default='/dev/video0')
    ap.add_argument('--media', default='/dev/media0')
    args = ap.parse_args()

    sweep = load_sweep()
    led = pathlib.Path(args.led)
    if not led.exists():
        sys.exit('no flash LED at %s' % led)
    level = int((led / 'max_brightness').read_text())

    def torch(on):
        (led / 'brightness').write_text(str(level if on else 0))

    sweep.setup_pipeline(args.media)
    stream = sweep.Stream(args.video)
    stream.start()
    torch(False)
    time.sleep(args.settle)

    readings = {False: [], True: []}
    try:
        for p in range(args.passes):
            for on in (False, True):
                torch(on)
                time.sleep(args.settle)
                mean, std, distinct = sweep.scene_stats(stream.fresh())
                readings[on].append(mean)
                print('pass %d  torch %-3s  mean %7.2f  std %6.2f  distinct %4d'
                      % (p + 1, 'on' if on else 'off', mean, std, distinct))
    finally:
        torch(False)
        stream.stop()

    off, on = readings[False], readings[True]
    print('\noff mean %.2f   on mean %.2f' % (sum(off) / len(off), sum(on) / len(on)))

    # The claim is separation, not a ratio: every lit frame brighter than every
    # unlit one is a result a drifting scene cannot fake.
    if min(on) > max(off):
        print('PASS: every torch-on frame is brighter than every torch-off one '
              '(%.2f > %.2f)' % (min(on), max(off)))
        return 0
    print('FAIL: the two states overlap - on ranges %.2f..%.2f, off %.2f..%.2f'
          % (min(on), max(on), min(off), max(off)))
    print('      A scene the torch cannot light gives exactly this. Try again '
            'with the lens close to a matte surface before blaming the LED.')
    return 1


if __name__ == '__main__':
    sys.exit(main())
