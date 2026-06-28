# polleneus — P4 PR-1: Ferrying below the percolation threshold (the cold-start lift)

**Version:** v0.1 — 2026-06-28 · **Roadmap:** P4 — PR-1 (§16-P4: blind ferrying; cold-start)
**Parent design:** [polleneus v0.5 §14](2026-06-25-polleneus-design.md) · **Builds on:** P3 hold-budget `H`, P0 storage/airtime budgets

> **Why this serves the mission.** polleneus is for *when things go down* — and a blackout/protest is exactly
> the **sparse, sub-percolation** regime. The static percolation oracle says a uniform network *shatters*
> below mean degree `d_c ≈ 4.51`: instantaneous multi-hop delivery collapses toward 0. If that were the whole
> story, the tool would not work in the very situation it is built for. The saving grace is **time**: mobile
> nodes physically **carry** sealed blobs between components (store-carry-forward = *blind ferrying*), so
> delivery below `d_c` is governed by **temporal connectivity**, not the static snapshot. This PR measures
> that lift honestly — **how much** ferrying delivers below `d_c`, **what it costs** (time-budget + latency),
> and **where it still fails** (the floor that motivates the PR-2 bridge + the §14 pair-to-activate / standby).

## 1. Problem & current state

The sim already has both ground truths but has **never compared them as a function of the time budget**:
- **Static bound** — `percolation.same_component_pair_fraction` (snapshot component reachability). Collapses
  below `d_c ≈ 4.51`. Exposed via `static_delivery_sweep`.
- **Temporal/ferrying delivery** — the engine's store-carry-forward flood over a **mobility trace**
  (validated against `percolation.temporal_reachable`, the interval-based time-respecting oracle). Exposed
  via `run_one` / `sweep`.

The existing `cluster_leak_sweep` is **engine-free** (it averages *static snapshots*), so it captures how
clustering changes instantaneous connectivity — **not** ferrying over time. No artifact answers the mission's
existential question: **does a message get delivered in a statically-shattered (sub-`d_c`) network, and at
what time/latency cost?**

## 2. The measurement (the deliverable)

`ferrying_budget_sweep(base_cfg, densities, budgets, reps)` — for each **sub-threshold density** `d` and each
**time budget** `T` (the blob's `ttl == measure_window == T`, i.e. the P3 hold-budget made into the
controllable knob), run the mobile engine and report **delivery(d, T)**, **latency**, and the **static
bound(d)**. The lift is `delivery(d,T) − static_bound(d)`.

- **Densities** sub-threshold: e.g. `d ∈ {0.3, 0.5, 0.8}` (small `N` — the engine is super-linear, but
  cold-start is naturally cheap: `N = d·WH/(πr²)` is tiny here, `N ≈ 13–35`). **Bounded**: low reps, capped
  density, every run short — no unbounded sweep.
- **Budgets** `T`: e.g. `{10, 30, 80, 200}` arena-time units, spanning "no time to ferry" → "fully ferried."
- **Honest framing:** delivery is reported as a function of `T` so the **budget→delivery** curve (and its
  latency cost) is explicit. `T` is the same quantity as the P3 hold-budget `H` and is bounded by the
  absolute TTL (≤ 7 d) and the P0 storage budget (holding longer costs buffer) — cross-referenced, not free.

## 3. What we measure (reproduced — RWP, W=H=140, r=12, speed 2; **seed=7, reps=4**)

| d (N) | static | T=10 | T=30 | T=80 | T=200 | budget_to_half |
|------:|------:|-----:|-----:|-----:|------:|---------------:|
| 0.3 (13) | 0.010 | 0.15 | 0.20 | 0.85 | 1.00 | 80 |
| 0.5 (22) | 0.024 | 0.05 | 0.23 | 0.90 | 1.00 | 80 |
| 0.8 (35) | 0.039 | 0.15 | 0.62 | 0.97 | 1.00 | 30 |

> **The `1.00` ceiling is NOT a capability result.** RWP on a torus is **ergodic**, so *every* src/dst pair
> eventually meets → delivery → 1.0 for **any** `d > 0` given enough budget (confirmed: even `N=2`, `d=0.05`,
> static 0.000, reaches 1.0 by `T≈1500`). So "ferrying delivers given budget" is, in this optimistic model, a
> restatement of ergodic mixing. **The only informative, mission-relevant content is the BUDGET SCALING** —
> how big a hold-budget the cold-start regime demands, and how it **blows up as density falls**.

Honest claims this supports:
1. **The cost of cold-start is the budget, and it rises as density falls.** `budget_to_half` (smallest budget
   reaching 50 % delivery) goes `30 → 80` as `d` falls `0.8 → 0.3`; the relation `budget_to_half(sparser) ≥
   budget_to_half(denser)` is robust (**20/20 seeds**, `d=0.3` vs `1.0`). In the limit `d → 0` the required
   budget → ∞ (and in real *constrained* mobility may be **unbounded** — the floor PR-2's bridge addresses).
   This is the same quantity as the **P3 hold-budget `H`** and the **P0 storage** budget: a thinner venue
   forces a longer hold and more buffer.
2. **Ferrying does lift delivery below `d_c`** — at `d=0.3` the static network delivers ~1 %, ferrying reaches
   ~100 % given budget. The lift is real; its *ceiling* is ergodic (claim 0), its *cost* is the budget (claim 1).
3. **Latency** (reported as `t50`, the median of delivered latencies — **delivered-only + right-censored at
   `T`**, hence a **lower bound** on true delay) is nonzero and grows toward the budget as the venue thins.
   Delivery is **non-decreasing in `T` in expectation** (local cell inversions occur seed-to-seed).

## 4. Honesty / invariants

- **UPPER BOUND (loud).** RWP open-field, full **ergodic** re-mixing, **no airtime/collision cost AND no
  buffer cost** on this path (`buffer_cap` effectively infinite, `p_fail=t_setup=0`) → an **optimistic**
  ceiling. Real mobility is constrained/clustered (people don't random-walk a city), so real budgets are
  **larger** and real delivery **lower**. Time/latency is in **arena-time units, not seconds**. Carries the
  existing upper-bound disclaimer; the clustered-regime temporal version is a noted follow-up.
- **No new mechanism, no invariant touched.** PR-1 is a *measurement* over existing, oracle-validated
  machinery (engine delivery is already checked against `temporal_reachable`); no engine/config change beyond
  the new scenario + report functions. Determinism preserved (seeded substreams).
- **The floor that motivates PR-2.** Below the budget floor — or where mobility is too constrained / `N` too
  small for any inter-component contact — even ferrying fails. That residual is the case for the **§14 bridge
  (opportunistic NAN/LoRa long-range sideband)** and the **pair-to-activate (N=2) / standby (N=0)** UX — **P4
  PR-2**. PR-1 establishes the budget-governed lift; PR-2 lifts the floor.

## 5. Tests (tiny/fast, reps ≤ 4)

- **Lift exists + sub-threshold + floor control (the teeth):** at a sub-threshold `d` (`static_bound < 0.1`),
  `delivery(T_large)` is large but `delivery(T_small) < 0.4` — i.e. a short budget sits near the static floor
  (no time to ferry). The discriminating assertion is the floor one (`small < 0.4`, robust); the large-budget
  ceiling is acknowledged as ergodic.
- **THE honest gate — budget rises as density falls:** `budget_to_half(sparser) ≥ budget_to_half(denser)`,
  both finite within the swept budgets (robust: 20/20 seeds, `d=0.3` vs `1.0`). Replaces the seed-brittle
  raw per-`T` comparison.
- **Latency honesty:** `t50` is finite and within `[0, T]` (delivered-only + censored — a lower bound).
- **Ergodic-saturation documented (anti-false-confidence):** an extremely sparse venue still saturates at a
  large budget — asserted explicitly so the `1.0` ceiling can't masquerade as a capability claim.
- **Determinism**; **report carries the UPPER-BOUND + ERGODIC + censoring headers.**

## 6. Plan sketch

1. `scenario.ferrying_budget_sweep(base_cfg, densities, budgets, reps)` → rows
   `{density, n, static_bound, per_budget: {T: {delivery, ci, mean_latency}}, ...}` (reuses `run_one`,
   `same_component_pair_fraction`; seeded by `_seed_for`).
2. `report.ferrying_table(...)` CSV/markdown with the loud upper-bound + RWP-regime header.
3. `tests/test_p4_ferrying.py` — the §5 gates, tiny configs.
4. README fidelity row (ferrying lift below `d_c`; budget-governed; UPPER BOUND; floor → PR-2).
5. Bounded measure; no unbounded sweep; document the numbers.
6. Fan-out code+security review; PR (`--base main`); merge.

## 7. Out of scope (PR-1)

- The **bridge** (NAN/LoRa long-range sideband) and **pair-to-activate / standby** UX — **PR-2**.
- **Clustered/constrained** temporal-ferrying (more realistic than RWP) — noted follow-up.
- Any airtime/collision cost on the ferrying path — the P0 airtime model is separate; here delivery is the
  connectivity ceiling, stated as such.
