import numpy as np
from soup_sim.cell_list import neighbor_pairs
from soup_sim.geometry import in_range


def brute(pos, r, w, h, b):
    return {(i, j)
            for i in range(len(pos))
            for j in range(i + 1, len(pos))
            if in_range(pos[i], pos[j], r, w, h, b)}


def test_celllist_equals_bruteforce_random():
    rng = np.random.default_rng(0)
    pos = rng.uniform(0, 100, (200, 2))
    for b in ("walls", "torus"):
        assert set(neighbor_pairs(pos, 8.0, 100, 100, b)) == brute(pos, 8.0, 100, 100, b)


def test_celllist_finds_cross_seam_pair_on_torus():
    pos = np.array([[1.0, 50.0], [99.0, 50.0]])  # 2 apart across the x-seam
    assert set(neighbor_pairs(pos, 5.0, 100, 100, "torus")) == {(0, 1)}
    assert set(neighbor_pairs(pos, 5.0, 100, 100, "walls")) == set()


def test_celllist_small_n():
    assert neighbor_pairs(np.array([[0.0, 0.0]]), 5.0, 100, 100, "walls") == []
