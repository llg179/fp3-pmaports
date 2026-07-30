# Building the watchdog safety net onto any branch, from scratch

This page is a **procedure**, written to be executed literally — by a person or
by an assistant — on a branch that has no debug layer and without assuming that
`wip/<base>/debug` still exists. Everything it needs is stored next to it in
[`files/`](files/).

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who ran the experiments behind it.

**What you get:** the SoC watchdog starts at driver probe instead of waiting for
userspace, so a hang anywhere in boot resets the phone instead of leaving a
device that only a thumb on the power button recovers. Why that window exists,
and why there is deliberately no `ramoops`, is in
[`README.md`](README.md) — read it for the *why*, this page is the *how*.

**When to use it.** Any branch you are about to boot, especially a throwaway
experiment: that is where an early hang is likeliest and where nobody wants to
walk to the phone. If `wip/<base>/debug` does exist, do **not** follow this page —
one command replays the whole layer instead:

```sh
git cherry-pick $(git merge-base HEAD wip/<base>/debug)..wip/<base>/debug
```

---

## 0. Preconditions — check, do not assume

Run all four. Each has a defined failure action; do not proceed past a failure.

```sh
# 0a. You are in the kernel tree, on the branch you want to modify.
git rev-parse --abbrev-ref HEAD
git status --porcelain            # must be empty

# 0b. The driver this modifies exists.
test -f drivers/watchdog/qcom-wdt.c && echo OK

# 0c. The board file exists (adjust the name for a different board).
test -f arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3.dts && echo OK

# 0d. The kernel config enables the watchdog and the open timeout.
grep -E '^CONFIG_(QCOM_WDT|WATCHDOG_CORE|WATCHDOG_OPEN_TIMEOUT)=' \
     ../fp3-pmaports/linux-fp3/config-fp3.aarch64
```

Expected for 0d — and this is the part that silently makes the whole exercise
pointless if it is wrong:

```
CONFIG_WATCHDOG_CORE=y
CONFIG_WATCHDOG_OPEN_TIMEOUT=300
CONFIG_QCOM_WDT=y
```

`CONFIG_WATCHDOG_OPEN_TIMEOUT=0` means "no deadline", so the core would ping the
hardware forever and a hung boot would never reset. If it is 0 or absent, set it
to `300` in `config-fp3.aarch64` before going further.

Failure actions: 0a not clean → commit or stash first. 0b/0c missing → you are on
the wrong tree or a board this page does not cover; stop. 0d wrong → fix the
config, that is a separate commit.

---

## 1. Route A — apply the stored patch

Try this first. It is one commit containing all three source changes.

```sh
git am ../fp3-pmaports/docs/debug/files/0001-watchdog-qcom-optionally-start-the-watchdog-at-probe.patch
```

**If it succeeds**, skip to [§3 Verify](#3-verify-in-three-places).

Executed on 2026-07-30 against `integration/7.1.3`, which carries no debug layer:
`git am` returned 0, the commit touched exactly the three expected files
(+54 / +1 / +18), the DTB carried all three markers, and
`git diff HEAD debug-int/7.1.3` excluding `FP3-TODO.md` was **empty** — the route
reproduces the shipped layer exactly. Route B below is written from the same
change but has not been run end to end as a separate exercise.

**If it fails**, undo cleanly and go to Route B:

```sh
git am --abort
```

A failure here is expected eventually, not a sign that something is broken: the
patch carries context from `drivers/watchdog/qcom-wdt.c` as it stood on base
`7.1.3`, and upstream edits that file over time. Route B reconstructs the same
change from its meaning rather than from its context, so it survives that drift.

---

## 2. Route B — reconstruct it by hand

Three edits, then one commit. They are independent; order does not matter.

### 2.1 Add the board device-tree file

Copy it in verbatim — it is stored complete, no editing needed:

```sh
cp ../fp3-pmaports/docs/debug/files/sdm632-fairphone-fp3-debug.dtsi \
   arch/arm64/boot/dts/qcom/
```

If you cannot reach that file, its entire content is reproducible from this
node — the register address and the 30 s bark come from Fairphone's downstream
device tree, and the compatible is the in-tree KPSS WDT binding:

```dts
&soc {
	watchdog@b017000 {
		compatible = "qcom,kpss-wdt";
		reg = <0x0b017000 0x1000>;
		clocks = <&sleep_clk>;
		interrupts = <GIC_SPI 3 IRQ_TYPE_EDGE_RISING>;
		timeout-sec = <30>;
		qcom,start-at-probe;
	};
};
```

☠️ **Do not put this node at the end of the board `.dts` instead.** Every other
category appends its nodes there, so a block appended at the end collides with
whichever categories the target branch happens to carry. Measured 2026-07-30: the
appended form conflicted on `wip/7.1.3/audio` and on `integration/7.1.3` and
applied clean on `camera` and `charger` — i.e. it worked or failed depending on
the target, which is the worst kind of failure. In its own file it collides with
nothing.

### 2.2 Include it from the board file

Add exactly one line, immediately after the last `#include "…dtsi"` at the **top**
of `arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3.dts`:

```diff
 #include "sdm632.dtsi"
 #include "pm8953.dtsi"
 #include "pmi632.dtsi"
+#include "sdm632-fairphone-fp3-debug.dtsi"
```

The top include block is the one region of that file no category touches, which
is why the line goes there and not at the bottom.

### 2.3 Teach the driver the new property

`drivers/watchdog/qcom-wdt.c` only claims the hardware when the bootloader left
it running. Two edits.

**First**, add the header that provides `device_property_read_bool()`, keeping the
list alphabetical:

```diff
 #include <linux/of.h>
 #include <linux/platform_device.h>
+#include <linux/property.h>
 #include <linux/watchdog.h>
```

**Second**, in `qcom_wdt_probe()`, find this exact block — it is the only
`qcom_wdt_is_running()` call in the function, and `struct device *dev` is already
in scope from the top of the function:

```c
	if (qcom_wdt_is_running(&wdt->wdd)) {
		qcom_wdt_start(&wdt->wdd);
		set_bit(WDOG_HW_RUNNING, &wdt->wdd.status);
	}
```

and extend it with an `else if`:

```c
	if (qcom_wdt_is_running(&wdt->wdd)) {
		qcom_wdt_start(&wdt->wdd);
		set_bit(WDOG_HW_RUNNING, &wdt->wdd.status);
	} else if (device_property_read_bool(dev, "qcom,start-at-probe")) {
		qcom_wdt_start(&wdt->wdd);
		set_bit(WDOG_HW_RUNNING, &wdt->wdd.status);
		dev_info(dev, "started at probe (bootloader left it disabled)\n");
	}
```

The `dev_info` is not decoration — it is the only positive evidence at boot that
the path ran, and [§3](#3-verify-in-three-places) greps for it. Keep the wording
identical so the check keeps working.

Also extend the comment above that `if` to say what was added and by whom; the
existing text describes Robert Marko's `8650d0f9e933` on Josh Cartwright's
original driver, and the new branch needs the same courtesy. The stored patch has
the full wording if you want it verbatim.

### 2.4 Commit

One commit, deliberately mixing `.dtsi` and `.c` — allowed here and nowhere else,
because this category never gets a `submit` series:

```sh
git add arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3-debug.dtsi \
        arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3.dts \
        drivers/watchdog/qcom-wdt.c
git commit
```

Message: say that the bootloader leaves the watchdog disabled, that the gap is
between kernel start and userspace opening `/dev/watchdog`, that the failure mode
is safe (each reset decrements the A/B retry counter until the bootloader falls
back to the other slot), and that the board node lives in its own file so the
commit replays onto any branch. Trailers per the repo convention: author and
`Signed-off-by:` for the human, `Co-authored-by: Claude <model>` for the
assistant — **never** an `Assisted-by:` here, that form is for LKML-bound work and
this will never be sent anywhere.

---

## 3. Verify, in three places

Do not stop at the first one. Each catches a different failure.

### 3.1 Source — did the edit land where you think?

```sh
git show --stat HEAD
```

Expect exactly three files: the new `.dtsi` (+~54), the board `.dts` (+1) and
`qcom-wdt.c` (+~18). A board `.dts` showing +40 or more means the node went to
the end of the file after all — go back to §2.1.

### 3.2 Build — is the node actually in the DTB?

The device tree compiler is architecture-independent, so this needs no
cross-toolchain and takes seconds. The `defconfig` line is not optional: a fresh
checkout or worktree has no `.config`, and without one the `make` fails with
`Makefile:884: .config, Error 1` before it ever reaches the device tree. Any
config will do — `dtc` does not depend on it.

```sh
make ARCH=arm64 CC=gcc HOSTCC=gcc defconfig        # only if .config is absent
make ARCH=arm64 CC=gcc HOSTCC=gcc qcom/sdm632-fairphone-fp3.dtb
python3 - <<'EOF'
d = open('arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3.dtb','rb').read()
for s in (b'watchdog@b017000', b'qcom,start-at-probe', b'qcom,kpss-wdt'):
    print(f"{s.decode():24s} {'present' if s in d else 'MISSING'}")
EOF
```

All three must say `present`. A missing `qcom,start-at-probe` with the node
present means the `#include` landed but the property did not — check §2.1.

☠️ A DTB that compiles is not a DTB that is deployed. If the branch is also
packaged, deploy the DTB **from the built package**, not from the source tree —
the tree's copy goes stale the moment you rebase or cherry-pick, and the symptom
is a driver that loads while the node is simply absent.

### 3.3 Device — did it arm?

After booting the new kernel:

```sh
dmesg | grep -i 'b017000.watchdog'
ls -l /dev/watchdog
cat /sys/class/watchdog/watchdog*/state 2>/dev/null
```

The line that proves the new path ran, at about 0.18 s:

```
qcom_wdt b017000.watchdog: started at probe (bootloader left it disabled)
```

If instead you see nothing, the node did not probe. If you see the driver bind
but no such line, the bootloader **did** leave the watchdog running on this
device — the `if` branch took the original path, the watchdog is armed anyway,
and nothing is wrong.

☠️ Do not "verify" by deliberately hanging the device unless you have a reason
to: the reset is real, it decrements the A/B retry counter, and a few of those in
a row hand the boot to the other slot.

---

## 4. Do **not** copy `FP3-TODO.md` here

This procedure builds the safety net and nothing else. `FP3-TODO.md` is the
port-wide index of open items; it already exists in two places that are kept
byte-identical — [`../FP3-TODO.md`](../FP3-TODO.md) in this repository and the
tree root on the canonical `wip/<base>/debug` and `debug-int/<base>` — and a
third copy on a branch built from this page would be a stale snapshot the moment
either of those moves. It is also not part of the watchdog change: nothing in the
safety net reads it, and leaving it out keeps this commit reviewable as one
thing.

---

## 5. Where the result belongs

Per [the branch model](../../README.md#the-branch-model): the debug layer's
cherry-pick twin goes to **`debug-int/<base>`**, never to `integration/<base>` —
integration stays a faithful preview of what the `submit` branches carry, and
`debug-int` is what the package builds and the phone runs.

If you built this on a one-off experimental branch, it belongs nowhere else; that
is the normal case for this page.

If you built it because `wip/<base>/debug` was lost, recreate that branch from
what you just made, and from then on use the one-line replay at the top of this
page instead of this procedure.

## Files stored next to this page

| file | what it is |
|---|---|
| [`files/0001-watchdog-qcom-optionally-start-the-watchdog-at-probe.patch`](files/0001-watchdog-qcom-optionally-start-the-watchdog-at-probe.patch) | the whole change as one `git am`-able patch (Route A) |
| [`files/sdm632-fairphone-fp3-debug.dtsi`](files/sdm632-fairphone-fp3-debug.dtsi) | the board file verbatim, for Route B |

**`sdm632-fairphone-fp3.dts` is deliberately not stored here**, and that is not
an oversight. Our change to it is a single `#include` line, which Route A carries
inside the patch and Route B shows as a four-line diff — a full copy would add
nothing. It would also be dangerous: that file is where *every* category appends
its nodes (audio +255, camera +50, charger +138, debug +1), so any stored copy is
a snapshot of one particular branch, and anyone who copied it in the way the
`.dtsi` is copied in would silently wipe out whatever categories the target
carries. The rule this follows: **store new files verbatim, express modifications
as diffs.** The `.dtsi` is safe to store precisely because it exists on no other
branch. A read-only reference copy of the board file, as it stands on
`integration/<base>`, is kept for a different purpose in
[`../device_tree/after_update/`](../device_tree/after_update/).

Both stored files are extracted from the fork rather than retyped. To refresh
them after the layer changes:

```sh
git show wip/<base>/debug~1:arch/arm64/boot/dts/qcom/sdm632-fairphone-fp3-debug.dtsi \
  > docs/debug/files/sdm632-fairphone-fp3-debug.dtsi
git format-patch -1 wip/<base>/debug~1 --stdout \
  > docs/debug/files/0001-watchdog-qcom-optionally-start-the-watchdog-at-probe.patch
```
