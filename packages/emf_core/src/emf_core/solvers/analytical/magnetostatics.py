"""Exact magnetostatic field of ideal current filaments in unbounded vacuum (Phase 3A).

Sources (see ``scene.currents``): infinitely long straight wires and circular loops, both
idealised as zero-radius filaments carrying a steady current I.

Straight wire (equation ``infinite_wire_field``), axis through p with unit direction d:

    r_perp = (r - p) - ((r - p)·d) d
    B(r)   = mu0 I / (2 pi |r_perp|^2) · d × r_perp            [T]

Circular loop of radius a (equation ``loop_field_elliptic``), local cylindrical coordinates
(rho, z) about its centre and normal n, D± = (a ± rho)^2 + z^2, m = 4 a rho / D+:

    B_z   = mu0 I / (2 pi sqrt(D+)) · [K(m) + (a^2 - rho^2 - z^2)/D- · E(m)]
    B_rho = mu0 I z / (2 pi rho sqrt(D+)) · f(m) / (2 (1 - m)),
    f(m)  = (2 - m) E(m) - 2 (1 - m) K(m)

K is evaluated as ellipkm1(1 - m) with 1 - m = D-/D+ formed directly (accurate near the wire,
where m -> 1); E as ellipe(m). Near the axis f(m) = O(m^2) is the difference of O(1) terms, so
for m <= NEAR_AXIS_M the exact power series f(m) = (pi/2) sum_{n>=2} f_n m^n is used, whose
coefficients follow from the hypergeometric series of K and E and are all positive (no
cancellation). It is written as f(m)/rho = (4a/D+) (pi/2) sum f_n m^(n-1), which is exact on the
axis, where B_rho = 0 and B_z = mu0 I a^2 / (2 (a^2 + z^2)^(3/2)).

H = B / mu0 (vacuum). The total field is the sum over sources (superposition). Pointwise
divergence of B and H is exactly zero wherever B is defined (the Biot–Savart field of a closed
or infinite filament is solenoidal off the filament); it is returned as exact 0, and NaN where
B is undefined. B is undefined (singular) only where a point is numerically indistinguishable
from an ideal filament: d ≤ FILAMENT_EPS_FACTOR · ε · S, with ε the float64 machine epsilon and S
the size of the local coordinates from which d is computed (loop: a + |p − c|; wire: |p − p0|).
The computed d carries an absolute rounding error of at most a few ε·S, so within this
tolerance d cannot be told apart from 0; any other point gets its analytical value, however
large. Close to a filament the computed field is the exact field at a point displaced by about
ε·S (backward stable), so its relative accuracy is bounded by PRECISION_EPS_FACTOR · ε · S / d;
this bound is returned per point and reported when it exceeds PRECISION_WARN (Phase 3B.1).
"""

from __future__ import annotations

import hashlib
import math
import time
from collections import OrderedDict
from dataclasses import dataclass
from dataclasses import field as dc_field
from fractions import Fraction
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from scipy.special import ellipe, ellipkm1

from ... import segments
from ...i18n import L, LocalizedText
from ...numerics.quadrature import adaptive_gk
from ...postprocess import magnetic_lines as ml
from ...sampling import PlaneGridSampling
from ...scene.currents import (
    CurrentSources,
    IdealToroidSource,
    LoopSource,
    MagnetSource,
    WireSource,
    current_sources,
)
from ...scene.models import GroupPrimitive, MaterialModel, Role, Scene, TimeDependentCurrent
from ...scene.passive import PassiveFilament
from ...scene.profiles import PiecewiseLinearProfile, RampProfile, SinusoidalProfile
from ...scene.timedep import TimeState, at_time, rates, time_state
from ...units import MU0, QUANTITIES
from ..base import (
    ArrayEntry,
    ArrayStats,
    CancelCheck,
    CurrentSourceInfo,
    FieldLineInfo,
    FieldLineSet,
    IdealSolenoidInfo,
    InductionInfo,
    MethodInfo,
    ModelContext,
    ProgressCallback,
    ResultHeader,
    SimulationResult,
    SolverCancelledError,
    SolveRequest,
    SolverKind,
    Support,
    TimeSourceInfo,
    TurnGeometry,
    quantities_for,
)

Arr = NDArray[np.float64]
Mask = NDArray[np.bool_]
COINCIDENCE_FACTOR = 1e-12  # domain-scaled position tolerance (probe display, sheet tolerance)
# Phase 3B.1: filament singularity and near-filament precision, scaled by the source geometry.
EPS = float(np.finfo(np.float64).eps)
FILAMENT_EPS_FACTOR = 64.0  # singular iff d <= 64 eps S (>= 10x the rounding error of d)
PRECISION_EPS_FACTOR = 8.0  # relative accuracy bound 8 eps S / d (measured <= 0.8 eps a / d)
PRECISION_WARN = 1e-8  # report points whose bound exceeds this
IN_PLANE_FACTOR = 1e-9
NEAR_AXIS_M = 0.5
SERIES_TERMS = 80
MAX_CONTRIBUTION_SOURCES = 12
_CHUNK = 100_000


def _series_coefficients(n_terms: int) -> NDArray[np.float64]:
    """f_n (in units of pi/2) of f(m) = (2-m)E - 2(1-m)K = (pi/2) sum f_n m^n, from
    K = (pi/2) sum c_n m^n, E = (pi/2) sum e_n m^n, c_n = ((1/2)_n / n!)^2, e_n = -c_n/(2n-1)."""
    c = [Fraction(1)]
    for n in range(1, n_terms + 1):
        c.append(c[-1] * Fraction(2 * n - 1, 2 * n) ** 2)
    e = [Fraction(1)] + [-c[n] / (2 * n - 1) for n in range(1, n_terms + 1)]
    f = [2 * e[n] - (e[n - 1] if n else 0) - 2 * c[n] + (2 * c[n - 1] if n else 0)
         for n in range(n_terms + 1)]
    assert f[0] == 0 and f[1] == 0 and all(x > 0 for x in f[2:])
    return np.array([float(x) for x in f])


F_SERIES = _series_coefficients(SERIES_TERMS)


def series_remainder_bound(m: float, terms: int = SERIES_TERMS) -> float:
    """Upper bound of the truncated tail, relative to the series sum (coefficients decrease)."""
    head = float(np.sum(F_SERIES[2: terms + 1] * m ** np.arange(2, terms + 1)))
    return float(F_SERIES[terms] * m ** (terms + 1) / (1 - m)) / head


def _f_over_m(m: Arr) -> Arr:
    """sum_{n>=2} f_n m^(n-1) (in units of pi/2), by Horner's rule."""
    acc = np.zeros_like(m)
    for coef in F_SERIES[:1:-1]:  # f_N ... f_2
        acc = acc * m + coef
    return acc * m


def _a_series_coefficients(n_terms: int) -> NDArray[np.float64]:
    """g_n (in units of pi/2) of g(m) = (1 - m/2) K(m) - E(m) = (pi/2) sum g_n m^n (Phase 4A).
    From the hypergeometric series of K and E: g_n = c_(n-1) (n-1) / (2n), all positive for
    n >= 2 (no cancellation), g_0 = g_1 = 0."""
    c = [Fraction(1)]
    for n in range(1, n_terms + 1):
        c.append(c[-1] * Fraction(2 * n - 1, 2 * n) ** 2)
    e = [Fraction(1)] + [-c[n] / (2 * n - 1) for n in range(1, n_terms + 1)]
    g = [c[n] - (c[n - 1] / 2 if n else 0) - e[n] for n in range(n_terms + 1)]
    assert g[0] == 0 and g[1] == 0
    assert all(g[n] == c[n - 1] * (n - 1) / (2 * n) and g[n] > 0 for n in range(2, n_terms + 1))
    return np.array([float(x) for x in g])


G_SERIES = _a_series_coefficients(SERIES_TERMS)


def _g_over_m(m: Arr) -> Arr:
    """sum_{n>=2} g_n m^(n-1) (in units of pi/2), by Horner's rule."""
    acc = np.zeros_like(m)
    for coef in G_SERIES[:1:-1]:
        acc = acc * m + coef
    return acc * m


def filament_tolerance(scale: Arr) -> Arr:
    """Distance below which a point cannot be told apart from an ideal filament, for distances
    computed from local coordinates of size ``scale`` (see the module docstring)."""
    out: Arr = FILAMENT_EPS_FACTOR * EPS * scale
    return out


def precision_bound(scale: Arr, dist: Arr) -> Arr:
    """Relative accuracy bound PRECISION_EPS_FACTOR · ε · S / d of a filament's field."""
    with np.errstate(divide="ignore", invalid="ignore"):  # masked where singular (d = 0)
        out: Arr = PRECISION_EPS_FACTOR * EPS * scale / dist
    return out


def wire_field(points: Arr, w: WireSource) -> tuple[Arr, Mask, Arr]:
    """(B, singular mask, relative precision bound) of an infinite wire."""
    r = points - w.point_m
    rp = r - (r @ w.direction)[:, None] * w.direction
    s2 = np.einsum("ij,ij->i", rp, rp)
    scale = np.linalg.norm(r, axis=1)
    dist = np.sqrt(s2)
    near = dist <= filament_tolerance(scale)
    s2 = np.where(near, 1.0, s2)
    b = (MU0 * w.current_A / (2.0 * np.pi) / s2)[:, None] * np.cross(w.direction, rp)
    b[near] = np.nan
    prec = np.where(near, 0.0, precision_bound(scale, dist))
    return b, near, prec


def loop_local(rho: Arr, z: Arr, a: float | Arr, current: float | Arr
               ) -> tuple[Arr, Arr, Arr]:
    """(B_rho, B_z, distance to the wire) in local cylindrical coordinates. ``a`` and
    ``current`` may be arrays broadcast with ``rho`` (many loops at once, Phase 3B)."""
    a_arr = np.broadcast_to(np.asarray(a, np.float64), np.shape(rho))
    c = MU0 * current / (2.0 * np.pi)
    dp = (a + rho) ** 2 + z**2
    dm = (a - rho) ** 2 + z**2
    # m <= 1 always. Within about 4e-8 a of the wire the exact m = 1 - q has q < ~4e-16, and
    # 4a rho / D+ can round to just above 1, where ellipe returns NaN; it is clamped to 1. This
    # changes E by |E(1 - q) - E(1)| <= (q/4)(ln(16/q) + 1) < 1e-14 (E is continuous at m = 1,
    # E(1) = 1), i.e. below rounding. K never uses m: it is ellipkm1(q) with q = D-^2 / D+^2
    # formed geometrically, so its logarithmic divergence near the wire is resolved exactly.
    m = np.minimum(4.0 * a * rho / dp, 1.0)
    p1 = dm / dp  # 1 - m, formed without cancellation
    with np.errstate(divide="ignore", invalid="ignore"):
        k = ellipkm1(p1)
        e = ellipe(m)
        sq = np.sqrt(dp)
        # a^2 - rho^2 - z^2 factored: near the wire (rho ~ a) a^2 - rho^2 would cancel and lose
        # eps a / d of relative accuracy; (a - rho)(a + rho) keeps a - rho exact (Sterbenz).
        bz = c / sq * (k + ((a - rho) * (a + rho) - z * z) / dm * e)
        b_rho = c * z / (rho * sq) * (-k + (a * a + rho * rho + z * z) / dm * e)
        # Near-axis series, evaluated only where it is used (m <= NEAR_AXIS_M).
        near = m <= NEAR_AXIS_M
        if np.any(near):
            mn = m[near]
            c_near = np.broadcast_to(c, np.shape(rho))[near]
            b_rho[near] = (c_near * z[near] / sq[near] * (4.0 * a_arr[near] / dp[near])
                           * (np.pi / 2.0) * _f_over_m(mn) / (2.0 * p1[near]))
    return b_rho, bz, np.sqrt(dm)


def loop_vector_potential_local(rho: Arr, z: Arr, a: float | Arr, current: float | Arr
                                ) -> tuple[Arr, Arr]:
    """(A_phi, distance to the wire) of a circular loop in its local cylindrical coordinates
    (Phase 4A), Coulomb gauge: A = mu0 I / (4 pi) ∮ dl' / |r - r'|, which for a circle is
    azimuthal,

        A_phi = mu0 I sqrt(D+) / (2 pi rho) * g(m),  g(m) = (1 - m/2) K(m) - E(m),

    with the same m = 4 a rho / D+ and q = 1 - m = D- / D+ as ``loop_local`` (parameter m, not
    the modulus k). K = ellipkm1(q) resolves the logarithmic divergence at the wire. For
    m <= NEAR_AXIS_M g(m) cancels (g ~ (pi/32) m^2); the exact positive series is used, written
    as A_phi = 2 mu0 I a / (pi sqrt(D+)) * g(m)/m, which is exact on the axis (A_phi = 0) and
    reduces to the dipole form mu0 I a^2 rho / (4 r^3) far away. Positive I: A along +phi
    (counter-clockwise about the loop normal), like the current."""
    a_arr = np.broadcast_to(np.asarray(a, np.float64), np.shape(rho))
    dp = (a + rho) ** 2 + z**2
    dm = (a - rho) ** 2 + z**2
    m = np.minimum(4.0 * a * rho / dp, 1.0)  # same clamp as loop_local (see there)
    q = dm / dp
    near = m <= NEAR_AXIS_M
    with np.errstate(divide="ignore", invalid="ignore"):
        k = ellipkm1(q)
        e = ellipe(m)
        sq = np.sqrt(dp)
        a_phi = MU0 * current * sq / (2.0 * np.pi * rho) * ((1.0 - 0.5 * m) * k - e)
        if np.any(near):
            c_near = np.broadcast_to(np.asarray(MU0 * current, np.float64), np.shape(rho))[near]
            a_phi[near] = (2.0 * c_near * a_arr[near] / (np.pi * sq[near])
                           * (np.pi / 2.0) * _g_over_m(m[near]))
    return a_phi, np.sqrt(dm)


LOOP_BATCH_ELEMENTS = 400_000  # points × loops evaluated per numpy call (bounds memory)


def _loop_arrays(loops: list[LoopSource]) -> tuple[Arr, Arr, Arr]:
    return (np.array([lp.center_m for lp in loops]), np.array([lp.normal for lp in loops]),
            np.array([lp.radius_m for lp in loops]))


def _chunks(n_points: int, n_loops: int) -> list[slice]:
    step = max(1, LOOP_BATCH_ELEMENTS // max(n_loops, 1))
    return [slice(i, i + step) for i in range(0, n_points, step)]


# Unit-current fields per source object (Phase 4A). Every loop object's B and A are linear in
# its current, so they are computed once per geometry and sample set at 1 A per turn and scaled:
# B(t) = I(t) B_unit, dB/dt = dI/dt B_unit, E_ind = -dI/dt A_unit. Large sample sets (grids) are
# cached by a digest of the turn geometry and the points; time and current never enter the key,
# so moving the simulation time reuses them. Small sets (probes, field-line steps) are not cached.
UNIT_CACHE_MIN_POINTS = 2000
UNIT_CACHE_ENTRIES = 48
_UNIT_CACHE: OrderedDict[tuple[str, str, str], tuple[Arr, Mask, Arr]] = OrderedDict()


def _digest(*arrays: Arr) -> str:
    h = hashlib.blake2b(digest_size=16)
    for a in arrays:
        h.update(np.ascontiguousarray(a, np.float64).tobytes())
        h.update(str(a.shape).encode())
    return h.hexdigest()


def _group_unit(loops: list[LoopSource], points: Arr, which: Literal["B", "A"]
                ) -> tuple[Arr, Mask, Arr]:
    """(field at 1 A per turn, singular mask, precision bound) of one object's turns."""
    c, nrm, rad = _loop_arrays(loops)
    out = np.zeros_like(points)
    sing = np.zeros(points.shape[0], bool)
    prec = np.zeros(points.shape[0])
    for sl in _chunks(points.shape[0], len(loops)):
        d = points[sl, None, :] - c[None, :, :]  # (P, L, 3)
        z = np.einsum("plk,lk->pl", d, nrm)
        rvec = d - z[..., None] * nrm[None, :, :]
        rho = np.linalg.norm(rvec, axis=2)
        ones = np.ones_like(rho)
        # Non-finite values on a filament are replaced by the singular mask below.
        with np.errstate(divide="ignore", invalid="ignore"):
            rhat = np.where(rho[..., None] > 0, rvec / rho[..., None], 0.0)
            if which == "B":
                br, bz, dist = loop_local(rho, z, rad[None, :] * ones, ones)
                vec = br[..., None] * rhat + bz[..., None] * nrm[None, :, :]
            else:
                a_phi, dist = loop_vector_potential_local(rho, z, rad[None, :] * ones, ones)
                tangent = np.cross(np.broadcast_to(nrm[None, :, :], rhat.shape), rhat)
                vec = a_phi[..., None] * tangent  # along the positive current direction
        scale = rad[None, :] + np.linalg.norm(d, axis=2)
        on = dist <= filament_tolerance(scale)
        vec[on] = 0.0
        out[sl] = vec.sum(axis=1)
        sing[sl] = on.any(axis=1)
        prec[sl] = np.where(on, 0.0, precision_bound(scale, dist)).max(axis=1)
    out[sing] = np.nan
    prec[sing] = 0.0
    return out, sing, prec


def _group_unit_cached(loops: list[LoopSource], points: Arr, which: Literal["B", "A"]
                       ) -> tuple[Arr, Mask, Arr]:
    if points.shape[0] < UNIT_CACHE_MIN_POINTS:
        return _group_unit(loops, points, which)
    c, nrm, rad = _loop_arrays(loops)
    key = (which, _digest(c, nrm, rad), _digest(points))
    hit = _UNIT_CACHE.get(key)
    if hit is not None:
        _UNIT_CACHE.move_to_end(key)
        return hit
    val = _group_unit(loops, points, which)
    _UNIT_CACHE[key] = val
    while len(_UNIT_CACHE) > UNIT_CACHE_ENTRIES:
        _UNIT_CACHE.popitem(last=False)
    return val


def _groups(loops: list[LoopSource]) -> list[tuple[float, list[LoopSource]]]:
    """Loops grouped by object (all turns of an object carry the same current)."""
    by: dict[tuple[str, float], list[LoopSource]] = {}
    for lp in loops:
        by.setdefault((lp.object_id, lp.current_A), []).append(lp)
    return [(cur, grp) for (_, cur), grp in by.items()]


def _scaled_sum(loops: list[LoopSource], points: Arr, which: Literal["B", "A"]
                ) -> tuple[Arr, Mask, Arr]:
    out = np.zeros_like(points)
    sing = np.zeros(points.shape[0], bool)
    prec = np.zeros(points.shape[0])
    for cur, grp in _groups(loops):
        unit, s_g, p_g = _group_unit_cached(grp, points, which)
        out += cur * np.nan_to_num(unit)
        sing |= s_g
        prec = np.maximum(prec, p_g)
    out[sing] = np.nan
    prec[sing] = 0.0
    return out, sing, prec


def loops_field(loops: list[LoopSource], points: Arr) -> tuple[Arr, Mask, Arr]:
    """Sum of many circular loops' fields (the turns of solenoids and toroids): per object, the
    unit-current field (one broadcast evaluation of ``loop_local`` over its turns, cached for
    large sample sets) times its current. Returns (B, singular mask, relative precision bound):
    a point within the filament tolerance of any turn is singular (B NaN, whatever the other
    turns give); the precision bound is the largest over the turns."""
    return _scaled_sum(loops, points, "B")


def loops_vector_potential(loops: list[LoopSource], points: Arr) -> tuple[Arr, Mask, Arr]:
    """Coulomb-gauge vector potential A (T·m) of circular loops, like ``loops_field``
    (Phase 4A). With currents dI/dt instead of I, -A of the same call is E_ind."""
    return _scaled_sum(loops, points, "A")


# ------------------------------------------------- Phase 4C: passive (induced-current) circuits


def _passive_loop(f: PassiveFilament, current: float) -> LoopSource:
    n = np.asarray(f.normal, float)
    return LoopSource(f.id, current, np.asarray(f.center_m, float), n / np.linalg.norm(n),
                      float(f.radius_m or 0.0), np.asarray(f.u, float) / np.linalg.norm(f.u))


def passive_unit(points: Arr, f: PassiveFilament, which: Literal["B", "A"] = "B"
                 ) -> tuple[Arr, Mask]:
    """Field (B or A) of one passive circuit carrying 1 A per turn, times its turns, and the
    mask of points on its filament (singular; NaN there)."""
    if f.kind == "circle":
        lp = _passive_loop(f, 1.0)
        val, sing, _ = (loops_field([lp], points) if which == "B"
                        else loops_vector_potential([lp], points))
    else:
        verts = np.asarray(f.vertices_m, float)
        val = (segments.segment_field(points, verts) if which == "B"
               else segments.segment_vector_potential(points, verts))
        scale = np.linalg.norm(points - verts.mean(axis=0), axis=1) + float(
            np.ptp(verts, axis=0).max())
        sing = segments.distance_to_polygon(points, verts) <= filament_tolerance(scale)
        val = np.where(sing[:, None], np.nan, val)
    out: Arr = val * f.turns
    return out, sing


def passive_distance(points: Arr, fils: list[PassiveFilament]) -> Arr:
    out = np.full(points.shape[0], np.inf)
    for f in fils:
        if f.kind == "circle":
            lp = _passive_loop(f, 1.0)
            d = points - lp.center_m
            z = d @ lp.normal
            rho = np.linalg.norm(d - z[:, None] * lp.normal, axis=1)
            out = np.minimum(out, np.hypot(rho - lp.radius_m, z))
        else:
            out = np.minimum(out, segments.distance_to_polygon(
                points, np.asarray(f.vertices_m, float)))
    return out


def passive_fields(points: Arr, fils: list[PassiveFilament], which: Literal["B", "A"] = "B",
                   rate: bool = False) -> tuple[Arr, Mask, list[Arr]]:
    """Σ I_j (or dI_j/dt) × unit field of every passive circuit, the singular mask, and each
    circuit's own contribution."""
    total = np.zeros_like(points)
    sing = np.zeros(points.shape[0], bool)
    parts: list[Arr] = []
    for f in fils:
        unit, s = passive_unit(points, f, which)
        part = unit * (f.rate_A_per_s if rate else f.current_A)
        parts.append(part)
        sing |= s
        total = total + np.nan_to_num(part)
    total[sing] = np.nan
    return total, sing, parts


def loop_field(points: Arr, lp: LoopSource) -> Arr:
    d = points - lp.center_m
    z = d @ lp.normal
    rvec = d - z[:, None] * lp.normal
    rho = np.linalg.norm(rvec, axis=1)
    b_rho, b_z, dist = loop_local(rho, z, lp.radius_m, lp.current_A)
    with np.errstate(divide="ignore", invalid="ignore"):
        rhat = np.where(rho[:, None] > 0, rvec / rho[:, None], 0.0)
    b = b_rho[:, None] * rhat + b_z[:, None] * lp.normal
    b[dist <= filament_tolerance(lp.radius_m + np.linalg.norm(d, axis=1))] = np.nan
    return b


# Per-point evaluation status (Phase 3B). Every status other than OK makes B and/or H undefined
# at that point, and is counted and explained, never hidden.
ST_OK, ST_SINGULAR, ST_SHEET, ST_END_FACE, ST_CORE_BOUNDARY = 0, 1, 2, 3, 4
# Relative accuracy of the magnet's surface-current quadrature by use.
MAGNET_CHUNK = 4000  # points per adaptive-quadrature call
MAGNET_RTOL = {"field": 1e-9, "probe": 1e-11, "lines": 1e-7, "ampere": 1e-11}


def magnet_local(points: Arr, mg: MagnetSource) -> tuple[Arr, Arr, Arr]:
    """Local cylindrical (rho, z) and unit radial vectors of points about a magnet's axis."""
    d = points - mg.center_m
    z = d @ mg.axis
    rvec = d - z[:, None] * mg.axis
    rho = np.linalg.norm(rvec, axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        rhat = np.where(rho[:, None] > 0, rvec / rho[:, None], 0.0)
    return rho, z, rhat


def magnet_regions(points: Arr, mg: MagnetSource, tol: float) -> tuple[Mask, Mask, Mask]:
    """Masks (inside, on the side-wall current sheet or its rim, on an end face)."""
    rho, z, _ = magnet_local(points, mg)
    half = mg.length_m / 2
    dz = np.maximum(np.abs(z) - half, 0.0)
    sheet = np.hypot(rho - mg.radius_m, dz) <= tol
    end_face = (~sheet) & (rho < mg.radius_m) & (np.abs(np.abs(z) - half) <= tol)
    inside = (~sheet) & (~end_face) & (rho < mg.radius_m) & (np.abs(z) < half)
    return inside, sheet, end_face


def magnet_field(points: Arr, mg: MagnetSource, tol: float, rtol: float
                 ) -> tuple[Arr, Mask, Mask, int]:
    """B of a uniformly magnetized cylinder from its side-wall bound current sheet
    K = M e_phi, as the integral of unit-current circular loops (the single loop
    implementation ``loop_local``): B = M ∫ B_loop(r; a, z', 1 A) dz' over [-L/2, L/2].

    Adaptive G7/K15 per point, split at z' = z where the integrand peaks next to the sheet.
    Returns (B, on_sheet mask, not-converged mask, integrand evaluations). Points on the sheet
    (within ``tol``) get NaN: the ideal sheet has different one-sided tangential limits there."""
    n = points.shape[0]
    if n > MAGNET_CHUNK:  # bound the quadrature's working memory
        parts = [magnet_field(points[i:i + MAGNET_CHUNK], mg, tol, rtol)
                 for i in range(0, n, MAGNET_CHUNK)]
        return (np.concatenate([q[0] for q in parts]), np.concatenate([q[1] for q in parts]),
                np.concatenate([q[2] for q in parts]), sum(q[3] for q in parts))
    b = np.zeros((n, 3))
    rho, z, rhat = magnet_local(points, mg)
    half, a = mg.length_m / 2, mg.radius_m
    sheet = np.hypot(rho - a, np.maximum(np.abs(z) - half, 0.0)) <= tol
    idx = np.flatnonzero(~sheet)
    unconverged = np.zeros(n, bool)
    if idx.size == 0 or mg.magnetization_A_per_m == 0.0:
        b[sheet] = np.nan
        return b, sheet, unconverged, 0
    # Initial partition per point: split at z' = clip(z), and geometrically around it at
    # offsets d·4^j (d = distance to the sheet) up to the cylinder length, so a point close to
    # the sheet starts with intervals matched to its peak instead of halving towards it pass by
    # pass. The adaptive refinement and its convergence test are unchanged.
    zc = np.clip(z[idx], -half, half)
    d = np.maximum(np.hypot(rho[idx] - a, np.maximum(np.abs(z[idx]) - half, 0.0)), 1e-300)
    offs = d[:, None] * 4.0 ** np.arange(24)[None, :]
    edges = np.concatenate([np.full((idx.size, 1), -half), zc[:, None] - offs[:, ::-1],
                            zc[:, None], zc[:, None] + offs, np.full((idx.size, 1), half)],
                           axis=1)
    edges = np.clip(edges, -half, half)
    lo_all, hi_all = edges[:, :-1], edges[:, 1:]
    keep = hi_all > lo_all
    item_pt = np.repeat(idx, keep.sum(axis=1))
    lo, hi = lo_all[keep], hi_all[keep]
    rho_i, z_i = rho[item_pt], z[item_pt]

    def integrand(items: NDArray[np.int64], t: Arr) -> Arr:
        br, bz, _ = loop_local(rho_i[items], z_i[items] - t, a, 1.0)
        return np.stack([br, bz], axis=1)

    res = adaptive_gk(integrand, lo, hi, 2, rtol, atol=1e-15 * MU0)
    vals = res.value * mg.magnetization_A_per_m
    sums = np.zeros((n, 2))
    np.add.at(sums, item_pt, vals)
    # Items of one point share the point's tolerance: the per-item absolute tolerance below is
    # tiny, so the relative test on each item is the binding one (conservative).
    bad = np.zeros(n, bool)
    np.logical_or.at(bad, item_pt, ~res.converged)
    unconverged[:] = bad
    b = sums[:, :1] * rhat + sums[:, 1:2] * mg.axis
    b[sheet] = np.nan
    return b, sheet, unconverged, res.evaluations


def ideal_toroid_fields(points: Arr, t: IdealToroidSource, tol: float
                        ) -> tuple[Arr, Arr, Mask]:
    """Ideal continuous-winding toroid: H = N I/(2 pi rho) e_phi and B = mu0 mu_r H inside the
    core (rho - R)^2 + z^2 < b_core^2, zero outside (ideal confinement). Points within ``tol`` of
    the core surface are a one-sided ideal-model boundary: NaN, reported.
    Returns (B, H, boundary mask)."""
    d = points - t.center_m
    z = d @ t.axis
    rvec = d - z[:, None] * t.axis
    rho = np.linalg.norm(rvec, axis=1)
    r_core = np.hypot(rho - t.major_radius_m, z)
    boundary = np.abs(r_core - t.core_radius_m) <= tol
    inside = (r_core < t.core_radius_m) & ~boundary & (rho > 0)
    h = np.zeros_like(points)
    with np.errstate(divide="ignore", invalid="ignore"):
        e_phi = np.cross(t.axis, rvec) / rho[:, None]
    hmag = t.turns * t.current_A / (2.0 * np.pi * rho[inside])
    h[inside] = hmag[:, None] * e_phi[inside]
    b = MU0 * t.relative_permeability * h
    b[boundary] = np.nan
    h[boundary] = np.nan
    return b, h, boundary


def source_fields(points: Arr, cs: CurrentSources, r_min: float,
                  rtol: float = MAGNET_RTOL["field"]) -> list[Arr]:
    """Each source object's own B (N, 3), in the order of ``cs.ids`` (the turns of a solenoid or
    toroid are summed into their object)."""
    by_id: dict[str, Arr] = {oid: np.zeros_like(points) for oid in cs.ids}
    for w in cs.wires:
        by_id[w.object_id] += wire_field(points, w)[0]
    owners = sorted({lp.object_id for lp in cs.loops})
    for oid in owners:
        b_obj, _, _ = loops_field([lp for lp in cs.loops if lp.object_id == oid], points)
        by_id[oid] += b_obj
    tol = sheet_tolerance(cs, r_min)
    for mg in cs.magnets:
        by_id[mg.object_id] += magnet_field(points, mg, tol, rtol)[0]
    for t in cs.ideal_toroids:
        by_id[t.object_id] += ideal_toroid_fields(points, t, tol)[0]
    return [by_id[oid] for oid in cs.ids]


def sheet_tolerance(cs: CurrentSources, r_min: float) -> float:
    """Geometric tolerance for "on a current sheet / core surface": IN_PLANE_FACTOR of the
    domain diagonal (r_min is COINCIDENCE_FACTOR of it)."""
    return r_min * (IN_PLANE_FACTOR / COINCIDENCE_FACTOR)


@dataclass
class FieldEval:
    b: Arr  # (N, 3) T; NaN where undefined
    h: Arr  # (N, 3) A/m; NaN where undefined
    m: Arr  # (N, 3) A/m prescribed magnetization at the point (0 outside magnets)
    status: NDArray[np.int64]  # ST_* per point
    unconverged: int  # points whose magnet quadrature did not converge
    material: NDArray[np.int64]  # 0 vacuum, 1 inside a magnet, 2 inside an ideal core
    # Relative accuracy bound from the nearest filament (8 eps S / d), 0 where not applicable.
    precision: Arr = dc_field(default_factory=lambda: np.zeros(0))


def evaluate_bh(points: Arr, cs: CurrentSources, r_min: float,
                rtol: float = MAGNET_RTOL["field"]) -> FieldEval:
    """B, H and M at points, with the constitutive relation of the region each point lies in:
    vacuum H = B/mu0; inside a magnet H = B/mu0 - M; inside the ideal toroid's core
    H = B/(mu0 mu_r) (the ideal toroid is never combined with other sources)."""
    n = points.shape[0]
    b = np.zeros((n, 3))
    status = np.zeros(n, np.int64)
    precision = np.zeros(n)
    for w in cs.wires:
        bi, wsing, wprec = wire_field(points, w)
        status[wsing] = ST_SINGULAR
        b += bi
        precision = np.maximum(precision, wprec)
    if cs.loops:
        bl, sing, lprec = loops_field(cs.loops, points)
        status[sing] = ST_SINGULAR
        b += bl
        precision = np.maximum(precision, lprec)
    tol = sheet_tolerance(cs, r_min)
    m = np.zeros((n, 3))
    material = np.zeros(n, np.int64)
    unconverged = np.zeros(n, bool)
    h_extra: Arr | None = None
    for mg in cs.magnets:
        bi, sheet, unc, _ = magnet_field(points, mg, tol, rtol)
        inside, _, end_face = magnet_regions(points, mg, tol)
        b += np.nan_to_num(bi)
        status[sheet & (status == ST_OK)] = ST_SHEET
        status[end_face & (status == ST_OK)] = ST_END_FACE
        m[inside] += mg.m_vector
        material[inside] = 1
        unconverged |= unc
    for t in cs.ideal_toroids:
        bi, hi, boundary = ideal_toroid_fields(points, t, tol)
        b += np.nan_to_num(bi)
        h_extra = hi
        status[boundary & (status == ST_OK)] = ST_CORE_BOUNDARY
        material[np.linalg.norm(np.nan_to_num(hi), axis=1) > 0] = 2
    h = np.nan_to_num(h_extra) if h_extra is not None else b / MU0 - m
    b_undef = (status == ST_SINGULAR) | (status == ST_SHEET) | (status == ST_CORE_BOUNDARY)
    h_undef = b_undef | (status == ST_END_FACE)
    b[b_undef] = np.nan
    h[h_undef] = np.nan
    precision[status == ST_SINGULAR] = 0.0
    return FieldEval(b=b, h=h, m=m, status=status, unconverged=int(np.count_nonzero(unconverged)),
                     material=material, precision=precision)


def evaluate(points: Arr, cs: CurrentSources, r_min: float,
             rtol: float = MAGNET_RTOL["field"]) -> Arr:
    """Total B [T] (N, 3) by superposition; NaN where it is singular or a sheet boundary."""
    return evaluate_bh(points, cs, r_min, rtol).b


def region_code(points: Arr, cs: CurrentSources) -> NDArray[np.int64]:
    """Material region of each point (bit k: inside magnet k; bit 40: inside the ideal core).
    Pure geometry, used where B or H jumps (field-line steps, Ampère breakpoints)."""
    code = np.zeros(points.shape[0], np.int64)
    for k, mg in enumerate(cs.magnets):
        rho, z, _ = magnet_local(points, mg)
        code |= ((rho < mg.radius_m) & (np.abs(z) < mg.length_m / 2)).astype(np.int64) << k
    for t in cs.ideal_toroids:
        d = points - t.center_m
        z = d @ t.axis
        rho = np.linalg.norm(d - z[:, None] * t.axis, axis=1)
        inside = np.hypot(rho - t.major_radius_m, z) < t.core_radius_m
        code |= inside.astype(np.int64) << 40
    return code


def distance_to_boundaries(points: Arr, cs: CurrentSources) -> Arr:
    """Distance to the nearest magnet side wall or ideal core surface (inf if none)."""
    out = np.full(points.shape[0], np.inf)
    for mg in cs.magnets:
        rho, z, _ = magnet_local(points, mg)
        out = np.minimum(out, np.hypot(rho - mg.radius_m,
                                       np.maximum(np.abs(z) - mg.length_m / 2, 0.0)))
    for t in cs.ideal_toroids:
        d = points - t.center_m
        z = d @ t.axis
        rho = np.linalg.norm(d - z[:, None] * t.axis, axis=1)
        out = np.minimum(out, np.abs(np.hypot(rho - t.major_radius_m, z) - t.core_radius_m))
    return out


def distance_to_magnet_surface(points: Arr, mg: MagnetSource) -> Arr:
    """Distance to the whole closed surface of a magnet (side wall and end faces)."""
    rho, z, _ = magnet_local(points, mg)
    half, a = mg.length_m / 2, mg.radius_m
    side = np.hypot(rho - a, np.maximum(np.abs(z) - half, 0.0))
    end = np.hypot(np.maximum(rho - a, 0.0), np.abs(z) - half)
    out: Arr = np.minimum(side, end)
    return out


def nearest_filament(points: Arr, cs: CurrentSources) -> tuple[Arr, Arr]:
    """(distance, coordinate scale S) of the nearest filament per point, with the same
    distance formulas and scales as the field evaluation (inf, nan where there is none)."""
    dist = np.full(points.shape[0], np.inf)
    scale = np.full(points.shape[0], np.nan)
    for w in cs.wires:
        r = points - w.point_m
        rp = r - (r @ w.direction)[:, None] * w.direction
        d = np.linalg.norm(rp, axis=1)
        closer = d < dist
        dist[closer], scale[closer] = d[closer], np.linalg.norm(r, axis=1)[closer]
    if cs.loops:
        c, nrm, rad = _loop_arrays(cs.loops)
        for sl in _chunks(points.shape[0], len(cs.loops)):
            dv = points[sl, None, :] - c[None, :, :]
            z = np.einsum("plk,lk->pl", dv, nrm)
            rho = np.linalg.norm(dv - z[..., None] * nrm[None, :, :], axis=2)
            d = np.sqrt((rad[None, :] - rho) ** 2 + z**2)
            j = d.argmin(axis=1)
            idx = np.arange(d.shape[0])
            dj = d[idx, j]
            sj = rad[j] + np.linalg.norm(dv[idx, j], axis=1)
            closer = dj < dist[sl]
            dist[sl] = np.where(closer, dj, dist[sl])
            scale[sl] = np.where(closer, sj, scale[sl])
    return dist, scale


def distance_to_sources(points: Arr, cs: CurrentSources) -> Arr:
    """Distance to the nearest filament (wire axis or loop wire), inf if there is none."""
    out = np.full(points.shape[0], np.inf)
    for w in cs.wires:
        r = points - w.point_m
        rp = r - (r @ w.direction)[:, None] * w.direction
        out = np.minimum(out, np.linalg.norm(rp, axis=1))
    if cs.loops:
        c, nrm, rad = _loop_arrays(cs.loops)
        for sl in _chunks(points.shape[0], len(cs.loops)):
            d = points[sl, None, :] - c[None, :, :]
            z = np.einsum("plk,lk->pl", d, nrm)
            rho = np.linalg.norm(d - z[..., None] * nrm[None, :, :], axis=2)
            out[sl] = np.minimum(out[sl], np.sqrt((rad[None, :] - rho) ** 2 + z**2).min(axis=1))
    return out


def _stats(a: Arr, vector: bool) -> ArrayStats:
    v = np.sqrt(np.einsum("...j,...j->...", a, a)) if vector else a
    finite = np.isfinite(v)
    bad = int(v.size - np.count_nonzero(finite))
    if not finite.any():
        return ArrayStats(min=None, max=None, non_finite_count=bad)
    return ArrayStats(min=float(v[finite].min()), max=float(v[finite].max()), non_finite_count=bad)


def _plane_normal(g: PlaneGridSampling) -> Arr:
    out: Arr = np.cross(np.asarray(g.u_dir, float), np.asarray(g.v_dir, float))
    return out


def current_source_table(cs: CurrentSources, planes: list[PlaneGridSampling]
                         ) -> list[CurrentSourceInfo]:
    """One entry per source object, with its world geometry (for drawing and the UI)."""
    wires = {w.object_id: w for w in cs.wires}
    turns: dict[str, list[LoopSource]] = {}
    for lp in cs.loops:
        turns.setdefault(lp.object_id, []).append(lp)
    out: list[CurrentSourceInfo] = []
    for obj in cs.objects:
        c = obj.center_m if obj.center_m is not None else np.zeros(3)
        ax = obj.axis if obj.axis is not None else np.array([0.0, 0.0, 1.0])
        base = {"object_id": obj.object_id, "kind": obj.kind,
                "current_A": float(obj.current_A or 0.0), "point_m": [float(x) for x in c],
                "direction": [float(x) for x in ax], "turns": obj.turns}
        dist = {g.id: float((c - np.asarray(g.center_m, float)) @ _plane_normal(g))
                for g in planes}
        geom = [TurnGeometry(center_m=[float(x) for x in t.center_m],
                             normal=[float(x) for x in t.normal], radius_m=t.radius_m)
                for t in turns.get(obj.object_id, [])]
        if obj.kind == "infinite_wire":
            w = wires[obj.object_id]
            cross: dict[str, list[float] | None] = {}
            sign: dict[str, int] = {}
            for g in planes:
                n = _plane_normal(g)
                dn = float(w.direction @ n)
                if abs(dn) <= 1e-9:
                    cross[g.id], sign[g.id] = None, 0
                else:
                    t_ = float((np.asarray(g.center_m, float) - w.point_m) @ n) / dn
                    cross[g.id] = [float(x) for x in w.point_m + t_ * w.direction]
                    sign[g.id] = (1 if dn * w.current_A > 0 else
                                  (-1 if dn * w.current_A < 0 else 0))
            out.append(CurrentSourceInfo(**base, plane_crossing_m=cross,
                                         plane_crossing_sign=sign))
        elif obj.kind == "circular_loop":
            out.append(CurrentSourceInfo(**base, radius_m=obj.params["radius_m"],
                                         turns_geometry=geom, plane_distance_m=dist))
        elif obj.kind == "solenoid":
            a, length = obj.params["radius_m"], obj.params["length_m"]
            spacing = length / (obj.turns - 1) if obj.turns > 1 else None
            ideal = None
            if obj.turns > 1 and length > 0:
                n_per = obj.turns / length
                ideal = IdealSolenoidInfo(turns_per_m=n_per,
                                          B_T=MU0 * n_per * float(obj.current_A or 0.0),
                                          H_A_per_m=n_per * float(obj.current_A or 0.0))
            out.append(CurrentSourceInfo(**base, radius_m=a, length_m=length,
                                         turn_spacing_m=spacing, ideal_long_solenoid=ideal,
                                         turns_geometry=geom, plane_distance_m=dist))
        elif obj.kind == "toroid_finite":
            out.append(CurrentSourceInfo(**base, major_radius_m=obj.params["major_radius_m"],
                                         winding_radius_m=obj.params["winding_radius_m"],
                                         turns_geometry=geom, plane_distance_m=dist))
        elif obj.kind == "toroid_ideal":
            out.append(CurrentSourceInfo(
                **base, major_radius_m=obj.params["major_radius_m"],
                core_radius_m=obj.params["core_radius_m"],
                relative_permeability=obj.params["relative_permeability"],
                plane_distance_m=dist))
        else:  # permanent magnet
            mg = next(m for m in cs.magnets if m.object_id == obj.object_id)
            out.append(CurrentSourceInfo(
                **base, radius_m=mg.radius_m, length_m=mg.length_m,
                magnetization_A_per_m=mg.magnetization_A_per_m,
                moment_A_m2=[float(x) for x in mg.moment_A_m2], plane_distance_m=dist))
    return out


_FL_SETTINGS = {
    "preview": {"atol": 1e-4, "h_max": 1 / 24, "max_steps": 500},
    "normal": {"atol": 1e-5, "h_max": 1 / 48, "max_steps": 1500},
    "high": {"atol": 1e-6, "h_max": 1 / 96, "max_steps": 5000},
}
_MAX_LINES = 900


def source_h(points: Arr, cs: CurrentSources, oid: str, b_i: Arr, tol: float) -> Arr:
    """H of one source alone: B_i/mu0 in vacuum, B_i/mu0 - M_i inside a magnet (its own
    magnetization), B_i/(mu0 mu_r) inside an ideal core."""
    for t in cs.ideal_toroids:
        if t.object_id == oid:
            return ideal_toroid_fields(points, t, tol)[1]
    h: Arr = b_i / MU0
    for mg in cs.magnets:
        if mg.object_id == oid:
            inside, _, end_face = magnet_regions(points, mg, tol)
            h = h - np.where(inside[:, None], mg.m_vector[None, :], 0.0)
            h[end_face] = np.nan
    return h


SPEED_OF_LIGHT = 299_792_458.0  # m/s
QUASISTATIC_WARN = 1e-2  # f L / c above this: retardation across the region is not negligible


def _quasistatic_ratio(scene: Scene) -> float:
    """Largest L / (c tau) over the time-dependent sources, with L the domain diagonal and tau
    the shortest time scale of the profile (1/f for a sinusoid, the ramp duration, the shortest
    keyframe interval). The magnetoquasistatic model neglects retardation, which is valid only
    when this is small."""
    length = scene.domain.diagonal_m
    worst = 0.0
    for o in scene.objects:
        src = o.source
        if not isinstance(src, TimeDependentCurrent) or src.profile is None:
            continue
        p = src.profile
        if isinstance(p, SinusoidalProfile):
            tau = 1.0 / p.frequency_Hz
        elif isinstance(p, RampProfile):
            tau = p.t_end_s - p.t_start_s
        elif isinstance(p, PiecewiseLinearProfile):
            tau = min(b.t_s - a.t_s for a, b in zip(p.keyframes, p.keyframes[1:], strict=False))
        else:
            continue
        worst = max(worst, length / (SPEED_OF_LIGHT * tau))
    return worst


def _time_assumptions(ts: TimeState) -> list[LocalizedText]:
    return [
        L(f"Magnetoquasistatic model at t = {ts.t_s:.6g} s: prescribed currents I(t) in fixed "
          "geometry; B follows I(t) instantaneously (no retardation, no radiation); the "
          "displacement current is neglected.",
          f"Magnetokvázisztatikus modell t = {ts.t_s:.6g} s időpontban: előírt I(t) áramok "
          "rögzített geometriában; B késleltetés nélkül követi I(t)-t (nincs késleltetés, "
          "sugárzás); az eltolási áramot elhanyagoljuk."),
        L("dB/dt = Σ dI_j/dt · B_j per unit current, with dI/dt from the profile analytically. "
          "E_ind = −∂A/∂t is the induced, nonconservative part of the electric field in the "
          "Coulomb gauge; it is not the complete electric field (no charges, no scalar "
          "potential of a time-dependent system).",
          "dB/dt = Σ dI_j/dt · B_j egységnyi áramra, dI/dt a profilból analitikusan. "
          "E_ind = −∂A/∂t az elektromos tér indukált, nem konzervatív része Coulomb-mértékben; "
          "nem a teljes elektromos tér (nincsenek töltések, nincs időfüggő skalárpotenciál)."),
        L("Induced fields do not act back: no induced currents, no eddy currents, the source "
          "currents are prescribed.",
          "Az indukált terek nem hatnak vissza: nincsenek indukált áramok, örvényáramok, a "
          "forrásáramok előírtak."),
    ]


def _time_warnings(ts: TimeState, ratio: float, request: SolveRequest) -> list[LocalizedText]:
    out: list[LocalizedText] = []
    wants = set(request.all_quantities())
    if ts.unsupported_ids and "E_ind" in wants:
        ids = ", ".join(ts.unsupported_ids)
        out.append(L(
            f"E_ind is not evaluated: the current of {ids} changes at this time, and no vector "
            "potential is implemented for that source (infinite wire or ideal toroid). A partial "
            "induced field is not shown.",
            f"E_ind nincs kiértékelve: {ids} árama ebben az időpontban változik, és ehhez a "
            "forráshoz (végtelen vezető vagy ideális toroid) nincs vektorpotenciál megvalósítva. "
            "Részleges indukált teret nem mutatunk."))
    corner = [st for st in ts.sources if not st.rate.unique]
    if corner and wants & {"dB_dt", "E_ind"}:
        parts = "; ".join(f"{st.object_id}: {st.rate.left:.6g} A/s before, {st.rate.right:.6g} "
                          "A/s after" for st in corner)
        parts_hu = "; ".join(f"{st.object_id}: előtte {st.rate.left:.6g} A/s, utána "
                             f"{st.rate.right:.6g} A/s" for st in corner)
        out.append(L(
            f"At t = {ts.t_s:.6g} s dI/dt jumps ({parts}); dB/dt and E_ind are shown with the "
            "right-hand (after) derivative and are not uniquely defined at this instant.",
            f"t = {ts.t_s:.6g} s-nál dI/dt ugrik ({parts_hu}); dB/dt és E_ind a jobb oldali "
            "(utána) deriválttal látható, ebben a pillanatban nem egyértelmű."))
    if ratio > QUASISTATIC_WARN:
        out.append(L(
            f"The quasistatic approximation is doubtful here: region size / (c × time scale) = "
            f"{ratio:.2g} (retardation across the region is neglected).",
            f"A kvázisztatikus közelítés itt kérdéses: tartományméret / (c × időskála) = "
            f"{ratio:.2g} (a tartományon belüli késleltetést elhanyagoljuk)."))
    return out


def _status_warnings(counts: NDArray[np.int64], unconverged: int, imprecise: int = 0,
                     worst: float = 0.0) -> list[LocalizedText]:
    out: list[LocalizedText] = []
    if imprecise:
        out.append(L(
            f"{imprecise} sample point(s) lie so close to an ideal current filament that float64 "
            f"arithmetic limits the relative accuracy of B and H there (worst bound {worst:.1e}, "
            f"reported above {PRECISION_WARN:.0e}). The values are the near-filament field itself, "
            "not capped, accurate to that relative bound.",
            f"{imprecise} mintavételi pont olyan közel van egy ideális áramszálhoz, hogy a float64 "
            "aritmetika korlátozza ott B és H relatív pontosságát (legrosszabb korlát "
            f"{worst:.1e}, {PRECISION_WARN:.0e} felett jelezve). Az értékek maguk a szál közeli "
            "tér értékei, nem levágva, e relatív korláton belül pontosak."))
    if counts[ST_SINGULAR]:
        out.append(L(
            f"{counts[ST_SINGULAR]} sample point(s) lie on an ideal current filament, where B "
            "and H are singular; they are reported as undefined.",
            f"{counts[ST_SINGULAR]} mintavételi pont ideális áramszálra esik, ahol B és H "
            "szinguláris; ezek értéke nem értelmezett."))
    if counts[ST_SHEET]:
        out.append(L(
            f"{counts[ST_SHEET]} sample point(s) lie on a magnet's bound current sheet, where the "
            "tangential B has different one-sided limits; no single value is reported there.",
            f"{counts[ST_SHEET]} mintavételi pont egy mágnes kötött áramrétegére esik, ahol a "
            "tangenciális B egyoldali határértékei eltérnek; ott nincs egyetlen érték."))
    if counts[ST_END_FACE]:
        out.append(L(
            f"{counts[ST_END_FACE]} sample point(s) lie on a magnet's end face: B is continuous "
            "there, but H jumps (its normal component by M), so H is not reported there.",
            f"{counts[ST_END_FACE]} mintavételi pont egy mágnes véglapjára esik: B ott folytonos, "
            "de H ugrik (normális komponense M-mel), ezért H ott nincs megadva."))
    if counts[ST_CORE_BOUNDARY]:
        out.append(L(
            f"{counts[ST_CORE_BOUNDARY]} sample point(s) lie on the ideal toroid's core surface, "
            "where the ideal model has only one-sided values.",
            f"{counts[ST_CORE_BOUNDARY]} mintavételi pont az ideális toroid magjának felületére "
            "esik, ahol az ideális modellnek csak egyoldali értékei vannak."))
    if unconverged:
        out.append(L(
            f"The surface-current quadrature of a magnet did not reach its tolerance at "
            f"{unconverged} point(s); their values are less accurate than stated.",
            f"Egy mágnes felületi áram szerinti kvadratúrája {unconverged} pontban nem érte el a "
            "tűrést; ezek értéke a megadottnál pontatlanabb."))
    return out


def _model_assumptions(cs: CurrentSources) -> list[LocalizedText]:
    kinds = {o.kind for o in cs.objects}
    out: list[LocalizedText] = []
    if "solenoid" in kinds:
        out.append(L(
            "Solenoid: discrete coaxial circular turns; the helical connections between turns "
            "and the lead wires are not modelled. The field is the sum of the turns' fields.",
            "Szolenoid: diszkrét, koaxiális kör alakú menetek; a menetek közötti csavarvonalas "
            "kapcsolatot és a hozzávezetéseket nem modellezzük. A tér a menetek terének összege."))
    if "toroid_finite" in kinds:
        out.append(L(
            "Finite-turn toroid: N separate circular turns in meridional planes, in vacuum (no "
            "core); leakage and the field outside the winding are included.",
            "Véges menetszámú toroid: N különálló kör alakú menet meridiánsíkokban, vákuumban "
            "(mag nélkül); a szórt tér és a tekercsen kívüli tér is szerepel."))
    if "toroid_ideal" in kinds:
        out.append(L(
            "Ideal toroid: continuous winding, homogeneous linear isotropic core (B = μ₀μᵣH), "
            "perfect confinement: B = H = 0 outside the core. Leakage, fringing and the discrete "
            "turns are neglected (idealization).",
            "Ideális toroid: folytonos tekercselés, homogén, lineáris, izotrop mag (B = μ₀μᵣH), "
            "tökéletes térbezárás: a magon kívül B = H = 0. A szórt teret, a peremhatásokat és a "
            "diszkrét meneteket elhanyagolja (idealizáció)."))
    if cs.magnets:
        out.append(L(
            "Permanent magnet: uniform prescribed axial magnetization M (no hysteresis, "
            "demagnetization curve or temperature dependence). B comes from the bound surface "
            "current K = M × n on the side wall, computed by adaptive quadrature; "
            "H = B/μ₀ − M inside, B/μ₀ outside.",
            "Állandó mágnes: egyenletes, előírt tengelyirányú M mágnesezettség (nincs hiszterézis, "
            "lemágnesezési görbe vagy hőmérsékletfüggés). B a palást K = M × n kötött felületi "
            "áramából, adaptív kvadratúrával számítva; belül H = B/μ₀ − M, kívül B/μ₀."))
    return out


def _classification_note(kind: str) -> LocalizedText:
    if kind == "idealized_model":
        return L("Idealized analytical model (ideal continuous-winding toroid): exact within its "
                 "idealization, not the field of a real winding.",
                 "Idealizált analitikus modell (ideális, folytonos tekercselésű toroid): "
                 "idealizációján belül egzakt, de nem egy valódi tekercs tere.")
    if kind == "numerical_approximation":
        return L("Filament fields are exact closed forms; the magnet's field is the numerical "
                 "integral of exact loop fields over its bound current sheet (adaptive "
                 "Gauss–Kronrod, relative tolerance 1e-9), evaluated in 64-bit floating point.",
                 "Az áramszálak tere egzakt zárt alak; a mágnes tere egzakt körvezető-terek "
                 "numerikus integrálja a kötött áramrétegen (adaptív Gauss–Kronrod, relatív tűrés "
                 "1e-9), 64 bites lebegőpontos számítással.")
    return L("Exact analytical solution (closed-form Biot–Savart solutions: straight wire, and "
             "circular loop with complete elliptic integrals) of an idealized filament model, "
             "evaluated in 64-bit floating point and transported as 32-bit.",
             "Idealizált áramszál-modell egzakt analitikus megoldása (a Biot–Savart-törvény zárt "
             "alakú megoldásai: egyenes vezető, valamint körvezető teljes elliptikus "
             "integrálokkal), 64 bites lebegőpontos számítással, 32 bites átvitellel.")


def _seed_sources(cs: CurrentSources) -> list[tuple[WireSource | LoopSource, float, str]]:
    """What seeds field lines, with its strength (|I|, N|I| or |M|L, ampere-turns) and owner.
    Wires seed on rays; everything else on a "seed disk" that every field line of the source
    threads once (Phase 3A loop seeding, reused): a loop's own disk; the midplane disk of a
    solenoid or magnet; a toroid's cross-section half-way between two turns (finite) or at its
    reference angle (ideal core)."""
    out: list[tuple[WireSource | LoopSource, float, str]] = []
    for w in cs.wires:
        out.append((w, abs(w.current_A), w.object_id))
    first_turn: dict[str, LoopSource] = {}
    for lp in cs.loops:
        if lp.kind == "circular_loop":
            out.append((lp, abs(lp.current_A), lp.object_id))
        else:
            first_turn.setdefault(lp.object_id, lp)
    for obj in cs.objects:
        t0 = first_turn.get(obj.object_id)
        strength = abs(obj.current_A or 0.0) * obj.turns
        if obj.kind == "solenoid" and t0 is not None and obj.center_m is not None:
            out.append((LoopSource(obj.object_id, obj.current_A or 0.0, obj.center_m, t0.normal,
                                   t0.radius_m, t0.u), strength, obj.object_id))
        elif obj.kind == "toroid_finite" and t0 is not None and obj.center_m is not None:
            half = math.pi / obj.turns
            e_rho = math.cos(half) * t0.u + math.sin(half) * t0.normal
            e_phi = -math.sin(half) * t0.u + math.cos(half) * t0.normal
            r_maj = obj.params["major_radius_m"]
            out.append((LoopSource(obj.object_id, obj.current_A or 0.0,
                                   obj.center_m + r_maj * e_rho, e_phi, t0.radius_m, e_rho),
                        strength, obj.object_id))
    for t in cs.ideal_toroids:
        e_phi = np.cross(t.axis, t.u)
        out.append((LoopSource(t.object_id, t.current_A, t.center_m + t.major_radius_m * t.u,
                               e_phi, t.core_radius_m, t.u), abs(t.current_A) * t.turns,
                    t.object_id))
    for mg in cs.magnets:
        out.append((LoopSource(mg.object_id, 1.0, mg.center_m, mg.axis, mg.radius_m, mg.u),
                    abs(mg.magnetization_A_per_m) * mg.length_m, mg.object_id))
    return out


def _perp(d: Arr) -> Arr:
    """A unit vector perpendicular to d."""
    a = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    v = np.cross(d, a)
    return v / np.linalg.norm(v)


class FilamentMagnetostaticSolver:
    id = "analytical.magnetostatics.filaments"
    version = "1.1.0"
    kind: SolverKind = "analytical"
    field_kinds: tuple[str, ...] = ("magnetic",)
    name = L("Analytical magnetostatics: current filaments, coils, toroids and permanent magnets",
             "Analitikus magnetosztatika: áramszálak, tekercsek, toroidok és állandó mágnesek")

    def supports(self, scene: Scene, request: SolveRequest) -> Support:
        reasons: list[LocalizedText] = []
        if request.field_kind != "magnetic":
            reasons.append(L("This solver computes B and H only.",
                             "Ez a megoldó csak B-t és H-t számít."))
        if scene.dimensionality != "3d":
            reasons.append(L(
                f"Dimensionality '{scene.dimensionality}' is not implemented; only the full 3D "
                "model is available.",
                f"A(z) '{scene.dimensionality}' dimenziójú modell nincs megvalósítva; csak a "
                "teljes 3D modell érhető el."))
        if scene.material(scene.domain.background_material_id).model is not MaterialModel.VACUUM:
            reasons.append(L("The background medium must be vacuum for this analytical model.",
                             "Ennél az analitikus modellnél a háttérközegnek vákuumnak kell "
                             "lennie."))
        if scene.boundaries:
            reasons.append(L("Boundary conditions require a boundary-value solver, which is not "
                             "available yet.",
                             "A peremfeltételek peremérték-megoldót igényelnek, amely még nem "
                             "érhető el."))
        reasons.extend(current_sources(scene).problems)
        for o in scene.objects:
            if not o.enabled or o.role in (Role.GEOMETRY_ONLY, Role.CURRENT_SOURCE,
                                           Role.CHARGE_SOURCE, Role.MAGNETIC_MATERIAL):
                continue
            label = o.name or o.id
            reasons.append(L(
                f"Object '{label}' has role '{o.role.value}', which no available solver supports "
                "yet (magnetic materials, conductors and dielectrics are later milestones). It is "
                "not approximated by a simpler model.",
                f"A(z) '{label}' objektum szerepe '{o.role.value}', amelyet még egyetlen elérhető "
                "megoldó sem támogat (a mágneses anyagok, vezetők és dielektrikumok későbbi "
                "mérföldkövek). Egyszerűbb modellel nem helyettesítjük."))
        return Support(supported=not reasons, reasons=reasons)

    # ------------------------------------------------------------------------- field lines

    def _seeds(self, scene: Scene, request: SolveRequest, cs: CurrentSources, guard: float,
               level_count: int) -> tuple[list[Arr], list[list[str]], list[str], bool | None]:
        """Seed points per density level, the source each seed belongs to, unseeded sources,
        and (planar seeding) whether every line stays in the plane exactly."""
        req = request.field_lines
        assert req is not None
        ref = next(s for s in request.samplings if s.id == req.sampling_id)
        assert ref.kind != "points"
        dmin, dmax = np.asarray(scene.domain.min_m, float), np.asarray(scene.domain.max_m, float)
        diag = scene.domain.diagonal_m
        seed_list = _seed_sources(cs)
        i_max = max((x[1] for x in seed_list), default=0.0)
        r_far = 0.5 * diag
        r_near = max(2.5 * guard, 1e-3 * diag)

        def inside(p: Arr) -> bool:
            return bool(np.all(p >= dmin) and np.all(p <= dmax))

        def wire_radii(n: int) -> Arr:
            # Geometric spacing: for an isolated wire B ∝ 1/r, so equal ratios between radii
            # enclose equal flux per unit length (a physically meaningful line density).
            return r_near * (r_far / r_near) ** ((np.arange(n) + 0.5) / n)

        def loop_radii(n: int, a: float) -> Arr:
            lim = max(a - 2.5 * guard, 0.05 * a)
            return lim * (np.arange(n) + 0.5) / n

        planar = req.seeding == "planar"
        unseeded: list[str] = []
        in_plane_all: bool | None = True if planar else None
        per_level: list[list[tuple[Arr, str]]] = [[] for _ in range(level_count)]
        base = req.base_lines
        if planar:
            assert isinstance(ref, PlaneGridSampling)
            u, v = np.asarray(ref.u_dir, float), np.asarray(ref.v_dir, float)
            nrm = np.cross(u, v)
            c0 = np.asarray(ref.center_m, float)
            tol = IN_PLANE_FACTOR * diag
        for src, cur, owner in seed_list:
            if cur == 0.0:
                continue
            for level in range(level_count):
                n = max(1, round(base * 2**level * cur / i_max))
                pts: list[Arr] = []
                if isinstance(src, WireSource):
                    if planar:
                        dn = float(src.direction @ nrm)
                        if abs(dn) <= 1e-9:
                            if level == 0:
                                unseeded.append(owner)
                                in_plane_all = False
                            continue
                        if level == 0 and abs(abs(dn) - 1.0) > 1e-9:
                            in_plane_all = False
                        x = src.point_m + float((c0 - src.point_m) @ nrm) / dn * src.direction
                        e = u - (u @ src.direction) * src.direction
                        e /= np.linalg.norm(e)
                        pts = [x + r * e for r in wire_radii(n)]
                    else:
                        # Three planes perpendicular to the wire, spread along its in-domain part.
                        ts = np.linspace(-1.0, 1.0, 3) * 0.5 * diag
                        e1 = _perp(src.direction)
                        centre = src.point_m + float(
                            (0.5 * (dmin + dmax) - src.point_m) @ src.direction) * src.direction
                        nn = max(1, round(n / 3 + 0.49))
                        for j, t in enumerate(ts):
                            rot = np.cos(j * 2.1) * e1 + np.sin(j * 2.1) * np.cross(src.direction,
                                                                                     e1)
                            pts += [centre + t * src.direction + r * rot for r in wire_radii(nn)]
                else:
                    a = src.radius_m
                    if planar:
                        nz = src.normal @ nrm
                        dist_c = float((src.center_m - c0) @ nrm)
                        if abs(nz) <= 1e-9:  # the plane is parallel to the loop axis
                            if level == 0 and abs(dist_c) > tol:
                                in_plane_all = False
                            # chord of the disk on the plane: line through the projection of the
                            # centre along the in-plane direction perpendicular to the normal
                            dirc = np.cross(src.normal, nrm)
                            dirc /= np.linalg.norm(dirc)
                            if abs(dist_c) >= a:
                                if level == 0:
                                    unseeded.append(owner)
                                continue
                            half = np.sqrt(a * a - dist_c * dist_c)
                            foot = src.center_m - dist_c * nrm
                            rr = loop_radii(n, half)
                            pts = [foot + s * r * dirc for r in rr for s in (1.0, -1.0)]
                        else:
                            if level == 0:
                                in_plane_all = False
                            if abs(abs(nz) - 1.0) <= 1e-9:  # loop parallel to the plane
                                if level == 0:
                                    unseeded.append(owner)
                                continue
                            # line where the slice cuts the loop plane, intersected with the disk
                            dirc = np.cross(src.normal, nrm)
                            dirc /= np.linalg.norm(dirc)
                            w_in = np.cross(src.normal, dirc)  # in loop plane, ⊥ dirc
                            denom = float(w_in @ nrm)
                            s0 = float((c0 - src.center_m) @ nrm) / denom
                            foot = src.center_m + s0 * w_in
                            if abs(s0) >= a:
                                if level == 0:
                                    unseeded.append(owner)
                                continue
                            half = np.sqrt(a * a - s0 * s0)
                            pts = [foot + s * r * dirc for r in loop_radii(n, half)
                                   for s in (1.0, -1.0)]
                    else:
                        e1 = src.u
                        e2 = np.cross(src.normal, e1)
                        nn = max(1, round(n / 2 + 0.49))
                        for phi in np.arange(4) * np.pi / 2 + 0.3:
                            dirr = np.cos(phi) * e1 + np.sin(phi) * e2
                            pts += [src.center_m + r * dirr for r in loop_radii(nn, a)]
                for p in pts:
                    if inside(p):
                        per_level[level].append((p, owner))
        seeds = [np.array([p for p, _ in lv]).reshape(-1, 3) for lv in per_level]
        owners = [[o for _, o in lv] for lv in per_level]
        return seeds, owners, unseeded, in_plane_all

    def _field_lines(self, scene: Scene, request: SolveRequest, cs: CurrentSources, r_min: float,
                     arrays: dict[str, Arr], entries: list[ArrayEntry]) -> FieldLineSet:
        req = request.field_lines
        assert req is not None
        ref = next(s for s in request.samplings if s.id == req.sampling_id)
        assert ref.kind != "points"
        diag = scene.domain.diagonal_m
        guard = req.guard_cells * ref.cell_m
        cfg = _FL_SETTINGS[request.quality]
        i_sum = cs.free_current_scale_A + sum(abs(mg.magnetization_A_per_m) * mg.length_m
                                              for mg in cs.magnets)
        settings = ml.Settings(
            atol=cfg["atol"] * diag, h_max=cfg["h_max"] * diag, h_min=1e-12 * diag,
            max_length=6.0 * diag, max_steps=int(cfg["max_steps"]), guard_radius=guard,
            stagnation_B=1e-9 * MU0 * i_sum / diag)
        dmin, dmax = np.asarray(scene.domain.min_m, float), np.asarray(scene.domain.max_m, float)
        seeds, owners, unseeded, stay = self._seeds(scene, request, cs, guard, req.levels)
        total = sum(len(s) for s in seeds)
        if total > _MAX_LINES:  # bound the work for scenes with many sources
            keep = _MAX_LINES / total
            for lv in range(len(seeds)):
                idx = np.unique(np.linspace(0, len(seeds[lv]) - 1,
                                            max(1, int(len(seeds[lv]) * keep))).astype(int)) \
                    if len(seeds[lv]) else np.empty(0, int)
                seeds[lv] = seeds[lv][idx]
                owners[lv] = [owners[lv][i] for i in idx]

        fils = request.passive

        def field_fn(p: Arr) -> Arr:
            out = evaluate(p, cs, r_min, MAGNET_RTOL["lines"])
            if fils:  # Phase 4C: lines of the total field, induced currents included
                out = out + passive_fields(p, fils)[0]
            return out

        def dist_fn(p: Arr) -> Arr:
            out: Arr = distance_to_sources(p, cs)
            if fils:
                out = np.minimum(out, passive_distance(p, fils))
            return out

        def region_fn(p: Arr) -> NDArray[np.int64]:
            return region_code(p, cs)

        def scale_fn(p: Arr) -> Arr:
            # Closure length scale and step limit also see magnet sheets and the ideal core
            # surface (which lines may cross); singular capture stays filaments only.
            out: Arr = np.minimum(distance_to_sources(p, cs), distance_to_boundaries(p, cs))
            return out

        infos: list[FieldLineInfo] = []
        chunks: list[Arr] = []
        cursor = 0
        # Seeds closer than this to an already drawn line are skipped (display choice).
        dedupe = 2.0 * ml.CLOSURE_ATOL_FACTOR * settings.atol + 0.25 * guard
        for level, (sd, own) in enumerate(zip(seeds, owners, strict=True)):
            if len(sd) == 0:
                continue
            lines = ml.trace_lines(field_fn, dist_fn, sd, dmin, dmax, settings, scale_fn=scale_fn,
                                   region_fn=region_fn if (cs.magnets or cs.ideal_toroids)
                                   else None)
            kept: list[Arr] = []
            for ln in lines:
                seed = sd[ln.seed_index][None, :]
                # A seed lying on a line already drawn would only draw that line again.
                if any(float(ml.polyline_distance(seed, k)[0]) <= dedupe for k in kept):
                    continue
                kept.append(ln.points)
                infos.append(FieldLineInfo(
                    start=cursor, count=len(ln.points), level=level,
                    start_reason=ln.start_reason,
                    end_reason=ln.end_reason,
                    start_object_id=own[ln.seed_index], steps=ln.steps,
                    closure_gap_m=ln.closure_gap))
                chunks.append(ln.points)
                cursor += len(ln.points)
        points = np.concatenate(chunks) if chunks else np.empty((0, 3))
        name = "field_lines.points"
        arrays[name] = points
        entries.append(ArrayEntry(name=name, sampling_id="field_lines", quantity="position",
                                  symbol="r", unit="m", components=3, kind="geometry",
                                  stats=_stats(points, True)))
        counts: dict[str, int] = {}
        for info in infos:
            if info.start_reason == "closed_loop":
                counts["closed_loop"] = counts.get("closed_loop", 0) + 1
                continue
            for reason in (info.start_reason, info.end_reason):
                counts[reason] = counts.get(reason, 0) + 1
        return FieldLineSet(
            array=name, field="B", seeding=req.seeding, levels=req.levels, guard_radius_m=guard,
            lines_stay_in_plane=stay, unseeded_object_ids=unseeded, lines=infos,
            end_reason_counts=counts, field_classification="exact_analytical",
            method=MethodInfo(
                kind="numerical_integration",
                name=L("Adaptive Dormand–Prince RK5(4) integration of dr/ds = B/|B| with "
                       "closed-loop detection",
                       "A dr/ds = B/|B| egyenlet adaptív Dormand–Prince RK5(4) integrálása "
                       "zárt hurok felismeréssel"),
                description=L(
                    "Magnetic field lines are numerical integral curves of the exact analytical "
                    "B field. A line is reported as closed only when the integrator returns to "
                    "its start point within the stated tolerance, with the same direction, "
                    "after going around a current; it is never joined to its start "
                    "artificially. Lines that do not close are traced in both directions from "
                    "their seed.",
                    "A mágneses erővonalak az egzakt analitikus B mező numerikusan integrált "
                    "görbéi. Egy vonal csak akkor számít zártnak, ha az integrátor a megadott "
                    "tűréssel, azonos iránnyal, egy áram megkerülése után visszaér a "
                    "kiindulópontjába; a végpontokat sosem kötjük össze mesterségesen. A nem "
                    "záródó vonalakat a kiindulópontból mindkét irányban követjük."),
                parameters={
                    "local_error_tolerance_m": settings.atol, "max_step_m": settings.h_max,
                    "min_step_m": settings.h_min, "max_length_m": settings.max_length,
                    "max_steps": settings.max_steps, "guard_radius_m": guard,
                    "stagnation_threshold_T": settings.stagnation_B,
                    "closure_tangent_cos": ml.CLOSURE_TANGENT_COS,
                    "closure_gap_error_factor": ml.CLOSURE_ERR_FACTOR,
                    "closure_gap_atol_factor": ml.CLOSURE_ATOL_FACTOR,
                    "duplicate_seed_distance_m": dedupe,
                },
                limitations=[
                    L("A line that reaches the edge of the region of interest is truncated "
                      "there; the physical line continues (B lines have no ends).",
                      "A vizsgált tartomány szélét elérő vonal ott le van vágva; a fizikai "
                      "erővonal folytatódik (a B-vonalaknak nincs végpontjuk)."),
                    L("Lines ending at a current filament, at a zero of B, at the maximum length "
                      "or by integration failure are numerical outcomes, drawn dashed.",
                      "Az áramszálnál, B nullhelyén, a maximális hossznál vagy integrálási hiba "
                      "miatt véget érő vonalak numerikus eredmények; szaggatottan jelennek meg."),
                    L("Line density is a display choice. Around a single wire the seed radii "
                      "are spaced geometrically, so neighbouring lines enclose equal flux per "
                      "unit length; with several sources this holds only approximately.",
                      "A vonalsűrűség megjelenítési választás. Egyetlen vezető körül az "
                      "indítási sugarak mértani sorozatot alkotnak, így a szomszédos vonalak "
                      "egységnyi hosszra azonos fluxust zárnak közre; több forrásnál ez csak "
                      "közelítőleg teljesül."),
                    L("Where B lines are not closed curves (general 3D configurations of "
                      "several sources), a line passing within the closure tolerance of its "
                      "start cannot be told apart from a closed one numerically.",
                      "Ahol a B-vonalak nem zárt görbék (több forrás általános 3D "
                      "elrendezése), a kiindulópontját a záródási tűrésen belül megközelítő "
                      "vonal numerikusan nem különböztethető meg a zárttól."),
                ],
            ),
        )

    # ------------------------------------------------------------------------------ solve

    def solve(self, scene: Scene, request: SolveRequest,
              progress: ProgressCallback | None = None,
              cancel: CancelCheck | None = None) -> SimulationResult:
        t0 = time.perf_counter()
        cs0 = current_sources(scene)
        # Phase 4A: every current at the simulation time (= the stored current at t = 0 and for
        # constant profiles), and the rates dI/dt for dB/dt and E_ind.
        ts = time_state(scene, cs0, request.time_s)
        cs = at_time(cs0, ts)
        cs_rate = rates(cs0, ts)
        fils = request.passive
        # Phase 4C: a moving passive circuit carrying current has ∂A/∂t from its motion too,
        # which is not evaluated: its ∂B/∂t and E_ind contribution is then unavailable.
        passive_rate_ok = not any(f.moving and f.current_A != 0.0 for f in fils)
        e_ind_ok = not ts.unsupported_ids and passive_rate_ok
        r_min = COINCIDENCE_FACTOR * scene.domain.diagonal_m
        total = sum(int(np.prod(s.shape)) for s in request.samplings)
        share = 1.0 if request.field_lines is None else 0.5

        def check_cancel() -> None:
            if cancel is not None and cancel():
                raise SolverCancelledError()

        arrays: dict[str, Arr] = {}
        entries: list[ArrayEntry] = []
        counts = np.zeros(5, np.int64)
        unconverged = 0
        imprecise = 0
        worst_precision = 0.0
        done = 0
        contrib_ok = cs.count <= MAX_CONTRIBUTION_SOURCES
        tol = sheet_tolerance(cs, r_min)
        for s in request.samplings:
            pts = s.points()
            b = np.empty_like(pts)
            h = np.empty_like(pts)
            status = np.empty(pts.shape[0], np.int64)
            for start in range(0, pts.shape[0], _CHUNK):
                check_cancel()
                sl = slice(start, start + _CHUNK)
                ev = evaluate_bh(pts[sl], cs, r_min)
                b[sl], h[sl], status[sl] = ev.b, ev.h, ev.status
                unconverged += ev.unconverged
                rough = ev.precision > PRECISION_WARN
                imprecise += int(np.count_nonzero(rough))
                if rough.any():
                    worst_precision = max(worst_precision, float(ev.precision.max()))
                done += pts[sl].shape[0]
                if progress is not None:
                    progress(share * done / max(total, 1), s.id)
            b_presc = b.copy()
            b_pass = None
            if fils:
                b_pass, psing, _ = passive_fields(pts, fils)
                b = b + b_pass
                h = h + b_pass / MU0
                status[psing] = ST_SINGULAR
            counts += np.bincount(status, minlength=5)
            wants = set(quantities_for(request, s))
            db_dt = e_ind = None
            if "dB_dt" in wants:
                # Linear in each current for fixed geometry: dB/dt = sum_j dI_j/dt B_j,unit,
                # from the analytical dI/dt (static sources removed).
                db_dt = np.empty_like(pts)
                for start in range(0, pts.shape[0], _CHUNK):
                    sl = slice(start, start + _CHUNK)
                    db_dt[sl] = evaluate_bh(pts[sl], cs_rate, r_min).b
                if fils:
                    db_dt = db_dt + passive_fields(pts, fils, "B", rate=True)[0]
                    if not passive_rate_ok:
                        db_dt[:] = np.nan
                db_dt[status == ST_SINGULAR] = np.nan
            if "E_ind" in wants:
                e_ind = np.full_like(pts, np.nan)
                if e_ind_ok:
                    # E_ind = -dA/dt = -sum_j dI_j/dt A_j,unit (Coulomb gauge, closed loops).
                    for start in range(0, pts.shape[0], _CHUNK):
                        sl = slice(start, start + _CHUNK)
                        e_ind[sl] = -loops_vector_potential(cs_rate.loops, pts[sl])[0]
                    if fils:  # −dI_j/dt A_j of the passive circuits (solved currents)
                        e_ind = e_ind - passive_fields(pts, fils, "A", rate=True)[0]
                    e_ind[status == ST_SINGULAR] = np.nan
            # Exact zeros where the field is defined: every source is divergence-free there
            # (Biot–Savart fields of filaments and sheets; the ideal core field is azimuthal and
            # depends on rho only). div H = -div M = 0 inside a uniform magnet.
            div_b = np.where(np.all(np.isfinite(b), axis=1), 0.0, np.nan)
            div_h = np.where(np.all(np.isfinite(h), axis=1), 0.0, np.nan)
            data_by_q = {"B": b, "H": h, "div_B": div_b, "div_H": div_h}
            if db_dt is not None:
                data_by_q["dB_dt"] = db_dt
            if e_ind is not None:
                data_by_q["E_ind"] = e_ind
            data_by_q["B_prescribed"] = b_presc
            data_by_q["B_passive"] = b_pass if b_pass is not None else np.zeros_like(b)
            for qty in quantities_for(request, s):
                info = QUANTITIES[qty]
                name = f"{s.id}.{qty}"
                shape = (*s.shape, 3) if info.rank == 1 else s.shape
                arrays[name] = data_by_q[qty].reshape(shape)
                entries.append(ArrayEntry(
                    name=name, sampling_id=s.id, quantity=qty, symbol=info.symbol,
                    unit=info.unit, components=3 if info.rank == 1 else 1,
                    stats=_stats(data_by_q[qty], info.rank == 1)))
            if s.id in request.source_contributions and contrib_ok:
                fields = source_fields(pts, cs, r_min)
                for oid, bi in zip(cs.ids, fields, strict=True):
                    hi = source_h(pts, cs, oid, bi, tol)
                    for qty, data in (("B", bi), ("H", hi)):
                        info = QUANTITIES[qty]
                        name = f"{s.id}.{qty}@{oid}"
                        arrays[name] = data.reshape(*s.shape, 3)
                        entries.append(ArrayEntry(
                            name=name, sampling_id=s.id, quantity=qty, symbol=f"{qty}ᵢ",
                            unit=info.unit, components=3, stats=_stats(data, True)))

        field_lines = None
        if request.field_lines is not None:
            check_cancel()
            if progress is not None:
                progress(share, "field_lines")
            field_lines = self._field_lines(scene, request, cs, r_min, arrays, entries)
        if progress is not None:
            progress(1.0, "done")

        excluded = [o.id for o in scene.objects
                    if o.enabled and o.role is Role.GEOMETRY_ONLY
                    and not isinstance(o.primitive, GroupPrimitive)]
        assumptions = [
            L("Steady (DC) currents in ideal filaments of zero radius: infinitely long straight "
              "wires and thin circular loops (also the turns of solenoids and finite toroids).",
              "Stacionárius (egyen-) áramok nulla vastagságú ideális áramszálakban: végtelen "
              "hosszú egyenes vezetők és vékony körvezetők (a szolenoidok és véges toroidok "
              "menetei is)."),
            L("Unbounded vacuum: B = μ₀H everywhere; no magnetic materials, conductors or "
              "boundaries." if not (cs.magnets or cs.ideal_toroids) else
              "Vacuum background: B = μ₀H outside the materials listed below; no conductors or "
              "boundaries.",
              "Végtelen kiterjedésű vákuum: mindenütt B = μ₀H; nincsenek mágneses anyagok, "
              "vezetők vagy peremek." if not (cs.magnets or cs.ideal_toroids) else
              "Vákuum háttér: az alább felsorolt anyagokon kívül B = μ₀H; nincsenek vezetők vagy "
              "peremek."),
            L("Magnetostatics: no time dependence, no induction. Point charges at rest produce "
              "no magnetic field; their electric field is solved separately.",
              "Magnetosztatika: nincs időfüggés, nincs indukció. A nyugvó ponttöltések nem "
              "keltenek mágneses mezőt; elektromos mezőjüket külön számítjuk."),
            L("The wires are electrically neutral; the straight wire is infinite (its drawn "
              "length is only a picture).",
              "A vezetők elektromosan semlegesek; az egyenes vezető végtelen hosszú (a "
              "megjelenített hossza csak ábrázolás)."),
            L("The region of interest only bounds sampling and drawing; it is not a physical "
              "boundary.",
              "A vizsgált tartomány csak a mintavételt és a rajzolást határolja; nem fizikai "
              "perem."),
        ]
        assumptions += _model_assumptions(cs)
        quasi_ratio = _quasistatic_ratio(scene)
        if ts.time_dependent:
            assumptions = [a for a in assumptions if not a.en.startswith("Magnetostatics:")]
            assumptions += _time_assumptions(ts)
        warnings: list[LocalizedText] = list(cs.warnings)
        warnings += _time_warnings(ts, quasi_ratio, request)
        if excluded:
            warnings.append(L(
                f"{len(excluded)} inert geometry object(s) are drawn but are not part of the "
                "physical model.",
                f"{len(excluded)} inert geometriai objektum látható, de nem része a fizikai "
                "modellnek."))
        warnings += _status_warnings(counts, unconverged, imprecise, worst_precision)
        if request.source_contributions and not contrib_ok:
            warnings.append(L(
                f"Individual source contributions are returned for at most "
                f"{MAX_CONTRIBUTION_SOURCES} sources; this scene has {cs.count}.",
                f"Az egyes források járulékai legfeljebb {MAX_CONTRIBUTION_SOURCES} forrásig "
                f"érhetők el; ebben a jelenetben {cs.count} van."))
        if field_lines is not None:
            bad = sum(field_lines.end_reason_counts.get(k, 0) for k in
                      ("max_length", "integration_failure", "source_singularity",
                       "stagnation_point"))
            if bad:
                warnings.append(L(
                    f"{bad} magnetic field-line end(s) are numerical outcomes (maximum length, "
                    "integration failure, filament or zero of B), not physical endings.",
                    f"{bad} mágneses erővonalvég numerikus eredmény (maximális hossz, "
                    "integrálási hiba, áramszál vagy B nullhelye), nem fizikai végpont."))
            if field_lines.unseeded_object_ids:
                warnings.append(L(
                    f"{len(field_lines.unseeded_object_ids)} current source(s) start no field "
                    "lines in this cross-section (parallel to it, or not crossing it).",
                    f"{len(field_lines.unseeded_object_ids)} áramforrás nem indít erővonalat "
                    "ebben a metszetben (párhuzamos vele, vagy nem metszi)."))
        kinds = sorted({o.kind for o in cs.objects})
        nonzero = [o for o in cs.objects
                   if (o.current_A or 0.0) != 0.0 or (o.magnetization_A_per_m or 0.0) != 0.0]
        evaluated = ["superposition_magnetic", "div_B_filaments"]
        if not cs.magnets and not cs.ideal_toroids:
            evaluated += ["b_mu0_h", "h_from_b"]
        if "infinite_wire" in kinds:
            evaluated.append("infinite_wire_field")
        if any(lp.kind == "circular_loop" for lp in cs.loops):
            evaluated += ["loop_field_elliptic", "loop_axis_field"]
        if "solenoid" in kinds:
            evaluated += ["loop_field_elliptic", "finite_solenoid_superposition",
                          "solenoid_turn_spacing"]
        if "toroid_finite" in kinds:
            evaluated += ["loop_field_elliptic", "finite_toroid_superposition"]
        if "toroid_ideal" in kinds:
            evaluated += ["ideal_toroid_H", "ideal_toroid_B", "constitutive_b_linear"]
        if cs.magnets:
            evaluated += ["loop_field_elliptic", "magnet_sheet_field", "constitutive_b_general",
                          "h_from_b_m", "bound_currents", "magnetic_moment"]
        evaluated += [f"current_{p}" if p != "piecewise_linear" else "current_piecewise"
                      for p in {st.profile_type for st in ts.sources}]
        if ts.time_dependent and e_ind_ok:
            evaluated += ["vector_potential_coulomb", "e_ind_from_a"]
        classification = ("idealized_model" if cs.ideal_toroids else
                          "numerical_approximation" if cs.magnets else "exact_analytical")
        header = ResultHeader(
            solver_id=self.id, solver_version=self.version, solver_kind=self.kind,
            classification=classification,
            classification_note=_classification_note(classification),
            assumptions=assumptions, warnings=warnings, excluded_object_ids=excluded,
            time_sources=[TimeSourceInfo(
                object_id=st.object_id, kind=st.kind,
                profile_type=st.profile_type,
                current_A=st.current_A, dI_dt_A_per_s=st.rate.right,
                dI_dt_left_A_per_s=st.rate.left, derivative_unique=st.rate.unique,
                induction_supported=st.induction_supported) for st in ts.sources],
            induction=InductionInfo(
                time_s=ts.t_s, time_dependent=ts.time_dependent,
                derivative_unique=ts.derivative_unique, e_ind_available=e_ind_ok,
                unsupported_object_ids=ts.unsupported_ids, quasistatic_ratio=quasi_ratio,
                passive_ids=[f.id for f in fils], passive_rate_available=passive_rate_ok),
            model_context=ModelContext(
                regime="quasi_static" if ts.time_dependent else "magnetostatic",
                dimensionality="3d", medium="vacuum", time_varying=ts.time_dependent,
                profile_types=sorted({st.profile_type for st in ts.sources}),
                e_ind_available=e_ind_ok,
                has_free_current=any((o.current_A or 0.0) != 0.0 for o in cs.objects),
                computes_magnetic_field=True, solver_id=self.id,
                source_count=len(nonzero), current_source_kinds=kinds,
                has_magnetization=bool(cs.magnets), has_linear_core=bool(cs.ideal_toroids),
                evaluated_equation_ids=sorted(set(evaluated))),
            samplings=[s.model_dump(mode="json", exclude={"points_m"}) for s in request.samplings],
            quality=request.quality, compute_time_ms=(time.perf_counter() - t0) * 1e3,
            current_sources=current_source_table(
                cs, [g for g in request.samplings if isinstance(g, PlaneGridSampling)]),
            in_plane_tolerance_m=IN_PLANE_FACTOR * scene.domain.diagonal_m,
            field_lines=field_lines, arrays=entries)
        return SimulationResult(header=header, arrays=arrays)

