"""Density-aware airtime budget for one contact episode.

Effective throughput collapses with local contention (parent §6/§11). A handshake
floor (t_setup) means very short contacts transfer nothing; transfer is quantized
to whole blobs; reconciliation decode-failure (p_fail) thins the result. The result
is an UPPER BOUND on what a real BLE contact could move.
"""
from __future__ import annotations
import math


class AirtimeBudget:
    def __init__(self, throughput_ideal: float, alpha: float, t_setup: float,
                 p_fail: float, blob_size: float,
                 model: str = "linear", beta: float = 0.0, t_setup_slope: float = 0.0,
                 n_channels: int = 3):
        self.throughput_ideal = throughput_ideal
        self.alpha = alpha
        self.t_setup = t_setup
        self.p_fail = p_fail
        self.blob_size = blob_size
        self.model = model
        self.beta = beta
        self.t_setup_slope = t_setup_slope
        self.n_channels = max(1, n_channels)

    def t_setup_at(self, n_contenders: int) -> float:
        return self.t_setup + self.t_setup_slope * max(0, n_contenders)

    def effective_goodput(self, n_contenders: int) -> float:
        """PER-LINK goodput (bytes/time), MONOTONE DECREASING for both models (the system
        turn-over lives in n*goodput, not here):
        linear:    throughput/(1+alpha*n)             (~1/n; system n*goodput -> plateau)
        collision: throughput*exp(-beta*n/n_channels) (ALOHA; system n*goodput interior max at n_channels/beta)."""
        n = max(0, n_contenders)
        loss = 1.0 - self.p_fail
        if self.model == "collision":
            return self.throughput_ideal * math.exp(-self.beta * n / self.n_channels) * loss
        return self.throughput_ideal / (1.0 + self.alpha * n) * loss

    def charged_airtime(self, served_blobs: int, n_contenders: int) -> float:
        """Airtime a contact consumes for `served_blobs`: handshake floor (once) + service time.
        Returns 0 if nothing served (no contact billed). Used for the OFFERED-airtime figure;
        the engine bills service incrementally per step for utilization (see engine)."""
        if served_blobs <= 0:
            return 0.0
        return self.t_setup_at(n_contenders) + served_blobs * self.blob_size / self.effective_goodput(n_contenders)

    def blobs_transferable(self, duration: float, n_local: int, rng) -> int:
        usable = max(0.0, duration - self.t_setup)
        if usable <= 0.0:
            return 0
        eff = self.throughput_ideal / (1.0 + self.alpha * max(0, n_local))
        gross = int((usable * eff) / self.blob_size)  # whole blobs only
        if gross <= 0:
            return 0
        if self.p_fail <= 0.0:
            return gross
        if self.p_fail >= 1.0:
            return 0
        return int(rng.binomial(gross, 1.0 - self.p_fail))
