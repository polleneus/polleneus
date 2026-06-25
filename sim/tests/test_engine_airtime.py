import numpy as np
from soup_sim.config import Config
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.budget import AirtimeBudget
from soup_sim.buffer import NodeBuffer
from soup_sim.blob import Blob

BIG = 10 ** 9


def cfg(**kw):
    d = dict(n=4, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0, cs_radius_mult=3.0)
    d.update(kw)
    return Config(**d)


def test_contenders_use_carrier_sense_radius_not_connectivity():
    # line at 0/8/16/24, r=10: connectivity max degree = 2; carrier-sense (3*r=30) degree = 3.
    seen = {}
    c = cfg()
    pos = np.array([[0., 50.], [8., 50.], [16., 50.], [24., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(4)]
    budget = AirtimeBudget(1e12, 0, 0, 0, 1.0)
    orig = budget.effective_goodput
    budget.effective_goodput = lambda n: seen.__setitem__("max_n", max(seen.get("max_n", 0), n)) or orig(n)
    eng = Engine(c, mob, bufs, budget, c.rng(1), on_deliver=lambda *_: None)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(2.0)
    eng.finalize()
    assert seen.get("max_n", 0) >= 3   # only carrier-sense range yields degree 3 here


def _two_node(throughput, dt, t_setup=0.0, slope=0.0, ttl=1e12, run=10.0, blobs=5, model="linear"):
    c = cfg(n=2, dt=dt, throughput_ideal=throughput, t_setup=t_setup, t_setup_slope=slope,
            ttl=ttl, cs_radius_mult=1.0, airtime_model=model)
    pos = np.array([[50., 50.], [55., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, ttl + 1e9, c.rng(3, i)) for i in range(2)]
    budget = AirtimeBudget(throughput, 0, t_setup, 0, 1.0, model=model, t_setup_slope=slope)
    eng = Engine(c, mob, bufs, budget, c.rng(1), on_deliver=lambda *_: None)
    for k in range(blobs):
        eng.inject(Blob(k, 0.0, ttl, 1.0), 0)
    eng.run_until(run)
    eng.finalize()
    return eng


def test_airtime_accounting_bounds():
    eng = _two_node(throughput=2.0, dt=1.0)
    assert eng.available_contact_time > 0
    assert 0.0 <= eng.charged_airtime <= eng.available_contact_time + 1e-9
    assert eng.offered_blobs >= eng.served_blobs >= 1
    assert eng.offered_airtime >= eng.charged_airtime - 1e-9


def test_t_setup_charged_once_per_episode():
    # long contact spanning 100 steps, big setup; charged setup must be ~1x, not 100x.
    eng = _two_node(throughput=1e9, dt=0.1, t_setup=0.5, run=10.0, blobs=3)
    assert abs(eng.charged_airtime - 0.5) < 0.05


def test_setup_starved_blobs_counted():
    # t_setup (1000) exceeds the whole contact -> setup-starved, nothing served, unmet -> setup_starved_blobs
    eng = _two_node(throughput=1e9, dt=1.0, t_setup=1000.0, run=10.0, blobs=3)
    assert eng.served_blobs == 0 and eng.setup_starved_blobs == 3 and eng.contention_blobs == 0


def test_utilization_le_one_under_varying_contention():
    # contention varies within the contact; util must stay <= 1 (per-step billing at accrual eff)
    eng = _two_node(throughput=8e3, dt=0.5, t_setup=0.05, slope=0.0, run=20.0, blobs=50, model="collision")
    assert eng.charged_airtime <= eng.available_contact_time + 1e-9
