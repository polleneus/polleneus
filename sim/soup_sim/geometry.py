"""Geometry: distances under torus/walls boundaries, and analytic contact timing.

Edge convention: nodes are in range iff center-to-center dist <= r (dist2 <= r*r).
This matches the d = lambda*pi*r^2 expected-degree convention behind d_c ~= 4.51.
"""
from __future__ import annotations
import numpy as np


def delta(a, b, w, h, boundary):
    """Minimum-image displacement b - a (wraps on a torus)."""
    d = np.asarray(b, float) - np.asarray(a, float)
    if boundary == "torus":
        size = np.array([w, h], float)
        d = d - size * np.round(d / size)
    return d


def dist2(a, b, w, h, boundary):
    d = delta(a, b, w, h, boundary)
    if d.ndim == 1:
        return float(np.dot(d, d))
    return np.einsum("...i,...i->...", d, d)


def in_range(a, b, r, w, h, boundary) -> bool:
    """True iff center-to-center distance <= r (boundary-inclusive)."""
    return bool(dist2(a, b, w, h, boundary) <= r * r)


def contact_interval(pa, va, pb, vb, r, t0, t1, w, h, boundary):
    """Sub-interval of [t0, t1] during which two constant-velocity points are within r.

    Solves |p0 + v_rel * t|^2 = r^2 over the leg. Returns (enter, exit) absolute
    times clamped to [t0, t1], or None if never strictly inside. The measure-zero
    grazing case (disc == 0, tangent touch) returns None (open-set convention).
    For torus, uses the minimum-image separation at t0; legs are short under CFL,
    so mid-leg seam crossings are out of scope (documented limitation).
    """
    p0 = delta(pa, pb, w, h, boundary)              # b - a at t0
    vrel = np.asarray(vb, float) - np.asarray(va, float)
    A = float(np.dot(vrel, vrel))
    B = 2.0 * float(np.dot(p0, vrel))
    C = float(np.dot(p0, p0)) - r * r
    if A == 0.0:                                     # no relative motion
        return (t0, t1) if C <= 0.0 else None
    disc = B * B - 4.0 * A * C
    if disc <= 0.0:                                  # never strictly inside (or grazes)
        return None
    s = disc ** 0.5
    enter = t0 + max(0.0, (-B - s) / (2.0 * A))
    exit_ = t0 + min(t1 - t0, (-B + s) / (2.0 * A))
    return (enter, exit_) if exit_ > enter else None
