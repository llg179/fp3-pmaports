#!/usr/bin/env python3
"""Watch every MBHC register on the WCD9335 while a jack is plugged and pulled.

Deliberately opinion-free: it logs the whole MBHC register block raw, in hex
and in binary, and prints a line whenever *anything* changes. Nothing is
filtered by what the reader expects to be interesting, because the driver has
already been wrong once about which bit carries the plug status - watching only
the bit you believe in is how that stays undiscovered.

Alongside the registers it logs SW_HEADPHONE_INSERT and SW_MICROPHONE_INSERT,
i.e. what the driver reports to userspace, so hardware and report can be
compared edge by edge.

A decoding of RESULT_3 is printed at the end for convenience only. It comes
from the five in-tree codecs of the same MBHC family (wcd934x, wcd937x,
wcd938x, wcd939x, pm4125), which map that register identically - but the raw
columns above it are the measurement, and they stand on their own if the
decoding turns out not to apply to this codec.

Run as root (debugfs), for example:

    systemd-run --unit=jackprobe --collect \
        sh -c 'python3 jack-probe.py 300 > /var/log/jackprobe.log 2>&1'

then plug and unplug a headset several times - at least twice per accessory,
since a state that drifts one edge at a time cannot be seen in a single cycle.
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

# The whole MBHC block: the ANA_MBHC registers, the button thresholds, and the
# MBHC_NEW control/status registers. Names are for the report only - every one
# of them is sampled whatever it is called.
REGISTERS = [
    (0x0614, "ANA_MECH"),
    (0x0615, "ANA_ELECT"),
    (0x0616, "ANA_ZDET"),
    (0x0617, "RESULT_1"),
    (0x0618, "RESULT_2"),
    (0x0619, "RESULT_3"),
    (0x061a, "BTN0"), (0x061b, "BTN1"), (0x061c, "BTN2"), (0x061d, "BTN3"),
    (0x061e, "BTN4"), (0x061f, "BTN5"), (0x0620, "BTN6"), (0x0621, "BTN7"),
    (0x0656, "CTL_1"),
    (0x0657, "CTL_2"),
    (0x0658, "PLUG_DETECT_CTL"),
    (0x065a, "ZDET_RAMP_CTL"),
]


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
    """Byte offset of one register's line in the dump, resolved once.

    Seeking to the line keeps a sample to a handful of SLIMbus transactions.
    Reading the whole dump every 20 ms would put hundreds on the bus and
    perturb the thing being measured.
    """

    def __init__(self, blob, reg):
        self.tag = ("%04x: " % reg).encode()
        off = blob.find(b"\n" + self.tag)
        if off < 0:
            self.off = None
            return
        self.off = off + 1
        self.len = len(self.tag) + 3

    def read(self, fh):
        if self.off is None:
            return None
        fh.seek(self.off)
        line = fh.read(self.len)
        if not line.startswith(self.tag):
            return None                 # dump shifted - caller re-resolves
        try:
            return int(line[len(self.tag):].strip(), 16)
        except ValueError:
            return None


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


def resolve(path):
    blob = read_all(path)
    lines = {}
    for reg, name in REGISTERS:
        rl = RegLine(blob, reg)
        if rl.off is None:
            print("# %s (%04x) is not in the dump - skipped" % (name, reg))
            continue
        lines[reg] = rl
    return lines


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    path = regmap_path()
    lines = resolve(path)
    present = [(r, n) for r, n in REGISTERS if r in lines]
    fd, jack = open_jack()

    print("# started %s" % time.strftime("%H:%M:%S"))
    print("# regmap %s   jack %s   period %d ms" % (path, jack, PERIOD * 1000))
    print("# every MBHC register is sampled; a line is printed on any change")
    print("#")
    print("# %-7s %s  %s" % ("t(s)", "  ".join("%-8s" % n for _, n in present),
                             "SW_HP SW_MIC"))

    last = None
    start = time.time()
    fh = open(path, "rb")
    while time.time() - start < seconds:
        vals = []
        stale = False
        for reg, _ in present:
            v = lines[reg].read(fh)
            if v is None:
                stale = True
                break
            vals.append(v)
        if stale:                       # offsets moved: reopen and re-resolve
            fh.close()
            lines = resolve(path)
            present = [(r, n) for r, n in REGISTERS if r in lines]
            fh = open(path, "rb")
            continue

        bits = bytearray(8)
        try:
            fcntl.ioctl(fd, EVIOCGSW, bits)
        except OSError:
            bits = bytearray(8)
        sw = int.from_bytes(bits, "little")
        hp = bool(sw & (1 << SW_HEADPHONE_INSERT))
        mic = bool(sw & (1 << SW_MICROPHONE_INSERT))

        row = tuple(vals) + (hp, mic)
        if row != last:
            cells = " ".join("%02x/%s" % (v, format(v, "08b")) for v in vals)
            print("%9.2f %s  %5s %5s" % (time.time() - start, cells, hp, mic),
                  flush=True)
            if last is not None:        # name what moved, raw, no interpretation
                changed = [present[i][1]
                           for i in range(len(vals)) if vals[i] != last[i]]
                if changed:
                    print("%9s   changed: %s" % ("", ", ".join(changed)),
                          flush=True)
            last = row
        time.sleep(PERIOD)

    fh.close()
    os.close(fd)
    print("# done")
    print("#")
    print("# RESULT_3 decoding, per wcd934x/937x/938x/939x/pm4125 (reference only):")
    print("#   bit0-2 BTN_RESULT   bit3 HS_COMP_RESULT   bit4 SWCH_LEVEL_REMOVE")
    print("#   bit5 MIC_SCHMT      bit6 HPHR_SCHMT        bit7 HPHL_SCHMT")
    print("# ANA_MECH: bit7 L_DET_EN  bit6 GND_DET_EN  bit5 MECH_DETECTION_TYPE")
    print("#   bit4 HPHL_PLUG_TYPE  bit3 GND_PLUG_TYPE  bit2 HS_L_DET_PULL_UP_COMP")
    print("#   bit0 SW_HPH_LP_100K_TO_GND")


main()
