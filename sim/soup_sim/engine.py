"""Time-stepped flooding engine with PER-STEP propagation.

A blob propagates at the moment information becomes available: every step, each in-range
pair exchanges blobs the peer lacks (drawing from a per-episode airtime pool that
accumulates over the contact — t_setup paid once, goodput integrated with the step's local
contention). This makes delivery match physical time-respecting reachability even when
contacts overlap or nest (the lazy settle-at-exit model got this wrong). Contacts are timed
analytically by contact_interval (cell-list only prunes candidates), so the contact graph is
dt-independent. Each closed contact is recorded as (i, j, entry, exit) in self.episodes,
the input to the independent interval-reachability oracle.

Addressing-blind: knows only blob {id, created_at, ttl, size}; metrics decides delivery via
on_deliver(node, blob, now). Causality: a blob is never delivered over a contact that ended
before it existed. one_hop (test mutant) disables forwarding (negative control).
"""
from __future__ import annotations
import numpy as np
from .cell_list import neighbor_pairs
from .geometry import contact_interval, in_range
from .policies import select_offers

_EPS = 1e-9


class Engine:
    def __init__(self, cfg, mob, buffers, budget, rng, on_deliver, one_hop=False, _pair_order=None):
        self.cfg = cfg
        self.mob = mob
        self.buffers = buffers
        self.budget = budget
        self.rng = rng
        self.on_deliver = on_deliver
        self.one_hop = one_hop
        self._pair_order = _pair_order
        self.t = 0.0
        self.open: dict[tuple[int, int], dict] = {}
        self.transmissions = 0
        self.durations: list[float] = []
        self.episodes: list[tuple[int, int, float, float]] = []  # (i, j, entry, exit)
        self.origin: dict[int, int] = {}

    def inject(self, blob, node_idx) -> None:
        self.origin.setdefault(blob.id, node_idx)
        self.buffers[node_idx].offer(blob, now=self.t)

    def run_until(self, t_end: float) -> None:
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
        if self._pair_order == "reversed":
            cand = list(reversed(cand))
        deg = self._degrees(p0, cand, r, w, h, b)
        triples = []
        for (i, j) in cand:
            iv = contact_interval(p0[i], v_leg[i], p0[j], v_leg[j], r, t, t + dt_step, w, h, b)
            triples.append((i, j, iv))
        triples.sort(key=lambda x: (x[0], x[1]))  # canonical order -> deterministic overlaps
        seen = set()
        for (i, j, iv) in triples:
            key = (i, j)
            seen.add(key)
            if iv is None:
                if key in self.open:
                    self._close(key)
                continue
            enter, exit_ = iv
            seg = exit_ - enter
            if key not in self.open:
                self.open[key] = {"entry": enter, "last_end": exit_,
                                  "setup_debt": self.budget.t_setup, "credit": 0.0}
            st = self.open[key]
            st["last_end"] = exit_
            pay = min(seg, st["setup_debt"])           # amortize the handshake floor once
            st["setup_debt"] -= pay
            eff = self.budget.effective_goodput(int(max(deg[i], deg[j])))
            st["credit"] += (seg - pay) * eff / self.budget.blob_size
            allowed = int(st["credit"])
            if allowed > 0:
                self.buffers[i].expire(enter)
                self.buffers[j].expire(enter)
                st["credit"] -= self._exchange(i, j, allowed, enter, exit_)
        for key in list(self.open):
            if key not in seen:
                self._close(key)
        self.t = t + dt_step

    def _close(self, key) -> None:
        st = self.open.pop(key)
        self.episodes.append((key[0], key[1], st["entry"], st["last_end"]))
        self.durations.append(st["last_end"] - st["entry"])

    def finalize(self) -> None:
        for key in list(self.open):          # per-step model already exchanged; just record open contacts
            self._close(key)

    @staticmethod
    def _degrees(pos, cand, r, w, h, b):
        deg = np.zeros(len(pos), dtype=int)
        for (i, j) in cand:
            if in_range(pos[i], pos[j], r, w, h, b):
                deg[i] += 1
                deg[j] += 1
        return deg

    def _offerable(self, src, peer_ids, end):
        blobs = self.buffers[src].blobs()
        if self.one_hop:                      # negative control: forward only originated blobs
            blobs = [bl for bl in blobs if self.origin.get(bl.id) == src]
        # causality: a blob can only move over a contact that was open after it existed
        return [bl for bl in blobs if bl.id not in peer_ids and bl.created_at <= end + _EPS]

    def _exchange(self, i, j, k, now, end) -> int:
        remaining, moved, progressed = k, 0, True
        while remaining > 0 and progressed:
            progressed = False
            for (src, dst) in ((i, j), (j, i)):
                db = self.buffers[dst]
                for blob in select_offers(self._offerable(src, db.ids(), end), set(), remaining, self.rng):
                    if remaining <= 0:
                        break
                    deliver_t = max(now, blob.created_at)   # real time within the contact
                    if db.offer(blob, deliver_t) == "Accepted":
                        self.transmissions += 1
                        self.on_deliver(dst, blob, deliver_t)
                        remaining -= 1
                        moved += 1
                        progressed = True
        return moved

    def mean_contact_duration(self) -> float:
        return float(np.mean(self.durations)) if self.durations else 0.0

    def settle_static_fixpoint(self) -> None:
        """Static unbounded path for the percolation gate: iterate exchange to a fixpoint =
        connected-component reachability. PRECONDITION: unbounded buffers + non-expiring blobs."""
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
