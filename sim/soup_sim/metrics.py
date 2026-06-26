"""Scoring oracle + delivery/latency/overhead metrics.

This is the ONLY module that knows message src/dst (the oracle). The engine calls
on_deliver(node_idx, blob, now); a delivery counts the first time a message's true
recipient holds it. The delivery-ratio denominator is the FAIR-CHANCE cohort:
messages whose (created_at + ttl) <= warmup_end + measure_window, i.e. that had a full
TTL of in-window simulated time (excludes right-censored end-of-run messages).
"""
from __future__ import annotations


class Metrics:
    def __init__(self, cfg, warmup_end: float, measure_window: float):
        self.cfg = cfg
        self.warmup_end = warmup_end
        self.measure_window = measure_window
        self.oracle: dict[int, tuple[int, int]] = {}
        self.created: dict[int, float] = {}
        self.delivered_at: dict[int, float] = {}

    def register(self, blob, src: int, dst: int) -> None:
        self.oracle[blob.id] = (src, dst)
        self.created[blob.id] = blob.created_at

    def on_deliver(self, node_idx: int, blob, now: float) -> None:
        sd = self.oracle.get(blob.id)
        if sd is None:
            return
        _, dst = sd
        if node_idx == dst and blob.id not in self.delivered_at:
            self.delivered_at[blob.id] = now

    def fair_chance_ids(self) -> list[int]:
        end = self.warmup_end + self.measure_window
        return [bid for bid, c in self.created.items() if (c + self.cfg.ttl) <= end + 1e-9]

    def delivery_ratio(self) -> float:
        fc = self.fair_chance_ids()
        if not fc:
            return 0.0
        delivered = sum(1 for bid in fc if bid in self.delivered_at)
        return delivered / len(fc)

    def fair_chance_delivered(self) -> int:
        return sum(1 for bid in self.fair_chance_ids() if bid in self.delivered_at)

    def latencies(self) -> list[float]:
        return [self.delivered_at[bid] - self.created[bid]
                for bid in self.fair_chance_ids() if bid in self.delivered_at]

    def overhead_ratio(self, transmissions: int) -> float:
        d = self.fair_chance_delivered()
        return transmissions / d if d > 0 else float("inf")

    # --- PR-2 airtime metrics -------------------------------------------------
    def utilization(self, charged: float, available: float) -> float:
        return charged / available if available > 0 else 0.0

    def utilization_vs_offered(self, charged: float, offered_airtime: float) -> float:
        return charged / offered_airtime if offered_airtime > 0 else 0.0

    def circulated_per_min(self, transmissions_in_window: int, measure_window: float) -> float:
        minutes = measure_window / 60.0
        return transmissions_in_window / minutes if minutes > 0 else 0.0

    def delivery_cdf_points(self):
        """(time, cumulative-delivered-fraction) over the FULL fair-chance cohort, so TTL-censored
        (undelivered) messages count against the denominator. NOT a Kaplan-Meier estimator —
        all censoring is at a single time (TTL), so the empirical CDF quantile is the right stat."""
        fc = self.fair_chance_ids()
        total = len(fc)
        if total == 0:
            return []
        lat = sorted(self.delivered_at[b] - self.created[b] for b in fc if b in self.delivered_at)
        out, cum = [], 0
        for t in lat:
            cum += 1
            out.append((t, cum / total))
        return out

    def t50(self):
        """Time to 50% of the fair-chance cohort delivered; None when <50% ever delivered
        (censored — avoids the survivorship trap where delivered-only mean looks flattering)."""
        for (t, frac) in self.delivery_cdf_points():
            if frac >= 0.5:
                return t
        return None

    def delivered_only_mean_latency(self) -> float:
        lat = self.latencies()
        return float(sum(lat) / len(lat)) if lat else 0.0   # LOWER bound (survivorship)
