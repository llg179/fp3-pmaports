# Audio bring-up tools

Small measurement helpers for the FP3 audio path. They read state, they do not
change it, so they are safe to run on a working phone. All of them need root,
because everything interesting lives under `/sys/kernel/debug`.

## `jack-probe.py`

Samples the WCD9335's own view of the headset jack against what the driver
reports to userspace, and prints a line whenever anything changes:

| column | source | meaning |
|---|---|---|
| `RESULT_3` / `plug(hw)` | codec register `0x0619` bit 3 | the codec's settled mechanical plug status, bit set while the jack is out |
| `MECH` / `armed_for` | codec register `0x0614` bit 5 | which direction the L_DET block is currently armed for |
| `SW_HP`, `SW_MIC` | `EVIOCGSW` on the "Headset Jack" input device | `SW_HEADPHONE_INSERT` and `SW_MICROPHONE_INSERT`, i.e. what the driver reports |

The driver tracks insertion by flipping a flag on every L_DET edge rather than
by reading the plug status, so the hardware columns and the switch columns can
disagree - and once they do, nothing puts them back in step. Seeing that
disagreement, and seeing whether `RESULT_3` tracks the plug at all, is what
this tool is for.

Run it, then plug and unplug a headset several times:

```sh
sudo systemd-run --unit=jackprobe --collect \
    sh -c 'python3 jack-probe.py 300 > /var/log/jackprobe.log 2>&1'
# ... insert / remove a few times, both 3-pole and 4-pole ...
sudo cat /var/log/jackprobe.log
```

Repeat each plug at least twice: a single insert/remove pair cannot show a
state that drifts one edge at a time.

### Reading the output

- `plug(hw)` should follow the socket. If it never changes while the switches
  do, the register is not a usable source of absolute state on this board -
  which is a result worth having, because it rules out replacing the driver's
  counter with a plain register read.
- `armed_for` should alternate, since the driver re-arms L_DET after each edge.
  If it stays put, the re-arm write is not taking effect.
- `SW_HP` disagreeing with `plug(hw)` locates the drift, and the timestamp says
  which edge caused it.

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
