# Feature Spec — Multi-Session Intersection Attack on Sender Anonymity (Slice 3, PR-3)

**Status:** Draft → CTO design-direction approved (score-fusion, both fusion rules) → **CTO SIGN-OFF (2026-06-26)** — authorizes the PR-3 implementation plan.
**Date:** 2026-06-26
**Parent design:** [polleneus v0.5](2026-06-25-polleneus-design.md) · **Builds on:** [anonymity sim slice 3, PR-1/PR-2](2026-06-26-anonymity-sim-spec.md)
**Roadmap:** measures **the dominant deferred threat** the prior slice named but did not model — *if the same device originates K messages and the adversary can link them, how fast does sender anonymity collapse, and at what K is the originator effectively pinned?* This is the honest number release-blocker #1 needs before any "anonymous" claim.

> **What this is and is NOT.** This slice measures **cross-message (multi-session) intersection** against the same **external passive receiver-grid** adversary as PR-1. It does **one** new thing: it lets a tracked device originate **K** messages and fuses the adversary's per-message rankings, assuming the K messages are **linkable to one device**. It does **NOT** model *how* linkage is obtained — PHY-layer device fingerprinting is a separate slice. Linkage is **assumed given** (the worst case, per parent §10 "assume a handset is uniquely labeled"). Insider/compromised nodes and defenses-against-intersection (PR-4) remain deferred. **Do not read any number here as "the system is anonymous."**

> **Honesty inversion (load-bearing, inherited).** Every number is an **UPPER BOUND on real anonymity**: we fuse the *best* per-message estimator across K linked messages and report the most-localizing result; a smarter real adversary (better estimator, better fusion, partial linkage exploited probabilistically) only does *better*. We never present a number as a floor or guarantee. Intersection can only *sharpen* localization vs the per-message PR-1 number — so PR-3's rank-1 is an upper bound that is **never below** PR-1's.

> **Scope tag travels with every number (hard requirement).** Every emitted figure — CLI, CSV, manifest, any plot — carries the clause inline, e.g. `fused_rank1=0.62 @K=8 [INTERSECTION over K linked originations; device-linkage ASSUMED given (PHY out of scope); single external-passive adversary; UPPER BOUND on anonymity]`. A DoD item forbids emitting an intersection number without it.

---

## 1. Threat model (extends PR-1)
- **Adversary = the same passive static receiver grid** as PR-1 (covers a fraction f of the arena; logs `(message_id, first_hear_time, receiver_location)` per overheard message; invisible to the protocol, post-hoc overlay — cannot perturb delivery/contention). PR-3 adds **one capability**: the adversary knows that a designated set of K message_ids were all originated by **one device** (linkage assumed), and fuses its per-message candidate rankings for that device.
- **Tracked device:** a node that originates **K** messages spread over the session window. The adversary's goal is to pin the tracked device's **identity** (node index) — stable across all K messages — from the fused ranking.
- **Coverage f:** held **fixed** at a realistic value for the headline (the sweep axis here is **K**, not f); a small f-robustness check is a secondary arm, not the headline.
- **Linkage is ASSUMED given**, not derived. This is the worst case and the explicit scope boundary; PHY-fingerprinting that *establishes* linkage is a named follow-up slice.
- **Out (named follow-ups):** PHY device-linkability (how linkage is actually obtained); insider/compromised colluding nodes; **defenses replayed against the intersection adversary (PR-4)**; partial/probabilistic linkage (we assume perfect linkage of the K ids).

## 2. Candidate set, fusion target, and metrics (all pinned)
- **Candidate set (pre-registered):** the union, over the K tracked messages, of nodes alive within each message's space-time reachability cone — i.e. any node that could have authored *at least one* of the K. Random-guess floor is uniform over this set. (A node that could not author any of the K is excluded.)
- **Fusion target:** the tracked device's **node index**, which is constant across all K messages. The per-message estimator scores candidates at each message's first-hear geometry; fusion combines the K score vectors into one ranking over node index (well-defined: the node set is stable).
- **Metrics (per tracked device, swept over K, averaged over seeds):**
  - **fused rank-1 (exact-catch) probability** — the **headline** scalar: P(the tracked device is the single top-ranked candidate after fusing K messages).
  - **fused rank** of the tracked device (count of candidates with strictly-better fused suspicion + fractional mid-rank on ties).
  - **fused anonymity-set (upper bound)** = `|{candidates within ε of the best fused score}|`, ε pre-registered, **always labelled an upper bound**.
  - **K-to-pin** = the smallest K at which fused rank-1 crosses the exposure threshold (§4); reported with its CI, or "not pinned within K_max."
  - **undetected fraction** = tracked messages heard by zero receivers (censoring-aware; a device whose messages are never overheard cannot be fused — reported separately, never folded into rank).
- Reported **jointly** with delivery ratio + censoring-aware T50 of the same run, and with the **PR-1 single-event rank-1** (K=1) as the baseline the curve must start from.

## 3. The fusion rules (the new estimator math)
Per tracked message m, the existing best-estimator (PR-1: first-spy ∨ reachability-likelihood, lower score = more suspicious) yields a per-candidate score vector `s_m[c]`. Fusion combines `{s_1, …, s_K}` into one vector `S[c]`; `rank_of(S, tracked_device)` is the result.

- **Primary — rank-sum (Borda).** For each message convert `s_m` to per-candidate ranks `r_m[c]` (0 = best, ties = mid-rank); `S_borda[c] = Σ_m r_m[c]`; lowest total wins. **Scale-free** (no cross-message normalization assumption), robust to a single message's magnitude outliers, and the most conservative fusion (it cannot be dominated by one over-confident message). This is the credited headline.
- **Sensitivity — normalized score-sum (≈ Bayesian intersection).** Normalize each message's scores to a comparable scale (subtract per-message min, divide by per-message std or the reach-cap), then `S_sum[c] = Σ_m ŝ_m[c]`; lowest wins. This approximates summing negative-log-likelihoods (product of likelihoods) — the theoretically right fusion if scores are comparable evidence.
- **Reporting rule:** report **both** fused rank-1 curves. **Agreement** (within CI) ⇒ the result is robust to fusion choice. **Divergence** ⇒ flagged in the output, and the **lower** (more anonymity-favorable) number is reported as the credited headline (honest direction — never credit the adversary the benefit of the doubt on a methodological choice).

> If even fusion across K_max linked messages under realistic coverage cannot drive fused rank-1 above the per-message baseline, that is itself a **publishable finding** ("intersection does not sharpen localization in epidemic flooding") — not a number to force.

## 4. Controls + publish gates (the honesty guards)
The trap: **fusion that pins the wrong thing, or that climbs by artifact.** Guards (all wired and surfaced):

- **Control A — random-guess floor (no-signal).** Fuse K random-guess score vectors the same way; fused random rank-1 must stay ~1/|candidate set| as K grows. Proves the climb is *signal*, not a property of fusing K vectors. The credited intersection gain is the climb **above** this fused-random floor.
- **Control B — decoy-centrality confound (make-or-break).** Fusion could pin whoever is most **topologically central** in the diffusion, independent of who originated. Decoy is pinned concretely (no betweenness computation needed): the **non-origin node with the highest distinct-foreign-relay count** (`relayed`, already tracked by the engine) among the candidate set — i.e. the most-central innocent relay. Run the identical K-message fusion targeting the decoy. If the decoy's fused rank-1 also climbs to "pinned," the result is **confounded by centrality and is discounted, not credited** — the gate credits an intersection gain only when the *originator's* fused rank-1 exceeds the decoy's by a pre-registered margin (`DECOY_MARGIN`).
- **Control C — must-localize (capability, inherited from PR-1).** The per-message estimator must already be demonstrably capable (PR-1 Control A) on the same venue; no intersection number publishes if the underlying estimator is inconclusive.
- **Intersection-exposure gate (headline claim "intersection deanonymizes the persistent sender").** Creditable only if fused rank-1 crosses the **pre-registered exposure threshold** (reuse PR-1's `exposure_gate`: rank-1 ≥ max(0.5, 5×floor) with adequate sample size) AND the decoy control (B) is satisfied (originator pinned, decoy not). State the prediction up front: *we expect fused rank-1 to rise monotonically with K and to cross the threshold by some K ≤ K_max under realistic f.*

## 5. Architecture — additive, reuses the PR-1/PR-2 overlay
No engine change is required (the hold-event recorder + receiver overlay already exist). All new code is additive and default-inert (the existing single-event sweeps are untouched).
- `adversary.py` (extend): `fuse_scores(score_vectors, method)` → fused per-candidate vector for `method ∈ {"borda","score_sum"}`. Pure function over a list of score arrays; unit-testable in isolation. Reuses `rank_of` / `anonymity_set_size`.
- `scenario.py` (extend): `make_tracked_cohort(cfg, k, n_tracked, …)` — a cohort where `n_tracked` tracked device(s) each originate K messages at spread-out times within the window, plus single-message background originators for realistic relay density; returns the tracked device→[message ids] map. `intersection_sweep(cfg, k_values, f, reps)` — per K: run the engine, score the K tracked messages with the best per-message estimator, fuse (both rules), compute fused rank-1 + the decoy control + the fused-random floor; return rows over K with CIs + gate verdicts.
- `anonymity.py` (extend): `INTERSECTION_SCOPE_TAG`; `intersection_gate(fused_rank1, decoy_rank1, floor, mustlocalize_ok, …)` → labelled verdict (credited only if exposure-threshold crossed AND decoy not pinned AND must-localize OK), mirroring `defense_gate`'s shape.
- `report.py` (extend): `intersection_to_csv_string` — one row per K carrying both fused-rank-1 rules, the random floor, the decoy control, the gate verdict, delivery/T50 cost, and the scope tag **as columns**.
- `run.py` (extend): `--preset anonymity-intersection` — sweep K at fixed realistic f, print the rank-1-vs-K curve + K-to-pin + the gate verdict + scope tags.
- **RNG substream tags (disjoint, extends PR-1/PR-2 §7):** intersection adds **top-level tag 7 = tracked-cohort placement/timing** (existing: mobility=0, engine=1, cohort=2 [PR-2 background soup = child path (2,7)], buffers=(3,i), placement=4, mixing=5, estimator=6, airtime-bootstrap=777). Top-level `cfg.rng(7)` is disjoint from the child path `cfg.rng(2,7)`. Extend the disjointness test to cover tag 7.
- **Stats:** CI over **seeds** (within-run the K messages of one device correlate); a pre-registered **minimum tracked-devices × seeds** so the fused rank-1 rate is stable; K_values = {1, 2, 4, 8, 16} with K=1 asserted equal to the PR-1 single-event rank-1 (continuity check).
- **Default-inert:** `intersection_sweep` is a new entry point; the existing `anonymity_sweep`/`anonymity_defense_sweep` and every prior number are bit-identical (no shared mutable path changed).

## 6. Bias table (every idealization, with direction)
| Mechanic | Direction |
|---|---|
| reported = best per-message estimator, fused | **UPPER BOUND on anonymity** (smarter adversary/fusion localizes better) |
| device-linkage ASSUMED perfect & given | **optimistic for the adversary** on the linkage axis (real linkage is partial/noisy) → makes our number a **worst-case upper bound**, the safe direction for a privacy claim |
| PHY fingerprinting (how linkage is obtained) not modeled | **scope boundary** — separate slice; do not read PR-3 as the end-to-end attack |
| single external-passive adversary (no insider) | **optimistic for privacy** (deferred) |
| defenses NOT replayed against intersection (PR-4) | PR-3 is the undefended intersection baseline; defenses may or may not help (measured in PR-4) |
| coverage f fixed (K is the axis) | f-robustness is a secondary arm; headline is one realistic f |
| credited headline = the LOWER of the two fusion rules on divergence | **conservative for exposure** (never credit the adversary a methodological coin-flip) |
| worst-case auxiliary info (all trajectories) | **conservative** for exposure (safe direction) |

## 7. Definition of Done
- `intersection_sweep` produces a fused rank-1-vs-K curve at fixed realistic f, with **both** fusion rules, the fused-random floor overlaid, and the decoy-centrality control — over a pre-registered K range starting at K=1 (asserted equal to the PR-1 single-event rank-1).
- `intersection_gate` wired and surfaced in CLI/CSV: credits "intersection deanonymizes the persistent sender" only if the exposure threshold is crossed AND the decoy control passes AND must-localize is OK; otherwise reports the honest negative/inconclusive result.
- Every emitted intersection number carries the scope tag (asserted by a test).
- Engine + all prior slices (1, 2, 3-PR-1, 3-PR-2) bit-identical / non-regressing with the new code present; deterministic by seed; one-command run (`--preset anonymity-intersection`).
- Bias table filled; the measured headline (does intersection cross the threshold, at what K, at what delivery cost) reported faithfully in the README — including a negative result if that is what the sim shows.

## 8. Decisions confirmed / to confirm at sign-off
- **Feature = Slice 3 PR-3, multi-session intersection on sender anonymity** — *CTO ✓ (feature pick delegated, intersection chosen).*
- **Adversary = score-fusion across K linked originations; linkage assumed given** — *CTO ✓ (approach A).*
- **Fusion = rank-sum (Borda) primary + normalized score-sum sensitivity; report both, credit the lower on divergence** — *CTO ✓ (both rules approved).*
- **Headline axis = K at fixed realistic f; K∈{1,2,4,8,16}; K=1 ≡ PR-1** — *recommend yes.*
- **Controls = fused-random floor + decoy-centrality confound + inherited must-localize; intersection-exposure gate credits only if originator pinned AND decoy not** — *recommend yes (the slice's whole credibility).*
- **Defenses replayed against intersection = deferred to PR-4** — *recommend yes (YAGNI; keep PR-3 the clean undefended baseline).*
