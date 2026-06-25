"""Uniform-grid (cell-list) spatial index for O(N) neighbor queries.

Returns the same set of within-r pairs as brute force, in O(N * local density)
instead of O(N^2). Cell size >= r so any two within-r nodes fall in adjacent
(or the same) cells; candidates are confirmed with geometry.in_range.
"""
from __future__ import annotations
from collections import defaultdict
import numpy as np
from .geometry import in_range


def neighbor_pairs(positions, r, w, h, boundary):
    pos = np.asarray(positions, float)
    n = len(pos)
    if n < 2:
        return []
    ncx = max(1, int(np.floor(w / r)))
    ncy = max(1, int(np.floor(h / r)))
    cx = np.minimum((pos[:, 0] / w * ncx).astype(int), ncx - 1)
    cy = np.minimum((pos[:, 1] / h * ncy).astype(int), ncy - 1)
    buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(n):
        buckets[(int(cx[i]), int(cy[i]))].append(i)

    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for (gx, gy), idxs in buckets.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                nx, ny = gx + dx, gy + dy
                if boundary == "torus":
                    nx %= ncx
                    ny %= ncy
                elif not (0 <= nx < ncx and 0 <= ny < ncy):
                    continue
                neigh = buckets.get((nx, ny))
                if not neigh:
                    continue
                for i in idxs:
                    for j in neigh:
                        if i >= j:
                            continue
                        key = (i, j)
                        if key in seen:
                            continue
                        seen.add(key)
                        if in_range(pos[i], pos[j], r, w, h, boundary):
                            pairs.append(key)
    return pairs
