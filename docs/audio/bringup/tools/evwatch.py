#!/usr/bin/env python3
# Watch several input devices at once and print one flushed line per event.
# No pipes, no shell filters: every stage between the kernel and the output
# buffers, and each one has silently swallowed a measurement here already.
import os, select, struct, sys, time
FMT = "llHHi"; SZ = struct.calcsize(FMT)
NAMES = {(5, 2): "SW_HEADPHONE_INSERT", (5, 4): "SW_MICROPHONE_INSERT",
         (5, 6): "SW_LINEOUT_INSERT", (5, 7): "SW_JACK_PHYSICAL_INSERT",
         (1, 226): "KEY_MEDIA", (1, 115): "KEY_VOLUMEUP",
         (1, 114): "KEY_VOLUMEDOWN", (1, 582): "KEY_VOICECOMMAND",
         (1, 260): "BTN_4", (1, 261): "BTN_5"}
fds = {}
for p in sys.argv[1:]:
    fds[os.open(p, os.O_RDONLY)] = os.path.basename(p)
print("watching %s" % ", ".join(fds.values()), flush=True)
while True:
    for fd in select.select(list(fds), [], [], 1.0)[0]:
        data = os.read(fd, SZ * 64)
        for off in range(0, len(data) - len(data) % SZ, SZ):
            sec, usec, t, c, v = struct.unpack(FMT, data[off:off + SZ])
            if t == 0:
                continue
            print("%-7s %s.%03d  %-24s value=%d"
                  % (fds[fd], time.strftime("%H:%M:%S", time.localtime(sec)),
                     usec // 1000, NAMES.get((t, c), "type%d/code%d" % (t, c)), v),
                  flush=True)
