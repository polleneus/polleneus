# Background (screen-off) BLE discovery — measured constraints + the scan duty cycler

**Status:** spike-VALIDATED on hardware (2 devices, 2 runs) · pre-B1 · numbers are small-N lab
results, not field data · **Date:** 2026-07-01

polleneus's mission test ("two phones with no internet exchange a message") passed on hardware, but
surfaced the real-world blocker for a *pocketed* mesh: with both screens off, **fresh peer discovery
did not converge in 30 seconds** under the original design (one continuous filtered
`SCAN_MODE_LOW_LATENCY` scan, started once and never restarted). This document records what a
source-cited research pass plus on-device measurement established about Android's actual screen-off
BLE behavior, and the duty-cycle design that fixed the failure. It is written to be load-bearing for
the client build and reviewable at B1.

## 1. Verified platform facts (adversarially checked against AOSP source + primary reports)

| # | Fact | Basis |
|---|---|---|
| F1 | A scan **with a non-empty ScanFilter keeps running screen-off** (Android 8.1→16); unfiltered scans are stopped outright. From 14 QPR2 the filter must have ≥1 non-empty field. | AOSP `ScanManager` across tags; confirmed by measurement (below) |
| F2 | On 13+, screen-off remaps filtered scans: LOW_POWER → hidden `SCAN_MODE_SCREEN_OFF` (512 ms window / 10 240 ms interval, 5 % duty); BALANCED → 183/730; **foreground-service LOW_LATENCY keeps 100/100**. On 8.1–12 there is no screen-off remap for filtered scans. | AOSP `ScanManager`; measured |
| F3 | **Continuous-scan timeout:** after a default 10 min (14+; 30 min ≤13; the filtered-scan exemption was removed in 13 QPR1) any scan session is **silently, stickily force-downgraded** to LOW_POWER — no callback; persists until a stop+restart with zero ongoing scans. Values are OEM-overridable. | AOSP (`android-13.0.0_r16 ScanManager`); **measured at ~5.1 min on a Samsung Android-16 device** — tighter than AOSP's default |
| F4 | **Scan-start quota:** sessions are recorded at scan STOP; a start is refused when the 5 most recent recorded sessions began within 30 s → safe budget ≤4 completed stop/start cycles per rolling 30 s. **Denial is silent**: the framework wrapper deliberately suppresses `onScanFailed(SCANNING_TOO_FREQUENTLY)` (verbatim in source, 9→16). | AOSP `AppScanStats` + `BluetoothLeScanner` |
| F5 | **Advertising is never throttled** — no screen/Doze/duty/restart limits in the AOSP advertising path (verified 11/13/16). LOW_LATENCY = 100 ms interval (framework minimum). RPA rotation (7–15 min) briefly (<1 s) disables connectable sets and gives neighbours a fresh MAC per rotation. | AOSP `AdvertiseManager`, `le_advertising_manager.cc` |
| F6 | `Handler.postDelayed` runs on uptime, which **freezes when the CPU suspends; a foreground service alone does not hold the CPU**. AOSP honors a PARTIAL_WAKE_LOCK from an FGS-hosting UID even in deep Doze (11–16); at least one vendor generation reportedly does not. Inexact `setAndAllowWhileIdle` ≈ one dispatch per ~9 min. | AOSP `PowerManagerService`, `AlarmManagerService`; **CPU napping measured on a charging Android-13 device** (timer drift ≤4.5 s during radio-quiet screen-off periods) |
| F7 | Hardware-offload paths are not core-path material: FIRST_MATCH **measured flaky** (zero results across an entire 40 s screen-on phase on Android 16; ~10 s MATCH_LOST); batch flushes are Doze-deferred; PendingIntent scans gain no throttle/screen-off privilege. | measured + AOSP + field reports |
| F8 | Prior art ships windowed background scanning, never continuous pocketed LOW_LATENCY (examples: 2 s/28 s LOW_POWER; 10 s windows with a ≥6 s minimum cycle; a screen-state receiver + filtered restart as the known Samsung fix). | public source of shipping BLE mesh/beacon apps |

Widely-reported OEM screen-off scan stoppages (zero results to an FGS callback scan) are so far
documented **on One UI 6 / Android 14 hardware only**; they did **not** reproduce on this project's
Android 11/13/16 lab devices — but they set the expectation that per-device measurement stays part
of bring-up forever.

## 2. Measured ground truth (lab, 2026-07-01)

Probe app: one filtered scan, one LOW_LATENCY/100 ms advertiser (separate device), timestamped
callback logging; fresh-discovery latency measured by restarting the advertiser (fresh RPA = a
genuinely new device to the scanner). Devices: Samsung Android 16 (SM-X210-class) and Android 13
(SM-G998B-class) scanners; Android 11 advertiser.

- Screen-off filtered scans **deliver** on all modes tested, both scanners (short sessions).
- Fresh-discovery latency, scanner screen-off: **LOW_LATENCY ≈ instant (≤1 s), BALANCED ≲1 s,
  LOW_POWER ≈ 4–6 s**; in the post-timeout downgraded state ~0.6–2 s observed (one rep per device,
  cross-device clocks uncorrected ±~1.5 s; theory bound ≤10.24 s for a 100 ms advertiser).
- **The F3 silent downgrade was reproduced and timed: rate collapse at ~5.1 min into the session**
  (Android 16 device; ~15–30/10 s → ~2–3/10 s with gaps mostly 6–9.5 s, tailing to ~12.5–15.5 s —
  consistent with the 512/10240 signature, attributed by rate/gap timing; the per-minute dumpsys
  cross-check silently failed). Single 14-min run per device; the Android 13 device showed **no
  downgrade in 14 min** while watching the same advertiser.
- Caveat: probe scanners were charging; unplugged deep-Doze behavior is an owed measurement.

## 3. The duty cycler (as built into the spike mesh node)

One controller owns all scan starts/stops (self-heal and lifecycle paths included):

1. **Screen on / pairing active** → continuous filtered LOW_LATENCY scan + a **preventive
   break-before-make restart every 4 min** (beats the tightest measured timeout, F3; costs 1 budget
   cycle per 4 min). Scheduling is session-age-aware: a policy re-apply (screen flick, pair toggle)
   restarts an overdue session instead of silently extending it past the cadence.
2. **Screen off** → **10 s LOW_LATENCY windows every 50–60 s (jittered)**; the first window opens
   immediately on screen-off; windows never live long enough to hit any timeout; LL inside the
   window because an FGS keeps 100 % duty screen-off (F2) — requesting LOW_POWER would remap to 5 %.
3. **Advertising + GATT server are never duty-cycled** (F5): a node mid-gap stays discoverable and
   connectable — whoever is in a window connects; sync does not need symmetric scanning.
4. **Budget:** ≤4 completed stop/start cycles per rolling 30 s, one slot reserved for self-heal;
   over-budget starts are deferred, never skipped; recovery is never gated on a scan-failure
   callback (F4: denial is silent).
5. **Deaf-node watchdog:** 4 consecutive zero-result windows while neighbours are known present →
   BLE soft-restart → degraded-mode log. This is the only usable tell for the silent quota and any
   vendor penalty.
6. **Wakelock:** PARTIAL_WAKE_LOCK held only during screen-off windows (timeout-capped), because of
   F6; plus one reused inexact while-idle alarm (~9 min) as a dead-man that re-kicks a frozen
   scheduler. Under true deep Doze the node degrades to ~9-min windows while remaining reachable via
   advertising.
7. **Churn hygiene:** failed connects to a peer not *seen* in 20 s do not count toward the self-heal
   threshold (a departed peer is not a sick radio — measured: a stopped peer's stale RPA otherwise
   burned two spurious soft-restarts in 75 s, each hiding the GATT server ~4 s); the peer table is
   pruned (RPA rotation adds an entry per neighbour per 7–15 min).

## 4. Validation (mesh level, the previously-failing test) — TRANSPORT semantics
*(corrected 2026-07-02; the first published wording said "message crosses", which overclaimed — see
the correction note below)*

Both devices verified dozing (`mWakefulness=Dozing`) before app launch; apps launched fresh with
screens already off; test blob injected on the source. Measured outcome = **full 2048-byte blob
DELIVERED to the receiver over BLE** (dark discovery → connect → offer/request → chunked transfer).

| test (transport) | before | after (3 runs) |
|---|---|---|
| both-dark fresh launch → full blob delivered | discovery never converged in 30 s | **≤10 s, ≤10 s, ≤5 s** |
| steady-state mid-gap redelivery (receiver relaunched empty) | — | **≤45 s, ≤55 s, ≤5 s** (window-phase dependent; bound: 60 s period) |
| screen-on recovery → continuous scan | — | pass (all runs) |
| 3-node all-dark (1 run) | — | **≤5 s and ≤10 s** to the two receivers |

**Correction note (what those runs did NOT prove — since RESOLVED).** The test harness used a legacy
raw-inject path that forges the content address (id ≠ SHA-256 of the blob), so after the transfer
every receiver **correctly rejected the blob at content-address validation** — the
validate-before-store/relay discipline working exactly as designed. Those runs therefore validated
the duty cycler's job — screen-off discovery and transport — but not valid-blob store-and-relay. The
same forged-id pitfall silently turned a first battery-soak start into a re-push loop (a rejected
blob is re-pushed every few seconds; there is no reject-memory) — caught within minutes, soak
restarted clean; noted here so no future test repeats it.

**Valid-blob all-dark run (2026-07-02, 1 run) — the owed measurement, now done.** Two devices paired
(post-quantum leg confirmed; the short-authentication-string compared across both devices' logs — the
lab equivalent of the product's human screen-compare), then all three devices verified dozing and
freshly launched dark; a real sealed message (X-Wing + key-committing AEAD, 1288 B, content-addressed,
sender-authenticated) injected on the source: the **non-recipient third node STORED and RELAYED it
blind in ≤5 s** ("carried, can't read"), and the **recipient decrypted it with the sender VERIFIED in
≤10 s**. Store-and-relay of a valid blob under the duty cycler: measured. Still owed: a **forced
multi-hop topology** (a receiver physically out of the source's radio range), and everything in §5.

The change also went through a multi-lens adversarial review (concurrency, state-machine, Android API,
security surface, honesty audit of every number against the raw logs): 24 confirmed findings, all
fixed before merge — including the session-age-aware preventive scheduling, the adapter-off retry
path, teardown races, and the §5 side-channel disclosure below. This correction note is itself the
same discipline applied one layer up: the flawed claim was caught by re-reading raw receiver logs
hours after publication and retracted the same night.

## 5. Honest limits (nothing below is claimed)

- **The duty cycle is itself an RF side channel (new, disclosed).** Android LE scanning is *active*
  (SCAN_REQ PDUs are transmitted during a window), so the continuous-vs-windowed cadence reveals the
  node's screen state to a passive BLE sniffer, and the 10 s/50–60 s signature can distinguish
  pocketed nodes running this design. Running the app is already a disclosed membership signal, and
  the advert is continuous either way — but this is a new, distinguishable pattern the previous
  always-on scan did not emit, and correlating a screen-on transition with a newly flooded message
  id gives an observer a (bounded) authorship hint. Mitigation (screen-decoupled cadence at a
  latency/battery cost, passive scanning) is future work; until then this belongs in the honest
  user-facing posture (B3).
- **No battery numbers.** The 10/50 window duty and LOW_LATENCY advertising cost is unmeasured
  (owed: overnight soak, LL-vs-BALANCED advertising A/B).
- **Unplugged deep-Doze fidelity unmeasured** (probes ran on chargers; the wakelock honor question
  on the oldest vendor generation is open).
- The **~30-min vendor scan penalty** observed once in earlier field testing remains unreproduced
  and unexplained; empirical characterization is deferred (it disables a device's scans for ~30 min
  per trial).
- Numbers are **2-device, in-room, small-N lab results** — upper bounds on real-world performance,
  not field data. Multi-node (3+) dark convergence is unmeasured.
- All of this is **pre-B1**: nothing ships before the independent security audit (release-blockers
  B1); the duty cycler adds no crypto surface but its exported-activity test scaffolding remains on
  the existing pre-ship strip list.
