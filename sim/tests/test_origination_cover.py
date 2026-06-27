"""Free-cover / "chamber" experiment (docs/originator-anonymity-limit.md §6): concurrent origination
gives single-message cover ~1/A(W) against a BLOB-BLIND adversary (the floor falls as the venue gets
busier), while the BLOB-KNOWN adversary is unaffected. Tiny/fast venue."""
import numpy as np
from soup_sim.config import Config
from soup_sim.scenario import origination_cover_sweep


def tiny_anon():
    # small dense venue, short window — fast; enough originators to show A(W) grow
    return Config(n=40, width=70.0, height=70.0, radius=10.0, boundary="torus", mobility="rwp",
                  speed_min=2.0, speed_max=2.0, dt=0.5, ttl=40.0, buffer_cap=200, throughput_ideal=1e9,
                  alpha=0.0, t_setup=0.0, p_fail=0.0, blob_size=1.0, warmup=10.0, measure_window=40.0,
                  drain=0.0, n_messages=0, seen_margin=40.0, master_seed=12345, adversary_range_mult=1.0)


def test_origination_cover_blind_floor_falls_known_unaffected():
    out = origination_cover_sweep(tiny_anon(), counts=[4, 12, 30], f=0.7, reps=2)
    rows = out["rows"]
    assert [r["n_orig"] for r in rows] == [4, 12, 30]
    aw = [r["distinct_origs"] for r in rows]
    blind = [r["blob_blind_rank1"] for r in rows]
    # A(W) grows with concurrent originations; the blob-blind floor 1/A(W) STRICTLY falls (free cover).
    assert aw[0] < aw[1] < aw[2], f"distinct originators should grow: {aw}"
    assert blind[0] > blind[1] > blind[2], f"blob-blind floor should fall: {blind}"
    assert blind[2] < 0.1, f"by 30 concurrent origs the blind floor should be well below the 4-orig 0.25: {blind}"
    # blob-blind floor is exactly 1/A(W)
    for r in rows:
        assert abs(r["blob_blind_rank1"] - 1.0 / r["distinct_origs"]) < 1e-9
    # blob-KNOWN rank-1 does NOT collapse with busyness (cover useless against it): every point stays
    # well above the blob-blind floor at the busy end (the honest contrast the experiment is about).
    known = [r["blob_known_rank1"] for r in rows]
    assert known[2] > blind[2], f"blob-known should not fall to the blind floor: known={known} blind={blind}"


def test_origination_cover_deterministic():
    a = origination_cover_sweep(tiny_anon(), counts=[8, 20], f=0.7, reps=2)
    b = origination_cover_sweep(tiny_anon(), counts=[8, 20], f=0.7, reps=2)
    assert a["rows"] == b["rows"]
