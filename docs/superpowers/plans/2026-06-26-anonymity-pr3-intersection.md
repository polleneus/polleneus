# Slice 3 PR-3 — Multi-Session Intersection Attack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure how fast sender anonymity collapses when one device originates K linkable messages and the adversary fuses its per-message rankings — the spec's named dominant deferred threat.

**Architecture:** Additive, default-inert overlay reusing the PR-1/PR-2 anonymity stack (engine position-log + receiver hearings + per-message candidate scores). New: a tracked-device cohort with **staggered origination times** (so each message is an independent geometric constraint), a pure **score-fusion** function (Borda primary + normalized score-sum sensitivity), a **decoy-centrality** confound control, and an **intersection gate**. One engine run per rep produces the whole K-sweep by fusing prefixes of a K_max-message plan.

**Tech Stack:** Python 3.11, numpy only (no scipy). pytest. Run sims from `sim/` with `.venv/Scripts/python.exe`.

## Global Constraints

- Every emitted intersection number carries the scope tag inline: `INTERSECTION_SCOPE_TAG = "[INTERSECTION over K linked originations; device-linkage ASSUMED given (PHY out of scope); single external-passive adversary; UPPER BOUND on anonymity]"` (a test asserts no number is emitted without it).
- Every number is an UPPER BOUND on anonymity (fuse the best estimator; a smarter adversary only does better). On fusion-rule divergence, the **lower** (more anonymity-favorable) rank-1 is the credited headline.
- Determinism: all randomness via `cfg.rng(*path)` substreams seeded by `_seed_for`. New top-level RNG tag = **7** (tracked-cohort placement/timing); disjoint from existing 0,1,2,(3,i),4,5,6,777 and from the child path `(2,7)`.
- Default-inert: `intersection_sweep` is a NEW entry point; `anonymity_sweep` / `anonymity_defense_sweep` and every prior number stay bit-identical (no shared mutable path changed).
- Candidate set = all N nodes (cone deferred, same simplification PR-1 disclosed); random-guess floor = 1/N.
- Linkage assumed given (no PHY model). Defenses replayed against intersection are deferred to PR-4.
- TDD: failing test → run-fail → minimal impl → run-pass → commit. Run from `cd sim`.

---

### Task 1: `fuse_scores` + average-rank helper (adversary.py)

**Files:**
- Modify: `sim/soup_sim/adversary.py` (add `_avg_rank`, `fuse_scores` after `estimate`)
- Test: `sim/tests/test_adversary.py` (append)

**Interfaces:**
- Consumes: nothing (pure numpy).
- Produces: `fuse_scores(score_vectors: list[np.ndarray], method: str = "borda") -> np.ndarray` — fuse K per-candidate score vectors (lower = more suspicious) into one fused vector (lower = more suspicious); `method ∈ {"borda","score_sum"}`. `_avg_rank(scores: np.ndarray) -> np.ndarray` — average ranks (0 = best/lowest, ties share mean rank).

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_adversary.py` append:

```python
def test_avg_rank_handles_ties():
    from soup_sim.adversary import _avg_rank
    import numpy as np
    r = _avg_rank(np.array([0.0, 0.0, 1.0]))   # two-way tie for best
    assert r[0] == 0.5 and r[1] == 0.5 and r[2] == 2.0


def test_fuse_borda_rewards_consistency():
    from soup_sim.adversary import fuse_scores
    from soup_sim.anonymity import rank_of
    import numpy as np
    # 4 candidates, 3 messages. Candidate A (idx 1) is ALWAYS 2nd; B/C/D rotate through 1st/3rd/4th.
    # consistent-2nd must beat the rotating extremes under Borda.
    m1 = np.array([0.0, 1.0, 2.0, 3.0])   # B,A,C,D
    m2 = np.array([3.0, 1.0, 0.0, 2.0])   # C 1st, A 2nd, D 3rd, B 4th
    m3 = np.array([2.0, 1.0, 3.0, 0.0])   # D 1st, A 2nd, B 3rd, C 4th
    fused = fuse_scores([m1, m2, m3], "borda")
    assert int(np.argmin(fused)) == 1                       # A wins
    assert rank_of(fused, 1) == 0                           # A is exact-catch


def test_fuse_score_sum_normalizes_per_message():
    from soup_sim.adversary import fuse_scores
    import numpy as np
    # message 2 has a huge scale; without per-message normalization it would dominate. With it,
    # the consistently-low candidate (idx 0) wins.
    m1 = np.array([0.0, 1.0, 2.0])
    m2 = np.array([0.0, 100.0, 200.0])
    fused = fuse_scores([m1, m2], "score_sum")
    assert int(np.argmin(fused)) == 0


def test_fuse_empty_raises():
    from soup_sim.adversary import fuse_scores
    import pytest
    with pytest.raises(ValueError):
        fuse_scores([], "borda")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_adversary.py -q -k "fuse or avg_rank"`
Expected: FAIL with ImportError / AttributeError (`_avg_rank` / `fuse_scores` not defined).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/adversary.py`, after the `estimate(...)` function (before `hearings`), add:

```python
def _avg_rank(scores) -> np.ndarray:
    """Average ranks (0 = best/lowest score). Ties share the mean of their positions — robust to
    the many exact ties the reachability estimator produces when there is no time gradient."""
    s = np.asarray(scores, float)
    n = len(s)
    order = np.argsort(s, kind="mergesort")
    sorted_s = s[order]
    ranks = np.empty(n, float)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and sorted_s[j + 1] - sorted_s[i] <= 1e-12:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return ranks


def fuse_scores(score_vectors, method="borda") -> np.ndarray:
    """Fuse K per-candidate score vectors (lower = more suspicious) into one fused vector.
    borda     — sum of per-message average-ranks (scale-free; conservative; the credited headline).
    score_sum — sum of per-message (min-subtracted, std-normalized) scores (~ sum of NLLs / Bayesian
                intersection); a scale-sensitivity arm. Each message normalized so no single message
                with a large score scale dominates the sum."""
    mats = [np.asarray(v, float) for v in score_vectors]
    if not mats:
        raise ValueError("fuse_scores: empty score_vectors")
    if method == "borda":
        return np.sum([_avg_rank(v) for v in mats], axis=0)
    if method == "score_sum":
        acc = np.zeros(len(mats[0]), float)
        for v in mats:
            vv = v - v.min()
            sd = float(vv.std())
            acc += vv / sd if sd > 1e-12 else vv
        return acc
    raise ValueError(f"unknown fusion method {method!r}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_adversary.py -q -k "fuse or avg_rank"`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/adversary.py sim/tests/test_adversary.py
git commit -m "feat(sim): score-fusion (Borda + normalized score-sum) for intersection adversary (PR-3 task 1)"
```

---

### Task 2: `intersection_gate` + constants (anonymity.py)

**Files:**
- Modify: `sim/soup_sim/anonymity.py` (add constants + `intersection_gate` after `defense_gate`)
- Test: `sim/tests/test_anonymity.py` (append)

**Interfaces:**
- Consumes: existing `EXPOSURE_RANK1`, `EXPOSURE_MARGIN_K`, `MIN_REPS`.
- Produces: `INTERSECTION_SCOPE_TAG: str`; `DECOY_MARGIN = 0.2`; `MIN_INTERSECTION_SAMPLES = 24`; `intersection_gate(fused_rank1: float, decoy_rank1: float, random_floor: float, mustlocalize_ok: bool, n_samples: int) -> dict` returning `{"credited": bool, "label": str}`.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_anonymity.py` append:

```python
def test_intersection_gate():
    from soup_sim.anonymity import intersection_gate
    # credited: well above threshold, decoy not pinned, powered, must-localize OK
    assert intersection_gate(0.80, 0.10, 0.0083, True, 60)["credited"] is True
    # underpowered -> refuse
    assert intersection_gate(0.80, 0.10, 0.0083, True, 5)["credited"] is False
    # must-localize failed -> inconclusive
    assert intersection_gate(0.80, 0.10, 0.0083, False, 60)["credited"] is False
    # below the exposure threshold -> not exposed
    assert intersection_gate(0.30, 0.05, 0.0083, True, 60)["credited"] is False
    # decoy ALSO pinned (centrality confound) -> not credited
    g = intersection_gate(0.80, 0.70, 0.0083, True, 60)
    assert g["credited"] is False and "centrality" in g["label"].lower()


def test_intersection_scope_tag():
    from soup_sim.anonymity import INTERSECTION_SCOPE_TAG
    t = INTERSECTION_SCOPE_TAG.lower()
    assert "intersection" in t and "linkage" in t and "upper bound" in t
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_anonymity.py -q -k "intersection"`
Expected: FAIL (ImportError: `intersection_gate` / `INTERSECTION_SCOPE_TAG`).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/anonymity.py`, add to the constants block (after `MIN_INTERSECTION_SIZE`):

```python
# PR-3 multi-session intersection
INTERSECTION_SCOPE_TAG = ("[INTERSECTION over K linked originations; device-linkage ASSUMED given "
                          "(PHY out of scope); single external-passive adversary; UPPER BOUND on anonymity]")
DECOY_MARGIN = 0.2           # the originator's fused rank-1 must beat the central-decoy's by >= this...
MIN_INTERSECTION_SAMPLES = 24  # ...over >= this many (device x seed) fusion samples, else underpowered
```

And after `defense_gate(...)`, add:

```python
def intersection_gate(fused_rank1, decoy_rank1, random_floor, mustlocalize_ok, n_samples) -> dict:
    """Credit "intersection deanonymizes the persistent sender" only if the fused rank-1 crosses the
    exposure threshold, beats the central-decoy by DECOY_MARGIN (else it's centrality, not origination),
    the per-message estimator was capable (must-localize), and the run is powered."""
    if n_samples < MIN_INTERSECTION_SAMPLES:
        return {"credited": False, "label": f"underpowered ({n_samples} fusion samples < {MIN_INTERSECTION_SAMPLES})"}
    if not mustlocalize_ok:
        return {"credited": False, "label": "inconclusive — per-message estimator failed must-localize"}
    threshold = max(EXPOSURE_RANK1, EXPOSURE_MARGIN_K * random_floor)
    if fused_rank1 < threshold:
        return {"credited": False, "label": f"not pinned (fused rank-1 {fused_rank1:.2f} < {threshold:.2f})"}
    if fused_rank1 - decoy_rank1 < DECOY_MARGIN:
        return {"credited": False, "label": f"confounded by centrality (origin {fused_rank1:.2f} vs decoy {decoy_rank1:.2f})"}
    return {"credited": True, "label": f"intersection deanonymizes the sender (fused rank-1 {fused_rank1:.2f} @ decoy {decoy_rank1:.2f})"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_anonymity.py -q -k "intersection"`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/anonymity.py sim/tests/test_anonymity.py
git commit -m "feat(sim): intersection gate + scope tag (PR-3 task 2)"
```

---

### Task 3: Tracked-device cohort + staggered engine run (scenario.py)

**Files:**
- Modify: `sim/soup_sim/scenario.py` (add `make_tracked_cohort`, `_run_one_anonymity_tracked` near `_run_one_anonymity`)
- Test: `sim/tests/test_scenario_anonymity.py` (append)

**Interfaces:**
- Consumes: `Blob`, `make_mobility`, `NodeBuffer`, `AirtimeBudget`, `Engine`, `Metrics`, `_anon_pos_at`, `cfg.rng(7)`.
- Produces:
  - `make_tracked_cohort(cfg, k_max, n_tracked, stride, inject_time, rng) -> tuple[list, dict]` — returns `(cohort, tracked)` where `cohort = [(Blob, src, dst)]` and `tracked = {device_node: [blob_id,...]}`. Tracked devices each originate `k_max` messages with `created_at = inject_time + k*stride`; plus `cfg.n_messages` background single-message originators at `inject_time`.
  - `_run_one_anonymity_tracked(cfg, k_max, n_tracked, stride) -> dict` — one engine run (defenses OFF, recorder ON); returns the same artifact dict as `_run_one_anonymity` PLUS `"tracked"`.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_scenario_anonymity.py` append:

```python
def test_make_tracked_cohort_staggers_and_maps():
    from soup_sim.scenario import make_tracked_cohort
    c = tiny()
    cohort, tracked = make_tracked_cohort(c, k_max=4, n_tracked=2, stride=2.0,
                                          inject_time=c.warmup, rng=c.rng(7))
    assert len(tracked) == 2 and all(len(ids) == 4 for ids in tracked.values())
    # tracked messages are staggered by stride
    by_id = {b.id: b for (b, _s, _d) in cohort}
    for dev, ids in tracked.items():
        times = [by_id[i].created_at for i in ids]
        assert times == [c.warmup + k * 2.0 for k in range(4)]
        # all four ids of a device share that device as src
        srcs = {s for (b, s, _d) in cohort if b.id in ids}
        assert srcs == {dev}
    # background present and un-tracked
    assert len(cohort) == 2 * 4 + c.n_messages


def test_run_tracked_respects_created_at_causality():
    from soup_sim.scenario import _run_one_anonymity_tracked
    c = tiny()
    art = _run_one_anonymity_tracked(c, k_max=3, n_tracked=1, stride=2.0)
    assert "tracked" in art and len(art["tracked"]) == 1
    dev, ids = next(iter(art["tracked"].items()))
    # a tracked message cannot be acquired by ANY node before its created_at (causality)
    cohort_created = {bid: created for (bid, _s, created, _ttl) in art["cohort"]}
    for (node, bid), t_acq in art["acquired"].items():
        if bid in cohort_created:
            assert t_acq >= cohort_created[bid] - 1e-9


def test_run_tracked_deterministic():
    from soup_sim.scenario import _run_one_anonymity_tracked
    a = _run_one_anonymity_tracked(tiny(), k_max=3, n_tracked=1, stride=2.0)
    b = _run_one_anonymity_tracked(tiny(), k_max=3, n_tracked=1, stride=2.0)
    assert a["acquired"] == b["acquired"] and a["tracked"] == b["tracked"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario_anonymity.py -q -k "tracked"`
Expected: FAIL (ImportError: `make_tracked_cohort` / `_run_one_anonymity_tracked`).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/scenario.py`, after `_run_one_anonymity(...)` (before `_forward_infection`), add:

```python
def make_tracked_cohort(cfg, k_max, n_tracked, stride, inject_time, rng):
    """n_tracked devices each originate k_max messages staggered by `stride` (so each is an
    independent geometric constraint on the device's trajectory), plus cfg.n_messages background
    single-message originators (realistic relay density). Returns (cohort, tracked) where
    cohort=[(Blob, src, dst)] and tracked={device_node: [blob_id,...]}."""
    devices = [int(x) for x in rng.choice(cfg.n, size=n_tracked, replace=False)]
    cohort, tracked, bid = [], {}, 0
    for dev in devices:
        ids = []
        for k in range(k_max):
            dst = int(rng.integers(0, cfg.n))
            cohort.append((Blob(id=bid, created_at=inject_time + k * stride, ttl=cfg.ttl,
                                size=cfg.blob_size), dev, dst))
            ids.append(bid)
            bid += 1
        tracked[dev] = ids
    for _ in range(cfg.n_messages):
        src = int(rng.integers(0, cfg.n))
        dst = int(rng.integers(0, cfg.n))
        cohort.append((Blob(id=bid, created_at=inject_time, ttl=cfg.ttl, size=cfg.blob_size), src, dst))
        bid += 1
    return cohort, tracked


def _run_one_anonymity_tracked(cfg, k_max, n_tracked, stride):
    """Like _run_one_anonymity but with a tracked-device cohort (staggered originations). Defenses
    OFF (PR-3 is the undefended intersection baseline). Future created_at + the engine's
    acquisition-time causality make each message's flood start at its own origination time."""
    cfg.validate()
    mob = make_mobility(cfg, cfg.rng(0))
    metrics = Metrics(cfg, cfg.warmup, cfg.measure_window)
    buffers = [NodeBuffer(cfg.buffer_cap, cfg.ttl + cfg.seen_margin, cfg.rng(3, i)) for i in range(cfg.n)]
    budget = AirtimeBudget(cfg.throughput_ideal, cfg.alpha, cfg.t_setup, cfg.p_fail, cfg.blob_size,
                           model=cfg.airtime_model, beta=cfg.beta,
                           t_setup_slope=cfg.t_setup_slope, n_channels=cfg.n_channels)
    eng = Engine(cfg, mob, buffers, budget, cfg.rng(1), on_deliver=metrics.on_deliver, record_positions=True)
    eng.run_until(cfg.warmup)
    cohort_raw, tracked = make_tracked_cohort(cfg, k_max, n_tracked, stride, cfg.warmup, cfg.rng(7))
    cohort = []
    for blob, src, dst in cohort_raw:
        metrics.register(blob, src, dst)
        eng.inject(blob, src)                            # un-gated; created_at carries the stagger
        cohort.append((blob.id, src, blob.created_at, blob.ttl))
    eng.run_until(cfg.warmup + cfg.measure_window + cfg.drain)
    eng.finalize()
    return {"position_log": eng.position_log, "acquired": dict(eng.acquired), "cohort": cohort,
            "episodes": list(eng.episodes), "n": cfg.n, "tracked": tracked,
            "relayed": {k: len(v) for k, v in eng.relayed.items()},
            "delivery": metrics.delivery_ratio(), "t50": metrics.t50()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario_anonymity.py -q -k "tracked"`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/scenario.py sim/tests/test_scenario_anonymity.py
git commit -m "feat(sim): tracked-device cohort + staggered-origination run (PR-3 task 3)"
```

---

### Task 4: `intersection_sweep` (scenario.py) — the K-sweep + controls

**Files:**
- Modify: `sim/soup_sim/scenario.py` (add `_tracked_score_vectors`, `intersection_sweep`; extend the `anonymity` import line with `intersection_gate, INTERSECTION_SCOPE_TAG`; extend the `adversary` import with `fuse_scores`)
- Test: `sim/tests/test_scenario_anonymity.py` (append — one fast smoke + one `@pytest.mark.slow` realistic)

**Interfaces:**
- Consumes: `_run_one_anonymity_tracked`, `_tracked_score_vectors`, `place_receivers`, `fuse_scores`, `estimate`, `rank_of`, `mean_ci`, `anonymity_sweep` (for must-localize), `intersection_gate`, `_anon_pos_at`, `hearings`, `_reach_capped`, `_forward_reach_matrix`.
- Produces:
  - `_tracked_score_vectors(art, receivers, cfg, msg_ids, rng_est) -> tuple[list, list]` — returns `(vectors, detected_ids)`: the reachability score vector (length N) per *detected* tracked message, in `msg_ids` order.
  - `intersection_sweep(cfg, k_values, f, reps, n_tracked=3, stride=2.0) -> dict` — keys: `rows` (one per K with `k, fused_rank1_borda, ci_lo, ci_hi, fused_rank1_score_sum, decoy_rank1, random_floor_fused, delivery, n_samples`), `mustlocalize`, `verdict`, `headline_k`, `random_floor`, `fusion_divergence`, `scope_tag`, `intersection_scope_tag`.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_scenario_anonymity.py` append:

```python
def test_intersection_sweep_structure_and_determinism():
    from soup_sim.scenario import intersection_sweep
    a = intersection_sweep(tiny(), k_values=[1, 2], f=0.7, reps=1, n_tracked=2, stride=2.0)
    b = intersection_sweep(tiny(), k_values=[1, 2], f=0.7, reps=1, n_tracked=2, stride=2.0)
    assert a["rows"] == b["rows"]                                   # deterministic
    assert "UPPER BOUND" in a["intersection_scope_tag"] and "linkage" in a["intersection_scope_tag"].lower()
    assert "credited" in a["verdict"]
    for r in a["rows"]:
        assert {"k", "fused_rank1_borda", "fused_rank1_score_sum", "decoy_rank1",
                "random_floor_fused", "delivery", "n_samples"} <= set(r)
    assert [r["k"] for r in a["rows"]] == [1, 2]


@pytest.mark.slow
def test_intersection_sharpens_with_k():
    from soup_sim.scenario import intersection_sweep
    cfg = base_intersection_cfg()
    out = intersection_sweep(cfg, k_values=[1, 4, 16], f=0.7, reps=4, n_tracked=4, stride=2.0)
    rows = {r["k"]: r for r in out["rows"]}
    # intersection must NOT make the originator harder to find as K grows (monotone-ish up)
    assert rows[16]["fused_rank1_borda"] >= rows[1]["fused_rank1_borda"] - 1e-9
    # the fused-random floor stays near 1/N (fusion itself creates no signal)
    assert rows[16]["random_floor_fused"] <= 5.0 / cfg.n
    # K=1 borda equals a single message's rank-1 (continuity with PR-1) within sampling noise
    assert abs(rows[1]["fused_rank1_borda"] - rows[1]["fused_rank1_score_sum"]) <= 0.5
    # powered enough to reach a real verdict (not the underpowered early return)
    assert "underpowered" not in out["verdict"]["label"].lower()


def base_intersection_cfg():
    return Config(n=120, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=120.0, buffer_cap=200, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=30.0, measure_window=120.0,
                  drain=20.0, n_messages=120, seen_margin=120.0, master_seed=13, adversary_range_mult=1.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario_anonymity.py -q -k "intersection_sweep or sharpens"`
Expected: FAIL (ImportError: `intersection_sweep`).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/scenario.py`, extend the two imports:

```python
from .adversary import place_receivers, realized_coverage, hearings, estimate, fuse_scores
from .anonymity import (localization_error, rank_of, anonymity_set_size, quantiles,
                        mustlocalize_gate, exposure_gate, defense_gate, intersection_gate,
                        SCOPE_TAG, DEFENSE_SCOPE_TAG, INTERSECTION_SCOPE_TAG, MIN_RELAY_DENSITY)
```

Then after `anonymity_defense_sweep(...)` add:

```python
def _tracked_score_vectors(art, receivers, cfg, msg_ids, rng_est):
    """Per DETECTED tracked message (in msg_ids order): the reachability estimator's per-candidate
    score vector (length n), seeded at that message's own origination time. Undetected messages
    (heard by no receiver) are skipped — they carry no fusion evidence."""
    log, acquired = art["position_log"], art["acquired"]
    adv_range = cfg.adversary_range_mult * cfg.radius
    created = {bid: c for (bid, _s, c, _ttl) in art["cohort"]}
    ttl_of = {bid: t for (bid, _s, _c, t) in art["cohort"]}
    expiry = {bid: created[bid] + ttl_of[bid] for bid in created}
    H = hearings(receivers, adv_range, log, acquired, expiry, cfg)
    by_blob = {}
    for (li, bid), t in H.items():
        by_blob.setdefault(bid, []).append((li, t))
    vectors, detected = [], []
    for bid in msg_ids:
        mh = by_blob.get(bid)
        if not mh:
            continue
        fh = min(t for _li, t in mh)
        cand_fh = _anon_pos_at(log, fh)
        reach = _reach_capped(_forward_reach_matrix(art["episodes"], log, receivers, created[bid],
                                                    art["n"], adv_range, cfg))
        est = estimate("reachability", mh, receivers, cand_fh, rng_est, reach=reach)
        vectors.append(np.asarray(est["scores"], float))
        detected.append(bid)
    return vectors, detected


def intersection_sweep(cfg, k_values, f, reps, n_tracked=3, stride=2.0):
    """Fused sender-localization vs K linked originations at fixed coverage f. One engine run per rep
    yields the whole K-sweep (fuse prefixes of each device's k_max plan). Borda (headline) + score-sum
    (sensitivity); fused-random floor + decoy-centrality control. Every number an UPPER BOUND."""
    k_max = max(k_values)
    mustloc = anonymity_sweep(cfg, [0.95], reps=1)["mustlocalize"]   # capability control (reuse PR-1)
    acc = {k: {"borda_o": [], "sum_o": [], "borda_d": [], "rand": [], "delivery": [], "inter": []}
           for k in k_values}
    for rep in range(reps):
        c = replace(cfg, master_seed=_seed_for(cfg.master_seed, 0, rep))
        art = _run_one_anonymity_tracked(c, k_max, n_tracked, stride)
        recv = place_receivers(c, f, "uniform", c.rng(4))
        rng_est = c.rng(6)                                          # ONE persistent estimator rng per rep
        tracked_nodes = set(art["tracked"])
        relayed = art["relayed"]
        decoy = max((nd for nd in range(c.n) if nd not in tracked_nodes),
                    key=lambda nd: relayed.get(nd, 0), default=None)
        cand0 = _anon_pos_at(art["position_log"], c.warmup)
        for dev, ids in art["tracked"].items():
            vecs, detected = _tracked_score_vectors(art, recv, c, ids, rng_est)
            rvecs = [estimate("random_guess", [(0, 0.0)], recv, cand0, rng_est)["scores"] for _ in detected]
            for k in k_values:
                if len(vecs) < k:
                    continue
                fb = fuse_scores(vecs[:k], "borda")
                fs = fuse_scores(vecs[:k], "score_sum")
                fr = fuse_scores(rvecs[:k], "borda")
                acc[k]["borda_o"].append(rank_of(fb, dev) == 0)
                acc[k]["sum_o"].append(rank_of(fs, dev) == 0)
                acc[k]["rand"].append(rank_of(fr, dev) == 0)
                if decoy is not None:
                    acc[k]["borda_d"].append(rank_of(fb, decoy) == 0)
                acc[k]["delivery"].append(art["delivery"])
                acc[k]["inter"].append(len(detected))
    rows = []
    for k in k_values:
        d = acc[k]
        m, lo, hi = mean_ci(d["borda_o"])
        rows.append({
            "k": k, "fused_rank1_borda": m, "ci_lo": lo, "ci_hi": hi,
            "fused_rank1_score_sum": float(np.mean(d["sum_o"])) if d["sum_o"] else 0.0,
            "decoy_rank1": float(np.mean(d["borda_d"])) if d["borda_d"] else 0.0,
            "random_floor_fused": float(np.mean(d["rand"])) if d["rand"] else 0.0,
            "delivery": float(np.mean(d["delivery"])) if d["delivery"] else 0.0,
            "n_samples": len(d["borda_o"]),
        })
    floor = 1.0 / cfg.n
    hk = next(r for r in rows if r["k"] == k_max)
    credited = min(hk["fused_rank1_borda"], hk["fused_rank1_score_sum"])   # honest: lower on divergence
    verdict = intersection_gate(credited, hk["decoy_rank1"], floor, mustloc["ok"], hk["n_samples"])
    return {"rows": rows, "mustlocalize": mustloc, "verdict": verdict, "headline_k": k_max,
            "random_floor": floor,
            "fusion_divergence": abs(hk["fused_rank1_borda"] - hk["fused_rank1_score_sum"]),
            "scope_tag": SCOPE_TAG, "intersection_scope_tag": INTERSECTION_SCOPE_TAG}
```

- [ ] **Step 4: Run the fast smoke; then the slow test**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario_anonymity.py -q -k "intersection_sweep"`
Expected: PASS (smoke).
Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario_anonymity.py -q -m slow -k "sharpens"`
Expected: PASS (may take 10–25 min — it is `@pytest.mark.slow`).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/scenario.py sim/tests/test_scenario_anonymity.py
git commit -m "feat(sim): intersection_sweep — fused rank-1 vs K + decoy/random controls (PR-3 task 4)"
```

---

### Task 5: Report CSV + CLI preset + RNG-disjointness + docs

**Files:**
- Modify: `sim/soup_sim/report.py` (add `intersection_to_csv_string`)
- Modify: `sim/run.py` (add `intersection_cfg`, `_run_anonymity_intersection`, register `anonymity-intersection` preset)
- Modify: `sim/README.md` (slice-3 PR-3 section + bias rows + run command)
- Modify: the RNG-disjointness test to include tag 7 (find it: `grep -rn "disjoint" sim/tests`)
- Test: `sim/tests/test_report.py` (append)

**Interfaces:**
- Consumes: `intersection_sweep` output dict.
- Produces: `intersection_to_csv_string(out: dict, manifest: dict) -> str` — one row per K carrying both fusion rules, decoy, random floor, delivery, n_samples, verdict credited/label, and both scope tags as columns.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_report.py` append:

```python
def test_intersection_csv_carries_tags_and_both_fusion_rules():
    from soup_sim.report import intersection_to_csv_string, INTERSECTION_FIELDS
    out = {
        "scope_tag": "[UPPER BOUND on anonymity]",
        "intersection_scope_tag": "[INTERSECTION; device-linkage ASSUMED given; UPPER BOUND on anonymity]",
        "verdict": {"credited": True, "label": "intersection deanonymizes the sender"},
        "rows": [
            {"k": 1, "fused_rank1_borda": 0.30, "ci_lo": 0.2, "ci_hi": 0.4, "fused_rank1_score_sum": 0.31,
             "decoy_rank1": 0.05, "random_floor_fused": 0.008, "delivery": 0.9, "n_samples": 40},
            {"k": 16, "fused_rank1_borda": 0.80, "ci_lo": 0.7, "ci_hi": 0.9, "fused_rank1_score_sum": 0.78,
             "decoy_rank1": 0.06, "random_floor_fused": 0.009, "delivery": 0.9, "n_samples": 40},
        ],
    }
    s = intersection_to_csv_string(out, {"master_seed": 13})
    lines = s.splitlines()
    assert lines[0].startswith("#") and lines[1].startswith("#")          # both tags as comments
    header = lines[2]
    for fld in INTERSECTION_FIELDS:
        assert fld in header
    assert "intersection_scope_tag" in header and "param_master_seed" in header
    assert "credited" in header and "fused_rank1_score_sum" in header
    assert len(lines) == 2 + 1 + 2                                        # 2 comments + header + 2 K rows
    assert out["intersection_scope_tag"] in lines[3]                      # tag survives as a column value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_report.py -q -k "intersection"`
Expected: FAIL (ImportError: `intersection_to_csv_string` / `INTERSECTION_FIELDS`).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/report.py`, after `anonymity_defense_to_csv_string(...)`, add:

```python
INTERSECTION_FIELDS = ["k", "fused_rank1_borda", "ci_lo", "ci_hi", "fused_rank1_score_sum",
                       "decoy_rank1", "random_floor_fused", "delivery", "n_samples"]


def intersection_to_csv_string(out, manifest) -> str:
    """One row per K. Both fusion rules (borda headline + score_sum sensitivity), the decoy-centrality
    control, the fused-random floor, and the credit verdict travel per row; both scope tags as columns
    + comments (a comment alone is dropped by dataframe readers)."""
    man = list(manifest.keys())
    header = (INTERSECTION_FIELDS + ["credited", "label", "scope_tag", "intersection_scope_tag"]
              + [f"param_{k}" for k in man])
    buf = io.StringIO()
    buf.write(f"# {out['scope_tag']}\n# {out['intersection_scope_tag']}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    v = out["verdict"]
    for r in out["rows"]:
        row = [r.get(k) for k in INTERSECTION_FIELDS] + [v["credited"], v["label"],
               out["scope_tag"], out["intersection_scope_tag"]] + [manifest[k] for k in man]
        w.writerow(row)
    return buf.getvalue()
```

- [ ] **Step 4: Run report test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_report.py -q -k "intersection"`
Expected: PASS.

- [ ] **Step 5: Wire the CLI preset**

In `sim/run.py`, update the imports:

```python
from soup_sim.scenario import (static_delivery_sweep, midpoint_with_ci, airtime_sweep, anonymity_sweep,
                               anonymity_defense_sweep, intersection_sweep)
from soup_sim.report import (write_csv, plot, airtime_to_csv_string, airtime_plot,
                             anonymity_to_csv_string, anonymity_plot, anonymity_defense_to_csv_string,
                             intersection_to_csv_string)
```

Add after `_run_anonymity_defenses(...)`:

```python
def intersection_cfg(seed: int) -> Config:
    # Same venue as the anonymity headline (PR-1), long window so staggered originations + spread fit.
    return replace(anonymity_cfg(seed), ttl=120.0, warmup=30.0, measure_window=120.0, drain=20.0,
                   seen_margin=120.0, n_messages=120)


def _run_anonymity_intersection(args) -> None:
    cfg = intersection_cfg(args.seed)
    reps = max(args.reps, 4)
    out = intersection_sweep(cfg, k_values=[1, 2, 4, 8, 16], f=0.7, reps=reps, n_tracked=4, stride=2.0)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(intersection_to_csv_string(out, cfg.manifest()))
    print(f"wrote {args.out} (K-sweep @ coverage f=0.7, reps={reps}, tracked=4)")
    print(out["scope_tag"]); print(out["intersection_scope_tag"])
    print(f"MUST-LOCALIZE control: {out['mustlocalize']['label']} (ok={out['mustlocalize']['ok']})")
    for r in out["rows"]:
        print(f"  K={r['k']:>2}: fused rank-1 borda {r['fused_rank1_borda']:.2f} "
              f"(score-sum {r['fused_rank1_score_sum']:.2f}; decoy {r['decoy_rank1']:.2f}; "
              f"rand {r['random_floor_fused']:.3f}; n={r['n_samples']})")
    print(f"VERDICT @K={out['headline_k']} (credited = LOWER fusion rule): {out['verdict']['label']}")
    print("note: every number is an UPPER BOUND on anonymity; device-linkage is ASSUMED given (PHY out")
    print("      of scope); the decoy is the most-central innocent relay — if it pins too, it's centrality.")
    if args.plot:
        print("note: --plot is not supported for the anonymity-intersection preset (no plot written).")
```

Register the preset in `main()`:

```python
    ap.add_argument("--preset",
                    choices=["static-cliff", "airtime-knee", "anonymity", "anonymity-defenses",
                             "anonymity-intersection"],
                    default="static-cliff")
```

and the dispatch:

```python
    elif args.preset == "anonymity-intersection":
        _run_anonymity_intersection(args)
```

- [ ] **Step 6: Extend the RNG-disjointness test for tag 7**

Run: `cd sim && grep -rn "disjoint\|substream" tests/` to locate the test. Add tag `7` (and confirm `(2,7)` child path stays distinct) to whatever tag set it asserts. If the test enumerates used tags, add `7`; the assertion is that `cfg.rng(7)` differs from `cfg.rng(0..6)`, `cfg.rng(2,7)`, and `cfg.rng(777)`. Example assertion to add if the test is list-based:

```python
def test_rng_tag7_disjoint():
    from soup_sim.config import Config
    c = base_defense_cfg() if "base_defense_cfg" in dir() else None
    import numpy as np
    from soup_sim.config import make_rng
    seeds = {tuple(p): make_rng(99, *p).integers(0, 2**31) for p in
             [(0,), (1,), (2,), (4,), (5,), (6,), (7,), (2, 7), (777,)]}
    assert len(set(seeds.values())) == len(seeds)     # all distinct streams
```

(Place this in `sim/tests/test_config.py` if it exists, else in `sim/tests/test_scenario_anonymity.py`.)

- [ ] **Step 7: Update the README**

In `sim/README.md`: add the run command under the existing preset block:
```
.venv/Scripts/python run.py --preset anonymity-intersection --out out/anon_intersection.csv  # PR-3: rank-1 vs K
```
Add a `## Anonymity intersection (slice 3 — PR-3)` section after the PR-2 section describing: the tracked-device staggered-origination model; Borda (headline) + score-sum (sensitivity, credit the lower on divergence); the fused-random floor + decoy-centrality controls; linkage assumed given (PHY out of scope); and that the measured headline (does fused rank-1 cross the threshold by K=16, and the decoy stays low) is reported faithfully — including a negative result. Add bias-table rows:
```
| anonymity intersection (multi-session) | §10 | slice-3 PR-3: fused rank-1 over K LINKED originations, **UPPER BOUND**; device-linkage ASSUMED given (PHY = separate slice) |
| intersection: linkage assumed perfect | §10 | **worst-case upper bound** (real linkage is partial/noisy) — safe direction for a privacy claim |
| intersection credit: decoy-centrality + fused-random controls | §10 | credit only if the ORIGINATOR is pinned and the most-central innocent relay (decoy) is not; fusion itself creates no signal (random floor stays ~1/N) |
| intersection: credited headline = lower of Borda/score-sum | §10 | **conservative** — never credit the adversary a fusion-rule coin-flip |
```
Also update the Module map line to mention `intersection_sweep`.

- [ ] **Step 8: Full non-regression + commit**

Run: `cd sim && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all prior tests + the new fast ones; slow ones deselected). Confirm no prior count regressed.

```bash
git add sim/soup_sim/report.py sim/run.py sim/README.md sim/tests/test_report.py sim/tests/test_scenario_anonymity.py sim/tests/test_config.py
git commit -m "feat(sim): intersection CSV + anonymity-intersection preset + PR-3 docs (PR-3 task 5)"
```

---

## Self-Review

**1. Spec coverage:**
- §1 threat model (tracked device, K axis, linkage assumed) → Tasks 3 (cohort) + 4 (sweep). ✓
- §2 metrics (fused rank-1 headline, anon-set upper bound, undetected handling) → Task 4 (fused rank-1, undetected messages skipped in `_tracked_score_vectors`). Anon-set-upper-bound under fusion is NOT separately emitted — acceptable YAGNI (the headline is rank-1; note in README). ✓ (minor: anon-set deferred, disclosed)
- §3 fusion rules (Borda + score-sum, credit lower on divergence) → Tasks 1 + 4. ✓
- §4 controls (random floor, decoy-centrality, must-localize, exposure gate) → Tasks 2 (gate) + 4 (floor, decoy, must-localize wired). ✓
- §5 architecture (additive, RNG tag 7, default-inert) → Tasks 3/4/5. ✓
- §6 bias table → Task 5 Step 7. ✓
- §7 DoD (scope tag on every number, non-regression, one-command run, K=1≡PR-1) → Task 5 (CSV/CLI tags, full suite), Task 4 (K=1 continuity test). ✓

**2. Placeholder scan:** No TBD/TODO; every code step has complete code. ✓

**3. Type consistency:** `intersection_sweep` returns the dict consumed by `intersection_to_csv_string` and `_run_anonymity_intersection` (keys `rows`, `verdict`, `scope_tag`, `intersection_scope_tag`, `mustlocalize`, `headline_k` — all match). `fuse_scores(list, method)` signature consistent across Tasks 1 and 4. `intersection_gate(fused_rank1, decoy_rank1, random_floor, mustlocalize_ok, n_samples)` consistent across Tasks 2 and 4. `_run_one_anonymity_tracked` artifact dict matches `_tracked_score_vectors`'s reads (`position_log`, `acquired`, `cohort`, `episodes`, `n`, `tracked`, `relayed`, `delivery`). ✓

**Note on candidate set / anon-set:** candidate set = all N nodes (cone deferred, same as PR-1); the fused anonymity-set-size is not separately reported (headline is fused rank-1) — disclosed in README, consistent with PR-1's existing simplification.
