# Building and deploying

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
./pmb build --arch aarch64 linux-fp3
```

The source tarball is ~250 MB straight from GitHub, so the first fetch takes a
minute or two. A warm ccache rebuild is around four minutes; a new `_commit`
means a new source directory and therefore a cold ccache, which is 20–35.

⚠️ **Push `integration/<base>` before you bump `_commit`.** The package fetches
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
