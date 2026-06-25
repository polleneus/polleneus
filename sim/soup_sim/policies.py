"""Flood offer-selection. No routing: a node offers blobs the peer lacks, and under
scarcity (more missing than the airtime budget k) picks uniformly at random — the
selection is a measured, seeded variable, never addressing-aware.
"""
from __future__ import annotations
from .blob import Blob


def select_offers(have: list[Blob], peer_ids: set[int], k: int, rng) -> list[Blob]:
    if k <= 0:
        return []
    missing = [b for b in have if b.id not in peer_ids]
    if len(missing) <= k:
        return missing
    idx = rng.permutation(len(missing))[:k]
    return [missing[i] for i in idx]
