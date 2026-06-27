"""P1 set-reconciliation cost model (spec §3): a FLAT, density-scheduled airtime floor billed per
funded contact-episode, INDEPENDENT of the symmetric difference and exact set sizes. Default OFF
(recon_cell_bytes=0) ⇒ bit-identical to the pre-P1 engine (no new branch, no new RNG draw)."""
import numpy as np
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import run_one, density_to_n
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


def test_recon_on_reduces_circulation():
    """Monotonicity gate (spec §4): turning recon ON can only SHRINK circulation, never grow it,
    at a couple of densities on the tiny airtime fixture. The spec's example params (cell_bytes=8,
    c0=2, k=0.5) are checked for the <= bound; a cap-binding config provides the non-vacuous strict
    reduction (in this UNSATURATED tiny arena the haircut comes from the cap(ρ) throttle — the flat
    S(ρ) floor only bites once airtime saturates, exactly as §4 anticipates)."""
    off = tiny()
    on = replace(off, recon_cell_bytes=8.0, recon_c0=2.0, recon_k=0.5)
    for d in (3.0, 6.0):
        c_off = run_one(_at_density(off, d))["circulated_per_min"]
        c_on = run_one(_at_density(on, d))["circulated_per_min"]
        assert c_on <= c_off + 1e-9, f"recon ON grew circulation at density {d}: on={c_on} off={c_off}"
    # Non-vacuity: a hard cap (S(n)=1 novel blob/episode) MUST strictly reduce circulation at both
    # densities and record capped episodes — guaranteeing the gate is testing a real effect.
    cap_on = replace(off, recon_cell_bytes=8.0, recon_c0=1.0, recon_k=0.0)
    for d in (3.0, 6.0):
        r_off = run_one(_at_density(off, d))
        r_cap = run_one(_at_density(cap_on, d))
        assert r_cap["circulated_per_min"] < r_off["circulated_per_min"] - 1e-9, \
            f"cap(ρ) did not reduce circulation at density {d}"
        assert r_cap["recon_capped_episodes"] >= 1


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
