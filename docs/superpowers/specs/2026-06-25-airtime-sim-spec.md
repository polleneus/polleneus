# Feature Spec — Airtime & Mobile-Delivery (Simulator Slice 2)

**Status:** Revised after fan-out review (round 1) → targeted re-review → **CTO sign-off** (loop step 1).
**Date:** 2026-06-25
**Parent design:** [polleneus v0.4](2026-06-25-polleneus-design.md) · **Builds on:** [soup-sim slice 1](2026-06-25-soup-sim-spec.md)
**Roadmap:** P0/P1 — measures the red-team's **risk #1: "airtime, not storage, is the real scale wall."**

> **Purpose.** Slice 1 measured *connectivity* (d_c≈4.51, engine-free static path). This slice asks the more
> existential question: **even when connected, does BLE airtime saturate at crowd density and collapse
> delivery?** It is split into two sequenced PRs so an engine bug can never be mistaken for an airtime effect.

> **Review-driven reshape (round 1, verdict needs-rework):** the original `1/(1+αn)` model *cannot* produce a
> rise-then-fall and `n_local` *was* the density axis — so any down-turn would have been an artifact. v2 fixes
> all six must-fixes below. **Every number remains an UPPER BOUND on real delivery.**

---

## 1. Two sequenced PRs (the scope split — must-fix #2)
The original spec bundled engine-refinement + a new airtime model + new measurements. A refinement that changes
exchange semantics would silently move slice-1's *validated* percolation numbers, and a reviewer couldn't tell
an engine bug from a real airtime effect. So:

- **PR-1 — Engine fidelity (no airtime model, no new physics).** Make the dynamic engine trustworthy for mobile
  multi-hop, gated hard. Ships first, merges, then:
- **PR-2 — Airtime model + measurement.** Built only on the trusted engine.

This spec covers both; **sign-off authorizes PR-1's plan first.**

---

## 2. PR-1 — Engine fidelity

### 2.1 Refined exchange semantics (must-fix #3)
- **Within an open episode, iterate offer-rounds to a fixpoint**, each round consuming from the **shared
  per-episode airtime pool** (granted once; `t_setup` charged once per physical episode), and able to pick up
  blobs that arrived in a prior round → real multi-hop *within* a long contact, not one hop.
- **Fix the latency timestamp at the ENGINE (not a clamp):** stamp `on_deliver` with the **actual delivery
  time** so `delivered_at ≥ created_at` holds *by construction*. Do **not** clamp/`max()` in `metrics` — a clamp
  would hide the underlying timing bug. The test asserts no negative or pre-creation latency *arises at the
  source* (it must fail if the engine ever emits one), and the latency curve is **not published until this passes.**
- **Overlapping-contact determinism:** for simultaneous A–B and B–C, assert delivered-set + timestamps are
  invariant to `neighbor_pairs` ordering; if not, canonicalize by earliest-enter-first and document it.

### 2.2 Fidelity gate (must-fix #2 — pinned, falsifiable)
PR-1 merges only if ALL pass:
- **Contact-timing fidelity (decoupled from exchange):** empirical RWP pairwise **meeting rate** and **mean
  contact duration** match the RWP analytic expressions within tolerance — proving the contact graph is right
  before testing exchange.
- **SI/epidemic growth:** in a clearly **supercritical, well-mixed** population (NOT near d_c, where mean-field
  SI is invalid), infected-count over time matches the closed form `I(t)=N/(1+(N-1)e^{-βt})` within a justified
  tolerance + CI over ≥N seeds, where **β is derived from the measured meeting rate** (not fitted).
- **Multi-hop-over-time (both directions):** a ≥3-hop chain *delivers* across *separate* contacts as mobility
  reconfigures — AND a **negative arm**: the same chain does **not** deliver when an intermediate link never
  forms (a node held out of range) and does **not** deliver when `t_setup` exceeds every contact duration
  (airtime-starved). The negative arm catches an *over-delivery* engine bug (leaked budget pool, stale
  never-settled `self.open` episode) that a positive-only test would miss — the exact channel by which an
  engine bug could masquerade as an airtime effect in PR-2.
- **Non-regression (hard gate):** `test_integration_percolation.py` (oracle-KAT + susceptibility peak) stays
  green bit-for-bit (or with an explicitly justified delta), AND the refined engine reproduces
  `settle_static_fixpoint` delivery in the `cap=∞ / ttl=∞ / α=0 / t_setup=0 / static` limit.

---

## 3. PR-2 — Airtime model + measurement

### 3.1 Collision-capable airtime model (must-fix #1 — the critical one)
- **Primary model must be able to turn over.** Connectionless BLE advertising is **ALOHA-like, not CSMA**:
  use `p_success(n) = exp(-β·n)` on the 3 shared advertising channels (and/or density-dependent
  `t_setup(n)=t_setup0 + c·n` driving usable airtime negative) so an **interior maximum is possible**. The old
  `1/(1+αn)` (monotone plateau) becomes the *optimistic-bound* sensitivity case, not the primary.
- **Decouple contenders from connectivity degree:** `n_contenders` is the **co-channel/interference**
  population, **not** the unit-disk graph degree (carrier-sense range ≠ connectivity range). Justify the mapping
  and its bias direction in the provenance table.
- **Model form is a first-class sensitivity axis:** report knee/peak under each form as a **model-uncertainty
  band**; state the falsifiable prediction up front (linear ⇒ plateau, collision ⇒ knee near X) and add a test
  that the two forms are actually distinguishable (interior max vs plateau).
- **α=0 control overlay** on the SAME axes for every airtime curve: if α=0 already turns over, the turn-down is
  connectivity/buffer/TTL, not airtime.

### 3.2 Precise metrics (must-fix #5)
- **Airtime utilization** = `Σ charged_airtime / Σ available_contact_time`, where
  `charged_airtime = t_setup + served_blobs·blob_size/eff` (budget RETURNS airtime, not just a count; `t_setup`
  is in the numerator — at high density many short contacts make it the real sink). Report **against OFFERED
  airtime** (what would move every blob the peer lacks) so a flat curve is interpretable.
- **Circulated-blobs/min** = accepted transfers **during the measure window only** (snapshot the counter at
  warmup-end and measure-end) / measure_window-in-minutes; document whether dummy/duplicate traffic counts.

### 3.3 Saturation-knee estimator + binding GATE (must-fix #4)
- **Knee = argmax of circulated-blobs/min** with a local quadratic-in-log-density fit (anti grid-pinning),
  bootstrapped over the per-rep matrix; returns **"no knee in range"** (not NaN) when monotone. Do NOT reuse the
  monotone 0.5-crossing machinery. Add a synthetic planted-peak test.
- **Hard publish gate:** the "airtime saturation" figure is published **only if** the contention-limited binding
  fraction (decomposed from setup-starved / quantization-limited / demand-limited) exceeds a **pre-registered
  threshold** at/beyond the knee AND the α=0 control does **not** also turn over. Otherwise label the curve
  connectivity/buffer/TTL-limited.

### 3.4 Latency + confounder controls (must-fix #6)
- **Censoring-aware latency:** TTL-expired = censored at TTL; report **time-to-X%-delivery (T50)** or a
  Kaplan-Meier-style estimate, **jointly with delivery ratio**; delivered-only mean latency is labelled a LOWER
  bound (survivorship makes it look flat/better exactly where the system worsens).
- **Control buffer_cap and TTL:** run ≥1 airtime sweep at `cap=∞ AND ttl=∞`; if the turn-down survives ⇒
  airtime, if it vanishes ⇒ buffer/TTL. Pre-register cap/TTL with bias direction.
- **Provenance table (filled, cited):** conservative `goodput_ideal ≈100 kbps` (no-DLE) as headline with the
  optimistic ~1.4 Mbps as upper sensitivity; **density-dependent `t_setup`** from cited discovery-latency-vs-
  advertiser-count; β/α from a cited collision curve; report the RWP contact-duration **distribution** (flag if
  its tail is optimistic vs human-contact data). Extend the README bias table with a row+direction per new
  mechanic (single-snapshot/max-degree contention, lump-at-entry vs incremental, independent per-blob p_fail,
  **omitted set-reconciliation overhead**, RWP-vs-clustered — all optimistic).

---

## 4. Scope
**In:** PR-1 (engine fidelity + gate); PR-2 (collision airtime model, precise metrics, knee+binding gate,
censoring-aware latency, cap/TTL controls, provenance). Reuses slice-1 infra (RWP+stationarity gate, run_one
timeline, mean_ci, RNG contract, sweep, bootstrap).
**Out (named deferrals):** crypto/tokens, anonymity source-estimator, real PHY beyond the contention model,
internet bridges, mobile platform, **set-reconciliation protocol overhead** (we model zero — optimistic, noted),
**clustered/"gathering" mobility** (RWP is open-field, least representative of a crowd → explicit fast-follow).

## 5. Definition of Done
PR-1: fidelity gate (timing + SI + multi-hop) passes; percolation non-regression holds; refined-exchange tests
(intra-contact multi-hop = single-pool budget; `delivered_at≥created`; overlap shuffle-invariance) green.
PR-2: collision model with α=0 control + model-uncertainty band; utilization/circulation defined + tested; knee
estimator + binding publish-gate; censoring-aware latency; cap/TTL control sweep; filled provenance + README
bias rows; all deterministic; one-command run.

## 6. Decisions to confirm at sign-off
- **PR split** (engine fidelity first, then measurement) — *recommend yes.*
- **Primary airtime model = ALOHA collision** (`exp(-βn)`), `1/(1+αn)` demoted to optimistic sensitivity — *recommend yes.*
- **Headline goodput = conservative ~100 kbps** with optimistic upper sensitivity — *recommend yes.*
- **Mobility = RWP** this slice (clustered mobility is a named fast-follow).
