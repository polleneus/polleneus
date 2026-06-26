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
