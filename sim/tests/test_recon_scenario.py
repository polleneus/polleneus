"""P1 PR-2 re-measure: recon OFF-vs-ON compare sweep + 2-D sensitivity band (spec §4).

All tests use a TINY arena and tiny grids (the engine is super-linear in crowd size). They assert
structure + determinism of recon_compare_sweep, that the recon-OFF arm is BIT-IDENTICAL to the plain
airtime numbers, and that at a SATURATED config recon-ON mean circ/min <= OFF (the real haircut)."""
import numpy as np
import pytest
from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import (recon_compare_sweep, recon_sensitivity_band, _airtime_arm, run_one,
                               density_to_n, _seed_for)
from soup_sim.report import (recon_compare_to_csv_string, RECON_COMPARE_FIELDS,
                             recon_band_to_csv_string, RECON_BAND_FIELDS)


# TINY arena (mirrors tests/test_scenario_airtime.py::tiny) — fast; engine is super-linear in crowd.
def tiny():
    return Config(n=0, width=30.0, height=30.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=15.0, buffer_cap=30, throughput_ideal=8e3,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=4.0, measure_window=8.0,
                  drain=0.0, n_messages=8, seen_margin=10.0, master_seed=7,
                  airtime_model="collision", beta=0.15, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)


# SATURATED fixture: low throughput + high seen_margin so the contact airtime is fully consumed and
# the haircut is real (not just within reordering noise). beta low so collision doesn't dominate.
def saturated():
    return Config(n=0, width=30.0, height=30.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=30.0, buffer_cap=200, throughput_ideal=600.0,
                  alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=200.0, warmup=4.0, measure_window=12.0,
                  drain=0.0, n_messages=40, seen_margin=30.0, master_seed=7,
                  airtime_model="collision", beta=0.05, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0)


RECON_ON = dict(recon_cell_bytes=8.0, recon_c0=2.0, recon_k=0.5)


def test_recon_compare_sweep_structure_and_determinism():
    dens = [3.0, 6.0]
    out1 = recon_compare_sweep(tiny(), dens, reps=2, recon_cfg=RECON_ON)
    out2 = recon_compare_sweep(tiny(), dens, reps=2, recon_cfg=RECON_ON)
    assert len(out1) == len(dens)
    # fully deterministic: every numeric field reproduces exactly
    for a, b in zip(out1, out2):
        assert a["density"] == b["density"] and a["n"] == b["n"]
        assert a["haircut"] == b["haircut"]
        for arm in ("off", "on"):
            assert a[arm] == b[arm]
    for r in out1:
        for arm in ("off", "on"):
            keys = {"circ_mean", "circ_ci_lo", "circ_ci_hi", "served_mean", "charged_mean",
                    "util_mean", "recon_capped_episodes"}
            assert keys <= set(r[arm])
            assert r[arm]["circ_ci_lo"] <= r[arm]["circ_mean"] <= r[arm]["circ_ci_hi"] + 1e-9
            assert 0.0 <= r[arm]["util_mean"] <= 1.0 + 1e-9
        assert r["off"]["recon_capped_episodes"] == 0          # OFF can never cap
        assert "haircut" in r


def test_recon_off_arm_bit_identical_to_plain_airtime():
    """The recon-OFF arm of recon_compare_sweep must equal the plain airtime numbers EXACTLY (it
    takes no recon branch, so it is the same engine run): same per-(density,rep) seeds, same metrics."""
    dens = [3.0, 6.0]
    out = recon_compare_sweep(tiny(), dens, reps=2, recon_cfg=RECON_ON)
    air_rows, _ = _airtime_arm(tiny(), dens, reps=2)
    assert len(out) == len(air_rows)
    for r, a in zip(out, air_rows):
        # circ/min mean + CI bit-identical to the plain airtime arm (same seeds, same off engine)
        assert r["off"]["circ_mean"] == a["circulated_per_min_mean"]
        assert r["off"]["circ_ci_lo"] == a["ci_lo"] and r["off"]["circ_ci_hi"] == a["ci_hi"]
        assert r["off"]["util_mean"] == a["utilization_mean"]


def test_recon_compare_charged_airtime_strictly_higher_on_when_cap_does_not_bind():
    """When the recon schedule is paid AND the cap does NOT bind (large S(n) ⇒ the SAME blobs move
    both arms), the ON arm's mean charged_airtime > OFF — the flat floor is genuinely billed on top, so
    the free-reconciliation optimism is provably gone (spec §4/§5 core guarantee). NB: with an
    AGGRESSIVE cap that throttles transfers, total charged_airtime can go EITHER way (the cap removes
    more blob-transfer bytes than the floor adds) — that is the §4 honest caveat, so we isolate the
    floor here exactly as test_recon.py does at the engine level: ample goodput (airtime not the limiter)
    + a large schedule (cap never binds, a SMALL per-cell byte cost so the floor doesn't itself starve)."""
    base = replace(tiny(), throughput_ideal=1e7)               # ample goodput ⇒ airtime is not the limiter
    on = dict(recon_cell_bytes=1.0, recon_c0=20.0, recon_k=0.0)  # S=20 >> blobs ⇒ cap never binds; tiny floor
    out = recon_compare_sweep(base, [6.0], reps=2, recon_cfg=on)
    r = out[0]
    assert r["off"]["charged_mean"] > 0.0                       # OFF does real work to compare against
    assert r["on"]["recon_capped_episodes"] == 0               # cap did NOT bind (floor isolated)
    assert r["on"]["served_mean"] == r["off"]["served_mean"]   # same blobs move both arms
    assert r["on"]["charged_mean"] > r["off"]["charged_mean"] + 1e-9


def test_recon_compare_saturated_haircut_on_le_off():
    """At a SATURATED config, recon-ON mean circ/min <= OFF (the real haircut, spec §4). Aggressive
    cap (S(n)=1) so the throttle bites alongside the flat floor. reps>=4 so the multi-rep mean is the
    claimed quantity, not a single noisy run."""
    base = saturated()
    on = dict(recon_cell_bytes=8.0, recon_c0=1.0, recon_k=0.0)   # S(n)=1: at most 1 novel blob/episode
    out = recon_compare_sweep(base, [4.0, 6.0], reps=4, recon_cfg=on)
    for r in out:
        assert r["on"]["circ_mean"] <= r["off"]["circ_mean"] + 1e-9, \
            f"saturated haircut violated at density {r['density']}: on={r['on']['circ_mean']} off={r['off']['circ_mean']}"
        assert r["haircut"] <= 1.0 + 1e-9


def test_recon_sensitivity_band_structure_and_determinism():
    cb_list, k_list = [1.0, 8.0], [0.0, 0.5]
    # base cfg carries recon_c0>0 so the k=0 cells are still a valid schedule (S(n)=c0).
    base = replace(saturated(), recon_c0=2.0)
    out1 = recon_sensitivity_band(base, density=6.0, reps=2, cell_bytes_list=cb_list, k_list=k_list)
    out2 = recon_sensitivity_band(base, density=6.0, reps=2, cell_bytes_list=cb_list, k_list=k_list)
    assert out1 == out2                                         # fully deterministic
    assert len(out1["cells"]) == len(cb_list) * len(k_list)
    assert out1["circ_off_mean"] > 0.0
    for c in out1["cells"]:
        assert {"cell_bytes", "k", "circ_on_mean", "haircut", "recon_capped_episodes"} <= set(c)
        assert c["cell_bytes"] in cb_list and c["k"] in k_list


def test_recon_band_haircut_monotone_in_cell_bytes():
    """β-knee discipline: at a saturated point with the schedule biting, a LARGER cell_bytes (more
    airtime per cell) must not INCREASE circulation — haircut is non-increasing in cell_bytes (k fixed)."""
    out = recon_sensitivity_band(replace(saturated(), recon_c0=2.0), density=6.0, reps=4,
                                 cell_bytes_list=[1.0, 8.0, 32.0], k_list=[0.5])
    by_cb = {c["cell_bytes"]: c["haircut"] for c in out["cells"]}
    assert by_cb[32.0] <= by_cb[1.0] + 1e-9, f"haircut rose with cell_bytes: {by_cb}"


def test_recon_compare_csv_fields_and_manifest():
    out = recon_compare_sweep(tiny(), [3.0], reps=1, recon_cfg=RECON_ON)
    s = recon_compare_to_csv_string(out, replace(tiny(), **RECON_ON).manifest())
    lines = s.splitlines()
    header = lines[0]
    for fld in RECON_COMPARE_FIELDS:
        assert fld in header
    assert "param_recon_cell_bytes" in header and "param_recon_k" in header
    assert "haircut" in header and "on_recon_capped_episodes" in header
    assert len(lines) == 1 + 1                                  # header + 1 density row


def test_recon_band_csv_fields_and_comment():
    base = replace(saturated(), recon_c0=2.0)
    out = recon_sensitivity_band(base, density=6.0, reps=1, cell_bytes_list=[1.0, 8.0],
                                 k_list=[0.0, 0.5])
    s = recon_band_to_csv_string(out, base.manifest())
    lines = s.splitlines()
    assert lines[0].startswith("#") and "density=" in lines[0] and "circ_off_mean=" in lines[0]
    header = lines[1]
    for fld in RECON_BAND_FIELDS:
        assert fld in header
    assert "param_master_seed" in header
    assert len(lines) == 1 + 1 + 4                              # comment + header + 2x2 grid rows
