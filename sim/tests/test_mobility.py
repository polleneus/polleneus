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


# --- slice-4: clustered "gathering" mobility -------------------------------------
def _ccfg(**kw):
    d = dict(n=60, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="clustered",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=60.0, buffer_cap=50, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=60.0,
             drain=0.0, n_messages=0, seen_margin=60.0, master_seed=7,
             n_clusters=6, cluster_sigma=6.0, cluster_leak=0.0)
    d.update(kw)
    return Config(**d)


def test_clustered_layout_and_homes():
    c = _ccfg()
    mob = make_mobility(c, c.rng(0))
    assert mob.mode == "clustered" and mob.centers.shape == (6, 2) and len(mob.home) == 60
    assert set(mob.home.tolist()) == set(range(6))            # round-robin uses every cluster
    assert mob.positions.shape == (60, 2)


def test_clustered_deterministic():
    c = _ccfg()
    a = make_mobility(c, c.rng(0)).positions
    b = make_mobility(c, c.rng(0)).positions
    assert np.array_equal(a, b)


def _same_home_frac(mob, c, steps=200):
    from soup_sim.cell_list import neighbor_pairs
    for _ in range(steps):
        mob.step(c.dt)
    pairs = neighbor_pairs(mob.positions, c.radius, c.width, c.height, c.boundary)
    return sum(1 for (i, j) in pairs if mob.home[i] == mob.home[j]) / max(1, len(pairs))


def test_leak0_keeps_nodes_near_home_leak1_spreads():
    # leak=0 keeps neighbors overwhelmingly intra-cluster; leak=1 mixes across homes toward ~1/K.
    # (Absolute thresholds are loose because random center placement can put two clusters close —
    # cluster overlap is realistic; the robust invariant is the CONTRAST leak=0 >> leak=1.)
    c0 = _ccfg(cluster_leak=0.0)
    c1 = _ccfg(cluster_leak=1.0)
    same0 = _same_home_frac(make_mobility(c0, c0.rng(0)), c0)
    same1 = _same_home_frac(make_mobility(c1, c1.rng(0)), c1)
    assert same0 > 1.0 / c0.n_clusters + 0.15               # leak=0 clearly above the uniform 1/K floor
    assert same0 > same1 + 0.15                             # and clearly more clustered than leak=1


def test_static_rwp_have_no_cluster_attrs():
    cs = _ccfg(mobility="static")
    cr = _ccfg(mobility="rwp")
    assert make_mobility(cs, cs.rng(0)).home is None
    assert make_mobility(cr, cr.rng(0)).home is None
