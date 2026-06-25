import numpy as np
from soup_sim.blob import Blob
from soup_sim.buffer import NodeBuffer


def test_reject_expired():
    b = NodeBuffer(10, 1000.0, np.random.default_rng(0))
    assert b.offer(Blob(1, 0.0, 10.0, 1.0), now=20.0) == "RejectedExpired"


def test_no_resurrection_evict_for_space_then_reoffer():
    b = NodeBuffer(1, 1000.0, np.random.default_rng(0))
    old = Blob(1, 0.0, 1000.0, 1.0)
    new = Blob(2, 5.0, 1000.0, 1.0)
    assert b.offer(old, now=10.0) == "Accepted"
    assert b.offer(new, now=10.0) == "Accepted"      # evicts old (oldest-by-creation)
    assert not b.has(1) and b.has(2)
    assert b.offer(old, now=11.0) == "RejectedSeen"  # evicted -> seen -> no resurrection


def test_forbidden_inversion_evicts_oldest_not_nearest_ttl():
    b = NodeBuffer(1, 1000.0, np.random.default_rng(0))
    old_lots_ttl = Blob(1, created_at=0.0, ttl=1000.0, size=1.0)       # old, far from expiry
    young_near_expiry = Blob(2, created_at=900.0, ttl=10.0, size=1.0)  # young, near expiry
    b.offer(old_lots_ttl, now=905.0)
    b.offer(young_near_expiry, now=905.0)
    assert b.has(2) and not b.has(1)  # oldest-by-creation evicted; NOT closest-to-TTL


def test_tie_break_rng_determined_both_outcomes_occur():
    a = Blob(1, 0.0, 1000.0, 1.0)
    c = Blob(2, 0.0, 1000.0, 1.0)  # same created_at -> rng tie-break

    def survivor(seed):
        buf = NodeBuffer(1, 1000.0, np.random.default_rng(seed))
        buf.offer(a, 0.0)
        buf.offer(c, 0.0)
        return tuple(sorted(buf.ids()))

    assert survivor(1) == survivor(1)                       # reproducible
    assert {survivor(s) for s in range(20)} == {(1,), (2,)}  # both outcomes appear


def test_eviction_property_oldest_le_survivors():
    gen = np.random.default_rng(7)
    buf = NodeBuffer(5, 1000.0, np.random.default_rng(0))
    blobs = [Blob(i, float(gen.integers(0, 100)), 1000.0, 1.0) for i in range(50)]
    for bl in blobs:
        buf.offer(bl, now=0.0)
    survivors = buf.blobs()
    survivor_min = min(b.created_at for b in survivors)
    evicted = [b for b in blobs if b.id not in buf.ids()]
    if evicted:
        assert max(b.created_at for b in evicted) <= survivor_min


def test_seen_window_aging_allows_after_window():
    b = NodeBuffer(1, seen_window=100.0, rng=np.random.default_rng(0))
    old = Blob(1, 0.0, 10000.0, 1.0)
    new = Blob(2, 5.0, 10000.0, 1.0)
    b.offer(old, now=10.0)
    b.offer(new, now=10.0)                              # old evicted -> seen at t=10
    assert b.offer(old, now=50.0) == "RejectedSeen"    # within window
    assert b.offer(old, now=200.0) == "Accepted"       # window elapsed (200-10 > 100)
