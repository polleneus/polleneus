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


def test_static_curve_is_monotone_increasing():
    cfg = base()
    rows = static_delivery_sweep(cfg, list(np.linspace(2.0, 10.0, 9)), reps=4)
    ys = [r["delivery_mean"] for r in rows]
    assert ys[0] < 0.2 and ys[-1] > 0.7        # low density poor, high density good
    assert all(ys[i] <= ys[i + 1] + 0.05 for i in range(len(ys) - 1))  # ~monotone
