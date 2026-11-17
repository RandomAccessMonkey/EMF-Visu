"""Independent magnetostatic references (Phase 3A). Validation only: the solver never uses them.

* Closed forms: B = mu0 I / (2 pi r) for an infinite wire; B_z = mu0 I a^2 / (2 (a^2 + z^2)^(3/2))
  on the axis of a circular loop.
* Numerical Biot–Savart line integral over a circular loop, written directly in world Cartesian
  coordinates from B = mu0 I / (4 pi) ∮ dl' × (r - r') / |r - r'|^3 with no use of the
  elliptic-integral solution. The integrand is smooth and periodic in the loop angle, so the
  trapezoidal rule converges exponentially; near the wire (distance d) the integrand is peaked
  over an angle of about d/a, and the number of nodes must grow like a/d. ``loop_converged``
  doubles the node count until two successive results agree to a requested relative tolerance.
* Numerical Biot–Savart integral over a finite straight segment [-L, L] (Gauss–Legendre on
  sub-intervals), plus the exact tail of the two half-infinite remainders, for the wire.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from ..units import MU0

Arr = NDArray[np.float64]


def wire_magnitude(current: float, r: float) -> float:
    return MU0 * abs(current) / (2.0 * math.pi * r)


def loop_axis_bz(current: float, a: float, z: float) -> float:
    return float(MU0 * current * a * a / (2.0 * (a * a + z * z) ** 1.5))


def loop_trapezoid(point: Arr, center: Arr, normal: Arr, u: Arr, a: float, current: float,
                   n: int) -> Arr:
    """Trapezoidal Biot–Savart sum with n nodes; the current circulates from u towards n × u."""
    v = np.cross(normal, u)
    out = np.zeros(3)
    for start in range(0, n, 200_000):
        t = 2.0 * np.pi * (np.arange(start, min(n, start + 200_000)) / n)
        c, s = np.cos(t), np.sin(t)
        src = center + a * (c[:, None] * u + s[:, None] * v)
        dl = (2.0 * np.pi * a / n) * (-s[:, None] * u + c[:, None] * v)
        r = point - src
        d3 = np.einsum("ij,ij->i", r, r) ** 1.5
        out += np.sum(np.cross(dl, r) / d3[:, None], axis=0)
    result: Arr = MU0 * current / (4.0 * np.pi) * out
    return result


@dataclass
class Converged:
    value: Arr
    nodes: int
    history: list[tuple[int, float]]  # (nodes, relative change against the previous level)


def loop_converged(point: Arr, center: Arr, normal: Arr, u: Arr, a: float, current: float,
                   rtol: float = 1e-13, n0: int = 256, n_max: int = 2**24) -> Converged:
    prev = loop_trapezoid(point, center, normal, u, a, current, n0)
    n = n0
    history: list[tuple[int, float]] = []
    while n < n_max:
        n *= 2
        cur = loop_trapezoid(point, center, normal, u, a, current, n)
        change = float(np.linalg.norm(cur - prev) / max(np.linalg.norm(cur), 1e-300))
        history.append((n, change))
        if change <= rtol:
            return Converged(cur, n, history)
        prev = cur
    raise RuntimeError(f"Biot–Savart reference did not converge to {rtol} with {n_max} nodes")


def wire_segment(point: Arr, origin: Arr, direction: Arr, current: float, half_length: float,
                 panels: int = 4000) -> Arr:
    """Biot–Savart over [-L, L] by 8-point Gauss–Legendre panels, plus the analytical field of the
    two half-infinite remainders, which is mu0 I / (4 pi rho) (1 - cos theta) each."""
    x, w = np.polynomial.legendre.leggauss(8)
    edges = np.linspace(-half_length, half_length, panels + 1)
    mid, half = 0.5 * (edges[1:] + edges[:-1]), 0.5 * (edges[1:] - edges[:-1])
    s = (mid[:, None] + half[:, None] * x[None, :]).ravel()
    ws = (half[:, None] * w[None, :]).ravel()
    src = origin + s[:, None] * direction
    r = point - src
    d3 = np.einsum("ij,ij->i", r, r) ** 1.5
    core = MU0 * current / (4.0 * np.pi) * np.sum(
        ws[:, None] * np.cross(direction, r) / d3[:, None], axis=0)
    rel = point - origin
    zp = float(rel @ direction)
    rperp = rel - zp * direction
    rho = float(np.linalg.norm(rperp))
    phi_hat = np.cross(direction, rperp / rho)
    tail = 0.0
    for end, sign in ((half_length, 1.0), (-half_length, -1.0)):
        dz = sign * (end - zp)  # distance along the axis from the point's foot to the end
        tail += 1.0 - dz / math.hypot(dz, rho)
    result: Arr = core + MU0 * current / (4.0 * math.pi * rho) * tail * phi_hat
    return result


def magnet_sheet(point: Arr, center: Arr, axis: Arr, u: Arr, a: float, length: float,
                 magnetization: float, n_phi: int = 4096, n_z: int = 400) -> Arr:
    """Independent reference for a uniformly magnetized cylinder: direct 2D Biot–Savart integral
    of its side-wall surface current K = M e_phi (amperes per metre) over the surface,
    B = mu0/(4 pi) ∫∫ K × (r - r') / |r - r'|^3 a dphi dz', with the periodic trapezoidal rule
    in phi and 16-point Gauss–Legendre panels in z. No circular-loop formula is used. Accurate
    away from the sheet itself."""
    v = np.cross(axis, u)
    x, w = np.polynomial.legendre.leggauss(16)
    panels = max(1, n_z // 16)
    edges = np.linspace(-length / 2, length / 2, panels + 1)
    mid, half = 0.5 * (edges[1:] + edges[:-1]), 0.5 * (edges[1:] - edges[:-1])
    zs = (mid[:, None] + half[:, None] * x[None, :]).ravel()
    wz = (half[:, None] * w[None, :]).ravel()
    phi = 2.0 * np.pi * np.arange(n_phi) / n_phi
    c, s_ = np.cos(phi), np.sin(phi)
    out = np.zeros(3)
    for zi, wi in zip(zs, wz, strict=True):
        src = center + zi * axis + a * (c[:, None] * u + s_[:, None] * v)
        k_dir = -s_[:, None] * u + c[:, None] * v  # e_phi
        r = point - src
        d3 = np.einsum("ij,ij->i", r, r) ** 1.5
        out += wi * np.sum(np.cross(k_dir, r) / d3[:, None], axis=0) * (2.0 * np.pi * a / n_phi)
    result: Arr = MU0 * magnetization / (4.0 * np.pi) * out
    return result


def finite_sheet_axis_bz(current_per_m: float, a: float, length: float, z: float) -> float:
    """On-axis B_z of a continuous cylindrical current sheet (n I or M per metre):
    (mu0 K / 2) [ (z + L/2)/sqrt(a^2 + (z + L/2)^2) - (z - L/2)/sqrt(a^2 + (z - L/2)^2) ]."""
    p, q = z + length / 2, z - length / 2
    return float(MU0 * current_per_m / 2 * (p / math.hypot(a, p) - q / math.hypot(a, q)))
