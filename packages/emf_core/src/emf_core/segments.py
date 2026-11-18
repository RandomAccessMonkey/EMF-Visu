"""Closed polygonal current filaments: exact Biot–Savart field and Coulomb-gauge vector
potential of straight segments (Phase 4A field, Phase 4C vector potential and distances).

For a segment P1 → P2 with unit direction û and R_k = P_k − r:

    B = μ₀I/(4π) (R1 × R2)(|R1| + |R2|) / (|R1||R2|(|R1||R2| + R1·R2))
    A = μ₀I/(4π) û [ln(|R2| + R2·û) − ln(|R1| + R1·û)]

The vector potential of a closed polygon is the sum over its edges (divergence-free: the
individual edge terms are not, their sum is). ln(|R| + s) with s = R·û < 0 is evaluated as
ln(|R × û|²) − ln(|R| − s) to avoid cancellation behind a segment.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .units import MU0

Arr = NDArray[np.float64]


def _edges(verts: Arr) -> list[tuple[Arr, Arr]]:
    return [(verts[i], verts[(i + 1) % len(verts)]) for i in range(len(verts))]


def segment_field(points: Arr, verts: Arr, current: float = 1.0) -> Arr:
    """B of a closed polygonal filament (vertices in traversal order) at points."""
    out = np.zeros_like(points)
    for p1, p2 in _edges(verts):
        r1, r2 = p1[None, :] - points, p2[None, :] - points
        n1, n2 = np.linalg.norm(r1, axis=1), np.linalg.norm(r2, axis=1)
        cr = np.cross(r1, r2)
        den = n1 * n2 * (n1 * n2 + np.einsum("ij,ij->i", r1, r2))
        with np.errstate(divide="ignore", invalid="ignore"):
            out += (cr * ((n1 + n2) / den)[:, None])
    result: Arr = MU0 * current / (4 * np.pi) * out
    return result


def _log_plus(r: Arr, u: Arr) -> Arr:
    """ln(|R| + R·û), accurate for R·û < 0 as well."""
    n = np.linalg.norm(r, axis=1)
    s = r @ u
    perp2 = np.einsum("ij,ij->i", c := np.cross(r, u[None, :]), c)
    with np.errstate(divide="ignore", invalid="ignore"):
        out: Arr = np.where(s >= 0, np.log(n + np.abs(s)), np.log(perp2) - np.log(n - s))
    return out


def segment_vector_potential(points: Arr, verts: Arr, current: float = 1.0) -> Arr:
    """Coulomb-gauge A of a closed polygonal filament at points."""
    out = np.zeros_like(points)
    for p1, p2 in _edges(verts):
        d = p2 - p1
        length = float(np.linalg.norm(d))
        if length == 0.0:
            continue
        u = d / length
        val = _log_plus(p2[None, :] - points, u) - _log_plus(p1[None, :] - points, u)
        out += val[:, None] * u[None, :]
    result: Arr = MU0 * current / (4 * np.pi) * out
    return result


def distance_to_polygon(points: Arr, verts: Arr) -> Arr:
    """Distance from points to the closed polyline."""
    best = np.full(points.shape[0], np.inf)
    for p1, p2 in _edges(verts):
        d = p2 - p1
        dd = float(d @ d)
        t = np.clip(((points - p1) @ d) / dd, 0.0, 1.0) if dd > 0 else np.zeros(len(points))
        best = np.minimum(best, np.linalg.norm(points - (p1 + t[:, None] * d), axis=1))
    return best
