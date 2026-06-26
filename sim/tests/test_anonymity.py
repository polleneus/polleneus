import numpy as np
from soup_sim.config import Config
from soup_sim.anonymity import (
    SCOPE_TAG, localization_error, rank_of, anonymity_set_size, quantiles,
    mustlocalize_gate, exposure_gate,
)


def cfg(**kw):
    d = dict(n=2, width=100.0, height=100.0, radius=10.0, boundary="torus", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e9, buffer_cap=10 ** 9, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e9, master_seed=0)
    d.update(kw)
    return Config(**d)


def test_localization_error_torus_wraps():
    assert abs(localization_error((1., 1.), (99., 99.), cfg()) - np.hypot(2., 2.)) < 1e-9


def test_rank_and_anon_set():
    scores = np.array([0.1, 0.2, 0.2, 5.0])
    assert rank_of(scores, 0) == 0                       # best -> exact catch
    assert rank_of(scores, 3) == 3
    assert anonymity_set_size(scores, eps=0.15) == 3     # 0.1, 0.2, 0.2 within eps of the best (0.1)
    assert anonymity_set_size(np.array([0.1, 0.1, 5.0]), eps=1e-6) == 2


def test_quantiles():
    med, p90, p95 = quantiles(list(range(101)))
    assert med == 50 and p90 == 90 and p95 == 95


def test_scope_tag():
    assert "UPPER BOUND" in SCOPE_TAG and "intersection" in SCOPE_TAG.lower()


def test_mustlocalize_gate():
    # best estimator demonstrably localizes (like the diagnostic: rank-1 0.35, err 0.7 radii, floor 0.017)
    assert mustlocalize_gate({"rank1": 0.35, "median_err_radii": 0.7}, random_floor=0.017)["ok"] is True
    # at the random floor -> not capable
    assert mustlocalize_gate({"rank1": 0.05, "median_err_radii": 1.8}, random_floor=0.017)["ok"] is False
    # localizes in rank but error too coarse -> not capable
    assert mustlocalize_gate({"rank1": 0.5, "median_err_radii": 2.0}, random_floor=0.017)["ok"] is False
    # high 1/N floor raises the margin bar above the observed rank-1 -> not capable
    assert mustlocalize_gate({"rank1": 0.3, "median_err_radii": 0.5}, random_floor=0.05)["ok"] is False
    # non-monotone power in coverage -> fail even if the point passes
    assert mustlocalize_gate({"rank1": 0.5, "median_err_radii": 0.5}, random_floor=0.017,
                             coverage_curve=[(0.3, 2.0), (0.6, 3.0), (0.9, 1.0)])["ok"] is False


def test_defense_gate():
    from soup_sim.anonymity import defense_gate
    # real gain: attack works, rank-1 cut >20%, survives timing-only, enough relays, big intersection
    assert defense_gate(0.30, 0.10, True, True, relay_density_ok=True, intersection_size=100)["credited"] is True
    # gain vanishes at TTL=inf -> message-dropping, not credited
    g = defense_gate(0.30, 0.10, True, False, intersection_size=100)
    assert g["credited"] is False and "dropping" in g["label"].lower()
    # attack didn't localize the baseline -> a drop is meaningless
    assert defense_gate(0.30, 0.10, False, True, intersection_size=100)["credited"] is False
    # no material drop
    assert defense_gate(0.30, 0.28, True, True, intersection_size=100)["credited"] is False
    # intersection too small -> inconclusive
    assert defense_gate(0.30, 0.05, True, True, intersection_size=5)["credited"] is False
    # low relay density -> not credited (gate-arm artifact)
    assert defense_gate(0.30, 0.10, True, True, relay_density_ok=False, intersection_size=100)["credited"] is False


def test_exposure_gate_margin_and_underpower():
    # powered, well above the 0.5 / K*floor threshold -> exposed
    assert exposure_gate(0.7, random_floor=0.02, beats_random=True, n_messages=200, n_reps=6)["exposed"] is True
    # high 1/N floor pushes the margin above rank-1 -> NOT exposed (kills vacuous-at-1/N)
    assert exposure_gate(0.4, random_floor=0.1, beats_random=True, n_messages=200, n_reps=6)["exposed"] is False
    # underpowered -> refuse
    assert exposure_gate(0.9, random_floor=0.02, beats_random=True, n_messages=20, n_reps=6)["exposed"] is False
    assert exposure_gate(0.9, random_floor=0.02, beats_random=True, n_messages=200, n_reps=2)["exposed"] is False
    # below threshold / no signal -> not exposed
    assert exposure_gate(0.3, random_floor=0.02, beats_random=True, n_messages=200, n_reps=6)["exposed"] is False
    assert exposure_gate(0.9, random_floor=0.02, beats_random=False, n_messages=200, n_reps=6)["exposed"] is False
