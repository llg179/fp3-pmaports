#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# qmiprobe.py <node> <port> [msg_ids...] - send empty QMI requests to a QRTR
# endpoint and print whatever comes back.  Used to ask the SSC's Sensor Manager
# whether it is alive after the registry services made its init succeed.
import socket, struct, sys, time, binascii

def main():
    node = int(sys.argv[1], 0)
    port = int(sys.argv[2], 0)
    ids = [int(x, 0) for x in sys.argv[3:]] or [0x0001, 0x0004, 0x0006, 0x0020, 0x0021]
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((s.getsockname()[0], 0))
    print('from %s -> %d:0x%x' % (s.getsockname(), node, port))
    s.settimeout(2.0)
    for i, mid in enumerate(ids):
        req = struct.pack('<BHHH', 0x00, i + 1, mid, 0)
        try:
            s.sendto(req, (node, port))
        except OSError as e:
            print('msg 0x%04x: send failed: %s' % (mid, e)); continue
        t0 = time.monotonic()
        got = False
        while time.monotonic() - t0 < 2.0:
            try:
                data, addr = s.recvfrom(65536)
            except socket.timeout:
                break
            got = True
            print('msg 0x%04x <- %s: %s' % (mid, addr, binascii.hexlify(data).decode()))
        if not got:
            print('msg 0x%04x: no reply' % mid)
    s.close()

if __name__ == '__main__':
    main()
