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
import math
from dataclasses import replace
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
        # P1 set-reconciliation cost (default off ⇒ NO new branch executes ⇒ bit-identical, no RNG touched).
        # Flat density-scheduled airtime floor billed per funded episode; deterministic, no sampling.
        self._recon_on = cfg.recon_cell_bytes > 0
        self.recon_capped_episodes = 0                                   # internal metric (not on the wire)
        # slice-3 PR-2 defenses (default off ⇒ bit-identical): Poisson mixing + receive-before-originate
        self._mixing_on = cfg.mixing_lambda > 0                          # no RNG touched when off ⇒ bit-identical
        self.forward_delay: dict[tuple[int, int], float] = {}            # (node, blob_id) -> Exp(lambda) hold
        self.relayed: dict[int, set] = {}                                # node -> set of distinct foreign ids forwarded
        self.gated_origins: set = set()                                  # blob ids subject to the originate-gate
        #   (only MEASURED cohort originations; background soup flows freely so the gate can't deadlock)
        # P3 clock-independent expiry (spec 2026-06-28). ALL default-inert ⇒ the legacy expire(t) path runs and
        # NO new RNG is drawn (namespaces 10/11 untouched) ⇒ every existing slice is bit-identical.
        self._H = cfg.hold_budget                       # local hold-budget (clearance); None ⇒ off
        self._B = cfg.hop_energy_init                   # hop-energy spread cap (separate); None ⇒ off
        self._offset_on = cfg.clock_skew_sigma > 0.0    # per-node RTC offset (EXPIRY-ONLY)
        # clock_trusted is an EXPLICIT input, NOT auto-derived: the clock is trusted unless blackout is set.
        # (The gossip-median auto-flag was DEFERRED — median-of-created_at tracks message-age center-of-mass,
        #  not "now", so |local_now − median| grows with elapsed time even for a perfect clock. A robust
        #  passive clock-trust signal from the sealed created_at stream is an open problem; see config.py.
        #  Clearance via H never depends on it.)
        self._blackout = bool(cfg.blackout)
        self._future_on = self._blackout and cfg.blackout_future_max > 0.0
        # P3 PR-2 density-adaptive hold-budget. When on, H_eff per node = H_min + (H_max−H_min)·(1−occ)^k with
        # occ = len(store)/cap (clock-free) ⇒ offset-invariance preserved (H_eff is still a threshold on
        # elapsed-since-receipt). When on, the fixed self._H is IGNORED. Off ⇒ self._H_eff returns self._H.
        self._H_adaptive = bool(cfg.hold_budget_adaptive)
        self._H_min = cfg.hold_budget_min
        self._H_max = cfg.hold_budget_max
        self._H_k = cfg.hold_budget_shape_k
        # "hold-budget engaged at all" — drives receipt-building + the H_eff path (fixed OR adaptive)
        self._H_on = (self._H is not None) or self._H_adaptive
        # the extended expiry sweep runs iff an expiry knob is engaged (else the legacy call → bit-identical)
        self._expiry_ext = (self._H_on or self._offset_on or self._blackout)
        # per-node RTC offset: drawn from DISJOINT namespace 10, gated on sigma>0 (no RNG drawn when off)
        self.clock_offset = ([float(cfg.rng(10, i).normal(0.0, cfg.clock_skew_sigma)) for i in range(cfg.n)]
                             if self._offset_on else None)

    def inject(self, blob, node_idx, gated=False) -> None:
        cfg = self.cfg
        if self._B is not None and blob.hop_energy is None:   # origin starts at full hop-energy B
            blob = replace(blob, hop_energy=self._B)
        receipt_t = blob.created_at                            # legacy: acquired = created_at (UNCHANGED off-path)
        if self._future_on:                                   # blackout: forge a FUTURE wire-ts, keep TRUE causality
            receipt_t = self.t                                #   acquisition = true origination (delivery graph intact)
            fwd = float(cfg.rng(11, int(blob.id)).uniform(0.0, cfg.blackout_future_max))
            blob = replace(blob, created_at=self.t + fwd)     #   forged created_at defeats the absolute origin-TTL test
        self.origin.setdefault(blob.id, node_idx)
        self.acquired[(node_idx, blob.id)] = receipt_t        # CAUSALITY: true origination time, NEVER the forged ts
        if gated:                                             # subject to the receive-before-originate gate
            self.gated_origins.add(blob.id)
        self._draw_mix_delay(node_idx, blob.id)
        self.buffers[node_idx].offer(blob, now=self.t)

    def _draw_mix_delay(self, node_idx, blob_id) -> None:
        # Hold is keyed deterministically on (blob, holder) — NOT a persistent generator — so a given
        # (blob, holder) gets the SAME Exp(lambda) hold regardless of delivery order or which defense arm
        # runs. This is what makes the mixing vs TTL=inf timing-only control a fair comparison (same
        # timing scramble, only message survival differs); a lazy order-dependent draw would confound it.
        if self._mixing_on:                                    # Poisson mixing on -> hold before forwardable
            self.forward_delay[(node_idx, blob_id)] = float(
                self.cfg.rng(5, int(blob_id), int(node_idx)).exponential(1.0 / self.cfg.mixing_lambda))

    # --- P3 clock-independent expiry helpers (all no-ops / true-time on the default-inert path) -------------
    def _offset(self, nd: int) -> float:
        """Node nd's RTC offset; 0.0 when the clock model is off. EXPIRY-ONLY (never causality/measurement)."""
        return self.clock_offset[nd] if self.clock_offset is not None else 0.0

    def _clock_trusted(self, nd: int, now: float) -> bool:
        """clock_trusted gate for the origin-TTL path — an EXPLICIT input, not auto-derived. Trusted unless
        blackout (no NTP / no trusted absolute clock). The deferred passive auto-flag is NOT in this path, so
        clearance (H) can never be defeated by a mis-estimated clock-trust signal."""
        return not self._blackout

    def _H_eff(self, nd: int) -> float | None:
        """Effective hold-budget for node nd this sweep (PR-2). Off ⇒ the fixed self._H (None ⇒ no H drop).
        Adaptive ⇒ H_min + (H_max−H_min)·(1−occ)^k with occ = len(store)/cap clamped to [0,1] — a CLOCK-FREE
        load signal, so the comparison against elapsed-since-receipt stays offset-invariant. Occupancy is
        snapshotted at sweep start; H_eff ∈ [H_min, H_max] so clearance stays bounded and the soup still clears."""
        if not self._H_adaptive:
            return self._H
        occ = len(self.buffers[nd].store) / self.buffers[nd].cap
        occ = 0.0 if occ < 0.0 else (1.0 if occ > 1.0 else occ)
        # H_eff = H_min + (H_max−H_min)·(1 − occ^k). occ=0 ⇒ H_max, occ=1 ⇒ H_min, monotone↓ in occ.
        # k=1 ⇒ linear; k>1 ⇒ holds near H_max until the buffer is nearly full, then sheds sharply (shed late).
        return self._H_min + (self._H_max - self._H_min) * (1.0 - occ ** self._H_k)

    def _recon_cells(self, n: int) -> float:
        """Scheduled cell count S(n) = recon_c0 + ceil(recon_k * n), a pure function of the public
        local-density proxy n — independent of the symmetric difference and exact set sizes (inv 4)."""
        return self.cfg.recon_c0 + math.ceil(self.cfg.recon_k * max(0, n))

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
                                  "setup_billed": False,
                                  # P1 reconciliation: a recon-debt amortized across funded steps like
                                  # setup_debt (dt-invariant, never under-bills c0); recon_n freezes S(n)
                                  # at first-bill so the schedule can't drift as st["n"] grows mid-episode.
                                  "recon_debt": 0.0, "recon_billed": False, "recon_n": None,
                                  "recon_capped": False}
            st = self.open[key]
            st["last_end"] = exit_
            st["n"] = max(st["n"], n_contenders)
            self.available_contact_time += (exit_ - enter)
            pay = min(exit_ - enter, st["setup_debt"])     # amortize the handshake floor once
            st["setup_debt"] -= pay
            avail = exit_ - enter - pay                     # post-setup contact time accrued this step
            eff = self.budget.effective_goodput(n_contenders)
            st["credit"] += avail * eff / self.budget.blob_size
            if self._recon_on and eff > 0.0 and not st["recon_billed"]:
                # P1: flat density-scheduled reconciliation floor, billed per funded episode BEFORE any
                # blob transfer (competes for the same airtime, even if 0 blobs move). Difference-independent
                # (inv 4). Amortized as a recon-DEBT across funded steps EXACTLY like setup_debt, so the full
                # c0 schedule is always eventually charged (no under-bill when the first step is short) and
                # charged_airtime is dt-INVARIANT. Each step pays at most that step's post-setup contact time
                # (avail) so utilization stays <= 1. S(n) is FROZEN at first-bill (recon_n) so the schedule
                # can't drift as st["n"] grows. recon_billed flips only when the FULL debt is paid.
                if st["recon_n"] is None:                   # first funded step: open the debt at S(recon_n)
                    # NAMED OPTIMISTIC GAP: S(recon_n)/eff(recon_n) is frozen at the first funded step, so if
                    # the crowd (n) grows mid-debt the schedule is UNDER-billed (cheaper than the realized
                    # density). This is consistent with the once-per-episode frozen-schedule semantics; a
                    # follow-up could re-price the unpaid debt at the current n. Direction is optimistic.
                    st["recon_n"] = st["n"]
                    st["recon_debt"] = self.cfg.recon_cell_bytes * self._recon_cells(st["recon_n"]) / eff
                recon_pay = min(st["recon_debt"], avail)    # pay down at most this step's post-setup airtime
                st["recon_debt"] -= recon_pay
                self.charged_airtime += recon_pay           # same eff as accrual => <= usable airtime
                st["credit"] -= recon_pay * eff / self.budget.blob_size
                if st["recon_debt"] <= _EPS:
                    st["recon_billed"] = True
            for (src, dst) in ((i, j), (j, i)):            # offered = distinct blobs the peer lacks (once/step)
                st["offered"].update(bl.id for bl in self._offerable(src, self.buffers[dst].ids(), exit_))
            active.append((i, j, enter, exit_, st, eff))
        for nd in expire_nodes:                            # sweep dead blobs regardless of airtime
            if self._expiry_ext:                           # P3 clock-independent expiry (H / clock / blackout)
                receipt = ({bid: self.acquired.get((nd, bid)) for bid in self.buffers[nd].ids()}
                           if self._H_on else None)
                self.buffers[nd].expire(t, hold_budget=self._H_eff(nd), receipt=receipt,
                                        clock_trusted=self._clock_trusted(nd, t),
                                        clock_offset=self._offset(nd))
            else:
                self.buffers[nd].expire(t)                  # legacy path → bit-identical
        progressed = True                                  # FIXPOINT: complete in-step multi-hop chains
        while progressed:
            progressed = False
            for (i, j, enter, exit_, st, eff) in active:
                allowed = int(st["credit"])
                room = None
                if self._recon_on:                         # circulation cap: <= floor(S(n)) NOVEL blobs/episode
                    # deterministic sec.3 cap(n) throttle: the schedule recovers at most floor(S(n)) novel
                    # blobs this episode; the rest waits for a future contact (a circulation haircut, NOT
                    # extra bytes). SIMPLIFICATION vs the spec's cap(rho)=floor(S/overhead)-c0_reserve: we
                    # take overhead=1 and c0_reserve=0 (the minisketch primary cost: 1 field element/cell,
                    # the cheapest defensible upper bound) => cap = floor(S(n)). S(n) uses the FROZEN
                    # recon_n (falls back to st["n"] only on the eff==0 path where nothing moves anyway).
                    cap_n = st["recon_n"] if st["recon_n"] is not None else st["n"]
                    room = int(self._recon_cells(cap_n)) - len(st["served"])
                    allowed = min(allowed, max(0, room))
                if allowed <= 0:
                    continue
                moved, served_ids = self._exchange(i, j, allowed, enter, exit_)
                if self._recon_on and room is not None and room > 0 and moved == room \
                        and len(st["offered"]) > len(st["served"]) + moved:
                    # cap GENUINELY bound: the exchange filled the cap (moved==room) AND deliverable offered
                    # blobs still remain unserved after — so the cap, not the budget/backlog, clamped a
                    # transfer that would otherwise have moved. (Set after _exchange, not on allowed>room:
                    # allowed=int(credit) is the budget, not the deliverable backlog -> avoids false +ve.)
                    st["recon_capped"] = True
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
        if self._recon_on and st["recon_capped"]:          # set precisely in the fixpoint loop (no proxy)
            self.recon_capped_episodes += 1                # cap(n) bound this episode (internal metric only)
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
                # time check uses the contact end (exit_), consistent with the causality/mixing guards
                # above — self.t is not advanced to the step end until after the fixpoint loop.
                if len(self.relayed.get(src, ())) < gate_g or exit_ + _EPS < gate_t:
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
                out_blob = blob
                if self._B is not None:                            # hop-energy spread cap: receiver = source_energy-1
                    se = blob.hop_energy
                    if se is not None and se - 1 <= 0:             # a copy that would arrive at energy 0 is NOT stored
                        # NOTE: the energy cap is applied HERE (storage), not in _offerable, so a frontier
                        # copy declined at energy 0 was still tallied as "offered" — the offered_blobs metric
                        # slightly OVER-counts under a binding B. Clearance/spread are unaffected (it never
                        # gets stored/forwarded); only the airtime offered-set bookkeeping is loose under B.
                        continue
                    out_blob = replace(blob, hop_energy=(se - 1) if se is not None else None)
                # causal + mixing: not before src acquired it AND its forward-hold elapsed
                deliver_t = max(enter, self.acquired[(src, blob.id)] + self.forward_delay.get((src, blob.id), 0.0))
                if db.offer(out_blob, deliver_t) == "Accepted":
                    self.acquired[(dst, blob.id)] = deliver_t
                    self._draw_mix_delay(dst, blob.id)                 # dst now holds it -> its own mixing hold
                    if self.origin.get(blob.id) != src:               # src relayed a FOREIGN id (gate accounting)
                        self.relayed.setdefault(src, set()).add(blob.id)
                    self.transmissions += 1
                    self.on_deliver(dst, out_blob, deliver_t)
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
