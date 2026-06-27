"""P1 set-reconciliation cost model (spec §3): a FLAT, density-scheduled airtime floor billed per
funded contact-episode, INDEPENDENT of the symmetric difference and exact set sizes. Default OFF
(recon_cell_bytes=0) ⇒ bit-identical to the pre-P1 engine (no new branch, no new RNG draw)."""
import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import run_one, density_to_n, mean_ci, _seed_for
from soup_sim.mobility import Mobility
from soup_sim.engine import Engine
from soup_sim.budget import AirtimeBudget
from soup_sim.buffer import NodeBuffer
from soup_sim.blob import Blob

BIG = 10 ** 9


# TINY airtime fixture (mirrors tests/test_scenario_airtime.py::tiny — fast; engine is super-linear in crowd).
def tiny():
    return Config(n=0, width=30.0, height=30.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=15.0, buffer_cap=30, throughput_ideal=8e3,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=4.0, measure_window=8.0,
                  drain=0.0, n_messages=8, seen_margin=10.0, master_seed=7,
                  airtime_model="collision", beta=0.15, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)


def _at_density(cfg, d):
    n = max(2, density_to_n(d, cfg.width, cfg.height, cfg.radius))
    return replace(cfg, n=n)


def test_recon_off_bit_identical():
    """Recon fields at their defaults must be byte-for-byte identical to the same run with the fields
    never set — the off path takes NO new branch and makes NO new RNG draw."""
    base = _at_density(tiny(), 6.0)
    explicit_off = replace(base, recon_cell_bytes=0.0, recon_c0=0.0, recon_k=0.0)
    r_default = run_one(base)
    r_off = run_one(explicit_off)
    for key in ("circulated_per_min", "served_blobs", "offered_blobs", "transmissions",
                "delivery_ratio", "utilization", "utilization_vs_offered", "t50",
                "setup_starved_blobs", "quantization_blobs", "contention_blobs"):
        # EXACT equality (not approx) — the off path must be bit-identical.
        assert r_default[key] == r_off[key], f"recon-OFF changed {key}: {r_default[key]} != {r_off[key]}"
    assert r_default["recon_capped_episodes"] == 0 == r_off["recon_capped_episodes"]


def _multi_rep_circ(base_cfg, d, reps):
    """Per-rep circulated_per_min at density d, mirroring scenario._airtime_arm seeding."""
    n = max(2, density_to_n(d, base_cfg.width, base_cfg.height, base_cfg.radius))
    out = []
    for rep in range(reps):
        cfg = replace(base_cfg, n=n, master_seed=_seed_for(base_cfg.master_seed, 0, rep))
        out.append(run_one(cfg)["circulated_per_min"])
    return out


def _multi_rep_served(base_cfg, d, reps):
    n = max(2, density_to_n(d, base_cfg.width, base_cfg.height, base_cfg.radius))
    total = 0
    for rep in range(reps):
        cfg = replace(base_cfg, n=n, master_seed=_seed_for(base_cfg.master_seed, 0, rep))
        total += run_one(cfg)["served_blobs"]
    return total


def test_recon_monotonicity_served_blobs_exact():
    """The honest invariant (spec §4): total reconciled novel transfers served_blobs(on) <= served_blobs(off)
    by CONSTRUCTION — recon only ever consumes airtime / caps transfers, never frees them. This is the
    EXACT monotone quantity (single-rep windowed circ/min is NOT monotone: recon shifts transfer timing,
    so a transfer can cross the measurement-window edge and jitter one rep up)."""
    off = tiny()
    on = replace(off, recon_cell_bytes=8.0, recon_c0=2.0, recon_k=0.5)
    saw_strict = False
    for d in (3.0, 6.0, 9.0):
        s_off = _multi_rep_served(off, d, reps=8)
        s_on = _multi_rep_served(on, d, reps=8)
        assert s_on <= s_off, f"served_blobs ON > OFF at density {d}: on={s_on} off={s_off}"
        saw_strict |= s_on < s_off
    assert saw_strict, "vacuous: recon ON never reduced total served_blobs at any density"


def test_recon_monotonicity_circ_per_min_within_ci_multirep():
    """Multi-rep circ/min(on) <= circ/min(off) within CI at each density (the spec §4 gate stated on the
    AGGREGATE, not a single fragile rep). Uses reps=8 and the Student-t CI helper the scenario uses."""
    off = tiny()
    on = replace(off, recon_cell_bytes=8.0, recon_c0=2.0, recon_k=0.5)
    for d in (3.0, 6.0, 9.0):
        c_off = _multi_rep_circ(off, d, reps=8)
        c_on = _multi_rep_circ(on, d, reps=8)
        m_off, lo_off, _ = mean_ci(c_off, clamp01=False)
        m_on, _, hi_on = mean_ci(c_on, clamp01=False)
        # ON mean must not exceed OFF mean beyond the OFF lower-CI slack: on_mean <= off_mean within CI.
        assert m_on <= m_off + (m_off - lo_off) + 1e-9, \
            f"circ/min ON above OFF beyond CI at density {d}: on={m_on} off={m_off} off_lo={lo_off}"


def test_recon_saturated_flat_floor_bites():
    """Non-vacuity for the FLAT FLOOR specifically (not the cap): in a SATURATED two-node contact
    (airtime fully consumed), the flat S(n) schedule strictly reduces served_blobs even though the cap
    never binds (S large vs served), proving the floor alone competes for airtime. Utilization stays <=1."""
    off = _two_node_cfg(throughput_ideal=2000.0, t_setup=0.0)
    on = replace(off, recon_cell_bytes=200.0, recon_c0=10.0, recon_k=0.0)  # S=10 cells; cap won't bind
    eng_off = _two_node_engine(off, blobs=30, run=3.0)
    eng_on = _two_node_engine(on, blobs=30, run=3.0)
    assert eng_off.charged_airtime > 0 and eng_off.served_blobs > 0       # OFF saturates and circulates
    assert eng_on.served_blobs < eng_off.served_blobs                     # the flat floor ate airtime
    assert eng_on.recon_capped_episodes == 0                              # the CAP did not bind (floor only)
    assert eng_on.charged_airtime <= eng_on.available_contact_time + 1e-9  # utilization stays <= 1


def test_recon_billing_dt_invariant():
    """The recon-debt is amortized across funded steps like setup_debt, so charged_airtime is
    dt-INVARIANT (mirroring the OFF dt-invariance the module docstring guarantees). A lazy 'bill it all
    on the first funded step' latch would make charged_airtime vary with dt when the first step is short."""
    base = _two_node_cfg(recon_cell_bytes=8.0, recon_c0=5.0, recon_k=1.0,
                         throughput_ideal=4e3, t_setup=0.1)
    charged = {}
    for dt in (0.05, 0.1, 1.0):
        eng = _two_node_engine(replace(base, dt=dt), blobs=8, run=6.0)
        charged[dt] = eng.charged_airtime
    vals = list(charged.values())
    assert max(vals) - min(vals) < 1e-6, f"charged_airtime not dt-invariant: {charged}"


def test_recon_on_deterministic():
    """Same seed -> identical circ/min and served across two recon-ON runs (no new variance source)."""
    cfg = replace(_at_density(tiny(), 6.0), recon_cell_bytes=8.0, recon_c0=2.0, recon_k=0.5)
    r1 = run_one(cfg)
    r2 = run_one(cfg)
    assert r1["circulated_per_min"] == r2["circulated_per_min"]
    assert r1["served_blobs"] == r2["served_blobs"]
    assert r1["utilization"] == r2["utilization"]
    assert r1["recon_capped_episodes"] == r2["recon_capped_episodes"]


def test_recon_degenerate_schedule_rejected():
    """Footgun guard: recon_cell_bytes>0 with c0=0 AND k=0 gives S(n)=0 -> cap=0 -> circulation silently
    zeroed at ~zero airtime cost. Config.validate() must reject it; a real schedule (c0>0 OR k>0) is ok."""
    with pytest.raises(ValueError, match="real schedule"):
        replace(_at_density(tiny(), 6.0), recon_cell_bytes=8.0, recon_c0=0.0, recon_k=0.0).validate()
    replace(_at_density(tiny(), 6.0), recon_cell_bytes=8.0, recon_c0=1.0, recon_k=0.0).validate()  # ok
    replace(_at_density(tiny(), 6.0), recon_cell_bytes=8.0, recon_c0=0.0, recon_k=0.1).validate()  # ok


def _two_node_engine(cfg, blobs, run=10.0):
    """node0 holds `blobs` blobs, node1 holds none; one static contact for the whole run."""
    pos = np.array([[50., 50.], [55., 50.]])
    mob = Mobility("static", pos, np.zeros_like(pos), cfg.width, cfg.height, 0.0, 0.0)
    bufs = [NodeBuffer(BIG, cfg.ttl + 1e9, cfg.rng(3, i)) for i in range(2)]
    budget = AirtimeBudget(cfg.throughput_ideal, cfg.alpha, cfg.t_setup, cfg.p_fail, cfg.blob_size,
                           model=cfg.airtime_model, beta=cfg.beta, t_setup_slope=cfg.t_setup_slope,
                           n_channels=cfg.n_channels)
    eng = Engine(cfg, mob, bufs, budget, cfg.rng(1), on_deliver=lambda *_: None)
    for k in range(blobs):
        eng.inject(Blob(k, 0.0, cfg.ttl, cfg.blob_size), 0)
    eng.run_until(run)
    eng.finalize()
    return eng


def _two_node_cfg(**kw):
    d = dict(n=2, width=2000.0, height=200.0, radius=10.0, boundary="walls", mobility="static",
             speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e12, buffer_cap=BIG, throughput_ideal=8e3,
             alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=0.0, measure_window=1.0,
             drain=0.0, n_messages=0, seen_margin=1e12, master_seed=0, cs_radius_mult=1.0,
             airtime_model="linear")
    d.update(kw)
    return Config(**d)


def test_recon_billed_on_zero_blob_episode():
    """A funded contact that moves ZERO blobs (both peers already in sync) must STILL pay the recon
    floor when recon is ON — the c0 term is exactly the Δ≈0 synced-dense regime the spec targets."""
    # zero blobs to move ⇒ no transfer at all; only the recon floor should be charged.
    cfg_off = _two_node_cfg(recon_cell_bytes=0.0)
    cfg_on = replace(cfg_off, recon_cell_bytes=8.0, recon_c0=3.0, recon_k=0.0)
    eng_off = _two_node_engine(cfg_off, blobs=0)
    eng_on = _two_node_engine(cfg_on, blobs=0)
    assert eng_off.served_blobs == 0 and eng_on.served_blobs == 0       # nothing to move either way
    assert eng_off.charged_airtime == 0.0                              # OFF: a zero-blob contact bills nothing
    assert eng_on.charged_airtime > 0.0                               # ON: the flat S(n) floor is still paid
    # the charged amount equals recon_cell_bytes * S(n) / eff for the single funded episode. Two nodes in
    # range ⇒ each has degree 1 ⇒ n_contenders = 1; S(1) = c0 (k=0); eff = effective_goodput(1).
    n1 = 1
    eff = eng_on.budget.effective_goodput(n1)
    expected = cfg_on.recon_cell_bytes * eng_on._recon_cells(n1) / eff   # S(1) = c0 (k=0)
    assert abs(eng_on.charged_airtime - expected) < 1e-9


def test_recon_utilization_stays_le_one():
    """Recon airtime is billed BEFORE blob transfer and competes for the same budget; it must never
    push utilization above 1 (charged_airtime <= available_contact_time)."""
    cfg = _two_node_cfg(recon_cell_bytes=8.0, recon_c0=5.0, recon_k=1.0, t_setup=0.05)
    eng = _two_node_engine(cfg, blobs=50, run=20.0)
    assert eng.available_contact_time > 0
    assert eng.charged_airtime <= eng.available_contact_time + 1e-9


def test_recon_cap_throttles_novel_transfers():
    """The deterministic cap(ρ) throttle: with a tiny schedule, an episode reconciles at most
    floor(S(n)) novel blobs even when many are offered; the rest waits for a future contact."""
    # c0=2, k=0 ⇒ S(n)=2 ⇒ at most 2 novel blobs per episode regardless of the 20 offered.
    cfg = _two_node_cfg(recon_cell_bytes=8.0, recon_c0=2.0, recon_k=0.0,
                        throughput_ideal=1e9, t_setup=0.0)   # huge goodput ⇒ credit is not the limiter
    eng = _two_node_engine(cfg, blobs=20, run=5.0)
    assert eng.served_blobs <= 2, f"cap(ρ)=2 exceeded: served {eng.served_blobs}"
    assert eng.recon_capped_episodes >= 1                  # the cap genuinely bound this episode
