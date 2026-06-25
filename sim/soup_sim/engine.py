"""Time-stepped flooding engine.

Contacts are tracked as physical entry->exit EPISODES timed analytically by
contact_interval (cell-list only prunes candidate pairs), so the contact graph and
durations are dt-independent. The airtime budget (incl. the t_setup floor) is charged
ONCE per episode over its analytic duration, as a single shared pool, and exchange
iterates to a fixpoint within the episode. Episodes are processed/settled in a canonical
(entry, i, j) order so overlapping contacts are deterministic. Each settled contact is
recorded as (i, j, exit_time) in self.episodes, enabling the temporal-reachability gate.

The engine is addressing-blind: it knows only blob {id, created_at, ttl, size}; the
metrics oracle decides whether a delivery counts via on_deliver(node_idx, blob, now).

settle_static_fixpoint() is the unbounded static path used by the percolation gate.
The optional one_hop flag (testing) disables forwarding (a node only offers blobs it
ORIGINATED) — the negative control for the temporal-reachability gate.
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
        self._pair_order = _pair_order          # None | "reversed" (test hook for order-invariance)
        self.t = 0.0
        self.open: dict[tuple[int, int], dict] = {}
        self.transmissions = 0
        self.durations: list[float] = []
        self.episodes: list[tuple[int, int, float]] = []   # (i, j, exit_time)
        self.origin: dict[int, int] = {}        # blob.id -> node that originated it

    def inject(self, blob, node_idx) -> None:
        self.origin.setdefault(blob.id, node_idx)
        self.buffers[node_idx].offer(blob, now=self.t)

    # ---- dynamic time-stepped run -------------------------------------------
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
        if self._pair_order == "reversed":          # test hook: perturb input order; canonical sort below neutralizes it
            cand = list(reversed(cand))
        deg = self._degrees(p0, cand, r, w, h, b)
        # compute contact intervals, then process in canonical (enter, i, j) order
        triples = []
        for (i, j) in cand:
            iv = contact_interval(p0[i], v_leg[i], p0[j], v_leg[j], r, t, t + dt_step, w, h, b)
            triples.append((i, j, iv))
        triples.sort(key=lambda x: (x[2][0] if x[2] is not None else float("inf"), x[0], x[1]))
        seen = set()
        settles = []  # (exit_time, i, j, entry) — applied in exit order so propagation == oracle
        for (i, j, iv) in triples:
            key = (i, j)
            seen.add(key)
            if iv is None:
                if key in self.open:
                    settles.append((self.open[key]["last_end"], i, j, self.open[key]["entry"]))
                    del self.open[key]
                continue
            enter, exit_ = iv
            in_at_end = exit_ >= t + dt_step - _EPS
            if key in self.open:
                if in_at_end:
                    self.open[key]["last_end"] = t + dt_step
                else:
                    settles.append((exit_, i, j, self.open[key]["entry"]))
                    del self.open[key]
            else:
                if in_at_end:
                    self.open[key] = {"entry": enter, "last_end": t + dt_step}
                else:
                    settles.append((exit_, i, j, enter))  # complete sub-step episode
        for key in list(self.open):
            if key not in seen:
                settles.append((self.open[key]["last_end"], key[0], key[1], self.open[key]["entry"]))
                del self.open[key]
        for (ex, i, j, entry) in sorted(settles):           # settle in (exit, i, j) order
            self._settle((i, j), entry, ex, deg)
        self.t = t + dt_step

    def finalize(self) -> None:
        if not self.open:
            return
        cfg = self.cfg
        p = np.asarray(self.mob.positions, float)
        cand = neighbor_pairs(p, cfg.radius, cfg.width, cfg.height, cfg.boundary)
        deg = self._degrees(p, cand, cfg.radius, cfg.width, cfg.height, cfg.boundary)
        settles = [(st["last_end"], k[0], k[1], st["entry"]) for k, st in self.open.items()]
        for (ex, i, j, entry) in sorted(settles):           # settle in (exit, i, j) order == oracle
            self._settle((i, j), entry, ex, deg)
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
        self.episodes.append((i, j, end))
        now = entry  # exchange modeled at contact start: expire only blobs dead before it began
        self.buffers[i].expire(now)
        self.buffers[j].expire(now)
        duration = max(0.0, end - entry)
        self.durations.append(duration)
        n_local = max(int(deg[i]), int(deg[j]))
        k = self.budget.blobs_transferable(duration, n_local, self.rng)
        if k > 0:
            self._exchange(i, j, k, now)

    def _offerable(self, src, peer_ids):
        blobs = self.buffers[src].blobs()
        if self.one_hop:  # negative control: forward only blobs this node ORIGINATED
            blobs = [bl for bl in blobs if self.origin.get(bl.id) == src]
        return [bl for bl in blobs if bl.id not in peer_ids]

    def _exchange(self, i, j, k, now) -> None:
        remaining = k
        progressed = True
        while remaining > 0 and progressed:
            progressed = False
            for (src, dst) in ((i, j), (j, i)):
                db = self.buffers[dst]
                missing = self._offerable(src, db.ids())
                for blob in select_offers(missing, set(), remaining, self.rng):
                    if remaining <= 0:
                        break
                    deliver_t = max(now, blob.created_at)  # real time, not a metrics clamp
                    if db.offer(blob, deliver_t) == "Accepted":
                        self.transmissions += 1
                        self.on_deliver(dst, blob, deliver_t)
                        remaining -= 1
                        progressed = True

    def mean_contact_duration(self) -> float:
        return float(np.mean(self.durations)) if self.durations else 0.0

    # ---- static unbounded path (percolation gate) ---------------------------
    def settle_static_fixpoint(self) -> None:
        """Iterate exchange to a fixpoint = connected-component reachability (true multi-hop).
        PRECONDITION: unbounded buffers (no eviction) and non-expiring blobs; with a finite
        cap the result is order-dependent and is NOT component reachability."""
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
