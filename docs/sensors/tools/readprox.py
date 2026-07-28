#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# readprox.py - read the SMGR proximity/light device.
#
# The SMGR devices are buffer-only: no *_raw attributes, so a reading means
# enabling the scan elements and pulling fixed-size records out of the character
# device.  A record is 3 x u32 followed by padding and a 64-bit timestamp; get
# the record size wrong and every Nth line still looks plausible, which is worse
# than reading nothing.
import os, struct, sys, glob, time

def find_dev(name):
    for d in glob.glob('/sys/bus/iio/devices/iio:device*'):
        try:
            if open(d + '/name').read().strip() == name:
                return d
        except OSError:
            pass
    return None

D = find_dev('qcom-smgr-prox-light')
if not D:
    print('no qcom-smgr-prox-light IIO device'); sys.exit(1)
print('device:', D)
print('channels:', sorted(os.listdir(D + '/scan_elements')))

for e in os.listdir(D + '/scan_elements'):
    if e.endswith('_en'):
        open(D + '/scan_elements/' + e, 'w').write('1')
open(D + '/buffer/length', 'w').write('128')
open(D + '/buffer/enable', 'w').write('1')

n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
dev = '/dev/' + os.path.basename(D).replace('iio:device', 'iio:device')
f = open(dev, 'rb')
print('  value0    value1      timestamp')
try:
    for _ in range(n):
        d = f.read(24)
        if len(d) < 24:
            break
        v0, v1, v2 = struct.unpack_from('<III', d, 0)
        ts, = struct.unpack_from('<q', d, 16)
        print('  %8d  %8d   %d' % (v0, v1, ts))
finally:
    f.close()
    open(D + '/buffer/enable', 'w').write('0')
