# Slice 4 PR-1 — Clustered "Gathering" Mobility — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a clustered "gathering" mobility model and measure whether a clustered venue stays connected enough to deliver, as a function of the inter-cluster leak rate.

**Architecture:** A new `clustered` mode in `mobility.py` reusing RWP's move-toward-target mechanics with cluster-aware retargeting; a mobility-only (engine-free) leak-rate sweep in `scenario.py` measuring time-averaged same-component delivery + giant-component fraction over the trajectory, with RWP recovered at `leak=1` as a correctness gate.

**Tech Stack:** Python 3.11, numpy only. pytest. Run sims from `sim/` with `.venv/Scripts/python.exe`.

## Global Constraints

- New config fields used ONLY when `mobility == "clustered"`: `n_clusters: int = 1`, `cluster_sigma: float = 0.0`, `cluster_leak: float = 0.0`. Existing static/rwp configs stay **bit-identical**.
- **Leak semantics (spec clarification):** a "leaking" retarget draws a **uniform-arena** target (a wanderer), NOT another specific cluster — so `leak=1` is statistically identical to RWP for ANY `cluster_sigma` (the spec's DoD RWP-recovery gate). `leak=0` → nodes never leave home (isolated islands).
- **No new RNG tag:** cluster centers + near-home init draw from the **mobility substream (tag 0)** that `make_mobility` already receives, BEFORE any per-leg target, so the cluster layout is fixed by the seed and identical across the leak sweep (only the per-retarget wander choices, drawn in `Mobility.step`, vary with `cluster_leak`). Home assignment is round-robin (`i mod K`, no draw).
- Every emitted clustered number carries the mobility-regime tag: `CLUSTER_REGIME_TAG = "[MOBILITY REGIME = clustered gathering; uniform/RWP is the optimistic baseline]"`.
- Every delivery number remains an UPPER BOUND on real delivery (inherited).
- Determinism: all randomness via `cfg.rng(*path)`. TDD: failing test → run-fail → minimal impl → run-pass → commit. Run from `cd sim`.

---

### Task 1: Config fields + validation

**Files:**
- Modify: `sim/soup_sim/config.py` (add 3 fields after `originate_gate_time`; extend `validate`)
- Test: `sim/tests/test_config.py` (append)

**Interfaces:**
- Produces: `Config.n_clusters: int`, `Config.cluster_sigma: float`, `Config.cluster_leak: float`; `mobility == "clustered"` accepted by `validate()`.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_config.py` append:

```python
def test_clustered_mobility_validates():
    c = base(mobility="clustered", speed_min=1.0, speed_max=1.0, n_clusters=8,
             cluster_sigma=10.0, cluster_leak=0.1)
    c.validate()                                          # ok
    import pytest
    with pytest.raises(ValueError, match="n_clusters"):
        base(mobility="clustered", speed_min=1.0, speed_max=1.0, n_clusters=0).validate()
    with pytest.raises(ValueError, match="cluster_leak"):
        base(mobility="clustered", speed_min=1.0, speed_max=1.0, cluster_leak=1.5).validate()
    with pytest.raises(ValueError, match="rwp|clustered|speed_min"):
        base(mobility="clustered", speed_min=0.0, speed_max=1.0).validate()   # moving model needs speed>0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_config.py -q -k clustered`
Expected: FAIL (TypeError: unexpected kwarg `n_clusters`, or mobility rejected).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/config.py`, add after the `originate_gate_time` field (line ~57):

```python
    # Slice-4 clustered "gathering" mobility (used only when mobility == "clustered")
    n_clusters: int = 1                # number of cluster centers (gathering zones)
    cluster_sigma: float = 0.0         # intra-cluster Gaussian spread (arena units)
    cluster_leak: float = 0.0          # per-retarget prob. a node wanders uniformly (0=islands, 1=RWP)
```

In `validate()`, change the mobility check and the rwp-speed check, and add cluster guards. Replace:

```python
        if self.mobility not in ("static", "rwp"):
            raise ValueError(f"mobility must be static|rwp, got {self.mobility!r}")
```
with:
```python
        if self.mobility not in ("static", "rwp", "clustered"):
            raise ValueError(f"mobility must be static|rwp|clustered, got {self.mobility!r}")
```
Replace:
```python
        if self.mobility == "rwp" and self.speed_min <= 0:
            raise ValueError("rwp requires speed_min > 0 (avoids RWP speed decay)")
```
with:
```python
        if self.mobility in ("rwp", "clustered") and self.speed_min <= 0:
            raise ValueError("rwp/clustered requires speed_min > 0 (avoids speed decay)")
        if self.mobility == "clustered":
            if self.n_clusters < 1:
                raise ValueError("n_clusters must be >= 1")
            if not 0.0 <= self.cluster_leak <= 1.0:
                raise ValueError("cluster_leak must be in [0, 1]")
            if self.cluster_sigma < 0.0:
                raise ValueError("cluster_sigma must be >= 0")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_config.py -q -k clustered`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/config.py sim/tests/test_config.py
git commit -m "feat(sim): clustered-mobility config fields + validation (slice-4 task 1)"
```

---

### Task 2: Clustered mobility model

**Files:**
- Modify: `sim/soup_sim/mobility.py` (Mobility fields + `_cluster_targets` + `step` retarget branch + `make_mobility` clustered branch + `mean_speed`)
- Test: `sim/tests/test_mobility.py` (append; create if absent)

**Interfaces:**
- Consumes: `Config` (clustered fields), `cfg.rng(0)`.
- Produces: `make_mobility(cfg, rng)` returns a `Mobility` with `mode="clustered"`, attrs `centers (K,2)`, `home (n,)`, `cluster_sigma`, `cluster_leak`, `n_clusters`, `boundary`. `Mobility.step(dt)` retargets cluster-aware. Non-clustered modes keep `home=None`, `centers=None`.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_mobility.py` append (create the file with `import numpy as np` + `from soup_sim.config import Config` + `from soup_sim.mobility import make_mobility` if it does not exist):

```python
def _cfg(**kw):
    d = dict(n=60, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="clustered",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=60.0,
             drain=0.0, n_messages=0, seen_margin=60.0, master_seed=7,
             n_clusters=6, cluster_sigma=6.0, cluster_leak=0.0)
    d.update(kw)
    return Config(**d)


def test_clustered_layout_and_homes():
    c = _cfg()
    mob = make_mobility(c, c.rng(0))
    assert mob.mode == "clustered" and mob.centers.shape == (6, 2) and len(mob.home) == 60
    assert set(mob.home.tolist()) == set(range(6))            # round-robin uses every cluster
    assert mob.positions.shape == (60, 2)


def test_clustered_deterministic():
    c = _cfg()
    a = make_mobility(c, c.rng(0)).positions
    b = make_mobility(c, c.rng(0)).positions
    assert np.array_equal(a, b)


def test_leak0_keeps_nodes_near_home_leak1_spreads():
    from soup_sim.cell_list import neighbor_pairs
    # leak=0: nodes stay in tight home clusters -> almost all neighbor pairs are SAME-home.
    c0 = _cfg(cluster_leak=0.0)
    m0 = make_mobility(c0, c0.rng(0))
    for _ in range(200):
        m0.step(c0.dt)
    pairs0 = neighbor_pairs(m0.positions, c0.radius, c0.width, c0.height, c0.boundary)
    if pairs0:
        same0 = sum(1 for (i, j) in pairs0 if m0.home[i] == m0.home[j]) / len(pairs0)
        assert same0 > 0.9                                   # leak=0 -> overwhelmingly intra-cluster
    # leak=1: nodes wander uniformly -> many cross-home neighbor pairs appear.
    c1 = _cfg(cluster_leak=1.0)
    m1 = make_mobility(c1, c1.rng(0))
    for _ in range(200):
        m1.step(c1.dt)
    pairs1 = neighbor_pairs(m1.positions, c1.radius, c1.width, c1.height, c1.boundary)
    same1 = sum(1 for (i, j) in pairs1 if m1.home[i] == m1.home[j]) / max(1, len(pairs1))
    assert same1 < 0.9                                       # leak=1 -> mixing across homes


def test_static_rwp_have_no_cluster_attrs():
    cs = _cfg(mobility="static")
    cr = _cfg(mobility="rwp")
    assert make_mobility(cs, cs.rng(0)).home is None
    assert make_mobility(cr, cr.rng(0)).home is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_mobility.py -q -k cluster`
Expected: FAIL (clustered branch not implemented; `mode` is not "clustered" / `home` missing).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/mobility.py`, extend `Mobility.__init__` signature and body — replace the signature + field block:

```python
    def __init__(self, mode, positions, velocities, w, h, smin, smax,
                 speeds=None, targets=None, rng=None,
                 boundary="torus", centers=None, home=None, cluster_sigma=0.0, cluster_leak=0.0):
        self.mode = mode
        self.positions = positions
        self.velocities = velocities
        self.w = w
        self.h = h
        self.smin = smin
        self.smax = smax
        self.speeds = speeds if speeds is not None else np.zeros(len(positions))
        self.targets = targets
        self.rng = rng
        self.boundary = boundary
        self.centers = centers
        self.home = home
        self.cluster_sigma = cluster_sigma
        self.cluster_leak = cluster_leak
        self.n_clusters = len(centers) if centers is not None else 0
```

Add a `_cluster_targets` method (after `__init__`, before `step`):

```python
    def _cluster_targets(self, idx) -> np.ndarray:
        """New targets for arrived nodes: near their home cluster, EXCEPT a `cluster_leak` fraction
        wander to a uniform-random arena point (so leak=1 == RWP for any sigma). Torus-wrap / wall-clip."""
        m = len(idx)
        homes = self.home[idx]
        pts = self.centers[homes] + self.rng.normal(0.0, self.cluster_sigma, (m, 2))
        wander = self.rng.random(m) < self.cluster_leak
        k = int(np.count_nonzero(wander))
        if k:
            pts[wander] = self.rng.uniform([0.0, 0.0], [self.w, self.h], (k, 2))
        if self.boundary == "torus":
            return np.mod(pts, [self.w, self.h])
        return np.clip(pts, 0.0, [self.w, self.h])
```

In `step`, replace the arrival retarget block (the `if np.any(arrived):` block) with a cluster-aware draw:

```python
        if np.any(arrived):
            idx = np.where(arrived)[0]
            pos[idx] = tgt[idx]
            if self.centers is not None:                      # clustered: cluster-aware retarget
                tgt[idx] = self._cluster_targets(idx)
            else:                                             # rwp: uniform retarget
                tgt[idx] = self.rng.uniform([0.0, 0.0], [self.w, self.h], (len(idx), 2))
            sp[idx] = self.rng.uniform(self.smin, self.smax, len(idx))
```

Update `mean_speed` to include clustered:

```python
    def mean_speed(self) -> float:
        return float(np.mean(self.speeds)) if self.mode in ("rwp", "clustered") else 0.0
```

Add a `clustered` branch in `make_mobility` (after the rwp setup, before `return mob`; structure it as an explicit branch):

```python
    if cfg.mobility == "clustered":
        K = cfg.n_clusters
        centers = rng.uniform([0.0, 0.0], [cfg.width, cfg.height], (K, 2))
        home = np.arange(n) % K                              # round-robin -> balanced clusters
        def near_home():
            p = centers[home] + rng.normal(0.0, cfg.cluster_sigma, (n, 2))
            return np.mod(p, [cfg.width, cfg.height]) if cfg.boundary == "torus" \
                else np.clip(p, 0.0, [cfg.width, cfg.height])
        pos = near_home()
        tgt = near_home()
        speeds = rng.uniform(cfg.speed_min, cfg.speed_max, n)
        mob = Mobility("clustered", pos, np.zeros((n, 2)), cfg.width, cfg.height,
                       cfg.speed_min, cfg.speed_max, speeds=speeds, targets=tgt, rng=rng,
                       boundary=cfg.boundary, centers=centers, home=home,
                       cluster_sigma=cfg.cluster_sigma, cluster_leak=cfg.cluster_leak)
        diag = (cfg.width ** 2 + cfg.height ** 2) ** 0.5
        mean_speed = max((cfg.speed_min + cfg.speed_max) / 2.0, 1e-9)
        burnin_steps = int(5.0 * 0.52 * diag / mean_speed / cfg.dt)
        for _ in range(min(burnin_steps, 20000)):
            mob.step(cfg.dt)
        return mob
```

Note: the existing `make_mobility` builds `pos`/`tgt`/`speeds` for the rwp path first; the clustered branch must come BEFORE the rwp `return mob` and rebuild its own pos/tgt (it ignores the rwp ones). Place the `if cfg.mobility == "clustered":` block right after `pos = rng.uniform(...)` and the `if cfg.mobility == "static":` early-return, i.e. as a second early-return branch, so the rwp tail only runs for rwp.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_mobility.py -q -k cluster`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/mobility.py sim/tests/test_mobility.py
git commit -m "feat(sim): clustered gathering mobility (intra-cluster RWP + uniform-wander leak) (slice-4 task 2)"
```

---

### Task 3: Leak-rate robustness sweep + RWP-recovery gate

**Files:**
- Modify: `sim/soup_sim/scenario.py` (add `CLUSTER_REGIME_TAG`, `_avg_snapshot_metrics`, `cluster_leak_sweep`; import `largest_component_fraction`)
- Test: `sim/tests/test_scenario.py` (append)

**Interfaces:**
- Consumes: `make_mobility`, `same_component_pair_fraction`, `largest_component_fraction`, `neighbor_pairs`, `density_to_n`, `mean_ci`, `_seed_for`.
- Produces:
  - `_avg_snapshot_metrics(cfg, rng, n_snap=8) -> dict` — keys `delivery`, `giant`, `intra_degree`, `inter_degree` (time-averaged over the trajectory).
  - `cluster_leak_sweep(base_cfg, leak_values, degree, reps) -> dict` — keys `rows` (per leak: `leak, n, delivery_mean, ci_lo, ci_hi, giant_mean, intra_degree, inter_degree`), `degree`, `rwp_delivery`, `rwp_recovered` (bool), `regime_tag`.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_scenario.py` append:

```python
def _cluster_base(**kw):
    from soup_sim.config import Config
    d = dict(n=2, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="clustered",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=30.0,
             drain=0.0, n_messages=0, seen_margin=60.0, master_seed=5,
             n_clusters=6, cluster_sigma=6.0, cluster_leak=0.0)
    d.update(kw)
    return Config(**d)


def test_cluster_leak_sweep_structure_and_determinism():
    from soup_sim.scenario import cluster_leak_sweep
    a = cluster_leak_sweep(_cluster_base(), leak_values=[0.0, 1.0], degree=6.0, reps=2)
    b = cluster_leak_sweep(_cluster_base(), leak_values=[0.0, 1.0], degree=6.0, reps=2)
    assert a["rows"] == b["rows"]                              # deterministic
    assert "clustered" in a["regime_tag"]
    for r in a["rows"]:
        assert {"leak", "n", "delivery_mean", "giant_mean", "intra_degree", "inter_degree"} <= set(r)
    assert [r["leak"] for r in a["rows"]] == [0.0, 1.0]


def test_cluster_leak0_fragments_leak1_connects():
    from soup_sim.scenario import cluster_leak_sweep
    out = cluster_leak_sweep(_cluster_base(), leak_values=[0.0, 1.0], degree=8.0, reps=3)
    rows = {r["leak"]: r for r in out["rows"]}
    # islands (leak=0) deliver strictly less than the well-mixed (leak=1) crowd at the same degree
    assert rows[0.0]["delivery_mean"] < rows[1.0]["delivery_mean"]
    # and the giant component is smaller under islands
    assert rows[0.0]["giant_mean"] < rows[1.0]["giant_mean"]
    # RWP-recovery gate: leak=1 clustered delivery ~ RWP delivery at the same degree
    assert out["rwp_recovered"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario.py -q -k cluster`
Expected: FAIL (ImportError: `cluster_leak_sweep`).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/scenario.py`, extend the percolation import (line ~16) to include `largest_component_fraction`:

```python
from .percolation import same_component_pair_fraction, placement, largest_component_fraction
```

Then add, after `static_delivery_sweep(...)` (before `_airtime_arm`):

```python
CLUSTER_REGIME_TAG = "[MOBILITY REGIME = clustered gathering; uniform/RWP is the optimistic baseline]"


def _avg_snapshot_metrics(cfg, rng, n_snap=8):
    """Mobility-only (engine-free): build the mobility, then sample positions over the window and
    average same-component delivery + giant-component fraction (+ intra/inter-cluster degree). Captures
    transit-node bridging (a leaking mover physically connects clusters it passes through)."""
    mob = make_mobility(cfg, rng)
    r, w, h, b = cfg.radius, cfg.width, cfg.height, cfg.boundary
    steps = max(1, int(cfg.measure_window / max(n_snap, 1) / cfg.dt))
    deliv, giant, intra, inter = [], [], [], []
    home = mob.home
    for _ in range(n_snap):
        for _ in range(steps):
            mob.step(cfg.dt)
        pos = mob.positions
        deliv.append(same_component_pair_fraction(pos, r, w, h, b))
        giant.append(largest_component_fraction(pos, r, w, h, b))
        if home is not None:
            pairs = neighbor_pairs(pos, r, w, h, b)
            same = sum(1 for (i, j) in pairs if home[i] == home[j])
            intra.append(2.0 * same / cfg.n)
            inter.append(2.0 * (len(pairs) - same) / cfg.n)
    return {"delivery": float(np.mean(deliv)), "giant": float(np.mean(giant)),
            "intra_degree": float(np.mean(intra)) if intra else float("nan"),
            "inter_degree": float(np.mean(inter)) if inter else float("nan")}


def cluster_leak_sweep(base_cfg, leak_values, degree, reps):
    """Delivery + giant-component vs inter-cluster leak at a FIXED global mean-degree. Engine-free
    (mobility snapshots). RWP recovered at leak=1 (correctness gate). Every number is an UPPER BOUND
    on delivery and carries the clustered mobility-regime tag."""
    n = max(2, density_to_n(degree, base_cfg.width, base_cfg.height, base_cfg.radius))
    rows = []
    for li, leak in enumerate(leak_values):
        d, g, intra, inter = [], [], [], []
        for rep in range(reps):
            cfg = replace(base_cfg, n=n, mobility="clustered", cluster_leak=leak,
                          master_seed=_seed_for(base_cfg.master_seed, li, rep))
            m = _avg_snapshot_metrics(cfg, cfg.rng(0))
            d.append(m["delivery"]); g.append(m["giant"])
            intra.append(m["intra_degree"]); inter.append(m["inter_degree"])
        mean, lo, hi = mean_ci(d)
        rows.append({"leak": leak, "n": n, "delivery_mean": mean, "ci_lo": lo, "ci_hi": hi,
                     "giant_mean": float(np.mean(g)), "intra_degree": float(np.mean(intra)),
                     "inter_degree": float(np.mean(inter))})
    rwp = []
    for rep in range(reps):
        cfg = replace(base_cfg, n=n, mobility="rwp", master_seed=_seed_for(base_cfg.master_seed, 999, rep))
        rwp.append(_avg_snapshot_metrics(cfg, cfg.rng(0))["delivery"])
    rwp_delivery = float(np.mean(rwp))
    leak1 = next((r for r in rows if r["leak"] == 1.0), None)
    recovered = bool(leak1 is not None
                     and abs(leak1["delivery_mean"] - rwp_delivery) <= max(0.1, leak1["ci_hi"] - leak1["ci_lo"]))
    return {"rows": rows, "degree": degree, "rwp_delivery": rwp_delivery,
            "rwp_recovered": recovered, "regime_tag": CLUSTER_REGIME_TAG}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_scenario.py -q -k cluster`
Expected: PASS (2 passed). If `rwp_recovered` is flaky at reps=3, that indicates the leak=1 wander is not reaching the RWP distribution — re-check `_cluster_targets` (leak=1 must make every retarget uniform).

- [ ] **Step 5: Commit**

```bash
git add sim/soup_sim/scenario.py sim/tests/test_scenario.py
git commit -m "feat(sim): cluster leak-rate sweep — delivery/giant-component vs leak + RWP-recovery gate (slice-4 task 3)"
```

---

### Task 4: Report CSV + CLI preset + docs + non-regression

**Files:**
- Modify: `sim/soup_sim/report.py` (add `CLUSTER_FIELDS`, `cluster_to_csv_string`)
- Modify: `sim/run.py` (add `cluster_cfg`, `_run_cluster_delivery`, register `cluster-delivery` preset)
- Modify: `sim/README.md` (run command + slice-4 section + bias rows + module map)
- Test: `sim/tests/test_report.py` (append)

**Interfaces:**
- Consumes: `cluster_leak_sweep` output.
- Produces: `cluster_to_csv_string(out, manifest) -> str` — one row per leak carrying delivery/CI, giant, intra/inter degree, the regime tag as a column.

- [ ] **Step 1: Write the failing test**

In `sim/tests/test_report.py` append:

```python
def test_cluster_csv_has_fields_and_regime_tag():
    from soup_sim.report import cluster_to_csv_string, CLUSTER_FIELDS
    out = {
        "regime_tag": "[MOBILITY REGIME = clustered gathering; uniform/RWP is the optimistic baseline]",
        "degree": 8.0, "rwp_delivery": 0.95, "rwp_recovered": True,
        "rows": [
            {"leak": 0.0, "n": 110, "delivery_mean": 0.16, "ci_lo": 0.1, "ci_hi": 0.2,
             "giant_mean": 0.17, "intra_degree": 7.0, "inter_degree": 0.0},
            {"leak": 1.0, "n": 110, "delivery_mean": 0.93, "ci_lo": 0.9, "ci_hi": 0.95,
             "giant_mean": 0.97, "intra_degree": 1.2, "inter_degree": 6.0},
        ],
    }
    s = cluster_to_csv_string(out, {"master_seed": 5})
    lines = s.splitlines()
    assert lines[0].startswith("#") and "clustered" in lines[0]      # regime tag comment
    header = lines[1]
    for fld in CLUSTER_FIELDS:
        assert fld in header
    assert "regime_tag" in header and "param_master_seed" in header
    assert len(lines) == 1 + 1 + 2                                   # comment + header + 2 leak rows
    assert out["regime_tag"] in lines[2]                            # tag survives as a column value
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_report.py -q -k cluster`
Expected: FAIL (ImportError: `cluster_to_csv_string`).

- [ ] **Step 3: Write minimal implementation**

In `sim/soup_sim/report.py`, after `anonymity_defense_to_csv_string` (or near the other csv helpers), add:

```python
CLUSTER_FIELDS = ["leak", "n", "delivery_mean", "ci_lo", "ci_hi", "giant_mean",
                  "intra_degree", "inter_degree"]


def cluster_to_csv_string(out, manifest) -> str:
    """One row per inter-cluster leak. The mobility-regime tag travels as a leading comment AND a
    column on every row (a comment alone is dropped by dataframe readers)."""
    man = list(manifest.keys())
    header = CLUSTER_FIELDS + ["regime_tag"] + [f"param_{k}" for k in man]
    buf = io.StringIO()
    buf.write(f"# {out['regime_tag']}  degree={out['degree']} rwp_delivery={out['rwp_delivery']:.3f} "
              f"rwp_recovered={out['rwp_recovered']}\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in out["rows"]:
        w.writerow([r.get(k) for k in CLUSTER_FIELDS] + [out["regime_tag"]] + [manifest[k] for k in man])
    return buf.getvalue()
```

- [ ] **Step 4: Run report test to verify it passes**

Run: `cd sim && .venv/Scripts/python.exe -m pytest tests/test_report.py -q -k cluster`
Expected: PASS.

- [ ] **Step 5: Wire the CLI preset**

In `sim/run.py`, extend the scenario import to include `cluster_leak_sweep` and the report import to include `cluster_to_csv_string`:

```python
from soup_sim.scenario import (static_delivery_sweep, midpoint_with_ci, airtime_sweep, anonymity_sweep,
                               anonymity_defense_sweep, intersection_sweep, cluster_leak_sweep)
from soup_sim.report import (write_csv, plot, airtime_to_csv_string, airtime_plot,
                             anonymity_to_csv_string, anonymity_plot, anonymity_defense_to_csv_string,
                             intersection_to_csv_string, cluster_to_csv_string)
```

Add after `_run_anonymity_intersection`:

```python
def cluster_cfg(seed: int) -> Config:
    return Config(
        n=0, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="clustered",
        speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=200, throughput_ideal=1e9,
        alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=60.0,
        drain=0.0, n_messages=0, seen_margin=60.0, master_seed=seed,
        n_clusters=8, cluster_sigma=6.0, cluster_leak=0.0,
    )


def _run_cluster_delivery(args) -> None:
    cfg = cluster_cfg(args.seed)
    reps = max(args.reps, 6)
    out = cluster_leak_sweep(cfg, leak_values=[0.0, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0], degree=6.0, reps=reps)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(cluster_to_csv_string(out, cfg.manifest()))
    print(f"wrote {args.out} (leak sweep @ global degree {out['degree']}, K={cfg.n_clusters}, reps={reps})")
    print(out["regime_tag"])
    for r in out["rows"]:
        print(f"  leak={r['leak']:>4}: delivery {r['delivery_mean']:.2f} (giant {r['giant_mean']:.2f}; "
              f"intra-deg {r['intra_degree']:.1f}, inter-deg {r['inter_degree']:.1f})")
    print(f"RWP reference delivery (same degree): {out['rwp_delivery']:.2f}  ->  "
          f"leak=1 recovers RWP: {out['rwp_recovered']}")
    print("note: every delivery number is an UPPER BOUND on real delivery; uniform/RWP is the optimistic")
    print("      baseline -- clustering is the optimism-removing axis (real crowds gather).")
```

Register the preset choice + dispatch in `main()`:

```python
    ap.add_argument("--preset",
                    choices=["static-cliff", "airtime-knee", "anonymity", "anonymity-defenses",
                             "anonymity-intersection", "cluster-delivery"],
                    default="static-cliff")
```
and in the dispatch chain:
```python
    elif args.preset == "cluster-delivery":
        _run_cluster_delivery(args)
```

- [ ] **Step 6: Smoke the CLI**

Run: `cd sim && .venv/Scripts/python.exe run.py --preset cluster-delivery --out out/cluster_smoke.csv --reps 6`
Expected: prints the leak curve (delivery rising from ~1/K at leak=0 toward the RWP value at leak=1), `leak=1 recovers RWP: True`. (Takes ~1-2 min; engine-free.)

- [ ] **Step 7: Update the README**

In `sim/README.md`: add under the preset block:
```
.venv/Scripts/python run.py --preset cluster-delivery --out out/cluster.csv  # slice-4: delivery vs clustering
```
Add a `## Clustered "gathering" mobility (slice 4 — PR-1)` section after the anonymity sections describing: the model (static clusters + intra-cluster RWP + uniform-wander leak; leak=0 islands, leak=1 recovers RWP); the leak-rate sweep (delivery + giant-component at fixed global degree); the honest finding (delivery collapses toward the within-cluster floor ~1/K as leak→0, recovering the RWP value as leak→1 — clustering can fragment the mesh below the uniform cliff's promise); and the RWP-recovery correctness gate. Use the actual numbers from the Step 6 run. Add bias-table rows:
```
| clustered "gathering" mobility (vs RWP open-field) | — | slice-4: **optimism-REMOVING** — real crowds cluster; clustered delivery <= RWP at the same global degree |
| clustered: static clusters (no gather->disperse) | — | abstraction; a forming/dispersing crowd is transient (named follow-up) |
| clustered: leak=1 recovers RWP | — | correctness sanity gate, not a bias |
```
Update the Module map line to mention `cluster_leak_sweep` and the `clustered` mobility mode.

- [ ] **Step 8: Full non-regression + commit**

Run: `cd sim && .venv/Scripts/python.exe -m pytest -q`
Expected: PASS (all prior tests + the new ones; slow deselected). Confirm no prior count regressed (static/rwp bit-identical: the engine + percolation + airtime + anonymity gates unchanged).

```bash
git add sim/soup_sim/report.py sim/run.py sim/README.md sim/tests/test_report.py
git commit -m "feat(sim): cluster CSV + cluster-delivery preset + slice-4 docs (slice-4 task 4)"
```

---

## Self-Review

**1. Spec coverage:**
- §1 model (static clusters, home, cluster-aware retarget, leak=0/1 limits) → Tasks 1-2. ✓ (leak semantics = uniform-wander, clarified in Global Constraints so the leak=1≡RWP DoD gate holds exactly.)
- §2 config (n_clusters, cluster_sigma, cluster_leak + validate) → Task 1. ✓
- §3 headline (delivery + giant-component + intra/inter degree vs leak; RWP-recovery PASS/FAIL) → Tasks 3-4. ✓
- §4 architecture (additive, mobility-agnostic, no new RNG tag, default-inert) → Tasks 1-4; cluster layout on tag-0 mobility substream. ✓
- §5 bias table → Task 4 Step 7. ✓
- §6 DoD (deterministic, RWP-recovery gate test, leak=0 isolation test, regime tag on every number, non-regression, one-command run, README) → Tasks 2-4. ✓
- §7 decisions → all reflected. ✓

**2. Placeholder scan:** No TBD/TODO; every code step has complete code; README Step 7 references the Step 6 run for real numbers (not a placeholder — an instruction to use measured output). ✓

**3. Type consistency:** `make_mobility` returns a `Mobility` with `.home`/`.centers`/`.n_clusters` used by `_avg_snapshot_metrics` (Task 3) — defined in Task 2. `cluster_leak_sweep` output keys (`rows`, `regime_tag`, `degree`, `rwp_delivery`, `rwp_recovered`) match `cluster_to_csv_string` (Task 4) and `_run_cluster_delivery` (Task 4). `CLUSTER_FIELDS`/`CLUSTER_REGIME_TAG` consistent across report/scenario. Config field names (`n_clusters`, `cluster_sigma`, `cluster_leak`) consistent Task 1 → 2 → 3. ✓

**Note (spec clarification, intentional):** the leak semantics are "uniform-wander" not "target another specific cluster" — this is what makes the spec's own DoD RWP-recovery gate hold for any `cluster_sigma`; it is the conservative, simplest model and is documented in Global Constraints + the README.
