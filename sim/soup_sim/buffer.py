"""Per-node bounded buffer with inversion-proof eviction and a sliding-window seen-record.

Eviction (parent §9.5): victims come from the OLDEST-by-creation cohort with a
randomized tie-break (retain younger) — NEVER closest-to-TTL.
Seen-record: FIFO-by-time with window `seen_window` (set >= maxTTL + margin) so a
dropped/expired id cannot be re-accepted within the window (no resurrection).
"""
from __future__ import annotations
from .blob import Blob


class NodeBuffer:
    def __init__(self, cap: int, seen_window: float, rng):
        self.cap = cap
        self.seen_window = seen_window
        self.rng = rng
        self.store: dict[int, Blob] = {}
        self.seen: dict[int, float] = {}  # id -> time it was dropped

    def has(self, blob_id: int) -> bool:
        return blob_id in self.store

    def ids(self) -> set[int]:
        return set(self.store.keys())

    def blobs(self) -> list[Blob]:
        return list(self.store.values())

    def _prune_seen(self, now: float) -> None:
        stale = [bid for bid, t in self.seen.items() if now - t > self.seen_window]
        for bid in stale:
            del self.seen[bid]

    def offer(self, blob: Blob, now: float) -> str:
        self._prune_seen(now)
        if now >= blob.expires_at:
            return "RejectedExpired"
        if blob.id in self.store:
            return "Accepted"  # idempotent
        if blob.id in self.seen:
            return "RejectedSeen"
        self.store[blob.id] = blob
        self._evict_to_fit(now)
        return "Accepted"

    def expire(self, now: float, hold_budget: float | None = None, receipt: dict | None = None,
               clock_trusted: bool = True, clock_offset: float = 0.0) -> None:
        """Per-step expiry sweep. A drop writes the seen-record (seen[bid]=now), like evict/legacy.

        With the DEFAULT args (hold_budget=None, receipt=None, clock_trusted=True, clock_offset=0.0)
        this reduces EXACTLY to the legacy rule `now >= b.expires_at` ⇒ bit-identical.

        P3 clock-independent expiry (spec §2/§3). `now` and `receipt` are TRUE global time
        (frame-consistent with offer/evict/seen/acquired); the per-node RTC `clock_offset` enters
        ONLY this comparison, never causality. The predicate is:

            local_now      = now + clock_offset                 # the node's LOCAL clock
            local_receipt  = receipt[bid] + clock_offset        # receipt in the SAME local frame
            expired = (H is not None AND local_now − local_receipt >= H)   # OFFSET-INVARIANT (offset cancels)
                      OR (clock_trusted AND local_now >= b.expires_at)     # origin-TTL (offset does NOT cancel)

        The hold-budget term clears the soup under ANY clock skew (offset cancels); the origin-TTL term
        fires only when the clock is trusted. Both only ever SHORTEN an honest blob's life.
        """
        local_now = now + clock_offset
        dead = []
        for bid, b in self.store.items():
            h_drop = False
            if hold_budget is not None and receipt is not None:
                rt = receipt.get(bid)
                if rt is not None:                       # local_now − local_receipt: clock_offset cancels
                    h_drop = (local_now - (rt + clock_offset)) >= hold_budget
            ttl_drop = clock_trusted and local_now >= b.expires_at
            if h_drop or ttl_drop:
                dead.append(bid)
        for bid in dead:
            del self.store[bid]
            self.seen[bid] = now
        self._prune_seen(now)

    def _evict_to_fit(self, now: float) -> None:
        while len(self.store) > self.cap:
            min_created = min(b.created_at for b in self.store.values())
            cohort = [bid for bid, b in self.store.items() if b.created_at == min_created]
            victim = cohort[0] if len(cohort) == 1 else int(self.rng.choice(cohort))
            del self.store[victim]
            self.seen[victim] = now
