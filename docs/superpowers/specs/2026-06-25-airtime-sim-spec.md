# Feature Spec — Airtime & Mobile-Delivery (Simulator Slice 2)

**Status:** Draft for fan-out review → CTO sign-off (loop step 1).
**Date:** 2026-06-25
**Parent design:** [polleneus v0.4](2026-06-25-polleneus-design.md) · **Builds on:** [soup-sim slice 1](2026-06-25-soup-sim-spec.md)
**Roadmap:** P0/P1 — measures the red-team's **risk #1: "airtime, not storage, is the real scale wall."**

> **Purpose.** Slice 1 measured *connectivity* (does the contact graph percolate? d_c≈4.51). It deliberately
> deferred the more existential question: **even when the graph is connected, can BLE physically *stir the
> soup* fast enough — or does airtime saturate and delivery collapse at crowd density?** This slice turns on
> the dynamic engine + a BLE-grounded airtime model and measures **delivery and airtime cost vs density under
> mobility**, finding the saturation knee — before any phone code commits us to a stack.

> **Every number is an UPPER BOUND on real delivery** (same idealizations as slice 1, plus the airtime model
> is still a model, not measured BLE).

---

## 1. Questions this slice answers
1. **Airtime ceiling:** circulated-blobs-per-minute and per-contact **airtime utilization** vs density. Does
   delivery **rise then fall** (contention-limited) or plateau? Where is the saturation knee?
2. **Mobile delivery:** delivery ratio + **latency** vs density under **Random Waypoint** carry-and-forward
   (does DTN delivery actually happen at gathering scale, and how slow is it?).
3. **Is airtime even binding?** The binding-constraint diagnostic: fraction of contacts where the budget bound.
   If ≈0 across the sweep, we are still measuring connectivity, not airtime (and must say so).

Co-headline output: **delivery vs density** AND **airtime-cost/utilization vs density**, both with CIs.

---

## 2. The honest blocker to resolve first — engine fidelity
Slice 1's *validated headline* used the **engine-free static** path (component reachability + percolation
gate). The **dynamic engine is comparatively unproven**: it settles each contact **once per episode at the
entry time**, which is fine for percolation but may **under-represent mobile multi-hop over time** (a node
that gains blobs mid-window forwarding them onward) and repeated exchange within long contacts.

**In scope before trusting any mobile curve:** a **fidelity gate** for the dynamic engine —
- reproduce a **known DTN result** (e.g., epidemic/SI delivery growth over time in a dense mixing population
  matches the analytic logistic SI curve within tolerance), and
- a multi-hop-over-time check (a 3+ hop chain delivers across *separate* contacts as mobility reconfigures).

If the engine fails these, **refine it** (deliver blobs at the time they become available during a contact;
allow repeated exchange as buffers grow) — refinement is part of this slice. We do not publish a mobile curve
the engine can't faithfully produce.

---

## 3. Airtime model (grounded, the core new work)
Extend the existing per-contact budget into a defensible BLE-contention model:
- **Effective goodput collapses with local contention:** model the shared 3 advertising channels (no hopping)
  — e.g. `goodput = goodput_ideal / (1 + α·n_contenders)` (current form) **and** a CSMA-style alternative to
  sensitivity-test; `n_contenders` = peers within range during the contact.
- **Per-contact setup floor `t_setup`** (handshake/discovery) subtracted before payload.
- **Whole-blob quantization** + reconciliation **decode-failure `p_fail`**.
- **Ground** `goodput_ideal`, `t_setup`, typical contact duration in **cited BLE figures** (a
  parameter-provenance table in the README; not invented numbers).
- **Sweep the airtime budget at ≥3 levels** (binding / marginal / non-binding) + report the binding fraction.

---

## 4. Method (reuse slice-1 infrastructure)
- **Mobility:** RWP (slice-1's burn-in stationary init + stationarity acceptance gate); RWP is the headline
  mobility for *this* slice (it's a moving-crowd question).
- **Timeline:** warmup → inject cohort → measure window → drain ≥ maxTTL (slice-1's run_one, now exercising
  the dynamic engine on the mobile path).
- **Stats:** per-replication CIs (slice-1 `mean_ci`, Student-t) + bootstrap saturation-knee estimate.
- **Determinism:** slice-1 injected-RNG contract (disjoint substreams) unchanged.

---

## 5. Scope
**In:** the fidelity gate + any engine refinement it requires; the grounded airtime model; the mobile
delivery + airtime-cost sweep; the binding-constraint + saturation-knee diagnostics; README update.
**Out (still deferred):** crypto/tokens, anonymity source-estimator, real PHY beyond the contention model,
internet bridges, mobile platform.

---

## 6. Definition of Done
1. **Engine fidelity gate passes** (SI/epidemic growth match + multi-hop-over-time) — gates the curves.
2. One-command run produces **delivery-vs-density** and **airtime-utilization-vs-density** (mean + CI) under
   RWP, plus circulated-blobs/min and the binding-constraint fraction; saturation knee reported with a CI.
3. ≥3-level airtime-budget sweep + provenance table; results labelled **upper bound**.
4. All tests green + deterministic; new tests for the fidelity gate, the contention model, and the diagnostics.
5. README: how to run, the measured airtime finding, fidelity-to-parent + caveats updated.
6. Loop gates: this spec signed off → plan → build → PR → `@codex review` (best-effort, 10-min) → CTO merge.

---

## 7. Decisions to confirm at sign-off
- **Engine refinement scope:** refine the dynamic engine to pass the fidelity gate (recommended), vs. measure
  as-is with heavy caveats. *(Recommend: refine — a mobile curve from an unfaithful engine is worse than none.)*
- **Airtime model form:** ship the `1/(1+α·n)` model as primary with a CSMA-style sensitivity check (recommend),
  vs. a fuller CSMA/collision model now.
- **Mobility = RWP** for this slice (a clustered "gathering" mobility model stays a later fast-follow).
