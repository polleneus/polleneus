import numpy as np
from soup_sim.config import Config
from soup_sim.adversary import place_receivers, realized_coverage, hearings


def cfg(**kw):
    d = dict(n=50, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e4,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=60.0, master_seed=3, adversary_range_mult=1.0)
    d.update(kw)
    return Config(**d)


def test_realized_coverage_increases_with_f():
    c = cfg()
    covs = [realized_coverage(place_receivers(c, f, "uniform", c.rng(4)), c.radius, c, c.rng(4))
            for f in (0.1, 0.4, 0.8)]
    assert covs[0] < covs[1] < covs[2]
    assert 0.0 <= covs[0] and covs[2] <= 1.0


def test_placement_deterministic():
    c = cfg()
    a = place_receivers(c, 0.5, "uniform", c.rng(4))
    b = place_receivers(c, 0.5, "uniform", c.rng(4))
    assert np.array_equal(a, b)


def test_chokepoint_differs_from_uniform():
    c = cfg()
    u = place_receivers(c, 0.4, "uniform", c.rng(4))
    k = place_receivers(c, 0.4, "chokepoint", c.rng(4))
    assert not (u.shape == k.shape and np.allclose(u, k))


def test_receiver_hears_in_range_holder_only():
    # holder of blob 7 sits at (50,50) for the whole log; R0 near, R1 far
    c = cfg(width=2000.0, height=200.0, boundary="walls")
    log = [(float(t), np.array([[50., 50.], [55., 50.]])) for t in range(5)]
    acquired = {(0, 7): 0.0}                  # node0 holds blob 7 from t=0
    recv = np.array([[58., 50.], [900., 50.]])
    h = hearings(recv, 10.0, log, acquired, {7: 1e12}, c)
    assert h[(0, 7)] == 0.0 and (1, 7) not in h


def test_hearing_respects_hold_lifetime():
    # node acquires blob 9 only at t=3 -> not heard before then
    c = cfg(width=2000.0, height=200.0, boundary="walls")
    log = [(float(t), np.array([[58., 50.]])) for t in range(6)]
    acquired = {(0, 9): 3.0}
    h = hearings(np.array([[58., 50.]]), 10.0, log, acquired, {9: 1e12}, c)
    assert h[(0, 9)] == 3.0
