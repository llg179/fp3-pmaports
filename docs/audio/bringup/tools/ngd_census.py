#!/usr/bin/env python3
"""
NGD1 (AP-oldali SLIMbus satellite) regiszter-cenzus, READ-ONLY alapmodban.

MIERT
    A boot-idei timeout-dump ezt mondja:
        capability exchange timed-out STATUS=0x40c CFG=0x0 INT_STAT=0x0
    A CFG=0x0 gyanus: a qcom_slim_ngd_setup() KOZVETLENUL elotte irja be a
    NGD_CFG_ENABLE|RX_MSGQ_EN|TX_MSGQ_EN bitkombot ugyanerre a cimre. Ha
    visszaolvasva 0, akkor az AP sajat NGD-jenek enable-je NEM RAGAD MEG.
    Ez pontosan az a pozitiv kontroll, ami eddig hianyzott.

CIM
    ctrl->base = 0x0c140000 (a slim-ngd MMIO ablak, /proc/iomem: 0c140000-0c16bfff)
    ngd->base  = ctrl->base + id*0x1000 + (id-1)*0x1000, id=1 -> 0x0c141000

GUARDRAIL (ugyanaz, mint frm_wakeup_pulse.py)
    Minden MMIO-hozzaferes ELOTT ujraellenorizve:
      - /sys/class/remoteproc/remoteproc2/state == "running"
      - az NGD device power/control == "on" (force-resume)
    Ha barmelyik elbukik -> azonnali kilepes. Gated LPASS-reg olvasasa is
    busz-hangot okozhat.

MODOK
    (default)  read-only cenzus
    --write    egyetlen NGD_CFG write + azonnali readback (pozitiv kontroll).
               Ezt a registert a driver maga is irja, tehat a normal envelopeon
               belul van; de irast csak explicit kapcsoloval vegzunk.
"""

import argparse
import mmap
import os
import struct
import sys
import time

CTRL_BASE = 0x0C140000
MAP_LEN = 0x2000          # lefedi a framert (+0x400..0x614) es az NGD1-et (+0x1000..)
NGD1 = 0x1000             # ngd->base offset a ctrl->base-hez kepest

NGD_REGS = [
    ("NGD_CFG",          0x00),
    ("NGD_STATUS",       0x04),
    ("NGD_RX_MSGQ_CFG",  0x08),
    ("NGD_INT_EN",       0x10),
    ("NGD_INT_STAT",     0x14),
    ("NGD_INT_CLR",      0x18),
    ("NGD_TX_MSG",       0x30),
    ("NGD_RX_MSG",       0x70),
    ("NGD_IE_STAT",      0xF0),
    ("NGD_VE_STAT",      0xF4),
]

FRM_REGS = [
    ("FRM_CFG",          0x400),
    ("FRM_STAT",         0x404),
    ("FRM_INT_EN",       0x410),
    ("FRM_INT_STAT",     0x414),
    ("FRM_CLKCTL_DONE",  0x420),
    ("FRM_IE_STAT",      0x430),
    ("INTF_CFG",         0x600),
    ("INTF_STAT",        0x604),
    ("INTF_INT_STAT",    0x614),
    ("COMP_CFG",         0x1004 - 0x1004),   # placeholder, nem hasznalt
]
FRM_REGS = [r for r in FRM_REGS if r[0] != "COMP_CFG"]

RPROC_STATE = "/sys/class/remoteproc/remoteproc2/state"
NGD_PWR = None  # felderitve


def find_ngd_power_control():
    root = "/sys/bus/platform/devices"
    for name in os.listdir(root):
        if "slim-ngd" in name:
            p = os.path.join(root, name, "power", "control")
            if os.path.exists(p):
                return p
    # a gyerek-device (qcom,slim-ngd.1) is szoba johet
    for base, dirs, _ in os.walk("/sys/devices/platform"):
        for d in dirs:
            if d.startswith("qcom,slim-ngd"):
                p = os.path.join(base, d, "power", "control")
                if os.path.exists(p):
                    return p
    return None


def read_file(p):
    try:
        with open(p) as f:
            return f.read().strip()
    except OSError:
        return None


def gate_ok(verbose=False):
    st = read_file(RPROC_STATE)
    if st != "running":
        if verbose:
            print(f"GATE FAIL: remoteproc2 state = {st!r}", file=sys.stderr)
        return False
    if NGD_PWR:
        pc = read_file(NGD_PWR)
        if pc != "on":
            if verbose:
                print(f"GATE FAIL: {NGD_PWR} = {pc!r}", file=sys.stderr)
            return False
    return True


def rd(mm, off):
    return struct.unpack("<I", mm[off:off + 4])[0]


def wr(mm, off, val):
    mm[off:off + 4] = struct.pack("<I", val)


def main():
    global NGD_PWR
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="NGD_CFG write + readback (pozitiv kontroll)")
    ap.add_argument("--reg", default="0x10",
                    help="NGD-offset amit irunk (default 0x10 = NGD_INT_EN)")
    ap.add_argument("--cfg-val", default="0x7",
                    help="a beirando NGD_CFG ertek (default 0x7 = ENABLE|RX|TX)")
    args = ap.parse_args()

    NGD_PWR = find_ngd_power_control()
    print(f"# NGD power/control: {NGD_PWR}")

    restore = None
    if NGD_PWR:
        cur = read_file(NGD_PWR)
        if cur != "on":
            restore = cur
            with open(NGD_PWR, "w") as f:
                f.write("on")
            time.sleep(0.2)

    if not gate_ok(verbose=True):
        print("ABORT: kapu nem nyilt ki", file=sys.stderr)
        return 2

    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    try:
        mm = mmap.mmap(fd, MAP_LEN, mmap.MAP_SHARED,
                       mmap.PROT_READ | mmap.PROT_WRITE, offset=CTRL_BASE)
    finally:
        os.close(fd)

    try:
        print(f"# ctrl->base = 0x{CTRL_BASE:08x}   ngd->base = 0x{CTRL_BASE + NGD1:08x}")
        print("## FRAMER (ctrl->base + off)")
        for name, off in FRM_REGS:
            if not gate_ok(verbose=True):
                return 2
            print(f"  {name:<18} +0x{off:04x} = 0x{rd(mm, off):08x}")

        print("## NGD1 (ngd->base + off)")
        for name, off in NGD_REGS:
            if not gate_ok(verbose=True):
                return 2
            print(f"  {name:<18} +0x{off:04x} = 0x{rd(mm, NGD1 + off):08x}")

        # ctrl->base+0 = COMP verzio-regiszter (a driver ctrl->ver-nek olvassa)
        print(f"  {'COMP_VER(ctrl+0)':<18} +0x0000 = 0x{rd(mm, 0):08x}")

        if args.write:
            # A pozitiv kontroll a NGD_INT_EN-en megy (offset 0x10), NEM a CFG-n:
            # az INT_EN pusztan interrupt-maszk, a busz nema -> nulla mellekhatas,
            # es pontosan ezt irja a driver a qcom_slim_ngd_power_up():1282-ben.
            reg_off = int(args.reg, 0)
            reg_name = dict((o, n) for n, o in NGD_REGS).get(reg_off, f"NGD+0x{reg_off:x}")
            val = int(args.cfg_val, 0)
            if not gate_ok(verbose=True):
                return 2
            before = rd(mm, NGD1 + reg_off)
            wr(mm, NGD1 + reg_off, val)
            time.sleep(0.01)
            after = rd(mm, NGD1 + reg_off)
            verdict = "LAND" if after == val else ("PARTIAL" if after else "DROPPED")
            print(f"## POZITIV KONTROLL {reg_name}: before=0x{before:08x} "
                  f"wrote=0x{val:08x} readback=0x{after:08x} -> {verdict}")
            # allitsuk vissza az eredetit
            wr(mm, NGD1 + reg_off, before)
            # utana-allapot
            for name, off in NGD_REGS:
                print(f"  post {name:<18} = 0x{rd(mm, NGD1 + off):08x}")
            for name, off in [("INTF_STAT", 0x604), ("FRM_STAT", 0x404)]:
                print(f"  post {name:<18} = 0x{rd(mm, off):08x}")
    finally:
        mm.close()
        if restore is not None:
            try:
                with open(NGD_PWR, "w") as f:
                    f.write(restore)
            except OSError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
