"""Density-aware airtime budget for one contact episode.

Effective throughput collapses with local contention (parent §6/§11). A handshake
floor (t_setup) means very short contacts transfer nothing; transfer is quantized
to whole blobs; reconciliation decode-failure (p_fail) thins the result. The result
is an UPPER BOUND on what a real BLE contact could move.
"""
from __future__ import annotations


class AirtimeBudget:
    def __init__(self, throughput_ideal: float, alpha: float, t_setup: float,
                 p_fail: float, blob_size: float):
        self.throughput_ideal = throughput_ideal
        self.alpha = alpha
        self.t_setup = t_setup
        self.p_fail = p_fail
        self.blob_size = blob_size

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
