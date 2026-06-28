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
    assert not b.has(1)                          # elapsed 10 >= H -> dropped (realized lifetime == H)
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
    assert eng.observed_created is None     # no gossip/clamp -> no observation tracking
    assert eng._expiry_ext is False         # legacy expire(t) path runs -> bit-identical


def test_default_inert_run_one_identical():
    base = tiny()
    r_default = run_one(base)
    r_explicit_off = run_one(replace(base, hold_budget=None, hop_energy_init=None,
                                     clock_skew_sigma=0.0, clock_trust_threshold=None,
                                     creation_ts_clamp=None, blackout=False))
    for k in ("delivery_ratio", "transmissions", "latencies", "circulated_per_min", "charged_airtime"):
        assert r_default[k] == r_explicit_off[k]


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


# ---- gossip-median + admission-time clamp (clock-trust guard; not clearance) ----------------------
def _engine_with(cfg):
    mob = make_mobility(cfg, cfg.rng(0))
    bufs = [NodeBuffer(cfg.buffer_cap, seen_window(cfg), cfg.rng(3, i)) for i in range(cfg.n)]
    return Engine(cfg, mob, bufs, AirtimeBudget(1e9, 0, 0, 0, 1.0), cfg.rng(1), on_deliver=lambda *_: None)


def test_gossip_median_trimmed_and_clock_trust():
    eng = _engine_with(tiny(clock_trust_threshold=5.0))
    assert eng._gossip_median(0) is None                  # cold start -> None -> trusted
    assert eng._clock_trusted(0, now=100.0) is True
    eng.observed_created[0] = [100.0] * 9 + [1e9]         # one liar (minority) far in the future
    assert abs(eng._gossip_median(0) - 100.0) < 1e-9      # trimmed median ignores the liar
    assert eng._clock_trusted(0, now=100.0) is True       # |100 - 100| <= 5 -> trusted
    assert eng._clock_trusted(0, now=200.0) is False      # |200 - 100| > 5 -> untrusted


def test_blackout_forces_untrusted():
    eng = _engine_with(tiny(blackout=True, clock_trust_threshold=5.0))
    eng.observed_created = {0: [100.0]}
    assert eng._clock_trusted(0, now=100.0) is False      # blackout -> never trusted (no NTP)


def test_creation_ts_clamp_pulls_down_extreme_future_only():
    eng = _engine_with(tiny(creation_ts_clamp=50.0))
    eng.observed_created[0] = [100.0] * 5                 # median ~100, ceiling = 150
    far = Blob(1, created_at=10_000.0, ttl=30.0, size=1.0)
    fresh = Blob(2, created_at=130.0, ttl=30.0, size=1.0)
    assert eng._clamp_created(0, far).created_at == 150.0  # extreme-future clamped to ceiling
    assert eng._clamp_created(0, fresh).created_at == 130.0  # honest-fresh (below ceiling) untouched
    # cold start: no median -> no clamp (loose; never false-rejects)
    eng2 = _engine_with(tiny(creation_ts_clamp=50.0))
    assert eng2._clamp_created(0, far).created_at == 10_000.0
