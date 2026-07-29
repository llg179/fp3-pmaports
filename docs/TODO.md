# Open items

Things that are known-broken, deliberately unfinished, or parked with enough
context to pick up later. Each entry says what was measured, not what was
guessed. Items that are already written up elsewhere are linked rather than
repeated.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who decided what belongs here and what is
> already settled. Each entry reports a measurement he made or reviewed.

## The notification LED blinks forever after a missed call

**Symptom:** after a missed call the LED keeps blinking; dismissing the
notification does not stop it.

It is **not** the camera flash — the phone exposes no flash or torch LED at all:

```
/sys/class/leds/ →  mmc0::   mmc1::   rgb:status
```

and the device tree contains no flash node (see the parked one below). What
blinks is `rgb:status`, the RGB status LED on the PMI632 LPG.

**Measured on the device:**

* `rgb:status` uses the `pattern` trigger with **`repeat = -1`** — repeat forever;
* feedbackd's `default.json` defines `phone-missed-call` as a `Led` feedback,
  `#00FFFF`, and `notification-missed-generic` as a blue one at frequency 500 —
  **neither carries a duration**, so the feedback runs until the client ends it;
* there is **no `fairphone,fp3.json` theme** installed (the FP5 has one, the FP3
  does not), so those generic rules are what apply.

**Immediate workaround:** `echo 0 | sudo tee /sys/class/leds/rgb:status/brightness`,
or restart feedbackd.

**Two things to do, in this order:**

1. Find out who fails to call `EndFeedback` when the notification is dismissed —
   phosh or the calls app. That is the actual bug; everything else limits the
   damage.
2. Ship a `fairphone,fp3.json` feedbackd theme that gives those LED feedbacks a
   bounded duration. It belongs next to the other userspace drop-ins this repo
   carries (`userspace-audio/udev`, `pulse`, `ucm2`).

## Parked: the PMI632 camera flash

A device-tree node for the flash exists but was never enabled, because the
probe path was not verified: `leds-qcom-flash.c` reads `FLASH_SUBTYPE_REG` and
has to recognise the subtype value it gets back. Until someone checks that on
hardware, enabling it risks a probe failure at boot.

The numbers below are the useful part — they come from Qualcomm's downstream
tree for this board and are not written down anywhere else:

```dts
/*
 * Camera flash: two flash channels ganged into a single white LED
 * (downstream gangs them with qcom,led-mask = <3> on the led-switch node).
 */
pmi632_flash: led-controller@d300 {
	compatible = "qcom,spmi-flash-led";
	reg = <0xd300>;
	status = "disabled";

	led-0 {
		function = LED_FUNCTION_FLASH;
		color = <LED_COLOR_ID_WHITE>;
		led-sources = <1>, <2>;
		led-max-microamp = <600000>;
		flash-max-microamp = <2000000>;
		flash-max-timeout-us = <1280000>;
	};
};
```

(`pmi632.dtsi` also needs `#include <dt-bindings/leds/common.h>`.)

Note that a torch device appearing under `/sys/class/leds` would also give
feedbackd something new to blink — see the item above before enabling it.

## Untested: interconnect path for the SCM/crypto node

An idea from the SLIMbus framer investigation that was never confirmed:
downstream's `pil-tz` votes MASTER_SPS→EBI bandwidth around the PAS SCM calls,
while mainline's `qcom_scm_bw_enable()` is a no-op here because the `scm` node
carries no interconnect path. Adding one would make `bw_enable()` vote during
`pas_init_image` / `mem_setup` / `auth_and_reset`:

```dts
&scm {
	interconnects = <&pcnoc MAS_CRYPTO RPM_ALWAYS_TAG
			 &bimc SLV_EBI RPM_ALWAYS_TAG>;
	interconnect-names = "crypto-ddr";
};
```

The audio path works without it, so this is not a blocker — it is kept in case
ADSP boot timing ever needs revisiting.

## Settled: the two QDSP6SS framer pokes were not needed

Removed on 2026-07-29. `integration/<base>` used to carry two commits clearing
QDSP6SS `0x0c20002c` bit 3 — one in `qcom_q6v5_pas.c` after `AUTH_AND_RESET`,
one in `qcom-ngd-ctrl.c` before the capability exchange. Both are reverted,
along with the `qcom,slim-framer-quirk-reg` device tree property that armed the
second one (76 lines gone).

What settled it, on the same phone with the same protocol, one variable:

| | audio opens | tone across SLIMbus both ways | `MC:0x21` | codec |
|---|---|---|---|---|
| without the pokes | 8/8 cold boots | 8/8 | 8 | 1 |
| with the pokes | 8/8 cold boots | 8/8 | **8** | 1 |

Not a trace of a difference. Three things worth keeping from getting there:

* **The PAS poke never wrote anything.** Its own log line reads
  `QDSP6SS 0xc20002c 0x101->0x101` — by the time it runs, bit 3 is already
  clear. Only the SLIMbus one wrote (`0x10b->0x103`).
* **`MC:0x21` is not a fault signal.** It is `SLIM_USR_MC_DEF_ACT_CHAN`,
  "define and activate channel", from `qcom_slim_ngd_enable_stream()`. It
  appears eight times per boot **with and without** the pokes while audio works
  — the count tracks how many streams are started, not how many failed. Same for
  `MC:0xd` (`ADDR_QUERY`, which is why `Failed to get logical address` is
  followed 200 ms later by the codec answering) and `capability exchange
  timed-out`.
* **A boot with nobody logged in measures nothing.** The first version of this
  test counted `MC:0x21` in the kernel log and found none in twenty-five boots,
  because without a user session nothing starts audio and the log ends at
  twenty seconds. The metric has to open the audio path.

Reverting the PAS commit does **not** change which ADSP firmware is loaded: the
descriptor it added differed from the msm8996 one only in the firmware name and
the quirk register, and the FP3 device tree sets `firmware-name` on `&lpass`,
which the driver prefers. The `required-opps` CX-turbo idea that used to share
this experiment was already disproven separately —
`qcom_pas_pds_enable()` votes `INT_MAX` on every proxy power domain, measured
live as `cx_perf = 2147483647` for roughly 160 ms across the ADSP boot window,
so it was a no-op.

## Also open, written up elsewhere

* **Charging is capped at 1 A** where Fairphone's own profile says 2.7 A. What
  it would take to lift it — battery temperature, JEITA, a thermal cooling
  device, and letting the DT drive the register — is in
  [`device_tree/README.md`](device_tree/README.md#what-it-would-take-to-charge-at-full-current).
* **Sensors work**, including proximity blanking during a call and ambient
  light. What is left there is calibration rather than bring-up: the
  magnetometer has an unknown hard-iron offset and scale, and the mount matrix
  is inherited from msm8996. See [`sensors/README.md`](sensors/README.md).
* **Camera streaming is not working end to end.** The sensor probes and its
  link into CAMSS enables; what remains is on the CAMSS side, not in the
  driver — see the `submit/<base>/camera` commit message.
