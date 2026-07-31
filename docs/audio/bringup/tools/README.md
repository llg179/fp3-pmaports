# Audio bring-up tools

Small measurement helpers for the FP3 audio path. They read state, they do not
change it, so they are safe to run on a working phone. All of them need root,
because everything interesting lives under `/sys/kernel/debug`.

## `jack-probe.py`

Samples **every** MBHC register on the codec while a jack is plugged and
pulled, and prints a line whenever anything changes - raw, in hex and binary,
with the names of the registers that moved.

It is deliberately opinion-free. The driver has already been wrong once about
which bit of `RESULT_3` carries the plug status, and watching only the bit you
believe in is exactly how that stays undiscovered. So the tool filters nothing:
`ANA_MECH`, `ANA_ELECT`, `ANA_ZDET`, `RESULT_1..3`, `BTN0..7`, `CTL_1`,
`CTL_2`, `PLUG_DETECT_CTL` and `ZDET_RAMP_CTL` are all sampled, next to
`SW_HEADPHONE_INSERT` and `SW_MICROPHONE_INSERT` - what the driver reports to
userspace - so hardware and report can be compared edge by edge.

A decoding of `RESULT_3` and `ANA_MECH` is printed after the run, taken from
the five in-tree codecs of the same MBHC family (`wcd934x`, `wcd937x`,
`wcd938x`, `wcd939x`, `pm4125`) which map those registers identically. Treat it
as a reading aid, not as the measurement: the raw columns stand on their own if
the decoding turns out not to apply to this codec.

## Running it

```sh
sudo systemd-run --unit=jackprobe --collect \
    sh -c 'python3 jack-probe.py 300 > /var/log/jackprobe.log 2>&1'
# ... insert / remove a few times, both 3-pole and 4-pole ...
sudo cat /var/log/jackprobe.log
```

Repeat each accessory at least twice: a state that drifts one edge at a time
cannot be seen in a single insert/remove pair.

### Reading the output

- Any register that tracks the socket is a candidate for absolute plug status.
  If none does, that is a result too - it rules out replacing the driver's
  edge counter with a plain register read, and points at the init sequence
  instead.
- `ANA_MECH` bit 5 should alternate, since the driver re-arms L_DET after each
  edge. If it stays put, the re-arm write is not taking effect.
- `SW_HP` disagreeing with the hardware locates the drift, and the timestamp
  says which edge caused it.

### Caveat on the read path

The register value is fetched by seeking straight to that register's line in
the regmap debugfs dump. Reading the whole dump instead would put a few hundred
SLIMbus transactions on the bus per sample and disturb what is being measured.
The line is checked to start with the expected register number and the offset
is re-resolved if it does not, so a shifted dump cannot silently yield wrong
values - but before believing a surprising result, cross-check one sample
against a full read of the file:

```sh
sudo grep -E '^06(14|19): ' /sys/kernel/debug/regmap/*:1a0:1:0/registers
```
