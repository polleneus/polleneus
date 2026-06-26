# Anonymity Slice 3 · PR-1 — Adversary infrastructure + baseline exposure Implementation Plan — v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

> **v2 (folds plan-review round 1):** estimator reframed to **diffusion/epidemic source-localization** (the engine floods epidemically — no `distance/c`); **post-hoc overlay** (engine adds only a position log; the overlay computes hearings for ANY receiver layout from `acquired` + positions + blob TTL — one sim run feeds all placements/coverage, both arms cheap); **chokepoint placement is the reported headline** (uniform shown only as the weaker arm); statistics pinned (`MIN_MESSAGES_PER_RUN`, `MIN_REPS`, CI over seeds, rank-1 refused below the floor); exposure gate uses a **margin** (beats_random is vacuous at 1/N); must-localize gate is **per-estimator + monotone-power**, not best-of-on-the-easy-case; metrics **conditional on detection** + undetected censoring; estimator-quality error measured at **first-hear position** (origin-time error + the gap = mobility-cloaking, reported separately); P90/P95 tail added; scope tag travels as a **CSV column + manifest field + enforced by a test**; adversary range wired from config; RNG disjointness test extended.

**Goal:** Build the passive receiver-grid adversary as a **post-hoc overlay** on the trusted engine, plus a *strong* diffusion-source estimator and the baseline **source-exposure** measurement, gated by a **must-localize capability control** — so that before any defense is credited (PR-2), we have proven (or honestly failed to prove) that the attack localizes the naked originator.

**Architecture:** The engine, behind a default-OFF flag, records a per-step **position log** (it already records per-(node,blob) acquire times in `acquired`). The overlay (`adversary.py`) places receivers and computes, for any layout, `first_hear[L,m]` = earliest step a holder of m (held over `[acquire, created+ttl]`) is within adversary-range of L — from the log alone, **no re-simulation, no engine nodes added** ⇒ contention/delivery untouched, bit-identical when off. `anonymity.py` scores localization + runs the capability/exposure gates; `scenario.py` sweeps coverage f and reports the stronger placement arm.

**Tech Stack:** Python 3, numpy, pytest (`pythonpath=["."]`), matplotlib (optional). Determinism via `cfg.rng(*path)`.

## Global Constraints
- **Every anonymity number is an UPPER BOUND on anonymity** (a stronger adversary localizes better); **never** a floor/guarantee.
- **Scope tag travels with every emitted number as a real carrier** (not a strippable comment): a `scope_tag` **CSV column on every row** + a manifest field + present in CLI stdout and plot title. A test asserts every anonymity emitter (CSV, plot title, `--preset anonymity` stdout via capsys) contains `SCOPE_TAG`.
- **Non-regression:** position-log recording defaults OFF ⇒ engine bit-identical (slices 1–2 gates green).
- **Determinism:** placement=`cfg.rng(4)`, estimator/Monte-Carlo=`cfg.rng(6)` (disjoint from 0/1/2/(3,i); 5 reserved for PR-2 mixing). Extend the RNG-disjointness test to cover 4 and 6. Replication unit = SEED.
- **Statistics (pinned):** `MIN_MESSAGES_PER_RUN = 150`, `MIN_REPS = 6`; per-message metrics estimated within a run, **CI over seeds** via `mean_ci`; the exposure path **refuses to emit rank-1** if messages<MIN or reps<MIN (returns "inconclusive — underpowered").
- **No `sender`/`recipient` in engine-layer files** (lint). Adversary/estimator code lives in new modules.
- **Pre-registered constants** (named in `anonymity.py`): `EXPOSURE_RANK1 = 0.5`, `EXPOSURE_MARGIN_K = 5` (exposed iff best detected-conditional rank-1 ≥ max(EXPOSURE_RANK1, K·random_floor)); `MUSTLOC_RANK1 = 0.9`, `MUSTLOC_ERR_RADII = 0.5`; `ANON_SET_EPS`. `adversary_range = cfg.adversary_range_mult * cfg.radius`.
- **Falsifiable prediction (stated up front):** *we predict the reachability estimator's detected-conditional rank-1 ≥ 0.5 at chokepoint coverage f ≥ ~0.4; if it never crosses 0.5, naked flooding does NOT cleanly expose the source on this axis (a publishable null).* 
- **Metrics conditional on detection:** rank-1 / localization error are computed over messages heard by ≥1 receiver; `undetected_fraction` reported separately (censoring); an `unconditional_rank1 = rank1 · (1−undetected_fraction)` is also reported. Estimator-quality error is measured against the originator's **first-hear-time** position; the **origination-time** error and the gap (mobility-cloaking) are reported separately.
- Candidate set (PR-1) = all real nodes; anonymity-set always labelled an UPPER BOUND (cone deferred — noted optimistic in the bias table).

## File Structure
- `sim/soup_sim/config.py` — MODIFY: `adversary_range_mult: float = 0.0` + validation.
- `sim/soup_sim/engine.py` — MODIFY: default-OFF per-step position log (`record_positions` flag).
- `sim/soup_sim/adversary.py` — CREATE: placement (uniform+chokepoint), realized coverage, overhearing-from-log, estimators (first_spy, reachability, random_guess).
- `sim/soup_sim/anonymity.py` — CREATE: metrics, gates, constants, SCOPE_TAG.
- `sim/soup_sim/scenario.py` — MODIFY: `anonymity_sweep`.
- `sim/soup_sim/report.py` — MODIFY: anonymity CSV (scope_tag column) + plot.
- `sim/run.py` — MODIFY: `--preset anonymity`.
- `sim/README.md` — MODIFY: slice-3 section + bias rows.
- Tests: `test_engine_anonymity.py`, `test_adversary.py`, `test_anonymity.py`, `test_scenario_anonymity.py` (CREATE); `test_config.py`, `test_report.py` (MODIFY).

---

## Task 1: Engine per-step position log (default-OFF, bit-identical)

**Files:** Modify `config.py`, `engine.py`; Test `tests/test_engine_anonymity.py` (CREATE).
**Interfaces:** `Config.adversary_range_mult: float = 0.0`; `Engine(..., record_positions=False)`. When True, `self.position_log: list[(t, positions_copy)]` is appended per step (and the origin's position at inject is recoverable from it). When False (default) ⇒ untouched ⇒ bit-identical. `acquired` (already present) is the hold-start oracle; hold end = blob `created_at + ttl`.

- [ ] **Step 1: failing test**
```python
# tests/test_engine_anonymity.py (CREATE)
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
def _eng(c, pos, record=False):
    mob = Mobility("static", np.array(pos, float), np.zeros((len(pos), 2)), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(len(pos))]
    return Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None,
                  record_positions=record)
def test_position_log_recorded_when_on():
    c = cfg(); eng = _eng(c, [[50., 50.], [55., 50.]], record=True)
    eng.inject(Blob(7, 0.0, 1e12, 1.0), 0); eng.run_until(3.0); eng.finalize()
    assert len(eng.position_log) >= 3
    t0, p0 = eng.position_log[0]
    assert p0.shape == (2, 2) and (0, 7) in eng.acquired   # acquire-time oracle present
def test_record_off_is_bit_identical():
    def run(rec):
        c = cfg(n=2); eng = _eng(c, [[50., 50.], [55., 50.]], record=rec)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0); eng.run_until(5.0); eng.finalize()
        return eng.transmissions, list(eng.episodes)
    assert run(False) == run(True)    # recording is passive: outcome identical
```
- [ ] **Step 2: run → FAIL** (`record_positions` unknown).
- [ ] **Step 3:** `config.py`: add `adversary_range_mult: float = 0.0` (validate ≥0). `engine.__init__`: `record_positions=False` param; `self.record_positions = record_positions; self.position_log = []`. In `_process_step`, after `self.t = t + dt_step`: `if self.record_positions: self.position_log.append((t, p0.copy()))`.
- [ ] **Step 4: run → PASS** + `pytest tests/test_engine_fidelity.py tests/test_engine_airtime.py -q` green.
- [ ] **Step 5: commit** `feat(sim): engine per-step position log (default-OFF, bit-identical) for anonymity overlay`

---

## Task 2: Receiver placement (uniform + chokepoint) + realized coverage

**Files:** Create `adversary.py`; Test `tests/test_adversary.py`.
**Interfaces:** `place_receivers(cfg, f, mode, rng) -> (R,2)` (`mode∈{"uniform","chokepoint"}`; chokepoint clusters toward a node-position sample); `realized_coverage(receivers, adv_range, cfg, rng, n_mc=20000) -> float`.

- [ ] **Step 1: failing test** — coverage rises with f; placement deterministic; chokepoint differs from uniform. (see spec §1)
```python
# tests/test_adversary.py (CREATE)
import numpy as np
from soup_sim.config import Config
from soup_sim.adversary import place_receivers, realized_coverage
def cfg(**kw):
    d = dict(n=50, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e4,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=60.0, master_seed=3); d.update(kw); return Config(**d)
def test_realized_coverage_increases_with_f():
    c = cfg(); rng = c.rng(4)
    covs = [realized_coverage(place_receivers(c, f, "uniform", c.rng(4)), c.radius, c, c.rng(4))
            for f in (0.1, 0.4, 0.8)]
    assert covs[0] < covs[1] < covs[2] and 0 <= covs[0] and covs[2] <= 1.0
def test_placement_deterministic():
    c = cfg()
    assert np.array_equal(place_receivers(c, 0.5, "uniform", c.rng(4)), place_receivers(c, 0.5, "uniform", c.rng(4)))
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement (uniform: grid spacing s with π·range²/s²≈f, jittered; chokepoint: centers drawn from a node-position sample so receivers cluster; `realized_coverage`: torus-aware Monte-Carlo fraction within range of any receiver).
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): adversary receiver placement (uniform+chokepoint) + realized coverage`

---

## Task 3: Overhearing from the log (post-hoc, any layout)

**Files:** Modify `adversary.py`; Test `tests/test_adversary.py`.
**Interfaces:** `hearings(receivers, adv_range, position_log, acquired, blob_ttl, cfg) -> dict[(recv_idx, blob_id) -> first_hear_time]` — for each receiver L and message m, earliest `t` in the log where some holder k of m (held over `[acquired[(k,m)], created_m + ttl]`) is within `adv_range` of L (torus-aware). Computed from the log, for any receiver set, no re-sim. (Hold assumed until TTL expiry — eviction ignored ⇒ adversary hears at least as much ⇒ conservative for the anonymity upper bound; noted.)

- [ ] **Step 1: failing test**
```python
# tests/test_adversary.py (append)
from soup_sim.adversary import hearings
def test_receiver_hears_in_range_holder_only():
    # holder of blob 7 sits at (50,50) for the whole log; R0 near, R1 far
    log = [(float(t), np.array([[50., 50.], [55., 50.]])) for t in range(5)]
    acquired = {(0, 7): 0.0}                  # node0 holds blob 7 from t=0
    recv = np.array([[58., 50.], [900., 50.]])
    c = cfg(width=2000.0, height=200.0, boundary="walls")
    h = hearings(recv, 10.0, log, acquired, {7: 1e12}, c)
    assert h[(0, 7)] == 0.0 and (1, 7) not in h
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement `hearings` (loop layout × log steps × holders; torus min-image; record first time in-range while held).
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): post-hoc overhearing from the position log (any receiver layout, no re-sim)`

---

## Task 4: Estimators — first-spy, reachability-likelihood, random-guess

**Files:** Modify `adversary.py`; Test `tests/test_adversary.py`.
**Interfaces:** `estimate(method, msg_hearings, receivers, cand_idx, cand_pos_at_hear, origin_reach, rng) -> {"point","scores"}` (lower score = more suspicious). `first_spy`: point = earliest receiver loc; scores = candidate distance to it. `reachability`: per candidate, residual between observed `(receiver, first_hear)` and the candidate's **forward time-respecting reachability time** to each receiver (`origin_reach[cand]` = precomputed earliest-reach times to each receiver from that candidate via the contact/log graph); the candidate whose predicted reach-order/time best matches observation scores lowest. `random_guess`: `rng.permutation`.

- [ ] **Step 1: failing test** — first_spy points at earliest receiver; reachability ranks the true source top on a constructed spread; reachability ≤ first_spy error on that case (stronger).
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement. `reachability` consumes precomputed per-candidate reach-times (the sweep computes them from the episode log + receiver proximity); score = sum of squared residuals (or Spearman) vs observed first-hears over the receivers that heard the message.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): diffusion-source estimators (first-spy, reachability-likelihood, random-guess)`

---

## Task 5: Anonymity metrics + constants + scope tag

**Files:** Create `anonymity.py`; Test `tests/test_anonymity.py`.
**Interfaces:** `SCOPE_TAG`; constants (`EXPOSURE_RANK1, EXPOSURE_MARGIN_K, MUSTLOC_RANK1, MUSTLOC_ERR_RADII, ANON_SET_EPS, MIN_MESSAGES_PER_RUN, MIN_REPS`); `localization_error(point, true_pos, cfg)` (torus); `rank_of(scores, true_idx)` (strict-better count + tie midrank); `anonymity_set_size(scores, eps)`; `quantiles(errs) -> (median, p90, p95)`.

- [ ] **Step 1: failing test** — torus error wraps; rank/anon-set on hand cases; SCOPE_TAG contains "UPPER BOUND" + "intersection"; constants present.
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement (`SCOPE_TAG = "[SINGLE-EVENT, EXTERNAL-PASSIVE; intersection+insider NOT modeled; UPPER BOUND on anonymity]"`).
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): anonymity metrics (error/rank/anon-set/quantiles) + pre-registered constants + scope tag`

---

## Task 6: Gates — must-localize (per-estimator + monotone), exposure (margin), no-signal

**Files:** Modify `anonymity.py`; Test `tests/test_anonymity.py`.
**Interfaces:** `mustlocalize_gate(per_estimator_results, coverage_curve) -> {"ok","label"}` — passes iff the **reachability** estimator (not best-of) reaches `rank1≥MUSTLOC_RANK1` AND `median_err≤MUSTLOC_ERR_RADII·radius` on the **slow-mobility + dense** control (NOT static — a static fully-connected arena floods in one fixpoint step → zero gradient → unlocalizable by any estimator) **AND** best-estimator median error is monotone-non-increasing (within CI) as coverage→1. `exposure_gate(best_rank1_detected, random_floor, beats_random, n_messages, n_reps) -> {"exposed","label"}` — refuses ("underpowered") if messages<MIN or reps<MIN; else exposed iff `best_rank1_detected ≥ max(EXPOSURE_RANK1, EXPOSURE_MARGIN_K·random_floor)`.

- [ ] **Step 1: failing test** — must-localize fails if reachability is weak even when first_spy is strong; fails if non-monotone; exposure refuses when underpowered; exposure margin bites when random_floor high. 
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement both gates against the constants.
- [ ] **Step 4: run → PASS.**
- [ ] **Step 5: commit** `feat(sim): must-localize (per-estimator+monotone) + margin exposure gate (underpower-refusing)`

---

## Task 7: anonymity_sweep over coverage f (both arms → headline = stronger)

**Files:** Modify `scenario.py`; Test `tests/test_scenario_anonymity.py`.
**Interfaces:** `anonymity_sweep(base_cfg, f_values, reps) -> {"rows","mustlocalize","scope_tag","headline_arm"}`. One engine run per (seed) with `record_positions=True`; from its `position_log`+`acquired` compute hearings for BOTH placement arms across all f; per arm/f and per detected cohort message compute best-estimator error (first-hear-time = estimator quality; origination-time + gap reported), rank, rank-1, anon-set, P90/P95, undetected fraction; **headline = the stronger (higher rank-1 / lower error) arm**; CI over seeds (reps≥MIN_REPS); plus a **must-localize control** (static mobility + f≈0.99) feeding `mustlocalize_gate`. Deterministic. `n` is set explicitly in `base_cfg` (coverage f is the axis, not density).

- [ ] **Step 1: failing test (tiny but valid n>0)** — structure (per-row keys incl. `rank1_prob, median_err_firsthear, median_err_origin, p90_err, undetected_fraction, beats_random, arm`), determinism, scope_tag present, `headline_arm` chosen, `mustlocalize` computed; assert ≥1 message heard at the top f (non-vacuous). Mark the realistic-power sweep `@pytest.mark.slow`.
```python
# tests/test_scenario_anonymity.py (CREATE)
import pytest
from soup_sim.config import Config
from soup_sim.scenario import anonymity_sweep
def tiny():   # n>0; smoke only — NOT a power config (rank-1 not trusted here)
    return Config(n=12, width=40.0, height=40.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=20.0, buffer_cap=40, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=4.0, measure_window=10.0,
                  drain=0.0, n_messages=10, seen_margin=20.0, master_seed=5, adversary_range_mult=1.0)
def test_anonymity_sweep_structure_and_determinism():
    a = anonymity_sweep(tiny(), [0.3, 0.7], reps=2); b = anonymity_sweep(tiny(), [0.3, 0.7], reps=2)
    assert a["rows"] == b["rows"] and "UPPER BOUND" in a["scope_tag"]
    assert a["headline_arm"] in ("uniform", "chokepoint") and "ok" in a["mustlocalize"]
    assert any(r["undetected_fraction"] < 1.0 for r in a["rows"])   # non-vacuous: something heard
    for r in a["rows"]:
        assert {"f","arm","rank1_prob","median_err_firsthear","median_err_origin","p90_err",
                "undetected_fraction","beats_random"} <= set(r)
```
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement `_run_one_anonymity(cfg)` (engine with `record_positions`, `adversary_range=cfg.adversary_range_mult*cfg.radius`) + `anonymity_sweep` (both arms from one log; reachability reach-times from the episode log; `cfg.rng(4)`/`cfg.rng(6)`; `_seed_for`; must-localize control = `replace(base_cfg, speed_min=0.5, speed_max=0.5)` [slow RWP, NOT static — a static flood has no gradient] + f≈0.99 coverage). Undetected = cohort messages with no hearing; metrics conditional on detection.
- [ ] **Step 4: run → PASS** (+ `tests/test_scenario.py` green).
- [ ] **Step 5: commit** `feat(sim): anonymity_sweep over coverage f (both arms->stronger headline) + must-localize control`

---

## Task 8: Report + CLI preset + docs (scope tag enforced everywhere)

**Files:** Modify `report.py`, `run.py`, `README.md`; Test `tests/test_report.py`.
**Interfaces:** `anonymity_to_csv_string(rows, manifest, scope_tag)` (a `scope_tag` **column** on every row + a `#`-comment + manifest `param_*`); `anonymity_plot` (rank-1 / error vs f, random floor overlaid, both arms, scope tag in title); `run.py --preset anonymity` (registered in `choices`; prints exposure verdict + must-localize verdict + scope tag); README slice-3 section + bias rows.

- [ ] **Step 1: failing test** — CSV has `scope_tag` as a **column value** (not just comment) + `rank1_prob` + `param_master_seed`; an enforcement test captures `--preset anonymity` stdout (capsys via `run.main` or a thin function) and the plot title, asserting `SCOPE_TAG` in each.
- [ ] **Step 2: run → FAIL.**
- [ ] **Step 3:** implement; **write the actual README rows** (append to the existing bias table): single-event ⇒ optimistic (dominant deferred risk); external-passive-only ⇒ optimistic; uniform shown only as the weaker arm, chokepoint is the headline; adversary unit-disk ⇒ optimistic; candidate-set=all-nodes ⇒ optimistic (anon-set crowd inflated, cone deferred); worst-case-aux ⇒ conservative-for-exposure. README slice-3 prose carries "UPPER BOUND on anonymity, never a floor" + the falsifiable prediction + "anonymity-set (UPPER BOUND)" (never "K-anonymity").
- [ ] **Step 4: run → PASS + FULL default suite** `pytest -q` green; `run.py --preset anonymity --out out/anon.csv` prints both verdicts + scope tag.
- [ ] **Step 5: commit** `feat(sim): anonymity CSV/plot (scope-tag column) + anonymity preset + slice-3 docs`

---

## Self-Review
**Spec coverage (PR-1):** post-hoc overlay (Tasks 1,3 — spec §7); uniform+chokepoint placement, chokepoint = headline (Tasks 2,7 — §1); diffusion-source estimators incl. a strong reachability-likelihood + random floor (Task 4 — §3); pinned metrics incl. both reference times, conditional-on-detection + undetected censoring, P90/P95, anon-set upper bound (Tasks 5,7 — §2); must-localize (per-estimator + monotone) + margin exposure gate + underpower refusal (Task 6 — §4); scope tag as column+manifest+CLI+title, test-enforced (Tasks 5,7,8 — banner); statistics MIN_MESSAGES/MIN_REPS + CI over seeds (Task 6,7 — §7); non-regression default-off (Task 1). **Deferred to PR-2 (correctly):** mixing, originate-gate, origin-vs-relay estimator, TTL=∞/relay-density confound controls, defense-scope disclaimer.
**Folded round-1 findings:** estimator physics (epidemic, not radial) → reachability estimator; inline→post-hoc overlay; chokepoint headline; statistics floor + underpower refusal; margin exposure gate; per-estimator+monotone must-localize; conditional-on-detection + undetected; mobility-cloaking separated (first-hear vs origin-time error); P90/P95; scope-tag carrier (column) + enforcement test; range wired from config; RNG disjointness test; tasks 6/7/8 split out.
**Execution judgment:** the reachability estimator's strength is enforced by the per-estimator must-localize gate + the monotone-power check; if it fails on a static source at f≈1, the build must strengthen it (toward a fuller forward-reachability likelihood) before any exposure number publishes — and if it still can't, that null ("source-localization is hard under epidemic flooding") is the honest reported result (spec §3).
