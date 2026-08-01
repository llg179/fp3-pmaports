#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# iiolog.py - dump raw timestamped samples from one Sensor Manager IIO device
# to a CSV, so the analysis can happen on the host instead of on the phone.
#
# sensortest.py answers "is this plausible?" interactively; this answers
# "what exactly did it read, and when?", which is what a mount-matrix
# determination or an ellipsoid fit needs.
#
# Usage:  iiolog.py accel|gyro|mag SECONDS OUTFILE
#
# Writes incrementally, so a run that is killed still leaves usable data --
# a sampler that only writes at the end loses everything when the session dies.
import os, struct, sys, time

NAMES = {
    'accel': ('qcom-smgr-accel', 'in_accel_scale'),
    'gyro': ('qcom-smgr-gyro', 'in_anglvel_scale'),
    'mag': ('qcom-smgr-mag', 'in_magn_scale'),
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


def main():
    what, secs, out = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    name, scale_attr = NAMES[what]
    path, index = find(name)
    if not path:
        print('%s: not found' % name)
        return 1
    scale = float(open(path + '/' + scale_attr).read())

    for e in os.listdir(path + '/scan_elements'):
        if e.endswith('_en'):
            open(path + '/scan_elements/' + e, 'w').write('1')
    open(path + '/buffer/length', 'w').write('128')
    open(path + '/buffer/enable', 'w').write('1')

    n = 0
    t0 = time.monotonic()
    try:
        with open(out, 'w') as fo, open('/dev/iio:device' + index, 'rb') as f:
            fo.write('# %s scale=%g\n' % (name, scale))
            fo.write('t,x,y,z\n')
            os.set_blocking(f.fileno(), False)
            last_mark = 0
            while True:
                t = time.monotonic() - t0
                if t >= secs:
                    break
                d = f.read(RECORD)
                if not d or len(d) < RECORD:
                    time.sleep(0.01)
                    continue
                v = [x * scale for x in struct.unpack_from('<iii', d, 0)]
                fo.write('%.4f,%.6f,%.6f,%.6f\n' % (t, v[0], v[1], v[2]))
                n += 1
                if n % 100 == 0:
                    fo.flush()
                if int(t) // 5 > last_mark:
                    last_mark = int(t) // 5
                    print('   %3.0fs  %8.3f %8.3f %8.3f'
                          % (t, v[0], v[1], v[2]), flush=True)
    finally:
        open(path + '/buffer/enable', 'w').write('0')
    print('   %d samples -> %s' % (n, out))
    return 0


sys.exit(main())
