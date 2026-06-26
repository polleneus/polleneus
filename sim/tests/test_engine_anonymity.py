import numpy as np
from soup_sim.config import Config
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.budget import AirtimeBudget
from soup_sim.buffer import NodeBuffer
from soup_sim.blob import Blob

BIG = 10 ** 9


def cfg(**kw):
    d = dict(n=2, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0)
    d.update(kw)
    return Config(**d)


def _eng(c, pos, record=False):
    mob = Mobility("static", np.array(pos, float), np.zeros((len(pos), 2)), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(len(pos))]
    return Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None,
                  record_positions=record)


def test_position_log_recorded_when_on():
    c = cfg()
    eng = _eng(c, [[50., 50.], [55., 50.]], record=True)
    eng.inject(Blob(7, 0.0, 1e12, 1.0), 0)
    eng.run_until(3.0)
    eng.finalize()
    assert len(eng.position_log) >= 3
    t0, p0 = eng.position_log[0]
    assert p0.shape == (2, 2) and (0, 7) in eng.acquired   # acquire-time oracle present


def test_record_off_is_bit_identical():
    def run(rec):
        c = cfg(n=2)
        eng = _eng(c, [[50., 50.], [55., 50.]], record=rec)
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(5.0)
        eng.finalize()
        return eng.transmissions, list(eng.episodes)
    assert run(False) == run(True)    # recording is passive: outcome identical


def _line_eng(c, pos):
    mob = Mobility("static", np.array(pos, float), np.zeros((len(pos), 2)), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(len(pos))]
    return Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None), bufs


# --- PR-2 Task 1: Poisson mixing delay ---------------------------------------
def test_mixing_delays_forwarding():
    # A(0)-B(9)-C(18) static line; A holds blob 0. With HEAVY mixing (small lambda), B's forward-hold
    # delays C's receipt vs no-mixing (which is ~immediate via the per-step fixpoint).
    def run(lam):
        c = cfg(n=3, mixing_lambda=lam)
        eng, _ = _line_eng(c, [[0., 50.], [9., 50.], [18., 50.]])
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(50.0); eng.finalize()
        return eng.acquired.get((2, 0))
    t_nomix = run(0.0)
    t_mix = run(0.05)                                  # HEAVY mixing = SMALL lambda (Exp mean 20s)
    assert t_nomix is not None and t_nomix <= 1.0
    assert t_mix is None or t_mix > t_nomix


def test_mixing_off_draws_nothing_bit_identical():
    def run(lam):
        c = cfg(n=2, mixing_lambda=lam)
        eng, _ = _line_eng(c, [[50., 50.], [55., 50.]])
        eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
        eng.run_until(5.0); eng.finalize()
        return eng.transmissions, list(eng.episodes), eng._mix_rng
    tx0, ep0, rng0 = run(0.0)
    assert rng0 is None                                # lambda=0 -> no generator -> no draws
    tx1, ep1, _ = run(0.0)
    assert (tx0, ep0) == (tx1, ep1)


# --- PR-2 Task 2: receive-before-originate gate ------------------------------
def test_originate_gate_holds_origin_until_relays():
    # node0 holds its OWN blob 100; foreign ids 1,2 injected at node1/node2 (reach node0). With G=2,
    # node0's own blob must NOT reach a peer until node0 has relayed both foreign ids; G=0 -> immediate.
    def run(G):
        c = cfg(n=4, originate_gate_relays=G)
        # node3 at x=-9 is in range of node0 ONLY (dist to node1=18, node2=27 both >r=10), so node0 is
        # the SOLE path that can deliver the foreign ids 1,2 (and its own 100) to node3 -> forces node0 to relay.
        eng, bufs = _line_eng(c, [[0., 50.], [9., 50.], [18., 50.], [-9., 50.]])
        eng.inject(Blob(100, 0.0, 1e12, 1.0), 0, gated=True)   # node0's measured origination (gated)
        eng.inject(Blob(1, 0.0, 1e12, 1.0), 1)                 # un-gated background soup node0 relays
        eng.inject(Blob(2, 0.0, 1e12, 1.0), 2)
        eng.run_until(5.0); eng.finalize()
        return bufs[3].has(100), len(eng.relayed.get(0, ()))
    own_left_off, _ = run(0)
    own_left_gate, relayed = run(2)
    assert own_left_off is True                        # gate off: own blob leaves immediately
    assert relayed == 2                                # node0 did relay both foreign ids
    assert own_left_gate is True                       # after relaying 2, its own becomes forwardable

