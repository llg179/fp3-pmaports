# FP3 charging on pmOS mainline

The PMI632 charger on the Fairphone 3 under a mainline kernel: what makes it
charge, what stops it charging too hard, and why the current it settles on is
2 A rather than the 2.7 A the pack is rated for.

> **AI-generated.** The driver changes, device tree and documentation in this
> directory were written by Claude (Opus 5) working under the direction of
> Lajosházi, László Gergely, who reviewed every change and made or reviewed
> every measurement they rest on. Kernel commits carry `Co-authored-by: Claude`;
> anything prepared for the LKML carries `Assisted-by:` instead and never a
> `Signed-off-by` from the assistant, since only a human can certify the DCO.

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
| `qcom_smbx.c` | the fast-charge current from `constant-charge-current-max-microamp`, bounded per generation | the property was parsed and then ignored; only `voltage_max_design_uv` reached the hardware |
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
| cell parameters, OCV curve, JEITA thresholds and per-zone currents | `qg-batterydata-Kayo-3000mah-Nov4th2019-pmi632.dtsi` |
| the thermal mitigation current table | `qcom,thermal-mitigation` on the downstream charger node |

**New here** is the variant abstraction, the device-tree interface for JEITA,
the cooling device, and the per-generation ceiling on the charge current.

## Status

Measured on the device unless a row says otherwise.

| | state |
|---|---|
| charging works | yes, since the charger node was enabled |
| capacity | from the OCV table; no coulomb counter exists for this PMIC in mainline |
| battery temperature | yes — [how, and why the curve is approximate](../kernel/README.md#battery-temperature) |
| hardware JEITA | **running the whole time**, but on the PMIC's generic defaults until now (see below) |
| JEITA thresholds from this pack's characterisation | implemented, **awaiting the first on-device read-back** |
| thermal mitigation | implemented, **awaiting the first on-device read-back** |
| fast-charge current | 1 A measured (`FAST_CHARGE_CURRENT_CFG = 0x14`); 2 A implemented, **not yet confirmed on the device** |
| high-voltage (QC) negotiation | **not done and not planned here** — see [the ceiling](#why-2-a-and-not-27) |

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

☠️ Reading these is cheap and needs no kernel build. The regmap debugfs file is
fixed-width, 9 bytes per line, so it seeks:

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
| 20 | 16060 | 16169 | +0.32 °C |
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

## Why 2 A and not 2.7

Not caution. Two independent ceilings, and the lower one is not the battery.

**The compensation register runs out.** The JEITA soft-zone reduction is a
six-bit field of 25 mA steps — at most **1575 mA** of reduction from whatever
fast-charge current is programmed. This pack's characterised cool-zone current
is 600 mA:

| fast-charge current | lowest reachable soft-zone current | Fairphone wants |
|---|---|---|
| 2700 mA | 1125 mA | 600 mA — **not expressible** |
| 2000 mA | 425 mA | 600 mA — fine |

So at the pack's rated current the hardware **cannot implement Fairphone's own
profile**. Anything at or below 2175 mA can.

**The port runs out first anyway.** Without high-voltage negotiation — which
mainline `qcom_smbx` does not do — a DCP gives 1.5 A at 5 V, which is about
1.9 A into a 3.8 V cell at best. Above roughly 2 A the binding constraint stops
being the charger and becomes the USB port, which is the right place for it.

Downstream reaches 2.7 A by negotiating a higher `Vbus`. That is a separate
piece of work, is not started, and is not required for the phone to charge at
the rate its port can actually supply.

## The device-tree interface

Three optional properties on the charger node, all no-ops when absent so no
other board changes behaviour:

```dts
&pmi632_charger {
	monitored-battery = <&fp3_battery>;

	qcom,jeita-hard-thresholds = <0x5675 0x1987>;   /* cold 0 degC, hot 55 degC */
	qcom,jeita-soft-thresholds = <0x3ebc 0x2204>;   /* cool 20 degC, warm 45 degC */
	qcom,jeita-soft-fcc-microamp = <600000 1000000>;

	qcom,thermal-mitigation = <2000000 1500000 1000000 500000>;
};
```

Each threshold pair is `<cold hot>`, as raw ADC codes; a higher code is a colder
battery, so the driver rejects a pair whose hot value is not the smaller one.

`qcom,jeita-soft-fcc-microamp` is the current to be **left** in each soft zone,
not the register's own offset — so the device tree describes a charge current
and the driver works out the delta. It reads the fast-charge current back out of
the hardware to do that, rather than trusting the device tree to match.

The charge current itself comes from the battery node:

```dts
constant-charge-current-max-microamp = <2000000>;
```

which the driver now applies, bounded by a **per-generation ceiling** in the
driver (`smb_variant::fcc_max_ua`): 1 A on SMB2, 2 A on SMB5. That ceiling is
what preserves the original intent of the hardcoded ~1 A — a device tree can ask
for a current, but not for one the driver has not been taught is safe on that
PMIC generation. It also means the two SMB2 boards in mainline that already ask
for 1.8 A (`sdm845-oneplus-enchilada`, `-fajita`) keep charging at exactly 1 A,
unchanged.

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

At 2 A with this pack's thresholds the expected values are `0x1061 = 0x28`,
`0x1092 = 0x28` (a 1000 mA hot reduction), `0x1093 = 0x38` (1400 mA cold), soft
thresholds `22 04 3e bc` and hard `19 87 56 75`.

## Known gaps

* **No high-voltage negotiation**, so the input side caps the whole thing near
  1.9 A into the cell. This is the only remaining thing between the phone and
  its rated 2.7 A, and it is a piece of work in its own right.
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
* **The JEITA compensation is relative to the programmed current**, so it has to
  be computed after the fast-charge current is set — which is why both it and
  the cooling device are initialised below that point in probe, and why both
  read the register back rather than trusting the device tree.
* **`50-charger` is skipped without a cable**, and a skipped check is not a
  passing one. Check what the run actually reported.
