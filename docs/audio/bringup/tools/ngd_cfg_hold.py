#!/usr/bin/env python3
"""
NGD_CFG.ENABLE HOLD-teszt.

UJ TENY (2026-07-22 ejszaka, ngd_decay.py):
    A NGD_CFG (0x0c141000) ENABLE bitje HARDVERESEN ONMAGAT TORLI.
    Beirva 0x1 -> ugyanabban az utasitas-folyamban 0x1-et olvas vissza es a
    NGD_STATUS 0x40c -> 0x40d-re valt, DE 100 ms-en belul mindketto visszaall
    0x40c / 0x0-ra. Ezert latszik a boot-idei timeout-dumpban CFG=0x0 kozvetlenul
    a qcom_slim_ngd_setup() irasa utan -- NEM eldobott iras, hanem HW self-clear.

HIPOTEZIS
    Ha az ADSP framer-inditasa azt varja, hogy az AP-oldali NGD ENABLE-je
    ALLJON (nem csak egy pillanatra villanjon), akkor a self-clear egy
    kor-fuggoseget zar be: nincs frame -> ENABLE eldol -> az ADSP sosem latja
    az engedelyezett NGD-t -> nem indit framet. Ha az ENABLE-t FOLYAMATOSAN
    tartjuk (tight loop), a kor megtorik.

MERES
    - HOLD kozben figyeljuk: NGD_STATUS (LADDR bit1!), NGD_INT_STAT,
      INTF_STAT (FS/SFS/MS bit 11/12/13), FRM_STAT.
    - PASS = INTF_STAT != 0 (a framer framel), VAGY NGD_STATUS & BIT(1) (laddr),
      VAGY a parhuzamosan futo driver-probe "capability exchange timed-out"
      helyett sikert jelent.
    - Ez a legjobb fajta teszt: a hipotezis pontosan az uj tenybol kovetkezik,
      es van valodi PASS-utja.

GUARDRAIL
    Minden 200. iteracioban ujraellenorizve rproc2 == running. A NGD_CFG-t a
    driver maga is irja ugyanezzel az ertekkel -> a normal envelopeon belul.
    Kilepeskor visszaallitjuk 0-ra (amugy is oda esne vissza).
"""

import argparse
import mmap
import os
import struct
import sys
import time

CTRL = 0x0C140000
MAP_LEN = 0x2000
NGD = 0x1000

NGD_CFG = 0x00
NGD_STATUS = 0x04
NGD_INT_STAT = 0x14
FRM_STAT = 0x404
INTF_STAT = 0x604
FRM_INT_STAT = 0x414
INTF_INT_STAT = 0x614

RPROC = "/sys/class/remoteproc/remoteproc2/state"


def rf(p):
    try:
        return open(p).read().strip()
    except OSError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=40.0)
    ap.add_argument("--val", default="0x7",
                    help="a folyamatosan beirt NGD_CFG ertek (0x7 = ENABLE|RX|TX)")
    args = ap.parse_args()
    val = int(args.val, 0)

    if rf(RPROC) != "running":
        print("GATE FAIL: remoteproc2 nem running", file=sys.stderr)
        return 2

    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    mm = mmap.mmap(fd, MAP_LEN, mmap.MAP_SHARED,
                   mmap.PROT_READ | mmap.PROT_WRITE, offset=CTRL)
    os.close(fd)

    r = lambda o: struct.unpack("<I", mm[o:o + 4])[0]
    w = lambda o, v: mm.__setitem__(slice(o, o + 4), struct.pack("<I", v))

    watch = [("NGD_STATUS", NGD + NGD_STATUS), ("NGD_INT_STAT", NGD + NGD_INT_STAT),
             ("INTF_STAT", INTF_STAT), ("FRM_STAT", FRM_STAT),
             ("FRM_INT_STAT", FRM_INT_STAT), ("INTF_INT_STAT", INTF_INT_STAT)]

    def snap():
        return tuple(r(o) for _, o in watch)

    base = snap()
    print(f"# HOLD NGD_CFG=0x{val:x} {args.duration}s")
    print("# baseline: " + "  ".join(f"{n}=0x{v:08x}" for (n, _), v in zip(watch, base)))
    sys.stdout.flush()

    t0 = time.time()
    n = 0
    hits = 0
    last = base
    laddr_seen = False
    framing_seen = False
    try:
        while time.time() - t0 < args.duration:
            w(NGD + NGD_CFG, val)
            n += 1
            if n % 200 == 0:
                if rf(RPROC) != "running":
                    print("GATE FAIL kozben -> leallas", file=sys.stderr)
                    break
                cur = snap()
                if cur != last:
                    hits += 1
                    t = time.time() - t0
                    print(f"  CHANGE t={t:7.3f}s " +
                          "  ".join(f"{nm}=0x{v:08x}" for (nm, _), v in zip(watch, cur)))
                    sys.stdout.flush()
                    last = cur
                if cur[0] & (1 << 1):
                    laddr_seen = True
                if cur[2] != 0:
                    framing_seen = True
    finally:
        w(NGD + NGD_CFG, 0)
        fin = snap()
        mm.close()

    print(f"# iteraciok: {n}, valtozasok: {hits}")
    print("# vegallapot: " + "  ".join(f"{nm}=0x{v:08x}" for (nm, _), v in zip(watch, fin)))
    verdict = "PASS" if (laddr_seen or framing_seen) else "NEGATIV"
    print(f"# VERDIKT: {verdict} (laddr={laddr_seen} framing={framing_seen})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
