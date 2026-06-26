import pytest
from soup_sim.config import Config
from soup_sim.scenario import anonymity_sweep


def tiny():   # n>0; smoke only — NOT a power config (rank-1 not trusted here)
    return Config(n=12, width=40.0, height=40.0, radius=8.0, boundary="torus", mobility="rwp",
                  speed_min=1.5, speed_max=1.5, dt=1.0, ttl=20.0, buffer_cap=40, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=4.0, measure_window=10.0,
                  drain=0.0, n_messages=10, seen_margin=20.0, master_seed=5, adversary_range_mult=1.0)


def test_anonymity_sweep_structure_and_determinism():
    a = anonymity_sweep(tiny(), [0.3, 0.7], reps=2)
    b = anonymity_sweep(tiny(), [0.3, 0.7], reps=2)
    assert a["rows"] == b["rows"]                                   # deterministic
    assert "UPPER BOUND" in a["scope_tag"]
    assert a["headline_arm"] in ("uniform", "chokepoint") and "ok" in a["mustlocalize"]
    assert any(r["undetected_fraction"] < 1.0 for r in a["rows"])   # non-vacuous: something heard
    for r in a["rows"]:
        assert {"f", "arm", "rank1_prob", "median_err_firsthear", "median_err_origin", "p90_err",
                "p95_err", "anon_set_upper_bound", "unconditional_rank1",
                "undetected_fraction", "beats_random", "realized_coverage"} <= set(r)


def test_report_lines_hard_gate_and_scope_tag():
    from run import anonymity_report_lines
    cfg = tiny()
    rows = [{"arm": "uniform", "rank1_prob": 0.9, "realized_coverage": 0.95, "beats_random": True}]
    tag = "[UPPER BOUND on anonymity; intersection NOT modeled]"
    # must-localize FAILED -> exposure must be INCONCLUSIVE, never an EXPOSES verdict
    out_fail = {"rows": rows, "headline_arm": "uniform", "scope_tag": tag,
                "mustlocalize": {"ok": False, "label": "inconclusive"}}
    lines = anonymity_report_lines(out_fail, cfg, reps=6)
    assert any(tag in ln for ln in lines)                          # scope tag travels
    assert any("INCONCLUSIVE" in ln for ln in lines)
    assert not any("EXPOSES" in ln for ln in lines)                # hard-gated: no exposure claim
    # must-localize OK + strong rank-1 -> an exposure verdict is allowed
    out_ok = {**out_fail, "mustlocalize": {"ok": True, "label": "ok"}}
    lines_ok = anonymity_report_lines(out_ok, cfg, reps=6)
    assert any("EXPOSURE:" in ln and "INCONCLUSIVE" not in ln for ln in lines_ok)
