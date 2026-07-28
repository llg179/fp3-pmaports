#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Capture ADSP F3 debug messages, focused on the SENSORS subsystem (ss_id 53),
# across an optional ADSP SSR.  Unlike diagcap.py this locates the ADSP
# remoteproc by NAME (not a hardcoded index) and RE-BINDS the DIAG rpmsg
# channels itself, because an SSR destroys and recreates them unbound.
#   sensdiag.py <secs> [ssr]
import os, sys, glob, select, time, struct

SENSOR_SSID = 53


def adsp_rproc():
    for r in glob.glob('/sys/class/remoteproc/remoteproc*'):
        try:
            if open(r + '/name').read().strip() == 'adsp':
                return os.path.basename(r)
        except OSError:
            pass
    return None


RPROC = adsp_rproc()
RP_STATE = '/sys/class/remoteproc/%s/state' % RPROC


def bind_diag():
    """Attach rpmsg_chrdev to this remoteproc's DIAG + DIAG_CNTL channels."""
    for d in glob.glob('/sys/bus/rpmsg/devices/%s:*' % RPROC):
        base = os.path.basename(d)
        if '.DIAG.' not in base and '.DIAG_CNTL.' not in base:
            continue
        if os.path.exists(d + '/driver'):
            continue
        try:
            with open(d + '/driver_override', 'w') as f:
                f.write('rpmsg_chrdev')
            with open('/sys/bus/rpmsg/drivers/rpmsg_chrdev/bind', 'w') as f:
                f.write(base)
        except OSError:
            pass


def find_devs():
    data = cntl = None
    for n in glob.glob('/sys/class/rpmsg/rpmsg*'):
        try:
            name = open(n + '/name').read().strip()
            real = os.path.realpath(n)
        except OSError:
            continue
        if RPROC not in real:
            continue
        dev = '/dev/' + os.path.basename(n)
        if name == 'DIAG':
            data = dev
        elif name == 'DIAG_CNTL':
            cntl = dev
    return data, cntl


def pkt_feature():
    return struct.pack('<III', 8, 6, 2) + bytes([1, 0])


def pkt_f3():
    # DIAG_MSG_CONFIG: enable every F3 level on every ss_id range
    return (struct.pack('<II', 11, 15) + bytes([1, 2, 0]) +
            struct.pack('<HHI', 0, 0, 1) + struct.pack('<I', 0xFFFFFFFF))


def arm(cntl):
    try:
        fd = os.open(cntl, os.O_RDWR | os.O_NONBLOCK)
    except OSError:
        return False
    for p in (pkt_feature(), pkt_f3()):
        try:
            os.write(fd, p)
        except OSError:
            pass
    os.close(fd)
    return True


def unescape(raw):
    u = bytearray(); esc = False
    for b in raw:
        if esc:
            u.append(b ^ 0x20); esc = False
        elif b == 0x7d:
            esc = True
        else:
            u.append(b)
    return bytes(u)


def parse_f3(p):
    if len(p) < 20:
        return None
    cmd = p[0]
    if cmd not in (0x79, 0x92):
        return None
    num_args = p[2]
    line = struct.unpack_from('<H', p, 12)[0]
    ssid = struct.unpack_from('<H', p, 14)[0]
    off = 20 + 4 * num_args
    parts = p[off:].split(b'\x00')
    if cmd == 0x79:
        fmt = parts[0].decode('ascii', 'replace') if parts else ''
        fname = parts[1].decode('ascii', 'replace') if len(parts) > 1 else ''
    else:
        qsr = struct.unpack_from('<I', p, 20)[0] if len(p) >= 24 else 0
        fmt = 'QSR#%08x' % qsr
        fname = ''
    return (cmd, ssid, line, fmt, fname)


GREP = ['sns', 'sensor', 'smgr', 'ssc', 'prox', 'alsprx', 'light', 'accel',
        'gyro', 'mag', 'dsps', 'sam', 'registry', 'sns_reg', 'ddf', 'i2c']


def main():
    global RPROC, RP_STATE
    secs = float(sys.argv[1])
    do_ssr = 'ssr' in sys.argv[2:]
    # Boot-armed use: the remoteproc devices do not exist yet when this starts
    # (sysinit runs long before the ADSP driver probes), so wait for it instead
    # of giving up -- an immediate 'no adsp remoteproc found' exit is how the
    # first boot-armed run silently captured nothing.
    for _ in range(600):
        RPROC = adsp_rproc()
        if RPROC:
            break
        time.sleep(0.1)
    if RPROC is None:
        print('no adsp remoteproc found after 60s'); return
    RP_STATE = '/sys/class/remoteproc/%s/state' % RPROC
    print('[adsp] %s (%s)' % (RPROC, open(RP_STATE).read().strip()))
    # Default output goes to the rootfs, not /tmp: when armed at sysinit a later
    # tmpfs mount over /tmp hides everything written before it.
    rawpath = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != 'ssr' \
        else '/home/fp3/adsp_sens_f3.bin'
    rawf = open(rawpath, 'wb')

    bind_diag()
    if do_ssr:
        try:
            with open(RP_STATE, 'w') as f: f.write('stop')
            time.sleep(1.0)
            with open(RP_STATE, 'w') as f: f.write('start')
            print('[ssr] adsp stop+start issued')
        except OSError as e:
            print('[ssr] FAILED:', e)

    end = time.monotonic() + secs
    dfd = None; last_arm = 0.0; last_bind = 0.0
    buf = bytearray(); seen = {}; hits = []; sens = []; total = 0

    while time.monotonic() < end:
        now = time.monotonic()
        if now - last_bind > 0.5:
            bind_diag(); last_bind = now
        data, cntl = find_devs()
        if not data or not cntl:
            if dfd is not None:
                os.close(dfd); dfd = None
            time.sleep(0.1); continue
        if now - last_arm > 0.25:
            arm(cntl); last_arm = now
        if dfd is None:
            try:
                dfd = os.open(data, os.O_RDWR | os.O_NONBLOCK)
            except OSError:
                time.sleep(0.05); continue
        r, _, _ = select.select([dfd], [], [], 0.2)
        if dfd not in r:
            continue
        try:
            d = os.read(dfd, 32768)
        except OSError:
            os.close(dfd); dfd = None; continue
        if not d:
            continue
        rawf.write(d); rawf.flush(); buf += d
        while b'\x7e' in buf:
            idx = buf.index(b'\x7e')
            frame = bytes(buf[:idx]); del buf[:idx + 1]
            if not frame:
                continue
            payload = unescape(frame)
            if len(payload) <= 2:
                continue
            m = parse_f3(payload[:-2])
            if not m:
                continue
            total += 1
            seen[m[1]] = seen.get(m[1], 0) + 1
            if m[1] == SENSOR_SSID:
                sens.append(m)
            text = (m[3] + ' ' + m[4]).lower()
            if any(t in text for t in GREP):
                hits.append(m)
    if dfd is not None:
        os.close(dfd)
    rawf.close()

    print('\n==== SUMMARY: %d F3 msgs, %d raw bytes -> %s ====' %
          (total, os.path.getsize(rawpath), rawpath))
    print('ss_id histogram:')
    for ss in sorted(seen, key=lambda k: -seen[k]):
        mark = '  <== SENSORS' if ss == SENSOR_SSID else ''
        print('   ss_id=%-6d %d%s' % (ss, seen[ss], mark))

    def dump(title, lst):
        print('\n==== %s (%d msgs) ====' % (title, len(lst)))
        uniq = set()
        for cmd, ssid, line, fmt, fname in lst:
            key = (ssid, line, fmt[:60])
            if key in uniq:
                continue
            uniq.add(key)
            print('  [%s ss=%d L%d %s] %s' %
                  ('EXT' if cmd == 0x79 else 'QSR', ssid, line, fname, fmt))

    dump('SENSORS ss_id=%d' % SENSOR_SSID, sens)
    dump('SENSOR-ISH TEXT (any ss_id)', hits)


if __name__ == '__main__':
    main()
