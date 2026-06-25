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

    def expire(self, now: float) -> None:
        dead = [bid for bid, b in self.store.items() if now >= b.expires_at]
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
