"""CLI for the soup simulator.

  python run.py --preset static-cliff --out out/cliff.csv [--plot out/cliff.png]

static-cliff: the headline STATIC delivery-vs-density curve (component reachability over a
Poisson torus ensemble — the validated quantity behind the percolation gate). Its 0.5
crossing sits JUST above the connectivity threshold d_c~4.51 (pairwise delivery ~ S^2 crosses
0.5 near threshold, ~d 4.5-4.7 at venue-scale N; ~d 6-7 is delivery SATURATION 0.95-0.99).

Every number is an UPPER BOUND on real-world delivery (see README).
"""
from __future__ import annotations
import argparse
import os
import numpy as np

from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import (static_delivery_sweep, midpoint_with_ci, airtime_sweep, anonymity_sweep,
                               anonymity_defense_sweep, intersection_sweep)
from soup_sim.report import (write_csv, plot, airtime_to_csv_string, airtime_plot,
                             anonymity_to_csv_string, anonymity_plot, anonymity_defense_to_csv_string,
                             intersection_to_csv_string)
from soup_sim.anonymity import exposure_gate, EXPOSURE_RANK1


def base_cfg(seed: int) -> Config:
    return Config(
        n=0, width=400.0, height=400.0, radius=10.0, boundary="torus",
        mobility="static", speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e9,
        buffer_cap=10 ** 9, throughput_ideal=1e9, alpha=0.0, t_setup=0.0, p_fail=0.0,
        blob_size=1.0, warmup=0.0, measure_window=1.0, drain=0.0, n_messages=0,
        seen_margin=1e9, master_seed=seed,
    )


def airtime_cfg(seed: int) -> Config:
    # Conservative goodput ~100 kbps (12.5 kB/s); blobs ~256 B; provenance in README. beta is an
    # UNCALIBRATED free parameter (0.1 here) chosen in the regime where the collision turn-over is
    # observable; the headline reports the knee as a function of it alongside the linear band.
    return Config(
        n=0, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
        speed_min=2.0, speed_max=2.0, dt=0.5, ttl=120.0, buffer_cap=200, throughput_ideal=12_500.0,
        alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=256.0, warmup=30.0, measure_window=120.0,
        drain=0.0, n_messages=80, seen_margin=60.0, master_seed=seed,
        airtime_model="collision", beta=0.1, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0,
    )


def _run_static(args) -> None:
    cfg = base_cfg(args.seed)
    degrees = list(np.linspace(1.0, 12.0, 23))
    rows = static_delivery_sweep(cfg, degrees, reps=args.reps)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_csv(rows, cfg.manifest(), args.out)
    info = midpoint_with_ci(rows, np.random.default_rng(args.seed))
    print(f"wrote {args.out} ({len(rows)} density points, reps={args.reps})")
    print(f"delivery=0.5 crossing at mean-degree ~= {info['midpoint']:.2f}  CI {info['ci']}")
    print("note: connectivity threshold d_c~=4.51 (susceptibility peak, validated by the gate).")
    print("      delivery rises STEEPLY through it; the 0.5 crossing sits AT the threshold within")
    print("      finite-size error -- measured here, not assumed.")
    if args.plot:
        ok = plot(rows, args.plot)
        print(f"plot -> {args.plot}" if ok else "matplotlib not installed; skipped plot")


def _run_airtime_knee(args) -> None:
    cfg = airtime_cfg(args.seed)
    densities = list(np.linspace(2.0, 18.0, 9))
    coll = airtime_sweep(cfg, densities, reps=args.reps)
    lin = airtime_sweep(replace(cfg, airtime_model="linear"), densities, reps=args.reps)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(airtime_to_csv_string(coll["rows"], cfg.manifest()))
    print(f"wrote {args.out} ({len(densities)} density points, reps={args.reps})")
    print(f"predicted knee ~= {coll['predicted_knee_contenders']} CONTENDERS (1/beta); "
          "density-space knee is found empirically below.")
    print(f"COLLISION (primary): knee {coll['knee']['status']} "
          f"{('@d='+format(coll['knee']['knee'],'.2f')+' CI '+str(tuple(round(x,2) for x in coll['knee']['ci']))) if coll['knee']['status']=='knee' else ''}")
    print(f"LINEAR (optimistic sensitivity): knee {lin['knee']['status']}  <- model-uncertainty band")
    print(f"PUBLISH GATE: publish={coll['gate']['publish']}  ->  {coll['gate']['label']}")
    print("every number is an UPPER BOUND on real delivery (see README provenance + bias table).")
    if args.plot:
        ok = airtime_plot(coll, args.plot)
        print(f"plot -> {args.plot}" if ok else "matplotlib not installed; skipped plot")


def anonymity_cfg(seed: int) -> Config:
    return Config(
        n=120, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
        speed_min=2.0, speed_max=2.0, dt=0.5, ttl=120.0, buffer_cap=200, throughput_ideal=1e9,
        alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=30.0, measure_window=120.0,
        drain=0.0, n_messages=160, seen_margin=60.0, master_seed=seed, adversary_range_mult=1.0,
    )


def anonymity_report_lines(out, cfg, reps) -> list:
    """Build the CLI report lines. The exposure verdict is HARD-GATED on the must-localize
    capability control (no exposure claim if the estimator failed it). Every line set carries
    the scope tag. Extracted for testability."""
    head = [r for r in out["rows"] if r["arm"] == out["headline_arm"]]
    best = max(head, key=lambda r: r["rank1_prob"]) if head else {"rank1_prob": 0.0, "realized_coverage": 0.0}
    floor = 1.0 / cfg.n
    gate = exposure_gate(best["rank1_prob"], floor, best.get("beats_random", False), cfg.n_messages, reps)
    lines = [out["scope_tag"],
             f"headline arm = {out['headline_arm']}",
             f"MUST-LOCALIZE control: {out['mustlocalize']['label']}  (ok={out['mustlocalize']['ok']})"]
    if not out["mustlocalize"]["ok"]:
        lines += [
            "EXPOSURE: INCONCLUSIVE — estimator failed the capability control, so NO exposure claim is made",
            f"  (for reference only, ungated: peak rank-1 {best['rank1_prob']:.2f} @ coverage {best['realized_coverage']:.2f})",
            "  the modeled attack cannot localize even a slow source under full coverage, consistent with",
            "  epidemic flooding erasing the spatial-origin signal — a stronger estimator may change it.",
        ]
    else:
        lines.append(f"EXPOSURE: peak rank-1 {best['rank1_prob']:.2f} @ realized coverage "
                     f"{best['realized_coverage']:.2f}  ->  {gate['label']}")
    lines.append("note: every number is an UPPER BOUND on anonymity; intersection + insider NOT modeled.")
    return lines


def _run_anonymity(args) -> None:
    cfg = anonymity_cfg(args.seed)
    f_values = [0.1, 0.2, 0.35, 0.5, 0.7, 0.9]
    reps = max(args.reps, 6)
    out = anonymity_sweep(cfg, f_values, reps=reps)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(anonymity_to_csv_string(out["rows"], cfg.manifest(), out["scope_tag"]))
    print(f"wrote {args.out} ({len(out['rows'])} rows)")
    for line in anonymity_report_lines(out, cfg, reps):
        print(line)
    if args.plot:
        ok = anonymity_plot(out, args.plot)
        print(f"plot -> {args.plot}" if ok else "matplotlib not installed; skipped plot")


def anonymity_defense_cfg(seed: int) -> Config:
    # Same venue as the anonymity headline, with defenses ON (mixing + receive-before-originate
    # gate). drain lets mixing-delayed blobs land inside the window. Defenses are an UPPER BOUND on
    # protection: they are credited ONLY through defense_gate (must-localize baseline, TTL=inf
    # timing-only confound, relay-density, same-detected-set intersection).
    return replace(anonymity_cfg(seed), ttl=40.0, warmup=10.0, measure_window=40.0, drain=20.0,
                   seen_margin=40.0, mixing_lambda=0.05, originate_gate_relays=3)


def _run_anonymity_defenses(args) -> None:
    cfg = anonymity_defense_cfg(args.seed)
    reps = max(args.reps, 4)
    out = anonymity_defense_sweep(cfg, f=0.7, reps=reps)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(anonymity_defense_to_csv_string(out, cfg.manifest()))
    print(f"wrote {args.out} (2 defense arms @ coverage f=0.7, reps={reps})")
    print(out["scope_tag"])
    print(out["defense_scope_tag"])
    for arm in ("mixing", "gate"):
        a = out[arm]
        v = a["verdict"]
        print(f"{arm.upper():8s}: baseline rank-1 {a['baseline_rank1']:.2f} -> defended "
              f"{a['defended_rank1']:.2f}  (TTL=inf control {a['timing_only_rank1']:.2f}; "
              f"same-detected-set n={a['intersection']})  ->  {v['label']}")
        print(f"          cost: delivery {a['cost']['delivery']:.2f}  t50 {a['cost']['t50']:.1f}  "
              f"credited={v['credited']}")
    print("note: a credited defense means the rank-1 drop SURVIVED the TTL=inf control on THAT arm")
    print("      (i.e. it is timing-scramble/structural, not message-dropping). Un-credited != useless; see CSV.")
    print("      (t50=nan means the cohort never reached 50% delivery in the window; gate arms are scored")
    print("       against the stronger origin_vs_relay adversary -- the conservative direction.)")
    if args.plot:
        print("note: --plot is not supported for the anonymity-defenses preset (no plot written).")


def intersection_cfg(seed: int) -> Config:
    # Same venue as the anonymity headline (PR-1), long window so staggered originations + spread fit.
    return replace(anonymity_cfg(seed), ttl=120.0, warmup=30.0, measure_window=120.0, drain=20.0,
                   seen_margin=120.0, n_messages=120)


def _run_anonymity_intersection(args) -> None:
    cfg = intersection_cfg(args.seed)
    reps = max(args.reps, 4)
    out = intersection_sweep(cfg, k_values=[1, 2, 4, 8, 16], f=0.7, reps=reps, n_tracked=8, stride=2.0)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(intersection_to_csv_string(out, cfg.manifest()))
    print(f"wrote {args.out} (K-sweep @ coverage f=0.7, reps={reps}, tracked=8)")
    print(out["scope_tag"])
    print(out["intersection_scope_tag"])
    print(f"MUST-LOCALIZE control: {out['mustlocalize']['label']} (ok={out['mustlocalize']['ok']})")
    for r in out["rows"]:
        print(f"  K={r['k']:>2}: fused rank-1 borda {r['fused_rank1_borda']:.2f} "
              f"(score-sum {r['fused_rank1_score_sum']:.2f}; decoy {r['decoy_rank1']:.2f}; "
              f"rand {r['random_floor_fused']:.3f}; n={r['n_samples']})")
    print(f"VERDICT @K={out['headline_k']} (credited = LOWER fusion rule): {out['verdict']['label']}")
    print("note: every number is an UPPER BOUND on anonymity; device-linkage is ASSUMED given (PHY out")
    print("      of scope); the decoy is the most-central innocent relay — if it pins too, it's centrality.")
    if args.plot:
        print("note: --plot is not supported for the anonymity-intersection preset (no plot written).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset",
                    choices=["static-cliff", "airtime-knee", "anonymity", "anonymity-defenses",
                             "anonymity-intersection"],
                    default="static-cliff")
    ap.add_argument("--out", default="out/cliff.csv")
    ap.add_argument("--plot", default=None)
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()
    if args.preset == "airtime-knee":
        _run_airtime_knee(args)
    elif args.preset == "anonymity":
        _run_anonymity(args)
    elif args.preset == "anonymity-defenses":
        _run_anonymity_defenses(args)
    elif args.preset == "anonymity-intersection":
        _run_anonymity_intersection(args)
    else:
        _run_static(args)


if __name__ == "__main__":
    main()
