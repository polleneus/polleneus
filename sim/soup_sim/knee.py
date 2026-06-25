"""Saturation-knee estimator + binding publish-gate (PR-2).

The knee is the argmax of circulated-blobs/min vs density, refined by a local quadratic-in-log
fit (anti grid-pinning) and bootstrapped over replications. It returns a "no_knee_in_range"
sentinel — never NaN — when the curve is monotone or merely plateaus (no real drop after the
peak). This deliberately does NOT reuse the monotone 0.5-crossing machinery in scenario.py.

The publish gate is the guard that an engine/buffer/TTL effect is never mislabeled "airtime":
a saturation figure publishes only if there is a knee AND the contention-bound fraction of
UNMET demand clears a pre-registered threshold at the knee AND neither the α=0 (airtime-free)
nor the cap=∞/ttl=∞ control turns over.
"""
from __future__ import annotations
import numpy as np

KNEE_DROP_MARGIN = 0.15   # require the curve to fall >=15% past the peak (else it's a plateau, not a knee)
BINDING_THRESHOLD = 0.5   # >=50% of UNMET demand must be contention-bound at the knee (conservative:
                          # a higher bar risks false "no airtime", a lower one false "airtime").


def binding_decomposition(offered, served, setup_starved_blobs, quantization_blobs, contention_blobs):
    """Decompose UNMET = offered-served (BLOB units) into setup-starved / quantization / contention
    shares; demand_satisfied = served/offered is reported separately (NOT part of the binding
    fraction, so a real airtime knee with high met-demand is not diluted)."""
    offered = max(0, offered)
    served = min(served, offered)
    unmet = offered - served
    if unmet <= 0:
        return {"contention_bound": 0.0, "setup_starved": 0.0, "quantization": 0.0,
                "demand_satisfied": (served / offered) if offered else None}  # None on empty traffic
    s = setup_starved_blobs + quantization_blobs + contention_blobs
    norm = s if s > 0 else 1                     # defensive: tallies should sum to unmet
    return {"contention_bound": contention_blobs / norm, "setup_starved": setup_starved_blobs / norm,
            "quantization": quantization_blobs / norm, "demand_satisfied": served / offered}


def _knee_point(dens, mean):
    mean = np.asarray(mean, float)
    k = int(np.argmax(mean))
    if k == 0 or k == len(mean) - 1:
        return None                              # peak at an edge -> monotone in range
    peak = mean[k]
    post_peak_min = float(np.min(mean[k + 1:]))   # deepest point AFTER the peak, not just the last
    if peak <= 0 or post_peak_min > peak * (1.0 - KNEE_DROP_MARGIN):
        return None                              # no real drop after the peak -> plateau, not a knee
    lo, hi = max(0, k - 2), min(len(mean) - 1, k + 2)   # +/-2 window (>=5 pts where possible)
    x = np.log(np.asarray(dens[lo:hi + 1], float))
    y = mean[lo:hi + 1]
    a, b, _c = np.polyfit(x, y, 2)
    if a >= 0:
        return None                              # not concave -> no interior max
    return float(np.exp(-b / (2 * a)))


def find_knee(densities, per_rep_circulation, rng, n_boot=200):
    dens = np.asarray(densities, float)
    mat = np.asarray(per_rep_circulation, float)         # (n_density, reps)
    point = _knee_point(dens, mat.mean(axis=1))
    if point is None:
        return {"knee": None, "ci": None, "status": "no_knee_in_range"}
    reps = mat.shape[1]
    boots = []
    for _ in range(n_boot):
        idx = rng.integers(0, reps, reps)
        kp = _knee_point(dens, mat[:, idx].mean(axis=1))
        if kp is not None:
            boots.append(kp)
    ci = (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))) if boots else (point, point)
    return {"knee": point, "ci": ci, "status": "knee"}


def binding_gate(knee_result, binding_at_knee, alpha0_turns_over, buffer_ttl_turns_over):
    if knee_result.get("status") != "knee":
        return {"publish": False, "label": "no knee in range"}
    if alpha0_turns_over:
        return {"publish": False, "label": "connectivity-limited (alpha=0 control also turns over)"}
    if buffer_ttl_turns_over:
        return {"publish": False, "label": "buffer/TTL-limited (cap=inf/ttl=inf control removes the turn-down)"}
    if binding_at_knee.get("contention_bound", 0.0) < BINDING_THRESHOLD:
        return {"publish": False, "label": "not airtime-bound (contention below threshold)"}
    return {"publish": True, "label": "airtime-saturation (contention-bound at knee)"}
