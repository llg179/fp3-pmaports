#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# smgrsweep.py - same request the in-kernel driver sends (report_rate =
# sample_rate * 0xf000, decimation 3, calibration 0xf), but with the data type
# as a parameter.  The first sweep used report_rate = rate*100, which in this
# encoding is one report every two minutes, so "one indication" there measured
# nothing but the initial report.
import socket, struct, sys, time

NODE, PORT = 5, 10
BUFFERING = 0x21
REQ, RESP = 0, 2
RATE_IN_HZ = 0xf000


def tlv(t, p):
    return struct.pack('<BH', t, len(p)) + p


def tlvs(buf):
    o, off = {}, 0
    while off + 3 <= len(buf):
        t, l = struct.unpack_from('<BH', buf, off)
        o[t] = buf[off + 3:off + 3 + l]
        off += 3 + l
    return o


def build(rid, action, rate, items):
    b = tlv(0x01, struct.pack('<B', rid))
    b += tlv(0x02, struct.pack('<B', action))
    b += tlv(0x03, struct.pack('<I', rate))
    it = struct.pack('<B', len(items))
    for sid, dt, dec, sr, cal in items:
        it += struct.pack('<BBHHH', sid, dt, dec, sr, cal)
    return b + tlv(0x04, it)


def samples(v):
    n = v[0]
    out = []
    for i in range(n):
        a, b, c = struct.unpack_from('<III', v, 1 + i * 16)
        out.append((a, b, c))
    return out


def run(sid, dtype, sr, secs):
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((s.getsockname()[0], 0))
    rid = 0x11
    s.sendto((lambda b: struct.pack('<BHHH', REQ, 1, BUFFERING, len(b)) + b)(
        build(rid, 1, sr * RATE_IN_HZ, [(sid, dtype, 3, sr, 0xf)])), (NODE, PORT))
    s.settimeout(secs)
    end, ind, nsamp, uniq = time.time() + secs, 0, 0, {}
    while time.time() < end:
        try:
            d, _ = s.recvfrom(65536)
        except socket.timeout:
            break
        typ, txn, mid, ml = struct.unpack_from('<BHHH', d, 0)
        body = tlvs(d[7:7 + ml])
        if typ == RESP:
            print('    resp result=%s' % body.get(0x02, b'').hex())
            continue
        ind += 1
        for sm in samples(body.get(0x03, b'\x00')):
            nsamp += 1
            uniq[sm] = uniq.get(sm, 0) + 1
    s.sendto((lambda b: struct.pack('<BHHH', REQ, 99, BUFFERING, len(b)) + b)(
        build(rid, 2, 0, [])), (NODE, PORT))
    time.sleep(0.3)
    s.close()
    print('  => sid 0x%02x dtype %d sr %d: %d ind, %d samples in %gs' %
          (sid, dtype, sr, ind, nsamp, secs))
    for sm, c in sorted(uniq.items(), key=lambda kv: -kv[1])[:5]:
        print('       %6dx  %s' % (c, ' '.join('0x%08x' % x for x in sm)))


sid = int(sys.argv[1], 0)
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 8
sr = int(sys.argv[3]) if len(sys.argv) > 3 else 50
for dtype in (int(sys.argv[4]),) if len(sys.argv) > 4 else (0, 1):
    print('-- sid 0x%02x dtype %d' % (sid, dtype))
    run(sid, dtype, sr, secs)
    time.sleep(0.5)
