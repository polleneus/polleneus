"""Scenario runner: one replication, a density sweep with per-replication confidence
intervals (the replication unit is the SEED, not the message — within-run messages are
correlated), and a bootstrap cliff-midpoint estimate.
"""
from __future__ import annotations
from dataclasses import replace
import numpy as np
from .mobility import make_mobility, mean_degree, stationarity_ok
from .buffer import NodeBuffer
from .budget import AirtimeBudget
from .engine import Engine
from .metrics import Metrics
from .workload import make_cohort
from .cell_list import neighbor_pairs
from .percolation import same_component_pair_fraction, placement


def density_to_n(d: float, w: float, h: float, r: float) -> int:
    return int(round(d * w * h / (np.pi * r * r)))


# Student-t two-sided 95% critical values by df (df>30 -> ~normal 1.96).
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
        16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074,
        23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042}


def _t_crit(df: int) -> float:
    if df <= 0:
        return 0.0
    return _T95.get(df, 1.96)


def mean_ci(values):
    """Student-t 95% CI across the per-replication observations (the replication unit is
    the SEED, not the message — small reps need t, not the normal z, or the band is too tight)."""
    arr = np.asarray(values, float)
    n = len(arr)
    if n == 0:
        return (0.0, 0.0, 0.0)
    m = float(np.mean(arr))
    if n == 1:
        return (m, m, m)
    se = float(np.std(arr, ddof=1)) / np.sqrt(n)
    t = _t_crit(n - 1)
    return (m, max(0.0, m - t * se), min(1.0, m + t * se))


def _seed_for(base_seed: int, di: int, rep: int) -> int:
    return int(np.random.SeedSequence([base_seed, di, rep]).generate_state(1)[0])


def run_one(cfg) -> dict:
    cfg.validate()
    # Disjoint substream namespaces (leading tag) so no path can alias another at any n:
    # mobility=0, engine=1, cohort=2, buffers=(3, i).
    mob = make_mobility(cfg, cfg.rng(0))
    metrics = Metrics(cfg, cfg.warmup, cfg.measure_window)
    buffers = [NodeBuffer(cfg.buffer_cap, cfg.ttl + cfg.seen_margin, cfg.rng(3, i))
               for i in range(cfg.n)]
    budget = AirtimeBudget(cfg.throughput_ideal, cfg.alpha, cfg.t_setup, cfg.p_fail, cfg.blob_size,
                           model=cfg.airtime_model, beta=cfg.beta,
                           t_setup_slope=cfg.t_setup_slope, n_channels=cfg.n_channels)
    eng = Engine(cfg, mob, buffers, budget, cfg.rng(1), on_deliver=metrics.on_deliver)

    eng.run_until(cfg.warmup)
    for blob, src, dst in make_cohort(cfg, inject_time=cfg.warmup, rng=cfg.rng(2)):
        metrics.register(blob, src, dst)
        eng.inject(blob, src)
    tx0 = eng.transmissions                       # circulation: count accepted transfers in-window only

    samples, n_samp = [], 10
    for s in range(1, n_samp + 1):
        eng.run_until(cfg.warmup + cfg.measure_window * s / n_samp)
        samples.append(mean_degree(mob.positions, cfg.radius, cfg.width, cfg.height, cfg.boundary))
    tx1 = eng.transmissions                       # snapshot BEFORE drain/finalize
    eng.run_until(cfg.warmup + cfg.measure_window + cfg.drain)
    eng.finalize()  # settle any still-open episodes exactly once at the true end

    first = float(np.mean(samples[: n_samp // 2]))
    second = float(np.mean(samples[n_samp // 2:]))
    return {
        "delivery_ratio": metrics.delivery_ratio(),
        "fair_chance": len(metrics.fair_chance_ids()),
        "delivered": metrics.fair_chance_delivered(),
        "latencies": metrics.latencies(),
        "overhead": metrics.overhead_ratio(eng.transmissions),
        "transmissions": eng.transmissions,
        "empirical_mean_degree": float(np.mean(samples)),
        "stationary_ok": stationarity_ok(first, second, tol=0.15),
        # PR-2 airtime measurements
        "circulated_per_min": metrics.circulated_per_min(tx1 - tx0, cfg.measure_window),
        "utilization": metrics.utilization(eng.charged_airtime, eng.available_contact_time),
        "utilization_vs_offered": metrics.utilization_vs_offered(eng.charged_airtime, eng.offered_airtime),
        "t50": metrics.t50(),
        "offered_blobs": eng.offered_blobs,
        "served_blobs": eng.served_blobs,
        "setup_starved_blobs": eng.setup_starved_blobs,
        "quantization_blobs": eng.quantization_blobs,
        "contention_blobs": eng.contention_blobs,
        "manifest": cfg.manifest(),
    }


def sweep(base_cfg, densities, reps: int) -> list[dict]:
    rows = []
    for di, d in enumerate(densities):
        n = density_to_n(d, base_cfg.width, base_cfg.height, base_cfg.radius)
        ratios, emp, overhead, st_ok = [], [], [], []
        for rep in range(reps):
            cfg = replace(base_cfg, n=max(2, n), master_seed=_seed_for(base_cfg.master_seed, di, rep))
            r = run_one(cfg)
            ratios.append(r["delivery_ratio"])
            emp.append(r["empirical_mean_degree"])
            overhead.append(r["overhead"] if np.isfinite(r["overhead"]) else np.nan)
            st_ok.append(r["stationary_ok"])
        m, lo, hi = mean_ci(ratios)
        rows.append({
            "density": d, "n": n, "delivery_mean": m, "ci_lo": lo, "ci_hi": hi,
            "empirical_mean_degree": float(np.mean(emp)),
            "overhead_mean": float(np.nanmean(overhead)) if np.any(np.isfinite(overhead)) else float("inf"),
            "stationary_ok": bool(np.all(st_ok)),
            "per_rep_ratios": ratios,
        })
    return rows


def static_delivery_sweep(base_cfg, degrees, reps: int) -> list[dict]:
    """Headline STATIC curve: component-reachability delivery vs mean degree over a
    Poisson torus ensemble. Exact and engine-free; the validated quantity behind the
    percolation gate. Its 0.5 crossing sits well ABOVE d_c (delivery ~ S^2), ~d 6-7.
    """
    w, h, r = base_cfg.width, base_cfg.height, base_cfg.radius
    lam_to_n = w * h / (np.pi * r * r)
    rows = []
    for di, d in enumerate(degrees):
        ratios, emp = [], []
        for rep in range(reps):
            rng = np.random.default_rng(np.random.SeedSequence([base_cfg.master_seed, di, rep]))
            n = int(rng.poisson(d * lam_to_n))
            pos = placement(n, w, h, rng)
            ratios.append(same_component_pair_fraction(pos, r, w, h, base_cfg.boundary))
            emp.append(2.0 * len(neighbor_pairs(pos, r, w, h, base_cfg.boundary)) / max(1, n))
        m, lo, hi = mean_ci(ratios)
        rows.append({
            "density": d, "n": int(round(d * lam_to_n)), "delivery_mean": m,
            "ci_lo": lo, "ci_hi": hi, "empirical_mean_degree": float(np.mean(emp)),
            "overhead_mean": float("nan"), "stationary_ok": True, "per_rep_ratios": ratios,
        })
    return rows


def crossing_0p5(densities, mean_ratios) -> float:
    x, y = np.asarray(densities, float), np.asarray(mean_ratios, float)
    for i in range(len(x) - 1):
        if (y[i] - 0.5) * (y[i + 1] - 0.5) <= 0 and y[i + 1] != y[i]:
            t = (0.5 - y[i]) / (y[i + 1] - y[i])
            return float(x[i] + t * (x[i + 1] - x[i]))
    return float("nan")


def midpoint_with_ci(rows, rng, n_boot: int = 200):
    """Delivery=0.5 crossing + bootstrap CI over replications (robust to 0/1 tails)."""
    densities = [r["density"] for r in rows]
    matrix = np.array([r["per_rep_ratios"] for r in rows])  # (n_density, reps)
    point = crossing_0p5(densities, matrix.mean(axis=1))
    reps = matrix.shape[1]
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, reps, reps)
        c = crossing_0p5(densities, matrix[:, idx].mean(axis=1))
        if not np.isnan(c):
            boots.append(c)
    if boots:
        lo, hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    else:
        lo = hi = point
    return {"midpoint": point, "ci": (lo, hi)}
