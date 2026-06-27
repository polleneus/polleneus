"""P2 PR-1 — token rate-limit harness (spec §3/§4). A DEFAULT-INERT post-hoc overlay over the
recorded contact graph (NOT in the engine), so mode='off' is bit-identical to the prior engine.

Design-review round 2: the rate-limit is a RACE between the seen-nf gossip front (gossip_delay) and
the holder's SERIALIZED BLE-handshake spend rate (token_spend_interval). slots/token(gossip) spans
~1 (gossip outpaces spends — rate-limit works) to ~D (a BURST holder defeats the gossip — NO rate-
limit). gossip_delay=0 is the UNPHYSICAL instantaneous-front edge and is excluded from the headline.

Tests (all TINY/bounded — the engine is super-linear in crowd size):
  - config: the four fields default OFF and validate;
  - OFF bit-identity: run_one with token fields at defaults == run_one without them — ALL keys, exact;
  - overlay unit logic on hand-built episode graphs incl. the spend-serialization RACE (1 <-> D);
  - scenario: the race curve spans 1<->D; broken/anchored == D (provable, not emergent); mobile EVADES
    the front more than static (residual relative to the front); Q is an exact min(n_tokens,Q) bound;
    determinism; the FALSIFIABLE must-demonstrate gate (passes when wired right, would fail otherwise).
"""
import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import (run_one, token_rate_limit_sweep, token_race_sweep,
                               token_amplification, token_demonstrate_gate,
                               TOKEN_BROKEN_FRACTION, TOKEN_GOSSIP_WIN_FRACTION, TOKEN_SCOPE_TAG,
                               density_to_n, _seed_for)
from soup_sim.report import (token_to_csv_string, TOKEN_FIELDS,
                             token_race_to_csv_string, TOKEN_RACE_FIELDS)
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
    assert c.token_rate_limit_mode == "off" and c.phy_session_quota == 0
    assert c.gossip_delay == 0.0 and c.token_spend_interval == 0.0
    c.validate()                                                       # ok at defaults
    for m in ("off", "broken", "anchored", "gossip"):
        base_cfg(token_rate_limit_mode=m).validate()                  # all modes valid
    base_cfg(token_spend_interval=2.0).validate()                     # ok when ON
    with pytest.raises(ValueError, match="token_rate_limit_mode"):
        base_cfg(token_rate_limit_mode="bogus").validate()
    with pytest.raises(ValueError, match="phy_session_quota"):
        base_cfg(phy_session_quota=-1).validate()
    with pytest.raises(ValueError, match="gossip_delay"):
        base_cfg(gossip_delay=-1.0).validate()
    with pytest.raises(ValueError, match="token_spend_interval"):
        base_cfg(token_spend_interval=-1.0).validate()


def test_token_off_bit_identical():
    """token fields at defaults must be byte-for-byte identical to a run with them never set: the
    overlay lives OUTSIDE the engine, so run_one is unchanged. EXACT equality of EVERY run_one key
    (incl. the manifest — defaults make the manifests identical too)."""
    plain = base_cfg(mobility="rwp", speed_min=1.0, speed_max=1.0)
    explicit_off = replace(plain, token_rate_limit_mode="off", phy_session_quota=0,
                           gossip_delay=0.0, token_spend_interval=0.0)
    r0, r1 = run_one(plain), run_one(explicit_off)
    assert set(r0) == set(r1)
    for key in r0:                                                     # ALL keys (was 11 of ~20)
        a, b = r0[key], r1[key]
        if isinstance(a, float) and np.isnan(a):
            assert isinstance(b, float) and np.isnan(b), f"token-OFF changed {key}"
        else:
            assert a == b, f"token-OFF changed {key}: {a!r} != {b!r}"


# ------------------------------------------------------------------------------------------------
# Overlay unit logic (hand-built episode graphs — no engine, fully deterministic)
# ------------------------------------------------------------------------------------------------
DENSE = [(0, 1, 0.0, 100.0), (0, 2, 0.0, 100.0), (0, 3, 0.0, 100.0),
         (1, 2, 0.0, 100.0), (2, 3, 0.0, 100.0), (1, 3, 0.0, 100.0)]   # holder 0 + a dense clique
FRAGMENTED = [(0, 1, 0.0, 0.5), (0, 2, 1.0, 1.5), (0, 3, 2.0, 2.5)]    # holder visits 3 disjoint pockets


def test_unit_broken_anchored_equal_D_provable():
    """broken == anchored == D is PROVABLE by construction under distinct-acceptor accounting (each
    distinct acceptor is met once with a fresh local seen-set), NOT an emergent measurement — and it
    is independent of the spend interval (serialization changes spend TIMES, not the count)."""
    for mode in ("broken", "anchored"):
        for si in (0.0, 7.0):
            r = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode=mode, token_spend_interval=si)
            assert r["distinct_acceptors"] == 3 and r["slots_per_token"] == 3.0


def test_unit_spend_serialization_spaces_spends():
    """The core fix: spend_time[k] = max(contact_time[k], spend_time[k-1] + interval). interval=0 is
    the instantaneous burst (all ~t0); interval>0 spreads spends out."""
    assert tok._spend_events(DENSE, 0, 0.0, 0.0) == [(1, 0.0), (2, 0.0), (3, 0.0)]      # burst
    assert tok._spend_events(DENSE, 0, 0.0, 5.0) == [(1, 0.0), (2, 5.0), (3, 10.0)]     # serialized


def test_unit_gossip_race_burst_to_serialized():
    """THE RACE (spec §3/§4) on a static dense clique at a PHYSICAL gossip_delay>0:
       - BURST (interval=0): all spends fire at ~t0, gossip can't catch up -> slots/token = D (no limit);
       - SERIALIZED faster than gossip (interval >> delay): gossip wins -> slots/token = 1."""
    gd = 0.5
    burst = tok.slots_for_token(DENSE, 0, 0.0, "gossip", gossip_delay=gd, token_spend_interval=0.0)
    serial = tok.slots_for_token(DENSE, 0, 0.0, "gossip", gossip_delay=gd, token_spend_interval=10.0)
    assert burst["slots_per_token"] == 3.0       # burst defeats gossip -> D
    assert serial["slots_per_token"] == 1.0      # gossip outpaces spends -> 1


def test_unit_gossip_delay_zero_is_unphysical_always_one():
    """gossip_delay=0 is the unphysical instantaneous front: it collapses to ~1 even for a BURST
    holder — exactly why it must be excluded from the headline."""
    r = tok.slots_for_token(DENSE, 0, 0.0, "gossip", gossip_delay=0.0, token_spend_interval=0.0)
    assert r["slots_per_token"] == 1.0


def test_unit_gossip_fragmented_leaks_fully():
    """The §9.3 fragmented case: nf NEVER reaches a disconnected pocket, so gossip leaks every spend
    (residual unbounded by gossip — bounded only by Q), independent of the spend rate."""
    r = tok.slots_for_token(FRAGMENTED, holder=0, t0=0.0, mode="gossip",
                            gossip_delay=0.5, token_spend_interval=0.01)
    assert r["slots_per_token"] == 3.0          # equals broken: no rejection possible


def test_unit_remeet_is_not_a_new_slot():
    """A re-met acceptor is NOT a new distinct-acceptor slot (per-(token, acceptor) accounting)."""
    eps = [(0, 1, 0.0, 1.0), (0, 1, 5.0, 6.0), (0, 2, 2.0, 3.0)]      # 0 meets 1 twice, 2 once
    r = tok.slots_for_token(eps, holder=0, t0=0.0, mode="broken")
    assert r["distinct_acceptors"] == 2                                # {1, 2}, not 3


def test_unit_phy_quota_is_exact_min_bound():
    """Per-PHY Q is an EXACT-BY-CONSTRUCTION bound min(n_tokens, Q), not an emergent measurement."""
    no_q = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode="broken", n_tokens=50)
    cap = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode="broken", phy_session_quota=3, n_tokens=50)
    over = tok.slots_for_token(DENSE, holder=0, t0=0.0, mode="broken", phy_session_quota=99, n_tokens=50)
    assert no_q["max_slots_per_phy"] == 50                             # unbounded: one session leaks all
    assert cap["max_slots_per_phy"] == 3                               # min(50, 3) = 3
    assert over["max_slots_per_phy"] == 50                             # min(50, 99) = 50 (Q above demand)


def test_unit_forward_infection_excludes_holder():
    """The holder never relays the seen-nf front (worst case): a path that only connects via the
    holder must NOT carry nf."""
    eps = [(0, 1, 0.0, 1.0), (0, 2, 2.0, 3.0)]                         # 1,2 connect ONLY through holder 0
    inf = tok.forward_infection(eps, {1: 0.0}, exclude={0})
    assert 2 not in inf                                                # holder did not carry nf to 2


# ------------------------------------------------------------------------------------------------
# Scenario: the spec §4 RACE on a real engine run
# ------------------------------------------------------------------------------------------------
def test_scenario_race_curve_spans_one_to_D():
    """THE HEADLINE: slots/token(gossip) spans ~1 (gossip wins) to ~D (burst defeats gossip), as a
    function of the gossip-rate / spend-rate ratio. Every row carries gossip_delay AND
    token_spend_interval. gossip_delay=0 is excluded from these (physical) points."""
    cfg = sweep_cfg()
    pts = [(0.5, 10.0),   # serialized slow, gossip wins -> ~1
           (0.5, 0.0)]    # burst, gossip loses -> ~D
    out = token_race_sweep(cfg, 8.0, reps=2, race_points=pts, holder="static")
    D = out["broken"]
    assert D >= 5.0                                                    # the attack is real (D large)
    wins = next(r for r in out["rows"] if r["token_spend_interval"] == 10.0)
    burst = next(r for r in out["rows"] if r["token_spend_interval"] == 0.0)
    assert wins["slots_per_token_mean"] <= 1.5                         # gossip wins -> ~1
    assert wins["gossip_wins"] is True
    assert burst["slots_per_token_mean"] >= TOKEN_BROKEN_FRACTION * D  # burst -> ~D (NO rate-limit)
    assert burst["gossip_wins"] is False
    for r in out["rows"]:                                              # every row carries both knobs
        assert "gossip_delay" in r and "token_spend_interval" in r


def test_scenario_headline_excludes_delay_zero():
    """The headline functions REJECT gossip_delay=0 (unphysical instantaneous front, spec §4)."""
    cfg = sweep_cfg()
    with pytest.raises(ValueError, match="gossip_delay"):
        token_amplification(cfg, 8.0, reps=1, gossip_delay=0.0, token_spend_interval=5.0)
    with pytest.raises(ValueError, match="gossip_delay"):
        token_demonstrate_gate(cfg, 8.0, reps=1, gossip_delay=0.0, token_spend_interval=5.0)


def test_scenario_broken_anchored_equal_D_on_engine():
    """On a real static-dense engine run, broken == anchored == D (provable, not emergent)."""
    cfg = sweep_cfg()
    b = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="broken", holder="static")[0]
    a = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="anchored", holder="static")[0]
    assert b["slots_per_token_mean"] == a["slots_per_token_mean"]
    assert b["broken_at_D"] is True
    assert b["slots_per_token_mean"] >= TOKEN_BROKEN_FRACTION * b["D_mean"] >= 5.0


def test_scenario_mobile_and_static_are_worst_case_on_DIFFERENT_axes():
    """Two distinct worst cases, measured — NOT the naive "mobile always evades more" (which is FALSE;
    verified across operating points). At a serialized spend rate + per-hop delay:
      - the MOBILE holder leaks a larger ABSOLUTE residual (it meets far more distinct acceptors D, so
        its total slots leaked is much higher) — the worst case for TOTAL leak;
      - the STATIC holder leaks a larger residual FRACTION (its few co-present acceptors are spent
        before the front catches them; the mobile holder spreads spends across a long trajectory so
        gossip keeps up fractionally) — the worst case for the EVASION RATE.
    The honest message: mobility raises absolute leak but not the fraction; a static burst (separate
    test) is what defeats the gossip wholesale."""
    cfg = sweep_cfg(width=120.0, height=120.0, radius=10.0, speed_min=6.0, speed_max=6.0, dt=0.4,
                    measure_window=30.0)  # CFL: 6*0.4=2.4 <= radius/4=2.5
    op = dict(gossip_delay=1.0, token_spend_interval=2.0)
    s = token_rate_limit_sweep(cfg, [3.0], reps=2, mode="gossip", holder="static", **op)[0]
    m = token_rate_limit_sweep(cfg, [3.0], reps=2, mode="gossip", holder="mobile", **op)[0]
    s_frac = s["residual_mean"] / max(1.0, s["D_mean"])
    m_frac = m["residual_mean"] / max(1.0, m["D_mean"])
    assert m["D_mean"] > s["D_mean"], f"mobile should meet more acceptors: m={m['D_mean']} s={s['D_mean']}"
    assert m["residual_mean"] > s["residual_mean"], \
        f"mobile should leak larger ABSOLUTE residual: m={m['residual_mean']} s={s['residual_mean']}"
    assert s_frac > m_frac, \
        f"static should leak larger FRACTION (mobile does NOT evade more): s={s_frac} m={m_frac}"


def test_scenario_phy_quota_bounds_slots_per_phy():
    """Q is an exact min(n_tokens, Q) bound on max slots/PHY-session in EVERY regime (§9.5)."""
    cfg = sweep_cfg()
    for mode in ("broken", "anchored", "gossip"):
        unb = token_rate_limit_sweep(cfg, [8.0], reps=2, mode=mode, holder="static", Q=0, n_tokens=40)[0]
        cap = token_rate_limit_sweep(cfg, [8.0], reps=2, mode=mode, holder="static", Q=4, n_tokens=40)[0]
        assert unb["max_slots_per_phy_mean"] == 40.0                   # unbounded leaks all tokens
        assert cap["max_slots_per_phy_mean"] == 4.0                    # min(40, 4) = 4


def test_scenario_deterministic_same_seed():
    cfg = sweep_cfg()
    kw = dict(mode="gossip", holder="mobile", gossip_delay=1.0, token_spend_interval=2.0)
    r1 = token_rate_limit_sweep(cfg, [6.0, 8.0], reps=2, **kw)
    r2 = token_rate_limit_sweep(cfg, [6.0, 8.0], reps=2, **kw)
    assert r1 == r2


def test_scenario_demonstrate_gate_falsifiable_and_passes():
    """The FALSIFIABLE must-demonstrate gate (spec §4): at a physical (gossip_delay>0, interval>0)
    point it requires BROKEN~D AND gossip credits a reduction WHEN SERIALIZED AND gossip does NOT
    reduce in the BURST regime. A correctly-wired model passes all three; a mis-wired one (gossip
    always 1, or gossip ignoring spend times) fails (2) or (3) — so the gate can actually FAIL."""
    cfg = sweep_cfg()
    v = token_demonstrate_gate(cfg, 8.0, reps=2, gossip_delay=0.5, token_spend_interval=10.0,
                               holder="static")
    assert v["broken_is_D"] is True                                   # (1) the attack is real
    assert v["gossip_wins_when_serialized"] is True                   # (2) gossip credits a reduction
    assert v["gossip_loses_when_burst"] is True                       # (3) burst holder defeats gossip
    assert v["ok"] is True
    # the gate is non-trivial: burst >> win (a tautological gate could not separate these).
    assert v["gossip_burst_slots"] > 2.0 * v["gossip_win_slots"]


def test_scenario_demonstrate_gate_can_fail_on_miswire():
    """Prove the gate is NOT a tautology: feeding it a contradictory expectation (a model where gossip
    'wins' even in the burst regime) would violate sub-check (3). We assert the real model does NOT
    satisfy that — i.e. the burst arm genuinely leaks ~D, so a 'gossip always wins' wiring would FAIL
    sub-check (3). This pins the falsifiability directly."""
    cfg = sweep_cfg()
    burst = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="gossip", holder="static",
                                   gossip_delay=0.5, token_spend_interval=0.0)[0]
    broken = token_rate_limit_sweep(cfg, [8.0], reps=2, mode="broken", holder="static")[0]
    # If the model were mis-wired to always collapse gossip to ~1, this would be False (and the gate's
    # sub-check (3) would fail). The correct model leaks ~D in the burst regime, so it is True.
    assert burst["slots_per_token_mean"] >= TOKEN_BROKEN_FRACTION * broken["slots_per_token_mean"]


def test_scenario_amplification_headline():
    """The headline amplification = slots/token(broken) / slots/token(gossip) at a PHYSICAL operating
    point (gossip_delay>0), carrying BOTH knobs; anchored == broken shows the win is the gossip step;
    the denominator is whatever the gossip leaves (NOT clamped to 1)."""
    out = token_amplification(sweep_cfg(), 8.0, reps=2, gossip_delay=0.5, token_spend_interval=10.0,
                              holder="static")
    assert out["gossip_delay"] == 0.5 and out["token_spend_interval"] == 10.0  # both carried
    assert out["broken"] == out["anchored"]                            # anchored == broken (static)
    assert out["amplification"] >= 3.0                                 # broken >> gossip (gossip wins)
    assert out["scope_tag"].startswith("[TOKEN RATE-LIMIT")


# ------------------------------------------------------------------------------------------------
# CSV reporters
# ------------------------------------------------------------------------------------------------
def test_token_csv_fields_tag_and_manifest():
    """CSV: the scope tag travels as a comment AND a per-row column; gossip_delay + token_spend_interval
    are on every row; the full param manifest (incl. all four token knobs) travels per row."""
    cfg = replace(sweep_cfg(), token_rate_limit_mode="gossip", phy_session_quota=4,
                  gossip_delay=1.0, token_spend_interval=2.0)
    rows = token_rate_limit_sweep(cfg, [6.0], reps=1, mode="gossip", holder="static",
                                  gossip_delay=1.0, token_spend_interval=2.0)
    s = token_to_csv_string(rows, cfg.manifest(), TOKEN_SCOPE_TAG)
    lines = s.splitlines()
    assert lines[0].startswith("#") and "TOKEN RATE-LIMIT" in lines[0]
    header = lines[1]
    for fld in TOKEN_FIELDS:
        assert fld in header
    assert "scope_tag" in header and "gossip_delay" in header and "token_spend_interval" in header
    assert "param_token_spend_interval" in header and "param_phy_session_quota" in header
    assert len(lines) == 1 + 1 + 1                                      # comment + header + 1 density row


def test_token_race_csv_fields_and_comment():
    """The race-curve CSV carries the density/n/broken(=D) reference + the scope tag as comments, and
    gossip_delay/token_spend_interval/rate_ratio on every row."""
    cfg = sweep_cfg()
    out = token_race_sweep(cfg, 8.0, reps=1, race_points=[(0.5, 10.0), (0.5, 0.0)], holder="static")
    s = token_race_to_csv_string(out, cfg.manifest(), TOKEN_SCOPE_TAG)
    lines = s.splitlines()
    assert lines[0].startswith("#") and "broken(=D)" in lines[0]
    assert lines[1].startswith("#") and "TOKEN RATE-LIMIT" in lines[1]
    header = lines[2]
    for fld in TOKEN_RACE_FIELDS:
        assert fld in header
    assert "broken_D" in header and "param_master_seed" in header
    assert len(lines) == 2 + 1 + 2                                      # 2 comments + header + 2 race rows
