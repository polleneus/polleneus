"""P2 PR-2: origination defenses — venue-wide cover floor (mixed-graph estimator) + probabilistic license.

Tiny/fast tests (the engine is super-linear in crowd size — every dummy is an extra propagating blob,
so all configs here are bounded). The slow, powered measurement lives behind @pytest.mark.slow.
"""
import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import (
    _run_one_anonymity, _mixed_graph_score_arm, license_release_time, license_liveness,
    origination_defense_sweep, COVER_BLOB_BASE,
)
from soup_sim.adversary import place_receivers
from soup_sim.anonymity import origination_defense_gate, MIN_INTERSECTION_SIZE


def tiny(**kw):
    d = dict(n=14, width=40.0, height=40.0, radius=8.0, boundary="torus", mobility="rwp",
             speed_min=1.5, speed_max=1.5, dt=1.0, ttl=20.0, buffer_cap=80, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=4.0, measure_window=12.0,
             drain=4.0, n_messages=12, seen_margin=40.0, master_seed=5, adversary_range_mult=1.0)
    d.update(kw)
    return Config(**d)


def _mixed(cfg, f=0.7):
    art = _run_one_anonymity(cfg)
    recv = place_receivers(cfg, f, "uniform", cfg.rng(4))
    res, n_emit, undet, total = _mixed_graph_score_arm(art, recv, cfg, cfg.rng(6))
    rank1 = float(np.mean([r["rank"] == 0 for r in res])) if res else 0.0
    rand1 = float(np.mean([r["rand_rank"] == 0 for r in res])) if res else 0.0
    return {"art": art, "res": res, "n_emit": n_emit, "rank1": rank1, "rand1": rand1, "total": total}


# --- bit-identity OFF -------------------------------------------------------------------------------

def test_cover_off_is_bit_identical_and_dormant():
    # cover_rate=0 + license off -> NO dummy roots injected, NO new RNG, deterministic, no 20M ids.
    a = _run_one_anonymity(tiny())
    b = _run_one_anonymity(tiny())
    assert a["acquired"] == b["acquired"] and a["delivery"] == b["delivery"]      # deterministic
    assert a["dummy_origins"] == {}                                               # no cover floor
    assert not any(bid >= COVER_BLOB_BASE for (_n, bid) in a["acquired"])         # no dummy ids leaked in
    # turning the cover floor ON actually changes the run (feature wired, not a silent no-op)
    on = _run_one_anonymity(tiny(cover_rate=0.3))
    assert len(on["dummy_origins"]) > 0 and on["acquired"] != a["acquired"]


def test_cover_dummies_are_distinct_emitter_nodes_namespace():
    on = _run_one_anonymity(tiny(cover_rate=0.5))
    assert all(bid >= COVER_BLOB_BASE for bid in on["dummy_origins"])             # disjoint namespace
    assert all(0 <= node < 14 for node in on["dummy_origins"].values())           # emitted by real nodes


# --- the mixed-graph estimator: must-localize cover-OFF, and the metric MOVES with cover -------------

def test_mixed_graph_localizes_cover_off_nonvacuous():
    # cover-OFF the mixed-graph estimator must localize the true node BETTER than a random guess among
    # the distinct emitter nodes, over a NON-VACUOUS candidate set (>1 distinct emitter) — else the
    # whole cover comparison is vacuous (the round-2 must-localize requirement).
    m = _mixed(tiny())
    assert m["n_emit"] > 1                                  # candidate set is real, not a single node
    assert m["rank1"] > m["rand1"]                          # localizes better than chance among nodes
    assert m["rank1"] >= 2.0 / m["n_emit"]                  # a real signal, not the 1/|E| floor


def test_metric_moves_with_cover_not_structurally_blind():
    # THE round-2 fix, pinned: the true-node rank-1 must MOVE as cover_rate rises (the estimator is NOT
    # structurally blind to the cover floor). Cover adds DISTINCT emitter nodes and the rank-1 drops.
    off = _mixed(tiny(cover_rate=0.0))
    on = _mixed(tiny(cover_rate=0.8))
    assert on["n_emit"] > off["n_emit"]                     # cover added distinct candidate NODES
    assert on["rank1"] < off["rank1"]                       # ...and the true-node rank-1 dropped (moved)


# --- distinct-node co-location control: the v1 1/K own-root trap cannot return -----------------------

def test_candidate_set_is_distinct_nodes_never_root_count():
    # the candidate set / random floor is over DISTINCT EMITTER NODES (<= n), never the number of ROOTS
    # (blobs). With a heavy cover floor there are FAR more roots than nodes; distinct_emitters must stay
    # bounded by n, and no message's rank may exceed the distinct-emitter count.
    c = tiny(cover_rate=1.0)
    m = _mixed(c)
    assert m["n_emit"] <= c.n                               # distinct NODES, not roots
    assert len(m["art"]["dummy_origins"]) > m["n_emit"]     # far more roots than distinct nodes
    assert all(r["rank"] < m["n_emit"] for r in m["res"])   # rank is AMONG the distinct emitter nodes


def test_distinct_node_gate_rejects_colocated_own_root_tie():
    # the gate's NEW co-location control: a rank-1 "drop" with NO growth in distinct candidate NODES is
    # an own-root/co-located tie artifact (the v1 1/K trap) and must be REJECTED even though it would
    # survive the TTL=inf control and look material.
    v = origination_defense_gate(baseline_rank1=0.30, defended_rank1=0.05, mustlocalize_ok=True,
                                 distinct_emitters_cover_on=8.0, distinct_emitters_cover_off=8.0,
                                 timing_only_gain_survives=True, intersection_size=100)
    assert v["credited"] is False and "artifact" in v["label"].lower()
    # ...but the SAME drop WITH genuine distinct-node growth (cover from OTHER nodes) is credited.
    v2 = origination_defense_gate(baseline_rank1=0.30, defended_rank1=0.05, mustlocalize_ok=True,
                                  distinct_emitters_cover_on=20.0, distinct_emitters_cover_off=8.0,
                                  timing_only_gain_survives=True, intersection_size=100)
    assert v2["credited"] is True


def test_origination_gate_retains_slice3_controls():
    # must-localize fail -> inconclusive; message-dropping (dies at TTL=inf) -> not credited; tiny
    # intersection -> inconclusive; no material drop -> not credited.
    assert origination_defense_gate(0.30, 0.05, False, 20.0, 8.0, True, 100)["credited"] is False
    g = origination_defense_gate(0.30, 0.05, True, 20.0, 8.0, False, 100)
    assert g["credited"] is False and "ttl=inf" in g["label"].lower()
    assert origination_defense_gate(0.30, 0.05, True, 20.0, 8.0, True, 5)["credited"] is False  # < MIN_INTERSECTION_SIZE
    assert origination_defense_gate(0.30, 0.28, True, 20.0, 8.0, True, 100)["credited"] is False  # no material drop


# --- the probabilistic, time-bounded license: never deadlocks + cadence-invariant -------------------

def test_license_never_deadlocks_and_ceils_at_T():
    rng = np.random.default_rng(0)
    # floor>0, NO relays (fully isolated/jammed) -> still fires, always within [t0, t0+T]
    for _ in range(50):
        t = license_release_time(t0=3.0, T=10.0, floor=0.15, relay_event_times=[],
                                 rng=rng, novelty_gain=0.0)
        assert 3.0 <= t <= 13.0 + 1e-9
    # floor=0 but T>0 -> the hard ceiling still fires by t0+T (deadlock-free)
    assert license_release_time(0.0, 10.0, 0.0, [], np.random.default_rng(1)) == 10.0
    # off (floor=0, T=0) -> immediate, no license
    assert license_release_time(5.0, 0.0, 0.0, [], np.random.default_rng(1)) == 5.0


def test_license_liveness_deadlock_free_and_cadence_invariant():
    out = license_liveness(tiny(license_floor=0.2, license_max_latency_T=10.0), reps=30)
    assert out["deadlock_free"] is True                     # every release lands by T
    assert out["isolated_fires_by_T"] is True               # the jammed target is never silent
    assert out["cadence_invariant"] is True                 # isolation oracle closed
    assert out["max_release"] <= out["T"] + 1e-9
    # novelty raises p -> the CONNECTED node fires sooner, but BOTH are bounded (liveness, not leak)
    assert out["mean_release_connected"] <= out["mean_release_isolated"] + 1e-9


# --- the sweep: structure, determinism, guard -------------------------------------------------------

def test_origination_defense_sweep_structure_and_determinism():
    base = tiny()
    a = origination_defense_sweep(base, cover_rates=[0.0, 0.5], f=0.7, reps=1)
    b = origination_defense_sweep(base, cover_rates=[0.0, 0.5], f=0.7, reps=1)
    assert a["arms"] == b["arms"]                           # deterministic
    assert "UPPER BOUND" in a["scope_tag"] and "credited" in a["verdict"]
    assert [arm["cover_rate"] for arm in a["arms"]] == [0.0, 0.5]
    for arm in a["arms"]:
        assert {"cover_rate", "rank1", "distinct_emitters", "cover_dummies_per_min",
                "median_err_radii", "delivery"} <= set(arm)
    # cover-ON adds distinct emitter nodes + airtime cost vs the cover-OFF baseline
    assert a["arms"][1]["distinct_emitters"] >= a["arms"][0]["distinct_emitters"]
    assert a["arms"][1]["cover_dummies_per_min"] > 0.0 and a["arms"][0]["cover_dummies_per_min"] == 0.0
    assert "mustlocalize" in a and "ttl_inf_rank1" in a


def test_origination_defense_sweep_requires_cover_off_baseline():
    with pytest.raises(ValueError):
        origination_defense_sweep(tiny(), cover_rates=[0.5, 0.8], f=0.7, reps=1)


# --- powered measurement (slow) ---------------------------------------------------------------------

def measure_cfg():
    return Config(n=45, width=70.0, height=70.0, radius=9.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=30.0, buffer_cap=400, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=8.0, measure_window=30.0,
                  drain=10.0, n_messages=45, seen_margin=60.0, master_seed=11, adversary_range_mult=1.0)


@pytest.mark.slow
def test_origination_defense_sweep_powered_verdict():
    out = origination_defense_sweep(measure_cfg(), cover_rates=[0.0, 0.3, 0.8], f=0.7, reps=2)
    # the mixed-graph estimator localizes cover-OFF (must-localize passes) so the verdict is a REAL
    # credit/null decision, not the "failed must-localize" early return.
    assert out["mustlocalize"]["ok"] is True
    assert out["intersection"] >= MIN_INTERSECTION_SIZE
    # the metric MOVES with cover at scale, and the verdict carries the distinct-node-controlled reason.
    assert out["arms"][-1]["distinct_emitters"] > out["arms"][0]["distinct_emitters"]
    assert "credited" in out["verdict"]
