"""P2 PR-2 (spec v0.4): origination defenses — venue-wide cover floor scored by the WHICH-ROOT,
timing-aware adversary (+ the grown-candidate-null honesty control) + the probabilistic license.

The round-2 "mixed-graph" estimator was proven a denominator artifact (it scored the real blob's own
hearings and merely enlarged the candidate list; a non-emitting padding null reproduced the whole
"credit"). These tests pin that artifact so it can never return, and exercise the which-root metric.

Tiny/fast (the engine is super-linear in crowd size — every dummy is an extra propagating blob).
"""
import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import (
    _run_one_anonymity, _which_root_score_arm, _dummy_created,
    license_release_time, license_liveness, origination_defense_sweep, COVER_BLOB_BASE,
)
from soup_sim.adversary import place_receivers
from soup_sim.anonymity import origination_defense_gate, MIN_INTERSECTION_SIZE


def tiny(**kw):
    d = dict(n=16, width=44.0, height=44.0, radius=9.0, boundary="torus", mobility="rwp",
             speed_min=1.5, speed_max=1.5, dt=1.0, ttl=20.0, buffer_cap=120, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=4.0, measure_window=12.0,
             drain=4.0, n_messages=14, seen_margin=40.0, master_seed=5, adversary_range_mult=1.0,
             cover_timing_window=12.0)
    d.update(kw)
    return Config(**d)


def _which(cfg, f=0.7, delta_t=None, **kw):
    art = _run_one_anonymity(cfg)
    recv = place_receivers(cfg, f, "uniform", cfg.rng(4))
    dt = cfg.cover_timing_window if delta_t is None else delta_t
    res = _which_root_score_arm(art, recv, cfg, cfg.rng(6), dt, **kw)
    rank1 = float(np.mean([r["rank"] == 0 for r in res])) if res else 0.0
    K = float(np.mean([r["K"] for r in res])) if res else 0.0
    coinc = float(np.mean([r["n_coincident"] for r in res])) if res else 0.0
    return {"art": art, "res": res, "rank1": rank1, "K": K, "coincident": coinc}


# --- bit-identity OFF -------------------------------------------------------------------------------

def test_cover_off_is_bit_identical_and_dormant():
    a = _run_one_anonymity(tiny())
    b = _run_one_anonymity(tiny())
    assert a["acquired"] == b["acquired"] and a["delivery"] == b["delivery"]      # deterministic
    assert a["dummy_origins"] == {}                                               # no cover floor
    assert not any(bid >= COVER_BLOB_BASE for (_n, bid) in a["acquired"])         # no dummy ids leaked in
    on = _run_one_anonymity(tiny(cover_rate=0.4))
    assert len(on["dummy_origins"]) > 0 and on["acquired"] != a["acquired"]       # cover ON changes the run


# --- THE round-2 artifact, pinned: the grown-candidate-null reproduces a "drop" with ZERO dummies ---

def test_grown_candidate_null_reproduces_drop_with_zero_dummies():
    # Pad the cover-OFF candidate set with NON-emitting nodes (zero dummies). The which-root rank-1 falls
    # purely from denominator size — this IS the artifact the gate must subtract, so it must be REAL here.
    m1 = _which(tiny(cover_rate=0.0))                                             # natural K=1 -> rank1=1.0
    m_pad = _which(tiny(cover_rate=0.0), pad_to=12, pad_rng=tiny().rng(9))        # pad to 12 non-emitters
    assert m1["K"] == 1.0 and m1["rank1"] == 1.0                                  # lone emitter trivially caught
    assert m_pad["K"] > 8 and m_pad["rank1"] < m1["rank1"]                        # denominator alone lowers rank-1


def test_which_root_candidate_is_emitters_only_not_arbitrary_nodes():
    # Without padding, the candidate set is ONLY the true source + time-coincident DUMMY emitters — a
    # non-emitting node is never a which-root suspect (no observed root points to it).
    m = _which(tiny(cover_rate=0.4))
    assert m["coincident"] >= 1                                                   # real coincident emitters exist
    assert m["K"] in (m["coincident"], m["coincident"] + 1)                      # = src + distinct coincident nodes


# --- timing-aware mechanism: widening Δt admits more plausibly-real dummies -------------------------

def test_timing_window_admits_more_dummies_as_delta_widens():
    narrow = _which(tiny(cover_rate=0.5), delta_t=2.0)
    wide = _which(tiny(cover_rate=0.5), delta_t=12.0)
    assert wide["coincident"] >= narrow["coincident"]                            # wider ±Δt -> more plausibly-real
    assert wide["coincident"] > 0                                                # the mechanism is live


def test_dummy_namespace_and_emitters_are_real_nodes():
    on = _run_one_anonymity(tiny(cover_rate=0.5))
    assert all(bid >= COVER_BLOB_BASE for bid in on["dummy_origins"])             # disjoint namespace
    assert all(0 <= node < 16 for node in on["dummy_origins"].values())
    created = _dummy_created(on, tiny(cover_rate=0.5))
    assert all(c >= tiny().warmup - 1e-9 for c in created.values())              # emitted within the window


# --- the gate: credit ONLY the increment above the grown-candidate-null -----------------------------

def test_gate_null_verdict_when_cover_equals_padding():
    # cover ~= null (increment ~0) -> NULL, NOT credited (the round-2 artifact is subtracted out).
    v = origination_defense_gate(null_rank1=0.16, cover_rank1=0.19, mustlocalize_ok=True,
                                 credited_increment=-0.03, cover_off_rank1=1.0,
                                 timing_only_gain_survives=True, intersection_size=100)
    assert v["credited"] is False and "null" in v["label"].lower()


def test_gate_credits_only_a_material_increment_above_null():
    # a genuine increment above the null (cover beats padding by a material margin) IS credited.
    v = origination_defense_gate(null_rank1=0.40, cover_rank1=0.10, mustlocalize_ok=True,
                                 credited_increment=0.30, cover_off_rank1=1.0,
                                 timing_only_gain_survives=True, intersection_size=100)
    assert v["credited"] is True
    # ...but must-localize fail -> inconclusive; TTL=inf undo -> not credited; tiny intersection -> inconclusive.
    assert origination_defense_gate(0.40, 0.10, False, 0.30, 1.0, True, 100)["credited"] is False
    assert origination_defense_gate(0.40, 0.10, True, 0.30, 1.0, False, 100)["credited"] is False
    assert origination_defense_gate(0.40, 0.10, True, 0.30, 1.0, True, 5)["credited"] is False


# --- the probabilistic, time-bounded license: never deadlocks + cadence-invariant ------------------

def test_license_never_deadlocks_and_ceils_at_T():
    rng = np.random.default_rng(0)
    for _ in range(50):
        t = license_release_time(t0=3.0, T=10.0, floor=0.15, relay_event_times=[], rng=rng, novelty_gain=0.0)
        assert 3.0 <= t <= 13.0 + 1e-9
    assert license_release_time(0.0, 10.0, 0.0, [], np.random.default_rng(1)) == 10.0   # ceiling fires
    assert license_release_time(5.0, 0.0, 0.0, [], np.random.default_rng(1)) == 5.0     # off -> immediate


def test_license_liveness_deadlock_free_and_cadence_invariant():
    out = license_liveness(tiny(license_floor=0.2, license_max_latency_T=10.0), reps=30)
    assert out["deadlock_free"] is True and out["isolated_fires_by_T"] is True
    assert out["cadence_invariant"] is True and out["max_release"] <= out["T"] + 1e-9
    assert out["mean_release_connected"] <= out["mean_release_isolated"] + 1e-9


# --- the sweep: structure, determinism, guard -------------------------------------------------------

def test_origination_defense_sweep_structure_and_determinism():
    base = tiny()
    a = origination_defense_sweep(base, cover_rates=[0.0, 0.4], f=0.7, reps=1)
    b = origination_defense_sweep(base, cover_rates=[0.0, 0.4], f=0.7, reps=1)
    assert a["arms"] == b["arms"] and a["verdict"] == b["verdict"]               # deterministic
    assert "UPPER BOUND" in a["scope_tag"] and "credited" in a["verdict"]
    assert {"grown_candidate_null_rank1", "cover_off_rank1", "cover_on_rank1",
            "credited_increment", "fixed_denominator", "delta_t"} <= set(a)
    assert a["arms"][1]["cover_dummies_per_min"] > 0.0 and a["arms"][0]["cover_dummies_per_min"] == 0.0
    # the credited increment is exactly null - cover (credit ONLY above the grown-candidate-null)
    assert abs(a["credited_increment"] - (a["grown_candidate_null_rank1"] - a["cover_on_rank1"])) < 1e-9


def test_origination_defense_sweep_requires_cover_off_baseline():
    with pytest.raises(ValueError):
        origination_defense_sweep(tiny(), cover_rates=[0.4, 0.8], f=0.7, reps=1)


# --- powered measurement (slow): the HONEST verdict -------------------------------------------------

def measure_cfg():
    return Config(n=40, width=60.0, height=60.0, radius=9.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=25.0, buffer_cap=400, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=8.0, measure_window=24.0,
                  drain=8.0, n_messages=40, seen_margin=60.0, master_seed=11, adversary_range_mult=1.0,
                  cover_timing_window=8.0)


@pytest.mark.slow
def test_origination_cover_is_null_above_grown_candidate_null():
    # THE honest verdict at scale: the venue-wide cover floor credits ~0 ABOVE the grown-candidate-null —
    # real time+space-coincident dummy emitters are no more confusable than random padding (uniform floor).
    out = origination_defense_sweep(measure_cfg(), cover_rates=[0.0, 0.4], f=0.7, reps=2)
    assert out["intersection"] >= MIN_INTERSECTION_SIZE
    assert abs(out["credited_increment"]) < 0.15          # null reproduces ~the entire cover "drop"
    assert out["verdict"]["credited"] is False            # NULL — denominator, not position cover
