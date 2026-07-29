# FP3 sensor userspace

One file, and without it nothing works: `iio-sensor-proxy` refuses to use a
proximity sensor that has no near level, logging *"Found proximity sensor but
no PROXIMITY_NEAR_LEVEL udev property"* and leaving `ProximityNear` permanently
false — the screen simply never blanks during a call, with no error anywhere.

```
sudo install -m644 90-fp3-proximity.rules /etc/udev/rules.d/
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=iio
sudo systemctl restart iio-sensor-proxy
```

Verify:

```
udevadm info /sys/bus/iio/devices/iio:device*/ | grep NEAR   # PROXIMITY_NEAR_LEVEL=1570
busctl --system get-property net.hadess.SensorProxy \
    /net/hadess/SensorProxy net.hadess.SensorProxy HasProximity   # b true
sudo monitor-sensor --proximity      # cover the earpiece: near flips 0/1
```

Note that `iio-sensor-proxy` only polls the sensor while a client has claimed
it, which during a call is phosh's job. Reading `ProximityNear` off the bus
without a claim shows `false` no matter what the sensor says — that is not a
fault, it is why the check above uses `monitor-sensor`, which claims it.

## Where the number comes from

`1570` is the phone's own factory calibration (`ps_near` in
`/persist/sensors/sns.reg`), and the measurement agrees with it: the driver's
`in_proximity_raw` is a reflected-infrared count that reads 0..507 with nothing
near and 1713..2714 with a hand over the earpiece.

The kernel side needs `linux-fp3` r15 or newer — earlier packages had no
`in_proximity_raw` at all, so `iio-sensor-proxy` skipped the device silently.
See [`../docs/sensors/README.md`](../docs/sensors/README.md) for how it got
there.
