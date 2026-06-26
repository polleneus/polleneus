# Anonymity Slice 3 · PR-1 — Adversary infrastructure + baseline exposure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build the passive receiver-grid adversary as a **non-participating overlay** on the trusted engine, plus the estimators and the baseline **source-exposure** measurement, gated by a **must-localize capability control** — so that *before* any defense is ever credited (PR-2), we have proven the attack actually localizes the naked originator.

**Architecture:** Adversary receivers are a static position list the engine checks **inline** during the real sim (they never enter `neighbor_pairs`/contention/exchange, so they cannot perturb delivery; default-empty ⇒ bit-identical to the merged engine). The engine records, behind a default-OFF flag, (a) per-(receiver, message) **first-hear time** and (b) a per-step **position log** (for candidate/originator positions over time). `adversary.py` places receivers + runs estimators; `anonymity.py` scores localization + runs the capability/exposure gates; `scenario.py` sweeps coverage f.

**Tech Stack:** Python 3, numpy, pytest (`pythonpath=["."]`), matplotlib (optional). Determinism via `cfg.rng(*path)`.

## Global Constraints
- **Every anonymity number is an UPPER BOUND on anonymity** (a stronger adversary localizes better); **never** a floor/guarantee.
- **Scope tag travels with every emitted number** (CLI/CSV/manifest): `[SINGLE-EVENT, EXTERNAL-PASSIVE; intersection+insider NOT modeled; UPPER BOUND on anonymity]`. A test asserts no anonymity CSV/print lacks it.
- **Non-regression:** adversary recording defaults OFF ⇒ engine bit-identical (slices 1–2 gates green: `test_engine_fidelity.py`, `test_integration_percolation.py`, `test_engine_airtime.py`).
- **Determinism:** receiver placement = `cfg.rng(4)`; estimator tie-breaks/random-guess = `cfg.rng(6)` (disjoint from mobility=0/engine=1/cohort=2/buffers=(3,i); mixing=5 reserved for PR-2). Replication unit = SEED; per-message metrics estimated within a run, CI over seeds.
- **No `sender`/`recipient` tokens in engine-layer files** (lint). Adversary/estimator code lives in new non-engine modules.
- **Pre-registered constants** (named, in `anonymity.py`): `EXPOSURE_RANK1 = 0.5` (flooding "exposes" if best-estimator rank-1 prob ≥ this at realistic f); `MUSTLOC_RANK1 = 0.9`, `MUSTLOC_ERR_RADII = 0.5` (capability control: static source + near-total coverage must reach these); `ANON_SET_EPS` (anonymity-set tie band). `adversary_range = radius` (sniffer ≈ node radio range; bias noted).
- Candidate set for PR-1 = **all real nodes** (cone-restriction is a documented refinement; it only tightens the random floor, and the headline rank-1 / exact-catch metric is unaffected by set size).

## File Structure
- `sim/soup_sim/config.py` — MODIFY: `adversary_range_mult: float = 0.0` (0 ⇒ recording off / no receivers) + validation.
- `sim/soup_sim/engine.py` — MODIFY: optional `adversary_pos`; inline first-hear + position-log recorders (default off).
- `sim/soup_sim/adversary.py` — CREATE: receiver placement (uniform + chokepoint), realized coverage, estimators (first_spy, time_gradient, random_guess).
- `sim/soup_sim/anonymity.py` — CREATE: localization metrics, gates, pre-registered constants, scope tag.
- `sim/soup_sim/scenario.py` — MODIFY: `anonymity_sweep`.
- `sim/soup_sim/report.py` — MODIFY: anonymity CSV (+ scope tag) + plot.
- `sim/run.py` — MODIFY: `--preset anonymity`.
- `sim/README.md` — MODIFY: slice-3 section + bias rows.
- Tests: `test_adversary.py`, `test_anonymity.py`, `test_scenario_anonymity.py` (CREATE); `test_config.py`, `test_report.py` (MODIFY).

---

## Task 1: Engine adversary-overhearing + position recorders (default-OFF, bit-identical)

**Files:** Modify `sim/soup_sim/config.py`, `sim/soup_sim/engine.py`; Test `sim/tests/test_engine_anonymity.py` (CREATE).

**Interfaces:**
- Produces: `Config.adversary_range_mult: float = 0.0`; `Engine(..., adversary_pos=None)` (an `(R,2)` array of receiver locations or None). When `adversary_pos` is set, the engine populates `self.hearings: dict[(recv_idx, blob_id) -> first_hear_time]` and `self.position_log: list[(t, positions_copy)]`. When None (default) neither is touched ⇒ bit-identical.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_engine_anonymity.py (CREATE)
import numpy as np
from soup_sim.config import Config
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.budget import AirtimeBudget
from soup_sim.buffer import NodeBuffer
from soup_sim.blob import Blob
BIG = 10 ** 9
def cfg(**kw):
    d = dict(n=2, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0)
    d.update(kw); return Config(**d)
def _eng(c, pos, adversary_pos=None):
    mob = Mobility("static", np.array(pos, float), np.zeros((len(pos), 2)), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(len(pos))]
    return Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1),
                  on_deliver=lambda *_: None, adversary_pos=adversary_pos)

def test_receiver_hears_in_range_holder_not_out_of_range():
    c = cfg()
    recv = np.array([[60., 50.], [900., 50.]])   # R0 near node0(50,50); R1 far
    eng = _eng(c, [[50., 50.], [55., 50.]], adversary_pos=recv)
    eng.adversary_range = 10.0                     # sniffer range
    eng.inject(Blob(7, 0.0, 1e12, 1.0), 0)
    eng.run_until(3.0); eng.finalize()
    assert (0, 7) in eng.hearings                  # R0 (dist 10 from node0) hears blob 7
    assert (1, 7) not in eng.hearings              # R1 (far) never hears it
    assert len(eng.position_log) >= 1

def test_adversary_off_is_bit_identical():
    def run(adv):
        c = cfg(n=2)
        eng = _eng(c, [[50., 50.], [55., 50.]], adversary_pos=adv)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0); eng.run_until(5.0); eng.finalize()
        return eng.transmissions, list(eng.episodes)
    assert run(None) == run(None)
    # with receivers present, the REAL sim outcome is unchanged (receivers don't participate)
    base = run(None)
    c = cfg(n=2); eng = _eng(c, [[50., 50.], [55., 50.]], adversary_pos=np.array([[60., 50.]]))
    eng.adversary_range = 10.0
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0); eng.run_until(5.0); eng.finalize()
    assert (eng.transmissions, list(eng.episodes)) == base   # non-perturbing
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_anonymity.py -q`
Expected: FAIL (`Engine() got unexpected keyword 'adversary_pos'`).

- [ ] **Step 3: Implement**

`config.py`: add `adversary_range_mult: float = 0.0` after the PR-2 fields; validate `>= 0`.

`engine.py.__init__`: add param `adversary_pos=None`; store `self.adversary_pos = adversary_pos`, `self.adversary_range = 0.0`, `self.hearings = {}`, `self.position_log = []`.

In `_process_step`, at the END (after `self.t = t + dt_step`), if `self.adversary_pos is not None`:
```python
        if self.adversary_pos is not None:
            self.position_log.append((t, p0.copy()))
            r2 = self.adversary_range * self.adversary_range
            for li, L in enumerate(self.adversary_pos):
                for k in range(len(p0)):
                    if (p0[k][0]-L[0])**2 + (p0[k][1]-L[1])**2 <= r2:   # walls metric; receivers static
                        for bid in self.buffers[k].ids():
                            self.hearings.setdefault((li, bid), t)
```
(Receivers are NOT added to `neighbor_pairs`/`_degrees`/`active`, so contention/exchange/airtime are untouched.)

- [ ] **Step 4: Run to verify it passes (+ non-regression)**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest tests/test_engine_anonymity.py tests/test_engine_fidelity.py tests/test_engine_airtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/config.py sim/soup_sim/engine.py sim/tests/test_engine_anonymity.py
git commit -m "feat(sim): engine adversary-overhearing + position recorders (default-OFF, non-perturbing)"
```

---

## Task 2: Receiver placement + realized coverage

**Files:** Create `sim/soup_sim/adversary.py`; Test `sim/tests/test_adversary.py` (CREATE).

**Interfaces:**
- Produces: `place_receivers(cfg, f, mode, rng) -> np.ndarray` (`(R,2)`), `mode in {"uniform","chokepoint"}` (chokepoint biases toward a node-position sample); `realized_coverage(receivers, adv_range, cfg, rng, n_mc=20000) -> float` (Monte-Carlo fraction of arena within `adv_range` of any receiver).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_adversary.py (CREATE)
import numpy as np
from soup_sim.config import Config
from soup_sim.adversary import place_receivers, realized_coverage
def cfg(**kw):
    d = dict(n=50, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e4,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=60.0, master_seed=3)
    d.update(kw); return Config(**d)
def test_realized_coverage_increases_with_f():
    c = cfg(); adv_range = c.radius
    covs = []
    for f in (0.1, 0.4, 0.8):
        recv = place_receivers(c, f, "uniform", c.rng(4))
        covs.append(realized_coverage(recv, adv_range, c, c.rng(4)))
    assert covs[0] < covs[1] < covs[2]
    assert 0.0 <= covs[0] and covs[2] <= 1.0
def test_placement_deterministic():
    c = cfg()
    a = place_receivers(c, 0.5, "uniform", c.rng(4))
    b = place_receivers(c, 0.5, "uniform", c.rng(4))
    assert np.array_equal(a, b)
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/test_adversary.py -q` → ImportError.

- [ ] **Step 3: Implement** `adversary.py`: `place_receivers` lays a grid whose spacing makes disk-coverage ≈ f (spacing `s` s.t. `π·adv_range² / s² ≈ f`, clamped), jitters each point by `rng`; "chokepoint" draws receiver centers from a sample of node start positions (`placement`-like) to cluster them. `realized_coverage` samples `n_mc` uniform arena points, fraction within `adv_range` of any receiver (torus-aware via min-image).

- [ ] **Step 4: Run to verify it passes** — `pytest tests/test_adversary.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/adversary.py sim/tests/test_adversary.py
git commit -m "feat(sim): adversary receiver placement (uniform+chokepoint) + realized coverage"
```

---

## Task 3: Estimators — first-spy, time-gradient, random-guess

**Files:** Modify `sim/soup_sim/adversary.py`; Test `sim/tests/test_adversary.py`.

**Interfaces:**
- Produces: `estimate(method, hearings_for_msg, receivers, candidates_pos, rng) -> {"point": (x,y), "scores": np.ndarray}` where `method in {"first_spy","time_gradient","random_guess"}`, `hearings_for_msg = list[(recv_idx, first_hear_time)]`, `candidates_pos = (C,2)` positions at the reference time, returns a per-candidate suspicion score (lower = more suspicious) and a point estimate. `first_spy`: point = earliest receiver's location; scores = distance to it. `time_gradient`: scores = residual of candidate explaining the arrival-order (a candidate closer to early receivers / farther from late ones scores lower). `random_guess`: scores = `rng.permutation`.

- [ ] **Step 1: Write the failing test (estimators localize a known source)**

```python
# sim/tests/test_adversary.py (append)
from soup_sim.adversary import estimate
def test_first_spy_points_at_earliest_receiver():
    recv = np.array([[0., 0.], [100., 0.], [200., 0.]])
    hearings = [(0, 5.0), (1, 9.0), (2, 14.0)]          # R0 earliest
    cands = np.array([[2., 0.], [150., 0.]])            # cand0 near R0
    out = estimate("first_spy", hearings, recv, cands, np.random.default_rng(0))
    assert np.allclose(out["point"], [0., 0.])
    assert out["scores"][0] < out["scores"][1]          # cand0 (near R0) more suspicious
def test_time_gradient_localizes_better_than_random_on_a_gradient():
    recv = np.array([[0., 0.], [50., 0.], [100., 0.], [150., 0.]])
    # source near x=0: arrival times increase with x
    hearings = [(0, 1.0), (1, 3.0), (2, 5.0), (3, 7.0)]
    cands = np.array([[1., 0.], [80., 0.], [149., 0.]])
    tg = estimate("time_gradient", hearings, recv, cands, np.random.default_rng(0))
    assert int(np.argmin(tg["scores"])) == 0            # candidate nearest the source ranks top
```

- [ ] **Step 2: Run to verify it fails** — ImportError `estimate`.

- [ ] **Step 3: Implement** the three methods in `adversary.py` per the interface.

- [ ] **Step 4: Run to verify it passes** — `pytest tests/test_adversary.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/adversary.py sim/tests/test_adversary.py
git commit -m "feat(sim): adversary estimators (first-spy, time-gradient, random-guess)"
```

---

## Task 4: Anonymity metrics + scope tag

**Files:** Create `sim/soup_sim/anonymity.py`; Test `sim/tests/test_anonymity.py` (CREATE).

**Interfaces:**
- Produces: `SCOPE_TAG` (str); `localization_error(point, true_pos, cfg) -> float` (torus-aware); `rank_of(scores, true_idx) -> int`; `rank1` helper; `anonymity_set_size(scores, ANON_SET_EPS) -> int`; pre-registered constants `EXPOSURE_RANK1, MUSTLOC_RANK1, MUSTLOC_ERR_RADII, ANON_SET_EPS`.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_anonymity.py (CREATE)
import numpy as np
from soup_sim.anonymity import localization_error, rank_of, anonymity_set_size, SCOPE_TAG
from soup_sim.config import Config
def cfg(**kw):
    d = dict(n=2, width=100.0, height=100.0, radius=10.0, boundary="torus", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e9, buffer_cap=10**9, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e9, master_seed=0)
    d.update(kw); return Config(**d)
def test_localization_error_torus():
    c = cfg()
    assert abs(localization_error((1., 1.), (99., 99.), c) - np.hypot(2., 2.)) < 1e-9  # wraps
def test_rank_and_anon_set():
    scores = np.array([0.1, 0.2, 0.2, 5.0])
    assert rank_of(scores, 0) == 0                       # best score -> rank 0 (exact catch)
    assert rank_of(scores, 3) == 3
    assert anonymity_set_size(scores, eps=0.15) == 3     # 0.1,0.2,0.2 within eps band of best
def test_scope_tag_present():
    assert "UPPER BOUND" in SCOPE_TAG and "intersection" in SCOPE_TAG.lower()
```

- [ ] **Step 2: Run to verify it fails** — ImportError.

- [ ] **Step 3: Implement** `anonymity.py` (torus-aware distance via min-image; `rank_of` = count of strictly-better scores; `anonymity_set_size` = count within `eps` of the best; constants; `SCOPE_TAG = "[SINGLE-EVENT, EXTERNAL-PASSIVE; intersection+insider NOT modeled; UPPER BOUND on anonymity]"`).

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/anonymity.py sim/tests/test_anonymity.py
git commit -m "feat(sim): anonymity metrics (loc error, rank, anon-set upper bound) + scope tag"
```

---

## Task 5: Capability (must-localize) + exposure gates

**Files:** Modify `sim/soup_sim/anonymity.py`; Test `sim/tests/test_anonymity.py`.

**Interfaces:**
- Produces: `mustlocalize_gate(static_dense_result) -> {"ok": bool, "label": str}` (best-estimator on a static source + near-total coverage must reach `rank1 >= MUSTLOC_RANK1` AND `median_err <= MUSTLOC_ERR_RADII * radius`); `exposure_gate(best_rank1, beats_random) -> {"exposed": bool, "label": str}` (exposed iff `best_rank1 >= EXPOSURE_RANK1` AND beats_random).

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_anonymity.py (append)
from soup_sim.anonymity import mustlocalize_gate, exposure_gate
def test_mustlocalize_gate():
    assert mustlocalize_gate({"rank1": 0.95, "median_err_radii": 0.2})["ok"] is True
    assert mustlocalize_gate({"rank1": 0.3, "median_err_radii": 0.2})["ok"] is False   # too weak
def test_exposure_gate():
    assert exposure_gate(best_rank1=0.7, beats_random=True)["exposed"] is True
    assert exposure_gate(best_rank1=0.7, beats_random=False)["exposed"] is False        # no signal
    assert exposure_gate(best_rank1=0.1, beats_random=True)["exposed"] is False          # below threshold
```

- [ ] **Step 2: Run to verify it fails** — ImportError.

- [ ] **Step 3: Implement** both gates against the pre-registered constants.

- [ ] **Step 4: Run to verify it passes** — PASS.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/anonymity.py sim/tests/test_anonymity.py
git commit -m "feat(sim): must-localize capability gate + exposure gate (pre-registered thresholds)"
```

---

## Task 6: Anonymity sweep over coverage f (+ must-localize control wired)

**Files:** Modify `sim/soup_sim/scenario.py`; Test `sim/tests/test_scenario_anonymity.py` (CREATE).

**Interfaces:**
- Produces: `anonymity_sweep(base_cfg, f_values, reps, placement="uniform") -> {"rows", "mustlocalize", "scope_tag"}`. Each run: place receivers (coverage f), run the engine with `adversary_pos`, for every originated cohort message compute the best-estimator (over first_spy/time_gradient) localization error (origination-time + first-hear-time), rank, rank-1, anonymity-set, and undetected fraction; aggregate per f with CI over seeds. Plus a separate **must-localize control** run (static source, f≈1) feeding `mustlocalize_gate`, and the random-guess floor. Deterministic by seed.

- [ ] **Step 1: Write the failing test (fast/tiny)**

```python
# sim/tests/test_scenario_anonymity.py (CREATE)
import pytest
from soup_sim.config import Config
from soup_sim.scenario import anonymity_sweep
def tiny():
    return Config(n=0, width=40.0, height=40.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=20.0, buffer_cap=40, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=4.0, measure_window=10.0,
                  drain=0.0, n_messages=12, seen_margin=20.0, master_seed=5)
def test_anonymity_sweep_structure_and_determinism():
    out1 = anonymity_sweep(tiny(), [0.3, 0.7], reps=1)
    out2 = anonymity_sweep(tiny(), [0.3, 0.7], reps=1)
    assert out1["rows"] == out2["rows"]                          # deterministic
    assert "UPPER BOUND" in out1["scope_tag"]
    assert "ok" in out1["mustlocalize"]
    for r in out1["rows"]:
        assert {"f", "realized_coverage", "rank1_prob", "median_err_origin",
                "undetected_fraction", "beats_random"} <= set(r)
```

- [ ] **Step 2: Run to verify it fails** — ImportError.

- [ ] **Step 3: Implement** `anonymity_sweep` (and a `_run_one_anonymity(cfg, receivers)` helper that calls the engine with `adversary_pos` + `adversary_range`, then scores via `adversary.estimate` + `anonymity.*`). Use `cfg.rng(4)` for placement, `cfg.rng(6)` for estimator randomness, `_seed_for` per (f-index, rep). Undetected = cohort messages with no `(recv, mid)` hearing. Reuse `mean_ci` for the per-seed CIs.

- [ ] **Step 4: Run to verify it passes** — `pytest tests/test_scenario_anonymity.py tests/test_scenario.py -q` → PASS.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/scenario.py sim/tests/test_scenario_anonymity.py
git commit -m "feat(sim): anonymity_sweep over coverage f + must-localize control"
```

---

## Task 7: Report + CLI preset + docs (scope tag travels)

**Files:** Modify `sim/soup_sim/report.py`, `sim/run.py`, `sim/README.md`; Test `sim/tests/test_report.py`.

**Interfaces:**
- Produces: `anonymity_to_csv_string(rows, manifest, scope_tag) -> str` (a leading `# <scope_tag>` comment line + columns f, realized_coverage, rank1_prob, median_err_origin, median_err_firsthear, anon_set_mean, undetected_fraction, beats_random + `param_*`); `run.py --preset anonymity` prints the exposure-gate verdict, the must-localize verdict, and the scope tag; README slice-3 section + bias rows.

- [ ] **Step 1: Write the failing test**

```python
# sim/tests/test_report.py (append)
def test_anonymity_csv_carries_scope_tag():
    from soup_sim.report import anonymity_to_csv_string
    rows = [{"f": 0.5, "realized_coverage": 0.48, "rank1_prob": 0.3, "median_err_origin": 22.0,
             "median_err_firsthear": 18.0, "anon_set_mean": 6.0, "undetected_fraction": 0.1,
             "beats_random": True}]
    s = anonymity_to_csv_string(rows, {"master_seed": 5}, "[UPPER BOUND on anonymity ...]")
    assert s.splitlines()[0].startswith("#") and "UPPER BOUND" in s.splitlines()[0]
    assert "rank1_prob" in s and "param_master_seed" in s
```

- [ ] **Step 2: Run to verify it fails** — ImportError.

- [ ] **Step 3: Implement** `anonymity_to_csv_string` (scope-tag comment line first), optional `anonymity_plot` (rank-1 / median-error vs f with the random-guess floor overlaid + the scope tag in the title), `run.py --preset anonymity` (uses `anonymity_sweep`; prints scope tag + both gate verdicts), README slice-3 section + bias rows (single-event optimistic; uniform-placement optimistic if chokepoint not run; adversary unit-disk optimistic; worst-case aux conservative-for-exposure).

- [ ] **Step 4: Run to verify it passes + FULL default suite green**

Run: `cd "C:/Users/rob/Documents/meldingx/sim" && .venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe run.py --preset anonymity --out out/anon.csv`
Expected: PASS; CLI prints exposure + must-localize verdicts + scope tag.

- [ ] **Step 5: Commit**
```bash
git add sim/soup_sim/report.py sim/run.py sim/README.md sim/tests/test_report.py
git commit -m "feat(sim): anonymity CSV/plot (scope-tag-carrying) + anonymity preset + slice-3 docs"
```

---

## Self-Review
**1. Spec coverage (PR-1 scope):** overlay adversary (Task 1, non-perturbing inline recorder — spec §7); receiver placement uniform+chokepoint + realized coverage (Task 2 — §1); estimators incl. a strong time-gradient + random-guess floor (Task 3 — §3); pinned metrics incl. both reference times + anonymity-set upper bound + undetected fraction (Tasks 4,6 — §2); **must-localize capability control + exposure gate** (Task 5 — §4 Control A/B + exposure); scope tag travels with every emitted number (Tasks 4,6,7 — honesty banner); sweep over f (Task 6 — §1); non-regression by default-off (Task 1). Defenses + defense-power gate + confound controls are **PR-2** (not here).
**2. Deferred to PR-2 (correctly):** mixing, originate-gate, origin-vs-relay estimator, TTL=∞/relay-density confound controls, defense-scope disclaimer.
**3. Determinism/non-regression:** new config field defaults to off; placement=rng(4), estimator=rng(6) disjoint; Task 1 re-runs the slices 1–2 gates; CI over seeds.
**4. Type consistency:** `estimate(...)->{"point","scores"}` consumed by `anonymity.*` and `anonymity_sweep`; gates consume `{"rank1","median_err_radii"}` / `(best_rank1, beats_random)`; sweep returns `{"rows","mustlocalize","scope_tag"}` consumed by report/CLI.
**5. Execution judgment:** the MLE/diffusion estimator (spec §3) is approximated here by `time_gradient`; if Control A (must-localize) fails to reach `MUSTLOC_RANK1` under static+dense coverage, the estimator is too weak and the build must strengthen `time_gradient` (toward a true arrival-time MLE) before any exposure number publishes — the capability gate enforces this.
