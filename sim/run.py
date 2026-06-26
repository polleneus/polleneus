"""CLI for the soup simulator.

  python run.py --preset static-cliff --out out/cliff.csv [--plot out/cliff.png]

static-cliff: the headline STATIC delivery-vs-density curve (component reachability over a
Poisson torus ensemble — the validated quantity behind the percolation gate). Its 0.5
crossing sits well above the connectivity threshold d_c~4.51 because pairwise delivery ~ S^2.

Every number is an UPPER BOUND on real-world delivery (see README).
"""
from __future__ import annotations
import argparse
import os
import numpy as np

from dataclasses import replace
from soup_sim.config import Config
from soup_sim.scenario import static_delivery_sweep, midpoint_with_ci, airtime_sweep, anonymity_sweep
from soup_sim.report import (write_csv, plot, airtime_to_csv_string, airtime_plot,
                             anonymity_to_csv_string, anonymity_plot)
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
    # UNCALIBRATED free parameter (0.3 here) chosen in the regime where the collision turn-over is
    # observable; the headline reports the knee as a function of it alongside the linear band.
    return Config(
        n=0, width=120.0, height=120.0, radius=10.0, boundary="torus", mobility="rwp",
        speed_min=2.0, speed_max=2.0, dt=0.5, ttl=120.0, buffer_cap=200, throughput_ideal=12_500.0,
        alpha=1.0, t_setup=0.05, p_fail=0.0, blob_size=256.0, warmup=30.0, measure_window=120.0,
        drain=0.0, n_messages=80, seen_margin=60.0, master_seed=seed,
        airtime_model="collision", beta=0.3, t_setup_slope=0.002, n_channels=3, cs_radius_mult=2.0,
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
    print(f"predicted knee ~= {coll['predicted_knee_contenders']} CONTENDERS (n_channels/beta); "
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


def _run_anonymity(args) -> None:
    cfg = anonymity_cfg(args.seed)
    f_values = [0.1, 0.2, 0.35, 0.5, 0.7, 0.9]
    out = anonymity_sweep(cfg, f_values, reps=max(args.reps, 6))
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        f.write(anonymity_to_csv_string(out["rows"], cfg.manifest(), out["scope_tag"]))
    head = [r for r in out["rows"] if r["arm"] == out["headline_arm"]]
    best = max(head, key=lambda r: r["rank1_prob"]) if head else {"rank1_prob": 0.0, "realized_coverage": 0.0}
    floor = 1.0 / cfg.n
    gate = exposure_gate(best["rank1_prob"], floor, best.get("beats_random", False), cfg.n_messages, max(args.reps, 6))
    print(out["scope_tag"])
    print(f"wrote {args.out} ({len(out['rows'])} rows; headline arm = {out['headline_arm']})")
    print(f"MUST-LOCALIZE control: {out['mustlocalize']['label']}  (ok={out['mustlocalize']['ok']})")
    if not out["mustlocalize"]["ok"]:
        print("  -> estimator did not pass the capability control; exposure numbers are INCONCLUSIVE (honest null).")
    print(f"EXPOSURE: peak rank-1 {best['rank1_prob']:.2f} @ realized coverage {best['realized_coverage']:.2f}"
          f"  ->  {gate['label']}")
    print("note: every number is an UPPER BOUND on anonymity; intersection + insider adversaries NOT modeled.")
    if args.plot:
        ok = anonymity_plot(out, args.plot)
        print(f"plot -> {args.plot}" if ok else "matplotlib not installed; skipped plot")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=["static-cliff", "airtime-knee", "anonymity"], default="static-cliff")
    ap.add_argument("--out", default="out/cliff.csv")
    ap.add_argument("--plot", default=None)
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()
    if args.preset == "airtime-knee":
        _run_airtime_knee(args)
    elif args.preset == "anonymity":
        _run_anonymity(args)
    else:
        _run_static(args)


if __name__ == "__main__":
    main()
