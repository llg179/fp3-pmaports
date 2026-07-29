#!/usr/bin/env python3
"""
PM8953 GPIO1-et OUTPUT-ra allitja a gpio chardev (v2) API-val es NYITVA TARTJA.

MIERT
    A downstream FP3 a codec 9.6 MHz MCLK-jat a PM8953 GPIO1-en adja ki:
        msm8953-audio.dtsi:
            clock_audio: audio_ext_clk { clocks = <&clock_gcc clk_div_clk2>;
                                         qcom,audio-ref-clk-gpio = <&pm8953_gpios 1 0>; }
            tasha_mclk_default { pins="gpio1"; function="func1"; output-low; }
    A mainline FP3 DT-ben ez a TELJES ut HIANYZIK: a `wcd_mclk` egy
    fixed-factor-clock a BB_CLK1-rol ("NEEDS VERIFICATION" megjegyzessel), es a
    PM8953 GPIO1 merve MUX UNCLAIMED / GPIO UNCLAIMED. Vagyis a WCD9326-nak
    fizikailag NINCS MCLK-ja. Egy ora nelkuli slave nem tud valaszolni a framer
    enumeration/capability uzenetere -> a framer feladja -> INTF_STAT FS = 0.

    A mux-ot a debugfs `pinmux-select` mar func1-re allitotta, de az irany
    bemenet maradt; a downstream `output-low`-t ker. Ez a script adja meg az
    irany-reszt.

HASZNALAT
    python3 pmic_gpio_out.py --hold 60        # 60 mp-ig tartja, kozben merheto
"""

import argparse
import ctypes
import fcntl
import os
import struct
import sys
import time

GPIO_V2_LINES_MAX = 64
GPIO_MAX_NAME_SIZE = 32
GPIO_V2_LINE_NUM_ATTRS_MAX = 10

GPIO_V2_LINE_FLAG_OUTPUT = 1 << 3

# struct gpio_v2_line_request: offsets[64]u32, consumer[32], config(272),
# num_lines u32, event_buffer_size u32, padding[5]u32, fd s32  -> 592 byte
LINE_REQUEST_SIZE = 592
CONFIG_SIZE = 272


def _ioc(direction, typ, nr, size):
    return (direction << 30) | (size << 16) | (typ << 8) | nr


GPIO_V2_GET_LINE_IOCTL = _ioc(3, 0xB4, 0x07, LINE_REQUEST_SIZE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chip", default="/dev/gpiochip1", help="pm8953 = gpiochip1")
    ap.add_argument("--offset", type=int, default=0, help="gpio1 = offset 0")
    ap.add_argument("--hold", type=float, default=60.0)
    args = ap.parse_args()

    buf = bytearray(LINE_REQUEST_SIZE)
    # offsets[0] = offset
    struct.pack_into("<I", buf, 0, args.offset)
    # consumer
    name = b"fp3-mclk-test\0"
    buf[GPIO_V2_LINES_MAX * 4:GPIO_V2_LINES_MAX * 4 + len(name)] = name
    cfg_off = GPIO_V2_LINES_MAX * 4 + GPIO_MAX_NAME_SIZE
    # config.flags = OUTPUT  (ertek marad 0 = low, mint a downstream output-low)
    struct.pack_into("<Q", buf, cfg_off, GPIO_V2_LINE_FLAG_OUTPUT)
    # config.num_attrs = 0
    struct.pack_into("<I", buf, cfg_off + 8, 0)
    # num_lines = 1
    struct.pack_into("<I", buf, cfg_off + CONFIG_SIZE, 1)

    fd = os.open(args.chip, os.O_RDWR)
    try:
        out = bytearray(buf)
        fcntl.ioctl(fd, GPIO_V2_GET_LINE_IOCTL, out, True)
        line_fd = struct.unpack_from("<i", out, cfg_off + CONFIG_SIZE + 4 + 4 + 20)[0]
        if line_fd < 0:
            print(f"HIBA: line fd = {line_fd}", file=sys.stderr)
            return 1
        print(f"OK: {args.chip} offset {args.offset} OUTPUT-LOW igenyelve, fd={line_fd}")
        print(f"tartas {args.hold}s ...")
        sys.stdout.flush()
        time.sleep(args.hold)
        os.close(line_fd)
        print("elengedve")
    finally:
        os.close(fd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
