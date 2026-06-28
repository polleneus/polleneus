import numpy as np
from soup_sim.geometry import dist2, in_range, contact_interval


def test_walls_plain_distance():
    assert dist2(np.array([0., 0.]), np.array([3., 4.]), 100, 100, "walls") == 25.0


def test_torus_wraps_short_way():
    d = dist2(np.array([1., 1.]), np.array([99., 1.]), 100, 100, "torus")
    assert d == 4.0  # 2 across the seam, not 98


def test_in_range_uses_squared_radius_boundary_inclusive():
    assert in_range(np.array([0., 0.]), np.array([0., 5.]), 5.0, 100, 100, "walls") is True
    assert in_range(np.array([0., 0.]), np.array([0., 5.001]), 5.0, 100, 100, "walls") is False


def test_head_on_contact_interval():
    iv = contact_interval(np.array([0., 0.]), np.array([1., 0.]),
                          np.array([10., 0.]), np.array([0., 0.]),
                          2.0, 0.0, 10.0, 1000, 1000, "walls")
    assert iv is not None and abs(iv[0] - 8.0) < 1e-9 and abs(iv[1] - 10.0) < 1e-9


def test_tangential_flyby_detected():
    iv = contact_interval(np.array([-50., 1.9]), np.array([1., 0.]),
                          np.array([0., 0.]), np.array([0., 0.]),
                          2.0, 0.0, 100.0, 1000, 1000, "walls")
    assert iv is not None and iv[1] > iv[0]


def test_never_in_range_returns_none():
    iv = contact_interval(np.array([0., 100.]), np.array([1., 0.]),
                          np.array([0., 0.]), np.array([0., 0.]),
                          2.0, 0.0, 10.0, 1000, 1000, "walls")
    assert iv is None


def test_grazing_contact_is_none():
    # closest approach exactly == r (disc == 0): open-set convention -> None
    iv = contact_interval(np.array([-50., 2.0]), np.array([1., 0.]),
                          np.array([0., 0.]), np.array([0., 0.]),
                          2.0, 0.0, 100.0, 1000, 1000, "walls")
    assert iv is None
