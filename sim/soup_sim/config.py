"""Simulation configuration + the RNG contract.

Edge convention (pinned): an edge exists iff center-to-center dist <= r, so the
expected degree d = lambda*pi*r^2 — the constant the continuum-percolation
threshold d_c ~= 4.51 is defined against.

RNG contract: there is no module-global RNG anywhere. Every random draw uses a
Generator obtained from Config.rng(*path) / make_rng(), so runs are deterministic
by master_seed and per-(density, replication, component) substreams are
order-independent via SeedSequence.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np


def make_rng(master_seed: int, *path: int) -> np.random.Generator:
    """Deterministic, order-independent substream generator."""
    return np.random.default_rng(np.random.SeedSequence([int(master_seed), *[int(p) for p in path]]))


@dataclass(frozen=True)
class Config:
    n: int
    width: float
    height: float
    radius: float
    boundary: str          # "torus" | "walls"
    mobility: str          # "static" | "rwp"
    speed_min: float
    speed_max: float
    dt: float
    ttl: float
    buffer_cap: int
    throughput_ideal: float
    alpha: float
    t_setup: float
    p_fail: float
    blob_size: float
    warmup: float
    measure_window: float
    drain: float
    n_messages: int
    seen_margin: float
    master_seed: int
    # PR-2 airtime model (behavior-preserving defaults: linear, no collision, contention=connectivity)
    airtime_model: str = "linear"     # "linear" (optimistic sensitivity) | "collision" (ALOHA primary)
    beta: float = 0.0                 # collision steepness; per-link goodput ~ exp(-beta*n) (no /n_channels)
    t_setup_slope: float = 0.0        # density-dependent setup: t_setup_at(n)=t_setup + slope*n
    n_channels: int = 3               # shared advertising channels
    cs_radius_mult: float = 1.0       # carrier-sense radius = cs_radius_mult * radius
    # Slice-3 anonymity: passive adversary sniffer range (0 ⇒ overlay off; bit-identical)
    adversary_range_mult: float = 0.0  # adversary receiver range = adversary_range_mult * radius

    def validate(self) -> None:
        if self.boundary not in ("torus", "walls"):
            raise ValueError(f"boundary must be torus|walls, got {self.boundary!r}")
        if self.mobility not in ("static", "rwp"):
            raise ValueError(f"mobility must be static|rwp, got {self.mobility!r}")
        if self.speed_min < 0 or self.speed_max < self.speed_min:
            raise ValueError("speed: require 0 <= speed_min <= speed_max")
        if self.mobility == "rwp" and self.speed_min <= 0:
            raise ValueError("rwp requires speed_min > 0 (avoids RWP speed decay)")
        if self.radius <= 0:
            raise ValueError("radius must be > 0")
        if self.speed_max * self.dt > self.radius / 4.0:
            raise ValueError(
                f"CFL: speed_max*dt={self.speed_max*self.dt} > radius/4={self.radius/4.0}"
            )
        if self.seen_margin < 0:
            raise ValueError("seen_margin must be >= 0")
        if self.buffer_cap <= 0:
            raise ValueError("buffer_cap must be > 0")
        if self.blob_size <= 0:
            raise ValueError("blob_size must be > 0 (engine divides airtime by it)")
        if self.throughput_ideal <= 0:
            raise ValueError("throughput_ideal must be > 0")
        if not 0.0 <= self.p_fail <= 1.0:
            raise ValueError("p_fail must be in [0, 1]")
        if self.alpha < 0:
            raise ValueError("alpha must be >= 0")
        if self.t_setup < 0:
            raise ValueError("t_setup must be >= 0")
        if self.airtime_model not in ("linear", "collision"):
            raise ValueError("airtime_model must be linear|collision")
        if self.beta < 0:
            raise ValueError("beta must be >= 0")
        if self.t_setup_slope < 0:
            raise ValueError("t_setup_slope must be >= 0")
        if self.n_channels < 1:
            raise ValueError("n_channels must be >= 1")
        if self.cs_radius_mult < 1.0:
            raise ValueError("cs_radius_mult must be >= 1 (carrier-sense >= connectivity range)")
        if self.adversary_range_mult < 0.0:
            raise ValueError("adversary_range_mult must be >= 0")

    def rng(self, *path: int) -> np.random.Generator:
        return make_rng(self.master_seed, *path)

    def manifest(self) -> dict:
        return asdict(self)
