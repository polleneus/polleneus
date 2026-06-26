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
    from .percolation import placement
    w, h = cfg.width, cfg.height
    R_range = cfg.radius * (cfg.adversary_range_mult if cfg.adversary_range_mult > 0 else 1.0)
    f = float(min(max(f, 1e-6), 1.0))
    s = R_range * np.sqrt(np.pi / f)                    # grid spacing for disk-coverage ~ f
    nx = max(1, int(round(w / s)))
    ny = max(1, int(round(h / s)))
    xs = (np.arange(nx) + 0.5) * (w / nx)
    ys = (np.arange(ny) + 0.5) * (h / ny)
    grid = np.array([[x, y] for x in xs for y in ys], float)
    R = len(grid)
    if mode == "chokepoint":
        # budget-matched smart adversary: place the SAME receiver count near actual node positions
        # (where traffic is). Under RWP (~uniform node density) this ~= uniform; it only beats uniform
        # under clustered mobility (a named follow-up). NOT collapsed into blobs (that was strictly weaker).
        nodes = placement(cfg.n, w, h, rng)
        idx = rng.choice(len(nodes), size=min(R, len(nodes)), replace=False)
        pts = nodes[idx] + rng.normal(0.0, R_range * 0.1, (len(idx), 2))
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


def estimate(method, msg_hearings, receivers, cand_pos, rng, reach=None) -> dict:
    """Rank candidates by suspicion (LOWER score = more suspicious) + a point estimate.
    msg_hearings = list[(recv_idx, first_hear_time)]; cand_pos = (C,2) candidate positions at
    the reference time; reach = (C,R) predicted forward-reachability times (reachability only).

    first_spy      — point = earliest-hearing receiver's location; score = candidate distance to it.
    reachability   — diffusion-source: score = -correlation(predicted reach-times, observed hear-times)
                     over the heard receivers (robust to the unknown origination offset/scale).
    random_guess   — no-signal floor.
    """
    C = len(cand_pos)
    if method == "random_guess":
        return {"point": cand_pos[int(rng.integers(0, C))] if C else (0.0, 0.0),
                "scores": rng.permutation(C).astype(float)}
    if not msg_hearings:
        return {"point": (0.0, 0.0), "scores": np.zeros(C)}
    earliest_recv = min(msg_hearings, key=lambda rt: rt[1])[0]
    point = np.asarray(receivers[earliest_recv], float)
    if method == "first_spy":
        return {"point": point, "scores": np.linalg.norm(np.asarray(cand_pos, float) - point, axis=1)}
    if method == "reachability":
        rec_idx = [r for (r, _t) in msg_hearings]
        obs = np.array([t for (_r, t) in msg_hearings], float)
        if reach is None or len(rec_idx) < 2 or np.allclose(obs, obs[0]):
            # not enough gradient to correlate -> fall back to first-spy geometry
            return {"point": point, "scores": np.linalg.norm(np.asarray(cand_pos, float) - point, axis=1)}
        scores = np.zeros(C)
        for c in range(C):
            pred = np.asarray(reach[c], float)[rec_idx]
            if np.allclose(pred, pred[0]):
                scores[c] = 0.0                         # candidate predicts no gradient -> uninformative
            else:
                corr = np.corrcoef(pred, obs)[0, 1]
                scores[c] = -corr if np.isfinite(corr) else 0.0
        return {"point": np.asarray(cand_pos[int(np.argmin(scores))], float), "scores": scores}
    raise ValueError(f"unknown estimator method {method!r}")


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
