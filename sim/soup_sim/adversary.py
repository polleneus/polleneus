"""Passive receiver-grid adversary (slice 3, post-hoc overlay).

The adversary is computed AFTER the real simulation from the engine's position log + the
per-(node, blob) acquire times (`acquired`) + blob hold lifetimes — it adds no engine nodes,
so it cannot perturb contention/delivery. Source-localization here is EPIDEMIC/diffusion
source estimation (the engine floods a component in one step and spreads via mobile holders),
NOT radio triangulation — estimators work off the recorded spread, not a propagation speed.

Every number this produces is an UPPER BOUND on anonymity (a stronger adversary localizes
better). See anonymity.py SCOPE_TAG.
"""
from __future__ import annotations
import numpy as np
from .geometry import dist2


def place_receivers(cfg, f, mode, rng) -> np.ndarray:
    """Return (R,2) receiver locations covering ~fraction f of the arena. mode:
    "uniform" = jittered grid; "chokepoint" = clustered toward hotspots (a budget-matched
    smart adversary; uniform-only would over-state anonymity)."""
    w, h, R_range = cfg.width, cfg.height, cfg.radius * max(cfg.adversary_range_mult, 1.0)
    f = float(min(max(f, 1e-6), 1.0))
    s = R_range * np.sqrt(np.pi / f)                    # grid spacing for disk-coverage ~ f
    nx = max(1, int(round(w / s)))
    ny = max(1, int(round(h / s)))
    xs = (np.arange(nx) + 0.5) * (w / nx)
    ys = (np.arange(ny) + 0.5) * (h / ny)
    grid = np.array([[x, y] for x in xs for y in ys], float)
    if mode == "chokepoint":
        # same receiver budget, concentrated in gaussian clusters around a few hotspots
        k = max(1, len(grid))
        n_hot = max(1, int(np.ceil(np.sqrt(len(grid)))))
        hot = rng.uniform([0.0, 0.0], [w, h], (n_hot, 2))
        idx = rng.integers(0, n_hot, k)
        pts = hot[idx] + rng.normal(0.0, R_range, (k, 2))
        return np.mod(pts, [w, h]) if cfg.boundary == "torus" else np.clip(pts, 0, [w, h])
    jit = rng.uniform(-0.25, 0.25, grid.shape) * np.array([w / nx, h / ny])
    pts = grid + jit
    return np.mod(pts, [w, h]) if cfg.boundary == "torus" else np.clip(pts, 0, [w, h])


def realized_coverage(receivers, adv_range, cfg, rng, n_mc=20000) -> float:
    """Monte-Carlo fraction of arena within adv_range of any receiver (torus-aware)."""
    if len(receivers) == 0:
        return 0.0
    pts = rng.uniform([0.0, 0.0], [cfg.width, cfg.height], (n_mc, 2))
    r2 = adv_range * adv_range
    covered = np.zeros(n_mc, dtype=bool)
    for L in receivers:
        covered |= dist2(pts, L, cfg.width, cfg.height, cfg.boundary) <= r2
    return float(np.mean(covered))


def hearings(receivers, adv_range, position_log, acquired, blob_expiry, cfg) -> dict:
    """{(recv_idx, blob_id): first_hear_time} — earliest log step where a holder of the blob
    (held over [acquire, expiry]) is within adv_range of the receiver. Hold-until-expiry
    ignores eviction ⇒ the adversary hears at least as much ⇒ conservative for the anonymity
    upper bound."""
    r2 = adv_range * adv_range
    out: dict = {}
    # group acquire times by blob for a tighter loop
    holders: dict = {}
    for (node, bid), t_acq in acquired.items():
        holders.setdefault(bid, []).append((node, t_acq))
    for (t, pos) in position_log:
        for bid, hs in holders.items():
            exp = blob_expiry.get(bid, float("inf"))
            for (node, t_acq) in hs:
                if t_acq - 1e-9 <= t <= exp + 1e-9:        # node holds bid at log time t
                    pk = pos[node]
                    for li, L in enumerate(receivers):
                        key = (li, bid)
                        if key not in out and dist2(pk, L, cfg.width, cfg.height, cfg.boundary) <= r2:
                            out[key] = t
    return out
