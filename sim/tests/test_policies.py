import numpy as np
from soup_sim.blob import Blob
from soup_sim.policies import select_offers


def have(ids):
    return [Blob(i, 0.0, 100.0, 1.0) for i in ids]


def test_only_missing_offered():
    out = select_offers(have([1, 2, 3]), peer_ids={2}, k=10, rng=np.random.default_rng(0))
    assert {b.id for b in out} == {1, 3}


def test_returns_min_k_nmissing():
    out = select_offers(have([1, 2, 3, 4, 5]), set(), 2, np.random.default_rng(0))
    assert len(out) == 2 and all(b.id in {1, 2, 3, 4, 5} for b in out)


def test_k_zero_empty():
    assert select_offers(have([1, 2]), set(), 0, np.random.default_rng(0)) == []


def test_scarcity_selection_reproducible():
    a = select_offers(have([1, 2, 3, 4, 5]), set(), 2, np.random.default_rng(7))
    b = select_offers(have([1, 2, 3, 4, 5]), set(), 2, np.random.default_rng(7))
    assert [x.id for x in a] == [x.id for x in b]
