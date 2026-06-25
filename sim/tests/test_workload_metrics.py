import numpy as np
from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.workload import make_cohort
from soup_sim.metrics import Metrics


def cfg(**kw):
    d = dict(n=10, width=100.0, height=100.0, radius=10.0, boundary="torus",
             mobility="static", speed_min=1.0, speed_max=1.0, dt=1.0, ttl=100.0,
             buffer_cap=100, throughput_ideal=1e9, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1000.0,
             drain=100.0, n_messages=20, seen_margin=100.0, master_seed=3)
    d.update(kw)
    return Config(**d)


def test_cohort_distinct_src_dst():
    c = cfg(n=10, n_messages=20)
    coh = make_cohort(c, inject_time=0.0, rng=c.rng())
    assert len(coh) == 20
    for blob, s, d in coh:
        assert s != d and 0 <= s < 10 and 0 <= d < 10
        assert blob.created_at == 0.0 and blob.ttl == c.ttl


def test_delivery_counted_once_no_resurrection_inflation():
    c = cfg(ttl=100.0, measure_window=1000.0)
    m = Metrics(c, warmup_end=0.0, measure_window=1000.0)
    b = Blob(0, 0.0, 100.0, 1.0)
    m.register(b, src=1, dst=2)
    m.on_deliver(2, b, now=5.0)
    m.on_deliver(2, b, now=9.0)  # re-receipt must not inflate
    assert m.fair_chance_delivered() == 1
    assert m.latencies() == [5.0]


def test_fair_chance_excludes_right_censored():
    c = cfg(ttl=100.0, measure_window=200.0)
    m = Metrics(c, warmup_end=0.0, measure_window=200.0)
    in_window = Blob(1, created_at=50.0, ttl=100.0, size=1.0)   # 150 <= 200 -> fair
    late = Blob(2, created_at=150.0, ttl=100.0, size=1.0)       # 250 > 200 -> excluded
    m.register(in_window, 0, 1)
    m.register(late, 0, 1)
    assert set(m.fair_chance_ids()) == {1}


def test_overhead_ratio_and_undefined():
    c = cfg()
    m = Metrics(c, 0.0, 1000.0)
    b = Blob(0, 0.0, 100.0, 1.0)
    m.register(b, 0, 1)
    m.on_deliver(1, b, 3.0)
    assert m.overhead_ratio(transmissions=10) == 10.0
    m2 = Metrics(c, 0.0, 1000.0)
    assert m2.overhead_ratio(5) == float("inf")
