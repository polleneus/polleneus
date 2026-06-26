"""Time-stepped flooding engine with PER-STEP, FIXPOINT propagation.

A blob propagates the moment information becomes available. Each step:
  1. for every in-range pair, accrue airtime into a per-episode pool (t_setup paid once via
     setup_debt; goodput integrated with the step's local contention);
  2. expire dead blobs on every in-range node (decoupled from airtime, so a starved contact
     still sweeps);
  3. run the pair-exchange to a FIXPOINT across all funded pairs, so a multi-hop chain whose
     contacts all overlap within a single step completes regardless of node-index order
     (a single canonical pass under-delivered "backward" chains);
  4. forfeit unused whole-blob airtime (no banking idle airtime into a later burst).

Causality is enforced by per-(node, blob) ACQUISITION TIME: a node may only forward a blob
over a contact whose exit is >= the time it acquired the blob, and the delivery time is
max(contact entry, the source node's acquisition time). This makes both the reachable SET and the
delivery TIMES match the independent interval-reachability oracle (percolation.temporal_reachable).

Contacts are timed analytically by contact_interval (cell-list only prunes candidates), so the
contact graph is dt-independent; each closed contact is recorded as (i, j, entry, exit) in
self.episodes. Addressing-blind: knows only blob {id, created_at, ttl, size}; metrics decides
delivery via on_deliver(node, blob, now). one_hop (test mutant) disables forwarding.
"""
from __future__ import annotations
import numpy as np
from .cell_list import neighbor_pairs
from .geometry import contact_interval, in_range
from .policies import select_offers

_EPS = 1e-9
_INF = float("inf")


class Engine:
    def __init__(self, cfg, mob, buffers, budget, rng, on_deliver, one_hop=False, _pair_order=None,
                 record_positions=False):
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
        self.acquired: dict[tuple[int, int], float] = {}  # (node, blob_id) -> time it held the blob
        # PR-2 airtime accounting (per-episode billing; blob-unit binding tallies sum to unmet)
        self.charged_airtime = 0.0
        self.available_contact_time = 0.0
        self.offered_airtime = 0.0
        self.offered_blobs = 0
        self.served_blobs = 0
        self.setup_starved_blobs = 0
        self.quantization_blobs = 0
        self.contention_blobs = 0
        # slice-3 anonymity overlay: per-step position log (default off ⇒ bit-identical)
        self.record_positions = record_positions
        self.position_log: list = []
        # slice-3 PR-2 defenses (default off ⇒ bit-identical): Poisson mixing + receive-before-originate
        self._mix_rng = cfg.rng(5) if cfg.mixing_lambda > 0 else None   # ONE persistent generator
        self.forward_delay: dict[tuple[int, int], float] = {}            # (node, blob_id) -> Exp(lambda) hold
        self.relayed: dict[int, set] = {}                                # node -> set of distinct foreign ids forwarded
        self.gated_origins: set = set()                                  # blob ids subject to the originate-gate
        #   (only MEASURED cohort originations; background soup flows freely so the gate can't deadlock)

    def inject(self, blob, node_idx, gated=False) -> None:
        self.origin.setdefault(blob.id, node_idx)
        self.acquired[(node_idx, blob.id)] = blob.created_at  # origin holds it from creation
        if gated:                                             # subject to the receive-before-originate gate
            self.gated_origins.add(blob.id)
        self._draw_mix_delay(node_idx, blob.id)
        self.buffers[node_idx].offer(blob, now=self.t)

    def _draw_mix_delay(self, node_idx, blob_id) -> None:
        if self._mix_rng is not None:                          # Poisson mixing on -> hold before forwardable
            self.forward_delay[(node_idx, blob_id)] = float(self._mix_rng.exponential(1.0 / self.cfg.mixing_lambda))

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
        cs_r = r * cfg.cs_radius_mult
        if cs_r > r:                                       # carrier-sense (co-channel) population != connectivity
            cs_cand = neighbor_pairs(p0, cs_r + 2.0 * max_disp + _EPS, w, h, b)
            cs_deg = self._degrees(p0, cs_cand, cs_r, w, h, b)
        else:
            cs_deg = self._degrees(p0, cand, r, w, h, b)
        seen, active, expire_nodes = set(), [], set()
        for (i, j) in sorted(cand):  # canonical order -> deterministic
            iv = contact_interval(p0[i], v_leg[i], p0[j], v_leg[j], r, t, t + dt_step, w, h, b)
            key = (i, j)
            seen.add(key)
            if iv is None:
                if key in self.open:
                    self._close(key)
                continue
            enter, exit_ = iv
            expire_nodes.add(i)
            expire_nodes.add(j)
            n_contenders = int(max(cs_deg[i], cs_deg[j]))  # computed BEFORE open-dict (scope) + slope-aware setup
            if key not in self.open:
                self.open[key] = {"entry": enter, "last_end": exit_, "credit": 0.0,
                                  "setup_debt": self.budget.t_setup_at(n_contenders),
                                  "setup_floor": self.budget.t_setup_at(n_contenders),  # bill the RESERVED floor
                                  "n": n_contenders, "served": set(), "offered": set(),
                                  "setup_billed": False}
            st = self.open[key]
            st["last_end"] = exit_
            st["n"] = max(st["n"], n_contenders)
            self.available_contact_time += (exit_ - enter)
            pay = min(exit_ - enter, st["setup_debt"])     # amortize the handshake floor once
            st["setup_debt"] -= pay
            eff = self.budget.effective_goodput(n_contenders)
            st["credit"] += (exit_ - enter - pay) * eff / self.budget.blob_size
            for (src, dst) in ((i, j), (j, i)):            # offered = distinct blobs the peer lacks (once/step)
                st["offered"].update(bl.id for bl in self._offerable(src, self.buffers[dst].ids(), exit_))
            active.append((i, j, enter, exit_, st, eff))
        for nd in expire_nodes:                            # sweep dead blobs regardless of airtime
            self.buffers[nd].expire(t)
        progressed = True                                  # FIXPOINT: complete in-step multi-hop chains
        while progressed:
            progressed = False
            for (i, j, enter, exit_, st, eff) in active:
                allowed = int(st["credit"])
                if allowed <= 0:
                    continue
                moved, served_ids = self._exchange(i, j, allowed, enter, exit_)
                if moved:
                    st["credit"] -= moved
                    st["served"].update(served_ids)
                    st["offered"].update(served_ids)       # in-step multi-hop served blobs are offered too
                    if not st["setup_billed"]:             # one handshake floor per episode (the RESERVED floor)
                        self.charged_airtime += st["setup_floor"]
                        st["setup_billed"] = True
                    self.charged_airtime += moved * self.budget.blob_size / eff  # same eff as accrual -> <= usable
                    progressed = True
        for entry in active:                               # forfeit idle whole-blob airtime (no bursts)
            st = entry[4]
            if st["credit"] >= 1.0:
                st["credit"] -= int(st["credit"])
        for key in list(self.open):
            if key not in seen:
                self._close(key)
        if self.record_positions:                          # passive overlay recorder (anonymity slice)
            self.position_log.append((t, p0.copy()))
        self.t = t + dt_step

    def _close(self, key) -> None:
        st = self.open.pop(key)
        dur = st["last_end"] - st["entry"]
        self.episodes.append((key[0], key[1], st["entry"], st["last_end"]))
        self.durations.append(dur)
        n = st["n"]
        served = len(st["served"])
        offered = len(st["offered"])
        self.served_blobs += served
        self.offered_blobs += offered
        self.offered_airtime += self.budget.charged_airtime(offered, n) if offered else 0.0
        unmet = offered - served
        if unmet > 0:                                      # classify UNMET blobs (blob-unit binding tallies)
            t0 = self.budget.t_setup_at(n)
            capacity = self.budget.effective_goodput(n) * max(0.0, dur - t0) / self.budget.blob_size
            if t0 >= dur:
                self.setup_starved_blobs += unmet          # couldn't even handshake
            elif capacity < 1.0:
                self.quantization_blobs += unmet           # too short/low-rate for one whole blob
            else:
                self.contention_blobs += unmet             # could move blobs, backlog exceeded capacity

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

    def _offerable(self, src, peer_ids, exit_):
        cfg = self.cfg
        gate_g = cfg.originate_gate_relays
        gate_t = cfg.originate_gate_time
        out = []
        for bl in self.buffers[src].blobs():
            if bl.id in peer_ids:
                continue
            if self.one_hop and self.origin.get(bl.id) != src:   # negative control: no forwarding
                continue
            if self.acquired.get((src, bl.id), _INF) > exit_ + _EPS:  # causality: had it before contact end
                continue
            # mixing: not forwardable until the Exp(lambda) hold elapses (default 0.0 -> no-op)
            if self.acquired.get((src, bl.id), _INF) + self.forward_delay.get((src, bl.id), 0.0) > exit_ + _EPS:
                continue
            # receive-before-originate: src's OWN gated origination is held until src has relayed >= G
            # distinct foreign ids (and been alive >= T). Only MEASURED gated originations are held
            # (background soup is un-gated, so the gate can't deadlock the whole network). default no-op.
            if (gate_g or gate_t) and bl.id in self.gated_origins and self.origin.get(bl.id) == src:
                if len(self.relayed.get(src, ())) < gate_g or self.t < gate_t:
                    continue
            out.append(bl)
        return out

    def _exchange(self, i, j, k, enter, exit_):
        remaining, moved, served_ids = k, 0, []
        for (src, dst) in ((i, j), (j, i)):
            if remaining <= 0:
                break
            db = self.buffers[dst]
            for blob in select_offers(self._offerable(src, db.ids(), exit_), set(), remaining, self.rng):
                # causal + mixing: not before src acquired it AND its forward-hold elapsed
                deliver_t = max(enter, self.acquired[(src, blob.id)] + self.forward_delay.get((src, blob.id), 0.0))
                if db.offer(blob, deliver_t) == "Accepted":
                    self.acquired[(dst, blob.id)] = deliver_t
                    self._draw_mix_delay(dst, blob.id)                 # dst now holds it -> its own mixing hold
                    if self.origin.get(blob.id) != src:               # src relayed a FOREIGN id (gate accounting)
                        self.relayed.setdefault(src, set()).add(blob.id)
                    self.transmissions += 1
                    self.on_deliver(dst, blob, deliver_t)
                    remaining -= 1
                    moved += 1
                    served_ids.append(blob.id)
        return moved, served_ids

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
