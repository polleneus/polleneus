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
    total = len(eng.buffers[0].ids()) + len(eng.buffers[1].ids())
    assert total == 3  # exactly one blob moved (per-direction would give 4)


def test_determinism_same_seed_identical_transmissions():
    def run():
        c = cfg(n=2, dt=1.0)
        eng = make_engine([[50, 50], [55, 50]], c)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(5.0)
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
        return eng.mean_contact_duration(), eng.buffers[1].has(0)
    d1, ok1 = run(1.0)
    d2, ok2 = run(0.5)
    assert ok1 and ok2
    assert abs(d1 - 20.0) < 0.6 and abs(d2 - 20.0) < 0.6  # analytic duration ~20
    assert abs(d1 - d2) < 0.2                              # dt-independent
