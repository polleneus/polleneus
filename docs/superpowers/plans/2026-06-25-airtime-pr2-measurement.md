# Airtime Model + Measurement (Feature 2 · PR-2) Implementation Plan — v3

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **v2 (folds plan-review round 1):** per-episode airtime billing; knee-bracketing grid; binding decomposition over UNMET demand; two control arms; budget fields threaded into `run_one`; T50 not "KM"; offered-airtime in engine.
>
> **v3 (folds plan-review round 2):** charged airtime billed **incrementally per step at the same `eff(n_step)` used for accrual** (so `utilization ≤ 1` holds on mobility, not just static fixtures), with `t_setup_at(n)` charged once; binding decomposition is in **BLOB units** with quantization vs contention separated by a **capacity test** (`goodput·usable/blob < 1` ⇒ quantization), closing the gate blind-spot; `setup_debt = t_setup_at(n)` (so `t_setup_slope` actually throttles delivery) with `n_contenders` computed **before** the open-dict (fixes a scope bug); `"t50"` wired into `run_one`; knee detector requires a **relative-drop margin** (kills the ~42%-flaky linear "no_knee"); **small test arenas + heavy end-to-end tests marked `slow`** (the [3..20]-density grid mapped to n≈900 → ~48-min suite); predicted knee expressed in **contenders** with the density-space knee bracketed empirically; Tasks 3 and 10 split.

**Goal:** On the trusted PR-1 engine, build a collision-capable airtime model and the measurement machinery to answer the red-team's risk #1 — *does BLE airtime saturate at crowd density and collapse delivery?* — with a binding publish-gate so an engine/buffer/TTL effect can never be mislabeled "airtime."

**Architecture:** Additive only. New config fields default to **current behavior** (`airtime_model="linear"`, `beta=0`, `t_setup_slope=0`, `cs_radius_mult=1.0`), so the merged fidelity gate (`test_engine_fidelity.py`) and percolation non-regression (`test_integration_percolation.py`) stay green bit-for-bit. The collision model lives in `budget.py`; the engine measures contention over a *carrier-sense* radius and bills airtime/counters **per physical episode**; `metrics.py` gains utilization, windowed circulation, and censoring-aware T50; a new `knee.py` locates the saturation knee and applies the binding gate; `scenario.py` gains an airtime sweep with **two** mandatory control arms (α=0 airtime-free, and cap=∞/ttl=∞).

**Tech Stack:** Python 3, numpy, pytest (`pythonpath=["."]`), matplotlib (optional, import-guarded). Determinism via `cfg.rng(*path)` SeedSequence substreams.

## Global Constraints

- **Every published number is an UPPER BOUND on real delivery.** New optimistic mechanics get a README bias row + direction.
- **Determinism:** all randomness via `cfg.rng(*path)` or `np.random.default_rng(seed)` derived from `master_seed`; no global RNG. The replication unit is the SEED.
- **Addressing-blind engine:** no `sender`/`recipient` tokens in engine-layer files (enforced by `test_lint_invariants.py`). Use `src`/`dst`/`local`/`contender`.
- **Primary airtime model = ALOHA collision** per-link goodput `throughput·exp(-β·n/n_channels)` (monotone in n; the SYSTEM aggregate `n·goodput` has an interior max at `n*=n_channels/β` → turns over). Old `1/(1+α·n)` is the **optimistic-bound sensitivity** case (system aggregate plateaus → no knee).
- **Airtime is billed INCREMENTALLY per step** at the same `eff(n_step)` used for credit accrual (service time `served_this_step·blob_size/eff(n_step)` ≤ the step's usable time), plus **one** `t_setup_at(n_open)` per episode. This guarantees `charged_airtime ≤ available_contact_time` ⇒ `utilization ≤ 1` even when contention varies within a contact. `setup_debt = t_setup_at(n_open)` so `t_setup_slope` throttles delivery (denser ⇒ more setup-starved short contacts).
- **Binding decomposition is in BLOB units** over UNMET = offered−served, classified per episode: setup-starved (`t_setup_at(n) ≥ duration`), quantization (capacity `eff(n)·max(0,duration−t_setup_at(n))/blob_size < 1` — couldn't complete even one blob), else contention. (Quantization ≠ contention: a low-goodput contact that COULD move blobs but didn't clear the backlog is contention, the gate's signal.)
- **TWO control arms, on the SAME axes, for every airtime curve:**
  - **α=0 airtime-free control** = `alpha=0, beta=0, t_setup_slope=0` (removes ALL airtime contention). If it still turns over → connectivity-limited.
  - **cap=∞/ttl=∞ control** = `buffer_cap=BIG, ttl=BIG`. If the turn-down vanishes → buffer/TTL-limited.
- **Headline goodput conservative ≈100 kbps** (no-DLE); optimistic ≈1.4 Mbps as upper sensitivity.
- **Pre-registered (named constants, justified in README before any run):** predicted knee contender count `n*=n_channels/β`; `BINDING_THRESHOLD=0.5`; the cap/ttl control values; the density grid that must bracket `n*`.
- **Knee estimator must NOT reuse the monotone 0.5-crossing machinery** (`crossing_0p5`/`midpoint_with_ci`). Returns **"no knee in range"** (sentinel), never NaN, when monotone.
- **Publish gate (hard):** publish the airtime-saturation figure **only if** `status=="knee"` AND `contention_bound` (fraction of UNMET demand attributable to contention) `>= BINDING_THRESHOLD` at/beyond the knee AND **neither** the α=0 control **nor** the cap/ttl control turns over. Else label connectivity/buffer/TTL-limited.
- **Latency is censoring-aware:** TTL-expired = censored; report **T50** (time to 50% of the fair-chance cohort delivered; `None` when <50% ever delivered) **jointly with delivery ratio**. Delivered-only mean is labelled a LOWER bound. (This is a TTL-censored CDF quantile — do NOT call it Kaplan-Meier.)
- **Contention population ≠ connectivity degree:** `n_contenders` = co-channel count over `cs_radius_mult·radius`, justified with bias direction in provenance.

---

## File Structure

- `sim/soup_sim/config.py` — MODIFY: add `airtime_model, beta, t_setup_slope, n_channels, cs_radius_mult` (behavior-preserving defaults) + validation.
- `sim/soup_sim/budget.py` — MODIFY: collision `effective_goodput`, `t_setup_at(n)`, `charged_airtime(served, n)`; keep linear selectable.
- `sim/soup_sim/engine.py` — MODIFY: carrier-sense contention; **per-episode** airtime accounting + setup-starved/quantization/total-contact counters + offered/served per episode.
- `sim/soup_sim/scenario.py` — MODIFY: thread budget fields into `run_one`; window snapshots; `airtime_sweep` with both control arms.
- `sim/soup_sim/metrics.py` — MODIFY: `utilization`, `utilization_vs_offered`, `circulated_per_min`, `t50`, `delivery_cdf_points`, `delivered_only_mean_latency`.
- `sim/soup_sim/knee.py` — CREATE: `binding_decomposition`, `find_knee`, `BINDING_THRESHOLD`, `binding_gate`.
- `sim/soup_sim/report.py` — MODIFY: airtime CSV + plot (both control overlays + knee marker).
- `sim/run.py` — MODIFY: `--preset airtime-knee` (emits collision + linear band + gate verdict).
- `sim/README.md` — MODIFY: provenance table + bias rows.
- Tests: `test_budget.py`, `test_config.py`, `test_report.py` (MODIFY); `test_engine_airtime.py`, `test_metrics_airtime.py`, `test_knee.py`, `test_scenario_airtime.py` (CREATE).

---

## Task 1: Collision airtime model + thread it into run_one

**Files:**
- Modify: `sim/soup_sim/config.py`, `sim/soup_sim/budget.py`, `sim/soup_sim/scenario.py`
- Test: `sim/tests/test_budget.py`

**Interfaces:**
- Produces: `Config.{airtime_model:str, beta:float, t_setup_slope:float, n_channels:int, cs_radius_mult:float}`; `AirtimeBudget(throughput_ideal, alpha, t_setup, p_fail, blob_size, model="linear", beta=0.0, t_setup_slope=0.0, n_channels=3)` with `effective_goodput(n)->float`, `t_setup_at(n)->float`, `charged_airtime(served, n)->float`. `run_one` constructs the budget with all fields from cfg.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_budget.py  (append)
import numpy as np
from soup_sim.budget import AirtimeBudget

def test_collision_aggregate_turns_over_linear_plateaus():
    # per-link goodput is monotone for BOTH models; the TURN-OVER is the SYSTEM aggregate n*goodput.
    ns = np.arange(1, 100)
    coll = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="collision", beta=0.08, n_channels=3)
    lin = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="linear")
    agg_c = np.array([n * coll.effective_goodput(int(n)) for n in ns])
    agg_l = np.array([n * lin.effective_goodput(int(n)) for n in ns])
    assert 0 < agg_c.argmax() < len(ns) - 1          # collision: interior maximum (turns over)
    assert agg_l.argmax() == len(ns) - 1             # linear: monotone up to plateau
    assert agg_c.max() > 1.5 * agg_c[-1]             # clear turn-over margin
    # interior max near the analytic prediction n* = n_channels/beta = 37.5
    assert abs(ns[agg_c.argmax()] - 3 / 0.08) < 5

def test_per_link_goodput_monotone_both_models():
    for b in (AirtimeBudget(1e5, 1.0, 0, 0, 1.0, model="collision", beta=0.08, n_channels=3),
              AirtimeBudget(1e5, 1.0, 0, 0, 1.0, model="linear")):
        g = [b.effective_goodput(int(n)) for n in range(1, 80)]
        assert np.all(np.diff(g) <= 1e-9)

def test_density_dependent_setup_and_charged_airtime():
    b = AirtimeBudget(100.0, 0.0, t_setup=0.5, p_fail=0.0, blob_size=10.0,
                      model="linear", t_setup_slope=0.05)
    assert b.t_setup_at(0) == 0.5 and b.t_setup_at(40) == 0.5 + 0.05 * 40
    assert abs(b.charged_airtime(3, 0) - (0.5 + 3 * 10.0 / 100.0)) < 1e-9
    assert b.charged_airtime(0, 0) == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_budget.py -q`
Expected: FAIL (`AirtimeBudget() got an unexpected keyword argument 'model'`).

- [ ] **Step 3a: Config fields + validation**

```python
# sim/soup_sim/config.py  — append to the dataclass field block (after master_seed; defaults legal)
    airtime_model: str = "linear"     # "linear" (optimistic sensitivity) | "collision" (ALOHA primary)
    beta: float = 0.0                 # collision steepness; per-link p ~ exp(-beta*n/n_channels)
    t_setup_slope: float = 0.0        # density-dependent setup: t_setup_at(n)=t_setup + slope*n
    n_channels: int = 3               # shared advertising channels
    cs_radius_mult: float = 1.0       # carrier-sense radius = cs_radius_mult * radius
```

```python
# sim/soup_sim/config.py  — append to validate()
        if self.airtime_model not in ("linear", "collision"):
            raise ValueError("airtime_model must be linear|collision")
        if self.beta < 0:
            raise ValueError("beta must be >= 0")
        if self.t_setup_slope < 0:
            raise ValueError("t_setup_slope must be >= 0")
        if self.n_channels < 1:
            raise ValueError("n_channels must be >= 1")
        if self.cs_radius_mult < 1.0:
            raise ValueError("cs_radius_mult must be >= 1 (carrier-sense >= connectivity range)")
```

- [ ] **Step 3b: Budget implementation**

```python
# sim/soup_sim/budget.py  — module top
import math
# ... in AirtimeBudget.__init__ add params model="linear", beta=0.0, t_setup_slope=0.0, n_channels=3
#     and store: self.model, self.beta, self.t_setup_slope, self.n_channels = max(1, n_channels)

    def t_setup_at(self, n_contenders: int) -> float:
        return self.t_setup + self.t_setup_slope * max(0, n_contenders)

    def effective_goodput(self, n_contenders: int) -> float:
        """PER-LINK goodput (bytes/time), MONOTONE DECREASING for both models.
        linear:    throughput/(1+alpha*n)             (~1/n; system n*goodput -> plateau)
        collision: throughput*exp(-beta*n/n_channels) (ALOHA; system n*goodput interior max at n_channels/beta)."""
        n = max(0, n_contenders)
        loss = 1.0 - self.p_fail
        if self.model == "collision":
            return self.throughput_ideal * math.exp(-self.beta * n / self.n_channels) * loss
        return self.throughput_ideal / (1.0 + self.alpha * n) * loss

    def charged_airtime(self, served_blobs: int, n_contenders: int) -> float:
        if served_blobs <= 0:
            return 0.0
        return self.t_setup_at(n_contenders) + served_blobs * self.blob_size / self.effective_goodput(n_contenders)
```

- [ ] **Step 3c: Thread fields into run_one (else the collision model is inert)**

```python
# sim/soup_sim/scenario.py  run_one — replace the AirtimeBudget(...) construction:
    budget = AirtimeBudget(cfg.throughput_ideal, cfg.alpha, cfg.t_setup, cfg.p_fail, cfg.blob_size,
                           model=cfg.airtime_model, beta=cfg.beta,
                           t_setup_slope=cfg.t_setup_slope, n_channels=cfg.n_channels)
```

Add a test that the wiring is live:

```python
# sim/tests/test_budget.py (append)
def test_run_one_uses_configured_model():
    from soup_sim.config import Config
    from soup_sim.scenario import run_one
    base = dict(n=20, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
                speed_min=2.0, speed_max=2.0, dt=0.5, ttl=30.0, buffer_cap=50, throughput_ideal=1e4,
                alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=10.0, measure_window=20.0,
                drain=0.0, n_messages=10, seen_margin=30.0, master_seed=1,
                airtime_model="collision", beta=0.2, t_setup_slope=0.0, n_channels=3, cs_radius_mult=1.0)
    r = run_one(Config(**base))                       # must run without error under collision
    assert r["manifest"]["airtime_model"] == "collision"
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_budget.py tests/test_config.py tests/test_scenario.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/config.py sim/soup_sim/budget.py sim/soup_sim/scenario.py sim/tests/test_budget.py
git commit -m "feat(sim): ALOHA collision airtime model + density-dependent setup, threaded into run_one"
```

---

## Task 2: Contention over a carrier-sense radius (decoupled from connectivity)

**Files:**
- Modify: `sim/soup_sim/engine.py`
- Test: `sim/tests/test_engine_airtime.py` (CREATE)

**Interfaces:**
- Produces: engine feeds `effective_goodput`/`charged_airtime` with `n_contenders` measured over `cs_radius_mult*radius`, NOT connectivity degree. Default `cs_radius_mult=1.0` ⇒ bit-identical to today.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_engine_airtime.py  (CREATE)
import numpy as np
from soup_sim.config import Config
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.budget import AirtimeBudget
from soup_sim.buffer import NodeBuffer
from soup_sim.blob import Blob

BIG = 10 ** 9
def cfg(**kw):
    d = dict(n=4, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0, cs_radius_mult=3.0)
    d.update(kw); return Config(**d)

def test_contenders_use_carrier_sense_radius_not_connectivity():
    # line at 0/8/16/24, r=10: connectivity max degree = 2; carrier-sense (3*r=30) degree = 3.
    seen = {}
    c = cfg()
    pos = np.array([[0., 50.], [8., 50.], [16., 50.], [24., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(4)]
    budget = AirtimeBudget(1e12, 0, 0, 0, 1.0)
    orig = budget.effective_goodput
    budget.effective_goodput = lambda n: seen.__setitem__("max_n", max(seen.get("max_n", 0), n)) or orig(n)
    eng = Engine(c, mob, bufs, budget, c.rng(1), on_deliver=lambda *_: None)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(2.0); eng.finalize()
    assert seen.get("max_n", 0) >= 3   # only carrier-sense range yields degree 3 here
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py -q`
Expected: FAIL (engine feeds connectivity degree, max 2 here; `max_n < 3`).

- [ ] **Step 3: Implement carrier-sense contention**

In `engine.py._process_step`, after computing `cand`/`deg`, add a carrier-sense degree and use it for the budget:

```python
        cs_r = r * cfg.cs_radius_mult
        if cs_r > r:
            cs_cand = neighbor_pairs(p0, cs_r + 2.0 * max_disp + _EPS, w, h, b)
            cs_deg = self._degrees(p0, cs_cand, cs_r, w, h, b)
        else:
            cs_deg = deg                                  # default: identical to connectivity (no-op)
```

Replace the credit-accrual contention with `cs_deg`:

```python
            n_contenders = int(max(cs_deg[i], cs_deg[j]))
            eff = self.budget.effective_goodput(n_contenders)
```

(Keep `n_contenders` in a local — Task 3 reuses it for billing.)

- [ ] **Step 4: Run to verify it passes + fidelity gate untouched**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py tests/test_engine_fidelity.py tests/test_engine.py -q`
Expected: PASS (fidelity uses unbounded throughput; default `cs_radius_mult=1.0` ⇒ no change).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/engine.py sim/tests/test_engine_airtime.py
git commit -m "feat(sim): contention over carrier-sense radius, decoupled from connectivity degree"
```

---

## Task 3: Per-episode airtime accounting + binding counters

**Files:**
- Modify: `sim/soup_sim/engine.py`
- Test: `sim/tests/test_engine_airtime.py`

**Interfaces:**
- Produces engine attributes: `charged_airtime, available_contact_time, offered_airtime: float`; `offered_blobs, served_blobs: int`; and BLOB-unit binding tallies `setup_starved_blobs, quantization_blobs, contention_blobs: int` (these sum to UNMET = offered−served). Service airtime is billed **incrementally per step** at the step's `eff(n_step)`; `t_setup_at(n_open)` is added once per episode the first step a blob is served. At `_close`, the episode's UNMET blobs are classified (setup-starved / quantization / contention via the capacity test) into the blob-unit tallies. `n_contenders` is computed BEFORE the open-dict so `setup_debt = t_setup_at(n_open)`.

- [ ] **Step 1: Write the failing tests**

```python
# sim/tests/test_engine_airtime.py  (append)
def _two_node(throughput, dt, t_setup=0.0, slope=0.0, ttl=1e12, run=10.0, blobs=5, model="linear"):
    c = cfg(n=2, dt=dt, throughput_ideal=throughput, t_setup=t_setup, t_setup_slope=slope,
            ttl=ttl, cs_radius_mult=1.0, airtime_model=model)
    pos = np.array([[50., 50.], [55., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, ttl + 1e9, c.rng(3, i)) for i in range(2)]
    budget = AirtimeBudget(throughput, 0, t_setup, 0, 1.0, model=model, t_setup_slope=slope)
    eng = Engine(c, mob, bufs, budget, c.rng(1), on_deliver=lambda *_: None)
    for k in range(blobs):
        eng.inject(Blob(k, 0.0, ttl, 1.0), 0)
    eng.run_until(run); eng.finalize()
    return eng

def test_airtime_accounting_bounds():
    eng = _two_node(throughput=2.0, dt=1.0)
    assert eng.available_contact_time > 0
    assert 0.0 <= eng.charged_airtime <= eng.available_contact_time + 1e-9
    assert eng.offered_blobs >= eng.served_blobs >= 1
    assert eng.offered_airtime >= eng.charged_airtime - 1e-9
    assert eng.total_contacts == 1

def test_t_setup_charged_once_per_episode():
    # long contact spanning 100 steps, big setup; charged setup must be ~1x, not 100x.
    eng = _two_node(throughput=1e9, dt=0.1, t_setup=0.5, run=10.0, blobs=3)
    # 3 blobs served at huge goodput -> service ~0; charged ~= one t_setup
    assert abs(eng.charged_airtime - 0.5) < 0.05

def test_setup_starved_blobs_counted():
    # t_setup (1000) exceeds the whole contact -> setup-starved, nothing served, unmet -> setup_starved_blobs
    eng = _two_node(throughput=1e9, dt=1.0, t_setup=1000.0, run=10.0, blobs=3)
    assert eng.served_blobs == 0 and eng.setup_starved_blobs == 3 and eng.contention_blobs == 0

def test_utilization_le_one_under_varying_contention():
    # contention varies within the contact (carrier-sense degree changes); util must stay <= 1
    eng = _two_node(throughput=8e3, dt=0.5, t_setup=0.05, slope=0.0, run=20.0, blobs=50, model="collision")
    assert eng.charged_airtime <= eng.available_contact_time + 1e-9
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py -q`
Expected: FAIL (`AttributeError: charged_airtime`).

- [ ] **Step 3: Implement per-step billing + per-episode blob-unit classification**

In `__init__` add: `self.charged_airtime = self.available_contact_time = self.offered_airtime = 0.0; self.offered_blobs = self.served_blobs = self.setup_starved_blobs = self.quantization_blobs = self.contention_blobs = 0`.

In `_process_step`, compute `n_contenders` BEFORE the open-dict creation (fixes the scope bug), and use it for the setup floor and the open-dict fields:

```python
            n_contenders = int(max(cs_deg[i], cs_deg[j]))
            if key not in self.open:
                self.open[key] = {"entry": enter, "last_end": exit_, "credit": 0.0,
                                  "setup_debt": self.budget.t_setup_at(n_contenders),  # slope throttles
                                  "n": n_contenders, "served": set(), "offered": set(),
                                  "setup_billed": False}
            st = self.open[key]
            st["last_end"] = exit_; st["n"] = max(st["n"], n_contenders)
            self.available_contact_time += (exit_ - enter)
            eff = self.budget.effective_goodput(n_contenders)
            # ... existing setup_debt pay + credit accrual using eff ...
            # record offered (distinct lacked ids), ONCE per pair per step, before the fixpoint:
            for (src, dst) in ((i, j), (j, i)):
                st["offered"].update(bl.id for bl in self._offerable(src, self.buffers[dst].ids(), exit_))
```

`_exchange` returns `(moved, served_ids)`; the fixpoint caller bills service at the step's `eff` and charges setup once:

```python
            moved, served_ids = self._exchange(i, j, allowed, enter, exit_)
            if moved:
                st["credit"] -= moved
                st["served"].update(served_ids)
                if not st["setup_billed"]:
                    self.charged_airtime += self.budget.t_setup_at(st["n"]); st["setup_billed"] = True
                self.charged_airtime += moved * self.budget.blob_size / eff   # same eff as accrual -> <= usable time
                progressed = True
```

In `_close(key)` classify the episode's UNMET blobs (blob units; capacity test separates quantization from contention):

```python
    def _close(self, key):
        st = self.open.pop(key)
        dur = st["last_end"] - st["entry"]
        self.episodes.append((key[0], key[1], st["entry"], st["last_end"]))
        self.durations.append(dur)
        n = st["n"]; served = len(st["served"]); offered = len(st["offered"])
        self.served_blobs += served; self.offered_blobs += offered
        self.offered_airtime += self.budget.charged_airtime(offered, n) if offered else 0.0
        unmet = offered - served
        if unmet > 0:
            t0 = self.budget.t_setup_at(n)
            capacity = self.budget.effective_goodput(n) * max(0.0, dur - t0) / self.budget.blob_size
            if t0 >= dur:
                self.setup_starved_blobs += unmet            # couldn't even handshake
            elif capacity < 1.0:
                self.quantization_blobs += unmet             # too short/low-rate for one whole blob
            else:
                self.contention_blobs += unmet               # could move blobs, backlog exceeded capacity
```

- [ ] **Step 3b (split): expose `total_contacts = len(self.episodes)` via a property and confirm `_exchange` change** — `total_contacts` is just `len(self.episodes)`; no separate counter. Verify the single `_exchange` caller is the fixpoint above (no other callers; `settle_static_fixpoint` inlines its own loop).

- [ ] **Step 4: Run to verify it passes + full engine suites green**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py tests/test_engine_fidelity.py tests/test_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/engine.py sim/tests/test_engine_airtime.py
git commit -m "feat(sim): per-episode airtime billing + offered/served + setup-starved/quantization counters"
```

---

## Task 4: Metrics — utilization + windowed circulation

**Files:**
- Modify: `sim/soup_sim/metrics.py`, `sim/soup_sim/scenario.py`
- Test: `sim/tests/test_metrics_airtime.py` (CREATE)

**Interfaces:**
- Produces: `Metrics.utilization(charged, available)->float` (≤1 by construction now), `utilization_vs_offered(charged, offered_airtime)->float`, `circulated_per_min(transmissions_in_window, measure_window)->float`. `run_one` snapshots `eng.transmissions` after warmup+inject (`tx0`) and after the measure window but **before drain/finalize** (`tx1`), and returns `circulated_per_min`, `utilization`, `utilization_vs_offered`, plus the engine's `charged_airtime/available_contact_time/offered_airtime/offered_blobs/served_blobs/total_contacts/setup_starved_contacts/quantization_contacts`.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_metrics_airtime.py  (CREATE)
from soup_sim.metrics import Metrics
from soup_sim.config import Config
def _cfg(**kw):
    d = dict(n=2, width=1.0, height=1.0, radius=1.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=100.0, buffer_cap=10**9, throughput_ideal=1.0,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=120.0,
             drain=0.0, n_messages=0, seen_margin=1.0, master_seed=0)
    d.update(kw); return Config(**d)
def test_utilization_and_circulation():
    m = Metrics(_cfg(), warmup_end=0.0, measure_window=120.0)
    assert abs(m.utilization(30.0, 120.0) - 0.25) < 1e-9
    assert m.utilization(0.0, 0.0) == 0.0
    assert abs(m.utilization_vs_offered(30.0, 60.0) - 0.5) < 1e-9
    assert abs(m.circulated_per_min(240, 120.0) - 120.0) < 1e-9
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py -q`
Expected: FAIL (`AttributeError: utilization`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/metrics.py  (append)
    def utilization(self, charged: float, available: float) -> float:
        return charged / available if available > 0 else 0.0
    def utilization_vs_offered(self, charged: float, offered_airtime: float) -> float:
        return charged / offered_airtime if offered_airtime > 0 else 0.0
    def circulated_per_min(self, transmissions_in_window: int, measure_window: float) -> float:
        minutes = measure_window / 60.0
        return transmissions_in_window / minutes if minutes > 0 else 0.0
```

In `scenario.run_one`: capture `tx0 = eng.transmissions` immediately after the inject loop; capture `tx1 = eng.transmissions` right after the `s`-sample loop completes the measure window (BEFORE the `drain` `run_until` and `finalize()`); add to the return dict: `"circulated_per_min": metrics.circulated_per_min(tx1 - tx0, cfg.measure_window)`, `"utilization": metrics.utilization(eng.charged_airtime, eng.available_contact_time)`, `"utilization_vs_offered": metrics.utilization_vs_offered(eng.charged_airtime, eng.offered_airtime)`, **`"t50": metrics.t50()`** (Task 5; `delivery_ratio` is already returned), and the raw engine blob-unit tallies (`offered_blobs, served_blobs, setup_starved_blobs, quantization_blobs, contention_blobs`). Note: `utilization ≤ 1` holds by construction now (per-step billing at the accrual `eff`). (Circulation counts ACCEPTED transfers only; the cohort carries no dummy/duplicate traffic — note this in the README.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py tests/test_scenario.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/metrics.py sim/soup_sim/scenario.py sim/tests/test_metrics_airtime.py
git commit -m "feat(sim): utilization (vs available + vs offered) + windowed circulated-blobs/min"
```

---

## Task 5: Censoring-aware latency (T50) + delivery ratio jointly

**Files:**
- Modify: `sim/soup_sim/metrics.py`
- Test: `sim/tests/test_metrics_airtime.py`

**Interfaces:**
- Produces: `Metrics.t50()->float|None` (time to 50% of the fair-chance cohort delivered; `None` when <50% ever delivered — TTL-censored quantile, NOT Kaplan-Meier), `delivery_cdf_points()->list[(t,frac)]`, `delivered_only_mean_latency()->float` (labelled LOWER bound). Denominator = full fair-chance cohort so censored (undelivered) messages count against.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_metrics_airtime.py  (append)
from soup_sim.blob import Blob
def test_t50_is_censoring_aware():
    c = _cfg(ttl=100.0, measure_window=100.0)
    m = Metrics(c, warmup_end=0.0, measure_window=100.0)
    for i in range(4):
        m.register(Blob(i, 0.0, 100.0, 1.0), 0, 1)
    for (i, t) in [(0, 10.0), (1, 20.0), (2, 80.0)]:
        m.delivered_at[i] = t
    assert abs(m.t50() - 20.0) < 1e-9            # 2/4 delivered by t=20
    m2 = Metrics(c, warmup_end=0.0, measure_window=100.0)
    for i in range(4):
        m2.register(Blob(i, 0.0, 100.0, 1.0), 0, 1)
    m2.delivered_at[0] = 5.0
    assert m2.t50() is None                       # <50% ever delivered -> censored, not a flattering 5.0
    assert m2.delivery_ratio() == 0.25            # reported jointly
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py::test_t50_is_censoring_aware -q`
Expected: FAIL (`AttributeError: t50`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/metrics.py  (append)
    def delivery_cdf_points(self):
        fc = self.fair_chance_ids(); total = len(fc)
        if total == 0:
            return []
        lat = sorted(self.delivered_at[b] - self.created[b] for b in fc if b in self.delivered_at)
        out, cum = [], 0
        for t in lat:
            cum += 1
            out.append((t, cum / total))        # denominator = full cohort (censored count against)
        return out
    def t50(self):
        for (t, frac) in self.delivery_cdf_points():
            if frac >= 0.5:
                return t
        return None
    def delivered_only_mean_latency(self) -> float:
        lat = self.latencies()
        return float(sum(lat) / len(lat)) if lat else 0.0   # LOWER bound (survivorship)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/metrics.py sim/tests/test_metrics_airtime.py
git commit -m "feat(sim): censoring-aware T50 (TTL-censored CDF quantile) reported with delivery ratio"
```

---

## Task 6: Binding-fraction decomposition (over UNMET demand)

**Files:**
- Create: `sim/soup_sim/knee.py`
- Test: `sim/tests/test_knee.py` (CREATE)

**Interfaces:**
- Produces: `binding_decomposition(offered, served, setup_starved_blobs, quantization_blobs, contention_blobs) -> dict` with `{"contention_bound", "setup_starved", "quantization", "demand_satisfied"}`. All inputs are BLOB counts; the three blob tallies sum to UNMET=offered−served. Shares are over UNMET (blob units, dimensionally consistent); `demand_satisfied = served/offered` reported separately. `contention_bound` = `contention_blobs/unmet` (a real airtime knee with high met-demand is NOT diluted, and ordinary low-goodput contention is NOT mislabeled quantization).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_knee.py  (CREATE)
from soup_sim.knee import binding_decomposition
def test_binding_decomposition_over_unmet_blob_units():
    # 60% met, all 40 unmet blobs are contention -> contention_bound == 1.0 of unmet (not 0.4 diluted)
    d = binding_decomposition(offered=100, served=60, setup_starved_blobs=0, quantization_blobs=0, contention_blobs=40)
    assert abs(d["contention_bound"] - 1.0) < 1e-9 and abs(d["demand_satisfied"] - 0.6) < 1e-9
    # unmet split 30 starved / 10 contention -> starvation dominates
    d = binding_decomposition(offered=100, served=10, setup_starved_blobs=80, quantization_blobs=0, contention_blobs=10)
    assert d["setup_starved"] > d["contention_bound"]
    # low-goodput contention (could move blobs, backlog exceeded) must NOT read as quantization
    d = binding_decomposition(offered=100, served=40, setup_starved_blobs=0, quantization_blobs=0, contention_blobs=60)
    assert d["contention_bound"] == 0.6 / 0.6 if False else abs(d["contention_bound"] - 1.0) < 1e-9
    # nothing unmet -> contention_bound 0
    d = binding_decomposition(offered=50, served=50, setup_starved_blobs=0, quantization_blobs=0, contention_blobs=0)
    assert d["contention_bound"] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py::test_binding_decomposition_over_unmet -q`
Expected: FAIL (no module `soup_sim.knee`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/knee.py  (CREATE)
def binding_decomposition(offered, served, setup_starved_blobs, quantization_blobs, contention_blobs):
    offered = max(0, offered); served = min(served, offered)
    unmet = offered - served
    if unmet <= 0:
        return {"contention_bound": 0.0, "setup_starved": 0.0, "quantization": 0.0,
                "demand_satisfied": (served / offered) if offered else 1.0}
    # blob tallies should sum to unmet; normalize defensively in case of off-by-rounding
    s = setup_starved_blobs + quantization_blobs + contention_blobs
    norm = s if s > 0 else 1
    return {"contention_bound": contention_blobs / norm, "setup_starved": setup_starved_blobs / norm,
            "quantization": quantization_blobs / norm, "demand_satisfied": served / offered}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py::test_binding_decomposition_over_unmet -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/knee.py sim/tests/test_knee.py
git commit -m "feat(sim): binding decomposition over UNMET demand (contention/setup/quantization)"
```

---

## Task 7: Saturation-knee estimator (±2 window, seeded bootstrap)

**Files:**
- Modify: `sim/soup_sim/knee.py`
- Test: `sim/tests/test_knee.py`

**Interfaces:**
- Produces: `find_knee(densities, per_rep_circulation, rng, n_boot=200) -> {"knee": float|None, "ci": (lo,hi)|None, "status": "knee"|"no_knee_in_range"}`. Knee = argmax of mean circulated/min refined by a quadratic-in-log(density) fit over a **±2-point window** (5 points, residual is meaningful); bootstrap over reps. Monotone (argmax at an edge, or upward parabola) ⇒ `"no_knee_in_range"`, `knee=None`. MUST NOT call `crossing_0p5`/`midpoint_with_ci`.

- [ ] **Step 1: Write the failing tests (planted peak, coarse-grid noise, monotone)**

```python
# sim/tests/test_knee.py  (append)
import numpy as np
from soup_sim.knee import find_knee
def test_find_knee_recovers_planted_peak():
    dens = np.linspace(1.0, 20.0, 20); peak = 9.0
    mean = 100.0 - 50.0 * (np.log(dens) - np.log(peak)) ** 2
    reps = np.stack([mean, mean + 0.3, mean - 0.3], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "knee" and abs(out["knee"] - peak) < 1.5
def test_find_knee_coarse_grid_with_noise():
    dens = np.array([2.0, 5.0, 8.0, 11.0, 14.0, 17.0, 20.0]); peak = 9.0
    mean = 100.0 - 30.0 * (np.log(dens) - np.log(peak)) ** 2
    rng = np.random.default_rng(3)
    reps = np.stack([mean + rng.normal(0, 3, len(dens)) for _ in range(12)], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "knee" and 4.0 < out["knee"] < 16.0   # robust, not a spurious no-knee
def test_find_knee_monotone_returns_no_knee():
    dens = np.linspace(1.0, 20.0, 20); mean = 100.0 - 3.0 * dens
    reps = np.stack([mean, mean + 0.1, mean - 0.1], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "no_knee_in_range" and out["knee"] is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py -q`
Expected: FAIL (`ImportError: find_knee`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/knee.py  (append)
import numpy as np
KNEE_DROP_MARGIN = 0.15   # require the curve to fall >=15% past the peak (else it's a plateau, not a knee)
def _knee_point(dens, mean):
    mean = np.asarray(mean, float)
    k = int(np.argmax(mean))
    if k == 0 or k == len(mean) - 1:
        return None                                  # peak at an edge -> monotone in range
    peak = mean[k]
    if peak <= 0 or mean[-1] > peak * (1.0 - KNEE_DROP_MARGIN):
        return None                                  # no real drop after the peak -> plateau, not a knee
    lo, hi = max(0, k - 2), min(len(mean) - 1, k + 2)   # +/-2 window (>=5 pts where possible)
    x = np.log(np.asarray(dens[lo:hi + 1], float)); y = mean[lo:hi + 1]
    a, b, _c = np.polyfit(x, y, 2)
    if a >= 0:
        return None                                  # not concave -> no interior max
    return float(np.exp(-b / (2 * a)))
def find_knee(densities, per_rep_circulation, rng, n_boot=200):
    dens = np.asarray(densities, float); mat = np.asarray(per_rep_circulation, float)
    point = _knee_point(dens, mat.mean(axis=1))
    if point is None:
        return {"knee": None, "ci": None, "status": "no_knee_in_range"}
    reps = mat.shape[1]; boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, reps, reps)
        kp = _knee_point(dens, mat[:, idx].mean(axis=1))
        if kp is not None:
            boots.append(kp)
    ci = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (point, point)
    return {"knee": point, "ci": ci, "status": "knee"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/knee.py sim/tests/test_knee.py
git commit -m "feat(sim): saturation-knee estimator (argmax + +/-2 quadratic-in-log fit + bootstrap; no-knee sentinel)"
```

---

## Task 8: Binding publish gate (two control arms)

**Files:**
- Modify: `sim/soup_sim/knee.py`
- Test: `sim/tests/test_knee.py`

**Interfaces:**
- Produces: `BINDING_THRESHOLD = 0.5`; `binding_gate(knee_result, binding_at_knee, alpha0_turns_over, buffer_ttl_turns_over) -> {"publish": bool, "label": str}`. Publishes iff `status=="knee"` AND `binding_at_knee["contention_bound"] >= BINDING_THRESHOLD` AND not `alpha0_turns_over` AND not `buffer_ttl_turns_over`.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_knee.py  (append)
from soup_sim.knee import binding_gate, BINDING_THRESHOLD
def test_binding_gate():
    knee = {"status": "knee", "knee": 9.0, "ci": (8.0, 10.0)}
    assert binding_gate(knee, {"contention_bound": 0.7}, False, False)["publish"] is True
    g = binding_gate(knee, {"contention_bound": 0.7}, True, False)
    assert g["publish"] is False and "connectivity" in g["label"].lower()
    g = binding_gate(knee, {"contention_bound": 0.7}, False, True)
    assert g["publish"] is False and ("buffer" in g["label"].lower() or "ttl" in g["label"].lower())
    assert binding_gate(knee, {"contention_bound": 0.2}, False, False)["publish"] is False
    assert binding_gate({"status": "no_knee_in_range"}, {"contention_bound": 0.9}, False, False)["publish"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py::test_binding_gate -q`
Expected: FAIL (`ImportError: binding_gate`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/knee.py  (append)
BINDING_THRESHOLD = 0.5   # >=50% of UNMET demand must be contention-bound at the knee (conservative:
                          # a higher bar would risk false "no airtime", a lower one false "airtime").
def binding_gate(knee_result, binding_at_knee, alpha0_turns_over, buffer_ttl_turns_over):
    if knee_result.get("status") != "knee":
        return {"publish": False, "label": "no knee in range"}
    if alpha0_turns_over:
        return {"publish": False, "label": "connectivity-limited (alpha=0 control also turns over)"}
    if buffer_ttl_turns_over:
        return {"publish": False, "label": "buffer/TTL-limited (cap=inf/ttl=inf control removes the turn-down)"}
    if binding_at_knee.get("contention_bound", 0.0) < BINDING_THRESHOLD:
        return {"publish": False, "label": "not airtime-bound (contention below threshold)"}
    return {"publish": True, "label": "airtime-saturation (contention-bound at knee)"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/knee.py sim/tests/test_knee.py
git commit -m "feat(sim): binding publish gate (pre-registered threshold + alpha=0 AND cap/ttl controls)"
```

---

## Task 9: Airtime sweep with both control arms + knee + gate

**Files:**
- Modify: `sim/soup_sim/scenario.py`
- Test: `sim/tests/test_scenario_airtime.py` (CREATE)

**Interfaces:**
- Consumes: `run_one` (airtime fields), `find_knee`, `binding_decomposition`, `binding_gate`.
- Produces: `airtime_sweep(base_cfg, densities, reps) -> {"rows", "alpha0_rows", "capttl_rows", "knee", "gate", "predicted_knee_density"}`. `rows` per density: `circulated_per_min_mean/ci_lo/ci_hi`, `utilization_mean`, `delivery_mean`, `t50`, `binding` (decomposition dict). Control arms: `alpha0_rows` via `replace(..., airtime_model="linear", alpha=0.0, beta=0.0, t_setup_slope=0.0)`; `capttl_rows` via `replace(..., buffer_cap=10**9, ttl=1e9)`. `find_knee` is seeded from `base_cfg.master_seed`. `alpha0_turns_over`/`buffer_ttl_turns_over` = `find_knee(...).status=="knee"` on each control's circulation. Deterministic: same seed ⇒ identical `rows`, `knee`, `gate`.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_scenario_airtime.py  (CREATE)
import numpy as np
from soup_sim.config import Config
from soup_sim.scenario import airtime_sweep
# SMALL arena: at density d, n = d*W*H/(pi r^2). W=H=55, r=10 -> n ~= d*9.6, so density 16 -> n~154 (fast).
def base():
    return Config(n=0, width=55.0, height=55.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=40.0, buffer_cap=50, throughput_ideal=8e3,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=10.0, measure_window=30.0,
                  drain=0.0, n_messages=25, seen_margin=20.0, master_seed=7,
                  airtime_model="collision", beta=0.15, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)
def test_airtime_sweep_controls_and_determinism():
    dens = [3.0, 6.0, 9.0, 12.0, 16.0]            # >=5 pts; the empirical density-knee must land interior (idx>=2)
    out1 = airtime_sweep(base(), densities=dens, reps=2)
    out2 = airtime_sweep(base(), densities=dens, reps=2)
    assert [r["circulated_per_min_mean"] for r in out1["rows"]] == [r["circulated_per_min_mean"] for r in out2["rows"]]
    assert out1["knee"] == out2["knee"] and out1["gate"] == out2["gate"]   # fully deterministic
    assert len(out1["alpha0_rows"]) == len(dens) and len(out1["capttl_rows"]) == len(dens)
    assert "publish" in out1["gate"]
    for r in out1["rows"]:
        assert {"circulated_per_min_mean", "utilization_mean", "delivery_mean", "t50", "binding"} <= set(r)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_scenario_airtime.py -q`
Expected: FAIL (`ImportError: airtime_sweep`).

- [ ] **Step 3: Implement** `airtime_sweep` in `scenario.py`:

```python
def _airtime_arm(base_cfg, densities, reps):
    rows, circ_matrix = [], []
    for di, d in enumerate(densities):
        n = density_to_n(d, base_cfg.width, base_cfg.height, base_cfg.radius)
        circ, util, deliv, t50s = [], [], [], []
        agg = {"offered": 0, "served": 0, "starved": 0, "quant": 0, "contention": 0}
        for rep in range(reps):
            cfg = replace(base_cfg, n=max(2, n), master_seed=_seed_for(base_cfg.master_seed, di, rep))
            r = run_one(cfg)
            circ.append(r["circulated_per_min"]); util.append(r["utilization"]); deliv.append(r["delivery_ratio"])
            t50s.append(r["t50"] if r["t50"] is not None else np.nan)
            agg["offered"] += r["offered_blobs"]; agg["served"] += r["served_blobs"]
            agg["starved"] += r["setup_starved_blobs"]; agg["quant"] += r["quantization_blobs"]
            agg["contention"] += r["contention_blobs"]
        m, lo, hi = mean_ci(circ)
        rows.append({"density": d, "n": n, "circulated_per_min_mean": m, "ci_lo": lo, "ci_hi": hi,
                     "utilization_mean": float(np.mean(util)), "delivery_mean": float(np.mean(deliv)),
                     "t50": float(np.nanmean(t50s)) if np.any(~np.isnan(t50s)) else None,
                     "binding": binding_decomposition(agg["offered"], agg["served"], agg["starved"],
                                                      agg["quant"], agg["contention"])})
        circ_matrix.append(circ)
    return rows, np.array(circ_matrix)

def airtime_sweep(base_cfg, densities, reps):
    rng = np.random.default_rng(np.random.SeedSequence([base_cfg.master_seed, 777]))
    rows, circ = _airtime_arm(base_cfg, densities, reps)
    a0_rows, a0_circ = _airtime_arm(replace(base_cfg, airtime_model="linear", alpha=0.0, beta=0.0,
                                            t_setup_slope=0.0), densities, reps)
    ct_rows, ct_circ = _airtime_arm(replace(base_cfg, buffer_cap=10 ** 9, ttl=1e9), densities, reps)
    knee = find_knee(densities, circ, np.random.default_rng(rng.integers(0, 2 ** 31)))
    a0_over = find_knee(densities, a0_circ, np.random.default_rng(rng.integers(0, 2 ** 31)))["status"] == "knee"
    ct_over = find_knee(densities, ct_circ, np.random.default_rng(rng.integers(0, 2 ** 31)))["status"] == "knee"
    binding_at_knee = rows[int(np.argmax([r["circulated_per_min_mean"] for r in rows]))]["binding"]
    gate = binding_gate(knee, binding_at_knee, a0_over, ct_over)
    return {"rows": rows, "alpha0_rows": a0_rows, "capttl_rows": ct_rows, "knee": knee, "gate": gate,
            "predicted_knee_contenders": base_cfg.n_channels / base_cfg.beta if base_cfg.beta else None}
```

Note: `predicted_knee_contenders = n_channels/beta` is a CONTENDER count (the per-link aggregate peak), NOT a density. The density-space knee depends on the contender↔density mapping (carrier-sense degree at density d) and the link-count weighting; it is found empirically by `find_knee` on the measured circulation. The pre-registered grid must bracket that empirical density-knee with an INTERIOR argmax (index ≥1, ideally ≥2) — Task 10's distinguishability test enforces it.

Add imports at the top of `scenario.py`: `from .knee import find_knee, binding_decomposition, binding_gate`.

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_scenario_airtime.py tests/test_scenario.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/scenario.py sim/tests/test_scenario_airtime.py
git commit -m "feat(sim): airtime sweep with alpha=0 AND cap/ttl control arms + knee + binding gate"
```

---

## Task 10: End-to-end model distinguishability + report/CLI/docs

**Files:**
- Modify: `sim/soup_sim/report.py`, `sim/run.py`, `sim/README.md`
- Test: `sim/tests/test_report.py`, `sim/tests/test_scenario_airtime.py`

**Interfaces:**
- Produces: `airtime_to_csv_string(rows, manifest)` (flattens `binding` into `binding_*` cols); `airtime_plot(out, alpha0_rows, capttl_rows, knee, path)`; `run.py --preset airtime-knee` runs the sweep under BOTH models (collision + linear) → emits a model-uncertainty band + the gate verdict; README provenance table + bias rows.

- [ ] **Step 1: Write the failing tests**

```python
# sim/tests/test_report.py  (append)
from soup_sim.report import airtime_to_csv_string
def test_airtime_csv_has_fields():
    rows = [{"density": 6.0, "circulated_per_min_mean": 12.0, "ci_lo": 10.0, "ci_hi": 14.0,
             "utilization_mean": 0.3, "delivery_mean": 0.4, "t50": 25.0,
             "binding": {"contention_bound": 0.6, "setup_starved": 0.3, "quantization": 0.1, "demand_satisfied": 0.4}}]
    s = airtime_to_csv_string(rows, {"airtime_model": "collision"})
    assert "circulated_per_min_mean" in s and "t50" in s and "binding_contention_bound" in s and "param_airtime_model" in s
```

```python
# sim/tests/test_scenario_airtime.py  (append)  -- end-to-end distinguishability (spec falsifiable prediction)
import pytest
from dataclasses import replace
def replace_model(cfg, model):
    return replace(cfg, airtime_model=model, alpha=1.0, beta=0.15)

@pytest.mark.slow   # heavier sweep; small arena keeps it ~minute-scale, excluded from default -m "not slow"
def test_collision_knee_linear_plateau_distinguishable():
    dens = [3.0, 6.0, 9.0, 12.0, 16.0]            # small-arena base() -> n <= ~154; brackets the density knee
    coll = airtime_sweep(base(), dens, reps=6)
    lin = airtime_sweep(replace_model(base(), "linear"), dens, reps=6)
    assert coll["knee"]["status"] == "knee"               # collision turns over -> knee
    assert lin["knee"]["status"] == "no_knee_in_range"    # linear plateaus -> no knee (drop-margin gate)
```

Register the marker so default runs skip it: add to `sim/pyproject.toml` under `[tool.pytest.ini_options]`:
```toml
markers = ["slow: heavier end-to-end sweeps (run with -m slow)"]
addopts = "-m 'not slow'"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_report.py tests/test_scenario_airtime.py -q`
Expected: FAIL (`ImportError: airtime_to_csv_string`; distinguishability test errors).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/report.py  (append)
AIRTIME_FIELDS = ["density", "circulated_per_min_mean", "ci_lo", "ci_hi", "utilization_mean",
                  "delivery_mean", "t50"]
BINDING_KEYS = ["contention_bound", "setup_starved", "quantization", "demand_satisfied"]
def airtime_to_csv_string(rows, manifest) -> str:
    import csv, io
    man = list(manifest.keys())
    header = AIRTIME_FIELDS + [f"binding_{k}" for k in BINDING_KEYS] + [f"param_{k}" for k in man]
    buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); w.writerow(header)
    for r in rows:
        w.writerow([r.get(k) for k in AIRTIME_FIELDS]
                   + [r.get("binding", {}).get(k) for k in BINDING_KEYS]
                   + [manifest[k] for k in man])
    return buf.getvalue()
```

Add `airtime_plot(...)` (import-guarded matplotlib): circulation vs density for `rows`, with `alpha0_rows` and `capttl_rows` overlaid and a vertical line at `knee["knee"]` if present.

In `run.py`: add `--preset airtime-knee`. Build an airtime base cfg; run `airtime_sweep` under `airtime_model="collision"` and again under `"linear"`; print both knees (the model-uncertainty band), the gate verdict + label, and `predicted_knee_density`; write CSV via `airtime_to_csv_string` and the plot if `--plot`.

In `README.md`: add a **Provenance table** (goodput headline 100 kbps / optimistic 1.4 Mbps; `t_setup` & `t_setup_slope` from cited BLE discovery-latency-vs-advertiser-count; `beta` labelled an UNCALIBRATED free parameter with predicted knee `n_channels/beta`; report the RWP contact-duration distribution and flag its tail as optimistic vs human-contact data) and **update/extend the bias table** with one row+direction per NEW optimistic mechanic: carrier-sense max-of-pair single-snapshot contention (optimistic); deterministic `(1-p_fail)` vs independent per-blob (removes tail risk); collision form (no capture/retransmission) — and **update** (not duplicate) the existing reconciliation-overhead and RWP-vs-clustered rows.

- [ ] **Step 4: Run to verify it passes + FULL suite green (incl. the slow distinguishability test once)**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m pytest -m slow -q && .venv/Scripts/python.exe run.py --preset airtime-knee --out out/airtime.csv`
Expected: default suite PASS (slow excluded by `addopts`); the explicit `-m slow` run PASSES the distinguishability test; CLI prints both-model knees + gate verdict.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/report.py sim/run.py sim/README.md sim/tests/test_report.py sim/tests/test_scenario_airtime.py
git commit -m "feat(sim): airtime CSV/plot + airtime-knee preset (collision-vs-linear band) + provenance & bias docs"
```

---

## Self-Review

**1. Spec coverage (v2):** §3.1 collision primary + linear demoted + decoupled contenders + α=0 control + model band → Tasks 1,2,9,10; the distinguishability prediction is now an END-TO-END test (Task 10) not just a budget unit test. §3.2 utilization (vs available AND offered) + windowed circulation + dummy-traffic note → Tasks 3,4. §3.3 knee + decomposition (setup/quantization/demand) + binding gate + planted-peak + no-knee sentinel + pre-registered threshold → Tasks 6,7,8. §3.4 censoring T50 + delivered-only LOWER-bound + cap/ttl control + provenance + bias rows → Tasks 5,9,10.

**2. Closed plan-review-round-1 findings:** per-episode-correct billing (Task 3); knee-bracketing grid (Tasks 9,10); decomposition over UNMET (Task 6); α=0 control truly airtime-free + separate cap/ttl arm (Tasks 8,9); budget threaded into run_one (Task 1); per-link test fixed (Task 1); T50 not called KM (Task 5); offered airtime in engine (Task 3); widened knee window + seeded bootstrap + coarse-grid test (Tasks 7,9); offered counted once per pair (Task 3); README bias rows reconciled (Task 10); Task 2 threshold raised to ≥3.

**2b. Closed plan-review-round-2 findings (v3):** incremental per-step billing at accrual `eff` ⇒ `utilization ≤ 1` on mobility (Task 3 + test); blob-unit binding tallies with quantization-vs-contention capacity test (Tasks 3,6) — closes the gate blind-spot; `setup_debt = t_setup_at(n_open)` with `n_contenders` computed before the open-dict (Task 3) — fixes the inert slope + scope NameError; `"t50"` wired into `run_one` (Task 4); `KNEE_DROP_MARGIN` relative-drop gate (Task 7) — kills the flaky linear "no_knee"; small test arenas + `@pytest.mark.slow` + `addopts="-m 'not slow'"` (Tasks 9,10) — suite stays ~1-min; `predicted_knee_contenders` renamed + density-knee bracketed empirically (Task 9). Right-sizing: Task 3 carries an explicit 3b split-step; Task 10's heavy distinguishability test is isolated behind the `slow` marker.

**3. Type consistency:** `find_knee`→`{status,knee,ci}`; `binding_decomposition`→`{contention_bound,setup_starved,quantization,demand_satisfied}`; `binding_gate(knee, binding, alpha0_over, capttl_over)`; `airtime_sweep`→`{rows,alpha0_rows,capttl_rows,knee,gate,predicted_knee_density}`. Consistent across Tasks 6–10.

**4. Determinism & non-regression:** new config fields default to current behavior; `airtime_sweep` seeds every arm via `_seed_for` and the bootstrap via a `master_seed`-derived generator; Tasks 2 & 3 re-run `test_engine_fidelity.py`/`test_engine.py`; Task 10 runs the full suite.

**5. Remaining judgment calls for execution:** the `base()` airtime parameters in Task 9 (`beta=0.15`, `throughput_ideal=8e3`, `blob_size=200`) are illustrative; the implementer should adjust within the provenance bounds so the collision arm produces an interior knee on the registered grid (the distinguishability test in Task 10 will catch a mis-tuned grid).
