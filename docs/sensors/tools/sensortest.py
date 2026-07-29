#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# sensortest.py - read any of the Sensor Manager's IIO devices and say whether
# the numbers are physically plausible, so "the driver binds" can be told apart
# from "the sensor works".
#
# Finds devices by name rather than by index: the Sensor Manager registers them
# as its QMI enumeration completes, so iio:deviceN moves between boots -- the
# accelerometer has been device2 and device3 on consecutive boots here.
#
# Usage:  sensortest.py accel|gyro|mag|prox [seconds]
#
# The three IMU devices are buffer-only (no *_raw), so they are read through
# /dev/iio:deviceN. A record is 3 x s32 followed by an s64 timestamp at offset
# 16 -- 24 bytes. Reading 32 makes every third line look correct, which is a
# more dangerous failure than reading nothing.
import os, struct, sys, time

NAMES = {
    'accel': ('qcom-smgr-accel', 'in_accel_scale', 'm/s^2'),
    'gyro': ('qcom-smgr-gyro', 'in_anglvel_scale', 'rad/s'),
    'mag': ('qcom-smgr-mag', 'in_magn_scale', 'Gauss?'),
    'prox': ('qcom-smgr-prox-light', None, 'counts'),
}

RECORD = 24


def find(name):
    for d in sorted(os.listdir('/sys/bus/iio/devices')):
        if not d.startswith('iio:device'):
            continue
        p = '/sys/bus/iio/devices/' + d
        try:
            if open(p + '/name').read().strip() == name:
                return p, d.split('device')[1]
        except OSError:
            pass
    return None, None


def read_buffered(path, index, scale, unit, secs, scale_attr=None):
    for e in os.listdir(path + '/scan_elements'):
        if e.endswith('_en'):
            open(path + '/scan_elements/' + e, 'w').write('1')
    open(path + '/buffer/length', 'w').write('128')
    open(path + '/buffer/enable', 'w').write('1')

    lo = [None] * 3
    hi = [None] * 3
    mags = []
    integ = ([], [], []) if 'anglvel' in (scale_attr or '') else None
    try:
        with open('/dev/iio:device' + index, 'rb') as f:
            os.set_blocking(f.fileno(), False)
            end = time.monotonic() + secs
            shown = 0
            while time.monotonic() < end:
                d = f.read(RECORD)
                if not d or len(d) < RECORD:
                    time.sleep(0.02)
                    continue
                v = [x * scale for x in struct.unpack_from('<iii', d, 0)]
                m = sum(x * x for x in v) ** 0.5
                mags.append(m)
                if integ is not None:
                    for i in range(3):
                        integ[i].append(v[i])
                for i in range(3):
                    lo[i] = v[i] if lo[i] is None else min(lo[i], v[i])
                    hi[i] = v[i] if hi[i] is None else max(hi[i], v[i])
                if shown < 6:
                    shown += 1
                    print('   %8.3f %8.3f %8.3f   |v| = %.3f %s'
                          % (v[0], v[1], v[2], m, unit), flush=True)
    finally:
        open(path + '/buffer/enable', 'w').write('0')

    if not mags:
        print('   NO SAMPLES -- the sensor is bound but sent nothing')
        return None
    print('   %d samples; per-axis range over the run:' % len(mags))
    for i, ax in enumerate('xyz'):
        print('     %s: %8.3f .. %8.3f   (swing %.3f)'
              % (ax, lo[i], hi[i], hi[i] - lo[i]))
    print('   |v|: %.3f .. %.3f' % (min(mags), max(mags)))

    if integ is not None:
        # Angle = integral of angular velocity. The samples arrive at a fixed
        # rate, so a uniform dt over the run is good enough to check a scale
        # against a rotation of known size -- turn the phone by 180 degrees and
        # one axis has to integrate to pi.
        dt = secs / len(integ[0])
        print('   integrated over the run (turn by a known angle to check the scale):')
        for i, ax in enumerate('xyz'):
            rad = sum(integ[i]) * dt
            print('     %s: %8.3f rad = %7.1f deg' % (ax, rad, rad * 180 / 3.141592653589793))
    return lo, hi, mags


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else 'accel'
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 6
    name, scale_attr, unit = NAMES[what]
    path, index = find(name)
    if not path:
        print('%s: not found -- is the module loaded and snsregd running?' % name)
        return 1
    print('%s = %s' % (path, name))

    if what == 'prox':
        end = time.monotonic() + secs
        seen = []
        while time.monotonic() < end:
            v = int(open(path + '/in_proximity_raw').read())
            if not seen or seen[-1] != v:
                print('   %5.1fs  %-8d %s'
                      % (secs - (end - time.monotonic()), v,
                         'NEAR' if v >= 1570 else 'far'), flush=True)
            seen.append(v)
            time.sleep(0.4)
        near = [v for v in seen if v >= 1570]
        print('   %d reads, %d near, range %d..%d'
              % (len(seen), len(near), min(seen), max(seen)))
        return 0

    scale = float(open(path + '/' + scale_attr).read())
    print('   scale = %g (raw -> %s)' % (scale, unit))
    read_buffered(path, index, scale, unit, secs, scale_attr)
    return 0


sys.exit(main())
