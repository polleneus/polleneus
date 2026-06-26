import numpy as np
from soup_sim.config import Config
from soup_sim.scenario import (
    density_to_n, mean_ci, crossing_0p5, midpoint_with_ci, run_one, sweep,
)


def cfg(**kw):
    d = dict(n=50, width=100.0, height=100.0, radius=15.0, boundary="torus",
             mobility="static", speed_min=1.0, speed_max=1.0, dt=1.0, ttl=200.0,
             buffer_cap=10 ** 6, throughput_ideal=1e9, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=300.0,
             drain=300.0, n_messages=20, seen_margin=200.0, master_seed=5)
    d.update(kw)
    return Config(**d)


def test_buffer_substreams_disjoint_from_cohort_and_engine():
    # buffer path (3, i) must never alias mobility(0)/engine(1)/cohort(2) even at large i
    from soup_sim.config import make_rng
    base = 12345
    others = {tuple(make_rng(base, t).integers(0, 1 << 31, 4)) for t in (0, 1, 2)}
    for i in (0, 1, 1000, 2000, 6000):
        s = tuple(make_rng(base, 3, i).integers(0, 1 << 31, 4))
        assert s not in others


def test_density_to_n_roundtrip():
    n = density_to_n(5.0, 200.0, 200.0, 10.0)
    d_back = n * np.pi * 100 / (200.0 * 200.0)
    assert abs(d_back - 5.0) < 0.05


def test_mean_ci_basic():
    m, lo, hi = mean_ci([0.4, 0.5, 0.6])
    assert abs(m - 0.5) < 1e-9 and lo < m < hi


def test_crossing_and_midpoint_recovers_synthetic_sigmoid():
    densities = list(np.linspace(2.0, 10.0, 17))
    d0 = 6.0
    mean_ratios = [1.0 / (1.0 + np.exp(-2.0 * (d - d0))) for d in densities]
    assert abs(crossing_0p5(densities, mean_ratios) - d0) < 0.3
    # build a per-rep matrix that averages to the sigmoid (3 identical reps)
    rows = [{"density": d, "per_rep_ratios": [r, r, r]} for d, r in zip(densities, mean_ratios)]
    info = midpoint_with_ci(rows, np.random.default_rng(0))
    assert abs(info["midpoint"] - d0) < 0.3


def test_run_one_static_stationary_and_ratio_in_range():
    r = run_one(cfg())
    assert 0.0 <= r["delivery_ratio"] <= 1.0
    assert r["stationary_ok"] is True  # static -> constant degree -> stationary


def test_sweep_deterministic_same_seed():
    base = cfg(n=0)  # n is set per-density inside sweep
    a = sweep(base, [3.0, 8.0], reps=2)
    b = sweep(base, [3.0, 8.0], reps=2)
    assert [row["delivery_mean"] for row in a] == [row["delivery_mean"] for row in b]
    assert [row["n"] for row in a] == [row["n"] for row in b]


# --- slice-4: clustered mobility leak-rate sweep ---------------------------------
def _cluster_base(**kw):
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
        assert {"leak", "n", "delivery_mean", "giant_mean", "intra_degree", "inter_degree",
                "realized_degree"} <= set(r)
    assert [r["leak"] for r in a["rows"]] == [0.0, 1.0]


def test_cluster_leak0_fragments_leak1_connects():
    from soup_sim.scenario import cluster_leak_sweep
    out = cluster_leak_sweep(_cluster_base(), leak_values=[0.0, 1.0], degree=8.0, reps=3)
    rows = {r["leak"]: r for r in out["rows"]}
    assert rows[0.0]["delivery_mean"] < rows[1.0]["delivery_mean"]   # islands deliver less than well-mixed
    assert rows[0.0]["giant_mean"] < rows[1.0]["giant_mean"]         # smaller giant component under islands
    assert out["rwp_recovered"] is True                             # leak=1 ~ RWP at the same N
    # honest framing: realized global degree is NOT fixed -- it is HIGHER at leak=0 (clustering
    # concentrates nodes) even though delivery is LOWER (fragmentation despite dense local degree).
    assert rows[0.0]["realized_degree"] > rows[1.0]["realized_degree"]
