#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# smgrbuf.py - send SNS_SMGR_BUFFERING requests by hand and print what the SSC
# says.
#
# Why: the in-kernel SMGR core sends one hardcoded parameter set, and the SSC
# accepts it for the accelerometer and rejects it for the proximity sensor with
# result 0x501. Finding out which field it objects to is a parameter sweep, and
# doing that in the driver costs a 30-minute kernel build per guess. From here
# it costs a second.
#
# Wire format, read off sns_smgr_buffering_req_ei in the upstream driver:
#   TLV 0x01  u8  report_id
#   TLV 0x02  u8  action        (1 = ADD, 2 = DELETE)
#   TLV 0x03  u32 report_rate
#   TLV 0x04  u8  item_len, then item_len x
#             { u8 sensor_id, u8 data_type, u16 decimation,
#               u16 sampling_rate, u16 calibration }
import socket, struct, sys, itertools, time

SMGR_NODE = 5
SMGR_PORT = 10
BUFFERING_MSG_ID = 0x21
QMI_REQUEST, QMI_RESPONSE = 0, 2


def tlv(t, payload):
    return struct.pack('<BH', t, len(payload)) + payload


def build(report_id, action, report_rate, items):
    body = b''
    body += tlv(0x01, struct.pack('<B', report_id))
    body += tlv(0x02, struct.pack('<B', action))
    body += tlv(0x03, struct.pack('<I', report_rate))
    it = struct.pack('<B', len(items))
    for sid, dtype, dec, rate, cal in items:
        it += struct.pack('<BBHHH', sid, dtype, dec, rate, cal)
    body += tlv(0x04, it)
    return body


def parse_tlvs(buf):
    out, off = {}, 0
    while off + 3 <= len(buf):
        t, l = struct.unpack_from('<BH', buf, off)
        out[t] = buf[off + 3:off + 3 + l]
        off += 3 + l
    return out


def request(s, txn, body):
    pkt = struct.pack('<BHHH', QMI_REQUEST, txn, BUFFERING_MSG_ID, len(body)) + body
    s.sendto(pkt, (SMGR_NODE, SMGR_PORT))
    s.settimeout(3.0)
    try:
        data, _ = s.recvfrom(65536)
    except socket.timeout:
        return None
    typ, rtxn, mid, mlen = struct.unpack_from('<BHHH', data, 0)
    return parse_tlvs(data[7:7 + mlen])


def result_of(resp):
    if resp is None:
        return 'timeout'
    v = resp.get(0x02)
    if v is None:
        return 'no result TLV: %r' % resp
    if len(v) >= 2:
        r, e = v[0], v[1]
        return 'result=%d error=%d (raw 0x%04x)' % (r, e, struct.unpack('<H', v[:2])[0])
    return 'result raw %r' % v


def main():
    sid = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x28
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((s.getsockname()[0], 0))
    print('sensor id 0x%02x, from %s' % (sid, s.getsockname()))

    txn = 1
    # The driver's own parameters first, as the control: this is the exact
    # request that works for the accelerometer.
    trials = [('driver default', 0x3, 50, 0xf, 0)]
    for dec in (0, 1, 0x3):
        for cal in (0, 1, 0xf):
            for dtype in (0, 1):
                trials.append(('dec=%d cal=%d dtype=%d' % (dec, cal, dtype),
                               dec, 5, cal, dtype))

    seen = {}
    for label, dec, rate, cal, dtype in trials:
        body = build(sid, 1, rate * 100, [(sid, dtype, dec, rate, cal)])
        r = result_of(request(s, txn, body))
        txn += 1
        seen.setdefault(r, []).append(label)
        print('  %-28s -> %s' % (label, r))
        # always try to tear down so the SSC is not left with a report
        request(s, txn, build(sid, 2, 0, []))
        txn += 1
        time.sleep(0.05)

    print('\nsummary:')
    for r, labels in seen.items():
        print('  %-40s %d trial(s), e.g. %s' % (r, len(labels), labels[0]))
    s.close()


if __name__ == '__main__':
    main()
