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


def test_defenses_off_pipeline_dormant_deterministic_and_wired():
    # bit-identical safety: with defenses OFF the pipeline takes the pre-PR-2 path (no background soup,
    # deterministic), and turning a defense ON actually changes the run (feature wired, not a silent no-op).
    from dataclasses import replace
    from soup_sim.scenario import _run_one_anonymity
    off = replace(tiny(), mixing_lambda=0.0, originate_gate_relays=0)
    a = _run_one_anonymity(off)
    b = _run_one_anonymity(off)
    assert a["acquired"] == b["acquired"] and a["delivery"] == b["delivery"]   # deterministic
    assert all(bid < 10_000_000 for (_n, bid) in a["acquired"])               # background soup NOT injected
    on = _run_one_anonymity(replace(off, mixing_lambda=0.5))
    assert on["acquired"] != a["acquired"]                                    # mixing ON changes the run


@pytest.mark.slow
def test_anonymity_defense_sweep_realistic():
    from dataclasses import replace
    from soup_sim.scenario import anonymity_defense_sweep
    from soup_sim.anonymity import MIN_INTERSECTION_SIZE
    base = replace(base_defense_cfg())
    out = anonymity_defense_sweep(base, f=0.7, reps=4)
    # NON-VACUOUS: the same-detected-set intersection must clear the floor, so the verdict is a real
    # credit/refuse decision -- not the "intersection too small" early return (which would pass even if
    # the whole credit machinery were deleted).
    assert out["mixing"]["intersection"] >= MIN_INTERSECTION_SIZE
    assert out["gate"]["intersection"] >= MIN_INTERSECTION_SIZE
    labels = {out["mixing"]["verdict"]["label"], out["gate"]["verdict"]["label"]}
    assert any("intersection" not in lb.lower() for lb in labels)   # credit path actually exercised
    # a credited gain must NOT be pure message-dropping: it must survive THAT arm's TTL=inf control.
    for arm in ("mixing", "gate"):
        a = out[arm]
        if a["verdict"]["credited"]:
            assert a["timing_only_rank1"] <= a["baseline_rank1"]    # gain survived TTL=inf


def base_defense_cfg():
    return Config(n=120, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=40.0, buffer_cap=200, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=10.0, measure_window=40.0,
                  drain=20.0, n_messages=160, seen_margin=40.0, master_seed=11, adversary_range_mult=1.0,
                  mixing_lambda=0.05, originate_gate_relays=3)


def test_make_tracked_cohort_staggers_and_maps():
    from soup_sim.scenario import make_tracked_cohort
    c = tiny()
    cohort, tracked = make_tracked_cohort(c, k_max=4, n_tracked=2, stride=2.0,
                                          inject_time=c.warmup, rng=c.rng(7))
    assert len(tracked) == 2 and all(len(ids) == 4 for ids in tracked.values())
    by_id = {b.id: b for (b, _s, _d) in cohort}
    for dev, ids in tracked.items():
        times = [by_id[i].created_at for i in ids]
        assert times == [c.warmup + k * 2.0 for k in range(4)]      # staggered by stride
        srcs = {s for (b, s, _d) in cohort if b.id in ids}
        assert srcs == {dev}                                        # all four share the device as src
    assert len(cohort) == 2 * 4 + c.n_messages                      # tracked + background


def test_run_tracked_respects_created_at_causality():
    from soup_sim.scenario import _run_one_anonymity_tracked
    art = _run_one_anonymity_tracked(tiny(), k_max=3, n_tracked=1, stride=2.0)
    assert "tracked" in art and len(art["tracked"]) == 1
    cohort_created = {bid: created for (bid, _s, created, _ttl) in art["cohort"]}
    for (node, bid), t_acq in art["acquired"].items():
        if bid in cohort_created:
            assert t_acq >= cohort_created[bid] - 1e-9              # no acquire before origination


def test_run_tracked_deterministic():
    from soup_sim.scenario import _run_one_anonymity_tracked
    a = _run_one_anonymity_tracked(tiny(), k_max=3, n_tracked=1, stride=2.0)
    b = _run_one_anonymity_tracked(tiny(), k_max=3, n_tracked=1, stride=2.0)
    assert a["acquired"] == b["acquired"] and a["tracked"] == b["tracked"]


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
