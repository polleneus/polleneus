"""P3 — PR-2: density-adaptive hold-budget (load-adaptive clearance).

H_eff = H_min + (H_max-H_min)*(1-occ)^k with occ = len(store)/cap (clock-free). Empty buffer -> H_max
(hold long, protect delivery when thin); full buffer -> H_min (shed fast, resist overflow when dense).
The headline (test_pareto_*): no single fixed H is on both fronts — fixed-H_max saturates storage when
dense, fixed-H_min loses delivery when sparse — but the adaptive knob is good on BOTH. All tests
tiny/fast (small arena, one-shot cohort). See spec 2026-06-28 §P3-PR-2."""
from dataclasses import replace
import numpy as np
import pytest

from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer
from soup_sim.budget import AirtimeBudget
from soup_sim.mobility import make_mobility
from soup_sim.engine import Engine
from soup_sim.workload import make_cohort
from soup_sim.scenario import seen_window, run_one


def tiny(**kw):
    d = dict(n=20, width=60.0, height=60.0, radius=12.0, boundary="torus",
             mobility="rwp", speed_min=1.0, speed_max=1.0, dt=0.5, ttl=30.0,
             buffer_cap=10**6, throughput_ideal=1e9, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=30.0,
             drain=0.0, n_messages=8, seen_margin=10.0, master_seed=7)
    d.update(kw)
    return Config(**d)


def _engine_with(cfg):
    cfg.validate()
    mob = make_mobility(cfg, cfg.rng(0))
    bufs = [NodeBuffer(cfg.buffer_cap, seen_window(cfg), cfg.rng(3, i)) for i in range(cfg.n)]
    return Engine(cfg, mob, bufs, AirtimeBudget(1e9, 0, 0, 0, 1.0), cfg.rng(1), on_deliver=lambda *_: None)


def flood_end_held(cfg, t_spread, t_end, force_offset=None):
    """One-shot cohort flood; return (peak total held after t_spread, total held at t_end). force_offset
    puts EVERY node's RTC behind/ahead true time by a fixed amount (deterministic behind-clock probe)."""
    cfg.validate()
    mob = make_mobility(cfg, cfg.rng(0))
    bufs = [NodeBuffer(cfg.buffer_cap, seen_window(cfg), cfg.rng(3, i)) for i in range(cfg.n)]
    budget = AirtimeBudget(cfg.throughput_ideal, cfg.alpha, cfg.t_setup, cfg.p_fail, cfg.blob_size)
    eng = Engine(cfg, mob, bufs, budget, cfg.rng(1), on_deliver=lambda *_: None)
    eng.run_until(cfg.warmup)
    for blob, src, dst in make_cohort(cfg, inject_time=cfg.warmup, rng=cfg.rng(2)):
        eng.inject(blob, src)
    if force_offset is not None:
        eng.clock_offset = [float(force_offset)] * cfg.n
    eng.run_until(cfg.warmup + t_spread)
    peak = sum(len(b.store) for b in bufs)
    eng.run_until(cfg.warmup + t_end)
    return peak, sum(len(b.store) for b in bufs)


def avg_held(cfg, t_end, sample_dt=10.0):
    """One-shot flood; return (time-averaged total held over the run, list of busiest-node H_eff samples).
    Time-averaged held is the storage-TIME pressure (the hard cap+eviction make instantaneous OVERflow
    impossible; the real cost of holding too long is sustained saturation -> eviction churn)."""
    cfg.validate()
    mob = make_mobility(cfg, cfg.rng(0))
    bufs = [NodeBuffer(cfg.buffer_cap, seen_window(cfg), cfg.rng(3, i)) for i in range(cfg.n)]
    eng = Engine(cfg, mob, bufs, AirtimeBudget(1e9, 0, 0, 0, 1.0), cfg.rng(1), on_deliver=lambda *_: None)
    for blob, src, dst in make_cohort(cfg, inject_time=0.0, rng=cfg.rng(2)):
        eng.inject(blob, src)
    held, heffs, t = [], [], 0.0
    while t < t_end:
        t += sample_dt
        eng.run_until(t)
        held.append(sum(len(b.store) for b in bufs))
        if cfg.hold_budget_adaptive:
            busy = max(range(cfg.n), key=lambda i: len(bufs[i].store))
            heffs.append(eng._H_eff(busy))
    return float(np.mean(held)), heffs


# ---- config defaults + validation -----------------------------------------------------------------
def test_pr2_config_defaults_off_and_validate():
    c = tiny()
    assert c.hold_budget_adaptive is False
    assert c.hold_budget_min is None and c.hold_budget_max is None
    assert c.hold_budget_shape_k == 1.0
    c.validate()
    # adaptive ON requires a band
    with pytest.raises(ValueError):
        tiny(hold_budget_adaptive=True).validate()
    with pytest.raises(ValueError):
        tiny(hold_budget_adaptive=True, hold_budget_min=10.0).validate()   # max missing
    # min must be <= max
    with pytest.raises(ValueError):
        tiny(hold_budget_adaptive=True, hold_budget_min=50.0, hold_budget_max=10.0).validate()
    # k >= 1
    with pytest.raises(ValueError):
        tiny(hold_budget_shape_k=0.5).validate()
    # positive band
    with pytest.raises(ValueError):
        tiny(hold_budget_min=0.0).validate()
    # a valid adaptive config passes
    tiny(hold_budget_adaptive=True, hold_budget_min=5.0, hold_budget_max=50.0).validate()


# ---- default-inert: the band is a no-op while adaptive is OFF --------------------------------------
def test_pr2_default_inert_bit_identical():
    """Setting the PR-2 band but leaving hold_budget_adaptive=False must change NOTHING (the fixed
    hold_budget path runs unchanged). Compare the FULL run_one result against a no-band baseline."""
    base = tiny(hold_budget=20.0)                      # PR-1 fixed-H path active
    r_off = run_one(base)
    r_band = run_one(replace(base, hold_budget_min=2.0, hold_budget_max=999.0, hold_budget_shape_k=3.0))
    for k in r_off:
        if k == "manifest":
            continue                                  # manifest legitimately differs by the band values
        assert r_off[k] == r_band[k], f"inert PR-2 band perturbed {k}"


# ---- H_eff curve: monotone in occupancy, bounded to [H_min, H_max] ---------------------------------
def test_H_eff_monotone_and_bounded():
    eng = _engine_with(tiny(hold_budget_adaptive=True, hold_budget_min=5.0, hold_budget_max=50.0,
                            buffer_cap=100))

    def heff_at(count):
        eng.buffers[0].store = {i: Blob(i, 0.0, 1e9, 1.0) for i in range(count)}
        return eng._H_eff(0)

    h_empty, h_half, h_full = heff_at(0), heff_at(50), heff_at(100)
    assert abs(h_empty - 50.0) < 1e-9                  # occ=0 -> H_max
    assert abs(h_full - 5.0) < 1e-9                    # occ=1 -> H_min
    assert h_empty > h_half > h_full                   # strictly monotone decreasing in occupancy
    assert all(5.0 - 1e-9 <= h <= 50.0 + 1e-9 for h in (h_empty, h_half, h_full))
    assert abs(heff_at(150) - 5.0) < 1e-9             # over-cap clamps occ to 1 -> H_min (never below)
    # shape k>1 holds nearer H_max at low occupancy (convex in (1-occ)): k=3 > k=1 at occ=0.5
    eng3 = _engine_with(tiny(hold_budget_adaptive=True, hold_budget_min=5.0, hold_budget_max=50.0,
                             hold_budget_shape_k=3.0, buffer_cap=100))
    eng3.buffers[0].store = {i: Blob(i, 0.0, 1e9, 1.0) for i in range(50)}
    assert eng3._H_eff(0) > h_half                     # k=3 sheds less than k=1 at the same mid occupancy


# ---- offset-invariance preserved: the ADAPTIVE ENGINE still clears on a behind clock ---------------
def test_offset_invariance_preserved_adaptive_engine():
    """The PR-1 crown jewel must survive PR-2 through the FULL adaptive engine path (not a buffer literal).
    H_eff is a threshold on elapsed-since-receipt and occ is a count (clock-free), so a behind clock can't
    defeat it. Force every node's RTC -1e6 behind true time, run the adaptive engine, blackout (untrusted ->
    origin-TTL never fires -> only H can clear): the soup must still clear to 0."""
    base = tiny(blackout=True, hold_budget_adaptive=True, hold_budget_min=3.0, hold_budget_max=30.0)
    _, end = flood_end_held(base, t_spread=base.ttl, t_end=10 * base.ttl, force_offset=-1e6)
    assert end == 0
    # and via the engine's own per-node offset draw (clock_skew_sigma>0), large skew + blackout still clears
    base2 = tiny(blackout=True, clock_skew_sigma=1e5, hold_budget_adaptive=True,
                 hold_budget_min=3.0, hold_budget_max=30.0)
    _, end2 = flood_end_held(base2, t_spread=base2.ttl, t_end=10 * base2.ttl)
    assert end2 == 0


# ---- blackout clears with adaptive on -------------------------------------------------------------
def test_blackout_clears_with_adaptive():
    """Untrusted clock (blackout) + adaptive H: H_eff <= H_max < inf, so the soup still clears."""
    base = tiny(blackout=True, hold_budget_adaptive=True, hold_budget_min=3.0, hold_budget_max=30.0)
    _, end = flood_end_held(base, t_spread=base.ttl, t_end=10 * base.ttl)
    assert end == 0


# ---- THE HONEST HEADLINE: no single GLOBAL fixed H is good in both regimes; adaptive captures the ----
# ---- favorable end of EACH per local load. It TRADES (not strict dominance) -------------------------
def test_adaptive_trades_no_global_fixed_H_wins_both():
    """The honest claim (NOT "dominates"): a fixed H forces ONE global operating point — small H starves
    delivery in a thin network; large H saturates storage when dense. Adaptive keys on LOCAL occupancy and
    captures the FAVORABLE END of each regime without a global pre-commit:
      DENSE storage: adaptive's time-averaged held is far below fixed-H_max's (which holds for the full,
        FINITE H_max -> sustained saturation). It is *slightly above* fixed-H_min (which holds nothing) —
        so it TRADES, it does not strictly dominate H_min on storage.
      SPARSE delivery: adaptive matches fixed-H_max delivery (occ~0 -> H_eff~H_max locally) while fixed-H_min
        loses it.
    Crucially the dense win runs through INTERIOR H_eff values (the feedback loop), not a pinned endpoint, so
    the curve earns its keep. The full per-node benefit is realized in a HETEROGENEOUS network where nodes
    face different loads at once — an end-to-end heterogeneous-network experiment is a noted follow-up."""
    # --- DENSE storage: FINITE H_max (no 1e9 tautology), measure time-averaged held + interior H_eff ---
    dense = tiny(n=25, width=40.0, height=40.0, radius=12.0, buffer_cap=8, n_messages=20,
                 ttl=1000.0, seen_margin=10.0, master_seed=11)   # ttl >> run so H, not TTL, binds
    H_MIN, H_MAX = 2.0, 200.0
    a_avg, heffs = avg_held(replace(dense, hold_budget_adaptive=True,
                                    hold_budget_min=H_MIN, hold_budget_max=H_MAX), 250.0)
    mx_avg, _ = avg_held(replace(dense, hold_budget=H_MAX), 250.0)
    mn_avg, _ = avg_held(replace(dense, hold_budget=H_MIN), 250.0)
    assert mn_avg <= a_avg < mx_avg          # TRADE+bracket: lighter than hold-long, >= shed-fast (not dominance)
    assert mx_avg > 4 * a_avg                # adaptive captures MOST of H_min's storage hygiene (big margin)
    # the win runs through INTERIOR H_eff (curve exercised, not a pinned endpoint):
    assert any(H_MIN + 1e-6 < h < H_MAX - 1e-6 for h in heffs), f"H_eff never interior: {heffs}"

    # --- SPARSE delivery: ttl=window so the cohort is fair-chance; H is the binding limit ---
    sparse = tiny(n=12, width=90.0, height=90.0, radius=16.0, speed_min=2.0, speed_max=2.0,
                  buffer_cap=10**6, ttl=120.0, measure_window=120.0, drain=0.0, n_messages=10, master_seed=11)
    d_adapt = run_one(replace(sparse, hold_budget_adaptive=True,
                              hold_budget_min=2.0, hold_budget_max=119.0))["delivery_ratio"]
    d_hmin = run_one(replace(sparse, hold_budget=2.0))["delivery_ratio"]
    d_hmax = run_one(replace(sparse, hold_budget=119.0))["delivery_ratio"]
    assert d_adapt > d_hmin                   # adaptive gets H_max-grade delivery WITHOUT a global H_max commit
    assert d_adapt >= d_hmax - 1e-9           # in a thin venue occ~0 -> adaptive ~ H_max (honest equivalence)
    assert d_hmax > d_hmin                    # delivery IS H-sensitive (the trade is real, not vacuous)


# ---- determinism ----------------------------------------------------------------------------------
def test_pr2_adaptive_deterministic():
    c = tiny(buffer_cap=8, n_messages=12, hold_budget_adaptive=True, hold_budget_min=2.0,
             hold_budget_max=50.0, ttl=1e9)
    assert flood_end_held(c, 30.0, 150.0) == flood_end_held(c, 30.0, 150.0)
