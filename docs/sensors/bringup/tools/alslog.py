#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# alslog.py - log the ambient light half of sensor 0x28 (data type 1) so the
# meaning of its three values can be read off a physical light change rather
# than guessed.
#
# Hypothesis under test: values[0] is lux in Q16 fixed point and values[1] is
# the raw ADC count behind it.  Both are printed, along with their ratio, which
# should stay constant if one is derived from the other.
import socket, struct, sys, time

NODE, PORT = 5, 10
BUFFERING, REPORT_IND = 0x21, 0x22
REQ, RESP = 0, 2
SMGR_REPORT_RATE_IN_HZ = 0xf000
SAMPLE_LEN = 16


def tlv(t, p):
    return struct.pack('<BH', t, len(p)) + p


def tlvs(buf):
    o, off = {}, 0
    while off + 3 <= len(buf):
        t, l = struct.unpack_from('<BH', buf, off)
        o[t] = buf[off + 3:off + 3 + l]
        off += 3 + l
    return o


def build(report_id, action, rate, items):
    b = tlv(0x01, struct.pack('<B', report_id))
    b += tlv(0x02, struct.pack('<B', action))
    b += tlv(0x03, struct.pack('<I', rate))
    it = struct.pack('<B', len(items))
    for sid, dt, dec, sr, cal in items:
        it += struct.pack('<BBHHH', sid, dt, dec, sr, cal)
    return b + tlv(0x04, it)


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    dtype = int(sys.argv[2], 0) if len(sys.argv) > 2 else 1
    sid = 0x28
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((s.getsockname()[0], 0))
    s.sendto(struct.pack('<BHHH', REQ, 1, BUFFERING, 0)[:0] +
             (lambda b: struct.pack('<BHHH', REQ, 1, BUFFERING, len(b)) + b)(
                 build(sid, 1, 5 * SMGR_REPORT_RATE_IN_HZ,
                       [(sid, dtype, 3, 5, 0xf)])), (NODE, PORT))
    print('sensor 0x%02x data type %d, %g s' % (sid, dtype, secs))
    print('  %8s %12s %10s %8s %8s' %
          ('t[s]', 'values[0]', 'as Q16', 'values[1]', 'ratio'))
    t0 = time.time()
    end = t0 + secs
    lo = hi = None
    while time.time() < end:
        s.settimeout(max(0.1, end - time.time()))
        try:
            d, _ = s.recvfrom(65536)
        except socket.timeout:
            break
        typ, txn, mid, mlen = struct.unpack_from('<BHHH', d, 0)
        if mid != REPORT_IND:
            continue
        smp = tlvs(d[7:7 + mlen]).get(0x03, b'')
        if not smp:
            continue
        for i in range(smp[0]):
            off = 1 + i * SAMPLE_LEN
            if off + SAMPLE_LEN > len(smp):
                break
            v0, v1, v2 = struct.unpack_from('<III', smp, off)
            q = v0 / 65536.0
            r = (v1 / q) if q else float('nan')
            lo = q if lo is None else min(lo, q)
            hi = q if hi is None else max(hi, q)
            print('  %8.2f %12d %10.3f %8d %8.3f' %
                  (time.time() - t0, v0, q, v1, r))
    print('  Q16 range: %s .. %s' % (lo, hi))
    s.sendto((lambda b: struct.pack('<BHHH', REQ, 2, BUFFERING, len(b)) + b)(
        build(sid, 2, 0, [])), (NODE, PORT))
    s.close()


if __name__ == '__main__':
    main()
