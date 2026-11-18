"""Magnetic flux, Faraday's law, Lenz's law and mutual induction (Phase 4A).

Magnetoquasistatic, stationary geometry: prescribed source currents I_j(t), fixed sources, fixed
measurement surfaces. A measurement surface is the flat region bounded by a closed planar path
(circle, rectangle, polygon: the Ampère path geometry), with the positive normal n given by the
right-hand rule from the traversal; reversing the path flips both. Because every source field is
linear in its current, the work is done once per geometry, at 1 A per source:

    Phi_j = ∫_S B_j,unit · n dS        (adaptive surface quadrature of the B solver's field)
    C_j   = ∮_C A_j,unit · dl          (adaptive line quadrature of the vector potential)

and at any time t:

    Phi(t)      = sum_j I_j(t) Phi_j + Phi_static
    dPhi/dt     = sum_j dI_j/dt Phi_j                      (analytical dI/dt)
    EMF         = ∮ E_ind · dl = -sum_j dI_j/dt C_j        (E_ind = -dA/dt)

Faraday's law ∮E_ind·dl = -dPhi/dt is verified by comparing EMF with -dPhi/dt: the two come from
different fields (A vs B), different formulas and different quadratures (Stokes' theorem
C_j = Phi_j is what is being checked). Mutual inductance M_12 = Phi_j (per ampere); the
reciprocal M_21 is the flux of the measurement loop's own 1 A field through the source's turns.

Not evaluated (reported, never replaced by a number): a filament that pierces the surface or
lies in it (B·n singular inside the surface), a boundary through a filament, sources whose
time-varying current has no vector potential (infinite wire, ideal toroid) for the EMF.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, model_validator

from .ampere import (
    AmperePath,
    CirclePath,
    PolygonPath,
    RectanglePath,
    _filament_approaches,
    _Geo,
    _graded,
    enclosed_current,
)
from .i18n import L, LocalizedText
from .numerics.quadrature import adaptive_gk
from .scene.currents import CurrentSources, LoopSource, current_sources
from .scene.models import PositiveFloat, Scene, StrictModel
from .scene.motion import MotionProfile, Translation, VelocityConvention
from .scene.timedep import TimeState, time_state, with_currents
from .segments import segment_field
from .solvers.analytical import magnetostatics as ms

Arr = NDArray[np.float64]

SURFACE_LEVELS = 10  # quadtree refinement levels per patch (cells down to 1/1024 of a patch)
SURFACE_MAX_CELLS = 40_000  # active cells per level (bounds the work)
SURFACE_ABS_FACTOR = 1e-9  # absolute floor: this × ∫|f| (cancellation scale)
LINE_ABS_FACTOR = 1e-9
GL_N = 5
_GL_X, _GL_W = np.polynomial.legendre.leggauss(GL_N)
CIRCLE_SECTORS = 8


class SlidingRodShape(StrictModel):
    """Sliding-rod generator (Phase 4B), in the surface's local frame: two stationary rails
    along +x at y = ±L/2 from x = 0 to x = rail_length, a stationary connecting segment at
    x = 0, and a straight rod joining the rails at x(t) = rod_position + d_x(t). The circuit is
    the rectangle [0, x(t)] × [−L/2, L/2]; only the rod moves (velocity along the rails)."""

    type: Literal["sliding_rod"] = "sliding_rod"
    rail_separation_m: PositiveFloat = 0.1
    rail_length_m: PositiveFloat = 0.3
    rod_position_m: PositiveFloat = 0.05  # x of the rod at the reference time
    rod_motion: Translation = Field(default_factory=lambda: _default_rod_motion())

    @model_validator(mode="after")
    def _along_rails(self) -> SlidingRodShape:
        m = self.rod_motion
        vecs: list[tuple[float, float, float]] = []
        for name in ("velocity_m_per_s", "acceleration_m_per_s2", "axis"):
            if hasattr(m, name):
                vecs.append(getattr(m, name))
        if any(abs(v[1]) > 0 or abs(v[2]) > 0 for v in vecs):
            raise ValueError("sliding rod: the rod moves along the rails (local x) only; the y and "
                             "z components of its motion must be zero")
        if self.rod_position_m > self.rail_length_m:
            raise ValueError("sliding rod: the rod must start on the rails")
        return self


def _default_rod_motion() -> Translation:
    from .scene.motion import ConstantVelocity
    return ConstantVelocity(velocity_m_per_s=(0.5, 0.0, 0.0))


FluxShape = Annotated[CirclePath | RectanglePath | PolygonPath | SlidingRodShape,
                      Field(discriminator="type")]


class FluxSurface(AmperePath):
    """A measurement surface: the planar region bounded by the path, oriented by the right-hand
    rule (the same geometry and conventions as an Ampère path). ``rtol`` is the relative
    tolerance of the Faraday comparison.

    Phase 4B (all optional, absent = the Phase 4A stationary surface): ``motion`` moves the
    surface and its boundary rigidly (reference pose = ``center_m`` and the rotation);
    ``turns`` > 1 makes it an explicitly defined N-turn measurement coil of N identical,
    coincident, series-connected turns (flux linkage NΦ); the ``sliding_rod`` shape is the
    rail generator, whose rod moves by its own ``rod_motion``."""

    shape: FluxShape  # type: ignore[assignment]
    motion: MotionProfile | None = Field(default=None, exclude_if=lambda v: v is None)
    turns: int = Field(default=1, ge=1, le=100_000, exclude_if=lambda v: v == 1)

    @model_validator(mode="after")
    def _rod_motion_only(self) -> FluxSurface:
        if isinstance(self.shape, SlidingRodShape) and self.motion is not None:
            raise ValueError("sliding rod: the rails are stationary; move the rod with its "
                             "rod_motion instead of a surface motion")
        return self

    @property
    def moving(self) -> bool:
        return self.motion is not None or isinstance(self.shape, SlidingRodShape)


class InductionRequest(StrictModel):
    surfaces: list[FluxSurface] = Field(min_length=1, max_length=8)
    time_s: Annotated[float, Field(allow_inf_nan=False)] = 0.0
    mutual: bool = True  # also compute the reciprocal mutual inductance M_21
    # Phase 4B: which one-sided velocity (and dI/dt) to use where it jumps. "undefined": the
    # instantaneous motional EMF is reported as not uniquely defined at such an instant.
    velocity_convention: VelocityConvention = Field(default="undefined",
                                                    exclude_if=lambda v: v == "undefined")


class SourceFlux(BaseModel):
    object_id: str
    kind: str
    current_A: float  # I(t), per turn
    dI_dt_A_per_s: float  # right-hand derivative
    unit_flux_Wb_per_A: float  # Phi_j = M_12 (H)
    unit_flux_error: float
    unit_circulation_Wb_per_A: float | None  # C_j = ∮A_unit·dl (None: no vector potential)
    unit_circulation_error: float | None
    flux_Wb: float  # I_j(t) Phi_j
    emf_V: float | None  # -dI_j/dt C_j


class Mutual(BaseModel):
    object_id: str
    available: bool
    M12_H: float | None = None  # flux through the measurement surface per ampere of the source
    M12_error_H: float | None = None
    M21_H: float | None = None  # flux through the source turns per ampere in the measurement loop
    M21_error_H: float | None = None
    reciprocity_difference_H: float | None = None
    reciprocity_relative: float | None = None
    reciprocity_ok: bool | None = None
    reason: LocalizedText | None = None


class Lenz(BaseModel):
    flux_trend: Literal["increasing", "decreasing", "steady"]  # along the positive normal
    emf_sign: Literal[1, 0, -1]
    # E_ind circulates along the path's traversal (EMF > 0) or against it (EMF < 0).
    circulation: Literal["along_path", "against_path", "none"]


SurfaceStatus = Literal["verified", "line_not_converged", "surface_not_converged", "invalid",
                        "singular", "unsupported", "failed", "derivative_not_converged",
                        "motion_undefined"]


class MotionState(BaseModel):
    """Instantaneous pose and velocities of a moving measurement conductor (Phase 4B)."""

    kind: Literal["rigid", "sliding_rod"]
    center_m: list[float]
    rotation: list[list[float]]  # R(t): columns are the local axes in world coordinates
    side: Literal["left", "right"] | None  # one-sided velocity used; None: undefined
    unique: bool  # the velocity is continuous at t
    velocity_m_per_s: list[float] | None  # V(t) used (None where undefined)
    angular_velocity_rad_per_s: list[float] | None
    velocity_left_m_per_s: list[float]
    velocity_right_m_per_s: list[float]
    angular_velocity_left_rad_per_s: list[float]
    angular_velocity_right_rad_per_s: list[float]
    max_speed_m_per_s: float | None = None  # largest |u| on the conductor
    rod_position_m: float | None = None
    rod_velocity_m_per_s: float | None = None  # along the rails (local +x)
    rod_length_m: float | None = None
    rails_m: list[list[list[float]]] = []  # stationary rails and connecting segment
    rod_m: list[list[float]] = []


class MotionalSample(BaseModel):
    """u, B and u × B at a point of the conductor (for display; values from the engine)."""

    point_m: list[float]
    u_m_per_s: list[float]
    B_T: list[float] | None
    u_cross_B_V_per_m: list[float] | None
    moving: bool  # False on stationary segments (rails)


class DerivativeInfo(BaseModel):
    """How dΦ/dt was obtained: analytically (stationary surface: Σ dI_j/dt Φ_j) or by
    Richardson-extrapolated finite differences of the flux values in time (moving surface)."""

    method: Literal["analytical", "central", "forward", "backward"]
    step_s: float | None = None  # smallest step used
    levels: int = 0
    converged: bool = True
    error_V: float | None = None


class UniformReference(BaseModel):
    """Idealized uniform-field reference (an approximation, never the result)."""

    kind: Literal["sliding_rod_BLv", "rotating_coil"]
    B_T: list[float]  # the field the reference assumes everywhere (evaluated at one point)
    point_m: list[float]
    flux_Wb: float | None
    emf_V: float
    note: LocalizedText


class SurfaceResult(BaseModel):
    surface_id: str
    valid: bool
    invalid_reasons: list[LocalizedText] = []
    status: SurfaceStatus
    status_reason: LocalizedText | None = None
    time_s: float
    derivative_unique: bool = True
    normal: list[float] | None = None
    center_m: list[float] | None = None
    area_m2: float | None = None
    perimeter_m: float | None = None
    polyline_m: list[list[float]] = []
    flux_Wb: float | None = None
    flux_error_Wb: float | None = None
    dflux_dt_V: float | None = None  # dPhi/dt in Wb/s = V
    dflux_dt_error_V: float | None = None
    emf_V: float | None = None  # ∮ E_ind · dl
    emf_error_V: float | None = None
    difference_V: float | None = None  # EMF + dPhi/dt (zero by Faraday's law)
    relative_error: float | None = None
    tolerance_V: float | None = None
    surface_converged: bool | None = None
    line_converged: bool | None = None
    surface_cells: int | None = None
    line_subintervals: int | None = None
    min_distance_to_filament_m: float | None = None
    lenz: Lenz | None = None
    sources: list[SourceFlux] = []
    static_flux_Wb: float | None = None  # permanent magnets (no dPhi/dt)
    mutual: list[Mutual] = []
    no_change: bool = False  # every dI/dt is zero at t: EMF and dPhi/dt are exactly zero
    # Phase 4B: moving conductors. emf_V above is the transformer EMF ∮E_ind·dl; the motional
    # EMF ∮(u × B)·dl and their sum, the generalized EMF, are separate. turns = N of an
    # N-turn measurement coil (every flux and EMF above is then the N-turn linkage).
    moving: bool = False
    turns: int = 1
    motion: MotionState | None = None
    emf_motional_V: float | None = None
    emf_motional_error_V: float | None = None
    emf_total_V: float | None = None
    emf_total_error_V: float | None = None
    generalized_complete: bool | None = None  # every transformer contribution is evaluated
    motional_samples: list[MotionalSample] = []
    derivative: DerivativeInfo | None = None
    reference: UniformReference | None = None
    warnings: list[LocalizedText] = []


class InductionHeader(BaseModel):
    solver_id: str
    solver_version: str
    time_s: float
    regime: Literal["magnetoquasistatic"] = "magnetoquasistatic"
    gauge: Literal["coulomb"] = "coulomb"
    method: LocalizedText
    surfaces: list[SurfaceResult]


# --------------------------------------------------------------------- surface quadrature


@dataclass
class Patch:
    """Maps the unit square (s, v) to the surface: point(s, v) and the area density jac(s)."""

    point: Callable[[Arr, Arr], Arr]
    jac: Callable[[Arr, Arr], Arr]


def radial_edges(geo: _Geo, cs: CurrentSources | None) -> list[float]:
    """Radii at which a disk is pre-split into rings: around every radius where a filament
    passes close to the surface (local minima of the distance along radial lines in 16
    directions, refined by golden section), graded r* ± d·4^j. The integrand B·n varies there on
    the scale d, so each ring is smooth across its width (the quadtree alone refines both
    directions at once and would need ~log2(R/d) levels)."""
    assert geo.circle_r is not None
    r_ = geo.circle_r
    edges = {0.0, r_}
    if cs is None or (not cs.wires and not cs.loops):
        return sorted(edges)
    rs = np.linspace(0.0, r_, 1025)
    g = (math.sqrt(5.0) - 1.0) / 2.0
    for th in np.linspace(0, 2 * math.pi, 16, endpoint=False):
        e = math.cos(th) * geo.ex + math.sin(th) * geo.ey

        def dist(r: float, e: Arr = e) -> float:
            return float(ms.nearest_filament((geo.c + r * e)[None, :], cs)[0][0])

        d = ms.nearest_filament(geo.c + rs[:, None] * e[None, :], cs)[0]
        for i in range(len(rs)):
            left = d[i - 1] if i > 0 else np.inf
            right = d[i + 1] if i + 1 < len(rs) else np.inf
            if not (d[i] <= left and d[i] <= right and d[i] < 0.05 * r_):
                continue
            lo, hi = float(rs[max(i - 1, 0)]), float(rs[min(i + 1, len(rs) - 1)])
            x1, x2 = hi - g * (hi - lo), lo + g * (hi - lo)
            f1, f2 = dist(x1), dist(x2)
            for _ in range(80):
                if f1 <= f2:
                    hi, x2, f2 = x2, x1, f1
                    x1 = hi - g * (hi - lo)
                    f1 = dist(x1)
                else:
                    lo, x1, f1 = x1, x2, f2
                    x2 = lo + g * (hi - lo)
                    f2 = dist(x2)
            r_star = 0.5 * (lo + hi)
            edges.update(_graded(r_star, dist(r_star), 1.0, 0.0, r_))
    return sorted(edges)


def _patches(geo: _Geo, cs: CurrentSources | None = None,
             rings: list[float] | None = None) -> list[Patch]:
    if geo.circle_r is not None:
        dth = 2 * math.pi / CIRCLE_SECTORS
        out: list[Patch] = []
        rings = radial_edges(geo, cs) if rings is None else rings
        for r0, r1 in zip(rings[:-1], rings[1:], strict=False):
            for k in range(CIRCLE_SECTORS):
                th0 = k * dth

                def point(s: Arr, v: Arr, th0: float = th0, r0: float = r0,
                          r1: float = r1) -> Arr:
                    th = th0 + dth * v
                    rr = r0 + (r1 - r0) * s
                    res: Arr = (geo.c + (rr * np.cos(th))[:, None] * geo.ex
                                + (rr * np.sin(th))[:, None] * geo.ey)
                    return res

                def jac(s: Arr, v: Arr, r0: float = r0, r1: float = r1) -> Arr:
                    res: Arr = (r1 - r0) * (r0 + (r1 - r0) * s) * dth
                    return res

                out.append(Patch(point, jac))
        return out
    assert geo.poly is not None
    tris = _triangulate(geo.poly)
    out = []
    for a, b, c in tris:
        area2 = abs(float((b - a)[0] * (c - b)[1] - (b - a)[1] * (c - b)[0]))

        def tri_point(s: Arr, v: Arr, a: Arr = a, b: Arr = b, c: Arr = c) -> Arr:
            xy = a[None, :] + s[:, None] * (b - a)[None, :] + (s * v)[:, None] * (c - b)[None, :]
            return geo.to_world(xy)

        def tri_jac(s: Arr, v: Arr, area2: float = area2) -> Arr:
            res: Arr = area2 * s
            return res

        out.append(Patch(tri_point, tri_jac))
    return out


def _triangulate(poly: Arr) -> list[tuple[Arr, Arr, Arr]]:
    """Ear clipping of a simple polygon (2D); the triangles cover it exactly."""
    p = poly if _area2(poly) > 0 else poly[::-1]
    idx = list(range(len(p)))
    tris: list[tuple[Arr, Arr, Arr]] = []
    guard = 0
    while len(idx) > 3 and guard < 10_000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = p[i0], p[i1], p[i2]
            if _cross(b - a, c - b) <= 0:
                continue  # reflex vertex
            if any(_in_tri(p[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((a, b, c))
            idx.pop(k)
            break
    tris.append((p[idx[0]], p[idx[1]], p[idx[2]]))
    return tris


def _area2(p: Arr) -> float:
    return float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))


def _cross(u: Arr, v: Arr) -> float:
    return float(u[0] * v[1] - u[1] * v[0])


def _in_tri(q: Arr, a: Arr, b: Arr, c: Arr) -> bool:
    return (_cross(b - a, q - a) >= 0 and _cross(c - b, q - b) >= 0
            and _cross(a - c, q - c) >= 0)


Cells = tuple[NDArray[np.int64], Arr, Arr, Arr, Arr]  # patch id, s0, s1, v0, v1


@dataclass
class SurfaceIntegral:
    value: Arr  # (K,)
    error: Arr  # (K,)
    converged: bool
    cells: int
    rule: Cells | None = None  # the accepted cells (children), for a frozen re-evaluation


def _rule_nodes() -> tuple[Arr, Arr, Arr]:
    s_nodes = 0.5 * (_GL_X + 1.0)
    w2 = np.outer(_GL_W, _GL_W).ravel() / 4.0
    grid_s, grid_v = np.meshgrid(s_nodes, s_nodes, indexing="ij")
    return grid_s.ravel(), grid_v.ravel(), w2


def fixed_integrate(f: Callable[[Arr], Arr], patches: list[Patch], cells: Cells, k: int) -> Arr:
    """∫ f dS with a fixed set of cells (5×5 Gauss–Legendre each): the same rule at every
    evaluation, so the result is a smooth function of the patch geometry (Phase 4B: finite
    differences of the flux in time through a moving surface)."""
    ss, vv, w2 = _rule_nodes()
    pid, s0, s1, v0, v1 = cells
    total = np.zeros(k)
    for j in np.unique(pid):
        sel = np.flatnonzero(pid == j)
        s = (s0[sel, None] + (s1 - s0)[sel, None] * ss[None, :]).ravel()
        v = (v0[sel, None] + (v1 - v0)[sel, None] * vv[None, :]).ravel()
        pt = patches[int(j)].point(s, v)
        wts = (w2[None, :] * ((s1 - s0) * (v1 - v0))[sel, None]).ravel() \
            * patches[int(j)].jac(s, v)
        total += (f(pt) * wts[:, None]).sum(axis=0)
    return total


def surface_integrate(f: Callable[[Arr], Arr], patches: list[Patch], k: int, rtol: float,
                      keep_rule: bool = False) -> SurfaceIntegral:
    """∫ f dS over the patches for K integrand components at once (f: (N,3) points -> (N,K)).

    Each cell of the unit square is integrated with a 5×5 tensor Gauss–Legendre rule; its error
    is estimated as the difference to the sum of its four children (computed anyway when the
    cell is refined). A cell is accepted when, for every component, that difference is below
    the tolerance share of its area: tol_c = max(rtol |I_c|, 1e-9 ∫|f_c|). Non-finite values
    never converge; after SURFACE_LEVELS the remaining cells are accepted and the result is
    marked not converged."""
    s_nodes = 0.5 * (_GL_X + 1.0)
    w2 = np.outer(_GL_W, _GL_W).ravel() / 4.0
    grid_s, grid_v = np.meshgrid(s_nodes, s_nodes, indexing="ij")
    ss: Arr = grid_s.ravel()
    vv: Arr = grid_v.ravel()

    def rule(pid: NDArray[np.int64], s0: Arr, s1: Arr, v0: Arr, v1: Arr
             ) -> tuple[Arr, Arr, Arr]:
        n = pid.size
        q = np.zeros((n, k))
        qa = np.zeros((n, k))
        area = np.zeros(n)
        for j in np.unique(pid):
            sel = np.flatnonzero(pid == j)
            s = (s0[sel, None] + (s1 - s0)[sel, None] * ss[None, :]).ravel()
            v = (v0[sel, None] + (v1 - v0)[sel, None] * vv[None, :]).ravel()
            pt = patches[int(j)].point(s, v)
            jac = patches[int(j)].jac(s, v)
            wts = (w2[None, :] * ((s1 - s0) * (v1 - v0))[sel, None]).ravel() * jac
            vals = f(pt)
            q[sel] = (vals * wts[:, None]).reshape(sel.size, -1, k).sum(axis=1)
            qa[sel] = (np.abs(vals) * wts[:, None]).reshape(sel.size, -1, k).sum(axis=1)
            area[sel] = wts.reshape(sel.size, -1).sum(axis=1)
        return q, qa, area

    def split(pid: NDArray[np.int64], s0: Arr, s1: Arr, v0: Arr, v1: Arr
              ) -> tuple[NDArray[np.int64], Arr, Arr, Arr, Arr]:
        sm, vm = 0.5 * (s0 + s1), 0.5 * (v0 + v1)
        return (np.repeat(pid, 4),
                np.stack([s0, sm, s0, sm], 1).ravel(), np.stack([sm, s1, sm, s1], 1).ravel(),
                np.stack([v0, v0, vm, vm], 1).ravel(), np.stack([vm, vm, v1, v1], 1).ravel())

    # Start from each patch split into 2×2.
    cells = split(np.arange(len(patches)), np.zeros(len(patches)), np.ones(len(patches)),
                  np.zeros(len(patches)), np.ones(len(patches)))
    q, qa, area = rule(*cells)
    total_area = float(area.sum())
    abs_scale = qa.sum(axis=0)
    value = np.zeros(k)
    error = np.zeros(k)
    converged = True
    n_cells = 0
    accepted: list[Cells] = []
    for level in range(SURFACE_LEVELS + 1):
        children = split(*cells)
        cq, cqa, carea = rule(*children)
        m = cells[0].size
        qsum = cq.reshape(m, 4, k).sum(axis=1)
        err = np.abs(q - qsum)
        est = value + qsum.sum(axis=0)
        tol = np.maximum(rtol * np.abs(est), SURFACE_ABS_FACTOR * abs_scale)
        frac = area / total_area
        finite = np.all(np.isfinite(qsum), axis=1) & np.all(np.isfinite(err), axis=1)
        ok = finite & np.all(err <= tol[None, :] * frac[:, None], axis=1)
        last = level == SURFACE_LEVELS or (~ok).sum() * 4 > SURFACE_MAX_CELLS
        acc = ok | last
        if keep_rule:
            take = np.repeat(acc, 4)
            accepted.append((children[0][take], children[1][take], children[2][take],
                             children[3][take], children[4][take]))
        value += qsum[acc].sum(axis=0)
        error += np.nan_to_num(err[acc], nan=np.inf).sum(axis=0)
        n_cells += int(acc.sum()) * 4
        if last and not ok.all():
            converged = False
        if acc.all():
            break
        keep = np.repeat(~acc, 4)
        cells = (children[0][keep], children[1][keep], children[2][keep], children[3][keep],
                 children[4][keep])
        q, area = cq[keep], carea[keep]
    frozen: Cells | None = None
    if keep_rule and accepted:
        frozen = (np.concatenate([a[0] for a in accepted]),
                  np.concatenate([a[1] for a in accepted]),
                  np.concatenate([a[2] for a in accepted]),
                  np.concatenate([a[3] for a in accepted]),
                  np.concatenate([a[4] for a in accepted]))
    return SurfaceIntegral(value, error, converged and bool(np.all(np.isfinite(value))),
                           n_cells, frozen)


# ------------------------------------------------------------------------ unit quantities


def _object_cs(cs: CurrentSources, oid: str) -> CurrentSources:
    """Only one object's current elements, carrying 1 A per turn."""
    sub = dataclasses.replace(
        cs, wires=[w for w in cs.wires if w.object_id == oid],
        loops=[lp for lp in cs.loops if lp.object_id == oid],
        ideal_toroids=[t for t in cs.ideal_toroids if t.object_id == oid], magnets=[],
        objects=[o for o in cs.objects if o.object_id == oid])
    return with_currents(sub, {oid: 1.0})


def _unit_fields(cs: CurrentSources, r_min: float) -> tuple[list[str], Callable[[Arr], Arr]]:
    """Object ids of the current sources, and f(points) -> B·n integrand columns: one per
    current object at 1 A, plus the static (magnet) field last."""
    ids = [o.object_id for o in cs.objects if o.current_A is not None]
    subs = [_object_cs(cs, oid) for oid in ids]
    static = dataclasses.replace(cs, wires=[], loops=[], ideal_toroids=[],
                                 objects=[o for o in cs.objects if o.current_A is None])

    def fields(points: Arr) -> Arr:
        cols = [ms.evaluate_bh(points, sub, r_min, ms.MAGNET_RTOL["probe"]).b for sub in subs]
        cols.append(ms.evaluate_bh(points, static, r_min, ms.MAGNET_RTOL["probe"]).b
                    if static.magnets else np.zeros_like(points))
        return np.stack(cols, axis=1)  # (N, K, 3)

    return ids, fields


@dataclass
class UnitResult:
    ids: list[str]
    kinds: list[str]
    flux: Arr  # (K,) per object at 1 A
    flux_err: Arr
    static_flux: float
    static_err: float
    surface_converged: bool
    cells: int
    circ: Arr  # (K,) NaN where unsupported
    circ_err: Arr
    line_converged: bool
    subintervals: int
    singular: LocalizedText | None
    min_dist: float | None
    mutual: list[Mutual]


def _pierced(geo: _Geo, cs: CurrentSources) -> LocalizedText | None:
    """A filament crossing the surface interior or lying in it makes B·n singular inside the
    surface (integrable for a transverse crossing, but not supported by this quadrature)."""
    fil = dataclasses.replace(cs, magnets=[], ideal_toroids=[])
    if not fil.wires and not fil.loops:
        return None
    enc = enclosed_current(geo, fil)
    lies_in = [n for n in enc.notes if "in the plane of the path" in n.en]
    coplanar_inside = False
    for lp in fil.loops:
        if lies_in and abs(float((lp.center_m - geo.c) @ geo.normal)) <= geo.tol:
            th = np.linspace(0, 2 * np.pi, 1024, endpoint=False)
            v = np.cross(lp.normal, lp.u)
            ring = lp.center_m + lp.radius_m * (np.cos(th)[:, None] * lp.u
                                                + np.sin(th)[:, None] * v)
            if np.any(geo.inside(geo.to_local(ring)[:, :2])):
                coplanar_inside = True
    if enc.crossings or enc.status != "ok" or coplanar_inside:
        return L("A current filament pierces the surface or lies in it, so B·n is singular "
                 "inside the surface. The flux of a transverse crossing is finite, but this "
                 "quadrature does not resolve that singularity: the flux is not evaluated. Move "
                 "the surface or the source.",
                 "Egy áramszál átdöfi a felületet vagy benne fekszik, ezért B·n a felület "
                 "belsejében szinguláris. Merőleges átdöfésnél a fluxus véges, de ez a "
                 "kvadratúra nem kezeli ezt a szingularitást: a fluxust nem értékeljük ki. "
                 "Mozgassa a felületet vagy a forrást.")
    return None


def _circulations(geo: _Geo, cs: CurrentSources, ids: list[str], rtol: float,
                  approaches: dict[int, list[tuple[float, float, float]]]
                  ) -> tuple[Arr, Arr, bool, int]:
    """C_j = ∮ A_j,unit · dl for every loop object (NaN for other kinds), by adaptive
    Gauss–Kronrod on each path piece, split at the closest approaches to filaments."""
    k_all = len(ids)
    circ = np.full(k_all, np.nan)
    err = np.full(k_all, np.nan)
    loop_objs = [(j, [lp for lp in cs.loops if lp.object_id == oid])
                 for j, oid in enumerate(ids)]
    loop_objs = [(j, lps) for j, lps in loop_objs if lps]
    if not loop_objs:
        return circ, err, True, 0
    edges_by_piece = []
    for piece, _ in enumerate(geo.pieces()):
        fil: list[float] = []
        for t_star, d, _ in approaches[piece]:
            speed = float(np.linalg.norm(geo.param(piece, np.array([t_star]))[1][0]))
            fil += _graded(t_star, d, speed, 0.0, 1.0)
        edges_by_piece.append(sorted({0.0, *fil, 1.0}))
    obj_of: list[int] = []
    piece_of: list[int] = []
    lo: list[float] = []
    hi: list[float] = []
    for idx, (_, _) in enumerate(loop_objs):
        for piece, edges in enumerate(edges_by_piece):
            for a, b in zip(edges[:-1], edges[1:], strict=True):
                obj_of.append(idx)
                piece_of.append(piece)
                lo.append(a)
                hi.append(b)
    obj_arr, piece_arr = np.asarray(obj_of), np.asarray(piece_of)

    def integrand(absolute: bool) -> Callable[[NDArray[np.int64], Arr], Arr]:
        def f(items: NDArray[np.int64], t: Arr) -> Arr:
            out = np.empty((t.size, 1))
            for oi in np.unique(obj_arr[items]):
                for pc in np.unique(piece_arr[items]):
                    sel = (obj_arr[items] == oi) & (piece_arr[items] == pc)
                    if not sel.any():
                        continue
                    pt, dp = geo.param(int(pc), t[sel])
                    a_unit = ms._group_unit_cached(loop_objs[int(oi)][1], pt, "A")[0]
                    val = np.einsum("ij,ij->i", a_unit, dp)
                    out[sel, 0] = np.abs(val) if absolute else val
            return out
        return f

    lo_a, hi_a = np.asarray(lo), np.asarray(hi)
    coarse = adaptive_gk(integrand(True), lo_a, hi_a, 1, 1e-6, max_levels=20)
    scale = np.bincount(obj_arr, weights=coarse.value[:, 0], minlength=len(loop_objs))
    atol = LINE_ABS_FACTOR * scale[obj_arr] / np.bincount(obj_arr)[obj_arr]
    res = adaptive_gk(integrand(False), lo_a, hi_a, 1, rtol, atol=atol, max_levels=30)
    vals = np.bincount(obj_arr, weights=res.value[:, 0], minlength=len(loop_objs))
    errs = np.bincount(obj_arr, weights=res.error, minlength=len(loop_objs))
    for idx, (j, _) in enumerate(loop_objs):
        circ[j], err[j] = vals[idx], errs[idx]
    return circ, err, bool(np.all(res.converged)), int(res.intervals.sum())


# -------------------------------------------------------------------- mutual (reciprocal)


def _measurement_field(geo: _Geo) -> Callable[[Arr], Arr]:
    """B of the measurement boundary carrying 1 A along its traversal."""
    if geo.circle_r is not None:
        lp = LoopSource("measurement", 1.0, geo.c, geo.normal, geo.circle_r, geo.ex)
        sub = CurrentSources(wires=[], loops=[lp], problems=[])
        return lambda pts: ms.loops_field(sub.loops, pts)[0]
    verts = np.vstack([geo.param(k, np.array([0.0]))[0] for k, _ in enumerate(geo.pieces())])
    return lambda pts: segment_field(pts, verts)


def _crosses_disk(poly_world: Arr, lp: LoopSource) -> bool:
    """Whether a closed polyline passes through the disk spanned by a turn."""
    h = (poly_world - lp.center_m) @ lp.normal
    nxt = np.roll(poly_world, -1, axis=0)
    hn = np.roll(h, -1)
    for i in np.flatnonzero(h * hn <= 0):
        if h[i] == hn[i]:
            pt = poly_world[i]
        else:
            w = h[i] / (h[i] - hn[i])
            pt = poly_world[i] + w * (nxt[i] - poly_world[i])
        rad = pt - lp.center_m - ((pt - lp.center_m) @ lp.normal) * lp.normal
        if np.linalg.norm(rad) <= lp.radius_m * (1 + 1e-12):
            return True
    return False


def _mutual(geo: _Geo, cs: CurrentSources, ids: list[str], kinds: list[str], flux: Arr,
            flux_err: Arr, rtol: float, ok_surface: bool) -> list[Mutual]:
    out: list[Mutual] = []
    bmeas = _measurement_field(geo)
    dense = geo.polyline(4096) if geo.circle_r is not None else np.vstack(
        [geo.param(k, np.linspace(0, 1, 257))[0] for k, _ in enumerate(geo.pieces())])
    for j, oid in enumerate(ids):
        loops = [lp for lp in cs.loops if lp.object_id == oid]
        if not loops:
            out.append(Mutual(object_id=oid, available=False, reason=L(
                "Mutual inductance is computed for closed circular sources (loops, solenoid and "
                "finite-toroid turns); this source is an infinite wire or an ideal toroid.",
                "A kölcsönös induktivitást zárt kör alakú forrásokra számítjuk (hurkok, "
                "szolenoid és véges toroid menetei); ez a forrás végtelen vezető vagy ideális "
                "toroid.")))
            continue
        if not ok_surface:
            out.append(Mutual(object_id=oid, available=False, reason=L(
                "The flux through the measurement surface is not available.",
                "A mérőfelületen átmenő fluxus nem érhető el.")))
            continue
        if any(_crosses_disk(dense, lp) for lp in loops):
            out.append(Mutual(object_id=oid, available=True, M12_H=float(flux[j]),
                              M12_error_H=float(flux_err[j]), reason=L(
                                  "The measurement loop passes through a source turn's disk: "
                                  "the reciprocal flux M21 is not evaluated (singular).",
                                  "A mérőhurok átmegy egy forrásmenet korongján: a kölcsönös "
                                  "M21 fluxust nem értékeljük ki (szinguláris).")))
            continue
        m21, m21_err, conv = 0.0, 0.0, True
        for lp in loops:
            disk = _Geo(AmperePath.model_validate({
                "id": "turn", "shape": {"type": "circle", "radius_m": lp.radius_m},
                "center_m": tuple(lp.center_m), "rotation_euler_xyz_rad": (0.0, 0.0, 0.0)}),
                geo.tol)
            # Orient the disk by the turn's own frame (normal: positive current direction).
            disk.ex, disk.ey, disk.ez = lp.u, np.cross(lp.normal, lp.u), lp.normal
            disk.normal = lp.normal
            def flux_density(p: Arr, n: Arr = lp.normal) -> Arr:
                out_: Arr = (bmeas(p) @ n)[:, None]
                return out_

            res = surface_integrate(flux_density, _patches(disk), 1, 0.1 * rtol)
            m21 += float(res.value[0])
            m21_err += float(res.error[0])
            conv &= res.converged
        m12 = float(flux[j])
        diff = m12 - m21
        tol = max(rtol * max(abs(m12), abs(m21)), float(flux_err[j]) + m21_err)
        out.append(Mutual(
            object_id=oid, available=True, M12_H=m12, M12_error_H=float(flux_err[j]),
            M21_H=m21 if conv else None, M21_error_H=m21_err if conv else None,
            reciprocity_difference_H=diff if conv else None,
            reciprocity_relative=(abs(diff) / max(abs(m12), abs(m21))
                                  if conv and max(abs(m12), abs(m21)) > 0 else None),
            reciprocity_ok=(abs(diff) <= tol) if conv else None))
    return out


_UNIT_CACHE: OrderedDict[str, UnitResult] = OrderedDict()
_UNIT_CACHE_ENTRIES = 64


def _geometry_key(scene: Scene, surface: FluxSurface, mutual: bool) -> str:
    """Everything the unit quantities depend on: the magnetic geometry and magnetization, the
    surface physics; never the currents, the profiles or the time."""
    s = scene.model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
        src = o.get("source")
        if isinstance(src, dict):
            src.pop("current_A", None)
            src.pop("profile", None)
    payload = json.dumps({"scene": s, "surface": surface.physics_dump(), "mutual": mutual},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


Approaches = dict[int, list[tuple[float, float, float]]]


def boundary_singularity(geo: _Geo, cs: CurrentSources
                         ) -> tuple[LocalizedText | None, float | None, Approaches]:
    """(reason if the surface or its boundary meets a filament, closest filament distance of
    the boundary, the closest approaches per boundary piece)."""
    approaches = {k: _filament_approaches(geo, k, cs) for k, _ in enumerate(geo.pieces())}
    dmin = None
    touches = False
    for found in approaches.values():
        for _, d_star, scale in found:
            dmin = d_star if dmin is None else min(dmin, d_star)
            touches |= d_star <= float(ms.filament_tolerance(np.asarray(scale)))
    singular = _pierced(geo, cs)
    if touches:
        singular = L("The boundary passes through a current filament, where the vector "
                     "potential and the field are singular.",
                     "A határgörbe áthalad egy áramszálon, ahol a vektorpotenciál és a tér "
                     "szinguláris.")
    return singular, dmin, approaches


def _unit_quantities(scene: Scene, cs: CurrentSources, surface: FluxSurface, geo: _Geo,
                     mutual: bool) -> UnitResult:
    key = _geometry_key(scene, surface, mutual)
    hit = _UNIT_CACHE.get(key)
    if hit is not None:
        _UNIT_CACHE.move_to_end(key)
        return hit
    r_min = ms.COINCIDENCE_FACTOR * scene.domain.diagonal_m
    ids, fields = _unit_fields(cs, r_min)
    kinds: list[str] = [str(next(o.kind for o in cs.objects if o.object_id == oid))
                        for oid in ids]
    singular, dmin, approaches = boundary_singularity(geo, cs)
    n_k = len(ids) + 1
    nan = np.full(n_k - 1, np.nan)
    if singular is not None:
        res = UnitResult(ids, kinds, nan.copy(), nan.copy(), math.nan, math.nan, False, 0,
                         nan.copy(), nan.copy(), False, 0, singular, dmin, [])
    else:
        normal = geo.normal
        rtol = 0.1 * surface.rtol

        def f(points: Arr) -> Arr:
            out: Arr = np.einsum("nkj,j->nk", fields(points), normal)
            return out

        si = surface_integrate(f, _patches(geo, cs), n_k, rtol)
        circ, circ_err, line_ok, nsub = _circulations(geo, cs, ids, rtol, approaches)
        mut = _mutual(geo, cs, ids, kinds, si.value[:-1], si.error[:-1], surface.rtol,
                      si.converged) if mutual else []
        res = UnitResult(ids, kinds, si.value[:-1], si.error[:-1], float(si.value[-1]),
                         float(si.error[-1]), si.converged, si.cells, circ, circ_err, line_ok,
                         nsub, None, dmin, mut)
    _UNIT_CACHE[key] = res
    while len(_UNIT_CACHE) > _UNIT_CACHE_ENTRIES:
        _UNIT_CACHE.popitem(last=False)
    return res


# ------------------------------------------------------------------------- time combination


# The flux counts as momentarily steady when |dPhi/dt| is below this fraction of its largest
# possible value (sum_j |Phi_j| max|dI_j/dt|): well above rounding of dI/dt at an extremum of the
# profile (~1e-16), far below any physical change.
STEADY_FRACTION = 1e-9


def _lenz(dphi: float, emf: float | None, tol: float) -> Lenz:
    trend: Literal["increasing", "decreasing", "steady"] = (
        "steady" if abs(dphi) <= tol else "increasing" if dphi > 0 else "decreasing")
    if emf is None or abs(emf) <= tol:
        return Lenz(flux_trend=trend, emf_sign=0, circulation="none")
    return Lenz(flux_trend=trend, emf_sign=1 if emf > 0 else -1,
                circulation="along_path" if emf > 0 else "against_path")


def scale_turns(r: SurfaceResult, n: int) -> SurfaceResult:
    """An N-turn measurement coil of identical coincident turns in series: every flux becomes
    the flux linkage NΦ and every EMF N times the single-turn EMF (Phase 4B)."""
    if n == 1:
        return r
    upd: dict[str, object] = {"turns": n}
    for name in ("flux_Wb", "flux_error_Wb", "dflux_dt_V", "dflux_dt_error_V", "emf_V",
                 "emf_error_V", "difference_V", "tolerance_V", "static_flux_Wb", "emf_motional_V",
                 "emf_motional_error_V", "emf_total_V", "emf_total_error_V"):
        v = getattr(r, name)
        if v is not None:
            upd[name] = n * v
    upd["sources"] = [s.model_copy(update={
        "unit_flux_Wb_per_A": n * s.unit_flux_Wb_per_A, "unit_flux_error": n * s.unit_flux_error,
        "unit_circulation_Wb_per_A": None if s.unit_circulation_Wb_per_A is None
        else n * s.unit_circulation_Wb_per_A,
        "unit_circulation_error": None if s.unit_circulation_error is None
        else n * s.unit_circulation_error,
        "flux_Wb": n * s.flux_Wb, "emf_V": None if s.emf_V is None else n * s.emf_V})
        for s in r.sources]
    upd["mutual"] = [m.model_copy(update={
        k: (None if getattr(m, k) is None else n * getattr(m, k))
        for k in ("M12_H", "M12_error_H", "M21_H", "M21_error_H", "reciprocity_difference_H")})
        for m in r.mutual]
    if r.derivative is not None and r.derivative.error_V is not None:
        upd["derivative"] = r.derivative.model_copy(update={"error_V": n * r.derivative.error_V})
    if r.reference is not None:
        upd["reference"] = r.reference.model_copy(update={
            "emf_V": n * r.reference.emf_V,
            "flux_Wb": None if r.reference.flux_Wb is None else n * r.reference.flux_Wb})
    return r.model_copy(update=upd)


def surface_result(scene: Scene, cs: CurrentSources, ts: TimeState, surface: FluxSurface,
                   mutual: bool, convention: VelocityConvention = "undefined") -> SurfaceResult:
    if surface.moving:
        from .motional import moving_surface_result  # noqa: PLC0415 (module cycle)
        return scale_turns(moving_surface_result(scene, cs, surface, ts.t_s, convention),
                           surface.turns)
    return scale_turns(_stationary_result(scene, cs, ts, surface, mutual), surface.turns)


def _stationary_result(scene: Scene, cs: CurrentSources, ts: TimeState, surface: FluxSurface,
                       mutual: bool) -> SurfaceResult:
    diag = scene.domain.diagonal_m
    geo = _Geo(surface, ms.IN_PLANE_FACTOR * diag)
    base = {"surface_id": surface.id, "time_s": ts.t_s, "derivative_unique": ts.derivative_unique}
    if geo.reasons:
        return SurfaceResult(**base, valid=False, invalid_reasons=geo.reasons, status="invalid")
    geom = {"valid": True, "normal": list(map(float, geo.normal)),
            "center_m": list(map(float, geo.c)), "area_m2": geo.area(),
            "perimeter_m": geo.perimeter(),
            "polyline_m": [list(map(float, p)) for p in geo.polyline()]}
    u = _unit_quantities(scene, cs, surface, geo, mutual)
    if u.singular is not None:
        return SurfaceResult(**base, **geom, status="singular", status_reason=u.singular,
                             min_distance_to_filament_m=u.min_dist)
    by_id = {s.object_id: s for s in ts.sources}
    cur = np.array([by_id[oid].current_A for oid in u.ids])
    rate = np.array([by_id[oid].rate.value for oid in u.ids])
    flux = float(cur @ u.flux + u.static_flux)
    flux_err = float(np.abs(cur) @ u.flux_err + u.static_err)
    dphi = float(rate @ u.flux)
    dphi_err = float(np.abs(rate) @ u.flux_err)
    varying = rate != 0.0
    unsupported = [oid for oid, v, c in zip(u.ids, varying, u.circ, strict=True)
                   if v and not np.isfinite(c)]
    emf = emf_err = None
    if not unsupported:
        emf = float(-(rate[varying] @ u.circ[varying])) if varying.any() else 0.0
        emf_err = float(np.abs(rate[varying]) @ u.circ_err[varying]) if varying.any() else 0.0
    # Scale-aware tolerance: relative to the result, with an absolute floor at the size of the
    # individual source terms (a near-zero EMF is not judged by a relative criterion alone).
    terms = float(np.abs(rate) @ np.maximum(np.abs(u.flux), np.nan_to_num(np.abs(u.circ))))
    tol = surface.rtol * max(abs(dphi), abs(emf or 0.0), terms)
    scale = np.array([by_id[oid].rate_scale for oid in u.ids])
    steady = STEADY_FRACTION * float(scale @ np.abs(u.flux))
    sources = [SourceFlux(
        object_id=oid, kind=kind, current_A=float(c), dI_dt_A_per_s=float(r),
        unit_flux_Wb_per_A=float(fl), unit_flux_error=float(fe),
        unit_circulation_Wb_per_A=float(ci) if np.isfinite(ci) else None,
        unit_circulation_error=float(ce) if np.isfinite(ce) else None,
        flux_Wb=float(c * fl), emf_V=float(-r * ci) if np.isfinite(ci) else None)
        for oid, kind, c, r, fl, fe, ci, ce in zip(u.ids, u.kinds, cur, rate, u.flux, u.flux_err,
                                                    u.circ, u.circ_err, strict=True)]
    common = {**base, **geom, "flux_Wb": flux, "flux_error_Wb": flux_err, "dflux_dt_V": dphi,
              "dflux_dt_error_V": dphi_err, "emf_V": emf, "emf_error_V": emf_err,
              "surface_converged": u.surface_converged, "line_converged": u.line_converged,
              "surface_cells": u.cells, "line_subintervals": u.subintervals,
              "min_distance_to_filament_m": u.min_dist, "sources": sources,
              "static_flux_Wb": u.static_flux, "mutual": u.mutual,
              "no_change": not varying.any(), "tolerance_V": tol,
              "lenz": _lenz(dphi, emf, steady)}
    if unsupported:
        return SurfaceResult(**common, status="unsupported", status_reason=L(
            f"The EMF is not evaluated: {', '.join(unsupported)} changes at this time and has no "
            "vector potential in this model (infinite wire or ideal toroid). The flux and its "
            "derivative are shown.",
            f"Az EMF nincs kiértékelve: {', '.join(unsupported)} ebben az időpontban változik, "
            "és ebben a modellben nincs vektorpotenciálja (végtelen vezető vagy ideális toroid). "
            "A fluxus és deriváltja látható."))
    assert emf is not None and emf_err is not None
    diff = emf + dphi
    rel = abs(diff) / max(abs(emf), abs(dphi)) if max(abs(emf), abs(dphi)) > 0 else None
    common.update(difference_V=diff, relative_error=rel)
    if not u.surface_converged or dphi_err > tol:
        return SurfaceResult(**common, status="surface_not_converged")
    if not u.line_converged or emf_err > tol:
        return SurfaceResult(**common, status="line_not_converged")
    return SurfaceResult(**common, status="verified" if abs(diff) <= tol else "failed")


def compute(scene: Scene, request: InductionRequest, solver_id: str, solver_version: str
            ) -> InductionHeader:
    cs = current_sources(scene)
    ts = time_state(scene, cs, request.time_s)
    return InductionHeader(
        solver_id=solver_id, solver_version=solver_version, time_s=ts.t_s,
        method=L("Φ_B = ∫B·n dS by adaptive Gauss–Legendre surface quadrature (5×5 per cell, "
                 "quadtree refinement) of each source's field at 1 A; dΦ_B/dt = Σ dI_j/dt Φ_j "
                 "with analytical dI/dt; EMF = ∮E_ind·dl = −Σ dI_j/dt ∮A_j·dl by adaptive "
                 "Gauss–Kronrod line quadrature of the Coulomb-gauge vector potential. The two "
                 "sides of Faraday's law come from different fields and quadratures.",
                 "Φ_B = ∫B·n dS adaptív Gauss–Legendre felületi kvadratúrával (cellánként 5×5, "
                 "négyfás finomítás) minden forrás 1 A-es terére; dΦ_B/dt = Σ dI_j/dt Φ_j "
                 "analitikus dI/dt-vel; EMF = ∮E_ind·dl = −Σ dI_j/dt ∮A_j·dl a Coulomb-mértékű "
                 "vektorpotenciál adaptív Gauss–Kronrod vonalkvadratúrájával. A Faraday-törvény "
                 "két oldala különböző terekből és kvadratúrákból adódik."),
        surfaces=[surface_result(scene, cs, ts, s, request.mutual, request.velocity_convention)
                  for s in request.surfaces])


def fingerprint(scene: Scene, request: InductionRequest) -> str:
    s = scene.model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
    payload = json.dumps({"scene": s, "time": request.time_s, "mutual": request.mutual,
                          "convention": request.velocity_convention,
                          "surfaces": [x.physics_dump() for x in request.surfaces]},
                         sort_keys=True, separators=(",", ":"))
    return "induction:" + hashlib.sha256(payload.encode()).hexdigest()
