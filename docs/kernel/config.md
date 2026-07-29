# The kernel config

`config-fp3.aarch64` is the postmarketOS `qcom-msm8953` config carried forward
to the current base. `prepare()` then turns on what that config misses:

| symbol | why |
|---|---|
| `CONFIG_SLIMBUS`, `CONFIG_SLIM_QCOM_NGD_CTRL`, `CONFIG_REGMAP_SLIMBUS` | the SLIMbus stack the codec lives on |
| `CONFIG_SND_SOC_WCD9335`, `CONFIG_SND_SOC_WCD_CLASSH` | the codec |
| `CONFIG_QCOM_BAM_DMA` | SLIMbus data path |
| `CONFIG_SND_SOC_AW8898` | speaker amplifier |
| `CONFIG_VIDEO_IMX363` | rear camera sensor |
| `CONFIG_DRM_PANEL_HIMAX_HX83112B` | the display panel |
| `CONFIG_CHARGER_QCOM_SMB2` | the PMI632 charger |
| `CONFIG_IIO_QCOM_SMGR` | the Sensor Manager core — every FP3 sensor is behind it |
| `CONFIG_IIO_QCOM_SMGR_ACCEL`, `_GYRO`, `_MAG`, `_PROX` | the four sensors the SSC enumerates |
| `CONFIG_WATCHDOG`, `_CORE`, `CONFIG_QCOM_WDT` | the SoC watchdog, with `HANDLE_BOOT_ENABLED` and `OPEN_TIMEOUT=300` |

## The panel symbol is a trap worth knowing about

The panel driver was called `CONFIG_DRM_PANEL_FAIRPHONE_FP3_HX83112B` up to
6.13 and was renamed to `CONFIG_DRM_PANEL_HIMAX_HX83112B` afterwards. Carrying
a 6.13 config forward therefore leaves the panel driver **silently not built** —
`olddefconfig` drops the unknown symbol without a word, the build succeeds, and
the failure only shows up on the device as a compositor that loops on:

```
phoc-wlroots-CRITICAL: [backend/backend.c:245] Found 0 GPUs, cannot create backend
```

with no `/dev/dri` at all. A kernel bump can lose a feature without a single
build warning; **on every base bump, re-check that the symbols above still
exist** — this is exactly the kind of breakage step 5 of the rolling procedure
is there to catch.

## The sensor symbols come as a set

All five `IIO_QCOM_SMGR*` symbols are modules, and the four sensor drivers
depend on the core. Turning on a sensor without `CONFIG_IIO_QCOM_SMGR` silently
builds nothing, the same failure mode as the panel symbol above.

They are also useless on their own: the SSC does not start its sensors until
userspace serves it the registry, so a kernel with these enabled and no
`snsregd` running produces no IIO device at all and looks exactly like a kernel
without them. Both halves are described in
[`../sensors/README.md`](../sensors/README.md).

## The watchdog symbols are the boot-hang safety net

`CONFIG_QCOM_WDT` plus `CONFIG_WATCHDOG_HANDLE_BOOT_ENABLED` and
`CONFIG_WATCHDOG_OPEN_TIMEOUT=300` are what recovers the phone from a kernel
that hangs before systemd. They need a device-tree property to be of any use
here — the driver only arms a watchdog the bootloader already started, and the
FP3's bootloader does not, which left no watchdog at all across exactly the
window an early hang falls into. See the safety-net section in
[`../sensors/README.md`](../sensors/README.md#the-boot-hang-safety-net).
