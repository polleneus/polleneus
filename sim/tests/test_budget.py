import numpy as np
from soup_sim.budget import AirtimeBudget


def test_linear_contention_reduces_per_link_goodput():
    bud = AirtimeBudget(1000, alpha=1.0, t_setup=0.0, p_fail=0.0, blob_size=100)
    assert bud.effective_goodput(9) < bud.effective_goodput(0)   # more contenders -> less per link


def test_pfail_scales_goodput_down():
    full = AirtimeBudget(1000, 0.0, 0.0, p_fail=0.0, blob_size=100).effective_goodput(0)
    half = AirtimeBudget(1000, 0.0, 0.0, p_fail=0.5, blob_size=100).effective_goodput(0)
    assert abs(half - 0.5 * full) < 1e-9


# --- PR-2: collision (ALOHA) airtime model -----------------------------------
def test_collision_aggregate_turns_over_linear_plateaus():
    # per-link goodput is monotone for BOTH models; the TURN-OVER is the SYSTEM aggregate n*goodput.
    ns = np.arange(1, 100)
    coll = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="collision", beta=0.08, n_channels=3)
    lin = AirtimeBudget(1e5, 1.0, 0.0, 0.0, 1.0, model="linear")
    agg_c = np.array([n * coll.effective_goodput(int(n)) for n in ns])
    agg_l = np.array([n * lin.effective_goodput(int(n)) for n in ns])
    assert 0 < agg_c.argmax() < len(ns) - 1          # collision: interior maximum (turns over)
    assert agg_l.argmax() == len(ns) - 1             # linear: monotone up to plateau
    assert agg_c.max() > 1.5 * agg_c[-1]             # clear turn-over margin
    assert abs(ns[agg_c.argmax()] - 3 / 0.08) < 5    # near analytic n* = n_channels/beta = 37.5


def test_per_link_goodput_monotone_both_models():
    for b in (AirtimeBudget(1e5, 1.0, 0, 0, 1.0, model="collision", beta=0.08, n_channels=3),
              AirtimeBudget(1e5, 1.0, 0, 0, 1.0, model="linear")):
        g = [b.effective_goodput(int(n)) for n in range(1, 80)]
        assert np.all(np.diff(g) <= 1e-9)


def test_density_dependent_setup_and_charged_airtime():
    b = AirtimeBudget(100.0, 0.0, t_setup=0.5, p_fail=0.0, blob_size=10.0,
                      model="linear", t_setup_slope=0.05)
    assert b.t_setup_at(0) == 0.5 and b.t_setup_at(40) == 0.5 + 0.05 * 40
    assert abs(b.charged_airtime(3, 0) - (0.5 + 3 * 10.0 / 100.0)) < 1e-9
    assert b.charged_airtime(0, 0) == 0.0


def test_run_one_uses_configured_model():
    from soup_sim.config import Config
    from soup_sim.scenario import run_one
    base = dict(n=20, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
                speed_min=2.0, speed_max=2.0, dt=0.5, ttl=30.0, buffer_cap=50, throughput_ideal=1e4,
                alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=10.0, measure_window=20.0,
                drain=0.0, n_messages=10, seen_margin=30.0, master_seed=1,
                airtime_model="collision", beta=0.2, t_setup_slope=0.0, n_channels=3, cs_radius_mult=1.0)
    r = run_one(Config(**base))                       # must run without error under collision
    assert r["manifest"]["airtime_model"] == "collision"
