#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# smgrind.py - ask the SSC for buffering on one sensor and print the indications
# it sends back, so "which sensor is this data actually from" is answered by the
# wire rather than by the driver's routing.
import socket, struct, sys, time

NODE, PORT = 5, 10
BUFFERING, REPORT_IND = 0x21, 0x22
REQ, RESP, IND = 0, 2, 4


def tlv(t, p):
    return struct.pack('<BH', t, len(p)) + p


def build(report_id, action, rate, items):
    b = tlv(0x01, struct.pack('<B', report_id))
    b += tlv(0x02, struct.pack('<B', action))
    b += tlv(0x03, struct.pack('<I', rate))
    it = struct.pack('<B', len(items))
    for sid, dt, dec, sr, cal in items:
        it += struct.pack('<BBHHH', sid, dt, dec, sr, cal)
    return b + tlv(0x04, it)


def tlvs(buf):
    o, off = {}, 0
    while off + 3 <= len(buf):
        t, l = struct.unpack_from('<BH', buf, off)
        o[t] = buf[off + 3:off + 3 + l]
        off += 3 + l
    return o


sid = int(sys.argv[1], 0)
secs = float(sys.argv[2]) if len(sys.argv) > 2 else 12
s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
s.bind((s.getsockname()[0], 0))
print('report_id 0x%02x, item sensor_id 0x%02x, from %s' % (sid, int(sys.argv[3],0) if len(sys.argv)>3 else sid, s.getsockname()))
s.sendto(struct.pack('<BHHH', REQ, 1, BUFFERING, 0) [:0] +
         (lambda body: struct.pack('<BHHH', REQ, 1, BUFFERING, len(body)) + body)(
             build(sid, 1, 500, [(int(sys.argv[3],0) if len(sys.argv)>3 else sid, 0, 0, 5, 0)])), (NODE, PORT))
s.settimeout(secs)
end = time.time() + secs
n = 0
while time.time() < end:
    try:
        d, a = s.recvfrom(65536)
    except socket.timeout:
        break
    typ, txn, mid, mlen = struct.unpack_from('<BHHH', d, 0)
    body = tlvs(d[7:7 + mlen])
    if mid == BUFFERING and typ == RESP:
        print('  response: %r' % body)
        continue
    n += 1
    if n <= 6:
        print('  IND msg=0x%02x len=%d tlvs=%s' % (mid, mlen, sorted(body)))
        for t, v in sorted(body.items()):
            print('     tlv 0x%02x len %2d: %s' % (t, len(v), v[:32].hex()))
print('  %d indication(s) in %gs' % (n, secs))
# tear down
s.sendto((lambda b: struct.pack('<BHHH', REQ, 2, BUFFERING, len(b)) + b)(build(sid, 2, 0, [])),
         (NODE, PORT))
s.close()
