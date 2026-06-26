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
from .blob import Blob
from .cell_list import neighbor_pairs
from .percolation import same_component_pair_fraction, placement
from .knee import find_knee, binding_decomposition, binding_gate
from .adversary import place_receivers, realized_coverage, hearings, estimate
from .anonymity import (localization_error, rank_of, anonymity_set_size, quantiles,
                        mustlocalize_gate, exposure_gate, defense_gate, SCOPE_TAG, DEFENSE_SCOPE_TAG,
                        MIN_RELAY_DENSITY)
from .geometry import dist2 as _dist2


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
    percolation gate. Its 0.5 crossing sits JUST ABOVE d_c (~d 4.5-4.7 at venue-scale N;
    delivery ~ S^2); ~d 6-7 is where delivery SATURATES (0.95-0.99), not the 0.5 crossing.
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


def _airtime_arm(base_cfg, densities, reps):
    """One density sweep returning per-density airtime rows + the per-rep circulation matrix."""
    rows, circ_matrix = [], []
    for di, d in enumerate(densities):
        n = density_to_n(d, base_cfg.width, base_cfg.height, base_cfg.radius)
        circ, util, deliv, t50s = [], [], [], []
        agg = {"offered": 0, "served": 0, "starved": 0, "quant": 0, "contention": 0}
        for rep in range(reps):
            cfg = replace(base_cfg, n=max(2, n), master_seed=_seed_for(base_cfg.master_seed, di, rep))
            r = run_one(cfg)
            circ.append(r["circulated_per_min"])
            util.append(r["utilization"])
            deliv.append(r["delivery_ratio"])
            t50s.append(r["t50"] if r["t50"] is not None else np.nan)
            agg["offered"] += r["offered_blobs"]
            agg["served"] += r["served_blobs"]
            agg["starved"] += r["setup_starved_blobs"]
            agg["quant"] += r["quantization_blobs"]
            agg["contention"] += r["contention_blobs"]
        m, lo, hi = mean_ci(circ)
        rows.append({
            "density": d, "n": n, "circulated_per_min_mean": m, "ci_lo": lo, "ci_hi": hi,
            "utilization_mean": float(np.mean(util)), "delivery_mean": float(np.mean(deliv)),
            "t50": float(np.nanmean(t50s)) if np.any(~np.isnan(t50s)) else None,
            "binding": binding_decomposition(agg["offered"], agg["served"], agg["starved"],
                                             agg["quant"], agg["contention"]),
        })
        circ_matrix.append(circ)
    return rows, np.array(circ_matrix)


def airtime_sweep(base_cfg, densities, reps):
    """Airtime density sweep with TWO mandatory control arms (alpha=0 airtime-free; cap=inf/ttl=inf),
    a saturation-knee estimate, and the binding publish-gate. Deterministic by master_seed."""
    rng = np.random.default_rng(np.random.SeedSequence([base_cfg.master_seed, 777]))
    rows, circ = _airtime_arm(base_cfg, densities, reps)
    a0_rows, a0_circ = _airtime_arm(
        replace(base_cfg, airtime_model="linear", alpha=0.0, beta=0.0, t_setup_slope=0.0), densities, reps)
    ct_rows, ct_circ = _airtime_arm(
        replace(base_cfg, buffer_cap=10 ** 9, ttl=1e9), densities, reps)
    knee = find_knee(densities, circ, np.random.default_rng(rng.integers(0, 2 ** 31)))
    a0_over = find_knee(densities, a0_circ, np.random.default_rng(rng.integers(0, 2 ** 31)))["status"] == "knee"
    ct_over = find_knee(densities, ct_circ, np.random.default_rng(rng.integers(0, 2 ** 31)))["status"] == "knee"
    if knee["status"] == "knee":                          # binding at the row nearest the REFINED knee density
        ki = int(np.argmin([abs(r["density"] - knee["knee"]) for r in rows]))
    else:
        ki = int(np.argmax([r["circulated_per_min_mean"] for r in rows]))
    gate = binding_gate(knee, rows[ki]["binding"], a0_over, ct_over)
    return {"rows": rows, "alpha0_rows": a0_rows, "capttl_rows": ct_rows, "knee": knee, "gate": gate,
            "predicted_knee_contenders": 1.0 / base_cfg.beta if base_cfg.beta else None}


def _anon_pos_at(log, t):
    """Node positions at the log step nearest time t."""
    return min(log, key=lambda e: abs(e[0] - t))[1]


def _run_one_anonymity(cfg):
    """One engine run with the position-log recorder on; returns the artifacts the post-hoc
    adversary overlay needs (no receivers in the sim ⇒ delivery untouched)."""
    cfg.validate()
    mob = make_mobility(cfg, cfg.rng(0))
    metrics = Metrics(cfg, cfg.warmup, cfg.measure_window)
    buffers = [NodeBuffer(cfg.buffer_cap, cfg.ttl + cfg.seen_margin, cfg.rng(3, i)) for i in range(cfg.n)]
    budget = AirtimeBudget(cfg.throughput_ideal, cfg.alpha, cfg.t_setup, cfg.p_fail, cfg.blob_size,
                           model=cfg.airtime_model, beta=cfg.beta,
                           t_setup_slope=cfg.t_setup_slope, n_channels=cfg.n_channels)
    eng = Engine(cfg, mob, buffers, budget, cfg.rng(1), on_deliver=metrics.on_deliver, record_positions=True)
    eng.run_until(cfg.warmup)
    gated = cfg.originate_gate_relays > 0 or cfg.originate_gate_time > 0
    if gated:
        # un-gated background soup so a gated originator has foreign ids to relay (else total deadlock)
        rng_bg = cfg.rng(2, 7)
        for m in range(cfg.n_messages):
            src = int(rng_bg.integers(0, cfg.n))
            eng.inject(Blob(id=10_000_000 + m, created_at=cfg.warmup, ttl=cfg.ttl, size=cfg.blob_size), src)
    cohort = []
    for blob, src, dst in make_cohort(cfg, inject_time=cfg.warmup, rng=cfg.rng(2)):
        metrics.register(blob, src, dst)
        eng.inject(blob, src, gated=gated)               # measured originations gated under the gate arm
        cohort.append((blob.id, src, blob.created_at, blob.ttl))
    eng.run_until(cfg.warmup + cfg.measure_window + cfg.drain)
    eng.finalize()
    return {"position_log": eng.position_log, "acquired": dict(eng.acquired), "cohort": cohort,
            "episodes": list(eng.episodes), "n": cfg.n, "relayed": {k: len(v) for k, v in eng.relayed.items()},
            "delivery": metrics.delivery_ratio(), "t50": metrics.t50()}


def _forward_infection(episodes, source, t0, n):
    """Earliest time each node is infected if the epidemic is SEEDED at `source` at t0, over the
    time-respecting contact graph (a contact [entry,exit] infects b at max(t_a,entry) iff t_a<=exit).
    This is the diffusion model the engine actually uses (NOT distance/c)."""
    inf = {source: t0}
    changed = True
    while changed:
        changed = False
        for (i, j, entry, exit_) in episodes:
            for a, b in ((i, j), (j, i)):
                ta = inf.get(a)
                if ta is not None and ta <= exit_ + 1e-9:
                    cand = max(ta, entry)
                    if b not in inf or cand < inf[b] - 1e-12:
                        inf[b] = cand
                        changed = True
    return inf


def _forward_reach_matrix(episodes, position_log, receivers, t0, n, adv_range, cfg):
    """reach[c][L] = predicted first-hear time of receiver L if candidate c were the source:
    earliest time any node infected by c's epidemic is within adv_range of L. Computed from the
    recorded spread (forward temporal reachability) + the position log — the proper diffusion-source
    predictor (replaces the wrong euclidean proxy)."""
    import bisect
    R = len(receivers)
    r2 = adv_range * adv_range
    in_range = [[[] for _ in range(R)] for _ in range(n)]    # (node, receiver) -> sorted in-range times
    for (t, pos) in position_log:
        for li, L in enumerate(receivers):
            d2 = _dist2(pos, L, cfg.width, cfg.height, cfg.boundary)
            for k in np.nonzero(d2 <= r2)[0]:
                in_range[int(k)][li].append(t)
    reach = np.full((n, R), np.inf)
    for c in range(n):
        inf = _forward_infection(episodes, c, t0, n)
        for k, tk in inf.items():
            row = in_range[k]
            for li in range(R):
                tl = row[li]
                idx = bisect.bisect_left(tl, tk)
                if idx < len(tl) and tl[idx] < reach[c][li]:
                    reach[c][li] = tl[idx]
    return reach


def _reach_capped(reach):
    """Replace unreachable (inf) predictions with a large finite sentinel so a candidate that
    cannot explain a hear correlates poorly (ranks worse) instead of breaking the correlation."""
    if reach.size == 0:
        return reach
    finite = reach[np.isfinite(reach)]
    cap = (float(np.max(finite)) * 10.0 + 1.0) if finite.size else 1.0
    out = reach.copy()
    out[~np.isfinite(out)] = cap
    return out


def _score_arm(art, receivers, cfg, rng_est, with_origin_vs_relay=False):
    """Score the adversary on one receiver layout: per detected cohort message, best-estimator
    rank/error (first-hear-time = estimator quality; origination-time = headline) + random floor.
    Returns (per-message records incl. the detected blob id, undetected, total). When
    with_origin_vs_relay (the GATE arm), adds the origin-vs-relay estimator to the best-of."""
    log, acquired, cohort = art["position_log"], art["acquired"], art["cohort"]
    adv_range = cfg.adversary_range_mult * cfg.radius
    expiry = {bid: created + ttl for (bid, _src, created, ttl) in cohort}
    H = hearings(receivers, adv_range, log, acquired, expiry, cfg)
    by_blob = {}
    for (li, bid), t in H.items():
        by_blob.setdefault(bid, []).append((li, t))
    origin_t = cfg.warmup
    cand_origin = _anon_pos_at(log, origin_t)
    reach = _reach_capped(_forward_reach_matrix(art["episodes"], log, receivers, origin_t,
                                                art["n"], adv_range, cfg))
    methods = ["first_spy", "reachability"] + (["origin_vs_relay"] if with_origin_vs_relay else [])
    res, undetected = [], 0
    for (bid, src, _created, _ttl) in cohort:
        mh = by_blob.get(bid)
        if not mh:
            undetected += 1
            continue
        fh = min(t for _li, t in mh)
        cand_fh = _anon_pos_at(log, fh)
        # upstream proxy (position oracle): a candidate is "preceded" (likely relayer) unless it is
        # the most-upstream — i.e. has the earliest forward-reach to the earliest-hearing receiver.
        upstream = None
        if with_origin_vs_relay:
            er = min(mh, key=lambda rt: rt[1])[0]
            col = reach[:, er]
            upstream = col > (col.min() + 1e-9)
        best = None
        for method in methods:
            est = estimate(method, mh, receivers, cand_fh, rng_est, reach=reach, upstream=upstream)
            rk = rank_of(est["scores"], src)
            if best is None or rk < best["rank"]:
                best = {"rank": rk, "bid": bid,
                        "err_fh": localization_error(est["point"], cand_fh[src], cfg),
                        "err_orig": localization_error(est["point"], cand_origin[src], cfg),
                        "anon": anonymity_set_size(est["scores"])}
        rand = estimate("random_guess", mh, receivers, cand_fh, rng_est)
        best["rand_rank"] = rank_of(rand["scores"], src)
        res.append(best)
    return res, undetected, len(cohort)


def _anon_aggregate(per_rep):
    """Mean over reps of the per-run anonymity aggregates (CI over seeds)."""
    def col(k):
        return [r[k] for r in per_rep]
    rank1 = mean_ci(col("rank1"))
    return {
        "rank1_prob": rank1[0], "ci_lo": rank1[1], "ci_hi": rank1[2],
        "median_err_firsthear": float(np.mean(col("median_err_firsthear"))),
        "median_err_origin": float(np.mean(col("median_err_origin"))),
        "p90_err": float(np.mean(col("p90_err"))),
        "p95_err": float(np.mean(col("p95_err"))),
        "anon_set_upper_bound": float(np.mean(col("anon_set_upper_bound"))),
        "unconditional_rank1": float(np.mean(col("unconditional_rank1"))),
        "undetected_fraction": float(np.mean(col("undetected_fraction"))),
        "beats_random": bool(np.mean(col("beats_random")) >= 0.5),
        "realized_coverage": float(np.mean(col("realized_coverage"))),
    }


def _arm_one_rep(cfg, f, mode):
    art = _run_one_anonymity(cfg)
    recv = place_receivers(cfg, f, mode, cfg.rng(4))
    res, undetected, total = _score_arm(art, recv, cfg, cfg.rng(6))
    rank1 = float(np.mean([r["rank"] == 0 for r in res])) if res else 0.0
    rand1 = float(np.mean([r["rand_rank"] == 0 for r in res])) if res else 0.0
    med, p90, p95 = quantiles([r["err_orig"] for r in res])
    medfh, _, _ = quantiles([r["err_fh"] for r in res])
    anon = float(np.mean([r["anon"] for r in res])) if res else float(cfg.n)
    undet = undetected / max(1, total)
    return {"rank1": rank1, "median_err_origin": med, "p90_err": p90, "p95_err": p95,
            "median_err_firsthear": medfh, "anon_set_upper_bound": anon,
            "undetected_fraction": undet, "unconditional_rank1": rank1 * (1.0 - undet),
            "beats_random": rank1 > rand1,
            "realized_coverage": realized_coverage(recv, cfg.adversary_range_mult * cfg.radius, cfg, cfg.rng(4))}


def anonymity_sweep(base_cfg, f_values, reps):
    """Source-exposure vs adversary coverage f, both placement arms (headline = the stronger),
    plus the must-localize capability control. Every number is an UPPER BOUND on anonymity."""
    rows, arm_rank1 = [], {"uniform": [], "chokepoint": []}
    for fi, f in enumerate(f_values):
        for mode in ("uniform", "chokepoint"):
            per_rep = [_arm_one_rep(replace(base_cfg, master_seed=_seed_for(base_cfg.master_seed, fi, rep)), f, mode)
                       for rep in range(reps)]
            agg = _anon_aggregate(per_rep)
            agg.update({"f": f, "arm": mode})
            rows.append(agg)
            arm_rank1[mode].append(agg["rank1_prob"])
    headline_arm = "chokepoint" if np.mean(arm_rank1["chokepoint"]) >= np.mean(arm_rank1["uniform"]) else "uniform"
    # must-localize control: SLOW mobility (not static -> a static flood has no gradient) + dense coverage
    ctrl = replace(base_cfg, speed_min=0.5, speed_max=0.5,
                   master_seed=_seed_for(base_cfg.master_seed, 999, 0))
    curve = []
    best_res = {"rank1": 0.0, "median_err_radii": float("inf")}
    for cov in (0.6, 0.95):
        art = _run_one_anonymity(ctrl)
        recv = place_receivers(ctrl, cov, "uniform", ctrl.rng(4))
        # BEST-estimator capability check (first-spy is the workhorse under dense coverage)
        res, _u, _t = _score_arm(art, recv, ctrl, ctrl.rng(6))
        ranks = [r["rank"] == 0 for r in res]
        errs = [r["err_fh"] / ctrl.radius for r in res]
        med_radii = float(np.median(errs)) if errs else float("inf")
        curve.append((cov, med_radii * ctrl.radius))
        if cov == 0.95:
            best_res = {"rank1": float(np.mean(ranks)) if ranks else 0.0, "median_err_radii": med_radii}
    mustlocalize = mustlocalize_gate(best_res, 1.0 / base_cfg.n, curve)
    return {"rows": rows, "mustlocalize": mustlocalize, "scope_tag": SCOPE_TAG, "headline_arm": headline_arm}


_DEFENSE_ARMS = {
    "baseline":    dict(mixing_lambda=0.0, originate_gate_relays=0),
    "mixing":      dict(originate_gate_relays=0),                       # keep base_cfg.mixing_lambda
    "gate":        dict(mixing_lambda=0.0),                            # keep base_cfg.originate_gate_relays
    "both":        dict(),                                             # both as set on base_cfg
    "timing_only": dict(originate_gate_relays=0, ttl=1e9),            # mixing at TTL=inf (drop-confound check)
}


def anonymity_defense_sweep(base_cfg, f, reps):
    """Measure mixing + receive-before-originate against the exposure baseline at coverage f.
    Per rep, all arms share one seed (identical cohort) so rank-1 is compared on the SAME-DETECTED-SET
    intersection (survivorship removed); the TTL=inf timing-only arm isolates timing-scramble from
    message-dropping. Every gain is an UPPER BOUND on the anonymity benefit; defense_gate credits a
    gain only if real (attack works, material drop, survives TTL=inf, enough relays, big intersection)."""
    mustloc = anonymity_sweep(base_cfg, [0.95], reps=1)["mustlocalize"]   # capability control (reuse PR-1)
    rows = []
    for rep in range(reps):
        seed = _seed_for(base_cfg.master_seed, 0, rep)
        arms = {}
        for mode, override in _DEFENSE_ARMS.items():
            cfg = replace(base_cfg, master_seed=seed, **override)
            art = _run_one_anonymity(cfg)
            recv = place_receivers(cfg, f, "uniform", cfg.rng(4))
            res, _u, _t = _score_arm(art, recv, cfg, cfg.rng(6), with_origin_vs_relay=(mode in ("gate", "both")))
            arms[mode] = {"rank0": {r["bid"]: (r["rank"] == 0) for r in res},
                          "detected": set(r["bid"] for r in res),
                          "relay_density": float(np.mean(list(art["relayed"].values()))) if art["relayed"] else 0.0,
                          "delivery": art["delivery"], "t50": art["t50"]}
        rows.append(arms)

    def _r1_on(arm_name, S):
        vals = [rows[r][arm_name]["rank0"][b] for r in range(reps) for b in S[r] if b in rows[r][arm_name]["rank0"]]
        return float(np.mean(vals)) if vals else 0.0

    S_mix = [rows[r]["baseline"]["detected"] & rows[r]["mixing"]["detected"] & rows[r]["timing_only"]["detected"]
             for r in range(reps)]
    S_gate = [rows[r]["baseline"]["detected"] & rows[r]["gate"]["detected"] for r in range(reps)]
    inter_mix = float(np.mean([len(s) for s in S_mix]))
    inter_gate = float(np.mean([len(s) for s in S_gate]))

    base_r1_m = _r1_on("baseline", S_mix)
    mix_r1 = _r1_on("mixing", S_mix)
    timing_r1 = _r1_on("timing_only", S_mix)
    base_r1_g = _r1_on("baseline", S_gate)
    gate_r1 = _r1_on("gate", S_gate)
    gate_relay_density = float(np.mean([rows[r]["gate"]["relay_density"] for r in range(reps)]))
    from .anonymity import DEFENSE_MIN_DROP
    timing_survives = timing_r1 <= base_r1_m * (1.0 - DEFENSE_MIN_DROP)   # gain persists at TTL=inf?

    mixing_verdict = defense_gate(base_r1_m, mix_r1, mustloc["ok"], timing_survives, intersection_size=inter_mix)
    gate_verdict = defense_gate(base_r1_g, gate_r1, mustloc["ok"], True,
                                relay_density_ok=(gate_relay_density >= MIN_RELAY_DENSITY), intersection_size=inter_gate)

    def _cost(arm):
        return {"delivery": float(np.mean([rows[r][arm]["delivery"] for r in range(reps)])),
                "rank1": _r1_on(arm, [rows[r][arm]["detected"] for r in range(reps)])}
    return {
        "mustlocalize": mustloc,
        "mixing": {"baseline_rank1": base_r1_m, "defended_rank1": mix_r1, "timing_only_rank1": timing_r1,
                   "intersection": inter_mix, "verdict": mixing_verdict, "cost": _cost("mixing")},
        "gate": {"baseline_rank1": base_r1_g, "defended_rank1": gate_r1, "relay_density": gate_relay_density,
                 "intersection": inter_gate, "verdict": gate_verdict, "cost": _cost("gate")},
        "both_cost": _cost("both"),
        "scope_tag": SCOPE_TAG, "defense_scope_tag": DEFENSE_SCOPE_TAG,
    }


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
