# Airtime PR-1 — Engine Fidelity Implementation Plan (v2 — post plan-review)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dynamic engine trustworthy for mobile multi-hop — intra-contact multi-hop exchange, correct delivery timestamps, deterministic overlapping contacts — gated by a **falsifiable temporal-reachability oracle**, without regressing slice-1's percolation result and with no airtime model.

**Architecture:** Refine `engine.py` exchange (fixpoint rounds, single shared pool, real delivery-time stamping, canonical order) and record each settled contact as `(i, j, exit_time)`. Validate the engine against an **independent time-respecting reachability oracle** (the dynamic analog of slice-1's static union-find KAT): in the unbounded-budget / infinite-TTL limit, the set of nodes that end up holding a source's blob must equal the set reachable from the source via contacts whose exit times form a non-decreasing journey. A deliberately one-hop mutant engine must FAIL this gate (negative control). PR-2 (airtime model) builds on this.

**Tech Stack:** Python 3.11+, numpy, pytest (slice-1 venv at `sim/.venv`).

## Global Constraints
- Run: `cd sim && .venv/Scripts/python -m pytest -q`.
- **No airtime model in PR-1** — `budget.AirtimeBudget` unchanged; fidelity runs use unbounded budget except where a test deliberately meters/starves it.
- **Fidelity is gated by a TEMPORAL-REACHABILITY ORACLE, not a mean-field model.** No SI logistic, no β fitting.
- **Hard non-regression gate:** `tests/test_integration_percolation.py` stays green; refined engine reproduces `settle_static_fixpoint` in the `cap=∞/ttl=∞/α=0/t_setup=0/static` limit.
- Determinism unchanged (injected RNG, no module-global RNG — lint stays green). Engine/policies stay addressing-blind (lint stays green).
- `delivered_at ≥ created_at` holds **by construction at the engine**, never via a `metrics` clamp.

## File Structure
- Modify `sim/soup_sim/engine.py` — fixpoint `_exchange`, per-blob real delivery time, canonical episode order, **record `self.episodes` = list of `(i, j, exit_time)`**, optional `one_hop` test flag.
- Modify `sim/soup_sim/percolation.py` — add `temporal_reachable(episodes, source, n)`.
- Create `sim/soup_sim/analytics.py` — `expected_relative_speed`, `expected_contact_duration`, `analytic_meeting_rate_per_node`.
- Test `sim/tests/test_engine_fidelity.py` — contact-timing gate, temporal-oracle gate + negative control, multi-hop both-arms, non-regression.
- Test (extend) `sim/tests/test_engine.py` — refined-exchange + latency + overlap unit tests.

---

### Task 1: Analytics + REAL contact-timing sanity gate (runs the engine)

**Files:** Create `sim/soup_sim/analytics.py`; Test `sim/tests/test_engine_fidelity.py`
**Interfaces:**
- `expected_relative_speed(v) -> float` = `(4/pi)*v` (two equal-speed nodes, independent uniform directions).
- `expected_contact_duration(r, v_rel) -> float` = `pi*r/(2*v_rel)` (mean chord / relative speed).
- `analytic_meeting_rate_per_node(r, v_rel, n, area) -> float` = `2*r*v_rel*(n-1)/area`.

- [ ] **Step 1: Failing test that RUNS the RWP engine and compares to analytics (not a tautology)**
```python
# sim/tests/test_engine_fidelity.py
import numpy as np
from soup_sim.config import Config
from soup_sim.mobility import make_mobility
from soup_sim.analytics import expected_relative_speed, expected_contact_duration, analytic_meeting_rate_per_node

def _cfg(**kw):
    d = dict(n=300, width=200.0, height=200.0, radius=8.0, boundary="torus", mobility="rwp",
             speed_min=3.0, speed_max=3.0, dt=0.5, ttl=1e12, buffer_cap=10**9,
             throughput_ideal=1e12, alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0,
             warmup=0.0, measure_window=1.0, drain=0.0, n_messages=0, seen_margin=1e12, master_seed=1)
    d.update(kw); return Config(**d)

def test_contact_timing_matches_rwp_analytics_within_tolerance():
    # Run the engine over many seeds; measured mean contact duration AND meeting rate must
    # match the RWP analytic targets within a generous (order-of-magnitude-tight) tolerance.
    from soup_sim.engine import Engine
    from soup_sim.buffer import NodeBuffer
    from soup_sim.budget import AirtimeBudget
    durs, rates = [], []
    for s in range(5):
        c = _cfg(master_seed=s)
        mob = make_mobility(c, c.rng(0))
        bufs = [NodeBuffer(c.buffer_cap, 1e12, c.rng(3, i)) for i in range(c.n)]
        eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
        T = 40.0
        eng.run_until(T); eng.finalize()
        durs.append(eng.mean_contact_duration())
        rates.append(2.0 * len(eng.episodes) / (c.n * T))   # meetings per node per time
    v_rel = expected_relative_speed(3.0)
    exp_dur = expected_contact_duration(8.0, v_rel)
    exp_rate = analytic_meeting_rate_per_node(8.0, v_rel, 300, 200.0 * 200.0)
    assert 0.5 * exp_dur <= np.mean(durs) <= 2.0 * exp_dur, (np.mean(durs), exp_dur)
    assert 0.5 * exp_rate <= np.mean(rates) <= 2.0 * exp_rate, (np.mean(rates), exp_rate)
```
- [ ] **Step 2: Run, expect fail** (no `analytics.py`, and `engine.episodes` not yet recorded).
- [ ] **Step 3: Implement `analytics.py`** (the three formulas) and ensure Task-5's `engine.episodes` recording exists (do Task 5 Step 3 engine change first if building in order, or stub `episodes=[]` here and let Task 5 fill it — but the meeting-rate assertion needs it, so record episodes now: `self.episodes.append((i, j, end))` in `_settle`).
- [ ] **Step 4: Run, expect pass** (tune the 0.5×–2× band only if the RWP constant differs; band is deliberately loose because this is an order-of-magnitude sanity, not the headline gate).
- [ ] **Step 5: Commit** — `git commit -am "feat(sim): analytics + real RWP contact-timing sanity gate; record engine.episodes"`

---

### Task 2: Stamp deliveries at real delivery time (latency fix, engine-side)
*(unchanged from v1 — sound per review)*
**Files:** Modify `engine.py`; Test extend `test_engine.py`.
- Per-blob `deliver_t = max(now, blob.created_at)` computed inside `_exchange` (a real instant within the contact, not a metrics clamp); pass to `buffer.offer` and `on_deliver`.
- Test `test_delivery_time_never_before_created`: inject a blob with `created_at=3.0`, capture all `on_deliver` times, assert every `delivered_at ≥ created_at`. Commit.

### Task 3: Refined intra-contact exchange (fixpoint rounds, single shared pool)
*(unchanged from v1 — sound per review)*
**Files:** Modify `engine.py`; Test extend `test_engine.py`.
- `_exchange` iterates `(i→j),(j→i)` rounds while `remaining>0 and progressed`, consuming a single shared `remaining` pool (granted once; `t_setup` once per episode).
- Test `test_exchange_single_pool_over_rounds`: two distinct blobs, pool `k=1` ⇒ exactly one transfer total. Commit.

---

### Task 4: Deterministic overlapping contacts — REAL order-invariance test

**Files:** Modify `engine.py` (canonical order + a test hook); Test `test_engine.py`
**Interfaces:** `_process_step` processes candidate pairs in canonical `(entry, i, j)` order; add `Engine(..., _pair_order=None)` hook letting a test force a specific/permuted processing order to prove invariance.

- [ ] **Step 1: Failing test — delivered-set + timestamps invariant to pair processing order**
```python
def test_overlap_pair_order_invariance():
    # A-B and B-C in range, A-C out; A holds a blob. Result must be identical whether the engine
    # processes (A,B) before (B,C) or the reverse -> tests canonicalization, not just a fixed seed.
    import numpy as np
    from soup_sim.engine import Engine
    from soup_sim.buffer import NodeBuffer
    from soup_sim.budget import AirtimeBudget
    from soup_sim.blob import Blob
    from soup_sim.mobility import Mobility
    def run(order):
        c = _cfg(n=3, mobility="static", speed_min=0.0, speed_max=0.0, radius=10.0, dt=1.0)
        pos = np.array([[0., 50.], [9., 50.], [18., 50.]])
        mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
        bufs = [NodeBuffer(10**9, 1e12, c.rng(3, i)) for i in range(3)]
        rec = []
        eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1),
                     on_deliver=lambda n, b, t: rec.append((n, b.id, t)), _pair_order=order)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0); eng.run_until(3.0); eng.finalize()
        return sorted(rec)
    assert run("sorted") == run("reversed")   # canonical (entry,i,j) order makes these identical
```
- [ ] **Step 2: Run, expect fail** if order changes the result (or if `_pair_order` hook absent).
- [ ] **Step 3: Implement** the `(entry, i, j)` canonical sort in `_process_step` and the `_pair_order` hook (apply the requested permutation, then the engine re-canonicalizes — proving the result is order-independent).
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(sim): canonical episode order + real pair-order invariance test"`

---

### Task 5: TEMPORAL-REACHABILITY ORACLE gate (the keystone) + negative control

**Files:** Modify `percolation.py`; Test `test_engine_fidelity.py`; `engine.py` (`episodes` recording from Task 1; `one_hop` flag).
**Interfaces:** `temporal_reachable(episodes, source, n) -> set[int]` — `episodes` = list of `(i, j, exit_time)`; returns nodes reachable from `source` via a journey of non-decreasing exit times (process episodes in exit-time order; when either endpoint is already infected, infect both).

- [ ] **Step 1: Oracle correctness test (hand-known, BOTH directions — anchors falsifiability)**
```python
from soup_sim.percolation import temporal_reachable

def test_temporal_reachable_respects_time_order():
    # A-B at exit t=1, B-C at exit t=2 (>1) -> C reachable from A
    assert temporal_reachable([(0, 1, 1.0), (1, 2, 2.0)], source=0, n=3) == {0, 1, 2}
    # B-C at exit t=1, A-B at exit t=2 -> C NOT reachable (B-C happened before B was infected)
    assert temporal_reachable([(1, 2, 1.0), (0, 1, 2.0)], source=0, n=3) == {0, 1}
```
- [ ] **Step 2: Run, expect fail** (no `temporal_reachable`).
- [ ] **Step 3: Implement `temporal_reachable`**
```python
# append to percolation.py
def temporal_reachable(episodes, source, n):
    infected = {source}
    for (i, j, _t) in sorted(episodes, key=lambda e: e[2]):
        if i in infected or j in infected:
            infected.add(i); infected.add(j)
    return infected
```
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: ENGINE-MATCHES-ORACLE gate + one-hop negative control**
```python
def _run_spread(seed, one_hop=False):
    import numpy as np
    from soup_sim.engine import Engine
    from soup_sim.buffer import NodeBuffer
    from soup_sim.budget import AirtimeBudget
    from soup_sim.blob import Blob
    c = _cfg(n=120, width=140.0, height=140.0, radius=16.0, speed_min=2.0, speed_max=2.0,
             dt=0.5, master_seed=seed)
    mob = make_mobility(c, c.rng(0))
    bufs = [NodeBuffer(10**9, 1e12, c.rng(3, i)) for i in range(c.n)]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1),
                 on_deliver=lambda *_: None, one_hop=one_hop)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    delivered = {k for k in range(c.n) if bufs[k].has(0)}
    return delivered, set(eng.episodes and __import__('soup_sim.percolation', fromlist=['temporal_reachable']).temporal_reachable([(i, j, t) for (i, j, t) in eng.episodes], 0, c.n))

def test_engine_matches_temporal_reachability():
    for s in range(5):
        delivered, oracle = _run_spread(s, one_hop=False)
        assert delivered == oracle, (len(delivered), len(oracle))   # exchange tracks contacts exactly

def test_one_hop_mutant_fails_the_gate():
    # NEGATIVE CONTROL: an engine that only forwards the SOURCE's own blob (no multi-hop) must
    # deliver a STRICT SUBSET of temporal reachability -> proves the gate catches under-delivery.
    delivered, oracle = _run_spread(0, one_hop=True)
    assert delivered < oracle  # strict subset
```
- [ ] **Step 6: Implement** `engine.episodes` (done in Task 1) and the `one_hop` flag: when `one_hop=True`, a node may only offer blobs it ORIGINATED (track origin per blob id at inject), disabling forwarding. Run; the real engine must equal the oracle, the mutant must be a strict subset.
- [ ] **Step 7: Run, expect pass** (both tests, ≥5 seeds). If the real engine ≠ oracle, that is a fidelity FAILURE to fix in Tasks 2–4 (NOT a reason to loosen the oracle).
- [ ] **Step 8: Commit** — `git commit -am "feat(sim): temporal-reachability oracle gate (engine==reachability) + one-hop negative control"`

---

### Task 6: Multi-hop both-arms + non-regression GATE

**Files:** Test `test_engine_fidelity.py`; full suite.
- [ ] **Step 1: Tests**
  - **Positive (subsumed but explicit):** a linear courier ferries a blob from island {0,1} to island {2,3}; node 3 eventually holds it.
  - **Negative-1:** courier held out of range of the second island → node 3 never holds it.
  - **Negative-2 (airtime-starved):** bridge forms but `t_setup` exceeds every contact duration → nothing delivers.
  - **Non-regression:** refined engine, `static + cap=∞ + ttl=∞ + α=0 + t_setup=0` ⇒ delivered pairs == `same_component_pairs` (same family as the percolation oracle KAT).
- [ ] **Step 2–3:** write failing, implement scenarios (linear courier; reuse `same_component_pairs`).
- [ ] **Step 4: Run the FULL suite** — `cd sim && .venv/Scripts/python -m pytest -q` — all green **including `test_integration_percolation.py` unchanged** + lint/determinism.
- [ ] **Step 5: Commit** — `git commit -am "test(sim): multi-hop both-arms + non-regression gate; PR-1 engine fidelity complete"`

---

## Self-Review (v2)
- **Gate is now falsifiable:** the temporal-reachability oracle is an independent algorithm (mirrors the validated static union-find KAT), anchored by hand-known both-direction cases, with a one-hop mutant negative control that MUST fail. No mean-field SI, no β fitting, no unanchored tolerance.
- **Spec (PR-1 §2) coverage:** refined exchange → T3; engine-side latency → T2; overlap *order-invariance* (real) → T4; contact-timing gate (real, runs engine) → T1; fidelity gate → T5 (+ negative control); multi-hop both-arms → T6; non-regression (percolation + static-fixpoint limit) → T6. PR-2 items absent (correct).
- **Placeholders:** all tasks carry concrete code; no "calibrate/TODO". Type names (`temporal_reachable`, `expected_*`, `engine.episodes`, `one_hop`, `_pair_order`, `_exchange(i,j,k,now)`) consistent across tasks and slice-1 code.

## Execution Handoff
Plan v2 saved. Pending a targeted re-review of the revised gate (Tasks 1/4/5), then subagent-driven build → in-repo code review → PR-1 + `@codex review` (best-effort, 10-min) → CTO merge.
