"""Closed-form reference solutions, written independently of the solver implementation."""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import NDArray

from ..units import EPS0


def point_charge_e_magnitude(q: float, r: float) -> float:
    """|E| = |q| / (4 pi eps0 r^2)."""
    return abs(q) / (4.0 * math.pi * EPS0 * r * r)


def point_charge_phi(q: float, r: float) -> float:
    return q / (4.0 * math.pi * EPS0 * r)


def dipole_e_on_axis(q: float, d: float, x: float) -> float:
    """Signed E_x on the axis of charges +q at -d/2 and -q at +d/2, for x > d/2."""
    k = 1.0 / (4.0 * math.pi * EPS0)
    return k * q * (1.0 / (x + d / 2) ** 2 - 1.0 / (x - d / 2) ** 2)


def dipole_e_on_bisector(q: float, d: float, y: float) -> float:
    """E_x on the perpendicular bisector (same charge layout): k q d / (y^2 + d^2/4)^(3/2)."""
    k = 1.0 / (4.0 * math.pi * EPS0)
    return float(k * q * d / (y * y + d * d / 4) ** 1.5)


def sphere_quadrature(n_theta: int, n_phi: int) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Unit-sphere nodes (N, 3) and weights (N,), Gauss–Legendre in cos(theta) x uniform in phi.
    The weights sum to 4 pi."""
    x, w = np.polynomial.legendre.leggauss(n_theta)
    phi = (np.arange(n_phi) + 0.5) * 2 * math.pi / n_phi
    ct, ph = np.meshgrid(x, phi, indexing="ij")
    st = np.sqrt(1 - ct**2)
    nodes = np.stack([st * np.cos(ph), st * np.sin(ph), ct], axis=-1).reshape(-1, 3)
    weights = np.repeat(w, n_phi) * (2 * math.pi / n_phi)
    return nodes, weights
