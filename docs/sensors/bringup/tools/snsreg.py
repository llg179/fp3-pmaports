#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# snsreg.py - advertise QMI service 0x10F (the one sensors.qti owns on Ubuntu
# Touch, node 1 port 0x37) over QRTR and dump every request the ADSP sends us.
#
# Purpose: the SSC sensor task completes its 12-message prologue and then waits.
# On the oracle it resumes 3.68s later with L307 (1, 271, 0) - 271 == 0x10F.
# If that reading is right, simply publishing the service here makes the ADSP
# talk to us, and the request bytes are the protocol we have to implement.
#
#   snsreg.py <secs> [outfile]
import socket, struct, sys, time, binascii, select

SERVICE = 0x10F
INSTANCE = 0x2          # raw instance field from the UT dump: version 2, instance 0
# ☠️ The control codes used to be hardcoded here and were WRONG twice (2, then
# 3, where NEW_SERVER is 4) -- every "publish" was really a BYE.  They now come
# from qrtrconst.py, which is a transcription of the kernel uapi header.
from qrtrconst import (QRTR_PORT_CTRL, QRTR_TYPE_NEW_SERVER,
                       QRTR_TYPE_DEL_SERVER, CTRL_NAME)


def ctrl_pkt(cmd, service=0, instance=0, node=0, port=0):
    return struct.pack('<IIIII', cmd, service, instance, node, port)


def ctrl_decode(b):
    if len(b) < 20:
        return '  ctrl (short, %d bytes)' % len(b)
    cmd, svc, inst, node, port = struct.unpack_from('<IIIII', b, 0)
    return ('  ctrl: %s service=0x%x instance=0x%x node=%d port=0x%x'
            % (CTRL_NAME.get(cmd, '?%d' % cmd), svc, inst, node, port))


def qmi_decode(b):
    """Decode a QMI service message header + TLV list (best effort)."""
    if len(b) < 7:
        return '  (short, %d bytes)' % len(b)
    flags, txn, msg_id, ln = struct.unpack_from('<BHHH', b, 0)
    kind = {0: 'REQUEST', 1: 'RESPONSE', 2: 'INDICATION'}.get(flags & 3, '?%d' % flags)
    out = ['  hdr: flags=0x%02x(%s) txn=0x%04x msg_id=0x%04x len=%d'
           % (flags, kind, txn, msg_id, ln)]
    off = 7
    while off + 3 <= len(b):
        t = b[off]
        (l,) = struct.unpack_from('<H', b, off + 1)
        val = b[off + 3:off + 3 + l]
        out.append('    TLV 0x%02x len=%d %s' % (t, l, binascii.hexlify(val).decode()))
        off += 3 + l
    if off != len(b):
        out.append('    (trailing %d bytes)' % (len(b) - off))
    return '\n'.join(out)


def load_services(path):
    out = []
    for ln in open(path):
        ln = ln.split('#')[0].split()
        if len(ln) == 2:
            out.append((int(ln[0]), int(ln[1])))
    return out


def main():
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0
    outp = sys.argv[2] if len(sys.argv) > 2 else '/tmp/snsreg.log'
    svclist = load_services(sys.argv[3]) if len(sys.argv) > 3 else [(SERVICE, INSTANCE)]
    fh = open(outp, 'w')

    def log(s):
        sys.stdout.write(s + '\n'); sys.stdout.flush()
        fh.write(s + '\n'); fh.flush()

    # One socket (= one port) per service, the way the oracle's sensors.qti does
    # it: there every node-1 service sat on its own port (0x2d, 0x2e, ...).
    socks = {}
    for svc, inst in svclist:
        s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
        # bind() only accepts the LOCAL node id (anything else -> EINVAL); an
        # unbound socket already reports it via getsockname(), so ask first.
        local_nid = s.getsockname()[0]
        s.bind((local_nid, 0))
        node, port = s.getsockname()
        s.sendto(ctrl_pkt(QRTR_TYPE_NEW_SERVER, svc, inst, node, port),
                 (node, QRTR_PORT_CTRL))
        socks[s] = (svc, inst, node, port)
    log('published %d service(s), one port each: %s' % (
        len(svclist),
        ' '.join('%d/%d@0x%x' % (v[0], v[1], v[3]) for v in socks.values())))

    t0 = time.monotonic()
    n = 0
    try:
        while time.monotonic() - t0 < dur:
            r, _, _ = select.select(list(socks), [], [], 0.5)
            for s in r:
                data, addr = s.recvfrom(65536)
                svc, inst, _, port = socks[s]
                n += 1
                log('[%7.3f] #%d svc=%d/%d port=0x%x <- node=%s port=0x%x  %d bytes'
                    % (time.monotonic() - t0, n, svc, inst, port,
                       addr[0], addr[1], len(data)))
                log('  raw: ' + binascii.hexlify(data).decode())
                log(ctrl_decode(data) if addr[1] == QRTR_PORT_CTRL
                    else qmi_decode(data))
    finally:
        for s, (svc, inst, node, port) in socks.items():
            try:
                s.sendto(ctrl_pkt(QRTR_TYPE_DEL_SERVER, svc, inst, node, port),
                         (node, QRTR_PORT_CTRL))
            except OSError:
                pass
            s.close()
        log('withdrew %d service(s)' % len(socks))
        log('done: %d packets' % n)
        fh.close()


if __name__ == '__main__':
    main()
