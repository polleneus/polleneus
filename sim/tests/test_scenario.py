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
