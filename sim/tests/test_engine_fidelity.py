import numpy as np
from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer
from soup_sim.budget import AirtimeBudget
from soup_sim.mobility import Mobility, make_mobility
from soup_sim.engine import Engine
from soup_sim.analytics import (
    expected_relative_speed, expected_contact_duration, analytic_meeting_rate_per_node,
)
from soup_sim.percolation import temporal_reachable, same_component_pairs

BIG = 10 ** 9


def _cfg(**kw):
    d = dict(n=120, width=140.0, height=140.0, radius=16.0, boundary="torus", mobility="rwp",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=1e12, buffer_cap=BIG,
             throughput_ideal=1e12, alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0,
             warmup=0.0, measure_window=1.0, drain=0.0, n_messages=0, seen_margin=1e12, master_seed=1)
    d.update(kw)
    return Config(**d)


def _spread_engine(c, one_hop=False):
    mob = make_mobility(c, c.rng(0))
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(c.n)]
    return Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1),
                  on_deliver=lambda *_: None, one_hop=one_hop), bufs


# --- analytic forms ---------------------------------------------------------
def test_analytic_forms():
    assert abs(expected_relative_speed(3.0) - (4.0 / np.pi) * 3.0) < 1e-9
    assert abs(expected_contact_duration(8.0, 3.0) - (np.pi * 8.0 / (2 * 3.0))) < 1e-9
    assert abs(analytic_meeting_rate_per_node(8.0, 3.0, 300, 40000.0) - (2 * 8 * 3 * 299 / 40000.0)) < 1e-9


# --- Task 1: contact-timing sanity gate (runs the engine) -------------------
def test_contact_timing_matches_rwp_analytics():
    durs, rates = [], []
    for s in range(3):
        c = _cfg(n=250, width=200.0, height=200.0, radius=8.0, speed_min=3.0, speed_max=3.0,
                 dt=0.5, master_seed=s)
        eng, _ = _spread_engine(c)
        T = 40.0
        eng.run_until(T)
        eng.finalize()
        durs.append(eng.mean_contact_duration())
        rates.append(2.0 * len(eng.episodes) / (c.n * T))
    v_rel = expected_relative_speed(3.0)
    exp_dur = expected_contact_duration(8.0, v_rel)
    exp_rate = analytic_meeting_rate_per_node(8.0, v_rel, 250, 200.0 * 200.0)
    assert 0.5 * exp_dur <= np.mean(durs) <= 2.0 * exp_dur, (np.mean(durs), exp_dur)
    assert 0.5 * exp_rate <= np.mean(rates) <= 2.0 * exp_rate, (np.mean(rates), exp_rate)


# --- Task 5: temporal-reachability oracle ----------------------------------
def test_temporal_reachable_respects_time_order():
    assert temporal_reachable([(0, 1, 1.0), (1, 2, 2.0)], 0, 3) == {0, 1, 2}   # journey exists
    assert temporal_reachable([(1, 2, 1.0), (0, 1, 2.0)], 0, 3) == {0, 1}      # B-C before B infected


def test_engine_matches_temporal_reachability():
    for s in range(5):
        c = _cfg(master_seed=s)
        eng, bufs = _spread_engine(c)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(80.0)
        eng.finalize()
        delivered = {k for k in range(c.n) if bufs[k].has(0)}
        oracle = temporal_reachable(eng.episodes, 0, c.n)
        assert delivered == oracle, (s, len(delivered), len(oracle))


def test_one_hop_mutant_fails_the_gate():
    for s in range(5):
        c = _cfg(master_seed=s)
        eng, bufs = _spread_engine(c, one_hop=True)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(80.0)
        eng.finalize()
        delivered = {k for k in range(c.n) if bufs[k].has(0)}
        oracle = temporal_reachable(eng.episodes, 0, c.n)
        assert delivered < oracle and len(delivered) < len(oracle)


# --- Task 6: multi-hop both-arms + non-regression --------------------------
def _linear_engine(positions, velocities, c, t_setup=0.0):
    pos = np.array(positions, float)
    mob = Mobility("linear", pos, np.array(velocities, float), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(len(pos))]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0.0, t_setup, 0.0, 1.0), c.rng(1),
                 on_deliver=lambda *_: None)
    return eng, bufs


def test_multihop_over_time_positive_and_negatives():
    base = dict(n=3, width=2000.0, height=200.0, radius=10.0, boundary="walls", dt=1.0, ttl=1e12)
    # node0 (blob) static; node1 courier moves +x past node0 then to node2; node2 static far.
    # POSITIVE: node2 reachable at x=100 via the courier
    c = _cfg(**base, master_seed=1)
    eng, bufs = _linear_engine([[0., 50.], [0., 50.], [100., 50.]], [[0., 0.], [2., 0.], [0., 0.]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    assert bufs[2].has(0)
    # NEGATIVE-1: node2 too far for the courier to ever bridge -> not delivered
    c = _cfg(**base, master_seed=1)
    eng, bufs = _linear_engine([[0., 50.], [0., 50.], [1900., 50.]], [[0., 0.], [2., 0.], [0., 0.]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    assert not bufs[2].has(0)
    # NEGATIVE-2: airtime-starved (t_setup exceeds every contact duration) -> nothing moves
    c = _cfg(**base, master_seed=1)
    eng, bufs = _linear_engine([[0., 50.], [0., 50.], [100., 50.]], [[0., 0.], [2., 0.], [0., 0.]], c, t_setup=1000.0)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    assert not bufs[1].has(0) and not bufs[2].has(0)


def test_non_regression_static_fixpoint_is_component_reachability():
    c = _cfg(n=60, width=160.0, height=160.0, radius=20.0, mobility="static",
             speed_min=0.0, speed_max=0.0, master_seed=4)
    from soup_sim.percolation import placement
    pos = placement(c.n, c.width, c.height, c.rng())
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(c.n)]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
    for i in range(c.n):
        eng.inject(Blob(i, 0.0, 1e12, 1.0), i)
    eng.settle_static_fixpoint()
    delivered = set()
    for j in range(c.n):
        for bid in bufs[j].ids():
            if bid != j:
                delivered.add((bid, j) if bid < j else (j, bid))
    assert delivered == same_component_pairs(pos, c.radius, c.width, c.height, c.boundary)
