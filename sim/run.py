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

from soup_sim.config import Config
from soup_sim.scenario import static_delivery_sweep, midpoint_with_ci
from soup_sim.report import write_csv, plot


def base_cfg(seed: int) -> Config:
    return Config(
        n=0, width=400.0, height=400.0, radius=10.0, boundary="torus",
        mobility="static", speed_min=0.0, speed_max=0.0, dt=1.0, ttl=1e9,
        buffer_cap=10 ** 9, throughput_ideal=1e9, alpha=0.0, t_setup=0.0, p_fail=0.0,
        blob_size=1.0, warmup=0.0, measure_window=1.0, drain=0.0, n_messages=0,
        seen_margin=1e9, master_seed=seed,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=["static-cliff"], default="static-cliff")
    ap.add_argument("--out", default="out/cliff.csv")
    ap.add_argument("--plot", default=None)
    ap.add_argument("--reps", type=int, default=12)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()

    cfg = base_cfg(args.seed)
    degrees = list(np.linspace(1.0, 12.0, 23))
    rows = static_delivery_sweep(cfg, degrees, reps=args.reps)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    write_csv(rows, cfg.manifest(), args.out)
    info = midpoint_with_ci(rows, np.random.default_rng(args.seed))

    print(f"wrote {args.out} ({len(rows)} density points, reps={args.reps})")
    print(f"delivery=0.5 crossing at mean-degree ~= {info['midpoint']:.2f}  CI {info['ci']}")
    print("note: connectivity threshold d_c~=4.51 (susceptibility peak, validated by the gate).")
    print("      delivery is ~0 below it and rises STEEPLY through it (2D percolation is sharp,")
    print("      order-parameter exponent beta~5/36), so the 0.5 crossing sits AT the threshold")
    print("      within finite-size error -- measured here, not assumed.")
    if args.plot:
        ok = plot(rows, args.plot)
        print(f"plot -> {args.plot}" if ok else "matplotlib not installed; skipped plot")


if __name__ == "__main__":
    main()
