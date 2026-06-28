"""P3 — clock-independent expiry (hold-budget H, hop-energy B, EXPIRY-ONLY clock model).

All tests tiny/fast (small arena, reps<=2). See spec 2026-06-28-p3-clock-independent-expiry-spec.md.
The headline: honest soup clears in a blackout IFF the local hold-budget H is binding — and because H
is elapsed-since-receipt it clears even on a behind clock (offset-invariant)."""
import sys
from dataclasses import replace
import numpy as np
import pytest

from soup_sim.config import Config
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer
from soup_sim.budget import AirtimeBudget
from soup_sim.mobility import make_mobility, Mobility
from soup_sim.engine import Engine
from soup_sim.workload import make_cohort
from soup_sim.scenario import seen_window, run_one

BIG = 10 ** 9


# ---- tiny config builders -------------------------------------------------------------------------
def tiny(**kw):
    """Small RWP arena for bounded integration runs (engine is super-linear; keep n/window small)."""
    d = dict(n=20, width=60.0, height=60.0, radius=12.0, boundary="torus",
             mobility="rwp", speed_min=1.0, speed_max=1.0, dt=0.5, ttl=30.0,
             buffer_cap=10**6, throughput_ideal=1e9, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=30.0,
             drain=0.0, n_messages=8, seen_margin=10.0, master_seed=7)
    d.update(kw)
    return Config(**d)


def linecfg(**kw):
    d = dict(n=6, width=200.0, height=200.0, radius=10.0, boundary="walls",
             mobility="static", speed_min=1.0, speed_max=1.0, dt=1.0, ttl=1e12,
             buffer_cap=BIG, throughput_ideal=1e12, alpha=0.0, t_setup=0.0,
             p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1e12,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0)
    d.update(kw)
    return Config(**d)


def held_after(cfg, t_end, force_offset=None):
    """Run a bounded cohort flood; return (peak held after spread, held at t_end). force_offset puts
    EVERY node's RTC behind/ahead true time by a fixed amount (deterministic behind-clock probe)."""
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
    eng.run_until(cfg.warmup + cfg.ttl)
    peak = sum(len(b.store) for b in bufs)
    eng.run_until(t_end)
    return peak, sum(len(b.store) for b in bufs)


def chain_reach(B):
    """Static 6-node line; inject at node 0 with hop_energy_init=B; return reached-node count."""
    c = linecfg(hop_energy_init=B)
    pos = np.array([[float(9 * i), 50.0] for i in range(6)])
    mob = Mobility("static", pos, np.zeros_like(pos), c.width, c.height, c.speed_min, c.speed_max)
    bufs = [NodeBuffer(BIG, 1e12, c.rng(3, i)) for i in range(6)]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e12, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
    eng.inject(Blob(0, 0.0, 1e12, 1.0), 0)
    eng.run_until(50.0)
    return [i for i in range(6) if bufs[i].has(0)]


# ---- config defaults + validation -----------------------------------------------------------------
def test_p3_config_defaults_off_and_validate():
    c = tiny()
    assert c.hold_budget is None and c.hop_energy_init is None
    assert c.clock_skew_sigma == 0.0 and c.clock_trust_threshold is None
    assert c.creation_ts_clamp is None and c.blackout is False and c.blackout_future_max == 0.0
    c.validate()
    tiny(hold_budget=30.0, hop_energy_init=4, clock_skew_sigma=2.0,
         clock_trust_threshold=5.0, creation_ts_clamp=100.0, blackout=True,
         blackout_future_max=50.0).validate()
    for bad in (dict(hold_budget=0.0), dict(hold_budget=-1.0), dict(hop_energy_init=0),
                dict(clock_skew_sigma=-1.0), dict(clock_trust_threshold=-1.0),
                dict(creation_ts_clamp=-1.0), dict(blackout_future_max=-1.0)):
        with pytest.raises(ValueError):
            tiny(**bad).validate()


# ---- buffer-level expiry predicate (deterministic, no engine) -------------------------------------
def test_expire_default_args_bit_identical_to_legacy():
    """Default args reduce EXACTLY to the legacy `now >= expires_at` rule."""
    b = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b.store[1] = Blob(1, 0.0, 10.0, 1.0)
    b.store[2] = Blob(2, 0.0, 100.0, 1.0)
    b.expire(now=10.0)                 # no P3 args
    assert not b.has(1) and b.has(2)   # blob1 (expires_at=10) dropped; blob2 (=100) kept
    assert b.seen.get(1) == 10.0       # drop wrote the seen-record at `now`


def test_H_drops_at_exactly_H_untrusted_isolates_hold_budget():
    b = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b.store[1] = Blob(1, 0.0, 1e12, 1.0)        # ttl huge -> origin-TTL irrelevant
    rec = {1: 0.0}
    b.expire(now=9.9, hold_budget=10.0, receipt=rec, clock_trusted=False)
    assert b.has(1)                              # elapsed 9.9 < H=10 -> alive
    b.expire(now=10.0, hold_budget=10.0, receipt=rec, clock_trusted=False)
    assert not b.has(1)                          # elapsed 10 >= H -> dropped. Buffer-level the realized
    #   lifetime is exactly H (we call expire at the boundary); at ENGINE scale the sweep is per-step, so
    #   the realized honest lifetime is <= H + one expiry-sweep step (dt), not exactly H.
    assert 1 in b.seen


def test_behind_clock_immortal_without_H_then_clears_with_H():
    """Offset-invariance: a node FAR behind true time never fires origin-TTL, so without H it is
    immortal; with H it still drops (elapsed-since-receipt cancels the offset)."""
    # without H: behind clock -> origin-TTL local_now>=expires_at never true -> immortal
    b = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b.store[1] = Blob(1, 0.0, 10.0, 1.0)
    b.expire(now=1e6, hold_budget=None, receipt=None, clock_trusted=True, clock_offset=-1e6)
    assert b.has(1)                              # immortal under a behind clock
    # with H: still clears regardless of the (huge negative) offset
    b2 = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b2.store[1] = Blob(1, 0.0, 10.0, 1.0)
    rec = {1: 0.0}
    b2.expire(now=19.0, hold_budget=20.0, receipt=rec, clock_trusted=True, clock_offset=-1e6)
    assert b2.has(1)                             # 19 - 0 = 19 < H=20
    b2.expire(now=25.0, hold_budget=20.0, receipt=rec, clock_trusted=True, clock_offset=-1e6)
    assert not b2.has(1)                         # 25 - 0 = 25 >= H=20 -> dropped despite behind clock


def test_trusted_origin_ttl_fires_even_with_huge_H():
    """clock-trusted path: the absolute origin-TTL still expires a blob at created_at+ttl even when H is huge."""
    b = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b.store[1] = Blob(1, 0.0, 10.0, 1.0)
    b.expire(now=10.0, hold_budget=1e12, receipt={1: 0.0}, clock_trusted=True, clock_offset=0.0)
    assert not b.has(1)                          # origin-TTL fired at created_at+ttl=10


def test_H_drop_writes_seen_no_resurrection_in_window():
    b = NodeBuffer(1, seen_window=100.0, rng=np.random.default_rng(0))
    blob = Blob(1, 0.0, 1e12, 1.0)
    b.store[1] = blob
    b.expire(now=20.0, hold_budget=10.0, receipt={1: 0.0}, clock_trusted=False)
    assert not b.has(1) and 1 in b.seen                 # H-dropped, seen written
    assert b.offer(blob, now=25.0) == "RejectedSeen"    # re-offer within H-window -> no resurrection
    assert not b.has(1)                                 # did not regain life


# ---- hop-energy spread cap (separate from clearance) ----------------------------------------------
def test_hop_energy_B_bounds_spread():
    assert chain_reach(None) == [0, 1, 2, 3, 4, 5]      # carried-but-ignored: full reach (today)
    assert chain_reach(2) == [0, 1]                     # B=2 -> 2 nodes
    assert chain_reach(3) == [0, 1, 2]                  # B=3 -> 3 nodes
    assert chain_reach(4) == [0, 1, 2, 3]               # smaller B reaches fewer nodes
    assert len(chain_reach(2)) < len(chain_reach(4))


# ---- the clock offset touches ONLY expiry (not causality/delivery) --------------------------------
def test_offset_does_not_touch_delivery_graph():
    """With expiry effectively disabled (huge ttl + huge H + trusted), a large per-node RTC offset must
    leave the DELIVERY graph byte-identical — proving the offset enters only the (never-firing) expiry
    comparison, never contact/causality/acquisition/measurement timing."""
    base = tiny(ttl=1e12, hold_budget=1e12, measure_window=15.0)
    r_off = run_one(replace(base, clock_skew_sigma=0.0))
    r_on = run_one(replace(base, clock_skew_sigma=50.0))
    assert r_off["transmissions"] == r_on["transmissions"]
    assert r_off["delivery_ratio"] == r_on["delivery_ratio"]
    assert r_off["latencies"] == r_on["latencies"]


# ---- default-inert: off path draws no namespace-10/11 RNG + bit-identity --------------------------
def test_default_inert_no_clock_rng_and_legacy_path():
    c = tiny()
    mob = make_mobility(c, c.rng(0))
    bufs = [NodeBuffer(c.buffer_cap, seen_window(c), c.rng(3, i)) for i in range(c.n)]
    eng = Engine(c, mob, bufs, AirtimeBudget(1e9, 0, 0, 0, 1.0), c.rng(1), on_deliver=lambda *_: None)
    assert eng.clock_offset is None        # sigma=0 -> NO rng(10,i) drawn
    assert eng._expiry_ext is False         # legacy expire(t) path runs -> bit-identical


def test_deferred_median_clamp_not_wired():
    """The gossip-median auto-flag + creation-ts clamp are DEFERRED (open problem): no engine state, no
    helpers, and setting their (still-validated) config fields does NOT change a run — clearance never
    depended on them."""
    eng = Engine.__new__(Engine)            # no instance needed: assert the helpers are gone from the class
    assert not hasattr(eng, "observed_created")
    assert not hasattr(Engine, "_gossip_median") and not hasattr(Engine, "_clamp_created")
    assert not hasattr(Engine, "_observe_created")
    # the deferred config knobs are inert: a run with them set == a run without them set
    base = tiny()
    r0 = run_one(base)
    r1 = run_one(replace(base, clock_trust_threshold=5.0, creation_ts_clamp=100.0))
    for k in ("delivery_ratio", "transmissions", "latencies", "circulated_per_min", "charged_airtime"):
        assert r0[k] == r1[k]


def test_bit_identity_inert_knob_is_noop():
    """Non-tautological default-inert check: flip a P3 knob that MUST be a no-op given the others off.
    clock_skew_sigma only touches the expiry comparison, so with expiry unable to fire (huge ttl + huge
    H + trusted) the FULL run_one result is identical to sigma=0 — the offset machinery (incl. its
    rng(10) draws) perturbs nothing else (metrics, other RNG namespaces)."""
    base = tiny(ttl=1e12, hold_budget=1e12, measure_window=15.0)
    r_off = run_one(replace(base, clock_skew_sigma=0.0))
    r_on = run_one(replace(base, clock_skew_sigma=50.0))
    for k in r_off:
        if k == "manifest":
            continue                        # manifest legitimately differs by the sigma value itself
        assert r_off[k] == r_on[k], f"sigma flip perturbed {k}"


# ---- THE HEADLINE: blackout soup-clearance iff H (integration, tiny) ------------------------------
def test_blackout_clears_iff_hold_budget():
    """Untrusted clock (blackout) -> origin-TTL never fires. H OFF: an immortal tail persists at
    t >> maxTTL; H ON: the soup clears (held -> 0)."""
    base = tiny(blackout=True)
    t_end = 10 * base.ttl
    _, end_off = held_after(replace(base, hold_budget=None), t_end)
    peak_on, end_on = held_after(replace(base, hold_budget=base.ttl), t_end)
    assert end_off > 0                      # immortal tail without H
    assert peak_on > 0                      # blobs did spread...
    assert end_on == 0                      # ...and fully cleared by H at t >> maxTTL


def test_behind_clock_clears_by_H_integration():
    """Engine-level behind-clock: every node forced far behind true time, clock trusted (not blackout).
    Without H immortal; with H clears (offset cancels in elapsed-since-receipt)."""
    base = tiny(clock_skew_sigma=1e-9)      # sigma>0 just allocates the offset array; we override it
    t_end = 10 * base.ttl
    _, end_off = held_after(replace(base, hold_budget=None), t_end, force_offset=-1e6)
    _, end_on = held_after(replace(base, hold_budget=base.ttl), t_end, force_offset=-1e6)
    assert end_off > 0 and end_on == 0


def test_blackout_H_run_is_deterministic():
    base = tiny(blackout=True, hold_budget=30.0, blackout_future_max=50.0)
    a = held_after(base, 10 * base.ttl)
    b = held_after(base, 10 * base.ttl)
    assert a == b


# ---- clock_trusted is an EXPLICIT input (blackout-driven), not auto-derived -----------------------
def _engine_with(cfg):
    mob = make_mobility(cfg, cfg.rng(0))
    bufs = [NodeBuffer(cfg.buffer_cap, seen_window(cfg), cfg.rng(3, i)) for i in range(cfg.n)]
    return Engine(cfg, mob, bufs, AirtimeBudget(1e9, 0, 0, 0, 1.0), cfg.rng(1), on_deliver=lambda *_: None)


def test_clock_trusted_is_explicit_blackout_driven():
    assert _engine_with(tiny())._clock_trusted(0, now=1e9) is True           # not blackout -> trusted
    assert _engine_with(tiny(blackout=True))._clock_trusted(0, now=0.0) is False  # blackout -> untrusted
    # the trust value does NOT drift with elapsed time (the bug the gossip-median auto-flag had):
    eng = _engine_with(tiny())
    assert eng._clock_trusted(0, now=0.0) == eng._clock_trusted(0, now=1e12) is True


def test_trusted_clock_clears_by_TTL_untrusted_only_by_H():
    """blackout=False -> trusted -> origin-TTL clears even with NO H. blackout=True -> untrusted ->
    origin-TTL never fires -> only H clears (the headline contrast, at integration scale)."""
    base = tiny()
    t_end = 10 * base.ttl
    _, end_trusted_noH = held_after(replace(base, blackout=False, hold_budget=None), t_end)
    _, end_untrusted_noH = held_after(replace(base, blackout=True, hold_budget=None), t_end)
    _, end_untrusted_H = held_after(replace(base, blackout=True, hold_budget=base.ttl), t_end)
    assert end_trusted_noH == 0          # trusted clock -> TTL clears the soup, no H needed
    assert end_untrusted_noH > 0         # untrusted -> TTL never fires -> immortal without H
    assert end_untrusted_H == 0          # untrusted -> H clears regardless of the (dropped) TTL path


# ---- monotonicity residual: a slow (behind) clock within ±threshold extends life up to TTL+threshold
def test_monotonicity_residual_within_threshold_then_H_beyond():
    TTL, thr, H = 10.0, 3.0, 1e12
    # WITHIN threshold + TRUSTED: a clock behind by exactly `thr` fires origin-TTL late, at TTL+thr.
    b = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b.store[1] = Blob(1, 0.0, TTL, 1.0)
    b.expire(now=TTL + thr - 0.1, hold_budget=H, receipt={1: 0.0}, clock_trusted=True, clock_offset=-thr)
    assert b.has(1)                                 # 12.9: local_now 9.9 < TTL -> alive (residual > TTL)
    b.expire(now=TTL + thr, hold_budget=H, receipt={1: 0.0}, clock_trusted=True, clock_offset=-thr)
    assert not b.has(1)                             # 13.0: realized lifetime == TTL+thr (bounded residual)
    # BEYOND threshold -> run as UNTRUSTED -> origin-TTL never fires -> clears strictly by H instead
    b2 = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b2.store[1] = Blob(1, 0.0, TTL, 1.0)
    b2.expire(now=1e6, hold_budget=None, receipt=None, clock_trusted=False, clock_offset=-1e6)
    assert b2.has(1)                                # untrusted + no H -> immortal (offset beyond any bound)
    b2.expire(now=20.0, hold_budget=20.0, receipt={1: 0.0}, clock_trusted=False, clock_offset=-1e6)
    assert not b2.has(1)                            # H clears it (independent of the huge offset)


# ---- behind-clock boundary (the exact >= H crossing) ----------------------------------------------
def test_behind_clock_boundary_drops_at_H():
    b = NodeBuffer(10, 1e9, np.random.default_rng(0))
    b.store[1] = Blob(1, 0.0, 1e12, 1.0)
    b.expire(now=20.0, hold_budget=20.0, receipt={1: 0.0}, clock_trusted=True, clock_offset=-1e6)
    assert not b.has(1)                             # offset=-1e6, H=20, receipt=0, now=20.0 -> dropped


# ---- bounded buffer + future-dated created_at: H still clears (H keys on TRUE receipt) -------------
def test_bounded_buffer_blackout_future_dated_clears_by_H():
    """A CAPPED buffer evicts oldest-by-created; a future-dated created_at looks YOUNGEST so it evades
    eviction, and (untrusted clock) the origin-TTL never fires -> immortal survivors without H. H keys on
    the TRUE receipt time, not created_at, so it clears them anyway."""
    base = tiny(buffer_cap=4, n_messages=12, blackout=True, blackout_future_max=200.0)
    t_end = 10 * base.ttl
    _, end_off = held_after(replace(base, hold_budget=None), t_end)
    _, end_on = held_after(replace(base, hold_budget=base.ttl), t_end)
    assert end_off > 0                              # future-dated survivors evade eviction + TTL -> immortal
    assert end_on == 0                              # H clears them despite the forged-future created_at
