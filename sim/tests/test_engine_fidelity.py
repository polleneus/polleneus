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


def _linear_engine(positions, velocities, c, t_setup=0.0):
    pos = np.array(positions, float)
    mob = Mobility("linear", pos, np.array(velocities, float), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(len(pos))]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0.0, t_setup, 0.0, 1.0), c.rng(1),
                 on_deliver=lambda *_: None)
    return eng, bufs


# --- analytic forms + contact-timing sanity (runs the engine) ---------------
def test_analytic_forms():
    assert abs(expected_relative_speed(3.0) - (4.0 / np.pi) * 3.0) < 1e-9
    assert abs(expected_contact_duration(8.0, 3.0) - (np.pi * 8.0 / (2 * 3.0))) < 1e-9
    assert abs(analytic_meeting_rate_per_node(8.0, 3.0, 300, 40000.0) - (2 * 8 * 3 * 299 / 40000.0)) < 1e-9


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


# --- INDEPENDENT interval oracle: hand-known, both directions ---------------
def test_temporal_reachable_interval_oracle():
    # contact (i, j, entry, exit). A-B then B-C (later) -> C reachable.
    assert temporal_reachable([(0, 1, 0.0, 1.0), (1, 2, 1.5, 2.0)], 0, 3) == {0, 1, 2}
    # B-C happens (and ENDS) before B is infected by A -> C NOT reachable.
    assert temporal_reachable([(1, 2, 0.0, 0.5), (0, 1, 1.0, 2.0)], 0, 3) == {0, 1}


# --- KEY discriminators (deterministic, dt-robust): nested overlap + time order ---
def test_nested_overlap_delivers_node2():
    # node0(blob)-node1 in range the WHOLE run; node2 grazes only node1 mid-run; node0-node2 never.
    # node1 physically holds the blob from t=0, so node2 IS reachable. The old lazy-exit-settle
    # model missed it ({0,1}); per-step propagation must deliver node2.
    c = _cfg(n=3, mobility="static", speed_min=0.0, speed_max=0.0, radius=10.0, dt=1.0,
             width=2000.0, height=2000.0, boundary="walls")
    eng, bufs = _linear_engine([[0., 0.], [0., 9.], [-20., 15.]],
                               [[0., 0.], [0., 0.], [2., 0.]], c)   # node2 sweeps x at y=15
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(40.0); eng.finalize()
    assert bufs[1].has(0) and bufs[2].has(0)                         # node2 reached via node1
    assert temporal_reachable(eng.episodes, 0, 3) == {0, 1, 2}       # independent oracle agrees


def test_time_order_is_respected_not_flooded():
    # node1 meets node2 FIRST (early), then meets node0(blob) LATE. A time-respecting engine
    # must NOT deliver to node2 (node1 had nothing during the early contact). A flood-ignoring
    # engine would wrongly deliver node2 (the union graph is connected).
    c = _cfg(n=3, mobility="static", speed_min=0.0, speed_max=0.0, radius=10.0, dt=1.0,
             width=2000.0, height=2000.0, boundary="walls")
    eng, bufs = _linear_engine([[0., 0.], [0., 95.], [0., 100.]],
                               [[0., 0.], [0., -2.], [0., 0.]], c)   # node1 descends past node2 then to node0
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(60.0); eng.finalize()
    assert bufs[1].has(0) and not bufs[2].has(0)                     # node1 yes (late), node2 no (time order)
    oracle = temporal_reachable(eng.episodes, 0, 3)
    assert oracle == {0, 1}                                          # oracle agrees: 2 unreachable
    assert any({1, 2} == {i, j} for (i, j, _e, _x) in eng.episodes)  # but node1-node2 DID contact (component connects 2)


def test_single_step_multihop_backward_chain_delivers():
    # node0 and node2 each transit static node1's range during ONE step; node0-node2 never meet.
    # Source = node2 (HIGH index): the chain node2->node1->node0 must complete within the single
    # step. A single canonical-(i,j)-order pass processes (0,1) before node1 is infected and
    # loses node0; the per-step FIXPOINT must deliver it. dt == run so it is exactly one step.
    c = _cfg(n=3, mobility="static", speed_min=0.0, speed_max=0.0, radius=10.0, dt=20.0,
             width=2000.0, height=2000.0, boundary="walls")
    eng, bufs = _linear_engine([[-6., 8.], [0., 0.], [-6., -8.]],
                               [[0.6, 0.], [0., 0.], [0.6, 0.]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 2)
    eng.run_until(20.0); eng.finalize()
    assert len(eng.episodes) == 2                                    # only (0,1) and (1,2) ever in range
    assert bufs[1].has(0) and bufs[0].has(0)                         # backward chain completes in one step
    assert temporal_reachable(eng.episodes, 2, 3) == {0, 1, 2}


def test_causality_future_blob_not_delivered():
    # node1 grazes node0 only early ([0,~3.3]) then leaves forever. Blob B is created at t=1000,
    # long after that contact ended -> the causality guard must NOT let it ride the earlier
    # contact. Blob A (created 0) must deliver. This load-bears the acquired<=exit guard.
    c = _cfg(n=2, mobility="static", speed_min=0.0, speed_max=0.0, radius=10.0, dt=1.0,
             width=2000.0, height=2000.0, boundary="walls")
    eng, bufs = _linear_engine([[0., 0.], [0., 0.]], [[0., 0.], [0., 3.]], c)
    eng.inject(Blob(1, 0.0, 1e12, 1.0), 0)        # A: exists from t=0
    eng.inject(Blob(2, 1000.0, 1e12, 1.0), 0)     # B: created after the only contact ends
    eng.run_until(100.0); eng.finalize()
    assert bufs[1].has(1) and not bufs[1].has(2)


# --- broad consistency on RWP -----------------------------------------------
def test_engine_matches_temporal_reachability_rwp_saturated():
    # Dense regime (oracle == N): retains power against UNDER-delivery only.
    for s in range(5):
        c = _cfg(master_seed=s)
        eng, bufs = _spread_engine(c)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(80.0); eng.finalize()
        delivered = {k for k in range(c.n) if bufs[k].has(0)}
        oracle = temporal_reachable(eng.episodes, 0, c.n)
        assert delivered == oracle == set(range(c.n))


def test_engine_matches_temporal_reachability_rwp_partial():
    # Sparse regime (oracle STRICTLY < N): a flood-without-time engine would over-deliver here,
    # so this adds discriminating power against OVER-delivery that the saturated test lacks.
    saw_partial = False
    for s in range(5):
        c = _cfg(radius=7.0, master_seed=s)
        eng, bufs = _spread_engine(c)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(15.0); eng.finalize()
        delivered = {k for k in range(c.n) if bufs[k].has(0)}
        oracle = temporal_reachable(eng.episodes, 0, c.n)
        assert delivered == oracle
        if 2 < len(oracle) < c.n:
            saw_partial = True
    assert saw_partial  # confirm the regime is genuinely partial (else the test has no power)


def test_one_hop_mutant_fails_the_gate():
    for s in range(5):
        c = _cfg(master_seed=s)
        eng, bufs = _spread_engine(c, one_hop=True)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(80.0); eng.finalize()
        delivered = {k for k in range(c.n) if bufs[k].has(0)}
        oracle = temporal_reachable(eng.episodes, 0, c.n)
        assert delivered < oracle and len(delivered) < len(oracle)


# --- courier multi-hop both arms + non-regression ---------------------------
def test_multihop_courier_positive_and_negatives():
    base = dict(n=3, width=2000.0, height=200.0, radius=10.0, boundary="walls", dt=1.0, ttl=1e12,
                mobility="static", speed_min=0.0, speed_max=0.0)
    c = _cfg(**base, master_seed=1)
    eng, bufs = _linear_engine([[0., 50.], [0., 50.], [100., 50.]], [[0., 0.], [2., 0.], [0., 0.]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    assert bufs[2].has(0)                                            # courier bridges
    c = _cfg(**base, master_seed=1)
    eng, bufs = _linear_engine([[0., 50.], [0., 50.], [1900., 50.]], [[0., 0.], [2., 0.], [0., 0.]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    assert not bufs[2].has(0)                                        # no bridge
    c = _cfg(**base, master_seed=1)
    eng, bufs = _linear_engine([[0., 50.], [0., 50.], [100., 50.]], [[0., 0.], [2., 0.], [0., 0.]], c, t_setup=1000.0)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(80.0); eng.finalize()
    assert not bufs[1].has(0) and not bufs[2].has(0)                 # airtime-starved


def test_non_regression_static_fixpoint_is_component_reachability():
    from soup_sim.percolation import placement
    c = _cfg(n=60, width=160.0, height=160.0, radius=20.0, mobility="static",
             speed_min=0.0, speed_max=0.0, master_seed=4)
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
