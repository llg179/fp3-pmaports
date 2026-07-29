#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# smgrals.py - read the proximity sensor's *second* data type.
#
# Why: SINGLE_SENSOR_INFO says sensor 0x28 is an "EPL259x ALS/PS" with two data
# types, and the in-kernel core only ever asks for SNS_SMGR_DATA_TYPE_PRIMARY.
# PS is the proximity half; the ambient light half must be the other data type.
# Establishing which one, and what its numbers mean, is a measurement - doing it
# from here costs a second per guess instead of a 30-minute kernel build.
#
# Indication wire format (from sns_smgr_buffering_report_ind_ei):
#   TLV 0x01  u8   report_id
#   TLV 0x02  struct metadata { u32 val1, u8 sample_count, u32 timestamp,
#                               u32 val2 }
#   TLV 0x03  u8 sample_count, then N x { u32 values[3], u8, u8, u16 }
#
# metadata.val1 packs the source: (data_type << 16) | (sensor_id << 8) | 1,
# which is how samples are told apart when one report carries both data types.
import socket, struct, sys, time

NODE, PORT = 5, 10
BUFFERING, REPORT_IND = 0x21, 0x22
REQ, RESP, IND = 0, 2, 4
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


def build(report_id, action, report_rate, items):
    b = tlv(0x01, struct.pack('<B', report_id))
    b += tlv(0x02, struct.pack('<B', action))
    b += tlv(0x03, struct.pack('<I', report_rate))
    it = struct.pack('<B', len(items))
    for sid, dt, dec, sr, cal in items:
        it += struct.pack('<BBHHH', sid, dt, dec, sr, cal)
    return b + tlv(0x04, it)


def send(s, txn, body):
    s.sendto(struct.pack('<BHHH', REQ, txn, BUFFERING, len(body)) + body,
             (NODE, PORT))


def decode_ind(body):
    md = body.get(0x02, b'')
    val1 = ts = None
    if len(md) >= 13:
        val1, _cnt, ts, _v2 = struct.unpack_from('<IBII', md, 0)
    out = []
    smp = body.get(0x03, b'')
    if smp:
        n = smp[0]
        for i in range(n):
            off = 1 + i * SAMPLE_LEN
            if off + SAMPLE_LEN > len(smp):
                break
            v0, v1, v2, q1, q2, q3 = struct.unpack_from('<IIIBBH', smp, off)
            out.append((v0, v1, v2, q1, q2, q3))
    return val1, ts, out


def source(val1):
    if val1 is None:
        return '?'
    return 'sensor 0x%02x dtype %d (val1 0x%08x)' % ((val1 >> 8) & 0xff,
                                                     (val1 >> 16) & 0xff, val1)


def run(sid, items, secs, label):
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((s.getsockname()[0], 0))
    rate = max(sr for _, _, _, sr, _ in items)
    print('\n== %s' % label)
    print('   items: %s, report_rate %d' % (
        ['0x%02x/dt%d/sr%d' % (a, b, d) for a, b, _c, d, _e in items],
        rate * SMGR_REPORT_RATE_IN_HZ))
    send(s, 1, build(sid, 1, rate * SMGR_REPORT_RATE_IN_HZ, items))
    end = time.time() + secs
    n = 0
    per_source = {}
    while time.time() < end:
        s.settimeout(max(0.1, end - time.time()))
        try:
            d, _ = s.recvfrom(65536)
        except socket.timeout:
            break
        typ, txn, mid, mlen = struct.unpack_from('<BHHH', d, 0)
        body = tlvs(d[7:7 + mlen])
        if mid == BUFFERING and typ == RESP:
            r = body.get(0x02, b'')
            print('   response: %s' % (('result=%d error=%d' %
                                        (r[0], r[1])) if len(r) >= 2 else r.hex()))
            continue
        if mid != REPORT_IND:
            continue
        n += 1
        val1, ts, samples = decode_ind(body)
        key = source(val1)
        per_source.setdefault(key, []).append(samples)
        if n <= 8 or samples:
            print('   [%2d] %s ts=%s' % (n, key, ts))
            for v0, v1, v2, q1, q2, q3 in samples[:4]:
                print('        values=(%10d, %10d, %10d)  q=(%d,%d,%d)' %
                      (v0, v1, v2, q1, q2, q3))
    print('   %d indication(s) in %gs' % (n, secs))
    for k, v in per_source.items():
        print('   from %s: %d indication(s)' % (k, len(v)))
    send(s, 99, build(sid, 2, 0, []))
    s.close()


def main():
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    sid = 0x28
    # One data type at a time first, so a silent one is unambiguous, then both
    # in a single report the way the driver would ask for them.
    run(sid, [(sid, 0, 3, 5, 0xf)], secs, 'data type 0 (PRIMARY) alone')
    time.sleep(0.5)
    run(sid, [(sid, 1, 3, 5, 0xf)], secs, 'data type 1 (SECONDARY) alone')
    time.sleep(0.5)
    run(sid, [(sid, 0, 3, 5, 0xf), (sid, 1, 3, 5, 0xf)], secs,
        'both data types in one report')


if __name__ == '__main__':
    main()
