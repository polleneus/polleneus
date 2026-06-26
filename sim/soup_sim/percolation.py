"""Independent percolation ground-truth: union-find over the contact graph.

Used to validate the engine (delivered pairs must equal same-component pairs) and to
locate the connectivity threshold via the susceptibility peak — the standard finite-size
estimator for the continuum-percolation critical mean degree d_c ~= 4.51. NOTE: the
threshold is GIANT-COMPONENT EMERGENCE, not delivery=0.5. Pairwise delivery ~ S^2 crosses
0.5 JUST ABOVE the threshold (~d 4.5-4.7 at venue-scale N); ~d 6-7 is where it SATURATES
(0.95-0.99 reach), not where it hits 0.5.
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


def same_component_pair_fraction(positions, r, w, h, boundary) -> float:
    """Fraction of unordered node pairs in the same component = the static, unbounded,
    multi-hop delivery probability for a uniform-random src/dst (component reachability)."""
    n = len(positions)
    if n < 2:
        return 0.0
    sizes = _component_sizes(positions, r, w, h, boundary)
    same = sum(s * (s - 1) // 2 for s in sizes)
    total = n * (n - 1) // 2
    return same / total if total else 0.0


def temporal_reachable(episodes, source, n) -> set[int]:
    """Independent INTERVAL-based time-respecting reachability — the physical ground truth.

    `episodes` are (i, j, entry, exit). A node is infected at a time; a contact [entry,exit]
    can carry the blob from an infected endpoint a (infected at t_a) to b iff t_a <= exit,
    delivering at max(t_a, entry). Iterated to a fixpoint (a newly-lowered infection time can
    enable earlier propagation through other overlapping contacts). This is computed purely
    from contact geometry — it does NOT replay the engine's delivery order — so it is a real
    independent check (it detects under-delivery across nested/overlapping contacts).

    PRECONDITION: the blob exists from before the first contact (created_at <= t0). The oracle
    ignores created_at; for a blob created mid-run, the engine's causality guard is the source
    of truth, not this function. NOTE: both engine and oracle consume contact_interval, so a
    bug in contact_interval itself would be invisible to an engine-vs-oracle comparison — the
    deterministic discriminator tests hand-verify the contact intervals to cover that.
    """
    INF = float("inf")
    inf_time = {source: -INF}
    changed = True
    while changed:
        changed = False
        for (i, j, entry, exit_) in episodes:
            for (a, b) in ((i, j), (j, i)):
                ta = inf_time.get(a, INF)
                if ta <= exit_:
                    cand = max(ta, entry)
                    if cand < inf_time.get(b, INF):
                        inf_time[b] = cand
                        changed = True
    return set(inf_time)


def placement(n: int, w: float, h: float, rng) -> np.ndarray:
    return rng.uniform([0.0, 0.0], [w, h], (n, 2))
