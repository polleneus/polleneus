# Soup-Simulator Spec — Fan-out Design Review (digest)

**Date:** 2026-06-25 · **Target:** soup-sim feature spec (first slice) · **Loop step:** 1 (design review)
**Method:** 5 lenses (measurement-validity, design-fidelity, scope-YAGNI, testability-arch, misleading-results) + synthesis.
**Verdict:** **ready-after-fixes** — all 5 lenses returned *sound-with-fixes* (none *needs-rework*).
**Raw:** `2026-06-25-soup-sim-spec-review-raw.json`. **Outcome:** all must-fixes folded into spec v2.

## Scope check (the good news)
The first-slice boundary was endorsed by **all five lenses** as the strongest part — "locate the
delivery-vs-density cliff before any phone code" is the right P0 move, faithfully exercising the
delivery-governing invariants while correctly deferring the orthogonal ones. The byte-budget-instead-of-IBLT
abstraction is a defensible YAGNI call. Two adjustments: add the measurement-rigor controls (below), and
promote airtime/circulation to a co-headline. Do **not** expand into crypto/anonymity/mobile.

## The risk it caught
As drafted, the sim would have produced a **confident, reproducible, and wrong** delivery-vs-density curve —
density axis corrupted by RWP non-uniformity, cliff unverifiable from single-seed runs, byte budget
optimistically density-independent, `dt` an unpinned confound, and the headline metric's denominator undefined.

## Must-fix (all 8 applied in spec v2)
1. **Workload + delivery-ratio denominator** (critical) — define M, injection cohort, uniform src/dst, and the fair-chance (non-censored) denominator. *(4 of 5 lenses)*
2. **Percolation-validation harness** (critical) — static/torus, B=∞/TTL=∞/buffer=∞ must recover mean-degree ≈ 4.51; gates all downstream. Make **static placement the primary cliff probe**.
3. **Density-axis fixes** (high) — explicit boundary topology (torus vs walls), RWP stationarity (v_min>0 + steady-state init), and report delivery vs **empirical** mean degree; stationarity sanity check.
4. **Replications + 95% CIs** (critical) — R≈20–30/point, SeedSequence.spawn sub-seeds, Wilson CI, latency as a distribution; DoD restated to non-overlapping CIs (falsifiable).
5. **Density-aware grounded byte budget** (high) — throughput collapses with local contenders, t_setup floor, p_fail, whole-blob quantization, cited BLE provenance, ≥3 B levels + binding-constraint diagnostic.
6. **Pin dt + per-episode budget** (high) — CFL `v_max·dt ≤ r/4`, dt-convergence, analytic contact timing, budget charged per contact *episode* not per step.
7. **RNG contract** (high) — one injected `default_rng`, no module-global RNG (lint test), substreams via spawn, byte-identical determinism test.
8. **Exchange semantics** (high) — per-episode budget, scarcity offer-selection as a measured policy, half-duplex justification, deterministic pair order, typed buffer-accept contract.

## Key should-consider (also folded in)
- **Invariant guard in code:** sender/recipient are scoring-only oracle labels; model/engine/policies see only `{id,created_at,ttl,size}` (lint-enforced) — protects inv 2 & 4.
- Circulation/airtime promoted to **co-headline**; contrasting buffer/TTL/B + eviction regimes; logistic-fit quantitative cliff; full parameter manifest per CSV row + fidelity-to-parent + caveats sections; O(N) cell-list index; censoring-robust deadline metric; **STATIC primary / RWP optimistic overlay**.

## Sign-off recommendation (from synthesis)
**Conditional approval — fix the spec, don't re-think it.** All high/critical findings converge on one short
root-cause list (strong signal). Stack=Python fine; first-slice boundary approved; **mobility default changed to
static-primary**. Re-confirm the must-fixes landed, then green-light the build.
