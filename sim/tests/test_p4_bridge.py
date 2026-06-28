"""P4 PR-2 — the bridge (cold-start floor-lift) + low-N activation.

In the clustered ISLAND regime (cluster_leak=0) ordinary nodes never leave their gathering, so cross-island
delivery is a hard floor. A BRIDGE node (personal leak=1.0) can ferry across — but only if it actually
VISITS the islands: a UNIFORM-wander bridge mostly sits in empty space (poor ferry); a TOUR bridge heads to
gatherings (the §14 'organizer gathering kit') and lifts the floor. Honest finding: effective ferrying is a
PURPOSEFUL-routing (operational) property, not an emergent protocol guarantee. All UPPER BOUNDS; the ceiling
is ergodic at unbounded budget (this is a fixed-budget floor-lift). See spec 2026-06-28-p4-bridge-lowN."""
import numpy as np
import pytest

from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer
from soup_sim.budget import AirtimeBudget
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.scenario import bridge_lift_sweep, run_one

BIG = 10 ** 9


def island_cfg(**kw):
    """K=4 GENUINELY-disconnected gatherings: tight clusters (sigma=4) far apart in a large arena (W=500)
    so giant-component ~ 1/K (verified per-run), not overlapping. leak=0 ⇒ true islands. Small N ⇒ cheap."""
    d = dict(n=40, width=500.0, height=500.0, radius=12.0, boundary="torus", mobility="clustered",
             n_clusters=4, cluster_sigma=4.0, cluster_leak=0.0, speed_min=4.0, speed_max=4.0,
             dt=0.5, ttl=250.0, buffer_cap=10**6, throughput_ideal=1e9, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=10.0, measure_window=250.0, drain=0.0,
             n_messages=12, seen_margin=10.0, master_seed=7)
    d.update(kw)
    return Config(**d)


def _arm(res, name):
    return {r["n_bridge"]: r["delivery_mean"] for r in res["arms"][name]}


def test_bridge_floor_and_tour_lift_and_uniform_is_weak():
    """One sweep, four honest claims (robust 8/8 over seed-groups in the scoping probe):
    (0) the islands are GENUINELY disconnected — giant-component ~ 1/K (not overlap-permeable), so the floor
        is a real cold-start floor (this is the premise the prose claims, now actually tested);
    (1) a TOUR bridge lifts the floor steeply; (2) a UNIFORM-wander bridge is a near-useless ferry in a
        genuinely-separated sparse arena (it mostly sits in empty space) — purposeful routing is what matters."""
    res = bridge_lift_sweep(island_cfg(), n_bridge_values=[0, 8], reps=4)
    floor = res["floor"]
    tour = _arm(res, "tour")
    uniform = _arm(res, "uniform")
    # (0) PREMISE: genuine islands — giant-component close to 1/K, not an overlap-inflated pseudo-floor.
    assert res["giant_frac"] < 1.6 * res["one_over_k"], \
        f"clusters overlap (not real islands): giant={res['giant_frac']:.3f} vs 1/K={res['one_over_k']:.3f}"
    assert tour[8] > floor + 0.3, f"a tour bridge must lift the floor steeply: floor={floor} tour8={tour[8]}"
    assert uniform[8] < floor + 0.25, \
        f"a uniform-wander bridge must be a weak ferry in true islands: floor={floor} uniform8={uniform[8]}"
    assert tour[8] > uniform[8] + 0.3, \
        f"purposeful (tour) must beat naive (uniform-wander) decisively: tour8={tour[8]} uniform8={uniform[8]}"


def test_bridge_floor_shared_across_arms():
    """At n_bridge=0 no node ever wanders (leak=0), so the routing flag is a no-op ⇒ the two arms report the
    identical floor (the same venue, no ferrying)."""
    res = bridge_lift_sweep(island_cfg(), n_bridge_values=[0], reps=3)
    assert res["arms"]["tour"][0]["delivery_mean"] == res["arms"]["uniform"][0]["delivery_mean"]


def test_bridge_default_inert_no_wander_means_tour_flag_is_noop():
    """Default-inert: with leak=0 and n_bridge=0 no node wanders, so bridge_tour cannot change anything —
    the FULL run_one result is identical with the flag on vs off (the new branch is never taken)."""
    base = island_cfg()
    from dataclasses import replace
    r_off = run_one(replace(base, bridge_tour=False))
    r_on = run_one(replace(base, bridge_tour=True))
    for k in r_off:
        if k == "manifest":
            continue                      # manifest differs by the flag value itself
        assert r_off[k] == r_on[k], f"bridge_tour flipped {k} despite no wander"


def test_config_validates_n_bridge_range():
    island_cfg(n_bridge=0).validate()
    island_cfg(n_bridge=40).validate()
    with pytest.raises(ValueError):
        island_cfg(n_bridge=-1).validate()
    with pytest.raises(ValueError):
        island_cfg(n_bridge=41).validate()       # > n


# ---- low-N activation: pair-to-activate (N=2 in range) vs standby (isolated, no false delivery) ----------
def _pair_reaches(gap):
    """Two STATIC nodes `gap` apart; inject at node 0; does node 1 ever hold it? Deterministic."""
    c = Config(n=2, width=400.0, height=400.0, radius=12.0, boundary="walls", mobility="static",
               speed_min=1.0, speed_max=1.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=1e12,
               alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1e12,
               drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0)
    pos = np.array([[100.0, 100.0], [100.0 + gap, 100.0]])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, c.speed_min, c.speed_max)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(2)]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(20.0)
    return bufs[1].has(0)


def test_pair_to_activate_and_standby():
    assert _pair_reaches(8.0) is True       # within radius 12 -> the pair activates, blob reaches node 1
    assert _pair_reaches(80.0) is False     # beyond radius -> isolated node, no false "delivery" (standby)


def test_bridge_sweep_deterministic():
    a = bridge_lift_sweep(island_cfg(), n_bridge_values=[0, 4], reps=2)
    b = bridge_lift_sweep(island_cfg(), n_bridge_values=[0, 4], reps=2)
    assert a["arms"] == b["arms"]
