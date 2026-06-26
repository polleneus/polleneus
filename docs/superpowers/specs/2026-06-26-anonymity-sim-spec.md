# Feature Spec — Anonymity & Source-Localization (Simulator Slice 3)

**Status:** Draft → (fan-out review) → **CTO sign-off pending**.
**Date:** 2026-06-26
**Parent design:** [polleneus v0.4](2026-06-25-polleneus-design.md) · **Builds on:** [soup-sim slice 1](2026-06-25-soup-sim-spec.md), [airtime slice 2](2026-06-25-airtime-sim-spec.md)
**Roadmap:** measures the **existential security promise** — *in a pure-flooding mesh, can an adversary localize who ORIGINATED a message?* Delivery (slice 1) and airtime (slice 2) measured whether the network *works*; this measures whether it *protects*.

> **Purpose.** Crypto/sealed-sender hides message *content* and the addressing, but pure flooding leaks a **physical-layer** signal: a message radiates outward from its origin in space and time, and an adversary with receivers can run that movie backwards. This slice measures that leak against a realistic receiver-grid adversary, and whether the design's two cheapest defenses (Poisson mixing delay + receive-before-originate gate) actually blunt it — and at what delivery cost.

> **Honesty inversion (read this first).** Unlike slices 1–2 (every number an UPPER BOUND on *delivery*), here **every anonymity number is an UPPER BOUND on real anonymity**: we run a fixed set of adversary estimators, and a smarter real adversary can only localize *better*. So a reported "median localization error = 40 m" means *"the originator is at least this exposed — probably more."* We never claim "at most this exposed."

---

## 1. Threat model (CTO-chosen: static receiver grid)
- **Adversary = passive static receivers** placed to cover a fraction **f** of the arena (the sweep axis, analogous to density/contention in prior slices). Each receiver logs, per message it hears, the tuple `(message_id, first_hear_time, receiver_location)`. Receivers never transmit, relay, or originate; they are invisible to the protocol.
- **Coverage f** = fraction of arena area within radio range of ≥1 adversary receiver (placed on a jittered grid; f swept from sparse to near-total). Report the receiver count and the realized coverage, not just nominal f.
- The adversary knows the protocol, the map, and the (mobile) positions of all *candidate* real nodes at all times (worst-case auxiliary info — conservative). It does **not** see message content (crypto holds) or which node is the true originator (that's what it estimates).
- **Out of this slice (named follow-ups):** compromised/insider colluding app-nodes (a stronger adversary — separate slice); long-term **intersection/traffic-analysis** across *many* messages from the same author (we localize a *single* origination event, not deanonymize a persistent identity); decoy/cover traffic as a defense.

## 2. What is measured
For each originated message, the adversary produces a suspicion ranking over candidate nodes and a point estimate of the origin. We report, swept over coverage f and over each defense arm:
- **Localization error** — distance from the point estimate to the true originator's position at origination time. Report the distribution (median + tail), not just the mean.
- **K-anonymity / rank** — the true originator's rank in the adversary's suspicion ordering (rank 1 = fully deanonymized), and the **anonymity-set size** (number of candidates indistinguishable from the true source under the estimator). Report the rank-1 (exact-catch) probability.
- All metrics are reported **jointly with the delivery ratio and latency** of the same run (a defense that destroys delivery isn't a defense — it's an outage).

## 3. The adversary estimators (model a CAPABLE attacker)
Because anonymity numbers are an upper bound, we must run the **strongest estimators we can**, and report the best (most-localizing) one as the adversary:
- **First-spy estimator** — the earliest adversary receiver to hear the message is nearest the source; point estimate = the candidate node closest to that receiver at the first-hear time. The classic flooding deanonymizer.
- **Time-gradient / arrival-order estimator** — uses first-hear times across *all* hearing receivers: the source minimizes a cost over candidates that best explains the observed radial arrival-time ordering (earlier-hearing receivers should be closer). Stronger than first-spy when coverage is non-trivial.
- The reported adversary success = **best (smallest error / best rank) across estimators**, per message.

## 4. The estimator-power control + publish gate (the honesty guard)
The trap (mirror of slice-2's "is it really airtime?"): **claiming anonymity when the attack is merely weak.** Guard:
- **Random-guess baseline** — an estimator that picks a candidate uniformly at random. Its error/rank is the no-information floor.
- **Estimator-power gate:** an anonymity *defense* claim ("mixing/gate raises localization error to X") is creditable **only if**, on the **undefended baseline**, the real estimator **beats random-guess by a pre-registered margin** (it demonstrably localizes). If the estimator can't localize even the naked originator, the run is labelled *"estimator too weak — anonymity result inconclusive,"* not "anonymous."
- **Exposure claim (the headline):** "pure flooding exposes the originator" is creditable only if the best estimator's rank-1 probability (or median error) on the undefended baseline crosses a pre-registered exposure threshold at realistic f. State the prediction up front (e.g., *first-spy localizes within ~1 radio-range at f ≥ X*).

## 5. The defenses (knobs, each with an OFF control on the same axes)
- **Poisson mixing delay** — a node holds a received (forwardable) blob for an `Exp(λ)` random time before it becomes eligible to rebroadcast, deliberately scrambling the radial arrival-time gradient the estimators exploit. Sweep λ; **off-control = zero delay**. Measure the localization-error gain **and** the delivery-latency cost (reuse slice-2's censoring-aware T50).
- **Receive-before-originate gate** — a node may originate only after it has relayed ≥ G others' messages (or been receiving ≥ T). An origination is then hidden among relays: the adversary can't equate "a node's first emission of this id" with "origin," because honest relayers also "first-emit" ids they didn't author. **Off-control = G=0** (originate immediately). Measure the rank/anonymity-set gain **and** the origination-latency cost (how long a user waits before their message can leave).
- Both-on arm, to see whether they compose.

## 6. Direction of every bias (so the gate stays honest)
- Reported anonymity is an **upper bound** (stronger adversary ⇒ less). 
- The adversary gets worst-case auxiliary info (all candidate positions) ⇒ **conservative** (pessimistic for privacy — the safe direction).
- Unit-disk reception for adversary receivers ⇒ optimistic for the adversary's coverage (real RF is messier) — note direction.
- Single-message localization only (no cross-message intersection) ⇒ **optimistic for privacy** (a persistent author is more exposed than one message) — loudly flagged; it's the biggest deferred risk.

## 7. Architecture (reuse the trusted engine; additive)
- `adversary.py` (new): jittered-grid receiver placement + realized-coverage measurement; the reception log; the three estimators (first_spy, time_gradient, random_guess).
- `anonymity.py` (new): localization-error, rank / anonymity-set-size, exposure + estimator-power gate.
- `engine.py` (extend, behind defaults): **passive receive-only nodes** (adversary receivers hear in-range transmissions, log, never relay/originate); per-(node,message) **first-hear time** already exists via `acquired`; a per-node **mixing-delay** hold before a blob becomes forwardable; an **originate-gate** predicate. All default OFF ⇒ bit-identical to the merged engine (fidelity + percolation + airtime gates stay green).
- `scenario.py` (extend): `anonymity_sweep` over coverage f with defense on/off arms + the estimator-power control, returning per-f localization/rank/delivery/latency + the gate verdict.
- `run.py`: `--preset anonymity` (sweeps f; prints exposure headline + each defense's anonymity gain and its latency cost + the gate verdict).
- Reuse slice 1/2: RWP mobility + stationarity gate, RNG substream contract, sweep/CI/bootstrap, the censoring-aware latency, report/CSV/manifest.

## 8. Definition of Done
- Baseline exposure curve (best-estimator localization error + rank-1 prob vs coverage f) with the random-guess floor overlaid.
- Estimator-power gate wired: a defense claim is suppressed unless the estimator beats random on the undefended baseline by the pre-registered margin; the verdict is surfaced in CLI + plot.
- Mixing-delay and originate-gate arms each measured **with their delivery/latency cost**, plus the both-on arm.
- Every number labelled an UPPER BOUND on anonymity; bias table extended (adversary unit-disk; single-message; worst-case aux info) with directions.
- All deterministic by seed; one-command run; engine non-regression (slices 1–2 gates) bit-identical with defaults off.

## 9. Decisions to confirm at sign-off
- **Threat model = static receiver grid, coverage f the axis** — *CTO-chosen ✓.*
- **Scope = baseline + Poisson mixing + receive-before-originate (each with off-control); decoy traffic + insider adversary deferred** — *CTO-chosen ✓.*
- **Headline metric = localization error (m) AND rank/anonymity-set, reported jointly with delivery+latency** — *recommend yes.*
- **Adversary = best of {first-spy, time-gradient} per message; random-guess as the power control** — *recommend yes.*
- **Honesty inversion: anonymity numbers are an UPPER BOUND; estimator-power gate prevents "weak-attack = anonymous"** — *recommend yes (this is the slice's whole credibility).*
