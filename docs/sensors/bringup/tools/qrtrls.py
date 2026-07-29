#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# qrtrls.py - enumerate every QRTR service the kernel name service knows about.
#
# The codes come from qrtrconst.py (kernel uapi header).  Note that the OLD
# qrtr_lookup.py was right all along -- NEW_LOOKUP 10 / NEW_SERVER 4 -- and an
# earlier "fix" in this file to 9/3 was the thing that broke it, printing zero
# services even for a service that was demonstrably registered.
# The instance field packs version | instance << 8.
import socket, struct, sys

from qrtrconst import (QRTR_PORT_CTRL, QRTR_TYPE_NEW_SERVER,
                       QRTR_TYPE_NEW_LOOKUP, QRTR_TYPE_DEL_LOOKUP)

WANT = {0x010F: 'SNS_REG', 0x0100: 'SENSOR_MGR(256)', 0x0004: 'DMS',
        0x0002: 'WDS', 0x0003: 'NAS', 0x001A: 'WDA', 0x0015: 'RFS',
        0x0040: 'SERVREG_LOC', 0x0042: 'SERVREG_NOTIF'}


def main():
    timeout = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    local = s.getsockname()[0]
    s.bind((local, 0))
    # service=0 instance=0 => match everything
    s.sendto(struct.pack('<IIIII', QRTR_TYPE_NEW_LOOKUP, 0, 0, 0, 0),
             (local, QRTR_PORT_CTRL))
    s.settimeout(timeout)

    rows = []
    while True:
        try:
            data, addr = s.recvfrom(65536)
        except socket.timeout:
            break
        if len(data) < 20:
            continue
        cmd, svc, inst, node, port = struct.unpack_from('<IIIII', data, 0)
        if cmd != QRTR_TYPE_NEW_SERVER:
            continue
        if (svc, inst, node, port) == (0, 0, 0, 0):
            break
        rows.append((node, svc, inst & 0xFF, inst >> 8, port))

    s.sendto(struct.pack('<IIIII', QRTR_TYPE_DEL_LOOKUP, 0, 0, 0, 0),
             (local, QRTR_PORT_CTRL))
    s.close()

    print('# local node = %d' % local)
    print('# node  service        ver  inst   port')
    for node, svc, ver, inst, port in sorted(rows):
        name = WANT.get(svc, '')
        print('  %-4d  %5d 0x%04x  %3d  %4d  0x%04x  %s'
              % (node, svc, svc, ver, inst, port, name))
    print('# total: %d services on nodes %s'
          % (len(rows), sorted(set(r[0] for r in rows))))
    for svc, name in sorted(WANT.items()):
        hits = [r for r in rows if r[1] == svc]
        print('# %-16s %s' % (name, 'node %s' % [h[0] for h in hits]
                              if hits else 'ABSENT'))


if __name__ == '__main__':
    main()
