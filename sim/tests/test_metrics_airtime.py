from soup_sim.metrics import Metrics
from soup_sim.config import Config
from soup_sim.blob import Blob


def _cfg(**kw):
    d = dict(n=2, width=1.0, height=1.0, radius=1.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=100.0, buffer_cap=10 ** 9, throughput_ideal=1.0,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=120.0,
             drain=0.0, n_messages=0, seen_margin=1.0, master_seed=0)
    d.update(kw)
    return Config(**d)


def test_utilization_and_circulation():
    m = Metrics(_cfg(), warmup_end=0.0, measure_window=120.0)
    assert abs(m.utilization(30.0, 120.0) - 0.25) < 1e-9
    assert m.utilization(0.0, 0.0) == 0.0
    assert abs(m.utilization_vs_offered(30.0, 60.0) - 0.5) < 1e-9
    assert abs(m.circulated_per_min(240, 120.0) - 120.0) < 1e-9


def test_t50_is_censoring_aware():
    c = _cfg(ttl=100.0, measure_window=100.0)
    m = Metrics(c, warmup_end=0.0, measure_window=100.0)
    for i in range(4):
        m.register(Blob(i, 0.0, 100.0, 1.0), 0, 1)
    for (i, t) in [(0, 10.0), (1, 20.0), (2, 80.0)]:
        m.delivered_at[i] = t
    assert abs(m.t50() - 20.0) < 1e-9            # 2/4 delivered by t=20
    m2 = Metrics(c, warmup_end=0.0, measure_window=100.0)
    for i in range(4):
        m2.register(Blob(i, 0.0, 100.0, 1.0), 0, 1)
    m2.delivered_at[0] = 5.0
    assert m2.t50() is None                       # <50% ever delivered -> censored, not a flattering 5.0
    assert m2.delivery_ratio() == 0.25            # reported jointly
