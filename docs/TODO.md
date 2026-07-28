# Open items

Things that are known-broken, deliberately unfinished, or parked with enough
context to pick up later. Each entry says what was measured, not what was
guessed. Items that are already written up elsewhere are linked rather than
repeated.

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

## Unsettled: are the two QDSP6SS framer pokes needed at all?

`integration/<base>` carries two commits that clear QDSP6SS `0x0c20002c` bit 3 —
one in `qcom_q6v5_pas.c` after `AUTH_AND_RESET`, one in `qcom-ngd-ctrl.c` before
the capability exchange (described in
[`kernel/README.md`](kernel/README.md#the-qdsp6ss-slimbus-framer-pair)). As last
measured (2026-07-26) the SLIMbus chain came up **identically with and without
them** — one boot each way, which is not enough to conclude.

**The measurement runs on `wip/7.1.3/audio-debug`.** That branch is not an
offshoot of `wip/7.1.3/audio`: it forks `integration/7.1.3` and adds exactly
three commits, which is the whole experiment —

* a revert of the `qcom-ngd-ctrl.c` poke,
* a revert of the `qcom_q6v5_pas.c` poke,
* `vote TURBO CX for the ADSP` (`required-opps = <&rpmpd_opp_turbo>`).

A few cold boots on that branch settle it; if the chain still comes up, both
poke commits can be dropped from `wip/<base>/audio` and `integration/<base>`.

**The CX-corner hypothesis behind the third commit is already disproven.** Its
message argues that the ADSP firmware derives the Q6 core divider from the CX
performance state, and that mainline never requests one. It does:
`qcom_pas_pds_enable()` calls `dev_pm_genpd_set_performance_state(pds[i],
INT_MAX)` on every proxy power domain before powering it up
(`drivers/remoteproc/qcom_q6v5_pas.c`), which was confirmed live —
`cx_perf = 2147483647` for roughly 160 ms across the ADSP boot window. So
`required-opps` is a no-op here and that commit should not be carried forward;
only the two reverts are the experiment.

## Also open, written up elsewhere

* **Charging is capped at 1 A** where Fairphone's own profile says 2.7 A. What
  it would take to lift it — battery temperature, JEITA, a thermal cooling
  device, and letting the DT drive the register — is in
  [`device_tree/README.md`](device_tree/README.md#what-it-would-take-to-charge-at-full-current).
* **Sensors do not work.** The SSC path and what was measured on it are in
  [`sensors/README.md`](sensors/README.md).
* **Camera streaming is not working end to end.** The sensor probes and its
  link into CAMSS enables; what remains is on the CAMSS side, not in the
  driver — see the `submit/<base>/camera` commit message.
