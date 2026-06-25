"""Independent percolation ground-truth: union-find over the contact graph.

Used to validate the engine (delivered pairs must equal same-component pairs) and to
locate the connectivity threshold via the susceptibility peak — the standard finite-size
estimator for the continuum-percolation critical mean degree d_c ~= 4.51. NOTE: the
threshold is GIANT-COMPONENT EMERGENCE, not delivery=0.5 (pairwise delivery ~ S^2 only
reaches 0.5 well above threshold, ~d 6-7).
"""
from __future__ import annotations
import numpy as np
from .cell_list import neighbor_pairs


class _UF:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.size = [1] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]


def _component_sizes(positions, r, w, h, boundary) -> list[int]:
    n = len(positions)
    uf = _UF(n)
    for (i, j) in neighbor_pairs(positions, r, w, h, boundary):
        uf.union(i, j)
    counts: dict[int, int] = {}
    for x in range(n):
        root = uf.find(x)
        counts[root] = counts.get(root, 0) + 1
    return list(counts.values())


def largest_component_fraction(positions, r, w, h, boundary) -> float:
    n = len(positions)
    if n == 0:
        return 0.0
    return max(_component_sizes(positions, r, w, h, boundary)) / n


def susceptibility(positions, r, w, h, boundary) -> float:
    """chi = sum over all-but-largest components of |c|^2 / N (peaks at the threshold)."""
    n = len(positions)
    if n == 0:
        return 0.0
    sizes = sorted(_component_sizes(positions, r, w, h, boundary), reverse=True)
    return sum(s * s for s in sizes[1:]) / n


def same_component_pairs(positions, r, w, h, boundary) -> set[tuple[int, int]]:
    n = len(positions)
    uf = _UF(n)
    for (i, j) in neighbor_pairs(positions, r, w, h, boundary):
        uf.union(i, j)
    groups: dict[int, list[int]] = {}
    for x in range(n):
        groups.setdefault(uf.find(x), []).append(x)
    pairs: set[tuple[int, int]] = set()
    for members in groups.values():
        members.sort()
        for a in range(len(members)):
            for b in range(a + 1, len(members)):
                pairs.add((members[a], members[b]))
    return pairs


def placement(n: int, w: float, h: float, rng) -> np.ndarray:
    return rng.uniform([0.0, 0.0], [w, h], (n, 2))
