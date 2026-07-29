#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# mbnid.py - read the signing identity out of a Qualcomm MBN firmware image.
#
# Why: "would two devices' firmware collide if the device tree named them
# without a path" is answerable from the images themselves. A signed MBN carries
# a hash segment whose certificate chain encodes SW_ID (which subsystem),
# HW_ID, OEM_ID and MODEL_ID (which device) in the subject's OU fields.
#
# Layout, all little-endian:
#   ELF32, QUALCOMM DSP6 or AARCH64. One program header has bits 20..22 of
#   p_flags equal to 2 (QCOM_MDT_TYPE_HASH); that segment holds:
#     u32 image_id, header_vsn, image_src, image_dest, image_size,
#         code_size, signature_ptr, signature_size, cert_chain_ptr,
#         cert_chain_size            (40 bytes)
#     code_size bytes of hashes, signature_size bytes of signature,
#     then cert_chain_size bytes of concatenated DER certificates.
#
# Usage:  mbnid.py <file> [<file> ...]        (needs openssl on PATH)
import struct, subprocess, sys, os, tempfile

HASH_SEGMENT = 2


def hash_segment(d):
    phoff, = struct.unpack_from('<I', d, 0x1c)
    phentsize, phnum = struct.unpack_from('<HH', d, 0x2a)
    for i in range(phnum):
        o = phoff + i * phentsize
        _t, p_off, _va, _pa, p_filesz, _memsz, p_flags, _al = \
            struct.unpack_from('<8I', d, o)
        if (p_flags >> 20) & 0x7 == HASH_SEGMENT:
            return p_off, p_filesz
    return None


def first_cert(certs):
    """The chain is concatenated DER; take the leaf, which carries the IDs."""
    if not certs or certs[0] != 0x30:
        return None
    nb = certs[1] & 0x7f
    if certs[1] & 0x80:
        ln = int.from_bytes(certs[2:2 + nb], 'big')
        total = 2 + nb + ln
    else:
        total = 2 + certs[1]
    return certs[:total]


def ids(path):
    with open(path, 'rb') as f:
        d = f.read(16384)
    hs = hash_segment(d)
    if not hs:
        return None, 'no hash segment'
    off, size = hs
    if off + size > len(d):
        with open(path, 'rb') as f:
            f.seek(off)
            h = f.read(size)
    else:
        h = d[off:off + size]

    (_img, _vsn, _src, _dst, _isz, csize, _sptr, ssize, _cptr, csz) = \
        struct.unpack_from('<10I', h, 0)
    certs = h[0x28 + csize + ssize: 0x28 + csize + ssize + csz]
    leaf = first_cert(certs)
    if not leaf:
        return None, 'no certificate chain'

    with tempfile.NamedTemporaryFile(suffix='.der', delete=False) as t:
        t.write(leaf)
        tmp = t.name
    try:
        out = subprocess.run(
            ['openssl', 'x509', '-inform', 'DER', '-in', tmp, '-noout',
             '-subject'], capture_output=True, text=True).stdout
    finally:
        os.unlink(tmp)

    f = {}
    for part in out.split(','):
        part = part.strip()
        if part.startswith('OU='):
            v = part[3:].split()
            if len(v) >= 3:
                f[v[2]] = v[1]
        elif part.startswith('CN='):
            f['CN'] = part[3:]
    return f, None


def main():
    if len(sys.argv) < 2:
        print(__doc__.strip().splitlines()[-1])
        return 1
    for p in sys.argv[1:]:
        f, err = ids(p)
        name = os.path.basename(p)
        if err:
            print('%-16s  %s' % (name, err))
            continue
        print('%-16s  SW_ID=%s HW_ID=%s OEM_ID=%s MODEL_ID=%s  signer=%s'
              % (name, f.get('SW_ID', '?'), f.get('HW_ID', '?'),
                 f.get('OEM_ID', '?'), f.get('MODEL_ID', '?'),
                 f.get('CN', '?')))
    return 0


sys.exit(main())
