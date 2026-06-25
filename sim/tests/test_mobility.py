import numpy as np
from soup_sim.config import Config
from soup_sim.mobility import make_mobility, mean_degree, stationarity_ok


def cfg(**kw):
    d = dict(n=100, width=100.0, height=100.0, radius=10.0, boundary="torus",
             mobility="static", speed_min=1.0, speed_max=2.0, dt=0.5, ttl=600.0,
             buffer_cap=200, throughput_ideal=1000.0, alpha=0.5, t_setup=0.2,
             p_fail=0.0, blob_size=1000.0, warmup=0.0, measure_window=600.0,
             drain=600.0, n_messages=200, seen_margin=60.0, master_seed=1)
    d.update(kw)
    return Config(**d)


def test_static_in_bounds_zero_velocity():
    c = cfg(mobility="static", n=200)
    m = make_mobility(c, c.rng())
    assert m.positions.shape == (200, 2)
    assert (m.positions >= 0).all() and (m.positions[:, 0] <= c.width).all() and (m.positions[:, 1] <= c.height).all()
    assert np.allclose(m.velocities, 0.0)


def test_static_mean_degree_torus_within_5pct():
    c = cfg(mobility="static", n=2000, width=200.0, height=200.0, radius=10.0)
    m = make_mobility(c, c.rng())
    expected = c.n * np.pi * c.radius ** 2 / (c.width * c.height)
    md = mean_degree(m.positions, c.radius, c.width, c.height, "torus")
    assert abs(md - expected) / expected < 0.05, (md, expected)


def test_rwp_no_speed_decay_first_vs_second_half():
    c = cfg(mobility="rwp", n=200, width=100.0, height=100.0,
            speed_min=1.0, speed_max=2.0, dt=0.2, radius=10.0)
    m = make_mobility(c, c.rng())
    samples = []
    for _ in range(400):
        m.step(c.dt)
        samples.append(m.mean_speed())
    first, second = np.mean(samples[:200]), np.mean(samples[200:])
    assert abs(first - second) / first < 0.10, (first, second)


def test_rwp_positions_stay_in_bounds():
    c = cfg(mobility="rwp", n=100, dt=0.2, radius=10.0)
    m = make_mobility(c, c.rng())
    for _ in range(100):
        m.step(c.dt)
    assert (m.positions >= -1e-6).all()
    assert (m.positions[:, 0] <= c.width + 1e-6).all() and (m.positions[:, 1] <= c.height + 1e-6).all()


def test_stationarity_ok_flat_true_drift_false():
    assert stationarity_ok(10.0, 10.3, 0.1) is True
    assert stationarity_ok(5.0, 10.0, 0.1) is False
