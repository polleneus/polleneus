import numpy as np
import pytest
from soup_sim.config import Config


def base(**kw):
    d = dict(n=100, width=100.0, height=100.0, radius=10.0, boundary="torus",
             mobility="static", speed_min=1.0, speed_max=1.0, dt=0.1, ttl=600.0,
             buffer_cap=200, throughput_ideal=1000.0, alpha=0.5, t_setup=0.2,
             p_fail=0.0, blob_size=1000.0, warmup=0.0, measure_window=600.0,
             drain=600.0, n_messages=200, seen_margin=60.0, master_seed=42)
    d.update(kw)
    return Config(**d)


def test_cfl_violation_raises():
    with pytest.raises(ValueError, match="CFL"):
        base(speed_max=1000.0, dt=1.0, radius=10.0).validate()


def test_cfl_ok_passes():
    base(speed_max=1.0, dt=0.1, radius=10.0).validate()


def test_rwp_requires_positive_speed_min():
    with pytest.raises(ValueError, match="rwp"):
        base(mobility="rwp", speed_min=0.0, speed_max=1.0).validate()


def test_clustered_mobility_validates():
    c = base(mobility="clustered", speed_min=1.0, speed_max=1.0, n_clusters=8,
             cluster_sigma=10.0, cluster_leak=0.1)
    c.validate()                                          # ok
    with pytest.raises(ValueError, match="n_clusters"):
        base(mobility="clustered", speed_min=1.0, speed_max=1.0, n_clusters=0).validate()
    with pytest.raises(ValueError, match="cluster_leak"):
        base(mobility="clustered", speed_min=1.0, speed_max=1.0, cluster_leak=1.5).validate()
    with pytest.raises(ValueError, match="rwp|clustered|speed_min"):
        base(mobility="clustered", speed_min=0.0, speed_max=1.0).validate()   # moving model needs speed>0


def test_rng_substreams_independent_and_deterministic():
    c = base()
    a1 = c.rng(1).integers(0, 1_000_000, 5)
    a2 = base().rng(1).integers(0, 1_000_000, 5)
    b = c.rng(2).integers(0, 1_000_000, 5)
    assert np.array_equal(a1, a2)
    assert not np.array_equal(a1, b)


def test_rng_all_tags_disjoint_incl_intersection():
    # every tag used across slices must yield a distinct stream — incl. PR-3 top-level tag 7, the PR-2
    # child path (2,7) [background soup], and the airtime-bootstrap tag 777. (2,7) != top-level 7.
    c = base()
    paths = [(0,), (1,), (2,), (3, 0), (4,), (5,), (6,), (7,), (2, 7), (777,)]
    firsts = [int(c.rng(*p).integers(0, 2**31)) for p in paths]
    assert len(set(firsts)) == len(paths)        # all streams distinct
    assert int(c.rng(7).integers(0, 2**31)) != int(c.rng(2, 7).integers(0, 2**31))
