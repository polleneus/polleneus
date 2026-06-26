"""Anonymity scoring + the capability/exposure publish-gates (slice 3, PR-1).

Honesty inversion: every number is an UPPER BOUND on anonymity (a stronger adversary
localizes better). SCOPE_TAG travels with every emitted figure. The must-localize gate
refuses to publish any number unless the (reachability) estimator demonstrably localizes a
slow-mobility source under near-total coverage — so we never mistake a weak attack for
anonymity. The exposure gate uses a MARGIN over the 1/N random-guess floor (a bare
"beats random" is vacuous at a 1/N floor) and refuses underpowered runs.
"""
from __future__ import annotations
import numpy as np
from .geometry import dist2

SCOPE_TAG = "[SINGLE-EVENT, EXTERNAL-PASSIVE; intersection+insider NOT modeled; UPPER BOUND on anonymity]"

# pre-registered constants
EXPOSURE_RANK1 = 0.5          # "flooding exposes the source" if detected rank-1 prob >= this...
EXPOSURE_MARGIN_K = 5         # ...AND >= K x the 1/N random-guess floor (kills the vacuous-at-1/N hole)
# Capability control = "does the BEST attack demonstrably localize the easy case (slow source +
# near-total coverage)?" — i.e. real signal, not near-perfection. (rank-1>=0.9 was mis-specified:
# catching 1-of-N exactly is not the bar for "can it localize at all".)
MUSTLOC_MARGIN_K = 10        # best-estimator rank-1 must beat the 1/N random floor by >= this factor...
MUSTLOC_MIN_RANK1 = 0.1     # ...and clear an absolute floor...
MUSTLOC_ERR_RADII = 1.0     # ...and pin the source to within ~one radio-range (median).
ANON_SET_EPS = 1e-6          # candidates within EPS of the best score count as an (upper-bound) anon set
MIN_MESSAGES_PER_RUN = 150   # below this rank-1 is not estimable -> exposure refuses
MIN_REPS = 6                 # below this the CI-over-seeds is degenerate -> exposure refuses


def localization_error(point, true_pos, cfg) -> float:
    return float(np.sqrt(dist2(np.asarray(point, float), np.asarray(true_pos, float),
                               cfg.width, cfg.height, cfg.boundary)))


def rank_of(scores, true_idx) -> float:
    """Rank of the true source (0 = exact catch) = #strictly-better + fractional mid-rank on ties."""
    s = np.asarray(scores, float)
    t = s[true_idx]
    strictly_better = int(np.sum(s < t - 1e-12))
    ties = int(np.sum(np.abs(s - t) <= 1e-12)) - 1
    return strictly_better + ties / 2.0


def anonymity_set_size(scores, eps=ANON_SET_EPS) -> int:
    s = np.asarray(scores, float)
    return int(np.sum(s <= s.min() + eps))


def quantiles(errs):
    a = np.asarray(errs, float)
    if a.size == 0:
        return (float("nan"), float("nan"), float("nan"))
    return (float(np.median(a)), float(np.percentile(a, 90)), float(np.percentile(a, 95)))


def mustlocalize_gate(best_result, random_floor, coverage_curve=None) -> dict:
    """Capability control: the BEST estimator must demonstrably localize a slow source under
    near-total coverage — beat the 1/N random floor by a wide margin AND pin the source to within
    ~one radio-range — AND best-estimator error must be monotone-non-increasing as coverage->1.
    (Uses the BEST estimator, not reachability-only: empirically first-spy is the workhorse under
    dense coverage. Else no slice-3 exposure number publishes.)"""
    rank1 = best_result.get("rank1", 0.0)
    err = best_result.get("median_err_radii", float("inf"))
    threshold = max(MUSTLOC_MIN_RANK1, MUSTLOC_MARGIN_K * random_floor)
    if not (rank1 >= threshold and err <= MUSTLOC_ERR_RADII):
        return {"ok": False, "label": f"estimator inconclusive (best rank-1 {rank1:.2f} < {threshold:.2f} "
                                      f"or median err {err:.2f} > {MUSTLOC_ERR_RADII} radii)"}
    if coverage_curve:                                  # [(coverage, best_median_err), ...] increasing coverage
        errs = [e for (_c, e) in sorted(coverage_curve)]
        if any(errs[i + 1] > errs[i] + 1e-9 for i in range(len(errs) - 1)):
            return {"ok": False, "label": "estimator power non-monotone in coverage"}
    return {"ok": True, "label": f"best estimator localizes (rank-1 {rank1:.2f}, err {err:.2f} radii) — capability confirmed"}


def exposure_gate(best_rank1_detected, random_floor, beats_random, n_messages, n_reps) -> dict:
    if n_messages < MIN_MESSAGES_PER_RUN or n_reps < MIN_REPS:
        return {"exposed": False, "label": f"underpowered (messages<{MIN_MESSAGES_PER_RUN} or reps<{MIN_REPS})"}
    threshold = max(EXPOSURE_RANK1, EXPOSURE_MARGIN_K * random_floor)
    if beats_random and best_rank1_detected >= threshold:
        return {"exposed": True, "label": f"flooding EXPOSES the source (rank-1 {best_rank1_detected:.2f} >= {threshold:.2f})"}
    return {"exposed": False, "label": f"not cleanly exposed (rank-1 {best_rank1_detected:.2f} < {threshold:.2f})"}
