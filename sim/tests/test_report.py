import numpy as np
from soup_sim.config import Config
from soup_sim.scenario import static_delivery_sweep
from soup_sim.report import to_csv_string, METRIC_FIELDS


def base():
    return Config(n=0, width=200.0, height=200.0, radius=10.0, boundary="torus",
                  mobility="static", speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e9,
                  buffer_cap=10 ** 9, throughput_ideal=1e9, alpha=0.0, t_setup=0.0,
                  p_fail=0.0, blob_size=1.0, warmup=0.0, measure_window=1.0, drain=0.0,
                  n_messages=0, seen_margin=1e9, master_seed=99)


def test_csv_has_metric_and_param_columns():
    cfg = base()
    rows = static_delivery_sweep(cfg, [3.0, 7.0], reps=3)
    s = to_csv_string(rows, cfg.manifest())
    header = s.splitlines()[0]
    for f in METRIC_FIELDS:
        assert f in header
    assert "param_master_seed" in header
    assert len(s.splitlines()) == 1 + 2  # header + 2 density rows


def test_csv_byte_identical_same_seed():
    cfg = base()
    a = to_csv_string(static_delivery_sweep(cfg, [3.0, 7.0], reps=3), cfg.manifest())
    b = to_csv_string(static_delivery_sweep(cfg, [3.0, 7.0], reps=3), cfg.manifest())
    assert a == b


def test_airtime_csv_has_fields():
    from soup_sim.report import airtime_to_csv_string
    rows = [{"density": 6.0, "circulated_per_min_mean": 12.0, "ci_lo": 10.0, "ci_hi": 14.0,
             "utilization_mean": 0.3, "delivery_mean": 0.4, "t50": 25.0,
             "binding": {"contention_bound": 0.6, "setup_starved": 0.3, "quantization": 0.1,
                         "demand_satisfied": 0.4}}]
    s = airtime_to_csv_string(rows, {"airtime_model": "collision"})
    header = s.splitlines()[0]
    assert "circulated_per_min_mean" in header and "t50" in header
    assert "binding_contention_bound" in header and "param_airtime_model" in header
    assert len(s.splitlines()) == 1 + 1


def test_anonymity_csv_scope_tag_is_a_column_not_just_comment():
    from soup_sim.report import anonymity_to_csv_string
    rows = [{"f": 0.5, "arm": "chokepoint", "realized_coverage": 0.48, "rank1_prob": 0.3,
             "ci_lo": 0.2, "ci_hi": 0.4, "median_err_firsthear": 18.0, "median_err_origin": 22.0,
             "p90_err": 40.0, "undetected_fraction": 0.1, "beats_random": True}]
    tag = "[UPPER BOUND on anonymity; intersection NOT modeled]"
    s = anonymity_to_csv_string(rows, {"master_seed": 5}, tag)
    lines = s.splitlines()
    assert lines[0].startswith("#") and "UPPER BOUND" in lines[0]      # human-readable comment
    assert "scope_tag" in lines[1] and "rank1_prob" in lines[1] and "param_master_seed" in lines[1]
    assert tag in lines[2]                                              # tag survives as a COLUMN value (row)


def test_defense_csv_carries_both_tags_as_columns():
    from soup_sim.report import anonymity_defense_to_csv_string, DEFENSE_FIELDS
    out = {
        "scope_tag": "[UPPER BOUND on anonymity]",
        "defense_scope_tag": "[defense benefit NOT evaluated against intersection/insider]",
        "mixing": {"baseline_rank1": 0.30, "defended_rank1": 0.12, "timing_only_rank1": 0.13, "intersection": 80,
                   "verdict": {"credited": True, "label": "credited: real timing-scramble gain"},
                   "cost": {"delivery": 0.91, "t50": 18.0}},
        "gate": {"baseline_rank1": 0.30, "defended_rank1": 0.20, "timing_only_rank1": 0.29, "intersection": 70,
                 "relay_density": 3.4, "verdict": {"credited": False, "label": "no material drop"},
                 "cost": {"delivery": 0.88, "t50": 22.0}},
    }
    s = anonymity_defense_to_csv_string(out, {"master_seed": 5, "mixing_lambda": 0.05})
    lines = s.splitlines()
    assert lines[0].startswith("#") and lines[1].startswith("#")        # both tags as comments
    header = lines[2]
    for fld in DEFENSE_FIELDS:
        assert fld in header
    assert "scope_tag" in header and "defense_scope_tag" in header and "param_mixing_lambda" in header
    assert len(lines) == 2 + 1 + 2                                      # 2 comments + header + 2 arms
    assert out["scope_tag"] in lines[3] and out["defense_scope_tag"] in lines[3]   # tags survive as columns
    assert "credited" in s and "3.4" in s                              # verdict + gate relay-density present


def test_intersection_csv_carries_tags_and_both_fusion_rules():
    from soup_sim.report import intersection_to_csv_string, INTERSECTION_FIELDS
    out = {
        "scope_tag": "[UPPER BOUND on anonymity]",
        "intersection_scope_tag": "[INTERSECTION; device-linkage ASSUMED given; UPPER BOUND on anonymity]",
        "verdict": {"credited": True, "label": "intersection deanonymizes the sender"},
        "rows": [
            {"k": 1, "fused_rank1_borda": 0.30, "ci_lo_borda": 0.2, "ci_hi_borda": 0.4, "fused_rank1_score_sum": 0.31,
             "decoy_rank1": 0.05, "random_floor_fused": 0.008, "delivery": 0.9, "n_samples": 40},
            {"k": 16, "fused_rank1_borda": 0.80, "ci_lo_borda": 0.7, "ci_hi_borda": 0.9, "fused_rank1_score_sum": 0.78,
             "decoy_rank1": 0.06, "random_floor_fused": 0.009, "delivery": 0.9, "n_samples": 40},
        ],
    }
    s = intersection_to_csv_string(out, {"master_seed": 13})
    lines = s.splitlines()
    assert lines[0].startswith("#") and lines[1].startswith("#")          # both tags as comments
    header = lines[2]
    for fld in INTERSECTION_FIELDS:
        assert fld in header
    assert "intersection_scope_tag" in header and "per_message_scope_tag" in header
    assert "param_master_seed" in header
    assert "headline_credited" in header and "fused_rank1_score_sum" in header
    assert len(lines) == 2 + 1 + 2                                        # 2 comments + header + 2 K rows
    assert out["intersection_scope_tag"] in lines[3]                      # tag survives as a column value


def test_cluster_csv_has_fields_and_regime_tag():
    from soup_sim.report import cluster_to_csv_string, CLUSTER_FIELDS
    out = {
        "regime_tag": "[MOBILITY REGIME = clustered gathering; uniform/RWP is the optimistic baseline]",
        "degree": 8.0, "rwp_delivery": 0.95, "rwp_recovered": True,
        "rows": [
            {"leak": 0.0, "n": 110, "delivery_mean": 0.16, "ci_lo": 0.1, "ci_hi": 0.2,
             "giant_mean": 0.17, "intra_degree": 7.0, "inter_degree": 0.0},
            {"leak": 1.0, "n": 110, "delivery_mean": 0.93, "ci_lo": 0.9, "ci_hi": 0.95,
             "giant_mean": 0.97, "intra_degree": 1.2, "inter_degree": 6.0},
        ],
    }
    s = cluster_to_csv_string(out, {"master_seed": 5})
    lines = s.splitlines()
    assert lines[0].startswith("#") and "clustered" in lines[0]      # regime tag comment
    header = lines[1]
    for fld in CLUSTER_FIELDS:
        assert fld in header
    assert "regime_tag" in header and "param_master_seed" in header
    assert len(lines) == 1 + 1 + 2                                   # comment + header + 2 leak rows
    assert out["regime_tag"] in lines[2]                            # tag survives as a column value


def test_static_curve_is_monotone_increasing():
    cfg = base()
    rows = static_delivery_sweep(cfg, list(np.linspace(2.0, 10.0, 9)), reps=4)
    ys = [r["delivery_mean"] for r in rows]
    assert ys[0] < 0.2 and ys[-1] > 0.7        # low density poor, high density good
    assert all(ys[i] <= ys[i + 1] + 0.05 for i in range(len(ys) - 1))  # ~monotone
