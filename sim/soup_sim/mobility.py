"""Mobility models: static-uniform (PRIMARY cliff probe) and Random Waypoint (overlay).

RWP draws a fresh speed in [speed_min, speed_max] (speed_min>0) per leg, which avoids
the classic RWP speed-decay; positions are relaxed toward the stationary distribution
by an internal burn-in before t=0. RWP is an explicitly-labeled OPTIMISTIC overlay;
the static-uniform model is the headline cliff probe (its density == theory's reduced density).
"""
from __future__ import annotations
import numpy as np
from .cell_list import neighbor_pairs


class Mobility:
    def __init__(self, mode, positions, velocities, w, h, smin, smax,
                 speeds=None, targets=None, rng=None,
                 boundary="torus", centers=None, home=None, cluster_sigma=0.0, cluster_leak=0.0):
        self.mode = mode
        self.positions = positions
        self.velocities = velocities
        self.w = w
        self.h = h
        self.smin = smin
        self.smax = smax
        self.speeds = speeds if speeds is not None else np.zeros(len(positions))
        self.targets = targets
        self.rng = rng
        self.boundary = boundary
        self.centers = centers
        self.home = home
        self.cluster_sigma = cluster_sigma
        self.cluster_leak = cluster_leak
        self.n_clusters = len(centers) if centers is not None else 0

    def _cluster_targets(self, idx) -> np.ndarray:
        """New targets for arrived nodes: near their home cluster, EXCEPT a `cluster_leak` fraction
        wander to a uniform-random arena point (so leak=1 == RWP for any sigma). Torus-wrap / wall-clip."""
        m = len(idx)
        homes = self.home[idx]
        pts = self.centers[homes] + self.rng.normal(0.0, self.cluster_sigma, (m, 2))
        wander = self.rng.random(m) < self.cluster_leak
        k = int(np.count_nonzero(wander))
        if k:
            pts[wander] = self.rng.uniform([0.0, 0.0], [self.w, self.h], (k, 2))
        if self.boundary == "torus":
            return np.mod(pts, [self.w, self.h])
        return np.clip(pts, 0.0, [self.w, self.h])

    def step(self, dt: float) -> None:
        if self.mode == "static":
            return
        if self.mode == "linear":  # deterministic constant-velocity motion (tests / simple model)
            self.positions = self.positions + self.velocities * dt
            return
        pos, tgt, sp = self.positions, self.targets, self.speeds
        rem = tgt - pos
        dist = np.linalg.norm(rem, axis=1)
        travel = sp * dt
        arrived = travel >= dist
        moving = (~arrived) & (dist > 0)
        if np.any(moving):
            pos[moving] += (rem[moving] / dist[moving, None]) * travel[moving, None]
        if np.any(arrived):
            idx = np.where(arrived)[0]
            pos[idx] = tgt[idx]
            if self.centers is not None:                      # clustered: cluster-aware retarget
                tgt[idx] = self._cluster_targets(idx)
            else:                                             # rwp: uniform retarget
                tgt[idx] = self.rng.uniform([0.0, 0.0], [self.w, self.h], (len(idx), 2))
            sp[idx] = self.rng.uniform(self.smin, self.smax, len(idx))
        rem2 = self.targets - self.positions
        d2 = np.linalg.norm(rem2, axis=1)
        self.velocities = np.where(d2[:, None] > 0, rem2 / np.where(d2[:, None] > 0, d2[:, None], 1.0) * sp[:, None], 0.0)

    def mean_speed(self) -> float:
        return float(np.mean(self.speeds)) if self.mode in ("rwp", "clustered") else 0.0


def make_mobility(cfg, rng) -> Mobility:
    n = cfg.n
    pos = rng.uniform([0.0, 0.0], [cfg.width, cfg.height], (n, 2))
    if cfg.mobility == "static":
        return Mobility("static", pos, np.zeros((n, 2)), cfg.width, cfg.height,
                        cfg.speed_min, cfg.speed_max)
    if cfg.mobility == "clustered":
        K = cfg.n_clusters
        centers = rng.uniform([0.0, 0.0], [cfg.width, cfg.height], (K, 2))
        home = np.arange(n) % K                              # round-robin -> balanced clusters

        def near_home():
            p = centers[home] + rng.normal(0.0, cfg.cluster_sigma, (n, 2))
            return (np.mod(p, [cfg.width, cfg.height]) if cfg.boundary == "torus"
                    else np.clip(p, 0.0, [cfg.width, cfg.height]))
        cpos = near_home()
        ctgt = near_home()
        cspeeds = rng.uniform(cfg.speed_min, cfg.speed_max, n)
        cmob = Mobility("clustered", cpos, np.zeros((n, 2)), cfg.width, cfg.height,
                        cfg.speed_min, cfg.speed_max, speeds=cspeeds, targets=ctgt, rng=rng,
                        boundary=cfg.boundary, centers=centers, home=home,
                        cluster_sigma=cfg.cluster_sigma, cluster_leak=cfg.cluster_leak)
        cdiag = (cfg.width ** 2 + cfg.height ** 2) ** 0.5
        cmean = max((cfg.speed_min + cfg.speed_max) / 2.0, 1e-9)
        for _ in range(min(int(5.0 * 0.52 * cdiag / cmean / cfg.dt), 20000)):
            cmob.step(cfg.dt)
        return cmob
    tgt = rng.uniform([0.0, 0.0], [cfg.width, cfg.height], (n, 2))
    speeds = rng.uniform(cfg.speed_min, cfg.speed_max, n)
    mob = Mobility("rwp", pos, np.zeros((n, 2)), cfg.width, cfg.height,
                   cfg.speed_min, cfg.speed_max, speeds=speeds, targets=tgt, rng=rng)
    diag = (cfg.width ** 2 + cfg.height ** 2) ** 0.5
    mean_speed = max((cfg.speed_min + cfg.speed_max) / 2.0, 1e-9)
    burnin_steps = int(5.0 * 0.52 * diag / mean_speed / cfg.dt)
    for _ in range(min(burnin_steps, 20000)):
        mob.step(cfg.dt)
    return mob


def mean_degree(positions, r, w, h, boundary) -> float:
    n = len(positions)
    if n < 2:
        return 0.0
    return 2.0 * len(neighbor_pairs(positions, r, w, h, boundary)) / n


def stationarity_ok(first_value: float, second_value: float, tol: float) -> bool:
    denom = max(abs(first_value), abs(second_value), 1e-9)
    return abs(first_value - second_value) / denom <= tol
