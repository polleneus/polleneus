"""Analytic targets for the contact-timing fidelity sanity gate (no fitting, no SI model).

For two nodes of equal speed v moving in independent uniform-random directions, the mean
relative speed is (4/pi)*v. Mean contact duration is the mean chord (pi*r/2 for the
center-to-center dist<=r edge convention) divided by the relative speed. The pairwise
meeting rate per node follows kinetic-theory swept-band: 2*r*v_rel*(n-1)/area.
"""
from __future__ import annotations
import numpy as np


def expected_relative_speed(v: float) -> float:
    return (4.0 / np.pi) * v


def expected_contact_duration(r: float, v_rel: float) -> float:
    return np.pi * r / (2.0 * v_rel)


def analytic_meeting_rate_per_node(r: float, v_rel: float, n: int, area: float) -> float:
    return 2.0 * r * v_rel * (n - 1) / area
