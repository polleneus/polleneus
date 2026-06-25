# Feature Spec — Soup Simulator (v1, first slice)

**Status:** Revised after fan-out review (round 1) → **awaiting CTO sign-off** (loop step 1).
**Date:** 2026-06-25
**Parent design:** [polleneus v0.4](2026-06-25-polleneus-design.md)
**Review trail:** [soup-sim spec review](../reviews/2026-06-25-soup-sim-spec-review.md)
**Roadmap:** P0 (re-scope & **measure**).

> **Purpose.** *Measure, don't assume.* Make the parent's headline physics measurable, starting with the
> make-or-break one: **does pure-flooding offline unicast deliver, and at what node density does it cross
> from useless to useful** (the §12.1 percolation cliff) — established *before* any phone code.

> **Review takeaway that shapes this revision:** as first drafted, the sim could have produced a *confident,
> reproducible, and wrong* curve. The fixes below exist so the measured cliff is a real percolation
> phenomenon, not an artifact of mobility bias, an unpinned time-step, a single RNG seed, or an
> over-optimistic airtime model. **Every number this sim reports is an UPPER BOUND on real-world delivery.**

---

## 1. Scope — first slice only

**In:** a seeded, reproducible sim of nodes meeting over a short-range radio, blindly carrying + re-sharing
fixed-size blobs that expire on an absolute TTL, with a bounded buffer + seen-record + a defined message
workload. **Two co-headline outputs vs density:** (a) **delivery ratio** (with confidence intervals) and (b)
**circulation/airtime cost** — because for a pure-flooding system the cost curve is co-equal with delivery
(100% delivery in an airtime-saturated regime is operationally dead).

**Out (deferred, explicit):** cryptography, tokens/PoSW, the anonymity source-estimator, rateless-recon
internals (modeled as a grounded byte budget §6), real BLE PHY/advertising-channel modeling, mobile platform,
internet bridges, ferrying. **Invariant guard (enforced in code even though unmeasured here):** sender/recipient
are **scoring-only ground-truth labels** in the metrics/oracle layer — `model`, `engine`, and `policies` may
read **only `{id, created_at, ttl, size}`** (protects inv 2 pure-flooding & inv 4 sealed-sender; a lint test
asserts no forwarding/eviction/exchange code references sender/recipient).

---

## 2. Measurement methodology (the heart of the revision)

### 2.1 Two regimes, not one curve
The percolation cliff is a **connectivity** threshold; delivery *also* depends on airtime, buffer, TTL, and
mobility. So we separate them:

- **(A) Percolation-validation baseline — the gating first test.** STATIC uniform/Poisson placement on a
  **torus** (periodic boundary, matches infinite-plane theory), `B=∞, TTL=∞, buffer=∞`. Assert the
  giant-component / delivery knee lands near the **known continuum-percolation critical mean degree ≈ 4.51**
  within a stated tolerance. This validates contact-detection + the density axis against ground truth and
  **gates everything downstream** (no trusting any curve until this passes).
- **(B) Dynamic delivery sweep.** The realistic measurement, with finite `B/TTL/buffer` and mobility. Reported
  *alongside* (A) so the reader can see whether a delivery drop is connectivity (never arrives) or
  airtime/TTL (arrives too slow / budget-starved).

**STATIC uniform placement is the PRIMARY cliff probe** (it is the regime where the density parameter literally
equals theory's reduced density). **Random Waypoint is a labeled *optimistic overlay*, not the headline default.**

### 2.2 Density axis (the one quantity we measure — keep it clean)
- Control parameter: mean degree `d = N·π·r² / (W·H)` for static uniform; **also compute and plot delivery
  against the EMPIRICAL mean neighbor degree** measured over the steady-state window (RWP center-concentrates
  nodes, so nominal ≠ realized).
- **Boundary mode is an explicit, logged config field:** `torus` for validation/cliff sweeps; `walls` for the
  venue scenario (report the expected upward threshold shift separately).
- Finer density spacing through the transition band.

### 2.3 Mobility validity (RWP overlay)
Enforce `v_min > 0` (kills RWP speed-decay); initialize positions+speeds from the **stationary** RWP
distribution (perfect init) **or** discard a detected warm-up window from all metrics. A **stationarity sanity
check** (first-half vs second-half contact-rate / mean-degree within tolerance) must pass before a curve is accepted.

### 2.4 Timeline & workload (define the denominator)
Three phases: **warm-up** (mobility + cover churn to steady state, or skip via stationary init) → **measurement
window** (inject the workload) → **drain** of ≥ one max-TTL after the last injection (no right-censoring).
- **Workload:** `M` messages; default a **single fixed cohort injected at warm-up end** (cleanest first curve;
  sweepable rate optional); src/dst = **uniform-random distinct pairs**.
- **Delivery ratio = (messages first-held by their recipient within absolute TTL) / (fair-chance cohort)**,
  where the fair-chance cohort = messages whose `creation_ts` leaves ≥ one max-TTL of in-window sim time
  (excludes right-censored end-of-run messages). A known-answer test pins this denominator.
- Confirm the load is **light enough not to itself saturate `B`** (else we'd measure congestion, not percolation).

### 2.5 Replications + confidence (a single seed cannot locate a cliff)
Variance is maximal at the threshold. Run **R independent replications per density point** (start R = 20–30,
denser near the cliff), sub-seeds via `numpy SeedSequence.spawn` from one master seed. Report **mean delivery
with a 95% Wilson CI** (better than normal near 0/1) and **latency as a distribution** (median + IQR/percentiles,
presented *jointly* with delivery and flagged conditional-on-delivery: survivorship bias can make mean latency
*improve* as the system worsens). Also report a **censoring-robust** "fraction delivered within deadline Δ".

---

## 3. Model

- **Space & mobility:** N nodes in W×H. Modes: **static-uniform (primary)**, **RWP overlay** (§2.3). Boundary:
  torus | walls (§2.2).
- **Contact:** in contact when `dist² ≤ r²`. Contact is an explicit **state machine** (out→in = start,
  in→in = ongoing, in→out = end). Compute entry/exit **analytically per straight-line leg** (closest-approach
  to segment) so contacts/durations are **dt-independent**; charge budget **per contact episode** (entry→exit),
  never per step. O(N) neighbor search via a **uniform grid / cell-list** bucketed by `r` (with a
  brute-force-equivalence test on small N).
- **Blob:** `{id, created_at, ttl, size}` (engine/policies see only these). Fixed `size` (~1 KB). Optional
  pluggable **hop-energy** field (born B, decrement-on-reshare, drop at 0) — default non-binding for v1.
- **Exchange (flooding):** on a contact episode, each node offers blobs the other lacks; transfer bounded by
  the §6 budget. **Offer-selection-under-scarcity** = explicit swappable seeded policy (default uniform-random
  among missing) and a *measured variable*. Budget per-direction or shared (justified vs BLE half-duplex).
  Deterministic pair-iteration order (sorted by id). Buffer accept contract returns
  `Accepted | RejectedSeen | RejectedExpired` with accept-then-evict-to-fit.
- **Buffer:** bounded; **eviction = oldest-by-creation cohort with randomized tie-break (retain younger), NOT
  closest-to-TTL** (parent §9.5); plus per-neighbor buffer-share cap. Pluggable (compare random/FIFO).
- **Seen-record:** sliding window `W ≥ maxTTL + margin` (parent §6), **FIFO-by-time** aging; anti-resurrection
  guaranteed (no expired/evicted id re-accepted within W; `delivery count == unique recipient-first-hold count`).
- **TTL:** absolute `created_at + ttl` everywhere (parent §6).

---

## 4. Time-step contract
- CFL-style constraint asserted at startup: `v_max · dt ≤ r/4 … r/5`.
- `dt`-convergence check in the validation plan: halving `dt` changes delivery ratio and mean contact duration
  by < tolerance. (Analytic contact timing makes this robust.) Log `dt` + a missed-contact estimate in the CSV.

---

## 5. RNG contract
Single injected `numpy.random.Generator` (`default_rng(seed)`) threaded explicitly through model/engine/policies.
**No module-global `np.random.*` / `random.seed`** anywhere (a grep/lint test enforces this). Per-replication and
per-component substreams via `SeedSequence.spawn` (order-independent → safe for parallel replications).
Determinism test: two same-seed runs produce **byte-identical output CSV**, and two cells run in swapped order are identical.

---

## 6. Airtime / byte-budget model (grounded, density-aware)
A constant budget is structurally optimistic (cheapest airtime exactly where the parent says it gets expensive).
Required:
1. Effective throughput `= throughput_ideal / (1 + α · n_local_contenders)`, `n_local_contenders` = peers within
   `r` at contact time; sweep/sensitivity-test `α`.
2. Per-contact **setup/handshake cost `t_setup`** subtracted before any payload — contacts shorter than
   `t_setup` transfer **zero** (kills the "free delivery on a 1-second brush" bias at the sparse end).
3. Reconciliation **decode-failure probability `p_fail`** → zero useful transfer.
4. **Quantize** transfer to whole ~1 KB blobs (0.9 blob delivers 0).
5. **Ground** throughput / `t_setup` / contact-duration in **cited BLE figures** (a parameter-provenance table).
6. Sweep `B` at ≥ 3 levels (binding / marginal / non-binding) + a **binding-constraint diagnostic**: the
   fraction of contacts where the budget actually bound. If ~0 across the sweep, we're measuring contact-graph
   percolation, not airtime-limited delivery, and the abstraction is decorative (say so).

README states constant-B is an **upper bound** on delivery.

---

## 7. Architecture (small, testable, invariant-safe units)
`model/` (entities, geometry, mobility, cell-list) · `engine/` (stepping, analytic contact state-machine,
exchange) · `policies/` (flood, offer-selection, eviction, retention, seen-record — swappable) · `metrics/`
(delivery, latency, circulation/overhead, occupancy; **holds the sender/recipient oracle**) · `scenario/`
(config dataclass, seeded runner, density sweep, replications) · `report/` (CSV + full param manifest, optional
matplotlib, logistic-fit cliff estimator) · `tests/`.

---

## 8. Stack
**Python 3.11+**, stdlib + `numpy` (vectorized geometry, `default_rng`, `SeedSequence`). `matplotlib` optional /
import-guarded. Hand-rolled engine. Cell-list spatial index for O(N). Keep the Rust hot-path option **only** if
profiling the 50k-node × R-replication sweep demands it.

---

## 9. Testing (TDD, tests first)
**Gating:** the §2.1(A) percolation-validation harness recovers mean-degree ≈ 4.51 within tolerance.
**Unit:** analytic contact entry/exit incl. fast tangential fly-through; per-episode budget cap; dt-convergence;
`dist² ≤ r²` boundary; exchange respects budget + only-missing + scarcity-selection; TTL expiry timing;
seen-record anti-resurrection past capacity; eviction exact-victim (oldest cohort, never closest-to-TTL) + property
test; RNG determinism (byte-identical CSV, swap-order identical, no module-global RNG); invariant lint (no
sender/recipient in model/engine/policies); cell-list ≡ brute force on small N.
**Integration (known-answer):** 2 in-range→delivered, permanently-out→never; static dense→high, sparse→low with
the **expected sigmoid shape and non-overlapping CIs across the transition**; junk-flood→honest delivery degrades
(no resurrection).

---

## 10. Definition of Done (this slice)
1. Percolation-validation harness passes (recovers ≈ 4.51 within tolerance) — the gate.
2. One-command density sweep → CSV (with **full parameter manifest** per row) + plots for **both** delivery
   (mean + 95% CI) and circulation/airtime cost vs density; STATIC primary, RWP overlay labeled optimistic.
3. **Quantitative cliff:** logistic fit reports the delivery=0.5 midpoint with a CI from replications
   (DoD #4 is now falsifiable, not eyeballed).
4. All §9 tests green; runs deterministic and independently reproducible from the manifest.
5. Sim README: how to run, parameters, **fidelity-to-parent traceability table** (each modeled mechanic → parent
   §, each abstraction → direction of its bias), and a **modeling-assumptions/caveats** section.
6. Loop gates: this revised spec signed off → plan → build → PR → `@codex review` → CTO merge.

---

## 11. Decisions to confirm at sign-off
- **Stack = Python** (numpy + cell-list; Rust only if profiling demands).
- **First-slice boundary** = delivery + circulation vs density; defer crypto/tokens/anonymity-estimator/real-PHY;
  reconciliation modeled as the grounded byte budget (§6). *(Endorsed by all 5 review lenses.)*
- **Mobility: STATIC uniform is the PRIMARY cliff probe; RWP is a labeled optimistic overlay** *(changed from the
  draft's RWP-default, per review)*. A clustered/hotspot "gathering" mobility model (truer to inv 7) is noted as a
  fast-follow, not in this slice.
