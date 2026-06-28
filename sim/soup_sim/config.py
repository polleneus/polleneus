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
    # P2 PR-2 origination defenses (all default OFF ⇒ engine bit-identical, zero new RNG on the off path).
    # Venue-wide self-loop cover floor: EVERY node emits byte-uniform PROPAGATING dummy roots into the soup
    # at this Poisson rate (per node, per measure-window-unit time). Dummies spread like any blob (sealed to
    # the emitter's own key; real-vs-dummy hidden) so the first-sighting graph carries roots from many
    # distinct emitter nodes. 0 ⇒ off (no dummies injected, no RNG drawn — bit-identical). (§10 cover floor.)
    cover_rate: float = 0.0
    # The WHICH-ROOT timing-aware adversary's ±Δt window (spec v0.4 §3): a dummy root is "plausibly-real"
    # iff its emission time lies within ±this of the real-origination time t*. An ADVERSARY capability
    # (post-hoc overlay), carried here so it travels in the manifest; 0 ⇒ only exactly-coincident roots are
    # plausibly-real (the strongest adversary admits no temporally-distant dummies).
    cover_timing_window: float = 0.0
    # Probabilistic, time-bounded origination license (liveness, NOT a leak reducer). Origination fires with
    # a per-step probability FLOORED at license_floor (>0 ⇒ never deadlocks) and CEILED to always fire by
    # license_max_latency_T. Measured post-hoc for deadlock-freedom + cadence-invariance. Both 0 ⇒ off.
    license_floor: float = 0.0         # per-step floor probability of releasing one's own origination (0 ⇒ off)
    license_max_latency_T: float = 0.0  # hard ceiling: the origination ALWAYS fires by t0 + T (0 ⇒ off)
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
    # P3 PR-1 clock-independent expiry (spec 2026-06-28; SCOPED-DOWN after code+security review). The SHIPPED
    # mechanisms are: H (clearance), B (spread cap), and an EXPIRY-ONLY clock with an EXPLICIT clock_trusted
    # input (driven by `blackout`). ALL default-inert ⇒ every existing slice is bit-identical:
    # H=None+B=None+sigma=0+blackout=False ⇒ engine takes the legacy expire(t) path and draws NO new RNG
    # (namespaces 10/11 untouched). See engine.py for the expiry predicate.
    hold_budget: float | None = None        # H: LOCAL hold-budget. A node drops a held blob when
    #   (local_now − local_receipt) >= H. Elapsed-since-receipt is OFFSET-INVARIANT (clock skew cancels) ⇒
    #   the clock-independent expiry that clears the soup. None ⇒ off (no hold-budget drop). NOT hop-energy.
    hop_energy_init: int | None = None      # B: anti-amplification SPREAD cap (separate from H). Origin starts
    #   at B; a receiver stores energy = source_energy−1; a copy that would arrive at 0 is not stored. Bounds
    #   the spread RADIUS (~B hops), does NOT clear the soup. None ⇒ off (energy carried-but-ignored, as today).
    clock_skew_sigma: float = 0.0           # per-node RTC offset ~ Normal(0, sigma), drawn from disjoint
    #   namespace cfg.rng(10,i), gated on sigma>0. The offset enters ONLY the expiry comparison — never
    #   contact/causality/acquisition/measurement timing (those stay TRUE global time). 0 ⇒ off (perfect clock).
    blackout: bool = False                  # EXPLICIT clock-trust input: no NTP / no trusted absolute clock ⇒
    #   ALL nodes clock_untrusted (origin-TTL path dropped network-wide; clearance falls to H). Also enables
    #   future-dated creation-ts (see blackout_future_max). This is the ONLY live driver of clock_trusted.
    blackout_future_max: float = 0.0        # if blackout, forge created_at into the future by U(0, this) drawn
    #   from disjoint namespace cfg.rng(11,id); causality still uses the TRUE origination time. Justification:
    #   a future-dated created_at (a) defeats the absolute origin-TTL test even on a trusted clock and (b)
    #   evades the oldest-by-created eviction (it looks YOUNGEST) — the point being that H, which keys on the
    #   TRUE receipt time not created_at, still clears it. 0 ⇒ no forging.
    # --- DEFERRED (open problem; NOT wired to live behavior; carried only for the manifest + the §4 bound) ---
    clock_trust_threshold: float | None = None  # DEFERRED. Intended as the tolerated-offset bound for the
    #   monotonicity residual gate (a slow clock within ±threshold can extend life up to TTL+threshold). The
    #   gossip-median auto-flag that would USE it is DEFERRED: median-of-created_at tracks the center-of-mass of
    #   message AGES, not "now", so |local_now − median| grows with elapsed time even for a perfect clock ⇒ it
    #   spuriously flags untrusted. A robust passive clock-trust signal from the sealed created_at stream is an
    #   OPEN PROBLEM. Not read by the engine; clearance (H) does not depend on it.
    creation_ts_clamp: float | None = None  # DEFERRED. A coarse admission-time future-clamp depended on the same
    #   broken median (and false-rejects honest-fresh mail on a lagging median), so it is NOT wired. Residual:
    #   a forged-future created_at on a TRUSTED clock is cleared anyway by H (H uses the true receipt time).

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
        if self.cover_rate < 0.0:
            raise ValueError("cover_rate must be >= 0")
        if self.cover_timing_window < 0.0:
            raise ValueError("cover_timing_window must be >= 0")
        if not 0.0 <= self.license_floor <= 1.0:
            raise ValueError("license_floor must be in [0, 1]")
        if self.license_max_latency_T < 0.0:
            raise ValueError("license_max_latency_T must be >= 0")
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
        # P3 clock-independent expiry knobs (None ⇒ off; otherwise must be a sane magnitude)
        if self.hold_budget is not None and self.hold_budget <= 0.0:
            raise ValueError("hold_budget (H) must be > 0 when set (None ⇒ off)")
        if self.hop_energy_init is not None and self.hop_energy_init < 1:
            raise ValueError("hop_energy_init (B) must be >= 1 when set (None ⇒ off)")
        if self.clock_skew_sigma < 0.0:
            raise ValueError("clock_skew_sigma must be >= 0")
        if self.clock_trust_threshold is not None and self.clock_trust_threshold < 0.0:
            raise ValueError("clock_trust_threshold must be >= 0 when set (None ⇒ off)")
        if self.creation_ts_clamp is not None and self.creation_ts_clamp < 0.0:
            raise ValueError("creation_ts_clamp must be >= 0 when set (None ⇒ off)")
        if self.blackout_future_max < 0.0:
            raise ValueError("blackout_future_max must be >= 0")

    def rng(self, *path: int) -> np.random.Generator:
        return make_rng(self.master_seed, *path)

    def manifest(self) -> dict:
        return asdict(self)
