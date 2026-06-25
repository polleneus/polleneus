import numpy as np
from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer
from soup_sim.budget import AirtimeBudget
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine

BIG = 10 ** 9


def cfg(**kw):
    d = dict(n=2, width=200.0, height=200.0, radius=10.0, boundary="walls",
             mobility="static", speed_min=1.0, speed_max=1.0, dt=1.0, ttl=1e12,
             buffer_cap=BIG, throughput_ideal=1e12, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1e12,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0)
    d.update(kw)
    return Config(**d)


def make_engine(positions, c, mode="static", velocities=None, rec=None):
    pos = np.array(positions, float)
    vel = np.zeros_like(pos) if velocities is None else np.array(velocities, float)
    mob = Mobility(mode, pos, vel, c.width, c.height, c.speed_min, c.speed_max)
    bufs = [NodeBuffer(c.buffer_cap, c.seen_margin, c.rng(i)) for i in range(len(pos))]
    budget = AirtimeBudget(c.throughput_ideal, c.alpha, c.t_setup, c.p_fail, c.blob_size)
    sink = rec if rec is not None else []
    return Engine(c, mob, bufs, budget, c.rng(999),
                  on_deliver=lambda n, b, t: sink.append((n, b.id)))


def test_static_fixpoint_two_nodes_in_range():
    c = cfg(n=2)
    eng = make_engine([[50, 50], [55, 50]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.settle_static_fixpoint()
    assert eng.buffers[1].has(0)


def test_static_fixpoint_abc_multihop_fails_one_hop():
    c = cfg(n=3)
    # A(0)-B(9)-C(18): A-B and B-C in range (<=10), A-C (18) NOT -> only multi-hop reaches C
    eng = make_engine([[0, 50], [9, 50], [18, 50]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.settle_static_fixpoint()
    assert eng.buffers[2].has(0)


def test_static_fixpoint_disconnected_never():
    c = cfg(n=2)
    eng = make_engine([[0, 50], [100, 50]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.settle_static_fixpoint()
    assert not eng.buffers[1].has(0)


def test_dynamic_two_in_range_delivered_at_run_end():
    c = cfg(n=2, dt=1.0)
    eng = make_engine([[50, 50], [55, 50]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(5.0)
    eng.finalize()
    assert eng.buffers[1].has(0)


def test_permanently_out_never_delivers():
    c = cfg(n=2, dt=1.0)
    eng = make_engine([[0, 50], [100, 50]], c)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(5.0)
    assert not eng.buffers[1].has(0)


def test_per_episode_shared_budget_is_one_pool_not_per_direction():
    c = cfg(n=2, dt=0.1, throughput_ideal=1.5, blob_size=1.0, t_setup=0.0, alpha=0.0)
    eng = make_engine([[50, 50], [55, 50]], c)
    eng.inject(Blob(10, 0.0, 1e12, 1.0), 0)
    eng.inject(Blob(20, 0.0, 1e12, 1.0), 1)
    eng.run_until(1.0)  # one episode, duration ~1.0 -> k=1 shared
    eng.finalize()
    total = len(eng.buffers[0].ids()) + len(eng.buffers[1].ids())
    assert total == 3  # exactly one blob moved (per-direction would give 4)


def test_determinism_same_seed_identical_transmissions():
    def run():
        c = cfg(n=2, dt=1.0)
        eng = make_engine([[50, 50], [55, 50]], c)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(5.0)
        eng.finalize()
        return eng.transmissions
    assert run() == run()


def test_dt_convergence_linear_pass():
    def run(dt):
        c = cfg(n=2, dt=dt, radius=10.0, throughput_ideal=1e9, blob_size=1.0)
        rec = []
        eng = make_engine([[0.0, 50.0], [50.0, 50.0]], c, mode="linear",
                          velocities=[[1.0, 0.0], [0.0, 0.0]], rec=rec)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(120.0)
        eng.finalize()
        return eng.mean_contact_duration(), eng.buffers[1].has(0)
    d1, ok1 = run(1.0)
    d2, ok2 = run(0.5)
    assert ok1 and ok2
    assert abs(d1 - 20.0) < 0.6 and abs(d2 - 20.0) < 0.6  # analytic duration ~20
    assert abs(d1 - d2) < 0.2                              # dt-independent


def test_cross_slicing_episode_equality():
    # A physically continuous contact must be ONE episode regardless of run_until slicing
    # (t_setup charged once) — run_until() no longer finalizes; finalize() is explicit.
    def durations(slices):
        c = cfg(n=2, dt=1.0, radius=10.0)
        eng = make_engine([[50, 50], [55, 50]], c)  # static -> always in range
        for s in slices:
            eng.run_until(s)
        eng.finalize()
        return eng.durations
    assert durations([10.0]) == durations([5.0, 10.0]) == [10.0]


def test_finite_ttl_delivered_when_in_contact_during_validity():
    # nodes in range from t=0; blob valid [0,5]; long run -> MUST deliver during the valid
    # window (Codex P1: exchange happens DURING the contact, not at the later expiry time).
    c = cfg(n=2, dt=1.0, radius=10.0, ttl=5.0)
    eng = make_engine([[50, 50], [55, 50]], c)
    eng.inject(Blob(0, created_at=0.0, ttl=5.0, size=1.0), 0)
    eng.run_until(20.0)
    eng.finalize()
    assert eng.buffers[1].has(0)


def test_delivery_time_never_before_created():
    c = cfg(n=2, dt=1.0, radius=10.0, ttl=1e12)
    pos = np.array([[50.0, 50.0], [55.0, 50.0]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(c.buffer_cap, c.seen_margin, c.rng(i)) for i in range(2)]
    times = []
    eng = Engine(c, mob, bufs, AirtimeBudget(c.throughput_ideal, 0, 0, 0, 1.0), c.rng(9),
                 on_deliver=lambda n, b, t: times.append((t, b.created_at)))
    eng.inject(Blob(0, created_at=3.0, ttl=1e12, size=1.0), 0)
    eng.run_until(10.0)
    eng.finalize()
    assert times and all(t >= cr - 1e-9 for (t, cr) in times)  # delivered_at >= created_at by construction


def test_overlap_pair_order_invariance():
    def run(order):
        c = cfg(n=3, mobility="static", speed_min=0.0, speed_max=0.0, radius=10.0, dt=1.0)
        pos = np.array([[0.0, 50.0], [9.0, 50.0], [18.0, 50.0]])
        mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
        bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(3)]
        rec = []
        eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1),
                     on_deliver=lambda n, b, t: rec.append((n, b.id, t)), _pair_order=order)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(3.0)
        eng.finalize()
        return sorted(rec)
    assert run(None) == run("reversed")  # canonical (exit,i,j) settle order -> input order irrelevant
    assert (2, 0, 0.0) in run(None)      # multi-hop A->B->C reached within the canonical settle


def test_finite_ttl_not_delivered_when_contact_starts_after_expiry():
    # node1 only enters range ~t=45, long after the blob's ttl=5 -> not delivered
    c = cfg(n=2, dt=1.0, radius=10.0, ttl=5.0)
    eng = make_engine([[0.0, 50.0], [100.0, 50.0]], c, mode="linear",
                      velocities=[[0.0, 0.0], [-2.0, 0.0]])
    eng.inject(Blob(0, created_at=0.0, ttl=5.0, size=1.0), 0)
    eng.run_until(60.0)
    eng.finalize()
    assert not eng.buffers[1].has(0)
