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


def tiny_defense():
    from dataclasses import replace
    return replace(tiny(), mixing_lambda=0.05, originate_gate_relays=2, adversary_range_mult=2.0)


def test_anonymity_defense_sweep_structure_and_determinism():
    from soup_sim.scenario import anonymity_defense_sweep
    a = anonymity_defense_sweep(tiny_defense(), f=0.7, reps=1)
    b = anonymity_defense_sweep(tiny_defense(), f=0.7, reps=1)
    assert a["mixing"]["verdict"] == b["mixing"]["verdict"]            # deterministic
    assert a["gate"]["verdict"] == b["gate"]["verdict"]
    assert "UPPER BOUND" in a["scope_tag"] and "NOT evaluated" in a["defense_scope_tag"]
    for arm in ("mixing", "gate"):
        assert {"baseline_rank1", "defended_rank1", "intersection", "verdict", "cost"} <= set(a[arm])
        assert "credited" in a[arm]["verdict"]
    assert a["mixing"]["timing_only_rank1"] is not None                # the TTL=inf confound arm ran


@pytest.mark.slow
def test_anonymity_defense_sweep_realistic():
    from dataclasses import replace
    from soup_sim.scenario import anonymity_defense_sweep
    base = replace(base_defense_cfg())
    out = anonymity_defense_sweep(base, f=0.7, reps=4)
    # mixing's credited gain must NOT be pure message-dropping: if mixing cuts rank-1 but the TTL=inf
    # timing-only arm does NOT also cut it, defense_gate must refuse credit.
    m = out["mixing"]
    if m["verdict"]["credited"]:
        assert m["timing_only_rank1"] <= m["baseline_rank1"]           # gain survived TTL=inf
    assert out["gate"]["intersection"] >= 0 and out["mixing"]["intersection"] >= 0


def base_defense_cfg():
    return Config(n=120, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=40.0, buffer_cap=200, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=10.0, measure_window=40.0,
                  drain=20.0, n_messages=160, seen_margin=40.0, master_seed=11, adversary_range_mult=1.0,
                  mixing_lambda=0.05, originate_gate_relays=3)


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
