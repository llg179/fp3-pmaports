# FP3 charging on pmOS mainline

> ⚠️ **AI-generated.** This page — and the code, device tree and tooling it
> describes — was written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement it rests on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

The PMI632 charger on the Fairphone 3 under a mainline kernel: what makes it
charge, what stops it charging too hard, and how it got from 1 A to the 2 A
this phone's pack is rated for.

## The shape of it

Everything is one PMIC. The charger, the fuel-gauge inputs and the thermistor
the safety logic reads all live inside the PMI632, and the AP only writes
registers over SPMI:

```
USB  -->  PMI632 charger (CHGR @ 0x1000)  -->  battery
             |                |
             |                +-- JEITA comparators  <-- BAT_THERM (PMIC ADC ch 0x4a)
             |
   qcom_smbx (AP) --- SPMI --+
             |
             +-- BAT_ID (PMIC ADC ch 0x4b)  ->  is this the described battery?
             |
             +-- power_supply "pmi632-charger"   (USB side: online, type, I/V)
             +-- power_supply "pmi632-battery"   (capacity from an OCV table, temp)
             +-- thermal_zone "pmi632-battery"   (free, from the power supply core)
             +-- cooling_device "qcom-smbx-charger"  <-- thermal zone "pmi632-thermal"
```

Two things follow from that picture and explain most of this page:

* **There is no coulomb-counting fuel gauge in mainline for this PMIC.**
  Capacity is interpolated from an OCV table in the board's `simple-battery`
  node, taken from Fairphone's own profile for this pack.
* **The JEITA block is hardware.** It compares the thermistor against four
  comparator thresholds and acts on the result with no software in the loop —
  which is exactly what makes it worth programming correctly before raising the
  current.

## Provenance

### Imported unchanged

`qcom_smbx.c` is **Casey Connolly's** (Linaro) SMB2 driver for the pmi8998 and
pm660. The interrupt handling, the status decoding, the AICL setup and the
power-supply plumbing are all his.

### Imported and extended here

| component | what was added | why |
|---|---|---|
| `qcom_smbx.c` | SMB5 (PMI632) support, as a variant structure rather than open-coded branches | the register *map* is largely shared with SMB2; what differs is the status-register prefix, the current step, the charge-status bit positions and where the JEITA status bits moved |
| `qcom_smbx.c` | `POWER_SUPPLY_PROP_TEMP` from the pack thermistor | nothing read the thermistor, so there was no temperature and no battery thermal zone |
| `qcom_smbx.c` | the hardware JEITA thresholds and soft-zone currents, from the device tree | the driver read the JEITA *status* for `POWER_SUPPLY_PROP_HEALTH` but nothing programmed the thresholds |
| `qcom_smbx.c` | the fast-charge current as a thermal cooling device | there was no path at all from "the phone is hot" to "charge slower" |
| `qcom_smbx.c` | the fast-charge current from `constant-charge-current-max-microamp`, bounded by the PMIC's own hardware maximum | the property was parsed and then ignored; only `voltage_max_design_uv` reached the hardware |
| `qcom_smbx.c` | verification of the battery ID before any of the battery's limits are applied | a board can name only one battery, and this one ships two — see [Which battery this phone has](#which-battery-this-phone-has) |
| `qcom-spmi-adc5.c` | the `ADC5_BAT_THERM_100K_PU` channel | the channel was missing from the table, so a device tree referencing it was rejected at probe |

Per-file detail, with commit links: [**Charger: `qcom_smbx.c`**](../kernel/README.md#charger-qcom_smbxc)
and [**Battery temperature**](../kernel/README.md#battery-temperature) in the
kernel page.

### Values taken from the vendor

Almost none of the numbers below are ours. They come out of Fairphone's
published Fairphone 3 kernel source release, checked in under
[`../device_tree/downstream/fairphone/3.A.0136/`](../device_tree/downstream/fairphone/3.A.0136/):

| value | where in the downstream tree |
|---|---|
| register offsets, the JEITA threshold block layout, the 25 mA compensation step, the 50 mA current step | `drivers/power/supply/qcom/smb5-reg.h`, `smb5-lib.c`, the `smb5_pmi632_params` table in `qpnp-smb5.c` |
| charger interrupt numbers and ADC channel assignment | `arch/arm64/boot/dts/qcom/pmi632.dtsi` |
| cell parameters, OCV curve, JEITA thresholds and per-zone currents | `qg-batterydata-Fuji-3000mah-Jan22th2019-pmi632.dtsi` — [the pack this phone has](#which-battery-this-phone-has) |
| the thermal mitigation current table | `qcom,thermal-mitigation` on the downstream charger node |

**New here** is the variant abstraction, the device-tree interface for JEITA,
the cooling device, and the per-generation ceiling on the charge current.

## Status

Measured on the device unless a row says otherwise.

| | state |
|---|---|
| charging works | yes, since the charger node was enabled |
| capacity | **integrated from the PMIC's QG fuel gauge since `r42`**, corrected against the OCV table only while the current is low — [what it was before, and why it had to change](#the-capacity-was-a-voltmeter) |
| a finished charge is restarted when the pack falls back | **yes since `r45`** — before that the SMB5 recharge field was left clear, so a charge that terminated never began again while the cable stayed in — [the measurement](#and-the-charger-really-had-stopped--a-recharge-that-could-never-happen) |
| a finished charge reads as full | **yes since `r43`** — the completion is remembered through the inhibit that follows it, instead of being caught in the instant the charger passes through termination — [why the reading stopped in the low nineties](#ninety-one-percent-on-a-charger-that-had-finished) |
| battery current and open-circuit voltage | **reported since `r42`** — `current_now` and `voltage_ocv` on `pmi632-battery`, both from the QG peripheral |
| battery temperature | yes — [how, and why the curve is approximate](../kernel/README.md#battery-temperature) |
| hardware JEITA | **running the whole time**, but on the PMIC's generic defaults until `r20` (see below) |
| JEITA thresholds from this pack's characterisation | **programmed and read back**: soft `22 04 44 ff`, hard `19 87 56 75` — byte-identical to what the stock stack programs |
| JEITA soft-zone compensation | **programmed and read back**: `0x1092 = 0x28` (−1000 mA hot), `0x1093 = 0x38` (−1400 mA cold), up from `0x0a` each |
| thermal mitigation | **live**: `cooling_device3` is `qcom-smbx-charger`, `max_state 3`, bound to `pmi632-thermal` at 70 / 80 / 90 °C |
| fast-charge current | `FAST_CHARGE_CURRENT_CFG` **`0x14` → `0x28`**, i.e. 1 A → 2 A |
| the battery is identified before its limits are applied | **yes since `r22`** — the ID reads 10.0 kΩ against the 10 kΩ the battery node declares, and the raised current is itself the proof the check passed |
| the fallback when the ID does *not* match | **implemented, not measured** — no second pack here to fit; see [Known gaps](#known-gaps) |
| 2 A actually flowing | **not measured** — needs a low state of charge and a wall charger; see [Testing](#testing) |
| the device-tree binding | **written and validated** since 2026-07-30; `dt_binding_check`, `yamllint` and `dtbs_check` all clean on the charger node, and the series is now `checkpatch --strict`-clean end to end |
| the battery node's four `qcom,*` properties | **fail `dtbs_check`** and are the one thing still blocking this series — [why, and what to do](#where-these-properties-belong) |
| high-voltage (QC) negotiation | **not done**, and now the only thing between this and a faster charge — see [the ceilings](#why-2-a-and-what-the-ceilings-would-be-on-the-other-pack) |

## The starting premise was wrong

Before writing any code the four JEITA registers were read off a running phone,
straight out of the regmap debugfs. `JEITA_EN_CFG` came back **`0x1f`** — every
bit set:

```
1061: 14      FAST_CHARGE_CURRENT_CFG  20 * 50000 = 1 000 000 uA
1090: 1f      JEITA_EN_CFG             hard limit + both float-voltage + both current bits
1091: 0a      FVCOMP
1092: 0a      CCCOMP_HOT               250 mA reduction
1093: 0a      CCCOMP_COLD              250 mA reduction
1094: 1b ff 44 c7    soft thresholds   hot ~50 degC, cold ~16 degC
1098: 15 aa 4a ff    hard thresholds   hot ~58 degC, cold ~11 degC
```

So the earlier note that "nothing writes the enable" was true, and the
conclusion drawn from it was not. **Hardware JEITA has been protecting this
phone all along** — just against the PMIC's power-on defaults, which are generic
values for no particular pack. The work is not to switch protection on. It is to
replace those thresholds with the ones Fairphone characterised for this cell.

☠️ Reading these is cheap and needs no kernel build — and it is worth doing
*before* writing the code, not after. Thirty seconds of `dd` overturned the
premise this work started from. The regmap debugfs file is fixed-width, 9 bytes
per line, so it seeks:

```sh
dd if=/sys/kernel/debug/regmap/0-02/registers bs=9 skip=$((0x1090)) count=12
```

`bs=1 skip=$((0x1090*9))` returns **nothing at all**, silently — and `cat`-ing
the whole file means 65536 SPMI reads.

## Raw ADC codes in the device tree, not degrees Celsius

The comparators take a raw `BAT_THERM` ADC code. Mainline does have the inverse
conversion (`qcom_adc_tm5_temp_volt_scale`), so carrying the thresholds in °C
and converting in the driver was a real option — and the cleaner-looking one.

It was rejected on a measurement. The generic 100k pull-up curve mainline would
have used was compared against Fairphone's four characterised codes:

| °C | Fairphone's code | from the mainline curve | error |
|---|---|---|---|
| 0 | 22133 | 22550 | **+1.54 °C** |
| 15 | 17663 | 17879 | +0.64 °C |
| 45 | 8708 | 8385 | **−1.29 °C** |
| 55 | 6535 | 6150 | **−1.97 °C** |

The errors are small, but **all four point outward** — a colder cold limit and a
hotter hot limit, so every safety window would widen in the unsafe direction. A
raw code involves no curve at all, so that is what the device tree carries.

The comparison also earns something it was not asked for: that all four land
within 2 °C **confirms the comparators work in the ADC5 raw code domain**, which
is the assumption the whole approach rests on and which nothing else here
verifies.

The same 1.5–2.5 °C divergence is why the battery *temperature* is documented as
good enough to read but not to charge by — see
[battery temperature](../kernel/README.md#battery-temperature). Nothing charges
by that curve; the hardware compares raw codes.

## Which battery this phone has

The FP3 ships **two different 3000 mAh packs**, told apart at runtime by a
battery-ID resistor. They are not interchangeable on paper:

| pack | `batt-id` | rated fast charge | JEITA cool band starts |
|---|---|---|---|
| Kayo (`qg-batterydata-Kayo-3000mah-Nov4th2019-pmi632`) | 50 kΩ | **2.7 A** | 20 °C |
| Fuji (`qg-batterydata-Fuji-3000mah-Jan22th2019-pmi632`) | 10 kΩ | **2.0 A** | 15 °C |

Booting the oracle slot and asking its stock stack settles which one is fitted:

```
/sys/class/power_supply/bms/battery_type
    Fuji_3000mAH_FG_averaged_MasterSlave_Jan22th2019
/sys/class/power_supply/bms/resistance_id
    9843
```

The two slots do not disagree about this, and could not: **mainline never reads
the battery ID.** `qcom_smbx` has no code for it and the charger node does not
request the channel, so the pack described in the device tree was a static
choice, made from the downstream sources without measuring which one this phone
has. It picked the wrong one.

The ID resistor can nevertheless be read from mainline, because `pmi632.dtsi`
already describes the channel and the ADC driver already exposes it:

```
$ cat /sys/bus/iio/devices/iio:device1/in_temp_bat_id_input
170891
```

That is the divider voltage in µV, against the PMIC's 100 kΩ pull-up on its
1.875 V reference, so R = 100k × V/(1.875 − V) = **10.03 kΩ**. Kayo's 50 kΩ
would read 625 mV, not 171. Mainline and downstream agree to 2 % on an
independent path — 10.03 kΩ against the stock stack's 9843 Ω.

**This phone has Fuji**, and both sides of the device now say so. That matters twice over. The 2 A below is the pack's
*full rating*, not a reduction of it — and the JEITA cool threshold is 15 °C,
not 20.

A `simple-battery` node cannot choose between the two, so the device tree
describes Fuji — the pack that can be measured here. What it can do, since
`r22`, is **check that the described pack is the fitted one before applying any
of its limits**:

```
                    qcom,batt-id-pullup-ohm      (charger node: board wiring)
                             |
BAT_ID pin --> ADC --> uV -->+--> R = pullup x uV / (1.875 V - uV)
                                            |
       qcom,batt-id-ohm (battery node) -->  compare, +/-15%
                                            |
                        match  -> apply the battery's current and JEITA
                     mismatch  -> leave the init sequence's ~1 A, and say so
```

Note what this is not: the ID does **not** select a profile and does not derive
a current. It is a gate on trusting the one description the device tree carries.
Selecting between two would need a binding for more than one
`monitored-battery`, which does not exist.

The cost of the single description remains: a Kayo phone charges at 1 A rather
than its rated 2.7 A — but it charges *safely*, at the conservative default,
instead of at another cell's numbers.

## What the stock stack does, measured

The oracle slot runs Fairphone's own 4.9 kernel with `qpnp-smb5`, on the same
PMIC and the same battery. Reading the same registers there is the closest thing
to a reference answer, and it was worth doing — it confirmed the encoding and
caught a wrong threshold.

| register | stock (UT / 4.9) | this port | comment |
|---|---|---|---|
| `0x1061` fast-charge current | `28` | `28` | both 2 A |
| `0x1070` float voltage | `4f` | — | 4.39 V |
| `0x1090` `JEITA_EN_CFG` | **`10`** | `1f` | see below |
| `0x1092` / `0x1093` soft compensation | `0a` / `0a` | `28` / `38` | stock leaves them at default; it compensates in software |
| `0x1094` soft thresholds | `22 04 44 ff` | `22 04 44 ff` | 45 / 15 °C — **identical** |
| `0x1098` hard thresholds | `19 87 56 75` | `19 87 56 75` | 55 / 0 °C — **identical** |

Three things come out of that.

**The hard thresholds and the soft-hot threshold match byte for byte**, which is
an independent check that the big-endian hot-then-cold layout and the raw-code
encoding used here are right — arrived at from the downstream source, confirmed
against the hardware it actually programs.

**`JEITA_EN_CFG` is `0x10` on stock, `0x1f` here.** Downstream sets
`qcom,sw-jeita-enable` and then calls `smblib_disable_hw_jeita()`, which clears
the four soft-limit bits: it programs the hardware thresholds but does the
compensation itself, in software, from the five-band `qcom,jeita-fcc-ranges`
table. This port does the opposite — it lets the hardware do it, which costs
resolution (one threshold per side instead of five bands) and buys not needing
software in the loop.

**Both systems settle on 2 A**, and the stock votable says why:

```
FCC: BATT_PROFILE_VOTER:  en=1 v=2000000
FCC: JEITA_VOTER:         en=1 v=2000000
FCC: THERMAL_DAEMON_VOTER: en=0
FCC: effective=BATT_PROFILE_VOTER type=Min v=2000000
```

The pack's own profile is the binding vote. The number this port chose from the
compensation-register arithmetic below turns out to be the number the vendor
stack runs at, for a different and simpler reason.

Downstream also registers the charger as a cooling device — `cooling_device9`,
type `battery`, `max_state 6` for its six-entry mitigation table — driven by its
thermal daemon rather than by a thermal zone.

## The capacity was a voltmeter

Until `r42` the reported capacity was the battery's terminal voltage looked up
in the `ocv-capacity-table-0` of the battery node. That table is the downstream
QG profile and it is correct — but it maps an **open-circuit** voltage, and a
phone's terminal voltage is nothing like one. It also spends eighteen points of
charge on the forty millivolts between 3.80 V and 3.84 V, so a small voltage
error is a large capacity error exactly where the battery spends most of its
life.

Measured on 2026-08-08 against the oracle slot, alternating between the two on
the same charge and the same cable:

| | this port, before the change | stock (UT / 4.9, `qpnp-qg`) |
|---|---|---|
| at rest, charging at ~380 mA | 59–65 % | **55–57 %** |
| terminal voltage, same moment | 3.96 V | 3.96 V |
| after 3 min of eight-thread `sha256sum` | **6 %** | **57 %** |
| terminal voltage under that load | 3.72 V | 3.64 V |

Two things fall out of that pair of columns. The terminal voltages agree to
within 1.3 mV, so nothing is wrong with the measurement — and the stock gauge
does not move *at all* across a 330 mV swing, so it is plainly not reading the
terminal voltage either. It coulomb-counts, and anchors to an open-circuit
voltage only when the current is near zero.

That also rules out the obvious cheap fix. Fitting a resistance to the load step
gives ~380–420 mΩ on **both** systems, while the pack's actual internal
resistance is 118–166 mΩ; the rest is the difference between a bursty load and
an averaged current sample. Subtracting `I·R` from a heavily loaded terminal
voltage does not recover the open-circuit one, and a resistance large enough to
make it look like it did would be wrong everywhere else.

### What it reads now, measured the same way

Same phone, same protocol, after the change — the load step is the one
`52-fuel-gauge` runs, and the oracle reading is 80 seconds after the pmOS one
with the phone charging throughout:

| | this port, after | stock, same charge |
|---|---|---|
| mid-charge, at ~360 mA | 82 % | **85 %** |
| near full, in taper at ~300 mA | 90 % | **96 %** |
| across a 30 s eight-thread burn | **90 % → 90 %** | (not re-run; it held 57 % before) |
| terminal voltage across that burn | 4.413 V → 4.183 V | — |
| battery current across it | +276 mA → −274 mA | — |

The load sensitivity is gone outright: 229 mV of sag moves the reported capacity
by zero points, where the same step used to move it by tens. Each oracle reading
above is 60–90 s after the pmOS one it sits beside, with the phone charging
across the slot switch.

**What is left is a lag, and it is worst near the top of the charge**: three
points behind the oracle mid-charge, six near full. The cause is visible in the
gauge's own numbers — near full it reported 90 % while its *own* open-circuit
estimate put the pack at 98 %, so the integral is drifting and the correction
that would catch it is switched off. It is switched off because the gate is on
current, and this phone charges at about 300 mA the whole way, which is above
the 150 mA band.

The gate is on the wrong quantity. What decides whether an OCV reading is worth
anything is not the current but **how much a millivolt of error in it costs**,
and that varies enormously along this curve: forty millivolts covers eighteen
points of charge in the flat middle and about two at either end. So the same IR
uncertainty that makes the OCV useless at 30 % makes it perfectly usable at
95 %. Evaluating the table at both ends of a plausible resistance range and
trusting the OCV whenever the two agree would gate on exactly that, and would
need no current threshold at all.

That is the next change, and it is deliberately not made here: settling its one
threshold honestly needs a full charge and discharge measured against the
oracle, not the handful of points above.

### What the PMIC already had

The PMI632's QG peripheral sits at `0x4800` on the same SPMI slave as the
charger, and it is **already running under mainline** — the PMIC's own boot
sequence starts it, so nothing here has to configure it. That is worth stating
plainly because the earlier note in this file that "no coulomb counter exists
for this PMIC in mainline" was about the absence of a *driver*, and was read as
the absence of the hardware.

Read-only, and confirmed live on this phone before any driver change, through
the regmap debugfs (9 bytes per line, so the offset is the address times nine):

```
dd if=/sys/kernel/debug/regmap/0-02/registers bs=9 skip=$((0x48c0)) count=4
```

| register | what it holds |
|---|---|
| `0x48c0` `LAST_ADC_V` | battery voltage, 194.637 nV per LSB |
| `0x48c2` `LAST_ADC_I` | battery current, signed, 152.588 nA per LSB, negative into the battery |
| `0x4870` `S7_PON_OCV` | open-circuit voltage measured at power-on, before anything drew |
| `0x4874` `S3_GOOD_OCV` | open-circuit voltage measured whenever the PMIC has seen the current near zero long enough |
| `0x4888` … `0x488e` | hardware accumulators: summed V, summed I, sample count |

The controls that make those trustworthy: `LAST_ADC_V` agreed with the
independent ADC5 `vbat_sns` channel to within 1.3 mV, it followed the load step
within one sample period, and `LAST_ADC_I` changed sign at the charge-to-
discharge crossing.

### What the driver does now

`qcom_smbx` carries the gauge base per PMIC variant (`smb_variant.qg_base`),
polls the voltage/current pair every ten seconds, and integrates it. The OCV
table is still the reference, but it is only consulted as a correction, weighted
by how quiet the current is: strongly below 50 mA, weakly below 150 mA, not at
all above that. A poll more than a minute late means the machine was suspended,
and a suspended phone is a rested battery — the one state where the table needs
no correction at all — so those re-anchor outright rather than integrating a
current nobody drew. Charge termination is taken from the charger, which knows
that better than any gauge does — but it has to be *remembered* rather than
caught, for the reason in the next section.

### Ninety-one percent on a charger that had finished

Measured 2026-08-08 on `r42`, on a phone that had been left on a wall charger
and had stopped climbing. The reported capacity sat in the low nineties and the
user interface said the charge was over, which read as a charger that gave up
early. It was not: the charger had done everything right and the *gauge* was
refusing to say so.

| register | read | meaning |
|---|---|---|
| `0x1006` | `0x40` | `CC_SOFT_TERMINATE` set, status code 0 — **inhibit**, not a fault |
| `0x1007` | `0x28` | no `BAT_OV` (that is bit 1 on SMB5) |
| `0x100d` | `0x00` | no JEITA zone active |
| `0x1070` | `0x4f` | float voltage 4.39 V, exactly what the device tree asks for |
| QG `0x48c0` | | 4.3149 V at **0 mA** into the pack |

**Three** things were wrong. Two were in the gauge; the third was in the
charger, and it was the one that actually stopped the charge.

**Termination is a state the charger passes through, not one it sits in.** Once
it has terminated, the cell is by definition above the recharge threshold, so
the hardware moves straight to inhibit and stays there until the cable comes out
or the voltage falls. A ten-second poll therefore has to land inside a window
the hardware leaves as fast as it can — and even when it does, the next poll
resumes correcting toward the OCV table at a quarter of the gap per poll, so a
correctly latched hundred percent is walked back down within a minute.

**And where it walks down to is not an error in the table.** The table's top
entry is an OCV of 4.3756 V, which a cell held at a 4.39 V float only shows
while it is still being held there. Let go, it settles some seventy millivolts
lower — six percent down this curve. So a battery as full as this charger will
ever make it reads in the mid nineties, and keeps reading that for as long as it
stays on the cable.

Since `r43` the driver remembers the completion instead of catching it. Inhibit
on its own is not evidence of a full pack — it is equally what a charger does
when handed a cell that was already above the threshold when the cable went in —
but inhibit *after a charge that was actually running* is the tail of that
charge. Tracking that pairing needs no knowledge of where the inhibit threshold
sits, survives any polling interval, and clears itself when the input goes away
or the charger starts charging again. The battery's status reads `Full` there
too, which the status code alone cannot support saying.

☠️ **Still open:** unplugging a full pack drops the reading to what the table
says about a rested cell, because nothing has re-anchored the table's top to the
OCV this pack actually rests at once full. Learning that anchor is a separate
change and wants a charge and a discharge measured against the oracle.

#### And the charger really had stopped — a recharge that could never happen

☠️ The two gauge bugs above were found first and made a tidy story: the charger
had done its job and only the reporting was wrong. That story was tested by
letting the pack fall, and it did not survive. At 4.24 V of a 4.39 V float,
with 500 mA available at the input, the charger delivered **exactly zero**
current. Pulling the cell to 4.14 V under a full-core load did not start it
either — which is what rules out the inhibit threshold, since no inhibit
setting on this part reaches that far down.

`CHGR_CFG2` is where a recharge is configured, and **its lower bits are not the
same on the two PMIC generations**. SMB2 has `AUTO_RECHG` at BIT(2) and
`EN_ANALOG_DROP_IN_VBATT` at BIT(1). SMB5 replaces both with a single two-bit
field naming what a recharge is decided *by*:

| `CHGR_CFG2[2:1]` | meaning on SMB5 |
|---|---|
| `00` | nothing restarts a finished charge |
| `10` (`VBAT_BASED_RECHG_BIT`) | the battery voltage |
| `11` (`SOC_BASED_RECHG_BIT`) | the state of charge |

`qcom_smbx`'s pmi632 init sequence was derived from the SMB2 one and carried
the same value across, so the field came out `00` — the one setting under which
a terminated charge is never restarted for as long as the cable stays in. State
of charge would not have worked anyway: the gauge that reports one to the PMIC
is Qualcomm's own `qpnp-qg`, which is not in mainline.

Fixed in `r45`: select the battery voltage, take three comparator samples
before acting as the vendor driver does whenever it makes that choice, and
program `CHGR_ADC_RECHARGE_THRESHOLD_MSB/LSB` from a new
`qcom,auto-recharge-microvolt` on the battery node — in the same 194637 nV
units the gauge reports, because it is the same ADC. This phone declares
4.30 V, which is what its own downstream node asks for.

☠️ **A wrong register was written first, and the phone said so.** The same fix
was attempted one revision earlier against `FG_UPDATE_CFG_2_SEL`, which is what
the SMB2 half of the driver uses for this — but that is `CHGR + 0x7D`, and on
SMB5 the same offset is `CHARGE_RCHG_SOC_THRESHOLD_CFG_REG`, a threshold rather
than a selector. The bit read back exactly as programmed and nothing else
changed, which is the signature of writing a register that is not the one you
meant. The disproven commit is kept at
`archive/wip-7.1.3-charger-smb2-recharge-register` with the verdict in its tag
message. **What settled it was the vendor's own `smb5-reg.h`**, which is on
disk with the rest of the downstream 4.9 tree; an earlier search for it had
been abandoned when a `find` across the big disk timed out, and a timed-out
search is not a negative result.

The gauge starts from the open-circuit voltage the PMIC measured with nothing
drawing, rather than from a live sample taken while the machine is busy booting.

The IR correction needs a resistance, which the board supplies as
`factory-internal-resistance-micro-ohms`; this phone declares 120 mΩ, what the
PMIC's own ESR measurement reports while the vendor stack runs it. Because the
correction is only ever applied at low current, the choice between that and the
profile's 166 mΩ is worth a few millivolts.

## Why 2 A, and what the ceilings would be on the other pack

For the Fuji pack fitted here, 2 A is simply its rating. The arithmetic below
still matters, because it is what a **Kayo** FP3 would run into if it asked for
its 2.7 A — and because it is why raising `fcc_max_ua` past 2 A on SMB5 is not a
one-line change.

Two independent ceilings, and the lower one is not the battery.

**The compensation register runs out.** The JEITA soft-zone reduction is a
six-bit field of 25 mA steps — at most **1575 mA** of reduction from whatever
fast-charge current is programmed. Both packs are characterised for 600 mA in
the cool zone:

| fast-charge current | lowest reachable soft-zone current | profile wants |
|---|---|---|
| 2700 mA (Kayo's rating) | 1125 mA | 600 mA — **not expressible** |
| 2000 mA (Fuji's rating) | 425 mA | 600 mA — fine |

So on a Kayo phone the hardware **cannot implement Fairphone's own profile at
the pack's rated current**. Anything at or below 2175 mA can — which is one
reason the SMB5 ceiling in the driver sits at 2 A and moving it is a decision
rather than an edit. It also explains why downstream compensates in software
instead: it is not bound by that register at all.

**The port runs out first anyway.** Without high-voltage negotiation — which
mainline `qcom_smbx` does not do — a DCP gives 1.5 A at 5 V, which is about
1.9 A into a 3.8 V cell at best. Above roughly 2 A the binding constraint stops
being the charger and becomes the USB port, which is the right place for it, and
it is why the input side is the next thing worth doing rather than the charge
current.

## The device-tree interface

Split by whose fact each value is, which is the reason it looks like this rather
than all in one node.

**On the battery** — everything that describes the cell:

```dts
fp3_battery: battery {
	compatible = "simple-battery";
	constant-charge-current-max-microamp = <2000000>;
	constant-charge-voltage-max-microvolt = <4390000>;

	qcom,batt-id-ohm = <10000>;
	qcom,auto-recharge-microvolt = <4300000>;
	qcom,jeita-hard-thresholds = <0x5675 0x1987>;   /* cold 0 degC, hot 55 degC */
	qcom,jeita-soft-thresholds = <0x44ff 0x2204>;   /* cool 15 degC, warm 45 degC */
	qcom,jeita-soft-fcc-microamp = <600000 1000000>;
};
```

Each threshold pair is `<cold hot>`, as raw ADC codes; a higher code is a colder
battery, so the driver rejects a pair whose hot value is not the smaller one.

`qcom,jeita-soft-fcc-microamp` is the current to be **left** in each soft zone,
not the register's own offset — so the battery node describes a charge current
and the driver works out the delta. It reads the fast-charge current back out of
the hardware to do that, rather than trusting the device tree to match.

An optional `qcom,batt-id-tolerance-percent` overrides the default 15, which is
the window the vendor's `batt-id-range-pct` uses on this board.

`qcom,auto-recharge-microvolt` is the voltage a finished charge is started again
at. It sits on the battery because how far a cell may relax before it is worth
cycling is a property of that cell, not of the board — and it is optional, since
a comparator left at its power-on threshold still works and a made-up threshold
for an unknown pack does not improve on it. SMB5 only: on SMB2 the same decision
is configured elsewhere.

**On the charger** — what belongs to the board rather than to the pack:

```dts
&pmi632_charger {
	monitored-battery = <&fp3_battery>;
	qcom,batt-id-pullup-ohm = <100000>;
	qcom,thermal-mitigation = <2000000 1500000 1000000 500000>;
};
```

The pull-up follows from the ADC channel chosen in `pmi632.dtsi`, but nothing in
the IIO consumer interface exposes which channel a consumer was given, so the
board states it. The mitigation table is a thermal-design fact, not a cell one.

**In the driver** — only what the PMIC itself imposes: `smb_variant::fcc_max_ua`
is the datasheet maximum of the fast-charge register on that generation, 3 A on
the PMI632 and 4.5 A on the pmi8998, taken from the `smb_params.fcc.max_u`
values Qualcomm's own drivers carry. It exists to stop a device tree asking the
hardware for something it cannot do — not to express an opinion about how hard
a battery should be charged, which is the board's business and was, for one
revision, wrongly encoded here.

**The binding.** The charger half of the above is documented as of 2026-07-30, in
the *existing* `Documentation/devicetree/bindings/power/supply/qcom,pmi8998-charger.yaml`
rather than a second file: one driver (`qcom_smbx`) serves all three PMICs, and
SMB2 and SMB5 differ in their register layout, not in the shape of the binding.
`qcom,pmi632-charger` joins the `compatible` enum; the three extra io-channels
become optional (`minItems: 2`), matching a driver that takes `vbat`,
`bat_therm` and `bat_id` with `devm_iio_channel_get()` and carries on without any
of them. Validated with `dt_binding_check` on both examples, `yamllint` against
the bindings' own config, and `dtbs_check` against this board's DTB, where the
charger node passes. It closed the last `checkpatch` complaint on the series.

### Where these properties belong

The split above is the one this port runs, and it is **not settled for
upstream**. Two things argue against the battery node as written:

* `battery.yaml` sets `additionalProperties: false` and contains **no**
  vendor-prefixed property at all, so `dtbs_check` rejects all four `qcom,*`
  names — measured, not predicted. The only JEITA precedent in tree,
  `qcom,jeita-extended-temp-range`, lives on a **charger** node
  (`qcom,pm8941-charger.yaml`).
* the thresholds are **raw BAT_THERM ADC codes**, and a code depends on the
  PMIC's ADC full scale and on the board's 100 kΩ pull-up as much as on the cell.
  By the same layering rule that moved the current ceiling out of the driver,
  a raw code is not a property of the battery.

The likely upstream shape is therefore: thresholds on the charger node, and the
pack identity as a **generic** `id-resistor-ohms` in `battery.yaml` — an ID
resistor is not a Qualcomm idea. That is a driver change as well as a device-tree
one, since the driver would read them from a different node, so it wants its own
build-and-measure cycle rather than an edit here.

## Thermal mitigation

The charger is registered as a thermal cooling device, so a thermal zone
throttles charging the way it throttles a CPU. State 0 is the unmitigated
current and each further state is lower.

Downstream drives the same table from a userspace thermal daemon through a
vendor power-supply property (`POWER_SUPPLY_PROP_SYSTEM_TEMP_LEVEL`). Driving it
from a thermal zone instead is what is new here.

The zone it binds to is **`pmi632-thermal`, the PMIC's own die temperature** —
which is the charger's die. Downstream calls the same idea
`qcom,hw-die-temp-mitigation`. The trip temperatures are **ours**: downstream's
thresholds live in its thermal daemon's configuration, not in its device tree,
so there was nothing to copy. They sit below the PMI632's own alarm at 95 °C
with room to taper first, against a die that idles at 37 °C on this board:

| trip | cooling state | fast-charge current |
|---|---|---|
| 70 °C | 1 | 1500 mA |
| 80 °C | 2 | 1000 mA |
| 90 °C | 3 | 500 mA |

The mitigation and the JEITA compensation compose without either knowing about
the other, because the compensation is a subtraction from whatever is
programmed: a mitigated current stays mitigated inside the soft zones too.

☠️ Each state is **clamped** to the current actually programmed, not validated
against it. That matters in exactly the case the ID check creates: if the fitted
battery cannot be identified the charger stays on ~1 A, while the board's table
still starts at the 2 A it was written for. An earlier revision rejected that as
a device-tree error and failed probe — so the outcome of a safety fallback was a
phone with no charger driver at all. Mitigation may only ever reduce.

## Building and installing

Nothing here is charger-specific and all of it is documented centrally:

* **kernel config** — `CONFIG_CHARGER_QCOM_SMB2` is built as a module, enabled
  by the package's `prepare()` rather than by the checked-in config, along with
  the other symbols the inherited config does not set:
  [`../kernel/config.md`](../kernel/config.md)
* **building and deploying** the kernel package, including the device-tree-only
  shortcut: [`../deploy/README.md`](../deploy/README.md)

There is no userspace component. Unlike the sensor stack, the charger needs
nothing installed beyond the kernel package.

## Testing

Two `fp3-selftest` checks, deliberately kept apart:

| check | what it proves | needs |
|---|---|---|
| [`50-charger`](../../tests/checks/50-charger-test.sh) | both power supplies bound, capacity and voltage are in range, and the battery actually **gains** charge over a short window — not merely that `status` says `Charging` | a cable |
| [`51-battery-temp`](../../tests/checks/51-battery-temp-test.sh) | the thermistor reads, and the `pmi632-battery` thermal zone exists | nothing |

☠️ They are separate on purpose. `50-charger` declares `Requires: cable` and is
skipped **whole** without one, while the thermistor is read through the ADC
whether anything is charging or not. Folding the temperature check into it would
have hidden the property in exactly the runs that do not plug the phone in.

Neither check covers charging *safely at current*. That needs a low state of
charge, a USB power meter, and both a high-current wall charger and a plain SDP
port, watching what the meter says against what the driver reports and against
the die and connector temperatures. Raise in steps — 1.0 → 1.5 → 2.0 A — rather
than in one move.

The registers are their own check, and the fastest one:

```sh
dd if=/sys/kernel/debug/regmap/0-02/registers bs=9 skip=$((0x1061)) count=1
dd if=/sys/kernel/debug/regmap/0-02/registers bs=9 skip=$((0x1090)) count=12
```

Measured on `linux-fp3-7.1.3-r20` (`#21-fp3`), against the same registers read
on `r19` before the change:

| register | `r19` | `r20` | **`r22`** | |
|---|---|---|---|---|
| `0x1061` fast-charge current | `14` | `28` | **`28`** | 1 A → 2 A |
| `0x1092` JEITA hot compensation | `0a` | `28` | **`28`** | −250 mA → −1000 mA |
| `0x1093` JEITA cold compensation | `0a` | `38` | **`38`** | −250 mA → −1400 mA |
| `0x1094` soft thresholds | `1b ff 44 c7` | `22 04 3e bc` | **`22 04 44 ff`** | ~50/16 °C → 45/20 → **45/15**, the vendor's values |
| `0x1098` hard thresholds | `15 aa 4a ff` | `19 87 56 75` | **`19 87 56 75`** | ~58/11 °C → 55/0 °C |

On `r22` the `0x28` in the first row is doing double duty: it is the charge
current *and* the proof that the battery-ID check passed, because a mismatch
leaves the init sequence's `0x14` there. There is no need to enable the driver's
debug print to know the gate opened.

`JEITA_EN_CFG` reads `0x1f` in both, which is the point of the section above: the
block was never off.

The device tree is checkable too, and worth doing as a **differential** — the
7.1.3 base fails `dtbs_check` 44 times on its own, so an absolute count says
nothing:

```sh
pip install dtschema yamllint          # needs swig, libfdt-dev, python3-dev
make ARCH=arm64 CC=gcc HOSTCC=gcc CHECK_DTBS=y \
     qcom/sdm632-fairphone-fp3.dtb
```

Run it once with the board files from the base checked out and once with this
branch's, and diff the two sorted error lists. Of the errors this tree adds, the
charger owns exactly one — the battery node — since the cooling-map node names
were fixed on 2026-07-30.

## Known gaps

* **The charge status was wrong at both ends of a charge until `r41`**, and the
  two causes are worth knowing because both are generation-dependent fields
  that looked generation-independent: BAT_OV is bit 5 of `STATUS_2` on SMB2 and
  bit 1 on SMB5, and the eight `BATTERY_CHARGER_STATUS_1` codes were renumbered
  (INHIBIT 6 -> 0, PAUSE into the vacated 6). Codes 3, 4, 5 and 7 agree, so the
  SMB2 table read correctly through the middle of every charge. Found because
  the phone said *Not charging* while the QG showed 300 mA going in.
* **The gauge has no learned capacity and no cycle counting.** It integrates
  against `charge-full-design-microamp-hours`, so an aged pack reads optimistic
  by however much it has faded. The PMIC's SDAM keeps a learned capacity and a
  cycle-count table that the vendor stack maintains; nothing here writes or
  reads them.
* **State of charge does not survive a reboot.** It is re-seeded from the PMIC's
  own power-on open-circuit measurement each boot, which is a good seed but not
  a continuation — the SDAM slot that would carry it across (`0xb147`, still
  holding whatever the vendor stack last wrote) is not read. Writing it would
  also make the two stacks agree across a slot switch.
* **`current_now` on `pmi632-charger` disagrees with the input current.** It
  reports about 199 mA where the vendor stack reports 499 mA for the same
  supply, and where the QG says 300–390 mA is reaching the battery — which
  199 mA of input cannot deliver. The `usb_in_i` scaling is the suspect; this is
  a separate measurement and is not fixed.
* **No high-voltage negotiation**, so the input side caps the whole thing near
  1.9 A into the cell — just under the 2 A the charger is now programmed for.
  This is the next thing worth doing on this side, and it is a piece of work in
  its own right.
* **The device tree can still describe only one of the two packs.** The ID is now
  read and checked, so the wrong pack is no longer charged to the wrong limits —
  it falls back to ~1 A instead. What is missing is *selection*: a binding for
  more than one `monitored-battery`, which mainline does not have. Until then a
  Kayo phone charges at 1 A rather than its rated 2.7 A, and still gets the
  wrong OCV curve, because capacity is read from the battery node whether the ID
  matched or not.
* **The mismatch path has not been exercised on hardware.** There is no second
  pack here to fit, and the check is written but only ever seen taking the
  matching branch. The cheap way to measure it is a device-tree-only cycle with
  `qcom,batt-id-ohm` deliberately set to the other pack's 50000: the log should
  carry *"Battery ID is … ohm, but the described battery is 50000 ohm"* and
  `0x1061` should stay at `0x14`. Two DTB deploys, no kernel build.
* **A mismatch leaves the previous boot's JEITA thresholds in place, not the
  PMIC's defaults.** Nothing writes those registers unless the battery verifies,
  and a warm reboot does not reset the PMIC — so after a pack swap the comparators
  keep the *old* pack's thresholds until a cold boot. The current is safe; the
  temperature limits are stale. Programming a known-safe default on the mismatch
  path would fix it, and needs a value nobody has characterised.
* **The float-voltage half of JEITA is left alone.** The two `*_SL_FCV` bits are
  whatever the PMIC defaults them to, because the register that scales the
  voltage reduction is not documented for this generation in any source
  available here — so there is nothing to program it from. Only the two
  charge-current bits are driven.
* **Hardware JEITA has one threshold per side, downstream's profile has five
  bands.** The 40–45 °C step at 1500 mA cannot be expressed; the hardware gives
  cool → 600 mA and warm → 1000 mA. Implementing the full table would mean
  software JEITA, which would then be driven by the approximate temperature
  curve rather than by the comparators.
* **The trip temperatures are a choice, not a measurement.** They are bounded by
  the PMI632's own alarm above and the idle die temperature below, but nobody
  has yet charged this phone hard enough to see which one it reaches.
* **No step charging and no `auto-recharge-vbat-mv`.** Downstream sets both
  (`qcom,step-charging-enable`, 4300 mV); they are worth copying once the above
  is exercised.

## Pitfalls

* **A green build is not the change.** `CONFIG_CHARGER_QCOM_SMB2` is set by the
  package's `prepare()`, not by the checked-in config — reading
  `config-fp3.aarch64` alone says `is not set` and means nothing.
* **`constant-charge-current-max-microamp` used to be documentation.**
  `power_supply_get_battery_info()` was called and only `voltage_max_design_uv`
  reached the hardware. If an older kernel is in the picture, raising the number
  in the device tree changes nothing at all.
* **☠️ A precise citation is not a check.** The JEITA thresholds here were, for
  one revision, the *other* pack's — copied out of the vendor tree and documented
  with the exact filename, which is what made the mistake survive. The vendor
  ships several `qg-batterydata-*` files and the board includes two of them;
  naming the file you copied from says nothing about whether it applies. That is
  what the ID check is for now, and why the battery node declares the resistance
  it expects.
* **The JEITA compensation is relative to the programmed current**, so it has to
  be computed after the fast-charge current is set — which is why both it and
  the cooling device are initialised below that point in probe, and why both
  read the register back rather than trusting the device tree.
* **`50-charger` is skipped without a cable**, and a skipped check is not a
  passing one. Check what the run actually reported.
