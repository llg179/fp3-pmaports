#!/usr/bin/env python3
"""Sample the WCD9335's own plug status against what the driver reports.

Three things are logged together, once per change:

  RESULT_3 (0x0619) bit 3   the codec's settled mechanical plug status,
                            set while the jack is out
  MECH     (0x0614) bit 5   the direction L_DET is currently armed for
  SW_HEADPHONE_INSERT,      what the driver reports to userspace
  SW_MICROPHONE_INSERT

The driver derives its state by flipping a flag on every L_DET edge, so any
disagreement between the hardware columns and the switch columns is the
counter having drifted away from reality - which is what this tool exists to
show. Running it across several physical insert/remove cycles also measures
whether RESULT_3 tracks the plug at all, and how long it takes to settle.

Run as root (debugfs), for example:

    systemd-run --unit=jackprobe --collect \
        sh -c 'python3 jack-probe.py 300 > /var/log/jackprobe.log 2>&1'

then plug and unplug a headset a few times and read the log.

Note on the read path: the register value is fetched by seeking straight to
that register's line in the regmap debugfs dump. Reading the whole dump would
put a few hundred SLIMbus transactions on the bus per sample and perturb the
very thing being measured. The line is checked to start with the expected
register number, and the offset is re-resolved if it ever does not, so a
shifted dump cannot silently produce wrong values. Cross-check the fast path
against a full read of the file before trusting a surprising result.
"""
import fcntl
import glob
import os
import sys
import time

PERIOD = 0.02                       # seconds between samples
EVIOCGSW = 0x8008451b               # EVIOCGSW(len=8)
EVIOCGNAME = 0x82004506             # EVIOCGNAME(len=64)
SW_HEADPHONE_INSERT = 0x02
SW_MICROPHONE_INSERT = 0x04

WCD9335_ANA_MBHC_RESULT_3 = 0x0619
WCD9335_ANA_MBHC_MECH = 0x0614
RESULT_3_PLUG_REMOVED = 0x08        # set while the jack is out
MECH_DETECT_TYPE = 0x20             # set means armed for removal


def read_all(path):
    """Read a debugfs file in full - one read() only returns the first slice."""
    blob = b""
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            blob += chunk
    return blob


def regmap_path():
    """The codec's regmap dump. Its name is the SLIMbus logical address, which
    is stable within a boot but not worth hardcoding."""
    cands = [p for p in glob.glob("/sys/kernel/debug/regmap/*") if ":1a0:" in p]
    if not cands:
        sys.exit("no wcd9335 regmap under /sys/kernel/debug/regmap")
    return sorted(cands)[-1] + "/registers"


class RegLine:
    """Byte offset of one register's line in the dump, resolved once."""

    def __init__(self, path, reg):
        self.path = path
        self.tag = ("%04x: " % reg).encode()
        blob = read_all(path)
        off = blob.find(b"\n" + self.tag)
        if off < 0:
            sys.exit("register %s is not in the dump" % self.tag.decode())
        self.off = off + 1
        self.len = len(self.tag) + 3

    def read(self, fh):
        fh.seek(self.off)
        line = fh.read(self.len)
        if not line.startswith(self.tag):
            return None                 # dump shifted - caller re-resolves
        return int(line[len(self.tag):].strip(), 16)


def open_jack():
    """The codec's headset-jack input device, matched by name because the
    event node number moves between boots."""
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        except OSError:
            continue
        name = bytearray(64)
        try:
            fcntl.ioctl(fd, EVIOCGNAME, name)
        except OSError:
            os.close(fd)
            continue
        if b"Headset Jack" in bytes(name):
            return fd, path
        os.close(fd)
    sys.exit("no headset jack input device found")


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    path = regmap_path()
    result3 = RegLine(path, WCD9335_ANA_MBHC_RESULT_3)
    mech = RegLine(path, WCD9335_ANA_MBHC_MECH)
    fd, jack = open_jack()

    print("# started %s" % time.strftime("%H:%M:%S"))
    print("# regmap %s   jack %s   period %d ms"
          % (path, jack, PERIOD * 1000))
    print("# t(s)  RESULT_3  plug(hw)  MECH  armed_for  SW_HP  SW_MIC")

    last = None
    start = time.time()
    fh = open(path, "rb")
    while time.time() - start < seconds:
        r = result3.read(fh)
        m = mech.read(fh)
        if r is None or m is None:      # offsets moved: reopen and re-resolve
            fh.close()
            result3 = RegLine(path, WCD9335_ANA_MBHC_RESULT_3)
            mech = RegLine(path, WCD9335_ANA_MBHC_MECH)
            fh = open(path, "rb")
            continue

        bits = bytearray(8)
        try:
            fcntl.ioctl(fd, EVIOCGSW, bits)
        except OSError:
            bits = bytearray(8)
        sw = int.from_bytes(bits, "little")

        row = (r, m,
               bool(sw & (1 << SW_HEADPHONE_INSERT)),
               bool(sw & (1 << SW_MICROPHONE_INSERT)))
        if row != last:
            print("%7.2f  %8s  %8s  %4s  %9s  %5s  %5s"
                  % (time.time() - start,
                     "%02x" % r,
                     "OUT" if r & RESULT_3_PLUG_REMOVED else "IN",
                     "%02x" % m,
                     "removal" if m & MECH_DETECT_TYPE else "insertion",
                     row[2], row[3]), flush=True)
            last = row
        time.sleep(PERIOD)

    fh.close()
    os.close(fd)
    print("# done")


main()
