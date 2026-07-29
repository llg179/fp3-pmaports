#!/usr/bin/env python3
"""
FRM_WAKEUP pulzus-teszt — a SLIMbus framer superframe-START kikenyszeritese AP-bol.

HIPOTEZIS
    Az eddigi ketoldali byte-diff kampany kizarolag OLVASHATO registereket
    hasonlitott ossze. Egy write-only, onmagat torlo trigger-register mindket
    oldalon mindig 0-t olvas vissza -> a diff strukturalisan VAK ra.
    A downstream vendor-forras (slim-msm-ctrl.c:548) szerint:

        FRM_WAKEUP = 0x41C ; writel_relaxed(1, base + FRM_WAKEUP)
        /* Slimbus wakes up in clock gear 10 at 24.576MHz. With each superframe
         * being 250 usecs, we wait for 20 superframes here */

    Ez a "kezdd el a superframe-eket" trigger.

FONTOS, OSZINTE CAVEAT
    Az msm8953 downstream az NGD (satellite) drivert hasznalja, ami EXPLICIT
    NULL-ra allitja a wakeup-ot (slim-msm-ngd.c:1864: dev->ctrl.wakeup = NULL).
    A FRM_WAKEUP-ot csak a MASTER controller driver (slim-msm-ctrl.c) irja,
    olyan SoC-okon ahol az AP a framer. Itt az ADSP a framer -> ez a register
    az ADSP-e. Ez tehat NEM egy downstream szekvencia visszaallitasa, hanem
    SPEKULATIV poke. Tovabba a FRM_WAKEUP dokumentaltan clock-pause-bol valo
    ebresztes; a mi framerunk nem clock-pause-ban van, hanem "konfiguralt de
    sosem indult" allapotban -> konnyen lehet no-op. A legvalószinubb kimenetel
    nem brick, hanem hogy nem tortenik semmi.

A LATCH-TRUKK
    Ha a pulzus csak tranziens frame-startot okoz (us-ok), a Python-polling
    elszalasztja. De a FRM_INT_STAT (0x414) es INTF_INT_STAT (0x614) LATCH-elnek.
    Ezert a hurok elott toroljuk oket (INT_CLR), es utana barmelyik beallt bit
    a pulzus bizonyiteka -- akkor is, ha az FS azonnal visszaesett.

HASZNALAT
    # 1. ELOSZOR mindig read-only pre-flight (nulla kockazat):
    sudo python3 frm_wakeup_pulse.py --dry-run
    # 2. Csak ha a pre-flight ep erteket mutat (FRM_CFG=0x000d0c83):
    sudo python3 frm_wakeup_pulse.py --duration 30

GUARDRAIL
    ADSP-down alatt TILOS az aperturahoz nyulni (gated LPASS reg -> 900e ->
    busz-hang -> watchdog-reboot). A script minden iteracio ELOTT ujra ellenorzi:
      - /sys/class/remoteproc/remoteproc2/state == "running"
      - az NGD force-resume aktiv
    Ha barmelyik elbukik, azonnal leall.
"""

import argparse
import mmap
import os
import struct
import sys
import time

# --- Framer aperture (AP-physical; LPASS_AP 0x0c000000 aliases LPASS_ADSP 0xee000000) ---
FRAMER_BASE = 0x0C140000
MAP_LEN = 0x1000  # covers every offset we touch (max 0x614)

# --- Register offsets: ubports-fp3-kernel/drivers/slimbus/slim-msm-ctrl.c:63-83 ---
FRM_CFG = 0x400
FRM_STAT = 0x404
FRM_INT_EN = 0x410
FRM_INT_STAT = 0x414  # latching
FRM_INT_CLR = 0x418
FRM_WAKEUP = 0x41C  # <-- write-only self-clearing trigger
FRM_CLKCTL_DONE = 0x420
FRM_IE_STAT = 0x430
INTF_CFG = 0x600
INTF_STAT = 0x604  # FS/SFS/MS = bit 11/12/13
INTF_INT_STAT = 0x614  # latching
INTF_INT_CLR = 0x618

# Sampled every iteration, in log order.
WATCH = [
    ("INTF_STAT", INTF_STAT),
    ("FRM_STAT", FRM_STAT),
    ("FRM_INT_STAT", FRM_INT_STAT),
    ("INTF_INT_STAT", INTF_INT_STAT),
    ("FRM_IE_STAT", FRM_IE_STAT),
    ("FRM_CLKCTL_DONE", FRM_CLKCTL_DONE),
]

FS_BIT, SFS_BIT, MS_BIT = 11, 12, 13
FS_MASK = (1 << FS_BIT) | (1 << SFS_BIT) | (1 << MS_BIT)

# Known-good dead-side baseline (journal folyt.133/155): sanity check the aperture is live.
EXPECT_FRM_CFG = 0x000D0C83
GOLDEN_INTF_STAT = 0x3E04  # UT, framing
GOLDEN_FRM_STAT = 0x060D1901  # UT, framing

RPROC_STATE = "/sys/class/remoteproc/remoteproc2/state"
NGD_POWER_CONTROL_CANDIDATES = [
    "/sys/bus/platform/devices/qcom,slim-ngd.1/power/control",
    "/sys/devices/platform/soc/c140000.slim-ngd/qcom,slim-ngd.1/power/control",
    "/sys/devices/platform/soc/c140000.slim/power/control",
]


def find_ngd_power_control():
    for p in NGD_POWER_CONTROL_CANDIDATES:
        if os.path.exists(p):
            return p
    # fall back to a shallow scan of the platform bus
    root = "/sys/bus/platform/devices"
    try:
        for name in os.listdir(root):
            if "slim-ngd" in name:
                cand = os.path.join(root, name, "power", "control")
                if os.path.exists(cand):
                    return cand
    except OSError:
        pass
    return None


def adsp_running():
    try:
        with open(RPROC_STATE) as f:
            return f.read().strip() == "running"
    except OSError:
        return False


class Gate:
    """Safety gate re-checked before every single MMIO access."""

    def __init__(self, pc_path):
        self.pc_path = pc_path

    def ok(self):
        if not adsp_running():
            return False, "ADSP nem 'running'"
        if self.pc_path:
            try:
                with open(self.pc_path) as f:
                    if f.read().strip() != "on":
                        return False, "NGD force-resume elveszett"
            except OSError:
                return False, "NGD power/control olvashatatlan"
        return True, ""


def rd(mm, off):
    return struct.unpack_from("<I", mm, off)[0]


def wr(mm, off, val):
    struct.pack_into("<I", mm, off, val)


def decode_intf(v):
    return "FS=%d SFS=%d MS=%d" % (
        (v >> FS_BIT) & 1,
        (v >> SFS_BIT) & 1,
        (v >> MS_BIT) & 1,
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="csak olvasas, SEMMI iras (mindig ezzel kezdj)",
    )
    ap.add_argument("--duration", type=float, default=30.0, help="hurok hossza mp-ben")
    ap.add_argument("--period", type=float, default=0.020, help="pulzus-periodus mp-ben")
    ap.add_argument("--log", default=None, help="mintak CSV-be")
    ap.add_argument(
        "--force",
        action="store_true",
        help="folytatas akkor is, ha a FRM_CFG sanity-check elbukik",
    )
    args = ap.parse_args()

    if os.geteuid() != 0:
        sys.exit("HIBA: root kell a /dev/mem-hez.")

    # --- Safety gate: ADSP up + NGD resumed ---------------------------------
    if not adsp_running():
        sys.exit(
            "HIBA: az ADSP nem 'running' (%s). Gated LPASS reg olvasasa 900e/busz-hangot\n"
            "      okozhat -> watchdog-reboot. Nem nyulok az aperturahoz." % RPROC_STATE
        )

    pc = find_ngd_power_control()
    restore_pc = None
    if pc:
        with open(pc) as f:
            prev = f.read().strip()
        if prev != "on":
            print("[gate] NGD force-resume: %s: %s -> on" % (pc, prev))
            with open(pc, "w") as f:
                f.write("on\n")
            restore_pc = (pc, prev)
            time.sleep(0.05)
        else:
            print("[gate] NGD mar force-resumed (%s)" % pc)
    else:
        print(
            "[gate] FIGYELEM: NGD power/control nem talalhato -- az apertura lehet, hogy\n"
            "       clock-gated. A FRM_CFG sanity-check majd eldonti."
        )

    gate = Gate(pc)
    fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    rc = 0
    try:
        mm = mmap.mmap(
            fd, MAP_LEN, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE,
            offset=FRAMER_BASE,
        )
    except Exception as e:
        os.close(fd)
        sys.exit("HIBA: mmap 0x%08x sikertelen: %s" % (FRAMER_BASE, e))

    logf = open(args.log, "w") if args.log else None
    try:
        # --- Pre-flight: is the aperture actually live? ----------------------
        cfg = rd(mm, FRM_CFG)
        intf_cfg = rd(mm, INTF_CFG)
        print("\n=== PRE-FLIGHT (read-only) ===")
        print("  FRM_CFG        (0x400) = 0x%08x   (vart: 0x%08x)" % (cfg, EXPECT_FRM_CFG))
        print("  INTF_CFG       (0x600) = 0x%08x   (vart: 0x1)" % intf_cfg)
        for name, off in WATCH:
            v = rd(mm, off)
            extra = "  <- %s" % decode_intf(v) if off == INTF_STAT else ""
            print("  %-15s(0x%03x) = 0x%08x%s" % (name, off, v, extra))
        print("  golden referencia: INTF_STAT=0x%04x  FRM_STAT=0x%08x"
              % (GOLDEN_INTF_STAT, GOLDEN_FRM_STAT))

        if cfg in (0x00000000, 0xFFFFFFFF):
            msg = ("\nHIBA: FRM_CFG=0x%08x -> az apertura NEM el (gated vagy nincs hozzaferes).\n"
                   "      Ne pulzalj bele. Ellenorizd az NGD force-resume-ot es az ADSP-t." % cfg)
            if not args.force:
                sys.exit(msg)
            print(msg + "\n      (--force miatt folytatom)")
        elif cfg != EXPECT_FRM_CFG:
            msg = ("\nFIGYELEM: FRM_CFG=0x%08x != vart 0x%08x. Masik slot/allapot?"
                   % (cfg, EXPECT_FRM_CFG))
            if not args.force:
                sys.exit(msg + "\n      Megallok. --force felulbiralja.")
            print(msg + "  (--force miatt folytatom)")

        if args.dry_run:
            print("\n[dry-run] Iras NEM tortent. Ha a fenti ertekek epek, futtasd ujra "
                  "--dry-run nelkul.")
            return

        # --- Clear the latching interrupt-status registers -------------------
        print("\n=== LATCH-TORLES (a pulzus elott) ===")
        pre_frm_int = rd(mm, FRM_INT_STAT)
        pre_intf_int = rd(mm, INTF_INT_STAT)
        print("  FRM_INT_STAT  torles elott = 0x%08x" % pre_frm_int)
        print("  INTF_INT_STAT torles elott = 0x%08x" % pre_intf_int)
        ok, why = gate.ok()
        if not ok:
            sys.exit("HIBA: gate elbukott a torles elott: %s" % why)
        wr(mm, FRM_INT_CLR, 0xFFFFFFFF)
        wr(mm, INTF_INT_CLR, 0xFFFFFFFF)
        time.sleep(0.005)
        print("  FRM_INT_STAT  torles utan  = 0x%08x" % rd(mm, FRM_INT_STAT))
        print("  INTF_INT_STAT torles utan  = 0x%08x" % rd(mm, INTF_INT_STAT))

        baseline = {name: rd(mm, off) for name, off in WATCH}

        # --- Pulse loop ------------------------------------------------------
        print("\n=== PULZUS-HUROK: 1 -> FRM_WAKEUP (0x41C), %.0f mp, %.0f ms periodus ==="
              % (args.duration, args.period * 1000))
        if logf:
            logf.write("t," + ",".join(n for n, _ in WATCH) + "\n")

        t0 = time.monotonic()
        n = 0
        changes = []
        success = False
        while time.monotonic() - t0 < args.duration:
            ok, why = gate.ok()
            if not ok:
                print("\n!! GATE MEGSZAKITAS %.3fs-nal: %s -- leallok." % (time.monotonic() - t0, why))
                rc = 2
                break

            # pulse, then read back as tightly as possible
            wr(mm, FRM_WAKEUP, 1)
            vals = [rd(mm, off) for _, off in WATCH]
            t = time.monotonic() - t0
            n += 1

            if logf:
                logf.write("%.4f,%s\n" % (t, ",".join("0x%08x" % v for v in vals)))

            for (name, _), v in zip(WATCH, vals):
                if v != baseline[name]:
                    line = "  [%7.3fs] %-15s 0x%08x -> 0x%08x" % (t, name, baseline[name], v)
                    if name == "INTF_STAT":
                        line += "   <- %s" % decode_intf(v)
                    print(line)
                    changes.append((t, name, baseline[name], v))
                    baseline[name] = v
                    if name == "INTF_STAT" and (v & FS_MASK):
                        success = True

            time.sleep(args.period)

        # --- Verdict ---------------------------------------------------------
        print("\n=== VERDIKT (%d pulzus) ===" % n)
        final_intf = rd(mm, INTF_STAT)
        final_frm = rd(mm, FRM_STAT)
        latch_frm = rd(mm, FRM_INT_STAT)
        latch_intf = rd(mm, INTF_INT_STAT)
        print("  INTF_STAT     = 0x%08x   %s" % (final_intf, decode_intf(final_intf)))
        print("  FRM_STAT      = 0x%08x" % final_frm)
        print("  FRM_INT_STAT  = 0x%08x   (latch)" % latch_frm)
        print("  INTF_INT_STAT = 0x%08x   (latch)" % latch_intf)

        if success or (final_intf & FS_MASK):
            print("\n  *** POZITIV: FS/SFS/MS beallt -> a framer KERETEZ. ***")
            print("      Kovetkezo: dmesg | grep -i 'capability\\|laddr\\|wcd9335'")
            print("      Az NGD ~10s-enkent ujraprobal, tehat a capability-exchange-nek")
            print("      magatol le kell futnia.")
        elif latch_frm or latch_intf:
            print("\n  ** RESZLEGES: az FS nem allt be, DE latch-elt interrupt-bit van.")
            print("     -> a pulzus CSINALT valamit (tranziens esemeny). Erdemes tovabb asni:")
            print("        melyik bit, es mit jelent a vendor int-enumban.")
        elif changes:
            print("\n  ** VALTOZAS volt, de nem FS es nem latch. Nezd at a fenti listat.")
        else:
            print("\n  -- NEGATIV: semmi nem valtozott, semmi nem latch-elt.")
            print("     A FRM_WAKEUP AP-bol no-op ezen a blokkon (a varhato kimenetel:")
            print("     a register ADSP-tulajdonu, es/vagy a framer nem clock-pause-ban van).")
            print("     Ez TISZTA negativ eredmeny -- a hipotezist zarja, nem hagyja nyitva.")
    finally:
        if logf:
            logf.close()
            print("\n  minta-log: %s" % args.log)
        try:
            mm.close()
        finally:
            os.close(fd)
        if restore_pc:
            path, prev = restore_pc
            try:
                with open(path, "w") as f:
                    f.write(prev + "\n")
                print("  [gate] NGD power/control visszaallitva: %s" % prev)
            except OSError as e:
                print("  [gate] FIGYELEM: nem sikerult visszaallitani a power/control-t: %s" % e)
    sys.exit(rc)


if __name__ == "__main__":
    main()
