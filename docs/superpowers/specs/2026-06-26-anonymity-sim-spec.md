# Feature Spec — Anonymity & Source-Localization (Simulator Slice 3) — v2

**Status:** Draft → fan-out review round 1 (folded, v2) → **CTO SIGN-OFF (2026-06-26)** — authorizes PR-1's plan first.
**Date:** 2026-06-26
**Parent design:** [polleneus v0.4](2026-06-25-polleneus-design.md) · **Builds on:** [soup-sim slice 1](2026-06-25-soup-sim-spec.md), [airtime slice 2](2026-06-25-airtime-sim-spec.md)
**Roadmap:** measures a **lower-bound proxy for the existential security promise** — *for a single origination event, against an external passive receiver grid, can the adversary localize who originated a message?*

> **What this is and is NOT.** This slice measures **one origination event** against an **external passive receiver-grid** adversary. It is a *lower-bound proxy* for real anonymity, **not** the whole promise: the parent design's own dominant threat is a **PHY-labeled persistent device under multi-session intersection** (device-linkage ≈ 1.0, §10), which this slice does **not** model. Single-event localization is therefore **optimistic for privacy** — the biggest deferred risk. Insider/compromised-node adversaries and decoy traffic are also deferred (named follow-ups). **Do not read any number here as "the system is anonymous."**

> **Honesty inversion (load-bearing).** Every anonymity number is an **UPPER BOUND on real anonymity**: we run a fixed estimator set and report the *best* (most-localizing) one; a smarter real adversary only localizes *better*. So "median localization error = 40 m" means *"at least this exposed — probably more."* We **never** claim "at most this exposed," and **never** present a number as a floor/guarantee. (Both prior slices bounded the optimistic side of *delivery*; this bounds the optimistic side of *anonymity*: real ≤ reported, always.)

> **Scope tag travels with every number (hard requirement).** Every emitted anonymity figure — CLI, CSV, manifest, any plot title — carries the scope clause inline, e.g. `loc_error_median_m=40 [SINGLE-EVENT, EXTERNAL-PASSIVE; intersection+insider NOT modeled; UPPER BOUND on anonymity]`. A DoD item forbids emitting an anonymity number without it. (Mirrors how slices 1–2 made "UPPER BOUND on delivery" + the publish-gate verdict travel with their numbers; the parent design names *false-confidence* the deadliest failure, §12.8.)

---

## 1. Threat model (CTO-chosen: static receiver grid)
- **Adversary = passive static receivers** covering a fraction **f** of the arena (the sweep axis). Each logs, per message it overhears, `(message_id, first_hear_time, receiver_location)`. Receivers never transmit/relay/originate and are **invisible to the protocol** (see §7 — they are a post-hoc overlay, so they cannot perturb contention/delivery).
- **Coverage f** = fraction of arena area within adversary-range of ≥1 receiver. Report **realized** coverage (disk-overlap aware), not just nominal f and receiver count.
- **Placement arms:** (a) **uniform jittered grid** (baseline) and (b) **chokepoint/clustered** placement biased toward node-density / mobility hotspots (a budget-matched *smart* adversary). Report the **stronger** as the adversary; uniform-only would over-state anonymity (a budget-matched adversary targets clusters) — flagged in the bias table.
- The adversary knows the protocol, the map, and all candidate nodes' trajectories (worst-case auxiliary info). It does **not** see content (crypto holds) or the true originator.
- **Out (named follow-ups):** insider/compromised colluding nodes; **cross-message intersection / persistent-author deanonymization** (the dominant real threat — see banner); decoy/cover traffic as a defense.

## 2. Candidate set, reference times, and metrics (all pinned — no implementer guessing)
- **Candidate set (pre-registered):** all real nodes **alive and within the message's space-time reachability cone** at origination (a node that could not possibly have authored it is excluded). The random-guess floor (§4) is uniform over *this* set. Bias direction noted (a smaller set ⇒ stronger random floor ⇒ optimistic for privacy).
- **Reference times (pinned):** the headline ground truth is the **originator's position at origination time** ("where the author was when they spoke"). Estimators evaluate candidate positions at the **per-receiver first-hear time**. Because the originator moves between origination and first-hear (especially under mixing), report **both** `error_origination_time` (headline) and `error_first_hear_time`; their gap is the *mobility-cloaking* component, kept separate from timing-scramble (so a defense can't bank the originator's own motion as its gain).
- **Metrics (per originated message, swept over f and arm):**
  - **localization error** = distance(point-estimate, ground truth); report **median + P90 + P95** (the tail — occasional exact catches — is what dooms a user).
  - **rank** of the true originator = count of candidates with strictly-better suspicion score (+ fractional mid-rank on ties).
  - **rank-1 (exact-catch) probability** — the **headline** scalar.
  - **estimator anonymity-set (upper bound)** = `|{candidates within ε of the best score}|`, ε pre-registered; **always labelled an upper bound** (a stronger adversary splits the set), **never** "K-anonymity / hiding crowd."
  - **undetected fraction** = messages heard by zero receivers (censoring-aware, see §4); reported **separately**, never folded into the error distribution.
- All reported **jointly with delivery ratio + censoring-aware T50** of the same run.

## 3. Adversary estimators (model a CAPABLE attacker; validated for power)
**IMPORTANT — the spread is EPIDEMIC, not radial.** This engine floods a blob to an entire connected component in one step; it then spreads further only as **mobile holders carry it into new components**. There is no `distance/c` radio wavefront — a receiver's first-hear time is *when a holder of the message first wanders into its range*. So source-localization here is **diffusion/epidemic source estimation** (infer where the spread *started*), not radio triangulation. Estimators must be defined against the recorded **hold log + trajectories**, not a propagation speed. Reported adversary success = **best across estimators per message**:
- **First-spy** — candidate nearest (in position-at-first-hear) the earliest-hearing receiver (a lower-power reference).
- **Reachability-likelihood (the strong estimator the upper-bound claim rests on)** — per candidate c with origination position p_c(t0): score how well "spread starting at p_c at t0" explains the observed `(receiver, first_hear_time)` vector, using the known trajectories + per-step reachability (forward-reachability from c: when would the flood, seeded at c, first bring a holder within range of each receiver?). Rank candidates by this likelihood/residual. Replaces the mis-specified "radial MLE."
- **Origin-vs-relay estimator (for the gate, PR-2 §5):** exploits the position oracle to down-weight candidates whose first-hold of the id was preceded by an in-range upstream holder (a true relayer) — so the originate-gate is tested against an adversary that actually tries to defeat it.
- **random-guess** — uniform over the candidate set; the no-signal floor.

> If even the reachability-likelihood estimator cannot localize a STATIC source under near-total coverage (the must-localize control, §4), that is itself a **publishable finding** ("source-localization is hard in epidemic flooding"), not a number to force. The capability gate enforces this honestly.

## 4. Two controls + the publish gates (the honesty guards)
The trap (mirror of slice-2): **claiming anonymity when the attack is merely weak.** Guards (both must be wired and surfaced like slice-2's `binding_gate`):
- **Control A — must-localize (capability):** on a **static source + near-total coverage (f→1)** the best estimator MUST drive error→~0 and rank-1→~1. If it can't nail a stationary source under full coverage, the estimator is too weak to measure anything ⇒ **no slice-3 number publishes** ("estimator inconclusive"). (The missing positive control; analog of proving the mechanism is real.)
- **Control B — no-signal:** random-guess is the floor every estimator must beat.
- **Exposure gate (headline claim "flooding exposes the originator"):** creditable only if, at realistic f, the best estimator's rank-1 probability / median error crosses a **pre-registered exposure threshold**. State the prediction up front.
- **Defense-power gate (the FLOOR — fixes the "beats-random-by-a-margin is too weak" hole):** a *defense* gain is creditable only if the **undefended baseline** already reached the exposure threshold (near-exact localization), so the defense's degradation is measured from a *strong* attack, not a mediocre one. "Beats random" alone is insufficient — reuse the exposure threshold as the precondition.
- **Defense-scope disclaimer:** every defense-gain number is emitted with "gain vs the single-event time-gradient adversary only; NOT evaluated against intersection/insider" — a defense that helps the narrow axis must not read as overall anonymity.

## 5. Defenses (PR-2; knobs, each with an OFF control + confound control)
- **Poisson mixing delay** — hold a forwardable blob `Exp(λ)` before rebroadcast; **λ fixed venue-wide** (a per-node/location rate is itself a fingerprint — parent §10). OFF = zero delay. **Confound control (mandatory):** mixing can "improve anonymity" merely by **dropping messages** (TTL expiry → fewer adversary samples), exactly as buffer/TTL masqueraded as airtime in slice-2. So measure a **timing-only arm at TTL=∞** (delivery held at 1.0): if the error gain survives ⇒ real timing-scramble; if it vanishes ⇒ it was message-dropping. The gate refuses to credit mixing if the gain disappears at TTL=∞. Also compute error on the **same detected-message set** across arms. Report delivery/T50/buffer-occupancy cost.
- **Receive-before-originate gate** — originate only after relaying ≥ G others' ids (or alive ≥ T). OFF = G=0. Scored by the **origin-vs-relay estimator** (§3) so "hidden among relays" is *measured*, not asserted. **Confound control:** a **relay-density** check — the gain is meaningless if few relays exist to hide among, so confirm the gain holds at realistic relay density (not a low-density artifact). Report origination-latency cost (how long a user waits before their message can leave). The gate/mixing are modeled as metadata-free idealizations ⇒ **optimistic for privacy** (real gate-eligibility timing leaks — flagged).
- **Both-on arm** to test composition (phrased as defense-specific, not "overall anonymity").

## 6. Bias table (every idealization, with direction)
| Mechanic | Direction |
|---|---|
| reported = best of a finite estimator set | **UPPER BOUND on anonymity** (smarter adversary localizes better) |
| single origination event, no cross-message intersection | **optimistic for privacy** — the dominant deferred risk |
| external passive only (no insider/compromised nodes) | **optimistic for privacy** (deferred) |
| uniform-grid placement (if chokepoint arm not run) | **optimistic for privacy** (budget-matched adversary targets clusters) |
| originate-gate scored without origin-vs-relay estimator | optimistic for the gate arm (omniscient adversary separates origin/relay) — mitigated by §3 estimator |
| mixing/gate modeled metadata-free (no eligibility-timing / rate fingerprint) | **optimistic for privacy** |
| adversary unit-disk reception | optimistic for the adversary's coverage (real RF messier) |
| worst-case auxiliary info (all trajectories) | **conservative** for exposure (safe direction) |

## 7. Architecture — POST-HOC OVERLAY (not real adversary nodes), additive
The adversary is computed **after** the real simulation, so it cannot change `n`, contention, goodput, delivery, or airtime (real engine-nodes would — they'd raise `n_contenders` and suppress goodput, perturbing the delivery measured jointly; and `acquired` is a *billed-transfer hold time*, not physical overhearing).
- `engine.py` (extend, default-OFF flag): a **hold/transmit event recorder** — per (node, blob): the interval the node *holds* the (unexpired) blob (it is treated as periodically advertising it while held). Default OFF ⇒ recorder list stays empty ⇒ **bit-identical** to the merged engine (slices 1–2 gates green).
- `adversary.py` (new): receiver placement (uniform + chokepoint) + realized-coverage; **overhearing** = for each (receiver L, message m), `first_hear = min t over holders k of m of {k holds m ∧ k within adversary-range of L at t}` — computed from the recorded hold log + trajectories (reproduced from the mobility substream). The estimators (first_spy, time_gradient/MLE, origin_vs_relay, random_guess).
- `anonymity.py` (new): candidate-cone, localization error (both reference times), rank / anonymity-set-upper-bound / rank-1 prob, undetected fraction; Controls A/B + exposure + defense-power gates (returns a labelled verdict like `binding_gate`).
- `scenario.py` (extend): `anonymity_sweep` over coverage f (+ placement arms), returning per-f metrics + delivery/T50 + gate verdicts. **PR-2** adds the defense arms + confound controls.
- **Defenses (PR-2, engine, default-OFF, guarded):** mixing delay in `_offerable` (`forwardable_at = acquired + delay ≤ exit_`; conjunct with the existing causality guard; delay drawn from a **dedicated RNG substream, only when λ>0** so OFF draws nothing; held blobs excluded from `offered`); originate-gate in `inject`. New config fields default to no-ops.
- **RNG substream tags (disjoint):** placement=4, mixing=5, estimator=6 (existing: mobility=0, engine=1, cohort=2, buffers=(3,i)). Extend the disjointness test to cover the new tags (slice-1 alias precedent).
- Reuse slice 1/2: RWP + stationarity gate, sweep/CI/bootstrap, censoring-aware T50, report/CSV/manifest. **Stats:** per-message distributions estimated *within* a run; **CI over SEEDs** (not messages — within-run messages correlate); a **pre-registered minimum messages/run** so the rare rank-1 rate is stable.

## 8. Two sequenced PRs (mirrors airtime's fidelity→measurement split)
A defense changes delivery/latency **and** the estimator's input wavefront at once; shipped together you can't tell "defense works" from "estimator/overlay bug." So:
- **PR-1 — Adversary/estimator infrastructure + baseline exposure (no defenses).** Hold-event recorder; `adversary.py`; `anonymity.py`; Controls A/B + exposure gate; the baseline exposure curve (best-estimator error/rank-1 vs f, random floor overlaid). DoD: Control A passes (estimator demonstrably localizes a static source at f→1); exposure gate wired; engine non-regression bit-identical. **This proves the attack works before any defense can be credited.**
- **PR-2 — Defenses + cost.** Mixing (with the TTL=∞ confound control), originate-gate (with origin-vs-relay estimator + relay-density control), both-on; per-arm delivery/T50/buffer cost; CLI preset. Defense-power gate + defense-scope disclaimers.

**Sign-off authorizes PR-1's plan first.**

## 9. Definition of Done
- PR-1: baseline exposure curve with random floor; Control A (must-localize) + exposure gate green and surfaced in CLI/plot; every emitted number carries the scope tag (asserted by a test); engine non-regression (slices 1–2) bit-identical with defaults off; deterministic by seed; one-command run.
- PR-2: mixing + originate-gate arms each measured with delivery/latency/buffer cost; the TTL=∞ timing-only and relay-density confound controls wired into the defense-power gate; both-on arm; defense-scope disclaimer on every gain; bias table filled.
- All anonymity numbers labelled UPPER BOUND on anonymity; no artifact emits one without the scope tag.

## 10. Decisions confirmed / to confirm at sign-off
- **Threat = static receiver grid, coverage f the axis** — *CTO ✓.* (v2 adds a chokepoint placement arm so uniform doesn't flatter.)
- **Scope = baseline + mixing + originate-gate (off-controls); decoy + insider + intersection deferred** — *CTO ✓.* (v2 sequences it as PR-1 infra/exposure → PR-2 defenses.)
- **Architecture = post-hoc overlay, not real adversary nodes** — *recommend yes (only design that is invisible-to-protocol + non-perturbing + bit-identical).* 
- **Headline = rank-1 probability + localization error (median/P90/P95), reported jointly with delivery+T50; anonymity-set always labelled an upper bound** — *recommend yes.*
- **Two controls (must-localize + no-signal) + defense-power FLOOR; scope tag travels with every number** — *recommend yes (the slice's whole credibility).*
