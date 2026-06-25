"""Time-stepped flooding engine.

Contacts are tracked as physical entry->exit EPISODES timed analytically by
contact_interval (cell-list only prunes candidate pairs), so the contact graph and
durations are dt-independent. The airtime budget (incl. the t_setup floor) is charged
ONCE per episode over its analytic duration, as a single shared pool split across both
directions (BLE half-duplex). The engine is addressing-blind: it knows only blob
{id, created_at, ttl, size}; whether a delivery counts is decided by the metrics oracle
via the on_deliver(node_idx, blob, now) callback.

settle_static_fixpoint() is the unbounded static path used by the percolation gate: it
iterates exchange to a fixpoint = connected-component reachability (true multi-hop).
"""
from __future__ import annotations
import numpy as np
from .cell_list import neighbor_pairs
from .geometry import contact_interval, in_range
from .policies import select_offers

_EPS = 1e-9


class Engine:
    def __init__(self, cfg, mob, buffers, budget, rng, on_deliver):
        self.cfg = cfg
        self.mob = mob
        self.buffers = buffers
        self.budget = budget
        self.rng = rng
        self.on_deliver = on_deliver
        self.t = 0.0
        self.open: dict[tuple[int, int], dict] = {}
        self.transmissions = 0
        self.durations: list[float] = []

    def inject(self, blob, node_idx) -> None:
        self.buffers[node_idx].offer(blob, now=self.t)

    # ---- dynamic time-stepped run -------------------------------------------
    def run_until(self, t_end: float) -> None:
        # Full dt steps, then ONE clamped partial step so self.t lands exactly on t_end
        # (no overshoot of warmup/injection/sample boundaries). self.open persists across
        # calls so a physically continuous contact stays ONE episode; call finalize() once
        # at the true end.
        dt = self.cfg.dt
        while self.t + dt <= t_end + _EPS:
            self._process_step(dt)
        rem = t_end - self.t
        if rem > _EPS:
            self._process_step(rem)
            self.t = t_end

    def _process_step(self, dt_step: float) -> None:
        cfg = self.cfg
        w, h, b, r = cfg.width, cfg.height, cfg.boundary, cfg.radius
        t = self.t
        p0 = np.asarray(self.mob.positions, float).copy()
        self.mob.step(dt_step)
        p1 = np.asarray(self.mob.positions, float)
        v_leg = (p1 - p0) / dt_step
        max_disp = float(np.max(np.linalg.norm(p1 - p0, axis=1))) if len(p0) else 0.0
        r_q = r + 2.0 * max_disp + _EPS
        cand = neighbor_pairs(p0, r_q, w, h, b)
        deg = self._degrees(p0, cand, r, w, h, b)
        seen = set()
        for (i, j) in cand:
            seen.add((i, j))
            iv = contact_interval(p0[i], v_leg[i], p0[j], v_leg[j], r, t, t + dt_step, w, h, b)
            key = (i, j)
            if iv is None:
                if key in self.open:
                    self._settle(key, self.open[key]["entry"], self.open[key]["last_end"], deg)
                    del self.open[key]
                continue
            enter, exit_ = iv
            in_at_end = exit_ >= t + dt_step - _EPS
            if key in self.open:
                if in_at_end:
                    self.open[key]["last_end"] = t + dt_step
                else:
                    self._settle(key, self.open[key]["entry"], exit_, deg)
                    del self.open[key]
            else:
                if in_at_end:
                    self.open[key] = {"entry": enter, "last_end": t + dt_step}
                else:
                    self._settle(key, enter, exit_, deg)  # complete sub-step episode
        for key in list(self.open.keys()):
            if key not in seen:
                self._settle(key, self.open[key]["entry"], self.open[key]["last_end"], deg)
                del self.open[key]
        self.t = t + dt_step

    def finalize(self) -> None:
        if not self.open:
            return
        cfg = self.cfg
        p = np.asarray(self.mob.positions, float)
        cand = neighbor_pairs(p, cfg.radius, cfg.width, cfg.height, cfg.boundary)
        deg = self._degrees(p, cand, cfg.radius, cfg.width, cfg.height, cfg.boundary)
        for key, st in list(self.open.items()):
            self._settle(key, st["entry"], st["last_end"], deg)
        self.open.clear()

    @staticmethod
    def _degrees(pos, cand, r, w, h, b):
        deg = np.zeros(len(pos), dtype=int)
        for (i, j) in cand:
            if in_range(pos[i], pos[j], r, w, h, b):
                deg[i] += 1
                deg[j] += 1
        return deg

    def _settle(self, key, entry, end, deg) -> None:
        i, j = key
        # The exchange happens DURING the contact, modeled at its start (entry): expire only
        # blobs already dead before the contact began, then transfer what was valid for it.
        now = entry
        self.buffers[i].expire(now)
        self.buffers[j].expire(now)
        duration = max(0.0, end - entry)
        self.durations.append(duration)
        n_local = max(int(deg[i]), int(deg[j]))
        k = self.budget.blobs_transferable(duration, n_local, self.rng)
        if k > 0:
            self._exchange(i, j, k, now)

    def _exchange(self, i, j, k, now) -> None:
        bi, bj = self.buffers[i], self.buffers[j]
        remaining = k
        for blob in select_offers(bi.blobs(), bj.ids(), remaining, self.rng):
            if remaining <= 0:
                break
            if bj.offer(blob, now) == "Accepted":
                self.transmissions += 1
                self.on_deliver(j, blob, now)
                remaining -= 1
        for blob in select_offers(bj.blobs(), bi.ids(), remaining, self.rng):
            if remaining <= 0:
                break
            if bi.offer(blob, now) == "Accepted":
                self.transmissions += 1
                self.on_deliver(i, blob, now)
                remaining -= 1

    def mean_contact_duration(self) -> float:
        return float(np.mean(self.durations)) if self.durations else 0.0

    # ---- static unbounded path (percolation gate) ---------------------------
    def settle_static_fixpoint(self) -> None:
        """Iterate exchange to a fixpoint = connected-component reachability (true multi-hop).
        PRECONDITION: unbounded buffers (no eviction) and non-expiring blobs; with a finite
        cap the result is order-dependent and is NOT component reachability. The percolation
        gate uses effectively-infinite caps/TTL so this precondition holds."""
        cfg = self.cfg
        pairs = neighbor_pairs(np.asarray(self.mob.positions, float), cfg.radius,
                               cfg.width, cfg.height, cfg.boundary)
        changed = True
        while changed:
            changed = False
            for (i, j) in pairs:
                bi, bj = self.buffers[i], self.buffers[j]
                for blob in bi.blobs():
                    if not bj.has(blob.id) and bj.offer(blob, 0.0) == "Accepted":
                        self.transmissions += 1
                        self.on_deliver(j, blob, 0.0)
                        changed = True
                for blob in bj.blobs():
                    if not bi.has(blob.id) and bi.offer(blob, 0.0) == "Accepted":
                        self.transmissions += 1
                        self.on_deliver(i, blob, 0.0)
                        changed = True
