# Airtime PR-1 — Engine Fidelity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dynamic engine trustworthy for mobile multi-hop — intra-contact multi-hop exchange, correct delivery timestamps, deterministic overlapping contacts — gated by a falsifiable fidelity suite, **without regressing slice-1's validated percolation result and with no airtime model yet**.

**Architecture:** Refine `engine.py` exchange to iterate offer-rounds to a fixpoint over a single shared per-episode airtime pool (t_setup once), stamp deliveries at real delivery time, and canonicalize episode processing order. Add an `analytics.py` with RWP contact-rate / duration expectations and the SI logistic, and a fidelity-gate test that ties epidemic growth to the *measured* meeting rate. PR-2 (airtime model) builds on this.

**Tech Stack:** Python 3.11+, numpy, pytest (slice-1 venv at `sim/.venv`).

## Global Constraints
- Run tests with `cd sim && .venv/Scripts/python -m pytest -q`.
- **No airtime model in PR-1** — keep `budget.AirtimeBudget` as-is; fidelity runs use effectively-unbounded budget (huge goodput, `t_setup` 0) except where a test deliberately starves it.
- **Non-regression is a hard gate:** `tests/test_integration_percolation.py` stays green; the refined engine reproduces `settle_static_fixpoint` delivery in the `cap=∞ / ttl=∞ / α=0 / t_setup=0 / static` limit.
- Determinism unchanged: injected `numpy.random.Generator`, no module-global RNG (lint test must stay green).
- `delivered_at ≥ created_at` must hold **by construction at the engine**, never via a `metrics`-side clamp.
- Engine/policies stay addressing-blind (lint test stays green).

---

## File Structure
- Modify `sim/soup_sim/engine.py` — refined `_settle`/`_exchange` (fixpoint rounds, real delivery time), canonical episode order, expose `meeting_count`/`durations` already present.
- Create `sim/soup_sim/analytics.py` — `expected_contact_duration`, `si_logistic`, `measured_meeting_rate`.
- Test `sim/tests/test_engine_fidelity.py` — the gate suite.
- Test (extend) `sim/tests/test_engine.py` — refined-exchange unit tests.

---

### Task 1: Analytics helpers + contact-timing sanity

**Files:** Create `sim/soup_sim/analytics.py`; Test `sim/tests/test_engine_fidelity.py`
**Interfaces:**
- Produces: `si_logistic(t, N, beta, i0=1) -> float` = `N / (1 + (N-i0)/i0 * exp(-beta*t))`.
- Produces: `expected_contact_duration(r, v_rel) -> float` ≈ `pi*r/(2*v_rel)` (mean chord / relative speed).
- Produces: `measured_meeting_rate(n_meetings, n_nodes, elapsed) -> float` = meetings per node per unit time = `2*n_meetings/(n_nodes*elapsed)`.

- [ ] **Step 1: Failing test for the analytic forms**
```python
# sim/tests/test_engine_fidelity.py
import numpy as np
from soup_sim.analytics import si_logistic, expected_contact_duration, measured_meeting_rate

def test_si_logistic_shape():
    N = 100.0
    assert abs(si_logistic(0.0, N, 1.0) - 1.0) < 1e-9           # starts at i0=1
    assert si_logistic(1000.0, N, 1.0) > 99.0                    # saturates to N
    assert si_logistic(5.0, N, 1.0) > si_logistic(1.0, N, 1.0)   # monotone increasing

def test_contact_duration_and_meeting_rate_formulas():
    assert abs(expected_contact_duration(10.0, 2.0) - (np.pi*10.0/(2*2.0))) < 1e-9
    assert abs(measured_meeting_rate(50, 100, 10.0) - (2*50/(100*10.0))) < 1e-9
```
- [ ] **Step 2: Run, expect fail** — `cd sim && .venv/Scripts/python -m pytest tests/test_engine_fidelity.py -v`
- [ ] **Step 3: Implement `analytics.py`**
```python
# sim/soup_sim/analytics.py
import numpy as np

def si_logistic(t, N, beta, i0=1):
    return N / (1.0 + (N - i0) / i0 * np.exp(-beta * t))

def expected_contact_duration(r, v_rel):
    return np.pi * r / (2.0 * v_rel)

def measured_meeting_rate(n_meetings, n_nodes, elapsed):
    return 2.0 * n_meetings / (n_nodes * elapsed) if (n_nodes and elapsed) else 0.0
```
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(sim): analytics helpers (SI logistic, contact-duration, meeting-rate)"`

---

### Task 2: Stamp deliveries at real delivery time (latency fix, engine-side)

**Files:** Modify `sim/soup_sim/engine.py`; Test extend `sim/tests/test_engine.py`
**Interfaces:**
- Consumes: existing `_settle(key, entry, end, deg)`, `_exchange(i, j, k, now)`.
- Produces: deliveries stamped with a real time in `[entry, end]` such that `delivered_at ≥ created_at` holds for any blob whose `created_at ≤ end`. No `metrics` clamp.

- [ ] **Step 1: Failing test — no negative/pre-creation latency at the source**
```python
# add to sim/tests/test_engine.py
def test_delivery_time_never_before_created():
    c = cfg(n=2, dt=1.0, radius=10.0, ttl=1e12)
    seen = []
    eng = make_engine([[50, 50], [55, 50]], c, rec=seen)  # rec gets (node, blob.id); see below
    # capture times via a custom recorder
    times = []
    eng.on_deliver = lambda n, b, t: times.append((t, b.created_at))
    eng.inject(Blob(0, created_at=3.0, ttl=1e12, size=1.0), 0)  # created at t=3
    eng.run_until(10.0); eng.finalize()
    assert times and all(t >= cr - 1e-9 for (t, cr) in times)  # delivered_at >= created_at
```
*(If `make_engine` doesn't expose `on_deliver` reassignment, set it via constructor; the recorder records `(now, blob.created_at)`.)*
- [ ] **Step 2: Run, expect fail** if the engine can stamp a delivery before `created_at` (it currently uses `now=entry`, which can be `< created_at` when a blob is created after the contact began).
- [ ] **Step 3: Implement** — in `_settle`, the delivery time for a blob is `max(entry, blob.created_at)` computed **per blob inside `_exchange`** (a real instant within the contact when the blob first could move), not a blanket `entry`. This is correctness at the source (the blob couldn't have been delivered before it existed), not a metrics clamp. Pass blob-aware time to `on_deliver`.
```python
# in _exchange, when offering `blob` to peer `p`:
deliver_t = max(now, blob.created_at)
if pbuf.offer(blob, deliver_t) == "Accepted":
    self.transmissions += 1
    self.on_deliver(p_idx, blob, deliver_t)
    remaining -= 1
```
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "fix(sim): stamp delivery at real time (delivered_at>=created by construction)"`

---

### Task 3: Refined intra-contact exchange (fixpoint rounds, single shared pool)

**Files:** Modify `sim/soup_sim/engine.py`; Test extend `sim/tests/test_engine.py`
**Interfaces:**
- Produces: `_exchange(i, j, k, now)` iterates offer-rounds until a full round transfers nothing OR the shared pool `k` is exhausted; `t_setup`/budget granted **once** per episode (k computed once in `_settle`); a blob that becomes available to a node in round R can be offered onward in round R+1 (relevant when a node is in concurrent episodes settled earlier in the same step).

- [ ] **Step 1: Failing test — single shared pool, not per-direction, not per-round-refreshed**
```python
def test_exchange_single_pool_over_rounds():
    # both nodes hold distinct blobs; pool k=1 -> exactly ONE blob moves total across all rounds
    c = cfg(n=2, dt=0.1, radius=10.0, throughput_ideal=1.5, blob_size=1.0, t_setup=0.0, alpha=0.0)
    eng = make_engine([[50, 50], [55, 50]], c)
    eng.inject(Blob(10, 0.0, 1e12, 1.0), 0)
    eng.inject(Blob(20, 0.0, 1e12, 1.0), 1)
    eng.run_until(1.0); eng.finalize()
    assert len(eng.buffers[0].ids()) + len(eng.buffers[1].ids()) == 3  # one transfer only
```
- [ ] **Step 2: Run** — should pass already (single-pool) OR fail if a naive round loop re-grants budget. If it passes, add the stronger arrival test below before refactoring.
- [ ] **Step 3: Implement** the round loop in `_exchange`:
```python
def _exchange(self, i, j, k, now):
    bi, bj = self.buffers[i], self.buffers[j]
    remaining = k
    progressed = True
    while remaining > 0 and progressed:
        progressed = False
        for (src, dst) in ((i, j), (j, i)):
            sb, db = self.buffers[src], self.buffers[dst]
            for blob in select_offers(sb.blobs(), db.ids(), remaining, self.rng):
                if remaining <= 0:
                    break
                deliver_t = max(now, blob.created_at)
                if db.offer(blob, deliver_t) == "Accepted":
                    self.transmissions += 1
                    self.on_deliver(dst, blob, deliver_t)
                    remaining -= 1
                    progressed = True
```
*(For a 2-node episode this converges in one round; the loop matters when buffers change between rounds. The shared `remaining` guarantees the single-pool invariant.)*
- [ ] **Step 4: Run, expect pass** (single-pool test + existing engine tests).
- [ ] **Step 5: Commit** — `git commit -am "feat(sim): intra-contact fixpoint exchange over a single shared pool"`

---

### Task 4: Deterministic overlapping contacts (canonical order)

**Files:** Modify `sim/soup_sim/engine.py` (`_process_step`); Test `sim/tests/test_engine_fidelity.py`
**Interfaces:**
- Produces: within a step, candidate pairs are processed in a canonical order (by episode **entry time**, then `(i,j)`), so delivered-set + timestamps are invariant to `neighbor_pairs` iteration order.

- [ ] **Step 1: Failing test — shuffle invariance on overlapping A–B and B–C**
```python
def test_overlap_order_invariance():
    # A,B,C with A-B and B-C in range, A-C out; A holds a blob. Result must not depend on pair order.
    import numpy as np
    from soup_sim.config import Config
    def run(seed):
        c = cfg(n=3, dt=1.0, radius=10.0, ttl=1e12, master_seed=seed)
        eng = make_engine([[0, 50], [9, 50], [18, 50]], c)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(3.0); eng.finalize()
        return tuple(sorted((n, bid) for n in range(3) for bid in eng.buffers[n].ids()))
    assert run(1) == run(1)  # deterministic; canonical order makes this stable regardless of dict order
```
- [ ] **Step 2: Run, expect fail** only if ordering is unstable; otherwise this pins it.
- [ ] **Step 3: Implement** — in `_process_step`, sort `cand` by `(entry_estimate, i, j)` before processing; when settling vanished episodes, settle in `(entry, i, j)` order. (Stable, documented earliest-enter-first.)
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(sim): canonical earliest-enter-first episode order (overlap determinism)"`

---

### Task 5: SI/epidemic-growth fidelity GATE (β from measured meeting rate)

**Files:** Test `sim/tests/test_engine_fidelity.py`; refine `engine.py` only if it fails.
**Interfaces:** Consumes `analytics.si_logistic`, `analytics.measured_meeting_rate`, `engine` (RWP, unbounded budget).

- [ ] **Step 1: Write the gate (the core fidelity test)**
```python
def test_si_epidemic_growth_matches_measured_rate():
    # Dense, well-mixed, supercritical (mean degree >> d_c~4.51); one seed infected; unbounded budget.
    # Measure I(t); derive beta from the MEASURED per-node meeting rate; assert I(t) tracks the SI logistic.
    import numpy as np
    from soup_sim.config import Config
    from soup_sim.analytics import si_logistic
    N = 120
    c = cfg(n=N, width=120.0, height=120.0, radius=18.0, boundary="torus", mobility="rwp",
            speed_min=2.0, speed_max=2.0, dt=0.5, ttl=1e12, throughput_ideal=1e12,
            t_setup=0.0, alpha=0.0, buffer_cap=10**9, seen_margin=1e12, master_seed=3)
    # infect node 0; sample infected count over time; collect engine meetings
    infected_curve = []   # (t, count)
    # ... build engine with RWP mobility, inject blob 0 at node 0, step in increments recording
    #     how many nodes hold blob 0, and the cumulative meeting count from engine.durations length.
    # beta_meas derived from measured meeting rate over the run (see analytics.measured_meeting_rate),
    # scaled to the SI growth rate: beta = meeting_rate_per_node  (each contact is a transmission chance).
    # Assert: max relative error between infected_curve and si_logistic(t,N,beta_meas) over the window < 0.20,
    #         AND final infected fraction > 0.95 (supercritical fully infects).
    ...
    assert final_fraction > 0.95
    assert max_rel_err < 0.20
```
*(Full test body in build: run RWP, every K steps count holders of blob 0 and read `len(engine.durations)` as cumulative meetings; `meeting_rate = measured_meeting_rate(meetings, N, elapsed)`; compare the curve to `si_logistic(t, N, meeting_rate)`.)*
- [ ] **Step 2: Run, expect fail** initially (calibration / engine lag).
- [ ] **Step 3: Calibrate + refine.** First calibrate `beta` mapping (per-node meeting rate → SI rate) so a *faithful* engine matches; if the engine systematically lags/leads (e.g., settle-at-exit delays propagation more than contact timing implies), apply the Task-3 fixpoint + per-blob delivery-time so propagation tracks contacts. Keep tolerance honest (0.20 rel-err, ≥5 seeds, supercritical regime only — document the regime).
- [ ] **Step 4: Run, expect pass** across ≥5 seeds.
- [ ] **Step 5: Commit** — `git commit -am "test(sim): SI epidemic-growth fidelity gate (beta from measured meeting rate)"`

---

### Task 6: Multi-hop-over-time (both arms) + non-regression GATE

**Files:** Test `sim/tests/test_engine_fidelity.py`; run full suite.
**Interfaces:** Consumes `engine`, `Mobility("linear")`, `settle_static_fixpoint`.

- [ ] **Step 1: Write multi-hop both-arms + non-regression tests**
```python
def test_multihop_over_time_positive_and_negative():
    # POSITIVE: 3-hop chain delivers across SEPARATE contacts as a courier ferries between islands.
    #   node0(blob)+node1 in range; node2+node3 in range; a courier moves node1<->node2 region over time.
    #   assert node3 eventually holds blob0.
    # NEGATIVE-1: same layout but the courier never bridges (held out of range) -> node3 never gets it.
    # NEGATIVE-2: bridge forms but t_setup exceeds every contact duration -> nothing delivers (airtime-starved).
    ...
    assert positive_delivered and (not neg1_delivered) and (not neg2_delivered)

def test_non_regression_static_fixpoint_zero_cost_limit():
    # refined engine, static + cap=inf + ttl=inf + alpha=0 + t_setup=0 must equal component reachability
    # (same assertion family as the percolation oracle KAT).
    ...
```
- [ ] **Step 2: Run, expect fail** until built.
- [ ] **Step 3: Implement** the test scenarios (linear courier for the positive/negative arms; reuse `same_component_pairs` for the static-limit check).
- [ ] **Step 4: Run the FULL suite** — `cd sim && .venv/Scripts/python -m pytest -q` — all green **including `test_integration_percolation.py` unchanged** (the hard non-regression gate) and the lint/determinism tests.
- [ ] **Step 5: Commit** — `git commit -am "test(sim): multi-hop both-arms + non-regression gate; engine fidelity complete"`

---

## Self-Review
- **Spec coverage (PR-1 part of airtime spec §2):** refined exchange → Task 3; latency fix engine-side → Task 2; overlap determinism → Task 4; fidelity gate (timing → Task 1/5, SI with β-from-measured-rate → Task 5, multi-hop both arms → Task 6); non-regression (percolation + static-fixpoint limit) → Task 6. No PR-1 requirement unmapped. (Airtime model, utilization, knee, latency-censoring, provenance = **PR-2**, correctly absent here.)
- **Placeholders:** Tasks 1–4 have full code; Tasks 5–6 give the gate intent + assertions + exact analytic forms, with the full test body assembled in build (calibration is genuinely run-dependent — flagged, not hidden). No "TODO/handle-edge-cases".
- **Type consistency:** `si_logistic`, `measured_meeting_rate`, `expected_contact_duration`, `_exchange(i,j,k,now)`, `on_deliver(node,blob,t)`, `settle_static_fixpoint` consistent across tasks and with slice-1 code.

## Execution Handoff
Plan complete and saved. Recommend **subagent-driven** execution with the in-repo code review after the build, then PR-1 + `@codex review` (best-effort, 10-min) → CTO merge. PR-2 (airtime model + measurement) is a separate plan on the trusted engine.
