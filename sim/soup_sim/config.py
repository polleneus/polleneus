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
    # Slice-3 PR-2 anonymity defenses (all default OFF ⇒ engine bit-identical)
    mixing_lambda: float = 0.0         # Poisson mixing: Exp(lambda) forward hold per blob (0 ⇒ no hold)
    originate_gate_relays: int = 0     # receive-before-originate: relay >= G distinct foreign ids before emitting own
    originate_gate_time: float = 0.0   # ...and/or be alive >= T before emitting own
    # Slice-4 clustered "gathering" mobility (used only when mobility == "clustered")
    n_clusters: int = 1                # number of cluster centers (gathering zones)
    cluster_sigma: float = 0.0         # intra-cluster Gaussian spread (arena units)
    cluster_leak: float = 0.0          # per-retarget prob. a node wanders uniformly (0=islands, 1=RWP)
    # P1 set-reconciliation cost model (all default OFF ⇒ zero overhead, zero new RNG draws, bit-identical).
    # Flat, density-scheduled airtime floor billed per funded contact-episode, INDEPENDENT of the symmetric
    # difference and exact set sizes (inv 4). S(n)=recon_c0+ceil(recon_k*n); cost=recon_cell_bytes*S(n).
    recon_cell_bytes: float = 0.0      # bytes per scheduled cell (8 = minisketch; 0 ⇒ OFF, exactly free)
    recon_c0: float = 0.0              # per-episode floor cells (the dominant conservative term, Δ≈0 regime)
    recon_k: float = 0.0               # cells per unit local density n (the density-scheduled term)
    # P2 PR-1 token rate-limit harness (spec §3). A POST-HOC overlay over the recorded contact graph;
    # these fields do NOT touch the engine (no new branch, no new RNG draw) — the harness is a separate
    # scenario function. Carried on Config only so they travel in the manifest and validate together.
    # All default OFF ⇒ every existing slice is bit-identical and these knobs are inert.
    token_rate_limit_mode: str = "off"  # "off" | "broken" | "anchored" | "gossip" (the acceptance regime)
    phy_session_quota: int = 0          # per-PHY-session quota Q: <= Q slots/holder-PHY-session (0 ⇒ off)
    gossip_delay: float = 0.0           # per-hop latency of the seen-nf gossip front (0 ⇒ UNPHYSICAL instantaneous)
    token_spend_interval: float = 0.0   # serialized-BLE-handshake spacing between consecutive spends (0 ⇒ burst:
    #   all of a static holder's co-present spends fire at ~t0, so gossip can never beat them — the no-rate-limit
    #   worst case). >0 spreads spends so the gossip front can RACE to later acceptors. The §4 headline is the
    #   slots/token RACE over the gossip-rate (gossip_delay) ÷ spend-rate (token_spend_interval) ratio.

    def validate(self) -> None:
        if self.boundary not in ("torus", "walls"):
            raise ValueError(f"boundary must be torus|walls, got {self.boundary!r}")
        if self.mobility not in ("static", "rwp", "clustered"):
            raise ValueError(f"mobility must be static|rwp|clustered, got {self.mobility!r}")
        if self.speed_min < 0 or self.speed_max < self.speed_min:
            raise ValueError("speed: require 0 <= speed_min <= speed_max")
        if self.mobility in ("rwp", "clustered") and self.speed_min <= 0:
            raise ValueError("rwp/clustered requires speed_min > 0 (avoids speed decay)")
        if self.mobility == "clustered":
            if self.n_clusters < 1:
                raise ValueError("n_clusters must be >= 1")
            if not 0.0 <= self.cluster_leak <= 1.0:
                raise ValueError("cluster_leak must be in [0, 1]")
            if self.cluster_sigma < 0.0:
                raise ValueError("cluster_sigma must be >= 0")
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
        if self.mixing_lambda < 0.0:
            raise ValueError("mixing_lambda must be >= 0")
        if self.originate_gate_relays < 0:
            raise ValueError("originate_gate_relays must be >= 0")
        if self.originate_gate_time < 0.0:
            raise ValueError("originate_gate_time must be >= 0")
        if self.recon_cell_bytes < 0.0:
            raise ValueError("recon_cell_bytes must be >= 0")
        if self.recon_c0 < 0.0:
            raise ValueError("recon_c0 must be >= 0")
        if self.recon_k < 0.0:
            raise ValueError("recon_k must be >= 0")
        if self.recon_cell_bytes > 0.0 and self.recon_c0 <= 0.0 and self.recon_k <= 0.0:
            # footgun: recon ON with S(n)=c0+ceil(k*n)=0 => cap=floor(0)=0 => ALL novel transfers capped
            # to zero at ~zero airtime cost (circulation silently zeroed). Require a real schedule.
            raise ValueError("recon_cell_bytes > 0 requires recon_c0 > 0 or recon_k > 0 (a real schedule)")
        if self.token_rate_limit_mode not in ("off", "broken", "anchored", "gossip"):
            raise ValueError("token_rate_limit_mode must be off|broken|anchored|gossip, "
                             f"got {self.token_rate_limit_mode!r}")
        if self.phy_session_quota < 0:
            raise ValueError("phy_session_quota must be >= 0")
        if self.gossip_delay < 0.0:
            raise ValueError("gossip_delay must be >= 0")
        if self.token_spend_interval < 0.0:
            raise ValueError("token_spend_interval must be >= 0")

    def rng(self, *path: int) -> np.random.Generator:
        return make_rng(self.master_seed, *path)

    def manifest(self) -> dict:
        return asdict(self)
