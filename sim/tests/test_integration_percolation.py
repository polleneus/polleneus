"""THE gate. Validates the contact graph + engine against percolation ground truth:
  (1) Oracle KAT: in the static unbounded regime, delivered (src,dst) pairs from the
      engine's multi-hop fixpoint EXACTLY equal union-find same-component pairs.
  (2) Threshold: over a Poisson torus ensemble, the susceptibility peaks near the
      continuum-percolation critical mean degree d_c ~= 4.51, and the giant component
      emerges (subcritical small, supercritical large). NOT delivery=0.5 (~d 6-7).
"""
import numpy as np
from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer
from soup_sim.budget import AirtimeBudget
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.percolation import (
    susceptibility, largest_component_fraction, same_component_pairs, placement,
)

BIG = 10 ** 9


def cfg(**kw):
    d = dict(n=150, width=200.0, height=200.0, radius=20.0, boundary="torus",
             mobility="static", speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e18,
             buffer_cap=BIG, throughput_ideal=1e18, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e18, master_seed=11)
    d.update(kw)
    return Config(**d)


def test_oracle_kat_delivered_equals_same_component_pairs():
    c = cfg()
    pos = placement(c.n, c.width, c.height, c.rng())
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, 1e18, c.rng(i)) for i in range(c.n)]
    budget = AirtimeBudget(1e18, 0.0, 0.0, 0.0, 1.0)
    eng = Engine(c, mob, bufs, budget, c.rng(9), on_deliver=lambda n, b, t: None)
    for i in range(c.n):
        eng.inject(Blob(i, 0.0, 1e18, 1.0), i)
    eng.settle_static_fixpoint()

    delivered = set()
    for j in range(c.n):
        for bid in bufs[j].ids():
            if bid != j:
                delivered.add((bid, j) if bid < j else (j, bid))
    oracle = same_component_pairs(pos, c.radius, c.width, c.height, c.boundary)
    assert delivered == oracle


def test_susceptibility_peak_near_threshold_and_giant_emerges():
    w = h = 380.0
    r = 10.0
    reps = 5
    degrees = list(np.linspace(2.0, 8.0, 13))
    lam_to_n = w * h / (np.pi * r * r)
    chi_means, s_means = [], []
    for di, d in enumerate(degrees):
        chis, ss = [], []
        for rep in range(reps):
            rng = np.random.default_rng(np.random.SeedSequence([777, di, rep]))
            n = int(rng.poisson(d * lam_to_n))
            pos = placement(n, w, h, rng)
            chis.append(susceptibility(pos, r, w, h, "torus"))
            ss.append(largest_component_fraction(pos, r, w, h, "torus"))
        chi_means.append(float(np.mean(chis)))
        s_means.append(float(np.mean(ss)))

    peak_degree = degrees[int(np.argmax(chi_means))]
    assert 4.0 <= peak_degree <= 5.2, (peak_degree, chi_means)   # validates d_c ~= 4.51
    assert s_means[0] < 0.15, s_means          # d=2 subcritical: no giant
    assert s_means[-1] > 0.6, s_means          # d=8 supercritical: giant dominates
