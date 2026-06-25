import numpy as np
from soup_sim.budget import AirtimeBudget


def test_short_contact_below_setup_transfers_zero():
    bud = AirtimeBudget(1000, alpha=0.0, t_setup=1.0, p_fail=0.0, blob_size=100)
    assert bud.blobs_transferable(0.5, 0, np.random.default_rng(0)) == 0


def test_contention_reduces_throughput():
    bud = AirtimeBudget(1000, alpha=1.0, t_setup=0.0, p_fail=0.0, blob_size=100)
    low = bud.blobs_transferable(1.0, 0, np.random.default_rng(0))   # eff 1000 -> 10
    high = bud.blobs_transferable(1.0, 9, np.random.default_rng(0))  # eff 100  -> 1
    assert high < low


def test_quantized_to_whole_blobs():
    bud = AirtimeBudget(90, alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=100)
    assert bud.blobs_transferable(1.0, 0, np.random.default_rng(0)) == 0  # 0.9 blob -> 0


def test_pfail_one_thins_to_zero():
    bud = AirtimeBudget(1000, alpha=0.0, t_setup=0.0, p_fail=1.0, blob_size=100)
    assert bud.blobs_transferable(1.0, 0, np.random.default_rng(0)) == 0
