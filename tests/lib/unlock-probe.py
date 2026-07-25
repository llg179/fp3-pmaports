#!/usr/bin/python3
"""Record the cold unlock: greeter -> authenticated -> home screen painted.

Runs from a boot-time unit, because the measurement cannot survive an SSH
login: connecting as the user starts the very systemd --user session whose cold
start we are timing.

The end marker is phosh's CPU time going quiet, chosen by measurement rather
than assumption (2026-07-25). During startup its deltas run to tens or hundreds
of jiffies per sample; once the home screen is up they drop to exactly +1 per
sample and stay there. Two rejected candidates, both instructive:

  * queued systemd --user jobs - DISQUALIFIED, not passive. Asking for them with
    `systemctl -M user@ --user list-jobs` starts the user manager, so the probe
    causes the thing it is trying to observe.
  * MDSS/DSI interrupts as a page-flip proxy - never settles. The display keeps
    refreshing at ~15 interrupts per sample forever, so there is no "quiet" to
    detect.

They are still recorded here as columns, because they cost nothing extra and
they make the trace readable when something looks wrong. All timestamps are
CLOCK_MONOTONIC from this one process, so nothing depends on the host clock or
on SSH round-trip time.
"""
import os
import re
import subprocess
import sys
import time

INTERVAL = 0.05
DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0
OUT = sys.argv[2] if len(sys.argv) > 2 else "/var/log/fp3-selftest/unlock-probe.tsv"


def phosh_pid():
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip() == "phosh":
                    return int(pid)
        except OSError:
            pass
    return None


def cpu_jiffies(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            parts = f.read().rsplit(") ", 1)[1].split()
        return int(parts[11]) + int(parts[12])  # utime + stime
    except (OSError, IndexError):
        return -1


IRQ_RE = re.compile(r"(mdss|dsi|msm_drm|kgsl)", re.I)


def irq_count():
    total = 0
    try:
        with open("/proc/interrupts") as f:
            for line in f:
                if IRQ_RE.search(line):
                    total += sum(int(x) for x in line.split()[1:9] if x.isdigit())
    except OSError:
        pass
    return total


def job_count(user):
    try:
        out = subprocess.run(
            ["systemctl", "-M", f"{user}@", "--user", "list-jobs", "--no-legend"],
            capture_output=True, text=True, timeout=3,
        ).stdout
        return len([l for l in out.splitlines() if l.strip()])
    except Exception:
        return -1


def main():
    # On a cold boot phosh does not exist yet: the device sits at the greetd
    # greeter (phrog) as uid 113, and the user's phosh is only born *during*
    # the thing we are measuring. So wait for it rather than requiring it.
    user = os.environ.get("SESSION_USER", "fp3")
    pid = None

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    start = time.clock_gettime(time.CLOCK_MONOTONIC)
    last_jobs_at = start  # absolute, like t - comparing against 0.0 made this fire every tick
    jobs = -1

    with open(OUT, "w", buffering=1) as f:
        f.write("# t_monotonic\tcpu_jiffies\tirq_total\tuser_jobs\n")
        f.write(f"# started at monotonic {start:.3f}\n")
        while True:
            t = time.clock_gettime(time.CLOCK_MONOTONIC)
            if t - start > DURATION:
                break
            if pid is None:
                pid = phosh_pid()
                if pid is not None:
                    f.write(f"# phosh appeared at t={t - start:.3f}, pid {pid}\n")
            # list-jobs shells out, far too slow for 50 ms - poll it at 2 Hz
            # and carry the last value forward.
            if t - last_jobs_at > 0.5:
                jobs = job_count(user)
                last_jobs_at = t
            f.write(f"{t - start:.3f}\t{cpu_jiffies(pid) if pid else -1}\t{irq_count()}\t{jobs}\n")
            time.sleep(INTERVAL)
    os.system("sync")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
