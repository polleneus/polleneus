"""P2 PR-1 — token rate-limit harness (spec §3/§4). A DEFAULT-INERT post-hoc overlay over the
recorded contact graph (NOT in the engine), so mode='off' is bit-identical to the prior engine.

Tests assert, all on TINY/bounded arenas (the engine is super-linear in crowd size):
  - config: the three fields default OFF and validate;
  - OFF bit-identity: run_one with token fields at defaults == run_one without them (exact);
  - overlay unit logic on hand-built episode graphs (broken/anchored ~ D for a static dense holder,
    gossip << that; a re-met acceptor is not a new slot; the fragmented case leaks fully);
  - scenario: broken ~ anchored ~ D >> gossip for a static dense holder; mobile leaks more than
    static under a per-hop gossip delay; residual grows as the venue fragments; Q bounds slots/PHY;
    determinism (same seed -> identical); the pre-registered broken-must-demonstrate gate.
"""
import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import (run_one, token_rate_limit_sweep, token_amplification,
                               TOKEN_BROKEN_FRACTION, TOKEN_SCOPE_TAG, density_to_n, _seed_for)
from soup_sim.report import token_to_csv_string, TOKEN_FIELDS
from soup_sim import token as tok


# ------------------------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------------------------
def base_cfg(**kw):
    """run_one fixture (matches tests/test_config.py::base shape)."""
    d = dict(n=60, width=100.0, height=100.0, radius=10.0, boundary="torus",
             mobility="static", speed_min=1.0, speed_max=1.0, dt=0.1, ttl=600.0,
             buffer_cap=200, throughput_ideal=1000.0, alpha=0.5, t_setup=0.2,
             p_fail=0.0, blob_size=1000.0, warmup=0.0, measure_window=20.0,
             drain=0.0, n_messages=20, seen_margin=60.0, master_seed=42)
    d.update(kw)
    return Config(**d)


def sweep_cfg(**kw):
    """TINY token-sweep fixture: small dense arena, RWP-capable, fast. CFL: speed*dt <= radius/4."""
    d = dict(n=0, width=40.0, height=40.0, radius=9.0, boundary="torus", mobility="rwp",
             speed_min=2.0, speed_max=2.0, dt=0.25, ttl=60.0, buffer_cap=300, throughput_ideal=8e3,
             alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=2.0, measure_window=20.0,
             drain=0.0, n_messages=12, seen_margin=20.0, master_seed=7,
             airtime_model="collision", beta=0.1, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)
    d.update(kw)
    return Config(**d)


# ------------------------------------------------------------------------------------------------
# Config: default-OFF + validation
# ------------------------------------------------------------------------------------------------
def test_token_fields_default_off_and_validate():
    c = base_cfg()
    assert c.token_rate_limit_mode == "off" and c.phy_session_quota == 0 and c.gossip_delay == 0.0
    c.validate()                                                       # ok at defaults
    for m in ("off", "broken", "anchored", "gossip"):
        base_cfg(token_rate_limit_mode=m).validate()                  # all modes valid
    with pytest.raises(ValueError, match="token_rate_limit_mode"):
        base_cfg(token_rate_limit_mode="bogus").validate()
    with pytest.raises(ValueError, match="phy_session_quota"):
        base_cfg(phy_session_quota=-1).validate()
    with pytest.raises(ValueError, match="gossip_delay"):
        base_cfg(gossip_delay=-1.0).validate()


def test_token_off_bit_identical():
    """token fields at defaults must be byte-for-byte identical to a run with them never set: the
    overlay lives OUTSIDE the engine, so run_one is unchanged. EXACT equality (not approx)."""
    plain = base_cfg(mobility="rwp", speed_min=1.0, speed_max=1.0)
    explicit_off = replace(plain, token_rate_limit_mode="off", phy_session_quota=0, gossip_delay=0.0)
    r0, r1 = run_one(plain), run_one(explicit_off)
    for key in ("circulated_per_min", "served_blobs", "offered_blobs", "transmissions",
                "delivery_ratio", "utilization", "utilization_vs_offered", "t50",
                "setup_starved_blobs", "quantization_blobs", "contention_blobs"):
        assert r0[key] == r1[key], f"token-OFF changed {key}: {r0[key]} != {r1[key]}"


# ------------------------------------------------------------------------------------------------
# Overlay unit logic (hand-built episode graphs — no engine, fully deterministic)
# ------------------------------------------------------------------------------------------------
DENSE = [(0, 1, 0.0, 100.0), (0, 2, 0.0, 100.0), (0, 3, 0.0, 100.0),
         (1, 2, 0.0, 100.0), (2, 3, 0.0, 100.0), (1, 3, 0.0, 100.0)]   # holder 0 + a dense clique
FRAGMENTED = [(0, 1, 0.0, 0.5), (0, 2, 1.0, 1.5), (0, 3, 2.0, 2.5)]    # holder visits 3 disjoint pockets


def test_unit_broken_anchored_equal_D_static_dense():
    for mode in ("broken", "anchored"):
        r = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode=mode)
        assert r["distinct_acceptors"] == 3
        assert r["slots_per_token"] == 3.0      # ~D: every distinct acceptor grants a slot


def test_unit_gossip_collapses_static_dense():
    r = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode="gossip")
    assert r["distinct_acceptors"] == 3
    assert r["slots_per_token"] == 1.0          # the mint leaks; the front reaches the rest -> residual 1


def test_unit_gossip_fragmented_leaks_fully():
    """The §9.3 fragmented case: nf NEVER reaches a disconnected pocket, so gossip leaks every spend
    (residual unbounded by gossip — bounded only by Q)."""
    r = tok.slots_for_token(FRAGMENTED, holder=0, t0=0.0, mode="gossip")
    assert r["slots_per_token"] == 3.0          # equals broken: no rejection possible


def test_unit_remeet_is_not_a_new_slot():
    """A re-met acceptor is NOT a new distinct-acceptor slot (per-(token, acceptor) accounting)."""
    eps = [(0, 1, 0.0, 1.0), (0, 1, 5.0, 6.0), (0, 2, 2.0, 3.0)]      # 0 meets 1 twice, 2 once
    r = tok.slots_for_token(eps, holder=0, t0=0.0, mode="broken")
    assert r["distinct_acceptors"] == 2                                # {1, 2}, not 3


def test_unit_phy_quota_bounds_slots_per_phy_many_tokens():
    """Per-PHY Q bounds slots/PHY-session even when many tokens are presented (§9.5 backstop)."""
    no_q = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode="broken", n_tokens=50)
    with_q = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode="broken", phy_session_quota=3, n_tokens=50)
    assert no_q["max_slots_per_phy"] == 50                             # unbounded: one session leaks all
    assert with_q["max_slots_per_phy"] == 3                            # clamped to Q


def test_unit_gossip_delay_lets_holder_outrun_front():
    """A per-hop gossip delay lets a spend beat the front: with enough delay even a connected graph
    leaks more than the zero-delay case."""
    line = [(0, 1, 0.0, 0.4), (1, 2, 0.4, 0.8), (0, 2, 1.0, 1.4)]     # 0->1->2 path, then 0 meets 2
    fast = tok.slots_for_token(line, holder=0, t0=0.0, mode="gossip", gossip_delay=0.0)
    slow = tok.slots_for_token(line, holder=0, t0=0.0, mode="gossip", gossip_delay=5.0)
    assert fast["slots_per_token"] == 1.0                              # front reaches 2 before t=1 -> reject
    assert slow["slots_per_token"] == 2.0                              # delayed front misses -> 2 also leaks


def test_unit_forward_infection_excludes_holder():
    """The holder never relays the seen-nf front (worst case): a path that only connects via the
    holder must NOT carry nf."""
    # 1 and 2 connect ONLY through holder 0; if 0 relayed, 2 would learn nf from 1 via 0.
    eps = [(0, 1, 0.0, 1.0), (0, 2, 2.0, 3.0)]
    inf = tok.forward_infection(eps, {1: 0.0}, exclude={0})
    assert 2 not in inf                                                # holder did not carry nf to 2


# ------------------------------------------------------------------------------------------------
# Scenario: the spec §4 headline on a real engine run
# ------------------------------------------------------------------------------------------------
def test_scenario_static_dense_broken_anchored_D_gossip_collapses():
    """STATIC dense holder: broken ~ anchored ~ D >> gossip ~ 1 (the win is the gossip, §9.3)."""
    cfg = sweep_cfg()
    b = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="broken", holder="static")[0]
    a = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="anchored", holder="static")[0]
    g = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="gossip", holder="static")[0]
    assert b["slots_per_token_mean"] == a["slots_per_token_mean"]      # anchored == broken (static)
    assert b["slots_per_token_mean"] >= 0.99 * b["D_mean"] >= 5.0      # broken ~ D, and D is large
    assert g["slots_per_token_mean"] <= 1.5                            # gossip collapses to ~1
    assert b["slots_per_token_mean"] >= 3.0 * g["slots_per_token_mean"]  # big amplification


def test_scenario_mobile_leaks_more_than_static_under_gossip_delay():
    """The §3 worst case: a MOBILE holder outruns the gossip front, leaking strictly more than a
    STATIC one. A per-hop gossip_delay makes the effect robust (deterministic)."""
    cfg = sweep_cfg()
    s = token_rate_limit_sweep(cfg, [5.0], reps=2, mode="gossip", holder="static", gossip_delay=2.0)[0]
    m = token_rate_limit_sweep(cfg, [5.0], reps=2, mode="gossip", holder="mobile", gossip_delay=2.0)[0]
    assert m["residual_mean"] > s["residual_mean"], \
        f"mobile did not leak more: mobile={m['residual_mean']} static={s['residual_mean']}"


def test_scenario_residual_grows_as_venue_fragments():
    """The epidemic residual grows as the venue fragments (lower density -> more disconnected pockets
    a mobile holder can reach before nf arrives). Compared at a per-hop delay so the trend is clear."""
    cfg = sweep_cfg(width=120.0, height=120.0, speed_min=6.0, speed_max=6.0, measure_window=30.0)
    lo = token_rate_limit_sweep(cfg, [2.0], reps=2, mode="gossip", holder="mobile", gossip_delay=1.0)[0]
    hi = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="gossip", holder="mobile", gossip_delay=1.0)[0]
    # normalize by D so this is a residual-FRACTION trend, not just a D trend: a sparser venue leaks a
    # larger SHARE of its spends before nf arrives (giant component is smaller -> more unreachable).
    assert lo["giant_mean"] < hi["giant_mean"]                         # density 2 IS more fragmented
    assert lo["residual_mean"] / max(1.0, lo["D_mean"]) > hi["residual_mean"] / max(1.0, hi["D_mean"])


def test_scenario_phy_quota_bounds_slots_per_phy():
    """Q bounds max slots/PHY-session in EVERY regime even under many tokens (§9.5)."""
    cfg = sweep_cfg()
    for mode in ("broken", "anchored", "gossip"):
        unb = token_rate_limit_sweep(cfg, [8.0], reps=2, mode=mode, holder="static", Q=0, n_tokens=40)[0]
        cap = token_rate_limit_sweep(cfg, [8.0], reps=2, mode=mode, holder="static", Q=4, n_tokens=40)[0]
        assert unb["max_slots_per_phy_mean"] == 40.0                   # unbounded leaks all tokens
        assert cap["max_slots_per_phy_mean"] == 4.0                    # Q clamps it


def test_scenario_deterministic_same_seed():
    cfg = sweep_cfg()
    r1 = token_rate_limit_sweep(cfg, [6.0, 8.0], reps=2, mode="gossip", holder="mobile", gossip_delay=1.0)
    r2 = token_rate_limit_sweep(cfg, [6.0, 8.0], reps=2, mode="gossip", holder="mobile", gossip_delay=1.0)
    assert r1 == r2


def test_scenario_broken_must_demonstrate_gate():
    """Pre-registered density-honest gate: BROKEN slots/token >= TOKEN_BROKEN_FRACTION * realized D
    (not a bare '>1'). Else the 'fix helps' claim is vacuous."""
    cfg = sweep_cfg()
    rows = token_rate_limit_sweep(cfg, [6.0, 8.0], reps=2, mode="broken", holder="static")
    for r in rows:
        assert r["broken_gate_ok"] is True
        assert r["slots_per_token_mean"] >= TOKEN_BROKEN_FRACTION * r["D_mean"]


def test_scenario_amplification_headline():
    """The headline: amplification = slots/token(broken) / slots/token(gossip), with the denominator
    NOT hard-clamped to 1, and anchored shown ~ broken (the win is the gossip step)."""
    out = token_amplification(sweep_cfg(), [8.0], reps=2, holder="static")
    assert out["broken_gate_ok"] is True
    amp = out["amplification"][0]
    assert amp["broken"] == amp["anchored"]                            # anchored == broken (static)
    assert amp["amplification"] >= 3.0                                 # broken >> gossip
    assert out["scope_tag"].startswith("[TOKEN RATE-LIMIT")


def test_token_csv_fields_tag_and_manifest():
    """CSV: the scope/honesty tag travels as a leading comment AND a per-row column; the full param
    manifest (incl. the three token knobs) travels per row; one row per density."""
    cfg = replace(sweep_cfg(), token_rate_limit_mode="gossip", phy_session_quota=4, gossip_delay=1.0)
    rows = token_rate_limit_sweep(cfg, [6.0], reps=1, mode="gossip", holder="static")
    s = token_to_csv_string(rows, cfg.manifest(), TOKEN_SCOPE_TAG)
    lines = s.splitlines()
    assert lines[0].startswith("#") and "TOKEN RATE-LIMIT" in lines[0]  # tag as a comment
    header = lines[1]
    for fld in TOKEN_FIELDS:
        assert fld in header
    assert "scope_tag" in header                                        # tag also a column
    assert "param_token_rate_limit_mode" in header and "param_phy_session_quota" in header
    assert "param_gossip_delay" in header
    assert len(lines) == 1 + 1 + 1                                      # comment + header + 1 density row
