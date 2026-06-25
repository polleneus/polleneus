import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import airtime_sweep


# TINY arena for the fast default-suite smoke test: n = d*W*H/(pi r^2) = d*30*30/(pi*64) ~= d*4.5
def tiny():
    return Config(n=0, width=30.0, height=30.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=15.0, buffer_cap=30, throughput_ideal=8e3,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=4.0, measure_window=8.0,
                  drain=0.0, n_messages=8, seen_margin=10.0, master_seed=7,
                  airtime_model="collision", beta=0.15, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)


# SMALL arena for the realistic (slow) sweeps: density 16 -> n ~= 154.
# Params tuned so the COLLISION arm produces a clear contention-bound interior knee (~d=9) while
# the LINEAR arm stays monotone (plateau) on the [3..16] grid (verified: collision knee@~6.8,
# linear no_knee). beta is uncalibrated (README provenance); this fixture exercises the apparatus.
def base():
    return Config(n=0, width=55.0, height=55.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=40.0, buffer_cap=200, throughput_ideal=8e3,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=10.0, measure_window=30.0,
                  drain=0.0, n_messages=40, seen_margin=20.0, master_seed=7,
                  airtime_model="collision", beta=0.3, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)


def replace_model(cfg, model):
    return replace(cfg, airtime_model=model, alpha=1.0, beta=0.15)


def test_airtime_sweep_smoke_structure_and_determinism():
    # fast: tiny arena, 2 densities, 1 rep -> exercises both control arms, knee, gate, determinism
    dens = [3.0, 6.0]
    out1 = airtime_sweep(tiny(), densities=dens, reps=1)
    out2 = airtime_sweep(tiny(), densities=dens, reps=1)
    assert [r["circulated_per_min_mean"] for r in out1["rows"]] == [r["circulated_per_min_mean"] for r in out2["rows"]]
    assert out1["knee"] == out2["knee"] and out1["gate"] == out2["gate"]   # fully deterministic
    assert len(out1["alpha0_rows"]) == len(dens) and len(out1["capttl_rows"]) == len(dens)
    assert "publish" in out1["gate"]
    for r in out1["rows"]:
        assert {"circulated_per_min_mean", "utilization_mean", "delivery_mean", "t50", "binding"} <= set(r)
        assert 0.0 <= r["utilization_mean"] <= 1.0 + 1e-9


@pytest.mark.slow   # realistic sweep (~minute-scale); excluded from default -m "not slow"
def test_airtime_sweep_controls_and_determinism():
    dens = [3.0, 6.0, 9.0, 12.0, 16.0]
    out1 = airtime_sweep(base(), densities=dens, reps=2)
    out2 = airtime_sweep(base(), densities=dens, reps=2)
    assert [r["circulated_per_min_mean"] for r in out1["rows"]] == [r["circulated_per_min_mean"] for r in out2["rows"]]
    assert out1["knee"] == out2["knee"] and out1["gate"] == out2["gate"]


@pytest.mark.slow   # falsifiable prediction: collision turns over (knee), linear plateaus (no knee)
def test_collision_knee_linear_plateau_distinguishable():
    dens = [3.0, 6.0, 9.0, 12.0, 16.0]
    coll = airtime_sweep(base(), dens, reps=6)
    lin = airtime_sweep(replace_model(base(), "linear"), dens, reps=6)
    assert coll["knee"]["status"] == "knee"
    assert lin["knee"]["status"] == "no_knee_in_range"
