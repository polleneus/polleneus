# Airtime Model + Measurement (Feature 2 · PR-2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On the trusted PR-1 engine, build a collision-capable airtime model and the measurement machinery to answer the red-team's risk #1 — *does BLE airtime saturate at crowd density and collapse delivery?* — with a binding publish-gate so an engine/buffer/TTL effect can never be mislabeled "airtime."

**Architecture:** Additive only. New config fields default to **current behavior** (`airtime_model="linear"`, `beta=0`, `cs_radius_mult=1.0`), so the merged fidelity gate (`test_engine_fidelity.py`) and percolation non-regression (`test_integration_percolation.py`) stay green bit-for-bit. The collision model lives in `budget.py`; the engine gains airtime *accounting* (charged/available/offered) and measures contention over a *carrier-sense* radius decoupled from the connectivity graph; `metrics.py` gains utilization, windowed circulation, and censoring-aware latency; a new `knee.py` locates the saturation knee and applies the binding gate; `scenario.py` gains an airtime sweep with the mandatory α=0 control overlay and a cap=∞/ttl=∞ control.

**Tech Stack:** Python 3, numpy, pytest (`pythonpath=["."]`), matplotlib (optional, import-guarded). Determinism via `cfg.rng(*path)` SeedSequence substreams.

## Global Constraints

- **Every published number is an UPPER BOUND on real delivery.** New optimistic mechanics get a README bias row + direction.
- **Determinism:** all randomness via `cfg.rng(*path)`; no `Date.now`/global RNG. The replication unit is the SEED.
- **Addressing-blind engine:** no `sender`/`recipient` tokens in engine-layer files (enforced by `test_lint_invariants.py`). Use `src`/`dst`/`local`/`contender`.
- **Primary airtime model = ALOHA collision** `p_success(n)=exp(-β·n)` on `n_channels=3` advertising channels and density-dependent `t_setup(n)=t_setup0 + slope·n`. The old `1/(1+α·n)` becomes the **optimistic-bound sensitivity** case, not primary.
- **α=0 control overlay on the SAME axes for every airtime curve.** If α=0 (and β=0) already turns over, the cause is connectivity/buffer/TTL, not airtime.
- **Headline goodput conservative ≈100 kbps** (no-DLE); optimistic ≈1.4 Mbps as upper sensitivity.
- **Knee estimator must NOT reuse the monotone 0.5-crossing machinery** (`crossing_0p5`/`midpoint_with_ci`). It returns **"no knee in range"** (a sentinel), never NaN, when the curve is monotone.
- **Publish gate (hard):** the airtime-saturation figure publishes **only if** the contention-binding fraction exceeds a **pre-registered threshold** (`BINDING_THRESHOLD = 0.5`) at/beyond the knee **AND** the α=0 control does not also turn over. Otherwise label the curve connectivity/buffer/TTL-limited.
- **Latency is censoring-aware:** TTL-expired = censored at TTL; report **T50** (time-to-50%-delivery) jointly with delivery ratio. Delivered-only mean latency is labelled a LOWER bound.
- **Contention population ≠ connectivity degree:** `n_contenders` is the co-channel/interference count over a carrier-sense radius (`cs_radius_mult · radius`), justified with bias direction in provenance.

---

## File Structure

- `sim/soup_sim/config.py` — MODIFY: add `airtime_model, beta, t_setup_slope, n_channels, cs_radius_mult` (behavior-preserving defaults) + validation.
- `sim/soup_sim/budget.py` — MODIFY: collision `effective_goodput`, density-dependent `t_setup_at(n)`, `charged_airtime(served, n)`; keep linear as a selectable form.
- `sim/soup_sim/engine.py` — MODIFY: measure contention over carrier-sense radius; accumulate `charged_airtime`, `available_contact_time`, `offered_airtime`.
- `sim/soup_sim/metrics.py` — MODIFY: `utilization()`, windowed `circulated_per_min()`, `t50()`/`km_survival()`, `binding_decomposition()`.
- `sim/soup_sim/knee.py` — CREATE: `find_knee()` (argmax + quadratic-in-log fit + bootstrap), `binding_gate()`.
- `sim/soup_sim/scenario.py` — MODIFY: `airtime_sweep()` (+ α=0 control overlay, cap/ttl control).
- `sim/soup_sim/report.py` — MODIFY: airtime CSV fields + plot.
- `sim/run.py` — MODIFY: `--preset airtime-knee`.
- `sim/README.md` — MODIFY: provenance table + bias rows.
- Tests: `sim/tests/test_budget.py` (MODIFY), `test_engine_airtime.py`, `test_metrics_airtime.py`, `test_knee.py`, `test_scenario_airtime.py` (CREATE), `test_report.py`/`test_config.py` (MODIFY).

---

## Task 1: Collision-capable airtime model

**Files:**
- Modify: `sim/soup_sim/config.py` (add fields + validate)
- Modify: `sim/soup_sim/budget.py`
- Test: `sim/tests/test_budget.py`

**Interfaces:**
- Consumes: `Config.{throughput_ideal, alpha, t_setup, p_fail, blob_size}` (existing).
- Produces: `Config.{airtime_model: str, beta: float, t_setup_slope: float, n_channels: int, cs_radius_mult: float}`; `AirtimeBudget(throughput_ideal, alpha, t_setup, p_fail, blob_size, model="linear", beta=0.0, t_setup_slope=0.0, n_channels=3)` with `effective_goodput(n_contenders) -> float`, `t_setup_at(n_contenders) -> float`, `charged_airtime(served_blobs, n_contenders) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_budget.py  (append)
import numpy as np
from soup_sim.budget import AirtimeBudget

# NOTE: per-link goodput is monotone DECREASING for BOTH models (more contenders -> less each).
# The TURN-OVER is a SYSTEM property: system circulation ~ n * per-link goodput. Under collision
# that aggregate has an interior max (knee); under linear it climbs to a plateau (no knee).
def test_collision_aggregate_turns_over_linear_plateaus():
    ns = np.arange(1, 100)
    coll = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="collision", beta=0.08, n_channels=3)
    lin = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="linear")
    agg_c = np.array([n * coll.effective_goodput(int(n)) for n in ns])   # system ~ n * per-link
    agg_l = np.array([n * lin.effective_goodput(int(n)) for n in ns])
    assert 0 < agg_c.argmax() < len(ns) - 1                  # collision: interior maximum (turns over)
    assert agg_l.argmax() == len(ns) - 1                     # linear: monotone up to plateau (max at edge)
    assert agg_c.max() > 1.5 * agg_c[-1]                     # clear turn-over margin vs the tail

def test_collision_per_link_decays_faster_than_linear():
    coll = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="collision", beta=0.08, n_channels=3)
    lin = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="linear")
    assert np.all(np.diff([coll.effective_goodput(int(n)) for n in range(1, 80)]) <= 1e-9)  # monotone
    assert coll.effective_goodput(60) < lin.effective_goodput(60)        # exp decays faster than 1/n

def test_density_dependent_setup_can_starve_airtime():
    b = AirtimeBudget(1e5, 0.0, t_setup=0.01, p_fail=0.0, blob_size=1.0,
                      model="collision", beta=0.0, t_setup_slope=0.05, n_channels=3)
    assert b.t_setup_at(0) == 0.01
    assert b.t_setup_at(40) > b.t_setup_at(0)               # setup grows with contenders

def test_charged_airtime_includes_setup_and_service():
    b = AirtimeBudget(100.0, 0.0, t_setup=0.5, p_fail=0.0, blob_size=10.0,
                      model="linear", t_setup_slope=0.0)
    # 3 blobs of 10 bytes at eff=100 B/s -> 0.3 s service + 0.5 s setup
    assert abs(b.charged_airtime(3, 0) - (0.5 + 3 * 10.0 / 100.0)) < 1e-9
    assert b.charged_airtime(0, 0) == 0.0                   # no contact charged if nothing served
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_budget.py -q`
Expected: FAIL (`AirtimeBudget() got an unexpected keyword argument 'model'`).

- [ ] **Step 3: Add config fields (behavior-preserving defaults)**

```python
# sim/soup_sim/config.py  — add to the dataclass field block (AFTER master_seed so defaults are legal)
    airtime_model: str = "linear"     # "linear" (optimistic sensitivity) | "collision" (ALOHA primary)
    beta: float = 0.0                 # collision steepness in p_success(n)=exp(-beta*n)
    t_setup_slope: float = 0.0        # density-dependent setup: t_setup_at(n)=t_setup + slope*n
    n_channels: int = 3               # shared advertising channels
    cs_radius_mult: float = 1.0       # carrier-sense radius = cs_radius_mult * radius
```

```python
# sim/soup_sim/config.py  — add to validate()
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

- [ ] **Step 4: Implement the collision budget**

```python
# sim/soup_sim/budget.py  — replace the class body, keeping blobs_transferable for reference/tests
import math

class AirtimeBudget:
    def __init__(self, throughput_ideal, alpha, t_setup, p_fail, blob_size,
                 model="linear", beta=0.0, t_setup_slope=0.0, n_channels=3):
        self.throughput_ideal = throughput_ideal
        self.alpha = alpha
        self.t_setup = t_setup
        self.p_fail = p_fail
        self.blob_size = blob_size
        self.model = model
        self.beta = beta
        self.t_setup_slope = t_setup_slope
        self.n_channels = max(1, n_channels)

    def t_setup_at(self, n_contenders: int) -> float:
        return self.t_setup + self.t_setup_slope * max(0, n_contenders)

    def effective_goodput(self, n_contenders: int) -> float:
        """PER-LINK goodput (bytes/time) after contention + reconciliation loss. MONOTONE
        DECREASING for both models (the system turn-over lives in n*goodput, not here):
        linear:    throughput/(1+alpha*n)             (~1/n; system n*goodput -> plateau)
        collision: throughput*exp(-beta*n/n_channels) (ALOHA: offered load per channel ~ n/n_channels,
                   the G/n share-cancellation already applied; system n*goodput has an interior max
                   at n=n_channels/beta -> turns over)."""
        n = max(0, n_contenders)
        loss = (1.0 - self.p_fail)
        if self.model == "collision":
            return self.throughput_ideal * math.exp(-self.beta * n / self.n_channels) * loss
        return self.throughput_ideal / (1.0 + self.alpha * n) * loss

    def charged_airtime(self, served_blobs: int, n_contenders: int) -> float:
        """Airtime a contact consumes: setup floor (once) + service time for served blobs.
        Returns 0 if nothing served (no contact billed)."""
        if served_blobs <= 0:
            return 0.0
        eff = self.effective_goodput(n_contenders)
        return self.t_setup_at(n_contenders) + served_blobs * self.blob_size / eff
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_budget.py tests/test_config.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add sim/soup_sim/config.py sim/soup_sim/budget.py sim/tests/test_budget.py
git commit -m "feat(sim): collision (ALOHA) airtime model + density-dependent setup + charged_airtime"
```

---

## Task 2: Contention over a carrier-sense radius (decoupled from connectivity)

**Files:**
- Modify: `sim/soup_sim/engine.py` (contention input only; delivery logic unchanged)
- Test: `sim/tests/test_engine_airtime.py` (CREATE)

**Interfaces:**
- Consumes: `Config.{cs_radius_mult, radius}`; `AirtimeBudget.effective_goodput(n_contenders)`.
- Produces: engine feeds `effective_goodput` with `n_contenders` measured over `cs_radius_mult*radius`, NOT the connectivity degree. Fidelity gate stays green (unbounded throughput is contention-insensitive).

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
    # 4 nodes in a line 8 apart: connectivity degree (r=10) sees ~1 neighbour; carrier-sense
    # (3*r=30) sees ~3. The engine must report the larger contender count to the budget.
    seen = {}
    c = cfg()
    pos = np.array([[0., 50.], [8., 50.], [16., 50.], [24., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(4)]
    budget = AirtimeBudget(1e12, 0, 0, 0, 1.0)
    budget.effective_goodput = lambda n, _orig=budget.effective_goodput, _s=seen: (
        _s.__setitem__("max_n", max(_s.get("max_n", 0), n)) or _orig(n))
    eng = Engine(c, mob, bufs, budget, c.rng(1), on_deliver=lambda *_: None)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(2.0); eng.finalize()
    assert seen.get("max_n", 0) >= 2   # carrier-sense range pulls in non-connected contenders
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py -q`
Expected: FAIL (engine currently passes connectivity `deg`, so `max_n` < 2 with these spacings).

- [ ] **Step 3: Implement carrier-sense contention**

In `engine.py._process_step`, compute a second degree count over the carrier-sense radius and feed it to the budget:

```python
        cs_r = r * getattr(cfg, "cs_radius_mult", 1.0)
        cs_cand = neighbor_pairs(p0, cs_r + 2.0 * max_disp + _EPS, w, h, b) if cs_r > r else cand
        cs_deg = self._degrees(p0, cs_cand, cs_r, w, h, b)
```

Then in the credit accrual line replace `max(deg[i], deg[j])` with `max(cs_deg[i], cs_deg[j])`:

```python
            eff = self.budget.effective_goodput(int(max(cs_deg[i], cs_deg[j])))
```

(`deg` over the connectivity radius is still used for nothing else here; keep it only if other code reads it — it does not. Remove the now-unused `deg` line if present.)

- [ ] **Step 4: Run to verify it passes (and the fidelity gate is untouched)**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py tests/test_engine_fidelity.py tests/test_engine.py -q`
Expected: PASS (fidelity gate uses unbounded throughput, so `effective_goodput` magnitude is irrelevant there).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/engine.py sim/tests/test_engine_airtime.py
git commit -m "feat(sim): measure contention over carrier-sense radius, decoupled from connectivity degree"
```

---

## Task 3: Engine airtime accounting (charged / available / offered)

**Files:**
- Modify: `sim/soup_sim/engine.py`
- Test: `sim/tests/test_engine_airtime.py`

**Interfaces:**
- Produces: `Engine.charged_airtime: float`, `Engine.available_contact_time: float`, `Engine.offered_blobs: int`, `Engine.served_blobs: int`. Charged airtime accrues per contact via `budget.charged_airtime`; available time = Σ in-range time; offered = blobs the peer lacked (whether or not airtime allowed them).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_engine_airtime.py  (append)
from soup_sim.mobility import Mobility
def test_airtime_accounting_bounds():
    c = cfg(n=2, throughput_ideal=2.0, blob_size=1.0, t_setup=0.0, cs_radius_mult=1.0)
    pos = np.array([[50., 50.], [55., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(2)]
    budget = AirtimeBudget(2.0, 0, 0.0, 0, 1.0)
    eng = Engine(c, mob, bufs, budget, c.rng(1), on_deliver=lambda *_: None)
    for k in range(5):
        eng.inject(Blob(k, 0.0, 1e12, 1.0), 0)   # 5 blobs at node0, peer lacks all 5
    eng.run_until(10.0); eng.finalize()
    assert eng.available_contact_time > 0
    assert 0.0 <= eng.charged_airtime <= eng.available_contact_time + 1e-9
    assert eng.offered_blobs >= eng.served_blobs >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py::test_airtime_accounting_bounds -q`
Expected: FAIL (`AttributeError: charged_airtime`).

- [ ] **Step 3: Implement accounting**

In `engine.__init__` add `self.charged_airtime = 0.0; self.available_contact_time = 0.0; self.offered_blobs = 0; self.served_blobs = 0`. In `_process_step`, for each active pair add `self.available_contact_time += (exit_ - enter)`. Have `_exchange` return `(moved, offered)` where `offered` = number of distinct blobs the peer lacked this call; accumulate `self.served_blobs += moved; self.offered_blobs += offered`, and after the per-pair fixpoint converges, bill `self.charged_airtime += self.budget.charged_airtime(moved_total_for_pair, n_contenders)` using that pair's served count this step. (Track per-pair served in the fixpoint loop; bill once per step per pair.)

- [ ] **Step 4: Run to verify it passes (full engine suites green)**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_airtime.py tests/test_engine_fidelity.py tests/test_engine.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/engine.py sim/tests/test_engine_airtime.py
git commit -m "feat(sim): engine airtime accounting — charged/available time + offered/served blobs"
```

---

## Task 4: Metrics — utilization + windowed circulation

**Files:**
- Modify: `sim/soup_sim/metrics.py`, `sim/soup_sim/scenario.py` (snapshot counters)
- Test: `sim/tests/test_metrics_airtime.py` (CREATE)

**Interfaces:**
- Produces: `Metrics.utilization(charged, available) -> float`; `Metrics.utilization_vs_offered(charged, offered_airtime) -> float`; `circulated_per_min(transmissions_in_window, measure_window) -> float`. Scenario snapshots `eng.transmissions` at warmup-end and measure-end so circulation excludes warmup.

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
    assert abs(m.utilization(charged=30.0, available=120.0) - 0.25) < 1e-9
    assert m.utilization(charged=0.0, available=0.0) == 0.0          # no contact -> 0, not div0
    # 240 transfers over a 120 s (=2 min) window -> 120/min
    assert abs(m.circulated_per_min(transmissions_in_window=240, measure_window=120.0) - 120.0) < 1e-9
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py -q`
Expected: FAIL (`AttributeError: utilization`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/metrics.py  (append methods)
    def utilization(self, charged: float, available: float) -> float:
        return charged / available if available > 0 else 0.0

    def utilization_vs_offered(self, charged: float, offered_airtime: float) -> float:
        return charged / offered_airtime if offered_airtime > 0 else 0.0

    def circulated_per_min(self, transmissions_in_window: int, measure_window: float) -> float:
        minutes = measure_window / 60.0
        return transmissions_in_window / minutes if minutes > 0 else 0.0
```

In `scenario.run_one`, snapshot `tx0 = eng.transmissions` right after warmup+inject and `tx1 = eng.transmissions` after the measure window, and return `circulated_per_min`, `utilization`, `utilization_vs_offered` (offered airtime = `budget.charged_airtime(eng.offered_blobs, mean_contenders)` proxy, documented), `charged_airtime`, `available_contact_time` in the result dict.

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py tests/test_scenario.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/metrics.py sim/soup_sim/scenario.py sim/tests/test_metrics_airtime.py
git commit -m "feat(sim): airtime utilization + windowed circulated-blobs/min metrics"
```

---

## Task 5: Censoring-aware latency (T50) + delivery ratio jointly

**Files:**
- Modify: `sim/soup_sim/metrics.py`
- Test: `sim/tests/test_metrics_airtime.py`

**Interfaces:**
- Produces: `Metrics.t50() -> float | None` (time to 50% of the fair-chance cohort delivered; `None`/"censored" if <50% ever delivered), `Metrics.km_points() -> list[tuple[float,float]]` (time, cumulative delivered fraction), `Metrics.delivered_only_mean_latency() -> float` (labelled LOWER bound). T50 uses the fair-chance cohort denominator (TTL-censored undelivered count against, not dropped).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_metrics_airtime.py  (append)
from soup_sim.blob import Blob
def test_t50_is_censoring_aware():
    c = _cfg(ttl=100.0, measure_window=100.0)
    m = Metrics(c, warmup_end=0.0, measure_window=100.0)
    # 4 fair-chance messages; deliver 1@t=10, 1@t=20, 1@t=80; one never delivered (censored)
    for i in range(4):
        b = Blob(i, 0.0, 100.0, 1.0); m.register(b, 0, 1)
    for (i, t) in [(0, 10.0), (1, 20.0), (2, 80.0)]:
        m.delivered_at[i] = t
    # 50% of 4 = 2 delivered -> reached at t=20
    assert abs(m.t50() - 20.0) < 1e-9
    # if only 1 of 4 delivered, never reaches 50% -> None (censored), NOT a small delivered-only mean
    m2 = Metrics(c, warmup_end=0.0, measure_window=100.0)
    for i in range(4):
        m2.register(Blob(i, 0.0, 100.0, 1.0), 0, 1)
    m2.delivered_at[0] = 5.0
    assert m2.t50() is None
    assert m2.delivery_ratio() == 0.25
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_metrics_airtime.py::test_t50_is_censoring_aware -q`
Expected: FAIL (`AttributeError: t50`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/metrics.py  (append)
    def km_points(self):
        fc = self.fair_chance_ids()
        total = len(fc)
        if total == 0:
            return []
        lat = sorted(self.delivered_at[b] - self.created[b] for b in fc if b in self.delivered_at)
        pts, cum = [], 0
        for t in lat:
            cum += 1
            pts.append((t, cum / total))          # denominator = full cohort (censored count against)
        return pts

    def t50(self):
        for (t, frac) in self.km_points():
            if frac >= 0.5:
                return t
        return None                               # never reached 50% -> censored, not a flattering mean

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
git commit -m "feat(sim): censoring-aware latency (T50 + KM points) reported with delivery ratio"
```

---

## Task 6: Binding-fraction decomposition

**Files:**
- Modify: `sim/soup_sim/metrics.py` (or `knee.py`); place with the gate in `knee.py`.
- Test: `sim/tests/test_knee.py` (CREATE)

**Interfaces:**
- Produces: `binding_decomposition(offered_blobs, served_blobs, setup_starved_contacts, total_contacts) -> dict` with keys `contention_bound, setup_starved, demand_limited` summing to 1.0. `contention_bound` = fraction of offered-but-not-served attributable to per-step airtime quantization/goodput; `setup_starved` = fraction of contacts where `t_setup_at(n) >= contact_duration`; `demand_limited` = offered≈served (peer had little to gain).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_knee.py  (CREATE)
from soup_sim.knee import binding_decomposition
def test_binding_decomposition_regimes():
    # demand-limited: nearly everything offered got served
    d = binding_decomposition(offered_blobs=100, served_blobs=98, setup_starved_contacts=0, total_contacts=50)
    assert d["demand_limited"] > 0.9 and abs(sum(d.values()) - 1.0) < 1e-9
    # setup-starved: many contacts too short to handshake
    d = binding_decomposition(offered_blobs=100, served_blobs=10, setup_starved_contacts=45, total_contacts=50)
    assert d["setup_starved"] >= d["contention_bound"]
    # contention-bound: contacts fine, but airtime couldn't move the backlog
    d = binding_decomposition(offered_blobs=100, served_blobs=10, setup_starved_contacts=0, total_contacts=50)
    assert d["contention_bound"] > 0.8
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py::test_binding_decomposition_regimes -q`
Expected: FAIL (no module `soup_sim.knee`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/knee.py  (CREATE)
def binding_decomposition(offered_blobs, served_blobs, setup_starved_contacts, total_contacts):
    offered = max(1, offered_blobs)
    unmet = max(0, offered_blobs - served_blobs)
    demand = served_blobs / offered                       # share of demand actually satisfied
    starved = (setup_starved_contacts / max(1, total_contacts)) * (unmet / offered)
    contention = (unmet / offered) - starved
    raw = {"demand_limited": demand, "setup_starved": max(0.0, starved),
           "contention_bound": max(0.0, contention)}
    s = sum(raw.values()) or 1.0
    return {k: v / s for k, v in raw.items()}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py::test_binding_decomposition_regimes -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/knee.py sim/tests/test_knee.py
git commit -m "feat(sim): binding-fraction decomposition (contention/setup-starved/demand)"
```

---

## Task 7: Saturation-knee estimator

**Files:**
- Modify: `sim/soup_sim/knee.py`
- Test: `sim/tests/test_knee.py`

**Interfaces:**
- Produces: `find_knee(densities, per_rep_circulation, rng, n_boot=200) -> dict` with `{"knee": float|None, "ci": (lo,hi)|None, "status": "knee"|"no_knee_in_range"}`. Knee = argmax of mean circulated/min refined by a local quadratic-in-log(density) fit around the argmax (anti grid-pinning); bootstrap over reps for the CI; **monotone curve ⇒ `status="no_knee_in_range"`, `knee=None`** (NOT NaN). MUST NOT call `crossing_0p5`/`midpoint_with_ci`.

- [ ] **Step 1: Write the failing test (planted peak + monotone)**

```python
# sim/tests/test_knee.py  (append)
import numpy as np
from soup_sim.knee import find_knee
def test_find_knee_recovers_planted_peak():
    dens = np.linspace(1.0, 20.0, 20)
    peak = 9.0
    mean = 100.0 - 2.0 * (np.log(dens) - np.log(peak)) ** 2 * 50.0   # quadratic-in-log peak at 9
    reps = np.array([mean + np.array([0.5, -0.5, 0.2]) for _ in range(1)]).reshape(len(dens), 3) \
        if False else np.stack([mean, mean + 0.3, mean - 0.3], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "knee"
    assert abs(out["knee"] - peak) < 1.5
def test_find_knee_monotone_returns_no_knee():
    dens = np.linspace(1.0, 20.0, 20)
    mean = 100.0 - 3.0 * dens                                        # strictly decreasing
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
def _knee_point(dens, mean):
    k = int(np.argmax(mean))
    if k == 0 or k == len(mean) - 1:
        return None                                  # peak at an edge -> monotone in range
    lo, hi = k - 1, k + 1                             # local quadratic-in-log fit (anti grid-pinning)
    x = np.log(np.asarray(dens[lo:hi + 1], float)); y = np.asarray(mean[lo:hi + 1], float)
    a, b, _c = np.polyfit(x, y, 2)
    if a >= 0:
        return None
    return float(np.exp(-b / (2 * a)))
def find_knee(densities, per_rep_circulation, rng, n_boot=200):
    dens = np.asarray(densities, float)
    mat = np.asarray(per_rep_circulation, float)      # (n_density, reps)
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
git commit -m "feat(sim): saturation-knee estimator (argmax + quadratic-in-log fit + bootstrap; no-knee sentinel)"
```

---

## Task 8: Binding publish gate

**Files:**
- Modify: `sim/soup_sim/knee.py`
- Test: `sim/tests/test_knee.py`

**Interfaces:**
- Produces: `BINDING_THRESHOLD = 0.5`; `binding_gate(knee_result, binding_at_knee, alpha0_turns_over) -> dict` with `{"publish": bool, "label": str}`. Publishes iff `status=="knee"` AND `binding_at_knee["contention_bound"] >= BINDING_THRESHOLD` AND not `alpha0_turns_over`. Else label `"connectivity/buffer/TTL-limited"` or `"no knee in range"`.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_knee.py  (append)
from soup_sim.knee import binding_gate, BINDING_THRESHOLD
def test_binding_gate():
    knee = {"status": "knee", "knee": 9.0, "ci": (8.0, 10.0)}
    assert binding_gate(knee, {"contention_bound": 0.7}, alpha0_turns_over=False)["publish"] is True
    # alpha=0 control also turns over -> NOT airtime
    g = binding_gate(knee, {"contention_bound": 0.7}, alpha0_turns_over=True)
    assert g["publish"] is False and "connectivity" in g["label"].lower()
    # binding too low -> NOT airtime-bound
    assert binding_gate(knee, {"contention_bound": 0.2}, alpha0_turns_over=False)["publish"] is False
    # no knee -> no publish
    assert binding_gate({"status": "no_knee_in_range"}, {"contention_bound": 0.9}, False)["publish"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py::test_binding_gate -q`
Expected: FAIL (`ImportError: binding_gate`).

- [ ] **Step 3: Implement**

```python
# sim/soup_sim/knee.py  (append)
BINDING_THRESHOLD = 0.5
def binding_gate(knee_result, binding_at_knee, alpha0_turns_over):
    if knee_result.get("status") != "knee":
        return {"publish": False, "label": "no knee in range"}
    if alpha0_turns_over:
        return {"publish": False, "label": "connectivity/buffer/TTL-limited (alpha=0 control also turns over)"}
    if binding_at_knee.get("contention_bound", 0.0) < BINDING_THRESHOLD:
        return {"publish": False, "label": "connectivity/buffer/TTL-limited (binding below threshold)"}
    return {"publish": True, "label": "airtime-saturation (contention-bound at knee)"}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_knee.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/knee.py sim/tests/test_knee.py
git commit -m "feat(sim): binding publish gate (pre-registered threshold + alpha=0 control)"
```

---

## Task 9: Airtime sweep with α=0 control + cap/TTL control

**Files:**
- Modify: `sim/soup_sim/scenario.py`
- Test: `sim/tests/test_scenario_airtime.py` (CREATE)

**Interfaces:**
- Consumes: `run_one` (now returns airtime fields), `find_knee`, `binding_gate`.
- Produces: `airtime_sweep(base_cfg, densities, reps) -> dict` with `rows` (per density: circulated/min mean+CI, utilization, delivery, T50, binding decomposition), `alpha0_rows` (same sweep forced `airtime_model="linear", alpha=0, beta=0`), `knee`, `gate`. Determinism: same seed ⇒ identical output.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_scenario_airtime.py  (CREATE)
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import airtime_sweep
def base():
    return Config(n=0, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e4,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=20.0, measure_window=60.0,
                  drain=0.0, n_messages=40, seen_margin=30.0, master_seed=7,
                  airtime_model="collision", beta=0.15, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)
    
def test_airtime_sweep_has_control_and_is_deterministic():
    out1 = airtime_sweep(base(), densities=[3.0, 6.0, 9.0], reps=2)
    out2 = airtime_sweep(base(), densities=[3.0, 6.0, 9.0], reps=2)
    assert [r["circulated_per_min_mean"] for r in out1["rows"]] == [r["circulated_per_min_mean"] for r in out2["rows"]]
    assert len(out1["alpha0_rows"]) == 3            # mandatory alpha=0 control overlay
    assert "gate" in out1 and "publish" in out1["gate"]
    for r in out1["rows"]:
        assert "t50" in r and "utilization_mean" in r and "binding" in r
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_scenario_airtime.py -q`
Expected: FAIL (`ImportError: airtime_sweep`).

- [ ] **Step 3: Implement** `airtime_sweep` in `scenario.py`: loop densities×reps calling `run_one`; aggregate circulated/min (mean+CI), utilization, delivery, T50, and accumulate offered/served/setup-starved/total-contacts to build the per-density binding decomposition; build `per_rep_circulation` matrix; call `find_knee`; rerun the sweep with `replace(base_cfg, airtime_model="linear", alpha=0.0, beta=0.0)` for `alpha0_rows`; compute `alpha0_turns_over = find_knee(...).status=="knee"`; `gate = binding_gate(knee, binding_at_knee, alpha0_turns_over)`. Return the dict. (run_one must also surface `setup_starved_contacts` and `total_contacts` — add counters to the engine in this task or read from episodes: a contact is setup-starved when `t_setup_at(n) >= duration`.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_scenario_airtime.py tests/test_scenario.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/scenario.py sim/soup_sim/engine.py sim/tests/test_scenario_airtime.py
git commit -m "feat(sim): airtime density sweep with alpha=0 control overlay + knee + binding gate"
```

---

## Task 10: Report + CLI preset + provenance/bias docs

**Files:**
- Modify: `sim/soup_sim/report.py`, `sim/run.py`, `sim/README.md`
- Test: `sim/tests/test_report.py`

**Interfaces:**
- Produces: airtime CSV (density, circulated_per_min_mean+CI, utilization_mean, delivery_mean, t50, binding_contention/setup/demand, + manifest); `airtime_to_csv_string(rows, manifest)`; `run.py --preset airtime-knee` prints knee + gate verdict; README provenance table (goodput 100 kbps headline / 1.4 Mbps optimistic; β/slope citations) + one bias row per new optimistic mechanic (carrier-sense=max-degree contention, lump-at-step billing, deterministic p_fail, omitted set-reconciliation overhead, RWP-vs-clustered).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_report.py  (append)
from soup_sim.report import airtime_to_csv_string
def test_airtime_csv_has_fields():
    rows = [{"density": 6.0, "circulated_per_min_mean": 12.0, "ci_lo": 10.0, "ci_hi": 14.0,
             "utilization_mean": 0.3, "delivery_mean": 0.4, "t50": 25.0,
             "binding": {"contention_bound": 0.6, "setup_starved": 0.3, "demand_limited": 0.1}}]
    s = airtime_to_csv_string(rows, {"airtime_model": "collision"})
    assert "circulated_per_min_mean" in s and "t50" in s and "binding_contention_bound" in s
    assert "param_airtime_model" in s
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_report.py -q`
Expected: FAIL (`ImportError: airtime_to_csv_string`).

- [ ] **Step 3: Implement** `airtime_to_csv_string` (flatten `binding` dict into `binding_*` columns), optional `airtime_plot` (import-guarded; circulation vs density with α=0 overlay + knee marker), `run.py --preset airtime-knee` wiring `airtime_sweep` and printing the gate verdict and knee CI, and the README provenance/bias additions.

- [ ] **Step 4: Run to verify it passes + FULL suite green**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all prior + new).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/report.py sim/run.py sim/README.md sim/tests/test_report.py
git commit -m "feat(sim): airtime CSV/plot + airtime-knee preset + provenance & bias-table docs"
```

---

## Self-Review

**1. Spec coverage:** §3.1 collision model + decoupled contenders + model band + α=0 control → Tasks 1,2,9; §3.2 utilization + circulation → Task 4; §3.3 knee + binding gate → Tasks 6,7,8; §3.4 censoring latency + cap/TTL control + provenance → Tasks 5,9,10. Model-distinguishability test (§3.1) → Task 1. Planted-peak (§3.3) → Task 7.

**2. Model-uncertainty band (§3.1):** the sweep can be run under both `airtime_model` values; the band is reported by running the preset twice (collision vs linear) — documented in README. (Not a separate task; it's two CLI runs over the same `airtime_sweep`.)

**3. Type consistency:** `find_knee` returns `status`/`knee`/`ci`; `binding_gate` consumes that dict + a `binding_at_knee` dict with `contention_bound`; `airtime_sweep` returns `rows`/`alpha0_rows`/`knee`/`gate`. Consistent across Tasks 7–10.

**4. Determinism & non-regression:** new config fields default to current behavior, so `test_engine_fidelity.py` and `test_integration_percolation.py` stay green; each task re-runs them where it touches the engine.
