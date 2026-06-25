# Feature Spec — Soup Simulator (v1, first slice)

**Status:** Draft for fan-out review → CTO sign-off (loop step 1).
**Date:** 2026-06-25
**Parent design:** [polleneus v0.4](2026-06-25-polleneus-design.md)
**Roadmap:** P0 (re-scope & **measure**) — turns asserted numbers into measured ones.

> **Purpose.** *Measure, don't assume.* The parent spec asserts the headline physics — delivery only works
> above a density threshold (§12.1 percolation cliff), airtime not storage is the wall (§11), flooding caps
> scale (§11). This simulator makes the **first** of those measurable: **delivery probability and latency vs
> node density** for the pure-flooding "uniform soup" model. It is the cheapest way to learn whether the core
> idea even delivers at gathering scale before any phone code is written.

---

## 1. Scope — first slice only

**In:** a reproducible, seeded simulation of nodes moving in an area, meeting over a short-range radio,
blindly carrying + re-sharing fixed-size blobs that expire on a TTL, with a bounded buffer and a seen-record.
**The one headline output:** a **delivery-ratio-vs-density curve** (and latency distribution) that locates the
percolation cliff.

**Out (deferred to later slices, explicitly):** cryptography, tokens/PoSW, the anonymity source-estimator,
the internal mechanics of rateless reconciliation (modeled here only as a per-contact byte budget — see §3),
real BLE PHY/advertising-channel modeling, mobile platform, internet bridges, ferrying.

This slice answers exactly one question: **at what node density does offline unicast delivery become useful,
and how does it degrade?**

---

## 2. Model

- **Space & mobility:** N nodes in a W×H area. Mobility = **Random Waypoint** (default; pluggable) with a
  configurable speed; also support a **static** mode (fixed positions) for percolation-only runs.
- **Contact:** two nodes are "in contact" when within radio range `r`. A contact lasts while they stay in
  range; an **exchange** happens at contact start (and may be re-attempted while in range).
- **Blob:** `{id, created_at, ttl, sender, recipient, size}`. Fixed `size` (the 255-char envelope ≈ 1 KB).
  `id` is opaque (a counter/hash; no crypto needed for this slice).
- **Exchange (flooding):** on contact, each node offers blobs the other lacks; transfer is bounded by a
  **per-contact budget** (bytes or count) representing finite airtime (see §3). No routing, no targeting —
  pure flooding.
- **Buffer:** bounded per node (size cap). When full, **eviction** by the parent §9.5 policy
  (youngest-by-real-age + randomized; *not* closest-to-TTL). Policy is pluggable so we can compare.
- **Seen-record:** per node, remembers recently-seen/dropped/expired IDs so a blob isn't re-accepted after
  eviction/expiry (sliding-window; §6). Prevents resurrection inflating delivery.
- **TTL:** each blob expires at `created_at + ttl` everywhere (absolute; the §6 rule). Expired blobs are
  dropped and recorded.
- **Delivery:** a message is "delivered" the first time its **recipient** holds it. (Trial-decrypt is modeled
  as "recipient recognizes its own id" — no crypto.)

---

## 3. Why model reconciliation as a byte budget (key modeling decision)

The parent design's airtime fix is rateless reconciliation (§8). For *this* slice we don't implement IBLT —
we model each contact as transferring at most `B` bytes (or `k` blobs), where `B` is derived from a contact's
duration × an assumed effective throughput. This **captures the binding constraint (finite airtime per
contact)** without the reconciliation internals, which is what the delivery-vs-density question actually
depends on. A later slice can replace the byte-budget with a real reconciliation model and measure the
delta. *(Reviewers: confirm this abstraction is faithful enough for the headline metric.)*

---

## 4. Metrics (the deliverables)

- **Delivery ratio** = delivered messages / total messages, swept across **density** (nodes per radio-disk
  area, i.e. `N·π·r² / (W·H)` — the percolation control parameter).
- **Delivery latency** distribution (creation → first recipient hold), for delivered messages.
- **Buffer occupancy** over time (sanity / scale check).
- **Circulated-blobs-per-minute** (a first airtime proxy).
- Output: deterministic CSV per run + a delivery-vs-density plot. Every run pinned by an explicit RNG seed.

---

## 5. Architecture (small, testable units)

- `model/` — entities (Node, Blob), geometry, mobility models.
- `engine/` — time-stepped loop, contact detection, exchange.
- `policies/` — flood, eviction, retention, seen-record (each swappable).
- `metrics/` — delivery, latency, occupancy collectors.
- `scenario/` — config (dataclass), seeded runner, density sweep.
- `report/` — CSV writer, optional plot (matplotlib optional dep).
- `tests/` — see §7.

Each unit answers: what does it do, how is it used, what does it depend on — and is testable in isolation.

---

## 6. Stack

**Python 3.11+**, standard library + `numpy` (vectorized geometry). Plotting via optional `matplotlib`
(import-guarded so core + tests need no GUI deps). Hand-rolled time-stepped engine (no SimPy dependency) for
transparency and testability. Fully **deterministic** given a seed. *(CTO confirm: Python is the right call;
we port hot paths to Rust only if 50k-node runs prove too slow.)*

---

## 7. Testing (TDD)

Write tests first. Unit:
- contact detection (in/out of range, boundary);
- exchange respects the per-contact budget and the "only blobs the other lacks" rule;
- TTL expiry drops at the right time everywhere;
- seen-record prevents re-acceptance (no resurrection);
- eviction policy behaves (buffer never exceeds cap; correct victim selection);
- determinism (same seed → identical run).

Integration (known-answer scenarios):
- two nodes in range → message delivered; permanently out of range → never delivered;
- one dense cluster → high delivery; sparse field → low delivery (the curve has the expected shape);
- a flood of junk fills buffers → honest delivery degrades (sanity for a later anti-abuse slice).

---

## 8. Definition of Done (this slice)

1. `delivery-vs-density` sweep runs from a single command and writes a CSV + (optional) plot.
2. All §7 tests green; runs are deterministic by seed.
3. A short `README` in the sim folder: how to run, params, how to read the output.
4. The curve clearly shows the cliff (or its absence) for a documented parameter set.
5. Loop gates: fan-out review clean → CTO sign-off (spec) → plan → build → PR → `@codex review` → CTO merge.

---

## 9. Decisions to confirm at sign-off

- **Stack = Python** (recommend).
- **First-slice boundary** = delivery-vs-density only; defer crypto, tokens, anonymity-estimator, real BLE PHY, reconciliation internals (modeled as a byte budget §3).
- **Mobility default = Random Waypoint** (+ static mode).
- These are the only product-level choices; everything else is implementation detail for the plan.
