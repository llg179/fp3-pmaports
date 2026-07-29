#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# sensinfo.py - ask SMGR what a sensor actually advertises (SINGLE_SENSOR_INFO,
# msg 0x06) before asking it for data.  The buffering request only makes sense
# in terms of the data types and rates the SSC itself reports here.
import socket, struct, sys

NODE, PORT = 5, 10
ALL_INFO, SINGLE_INFO = 0x05, 0x06
REQ, RESP = 0, 2


def tlv(t, p):
    return struct.pack('<BH', t, len(p)) + p


def tlvs(buf):
    o, off = {}, 0
    while off + 3 <= len(buf):
        t, l = struct.unpack_from('<BH', buf, off)
        o[t] = buf[off + 3:off + 3 + l]
        off += 3 + l
    return o


def call(s, txn, mid, body):
    s.sendto(struct.pack('<BHHH', REQ, txn, mid, len(body)) + body, (NODE, PORT))
    s.settimeout(3)
    while True:
        d, _ = s.recvfrom(65536)
        typ, rt, m, ml = struct.unpack_from('<BHHH', d, 0)
        if typ == RESP and m == mid:
            return tlvs(d[7:7 + ml])


s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
s.bind((s.getsockname()[0], 0))

print('== ALL_SENSOR_INFO')
r = call(s, 1, ALL_INFO, b'')
for t, v in sorted(r.items()):
    print('  tlv 0x%02x len %3d: %s' % (t, len(v), v.hex()))

ids = sys.argv[1:] or ['0x00', '0x28']
for a in ids:
    sid = int(a, 0)
    print('\n== SINGLE_SENSOR_INFO 0x%02x' % sid)
    r = call(s, 2, SINGLE_INFO, tlv(0x01, struct.pack('<B', sid)))
    for t, v in sorted(r.items()):
        print('  tlv 0x%02x len %3d: %s' % (t, len(v), v.hex()))
s.close()
