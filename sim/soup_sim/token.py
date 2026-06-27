"""P2 PR-1 — token rate-limit harness (spec §3), a DEFAULT-INERT post-hoc overlay.

This module never touches the engine. It consumes the engine's RECORDED contact graph
(`self.episodes` = (i, j, entry, exit)) plus a designated adversary HOLDER, and meters how
many useful relay SLOTS one minted token buys, where:

    SLOT = the token accepted by a DISTINCT ACCEPTOR for a distinct novel forward.

This is NEW per-(token, acceptor) accounting — it does NOT reuse the engine's `relayed` field
(which counts distinct foreign BLOB ids, not distinct acceptors granting a token-slot).

Adversary model (spec §3, worst case): the holder spends ONE token `s` (nf = hash(s), an int)
at every relay opportunity. A relay opportunity against acceptor Y is the holder's FIRST contact
with Y at or after the token is live (t0) — i.e. each DISTINCT acceptor the holder ever meets is
one potential slot. (We model the holder as always having a novel forward to offer: the worst case
for the rate-limit, and the quantity the spec's "distinct acceptors relayed-to ~ D" names.)

Three acceptance regimes decide whether each opportunity actually GRANTS a slot:

  broken   : accept once per (token, acceptor) pair  -> slots/token = distinct acceptors = ~D.
  anchored : each acceptor keeps a LOCAL seen-nf set; accept iff that acceptor has not seen nf.
             For a STATIC dense holder this is still ~D (each fresh acceptor accepts once); it
             drops below D only when the holder physically moves to neighbourhoods it has not
             yet hit (it never re-meets an acceptor, so the local set is irrelevant) -> the
             anchoring ALONE buys little (spec §9.3). [Modelled identically to broken because a
             distinct acceptor is by construction met once; see _spend_events.]
  gossip   : the seen-nf set PROPAGATES epidemically on the engine's own contact dynamics. nf is
             BORN at its first spend (t0, holder position). A node learns nf when the gossip front
             reaches it from the set of nf-knowers AFTER t0 (acquisition-time causality on the SAME
             contacts that move blobs). An acceptor that ALREADY knows nf at spend time rejects
             (no slot). slots/token -> 1 + residual = spends accepted before nf's front arrives.

Epidemic nf propagation uses the engine's contact dynamics directly (a multi-source forward
infection over self.episodes), seeded at the token's MID-RUN first-spend time. It deliberately
does NOT use percolation.temporal_reachable (whose docstring warns it IGNORES created_at and is
wrong for a marker born mid-run): that oracle seeds infection at -inf, which would mark every node
as a knower from the very first contact and zero out the residual. We seed at t0 instead.
"""
from __future__ import annotations

_EPS = 1e-9
_INF = float("inf")


def token_nf(s: int) -> int:
    """nf = hash(s) as an int (no crypto computed; spec §3 'nf = hash(s) is an int')."""
    return hash(("nf", int(s)))


def forward_infection(episodes, seeds: dict[int, float], gossip_delay: float = 0.0,
                      exclude: set | None = None) -> dict[int, float]:
    """Earliest time each node KNOWS nf, given `seeds` = {node: time it first knew nf}, diffusing
    over the time-respecting contact graph: a contact [entry, exit] carries nf from a knower a
    (known since t_a) to b at max(t_a, entry) + gossip_delay iff t_a <= exit. Iterated to a fixpoint.

    `exclude` nodes (e.g. the adversary holder) are never carriers OR recipients of the gossip front:
    the holder does not relay the seen-nf set for its own token (it wants to spend, not advertise), so
    nf must not flow into or out of it during honest-acceptor gossip.

    This is the SAME diffusion the engine uses to move blobs (acquisition-time causality), NOT
    distance/c and NOT percolation.temporal_reachable (which ignores created_at -> seeds at -inf).
    Seeds carry their own MID-RUN known-times, so nf is born at t0, not before the run."""
    skip = exclude or set()
    inf = {nd: t for nd, t in seeds.items() if nd not in skip}
    changed = True
    while changed:
        changed = False
        for (i, j, entry, exit_) in episodes:
            if i in skip or j in skip:               # holder never carries/receives the gossip front
                continue
            for a, b in ((i, j), (j, i)):
                ta = inf.get(a)
                if ta is not None and ta <= exit_ + _EPS:
                    cand = max(ta, entry) + gossip_delay
                    if cand <= exit_ + _EPS and (b not in inf or cand < inf[b] - 1e-12):
                        inf[b] = cand
                        changed = True
    return inf


def _spend_events(episodes, holder: int, t0: float):
    """Token spend opportunities for `holder`: the FIRST contact with each DISTINCT other node at
    or after t0, in increasing spend-time order. spend_time = max(entry, t0) (the holder cannot
    spend before the token is live). Returns [(acceptor, spend_time), ...]; distinct acceptors only
    (a re-meet of the same acceptor is NOT a new distinct-acceptor slot)."""
    first: dict[int, float] = {}
    for (i, j, entry, exit_) in episodes:
        for a, b in ((i, j), (j, i)):
            if a != holder:
                continue
            if exit_ < t0 - _EPS:                 # contact ended before the token was live: no spend
                continue
            ts = max(entry, t0)
            if b not in first or ts < first[b]:
                first[b] = ts
    return sorted(first.items(), key=lambda kv: (kv[1], kv[0]))


def pick_holder(episodes, n: int, warmup: float) -> int:
    """The worst-case adversary position: the node that meets the MOST distinct other nodes at or
    after `warmup` (the largest D = the most relay slots to buy). Ties broken by lowest index."""
    counts: dict[int, set] = {}
    for (i, j, entry, exit_) in episodes:
        if exit_ < warmup - _EPS:
            continue
        counts.setdefault(i, set()).add(j)
        counts.setdefault(j, set()).add(i)
    if not counts:
        return 0
    return max(range(n), key=lambda nd: (len(counts.get(nd, ())), -nd))


def first_spend_time(episodes, holder: int, warmup: float) -> float:
    """t0 = the token's birth = the holder's earliest contact at/after `warmup` (the token is minted
    at the start of the measurement window). Falls back to `warmup` if the holder has no contacts."""
    earliest = _INF
    for (i, j, entry, exit_) in episodes:
        if (i == holder or j == holder) and exit_ >= warmup - _EPS:
            earliest = min(earliest, max(entry, warmup))
    return earliest if earliest < _INF else warmup


def slots_for_token(episodes, holder: int, t0: float, mode: str,
                    phy_session_quota: int = 0, gossip_delay: float = 0.0,
                    n_tokens: int = 1) -> dict:
    """Meter slots/token for ONE holder spending `n_tokens` identical-policy tokens.

    broken/anchored: each distinct acceptor is met once, so it grants exactly one slot -> slots/token
    = D. gossip: run the SEQUENTIAL epidemic (_gossip_accept) -> only acceptors the seen-nf front has
    not yet reached at spend time grant a slot, so slots/token = 1 + residual.

    Per-PHY quota Q (orthogonal, §9.5): one holder-PHY-session is granted <= Q slots TOTAL no matter
    how many tokens it presents. slots/token is reported per token (one accepting acceptor = 1 slot);
    max_slots_per_phy = min(n_tokens, Q) when Q>0 (the §9.5 fail-closed backstop), else n_tokens (one
    PHY session leaks n_tokens unbounded).

    Returns {distinct_acceptors (=D), slots_per_token, max_slots_per_phy, residual_acceptors}.
    """
    spends = _spend_events(episodes, holder, t0)
    D = len(spends)
    if D == 0:
        return {"distinct_acceptors": 0, "slots_per_token": 0.0,
                "max_slots_per_phy": 0, "residual_acceptors": 0}

    # accepted[Y] = whether acceptor Y grants a slot for ONE token under the regime.
    if mode in ("broken", "anchored"):
        # Each distinct acceptor is met once, so its local seen-set is always fresh on first contact
        # -> it accepts. (anchored == broken for a once-met acceptor; the win is the gossip, §9.3.)
        accepted = {Y: True for (Y, _ts) in spends}
    elif mode == "gossip":
        accepted = _gossip_accept(episodes, holder, spends, gossip_delay)
    else:  # off (defensive: the overlay should not be invoked when off)
        accepted = {Y: True for (Y, _ts) in spends}

    granted = [Y for (Y, _ts) in spends if accepted[Y]]
    residual = len(granted)

    per_token_slots = float(residual)            # slots one token buys (granted distinct acceptors)
    # Per-PHY quota Q (§9.5 backstop): a single holder-PHY-session is granted <= Q slots TOTAL no
    # matter how many tokens it presents. The headline is max_slots_per_phy: with Q off, one session
    # leaks n_tokens slots; with Q on, it is clamped to min(n_tokens, Q) — exposing the bound under
    # the many-tokens case the spec requires the harness to exercise.
    if phy_session_quota > 0:
        max_slots_per_phy = min(n_tokens, phy_session_quota)
    else:
        max_slots_per_phy = n_tokens

    return {"distinct_acceptors": D, "slots_per_token": per_token_slots,
            "max_slots_per_phy": max_slots_per_phy, "residual_acceptors": residual}


def _gossip_accept(episodes, holder: int, spends, gossip_delay: float) -> dict:
    """Sequential epidemic acceptance — THE CORE EPIDEMIC LOGIC. Process spends in increasing time
    order. A spend (Y, ts) is GRANTED (a leaked slot) iff no previously-granted acceptor's gossip
    front has reached Y at or before ts; otherwise REJECTED (Y already saw nf). A granted acceptor
    becomes a gossip source at its spend time and re-broadcasts, so we recompute the front after each
    grant (monotone: adding earlier-or-equal sources only lowers known-times -> it converges).

    This does NOT use percolation.temporal_reachable: the front is seeded at granted acceptors at
    their MID-RUN spend times and diffused via forward_infection. temporal_reachable seeds at -inf
    (it ignores created_at), which would mark every node a knower from the first contact and collapse
    the residual to ~0 — wrong for a marker born mid-run."""
    # The seen-nf set is gossiped by HONEST ACCEPTORS, not by the adversary holder: the holder wants
    # to spend, not advertise, so it is NOT a gossip source. This is the HONEST/WORST-CASE direction
    # the spec demands (every number is a LOWER bound on slots leaked): a holder that broadcast nf
    # would only HELP the defense (more rejections) -> optimistic, so we exclude it. nf is born at an
    # acceptor the instant it observes a spend, and that acceptor re-broadcasts it on the flood.
    # Ties (nf arrives in the same contact that carries the spend) count as already-seen. The MINT
    # (first spend, empty knower set) always leaks (the '+1'); a STATIC dense holder then floods nf to
    # all its neighbours via that first acceptor (residual ~ 1), while a MOBILE holder that reaches a
    # fresh pocket BEFORE the front does still leaks (residual grows with diameter / mobility).
    exclude = {holder}                                # the holder never relays the seen-nf front
    accepted: dict[int, bool] = {}
    known: dict[int, float] = {}                      # gossip sources = granted acceptors, by learn-time
    inf: dict[int, float] = {}
    for (Y, ts) in spends:                            # increasing spend-time order
        if known and inf.get(Y, _INF) <= ts + _EPS:  # an OTHER acceptor's front already reached Y
            accepted[Y] = False
        else:
            accepted[Y] = True
            known[Y] = ts                            # Y observed the spend -> it now gossips nf from ts
            inf = forward_infection(episodes, known, gossip_delay, exclude=exclude)
    return accepted
