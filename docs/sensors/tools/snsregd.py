#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# snsregd.py - Qualcomm Sensor Registry (SNS_REG) server, Python re-implementation
# of Yassine Oudjana's sns-reg (gitlab.com/msm8996-mainline/sns-reg, GPL-3.0-or-later).
#
# Why a re-implementation: sns-reg is C + SCons + libqrtr, which would need a
# cross-toolchain or an aport before it can run on the device.  The protocol is
# small enough (one request message) that a Python server gets us a live answer
# in one step; the C daemon is the packaged end state.
#
# Protocol (from sns-reg qmi/sns_reg.h + sns_reg.c):
#   service 0x010F, version 2, instance 0
#   SNS_REG_GROUP  msg id 0x0004
#     request : TLV 0x01 = u16 group id
#     response: TLV 0x02 = u16 result, TLV 0x03 = u16 group id,
#               TLV 0x04 = u16 data_len followed by data_len bytes
#   The data blob is the group's keys concatenated, each key contributing
#   key.len bytes of registry[key.id] (little endian); keys with id -1 are
#   padding and contribute zeros.
#
#   snsregd.py [registry.conf] [groups.txt]
import socket, struct, sys, time, os

SERVICE = 0x010F
VERSION = 2
INSTANCE = 0
# ☠️ These were 3/4 here, i.e. BYE/NEW_SERVER -- so this daemon announced a
# BYE instead of publishing SNS_REG and could never receive a request.
from qrtrconst import (QRTR_PORT_CTRL, QRTR_TYPE_NEW_SERVER,
                       QRTR_TYPE_DEL_SERVER)

QMI_REQUEST = 0
QMI_RESPONSE = 2
SNS_REG_GROUP_MSG_ID = 0x0004
QMI_RESULT_SUCCESS = 0
QMI_RESULT_FAILURE = 1


def load_registry(path):
    reg = {}
    for ln in open(path):
        ln = ln.split('#')[0].split()
        if len(ln) == 2:
            reg[int(ln[0])] = int(ln[1])
    return reg


def load_groups(path):
    groups = {}
    for ln in open(path):
        f = ln.split()
        if not f:
            continue
        gid = int(f[0])
        groups[gid] = [tuple(int(x) for x in k.split(':')) for k in f[1:]]
    return groups


def tlvs(buf):
    out = {}
    off = 0
    while off + 3 <= len(buf):
        t = buf[off]
        (l,) = struct.unpack_from('<H', buf, off + 1)
        out[t] = buf[off + 3:off + 3 + l]
        off += 3 + l
    return out


def build_group_data(keys, reg):
    data = bytearray()
    for kid, klen in keys:
        if kid == -1:
            data += b'\x00' * klen
        else:
            v = reg.get(kid, 0)
            data += (v & ((1 << (8 * klen)) - 1)).to_bytes(klen, 'little')
    return bytes(data)


def main():
    regpath = sys.argv[1] if len(sys.argv) > 1 else '/etc/sns-reg.d/registry.conf'
    grppath = sys.argv[2] if len(sys.argv) > 2 else '/etc/sns-reg.d/groups.txt'
    reg = load_registry(regpath)
    groups = load_groups(grppath)
    sys.stderr.write('registry: %d keys, %d groups\n' % (len(reg), len(groups)))

    s = socket.socket(socket.AF_QIPCRTR, socket.SOCK_DGRAM)
    s.bind((s.getsockname()[0], 0))
    node, port = s.getsockname()
    # QRTR packs the QMI version and instance into one field.
    inst = (VERSION & 0xFF) | (INSTANCE << 8)
    s.sendto(struct.pack('<IIIII', QRTR_TYPE_NEW_SERVER, SERVICE, inst, node, port),
             (node, QRTR_PORT_CTRL))
    sys.stderr.write('published SNS_REG 0x%x v%d/i%d at %d:0x%x\n'
                     % (SERVICE, VERSION, INSTANCE, node, port))

    served = miss = 0
    try:
        while True:
            data, addr = s.recvfrom(65536)
            if addr[1] == QRTR_PORT_CTRL or len(data) < 7:
                continue
            typ, txn, msg_id, mlen = struct.unpack_from('<BHHH', data, 0)
            if typ != QMI_REQUEST or msg_id != SNS_REG_GROUP_MSG_ID:
                sys.stderr.write('ignoring type=%d msg=0x%04x from %s\n'
                                 % (typ, msg_id, addr))
                continue
            body = tlvs(data[7:7 + mlen])
            gid = struct.unpack('<H', body[0x01])[0] if 0x01 in body else 0xFFFF

            keys = groups.get(gid)
            if keys is None:
                served_data = b''
                result = QMI_RESULT_FAILURE
                miss += 1
                sys.stderr.write('group %d UNMAPPED\n' % gid)
            else:
                served_data = build_group_data(keys, reg)
                result = QMI_RESULT_SUCCESS
                served += 1

            payload = (struct.pack('<BHH', 0x02, 2, result) +
                       struct.pack('<BHH', 0x03, 2, gid) +
                       struct.pack('<BHH', 0x04, 2 + len(served_data), len(served_data)) +
                       served_data)
            resp = struct.pack('<BHHH', QMI_RESPONSE, txn, msg_id, len(payload)) + payload
            s.sendto(resp, addr)
            if (served + miss) % 25 == 0:
                sys.stderr.write('... %d served, %d unmapped\n' % (served, miss))
    except KeyboardInterrupt:
        pass
    finally:
        s.sendto(struct.pack('<IIIII', QRTR_TYPE_DEL_SERVER, SERVICE, inst, node, port),
                 (node, QRTR_PORT_CTRL))
        s.close()
        sys.stderr.write('done: %d served, %d unmapped\n' % (served, miss))


if __name__ == '__main__':
    main()
