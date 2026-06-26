import numpy as np
from soup_sim.knee import binding_decomposition, find_knee, binding_gate, BINDING_THRESHOLD


# --- Task 6: binding decomposition over UNMET (blob units) --------------------
def test_binding_decomposition_over_unmet_blob_units():
    # 60% met, all 40 unmet blobs contention -> contention_bound == 1.0 of unmet (not 0.4 diluted)
    d = binding_decomposition(offered=100, served=60, setup_starved_blobs=0, quantization_blobs=0, contention_blobs=40)
    assert abs(d["contention_bound"] - 1.0) < 1e-9 and abs(d["demand_satisfied"] - 0.6) < 1e-9
    # unmet split 80 starved / 10 contention -> starvation dominates
    d = binding_decomposition(offered=100, served=10, setup_starved_blobs=80, quantization_blobs=0, contention_blobs=10)
    assert d["setup_starved"] > d["contention_bound"]
    # low-goodput contention (could move blobs, backlog exceeded) must NOT read as quantization
    d = binding_decomposition(offered=100, served=40, setup_starved_blobs=0, quantization_blobs=0, contention_blobs=60)
    assert abs(d["contention_bound"] - 1.0) < 1e-9
    # nothing unmet -> contention_bound 0
    d = binding_decomposition(offered=50, served=50, setup_starved_blobs=0, quantization_blobs=0, contention_blobs=0)
    assert d["contention_bound"] == 0.0


# --- Task 7: saturation-knee estimator ---------------------------------------
def test_find_knee_recovers_planted_peak():
    dens = np.linspace(1.0, 20.0, 20)
    peak = 9.0
    mean = 100.0 - 50.0 * (np.log(dens) - np.log(peak)) ** 2
    reps = np.stack([mean, mean + 0.3, mean - 0.3], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "knee" and abs(out["knee"] - peak) < 1.5


def test_find_knee_coarse_grid_with_noise():
    dens = np.array([2.0, 5.0, 8.0, 11.0, 14.0, 17.0, 20.0])
    peak = 9.0
    mean = 100.0 - 30.0 * (np.log(dens) - np.log(peak)) ** 2
    rng = np.random.default_rng(3)
    reps = np.stack([mean + rng.normal(0, 3, len(dens)) for _ in range(12)], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "knee" and 4.0 < out["knee"] < 16.0


def test_find_knee_monotone_returns_no_knee():
    dens = np.linspace(1.0, 20.0, 20)
    mean = 100.0 - 3.0 * dens
    reps = np.stack([mean, mean + 0.1, mean - 0.1], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "no_knee_in_range" and out["knee"] is None


def test_find_knee_saturating_plateau_returns_no_knee():
    # mild concave plateau that ends only ~1% below the peak -> drop-margin rejects it
    dens = np.linspace(1.0, 20.0, 20)
    mean = 100.0 * dens / (1.0 + dens)        # monotone-increasing saturation
    reps = np.stack([mean, mean + 0.2, mean - 0.2], axis=1)
    out = find_knee(dens, reps, np.random.default_rng(0))
    assert out["status"] == "no_knee_in_range"


# --- Task 8: binding publish gate --------------------------------------------
def test_binding_gate():
    knee = {"status": "knee", "knee": 9.0, "ci": (8.0, 10.0)}
    assert binding_gate(knee, {"contention_bound": 0.7}, False, False)["publish"] is True
    g = binding_gate(knee, {"contention_bound": 0.7}, True, False)
    assert g["publish"] is False and "connectivity" in g["label"].lower()
    g = binding_gate(knee, {"contention_bound": 0.7}, False, True)
    assert g["publish"] is False and ("buffer" in g["label"].lower() or "ttl" in g["label"].lower())
    assert binding_gate(knee, {"contention_bound": 0.2}, False, False)["publish"] is False
    assert binding_gate({"status": "no_knee_in_range"}, {"contention_bound": 0.9}, False, False)["publish"] is False
