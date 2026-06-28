"""P4 PR-1 — ferrying below the percolation threshold (the cold-start lift).

Below the static threshold d_c~=4.51 a uniform network shatters (static delivery -> 0), but mobile nodes
CARRY blobs between components (store-carry-forward = blind ferrying). HONEST framing (per adversarial
review): RWP on a torus is ERGODIC, so delivery -> 1.0 for ANY d>0 given enough time -> the 1.0 ceiling is
a mixing tautology, NOT a capability result. The informative, mission-relevant quantity is the
BUDGET-TO-DELIVER, which rises as density falls (the cost of cold-start). All UPPER BOUNDS (RWP open-field,
no airtime/buffer cost on this path). Tiny/fast: cold-start ⇒ small N (~13-68). See spec 2026-06-28-p4."""
import numpy as np

from soup_sim.config import Config
from soup_sim.scenario import ferrying_budget_sweep, density_to_n
from soup_sim.report import ferrying_to_csv_string


def base(**kw):
    d = dict(n=2, width=140.0, height=140.0, radius=12.0, boundary="torus", mobility="rwp",
             speed_min=2.0, speed_max=2.0, dt=0.5, ttl=30.0, buffer_cap=10**6, throughput_ideal=1e9,
             alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=30.0,
             drain=0.0, n_messages=10, seen_margin=10.0, master_seed=7)
    d.update(kw)
    return Config(**d)


def _row(res, density):
    return next(r for r in res["rows"] if r["density"] == density)


def test_ferrying_lift_below_threshold_is_real_and_sub_threshold():
    """At a deeply sub-threshold density the static network shatters (bound < 0.1), yet with a large time
    budget ferrying delivers — a real lift. (The large-budget ceiling itself is ergodic saturation; the
    test with TEETH is that a SHORT budget sits near the static floor — no time to ferry.)"""
    res = ferrying_budget_sweep(base(), densities=[0.3], budgets=[10.0, 200.0], reps=4)
    row = _row(res, 0.3)
    assert row["static_bound"] < 0.1, f"density not sub-threshold: {row['static_bound']}"
    big = row["per_budget"][200.0]["delivery_mean"]
    small = row["per_budget"][10.0]["delivery_mean"]
    assert big > 0.8 and big > small               # ferrying delivers given budget (ergodic ceiling)
    assert small < 0.4, f"short budget must sit near the static floor (no time to ferry): {small}"
    assert row["per_budget"][200.0]["lift"] > 0.7  # lift over the static bound is large


def test_budget_to_deliver_rises_as_density_falls():
    """THE honest, discriminating result (robust across seeds — the brittle per-T comparison was replaced):
    the smallest budget reaching 50% delivery is >= for a sparser venue than a denser one (and finite for
    both within the swept range). This is the cost of cold-start: thinner crowd ⇒ longer hold to deliver."""
    res = ferrying_budget_sweep(base(), densities=[0.3, 1.0], budgets=[20.0, 60.0, 150.0, 400.0], reps=4)
    b_sparse = _row(res, 0.3)["budget_to_half"]
    b_dense = _row(res, 1.0)["budget_to_half"]
    assert b_dense is not None and b_sparse is not None, "both should reach 50% within the swept budgets"
    assert b_sparse >= b_dense, f"sparser must need >= budget: sparse={b_sparse} dense={b_dense}"


def test_ferrying_latency_reported_and_censored():
    """Delivery below threshold is bought with delay. t50 is reported (median, delivered-only + censored at
    T -> a LOWER bound); it must be finite and within [0, T] at a budget that delivers."""
    res = ferrying_budget_sweep(base(), densities=[0.8], budgets=[80.0], reps=4)
    t50 = _row(res, 0.8)["per_budget"][80.0]["t50"]
    assert np.isfinite(t50) and 0.0 <= t50 <= 80.0, f"t50 must be finite and censored within [0,T]: {t50}"


def test_ergodic_saturation_even_when_extremely_sparse():
    """Documents the tautology so it can't masquerade as a capability claim: even an extremely sparse venue
    (here N small, static bound ~0) saturates toward full delivery at a large enough budget — that is RWP
    ergodic mixing, NOT evidence the protocol 'beats' percolation. Only the budget scaling is informative."""
    res = ferrying_budget_sweep(base(), densities=[0.3], budgets=[400.0], reps=3)
    assert _row(res, 0.3)["per_budget"][400.0]["delivery_mean"] > 0.9


def test_ferrying_sweep_deterministic():
    a = ferrying_budget_sweep(base(), densities=[0.5], budgets=[30.0, 100.0], reps=2)
    b = ferrying_budget_sweep(base(), densities=[0.5], budgets=[30.0, 100.0], reps=2)
    assert a["rows"] == b["rows"]


def test_report_carries_honesty_headers():
    res = ferrying_budget_sweep(base(), densities=[0.5], budgets=[30.0], reps=2)
    csv = ferrying_to_csv_string(res, base().manifest())
    assert "UPPER BOUND" in csv and "RWP" in csv               # optimism disclaimer
    assert "ERGODIC" in csv                                    # the saturation caveat is loud
    assert "budget_to_half" in csv and "t50_delivered_censored" in csv and "lift" in csv
