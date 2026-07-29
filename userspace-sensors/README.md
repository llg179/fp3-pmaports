# FP3 sensor userspace

Everything the phone needs for the SSC sensors, next to the kernel package that
provides the drivers. Nothing here is optional: without the registry server the
sensors never start, and without the near level `iio-sensor-proxy` ignores the
proximity sensor in silence.

> **AI-generated.** Written by Claude (Opus 5) under the direction of Lajosházi,
> László Gergely, who reviewed every change and made the measurements behind the
> numbers. How this was arrived at is written up in
> [`../docs/sensors/bringup/`](../docs/sensors/bringup/); what the port consists
> of is in [`../docs/sensors/`](../docs/sensors/).

| file | role |
|---|---|
| `snsregd.py` | serves the sensor registry (QMI `SNS_REG`, service `0x10F`) so the SSC brings its sensors up. A Python stand-in for upstream's C [`sns-reg`](https://gitlab.com/msm8996-mainline/sns-reg) |
| `snsregd.service` | runs it from boot |
| `registry.conf` | 1437 key/value pairs decoded from this phone's own factory `sns.reg` |
| `groups.txt` | 68 groups / 1516 keys, from upstream `sns-reg`'s `map.c` |
| `90-fp3-proximity.rules` | `PROXIMITY_NEAR_LEVEL=1570` for `iio-sensor-proxy` |
| `sensortest.py` | reads any of the four sensors and reports whether the numbers are physically plausible |
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
`iio-sensor-proxy` skipped the device.

## Verify

```
ls /sys/bus/iio/devices/*/name | xargs cat        # four qcom-smgr-* devices
sudo python3 sensortest.py prox 12                # cover the earpiece
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
