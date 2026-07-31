# Building and deploying

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

How a change gets from an edit to a booted phone, and how the last working
kernel stays bootable while the new one is tried.

## Building

Assumes the checkouts and the `pmb` wrapper from
[Setting the checkouts up](../rolling-a-new-base.md#setting-the-checkouts-up-once-per-machine). After a
change to the APKBUILD or the config, mirror it into pmaports and build:

```sh
cp fp3-pmaports/linux-fp3/{APKBUILD,config-fp3.aarch64} \
   pmaports/device/testing/linux-fp3/

./pmb checksum linux-fp3            # only needed if you changed _commit
./pmb build --arch aarch64 --force --lax linux-fp3
```

`--force` and `--lax` are **`build` flags, not global ones** — `./pmb --lax build`
is rejected with `unrecognized arguments`. Without `--force`, a rebuild at the
same `pkgver` is skipped with *"Package is up to date"* even though `_commit`
changed; without `--lax` the buildroots are zapped first, which throws the
ccache away and turns a four-minute rebuild into thirty.

The source tarball is ~250 MB straight from GitHub, so the first fetch takes a
minute or two. A warm ccache rebuild is around four minutes; a new `_commit`
means a new source directory and therefore a cold ccache, which is 20–35.

⚠️ **Push `debug-int/<base>` before you bump `_commit`.** The package fetches
the tarball from GitHub, so a commit that only exists locally gives a 404 during
`./pmb checksum`. If you skip the checksum step, the build fails one step
later with the far less helpful

```
ERROR: linux-fp3-<sha>.tar.gz is missing in checksums
```

which points at the checksums rather than at the missing push.

## Deploying

The built package lands in the work directory the wrapper pins
(`work/packages/edge/aarch64/`, or `~/.local/var/pmbootstrap/packages/...` with
a default pmbootstrap). An apk is a gzipped tar, so unpack it and take the
pieces you need:

```sh
APK=work/packages/edge/aarch64/linux-fp3-7.1.3-r0.apk
mkdir -p /tmp/apk && tar xzf "$APK" -C /tmp/apk

tar tzf "$APK" | grep q6voice-dai        # check the module is actually in there
```

**Device tree only** — extlinux loads the fdt separately, so no kernel flash and
no module rebuild is needed. Roughly a two-minute round trip:

```sh
scp /tmp/apk/boot/dtbs/qcom/sdm632-fairphone-fp3.dtb fp3@$FP3_DEV_IP:/tmp/
ssh fp3@$FP3_DEV_IP 'sudo cp /tmp/sdm632-fairphone-fp3.dtb /boot/ && sudo sync && sudo reboot'
```

**A driver change** — copy the module in beside the others and refresh the
dependency list:

```sh
KREL=$(ssh fp3@$FP3_DEV_IP uname -r)
scp /tmp/apk/lib/modules/$KREL/kernel/sound/soc/qcom/qdsp6/q6voice-dai.ko \
    fp3@$FP3_DEV_IP:/tmp/
ssh fp3@$FP3_DEV_IP "sudo cp /tmp/q6voice-dai.ko \
    /lib/modules/$KREL/kernel/sound/soc/qcom/qdsp6/ && sudo depmod -a && sudo reboot"
```

**A full kernel change (a new base)** — deploy by hand. The pmOS
`mkinitfs`/`boot-deploy` tooling does **not** work here, for two independent
reasons, so do not rely on the apk's install trigger to put the kernel in
`/boot`:

* `mkinitfs` refuses to run with more than one kernel *flavor* present
  (`only one kernel release/flavor is supported`), and a device that has been
  through a rename or a parallel-package phase easily has two or three stamps
  under `/usr/share/kernel/`; and
* `boot-deploy` regenerates the extlinux config, which fails against the FP3's
  hand-maintained lk2nd + `extlinux.conf` (`boot-deploy failed`, exit 1).

Because every boot-critical driver is built **in** (`MMC_BLOCK`, `SDHCI_MSM`,
`EXT4`, `F2FS` = `y`), the one initramfs boots any of these kernels, so a
fallback is just a second set of boot files and a second extlinux entry. Full
procedure, from the host (`$D` = device, e.g. `fp3@172.16.42.1`):

```sh
APK=work/packages/edge/aarch64/linux-fp3-7.1.3-r0.apk
scp "$APK" $D:/tmp/linux-fp3.apk

ssh $D 'sudo sh -c '"'"'
  cd /boot

  # 1. keep the current kernel as the version-free fallback
  cp -n vmlinuz vmlinuz-fallback
  cp -n sdm632-fairphone-fp3.dtb sdm632-fairphone-fp3.dtb-fallback

  # 2. register the package (for apk info + the /usr/share/kernel/fp3 stamp that
  #    01-identity checks); its mkinitfs trigger will error - that is expected
  apk add --allow-untrusted /tmp/linux-fp3.apk

  # 3. leave exactly one flavor: drop the old package and any stale flavor stamp
  apk del linux-fp3-709 2>/dev/null
  rm -rf /usr/share/kernel/fp3-713 /usr/share/kernel/fp3-709   # whatever is stale

  # 4. copy the kernel, DTB and modules in by hand (bypassing boot-deploy)
  mkdir -p /tmp/x && tar xzf /tmp/linux-fp3.apk -C /tmp/x
  KV=$(cat /tmp/x/usr/share/kernel/fp3/kernel.release)
  cp /tmp/x/boot/vmlinuz /boot/vmlinuz
  cp /tmp/x/boot/dtbs/qcom/sdm632-fairphone-fp3.dtb /boot/sdm632-fairphone-fp3.dtb
  cp -a /tmp/x/lib/modules/$KV /lib/modules/ && depmod $KV
  sync
'"'"''
```

Then write `extlinux.conf` by hand — two version-free entries, the new kernel as
default and the preserved one as fallback (keep the `append` line's UUIDs
exactly as they were):

```
timeout 3
default postmarketOS
menu title FP3 boot (linux-fp3 / fallback)

label postmarketOS
	kernel /vmlinuz
	fdt /sdm632-fairphone-fp3.dtb
	initrd /initramfs
	append quiet splash ... pmos_boot_uuid=<...> pmos_root_uuid=<...> pmos_rootfsopts=defaults

label postmarketOS-fallback
	kernel /vmlinuz-fallback
	fdt /sdm632-fairphone-fp3.dtb-fallback
	initrd /initramfs
	append quiet splash ... pmos_boot_uuid=<...> pmos_root_uuid=<...> pmos_rootfsopts=defaults
```

Reboot and confirm the identity: `uname -v` shows `#<pkgrel+1>-fp3` and
`tests/fp3-selftest --only identity` is green (build stamp, installed package,
source commit). To test a base before trusting it, deploy it as the *fallback*
first, or flip `default` and reboot — a power-cycle then recovers on its own
only if the entry you booted is not the default, so revert `default` as soon as
SSH returns.

⚠️ Take the DTB from the **built package**, not from your source tree — a stale
locally-built DTB is an easy way to spend an hour debugging a device tree that
was never deployed. The symptom is silent: the driver loads, the node it needs
simply is not there.

⚠️ The slot_b rootfs is 2.4 GB and normally sits around 90% full. At 100% the
graphical session does not come up at all, which looks like a kernel
regression and is not one — check `df -h /` before blaming the build.

## Things that look like build or kernel bugs and are not

Every one of these cost real time at least once.

**Never pad an abbreviated commit hash.** `_commit` takes the full 40
characters; extending the 12 from `git log --oneline` by guessing gives a
GitHub 404 at `./pmb checksum` that reads like the push failed. Take it from
`git rev-parse <branch>` or, better, from `git ls-remote fork <branch>`, which
also proves the push landed.

**"Package is up to date" can mean a stale package outranks your bump.** `--lax`
compares against the highest version in the local work repo, and a leftover
`--src` build carries a `_pYYYYMMDDHHMMSS` suffix that sorts **above** a plain
`pkgrel` bump — with `linux-fp3-7.1.3_p20260729013201-r12` sitting in the repo,
`7.1.3-r21` was skipped as up to date, twice, with no hint why. Deleting the
`.apk` is only half the fix: `APKINDEX.tar.gz` still advertises it. Move the
stale apk aside, then

```sh
./pmb index
```

and build again. What matters is not the `pkgrel` number but that the highest
version *in the index* is below yours — which is what to check when a build
refuses to run:

```sh
sudo tar xzOf work/packages/edge/aarch64/APKINDEX.tar.gz APKINDEX |
    awk '/^P:linux-fp3$/{p=1} p&&/^V:/{print; p=0}' | sort -V | tail -3
```

**Do not run `./pmb checksum` (or a second build) while a build is running.**
They share `/home/pmos/build` in the chroot, so the running build loses its
source tree mid-compile and dies with

```
<command-line>: fatal error: ./include/linux/compiler-version.h: No such file or directory
```

which points at the kernel source rather than at the concurrent command.

**`apk add` finishing with `1 error` is usually the network, not the package.**
With no route to the repositories the phone reports

```
WARNING: updating and opening https://...: DNS: transient error (try again later)
1 error; 2035.3 MiB in 1208 packages
```

and still installs the local apk correctly — `apk list -I | grep linux-fp3`
confirms it. It matters because a deploy script with `set -e` aborts here, which
silently skips whatever came after (in one case the whole extlinux fix-up, so
the fallback entry, `panic=10` and the menu timeout were all missing on the next
boot).

**`apk add` regenerates `extlinux.conf` and overwrites `/boot/*.dtb`,** so the
fallback label, `panic=10` and the menu timeout have to be written *after* the
install, never before. Check the file, do not assume:

```sh
ssh $D cat /boot/extlinux/extlinux.conf
```

**Watch the device's free space.** Each kernel apk is ~30 MB and they accumulate
in `/home/fp3` and `/var/cache/apk`; on a 2.4 GB rootfs a day of iteration
reaches 99% full, and the phone raises a low-disk notification long before
anything fails visibly. Clean up between rounds:

```sh
ssh $D 'sudo sh -c "rm -f /home/fp3/*.apk; rm -rf /var/cache/apk/*; \
    journalctl --vacuum-size=20M"'
```

⚠️ `journalctl --vacuum-size` is not free: it drops the kernel log of earlier
boots, and a later comparison across boots then shows a *perfect* correlation
that is really just missing data. If you are about to compare boots, check that
each one still has a plausible number of lines
(`journalctl -b -N -k | wc -l`).
