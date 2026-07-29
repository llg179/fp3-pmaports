# The QDSP6SS framer poke: what it was, and why it is gone

For most of this port's life the kernel wrote to a QDSP6SS register on every
boot, in two places, to make the WCD9335 audio codec answer at all. That code
was removed on 2026-07-29 after it was measured to do nothing. This page is the
record: what the poke was, why it looked necessary, and what settled it.

> **AI-generated.** Written by Claude (Opus 5) under the direction of
> Lajosházi, László Gergely, who ran the phone and made the physical
> measurements. The commits it describes are linked.

## Why it existed

The Fairphone 3's codec sits on SLIMbus, and the bus master — the *framer* —
lives in the ADSP. Before any audio can flow the AP and the ADSP have to
complete a **master-capability exchange**, after which the codec is assigned a
logical address. Early in the port that exchange did not complete: the log
showed

```
qcom,slim-ngd-ctrl: capability exchange timed-out
wcd9335-slim: Failed to get logical address
```

and audio stayed silent.

The lead came from a [2025 LKML thread](https://lkml.iu.edu/hypermail/linux/kernel/2502.1/00985.html)
about QDSP6SS register `0x0c20002c`, whose **bit 3** gates the ADSP-side framer.
Downstream's PIL boot path clears that bit; the mainline PAS path does not. That
matched the symptom exactly, so two commits were written:

| commit | what it did |
|---|---|
| [`6cd150e`](https://github.com/llg179/linux/commit/6cd150e75fb7f8d93cbc0f1fe6ca9cc23c33171e) | a msm8953 ADSP descriptor in `qcom_q6v5_pas.c` carrying `slim_framer_quirk_reg = 0x0c20002c`; after `AUTH_AND_RESET` it `ioremap`s the register and clears bit 3 |
| [`36c9399`](https://github.com/llg179/linux/commit/36c939972197288de5b5e690fd8740d8a8b9eb90) / [`dab21aa`](https://github.com/llg179/linux/commit/dab21aa7077d8493f4d658f4f1bfdf54e849e7f5) | the same clear again in `qcom-ngd-ctrl.c`, immediately before triggering the capability exchange, on the theory that the ADSP re-sets the bit during its own init |

plus a device tree property that armed the second one:

```dts
&slim_msm {
	/* FP3 quirk: QDSP6SS reg whose bit3 blocks the ADSP framer
	 * master-capability if left set by the mainline PAS boot. */
	qcom,slim-framer-quirk-reg = <0x0c20002c>;
};
```

Audio worked after that, and the pokes were kept — which is the trap. They were
kept because they were present when it started working, not because either was
ever shown to be the reason.

## What settled it

The question was reopened by **@cristian_c:matrix.org**, and their asking is
what turned a lingering "probably still needed" into a measurement. The answer
took four independent pieces of evidence, on the same phone, with the pokes as
the only variable.

**The PAS poke never wrote anything.** Its own log line gives it away:

```
qcom_q6v5_pas: slim-framer quirk: QDSP6SS 0xc20002c 0x101->0x101
qcom,slim-ngd-ctrl: slim-framer quirk: 0x10b->0x103
```

By the time it runs, bit 3 is already clear — the value goes in and comes out
unchanged. Only the SLIMbus one ever wrote. So half of the fix had been a no-op
from the start, on every boot, for months.

**The codec comes up without either.** Ten warm reboots and five cold boots on
a poke-free kernel: every one reached `WCD9335 CODEC version is v2.0` and
registered the card.

**Sound crosses the bus in both directions.** A 1 kHz tone played on the
headphones — which go out over SLIMbus through the WCD9335 — was heard by ear
and captured on the headset microphone, which comes back over SLIMbus, at
999.76 Hz and 33 dB. This is what [`23-audio-slimbus`](../../../tests/checks/23-audio-slimbus-test.sh)
now checks on every run; the older acoustic checks play through the speaker,
which hangs off QUIN_MI2S and the AW8898 amplifier and never touches SLIMbus.

**A/B, eight cold boots each way, one variable:**

| | audio opens | tone across SLIMbus | `MC:0x21` | codec |
|---|---|---|---|---|
| without the pokes | 8/8 | 8/8 | 8 | 1 |
| with the pokes | 8/8 | 8/8 | **8** | 1 |

Not a trace of a difference, in the working state or in the log.

## The log lines that misled us

Three messages around this exchange read like faults and are not:

| line | what it is |
|---|---|
| `capability exchange timed-out` | appears in **every** boot, including working ones, with and without the pokes |
| `TX timed out:MC:0xd` | `SLIM_USR_MC_ADDR_QUERY` — the address query. This is why `Failed to get logical address` is followed 200 ms later by the codec answering anyway |
| `TX timed out:MC:0x21` | `SLIM_USR_MC_DEF_ACT_CHAN`, "define and activate channel", from `qcom_slim_ngd_enable_stream()`. It appears eight times per boot **while audio works**; the count tracks how many streams are started, not how many failed |

A timeout here is survivable when the retry succeeds. The failure to look for is
audio that does not open — not a line in the log.

## What was removed

A single revert commit, 76 lines gone: both driver changes and the device tree
property. On `wip/7.1.3/audio` as `c71d7df` and on `integration/7.1.3` as
`3b3043f`.

Reverting the PAS commit does **not** change which ADSP firmware is loaded. The
descriptor it added differed from the msm8996 one only in the firmware name and
the quirk register, and the FP3 device tree sets `firmware-name` on `&lpass`,
which `qcom_pas_probe()` prefers over the descriptor.

The upstream-bound series `submit/7.1.3/audio` was regenerated without the two
commits, so the quirk is not proposed to the LKML. The previous tip is preserved
as the tag `submit-7.1.3-audio-with-poke-2026-07-29`.

## What it cost to find out

Two measurement mistakes are worth recording, because both produced believable
numbers that answered the wrong question:

* **A boot with nobody logged in exercises no audio.** The first version of the
  test counted `MC:0x21` in the kernel log and found none in twenty-five boots.
  Without a user session nothing starts audio and the kernel log ends at twenty
  seconds — the test was measuring a bus that was never used.
* **Waiting for `uptime < 100` does not mean "it rebooted".** The old boot's
  uptime satisfies it too, so the loop measured the same boot twice, in pairs,
  and the identical log line counts were the only tell. `boot_id` changes
  exactly once per boot and is the right signal.
