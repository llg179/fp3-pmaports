# FP3 sensor userspace

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

Everything the phone needs for the SSC sensors, next to the kernel package that
provides the drivers. Nothing here is optional: without the registry server the
sensors never start, and without the near level `iio-sensor-proxy` ignores the
proximity sensor in silence.

| file | role |
|---|---|
| `snsregd.py` | serves the sensor registry (QMI `SNS_REG`, service `0x10F`) so the SSC brings its sensors up. A Python stand-in for upstream's C [`sns-reg`](https://gitlab.com/msm8996-mainline/sns-reg) |
| `snsregd.service` | runs it from boot |
| `registry.conf` | 1437 key/value pairs decoded from this phone's own factory `sns.reg` |
| `groups.txt` | 68 groups / 1516 keys, from upstream `sns-reg`'s `map.c` |
| `90-fp3-proximity.rules` | `PROXIMITY_NEAR_LEVEL=1570` for `iio-sensor-proxy` |
| `sensortest.py` | reads any of the sensors (`accel`, `gyro`, `mag`, `prox`, `light`) and reports whether the numbers are physically plausible |
| `iiolog.py` | dumps timestamped samples from one buffer-only device to a CSV, so the analysis happens on the host. Log the accelerometer alongside whatever you are calibrating — it is the only way to ask "was the phone in the same orientation?" afterwards |
| `magfit.py` | fits the magnetometer's hard-iron offset and per-axis gain from an `iiolog.py` run, and reports the residual, which is what says whether the run was valid |
| `proxcal.sh` | prints `in_proximity_raw` once a second, for calibrating the near level on another unit |

## Install

```
sudo install -m755 snsregd.py /usr/local/bin/
sudo install -m644 snsregd.service /etc/systemd/system/
sudo mkdir -p /etc/sns-reg.d && sudo cp registry.conf groups.txt /etc/sns-reg.d/
sudo systemctl enable --now snsregd

sudo install -m644 90-fp3-proximity.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=iio
sudo systemctl restart iio-sensor-proxy
```

Needs `linux-fp3` r15 or newer — earlier packages had no `in_proximity_raw`, so
`iio-sensor-proxy` skipped the device. `in_illuminance_input` needs r16.

## Verify

```
ls /sys/bus/iio/devices/*/name | xargs cat        # four qcom-smgr-* devices
sudo python3 sensortest.py prox 12                # cover the earpiece
sudo python3 sensortest.py light 20               # cover, then a torch
udevadm info /sys/bus/iio/devices/iio:device*/ | grep NEAR
busctl --system get-property net.hadess.SensorProxy \
    /net/hadess/SensorProxy net.hadess.SensorProxy HasProximity
sudo monitor-sensor --proximity                   # near flips 0/1
```

☠️ `ProximityNear` on the bus stays `false` until a client **claims** the sensor
— during a call that is phosh's job. Reading the property without a claim looks
exactly like a dead sensor, which is why the check above uses `monitor-sensor`.

☠️ The IIO device index moves between boots: the Sensor Manager registers each
device as its enumeration completes, so the accelerometer has been `iio:device2`
on one boot and `iio:device3` on the next. Match on `name`, as the udev rule and
`sensortest.py` do.

## Where the near level comes from

`1570` is the phone's own factory calibration (`ps_near` in
`/persist/sensors/sns.reg`), and the measurement agrees: `in_proximity_raw` is a
reflected-infrared count that reads 0..507 with nothing near and 1713..2966 with
a hand over the earpiece. On another unit, run `proxcal.sh` and pick a value
between the two levels.
