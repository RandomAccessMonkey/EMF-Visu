"""Moving measurement conductors: motional EMF and the generalized Faraday law (Phase 4B).

A moving closed conductor C(t) bounds the flat surface S(t) it spans (circle, rectangle,
polygon moved rigidly, or the sliding-rod rectangle whose rod edge moves along the rails).
The sources stay fixed; their currents may follow the Phase 4A profiles. At simulation time t:

    Φ_B(t)      = ∫_{S(t)} B(r, t) · n(t) dS               adaptive surface quadrature
    EMF_tr      = ∮_{C(t)} E_ind · dl = −Σ_j dI_j/dt ∮ A_j · dl   (transformer, Phase 4A field)
    EMF_mot     = ∮_{C(t)} (u × B) · dl                    adaptive line quadrature, u from
                                                            the analytical motion
    EMF         = EMF_tr + EMF_mot                         generalized EMF
    dΦ_B/dt     from the flux values only: Richardson-extrapolated finite differences of Φ_B
                at nearby times (central, or one-sided at a velocity or current jump), each
                flux evaluated with the same (frozen) quadrature cells so that the
                discretization is a smooth function of time.

The generalized Faraday law  ∮[E + u × B]·dl = −dΦ_B/dt  is verified by comparing EMF with
−dΦ_B/dt; the electrostatic part of E integrates to zero around a closed path and is counted as
zero. All fields come from one field model: B per source at 1 A (the magnetostatic solver),
A per source at 1 A (the Coulomb-gauge loop potential), combined with I_j(t) and dI_j/dt.

Nothing here makes a source move, drives a current in the conductor or feeds back on the
sources: the conductor is a passive measurement path.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .ampere import AmperePath, _Geo, _graded
from .i18n import L, LocalizedText
from .induction import (
    LINE_ABS_FACTOR,
    STEADY_FRACTION,
    Approaches,
    Cells,
    DerivativeInfo,
    FluxSurface,
    Lenz,
    MotionalSample,
    MotionState,
    SlidingRodShape,
    SourceFlux,
    SurfaceResult,
    UniformReference,
    _lenz,
    _patches,
    _unit_fields,
    boundary_singularity,
    fixed_integrate,
    radial_edges,
    surface_integrate,
)
from .numerics.quadrature import adaptive_gk
from .scene import motion as mo
from .scene.currents import CurrentSources
from .scene.models import Scene
from .scene.profiles import corners as profile_corners
from .scene.timedep import time_state
from .scene.transforms import rotation_matrix_xyz
from .solvers.analytical import magnetostatics as ms

Arr = NDArray[np.float64]
Side = Literal["left", "right"]

DERIVATIVE_LEVELS = 9  # step halvings of the Richardson sequence
DERIVATIVE_START = 0.05  # first step: this × the characteristic time
DERIVATIVE_TOL_SHARE = 0.1  # the derivative's error budget: this × the comparison tolerance
CORNER_NEAR = 1e-9  # |t − corner| below this × the time scale counts as at the corner
RELATIVISTIC_WARN = 1e-2  # |u|/c above this: the magnetoquasistatic, Galilean picture degrades
SAMPLES_RIGID = 32
SAMPLES_ROD = 9


# --------------------------------------------------------------------------- field model


@dataclass
class FieldModel:
    """B(r, t) = Σ_k w_k(t) B_k(r): K columns (one per current source at 1 A, then a static
    column with weight 1), and per source column a vector potential at 1 A where one exists.
    Built from a scene (``scene_field_model``) or, in tests, from an analytical field."""

    ids: list[str]  # source ids of the columns (the last, static column has no id)
    unit_b: Callable[[Arr], Arr]  # points (N, 3) -> (N, K, 3)
    unit_a: list[Callable[[Arr], Arr] | None]  # per source column (len K − 1)
    weights: Callable[[float], Arr]  # t -> (K,) currents (static column: 1)
    rates: Callable[[float, Side], Arr]  # (t, side) -> (K − 1,) dI/dt
    rate_scale: Arr  # (K − 1,) largest |dI/dt| of each profile (A/s)
    rate_unique: Callable[[float], bool]
    corners: list[float]  # times where some dI/dt jumps
    time_scale: float  # characteristic time of the currents (inf: none)
    cs: CurrentSources | None = None  # filaments, for singularity handling

    def b(self, points: Arr, t: float) -> Arr:
        out: Arr = np.einsum("nkj,k->nj", self.unit_b(points), self.weights(t))
        return out


def scene_field_model(scene: Scene, cs: CurrentSources) -> FieldModel:
    r_min = ms.COINCIDENCE_FACTOR * scene.domain.diagonal_m
    ids, fields = _unit_fields(cs, r_min)
    ts0 = time_state(scene, cs, 0.0)
    order = {s.object_id: k for k, s in enumerate(ts0.sources)}
    unit_a: list[Callable[[Arr], Arr] | None] = []
    for oid in ids:
        loops = [lp for lp in cs.loops if lp.object_id == oid]
        if loops:
            def a_fn(p: Arr, loops: list = loops) -> Arr:  # type: ignore[type-arg]
                out: Arr = ms._group_unit_cached(loops, p, "A")[0]
                return out
            unit_a.append(a_fn)
        else:
            unit_a.append(None)

    def weights(t: float) -> Arr:
        st = time_state(scene, cs, t).sources
        return np.array([*(st[order[oid]].current_A for oid in ids), 1.0])

    def rates(t: float, side: Side) -> Arr:
        st = time_state(scene, cs, t).sources
        return np.array([getattr(st[order[oid]].rate, side) for oid in ids])

    by_id = {o.id: o for o in scene.objects}
    corner_set: set[float] = set()
    scale = math.inf
    for oid in ids:
        prof = getattr(by_id[oid].source, "profile", None)
        if prof is None:
            continue
        corner_set.update(profile_corners(prof))
        if prof.type == "sinusoidal" and prof.peak_A > 0:
            scale = min(scale, 1.0 / (2 * math.pi * prof.frequency_Hz))
    return FieldModel(
        ids=ids, unit_b=fields, unit_a=unit_a, weights=weights, rates=rates,
        rate_scale=np.array([ts0.sources[order[oid]].rate_scale for oid in ids]),
        rate_unique=lambda t: time_state(scene, cs, t).derivative_unique,
        corners=sorted(corner_set), time_scale=scale, cs=cs)


# ------------------------------------------------------------------------- posed geometry


@dataclass
class Posed:
    """The conductor at one instant: its geometry and the material velocity of its points."""

    geo: _Geo
    pose: mo.Pose | None  # rigid motion
    rod: tuple[float, float, float] | None  # sliding rod: x(t), v_x left, v_x right
    rod_axis: Arr | None  # world direction of the rails (+x local)
    moving_pieces: list[int]
    invalid: list[LocalizedText]

    @property
    def unique(self) -> bool:
        if self.pose is not None:
            return self.pose.unique
        assert self.rod is not None
        return self.rod[1] == self.rod[2]

    def velocity(self, points: Arr, piece: int, side: Side) -> Arr:
        if piece not in self.moving_pieces:
            return np.zeros_like(points)
        if self.pose is not None:
            return self.pose.material_velocity(points, side)
        assert self.rod is not None and self.rod_axis is not None
        v = self.rod[1] if side == "left" else self.rod[2]
        return np.broadcast_to(v * self.rod_axis, points.shape).copy()


def _reference_frame(surface: FluxSurface) -> tuple[Arr, Arr]:
    return (np.asarray(surface.center_m, float),
            rotation_matrix_xyz(surface.rotation_euler_xyz_rad))


def _path(surface: FluxSurface, shape: dict[str, object], center: Arr) -> AmperePath:
    return AmperePath.model_validate({
        "id": surface.id, "shape": shape, "center_m": tuple(map(float, center)),
        "rotation_euler_xyz_rad": surface.rotation_euler_xyz_rad,
        "reversed": surface.reversed, "rtol": surface.rtol})


def posed(surface: FluxSurface, t: float, tol: float,
          rod_state: tuple[float, float] | None = None) -> Posed:
    """The conductor at time t. ``rod_state`` (x, v) overrides the sliding rod's prescribed
    motion (Phase 4C: the rod's position and velocity come from its equation of motion)."""
    c0, r0 = _reference_frame(surface)
    shape = surface.shape
    if isinstance(shape, SlidingRodShape):
        tr = shape.rod_motion
        if rod_state is not None:
            x, vl = rod_state
            vr = vl
        else:
            x = shape.rod_position_m + float(mo.displacement(tr, t)[0])
            vl = float(mo.velocity(tr, t, "left")[0])
            vr = float(mo.velocity(tr, t, "right")[0])
        invalid: list[LocalizedText] = []
        if not x > tol:
            invalid.append(L("The rod has reached the connecting segment: the circuit encloses "
                             "no area.",
                             "A rúd elérte az összekötő szakaszt: az áramkör nem zár közre "
                             "területet."))
        elif x > shape.rail_length_m:
            invalid.append(L("The rod has left the rails: there is no closed circuit.",
                             "A rúd lecsúszott a sínekről: nincs zárt áramkör."))
        width = max(x, tol)
        geo = _Geo(_path(surface, {"type": "rectangle", "width_m": width,
                                   "height_m": shape.rail_separation_m},
                         c0 + r0[:, 0] * (width / 2)), tol)
        # Rectangle pieces in traversal order: rail, rod, rail, connecting segment (the
        # reversed traversal visits the same edges in the opposite direction).
        return Posed(geo, None, (x, vl, vr), r0[:, 0].copy(), [1], invalid)
    assert surface.motion is not None
    pose = mo.pose(surface.motion, c0, r0, t)
    geo = _Geo(_path(surface, shape.model_dump(mode="json"), c0), tol)
    if not geo.reasons:
        geo.c = pose.center
        geo.ex, geo.ey, geo.ez = (pose.rotation[:, 0].copy(), pose.rotation[:, 1].copy(),
                                  pose.rotation[:, 2].copy())
        geo.normal = geo.sense * geo.ez
    return Posed(geo, pose, None, None, list(range(len(geo.pieces())) if not geo.reasons
                                             else []), list(geo.reasons))


def _motion_corners(surface: FluxSurface) -> list[float]:
    if isinstance(surface.shape, SlidingRodShape):
        tr = surface.shape.rod_motion
        return tr.corners() if isinstance(tr, mo._Window) else []
    assert surface.motion is not None
    return mo.corners(surface.motion)


def _motion_scale(surface: FluxSurface, length: float) -> float:
    if isinstance(surface.shape, SlidingRodShape):
        return mo.time_scale(mo.MotionProfile(translation=surface.shape.rod_motion), length)
    assert surface.motion is not None
    return mo.time_scale(surface.motion, length)


# ----------------------------------------------------------------------- line integrals


@dataclass
class LineIntegral:
    value: Arr  # (C,)
    error: float
    abs_value: Arr  # (C,) ∫|integrand| (scale of cancellation)
    converged: bool
    subintervals: int


def line_integral(geo: _Geo, pieces: list[int], fn: Callable[[int, Arr, Arr], Arr], comps: int,
                  rtol: float, approaches: Approaches | None, scale: float = 0.0
                  ) -> LineIntegral:
    """Σ over pieces of ∫_0^1 fn(piece, r(t), dr/dt) dt, by adaptive Gauss–Kronrod with
    breakpoints graded around the closest approaches to filaments (as for Ampère paths)."""
    piece_of: list[int] = []
    lo: list[float] = []
    hi: list[float] = []
    for piece in pieces:
        fil: list[float] = []
        for t_star, d, _ in (approaches or {}).get(piece, []):
            speed = float(np.linalg.norm(geo.param(piece, np.array([t_star]))[1][0]))
            fil += _graded(t_star, d, speed, 0.0, 1.0)
        edges = sorted({0.0, *fil, 1.0})
        for a, b in zip(edges[:-1], edges[1:], strict=True):
            piece_of.append(piece)
            lo.append(a)
            hi.append(b)
    if not lo:
        z = np.zeros(comps)
        return LineIntegral(z, 0.0, z.copy(), True, 0)
    piece_arr = np.asarray(piece_of)

    def make(absolute: bool) -> Callable[[NDArray[np.int64], Arr], Arr]:
        def f(items: NDArray[np.int64], t: Arr) -> Arr:
            out = np.empty((t.size, comps))
            pcs = piece_arr[items]
            for pc in np.unique(pcs):
                sel = pcs == pc
                pt, dp = geo.param(int(pc), t[sel])
                val = fn(int(pc), pt, dp)
                out[sel] = np.abs(val) if absolute else val
            return out
        return f

    lo_a, hi_a = np.asarray(lo), np.asarray(hi)
    coarse = adaptive_gk(make(True), lo_a, hi_a, comps, 1e-6, max_levels=20)
    abs_val = coarse.value.sum(axis=0)
    atol = LINE_ABS_FACTOR * max(float(np.linalg.norm(abs_val)), scale) / len(lo)
    res = adaptive_gk(make(False), lo_a, hi_a, comps, rtol, atol=atol, max_levels=30)
    return LineIntegral(res.value.sum(axis=0), float(res.error.sum()), abs_val,
                        bool(np.all(res.converged)), int(res.intervals.sum()))


def ub_scale(p: Posed, fm: FieldModel, t: float, side: Side, n: int = 16) -> float:
    """∫ |u| |B| |dl| over the moving pieces (midpoint rule): the size the motional EMF can
    reach for this speed and field whatever the orientation, used as the absolute scale of the
    tolerances (an instant where u × B ⊥ dl everywhere has EMF 0, not a relative error)."""
    w = fm.weights(t)
    total = 0.0
    ts = (np.arange(n) + 0.5) / n
    for piece in p.moving_pieces:
        pt, dp = p.geo.param(piece, ts)
        b = np.einsum("nkj,k->nj", fm.unit_b(pt), w)
        u = p.velocity(pt, piece, side)
        val = np.linalg.norm(u, axis=1) * np.linalg.norm(b, axis=1) * np.linalg.norm(dp, axis=1)
        total += float(np.sum(val[np.isfinite(val)])) / n
    return total


def motional_emf(p: Posed, fm: FieldModel, t: float, side: Side, rtol: float,
                 approaches: Approaches | None, scale: float = 0.0) -> LineIntegral:
    """EMF_mot = ∮ (u × B) · dl over the conductor at time t (only moving pieces contribute)."""
    w = fm.weights(t)

    def fn(piece: int, pt: Arr, dp: Arr) -> Arr:
        b = np.einsum("nkj,k->nj", fm.unit_b(pt), w)
        u = p.velocity(pt, piece, side)
        out: Arr = np.einsum("ij,ij->i", np.cross(u, b), dp)[:, None]
        return out

    return line_integral(p.geo, p.moving_pieces, fn, 1, rtol, approaches, scale)


def unit_circulations(p: Posed, fm: FieldModel, rtol: float, approaches: Approaches | None
                      ) -> tuple[Arr, Arr, bool, int]:
    """C_j = ∮ A_j · dl at 1 A per source with a vector potential (NaN otherwise)."""
    have = [j for j, a in enumerate(fm.unit_a) if a is not None]
    circ = np.full(len(fm.unit_a), np.nan)
    err = np.full(len(fm.unit_a), np.nan)
    if not have:
        return circ, err, True, 0

    def fn(piece: int, pt: Arr, dp: Arr) -> Arr:
        cols = []
        for j in have:
            a_fn = fm.unit_a[j]
            assert a_fn is not None
            cols.append(np.einsum("ij,ij->i", a_fn(pt), dp))
        out: Arr = np.stack(cols, axis=1)
        return out

    res = line_integral(p.geo, list(range(len(p.geo.pieces()))), fn, len(have), rtol, approaches)
    for k, j in enumerate(have):
        circ[j] = res.value[k]
        err[j] = res.error  # norm over all components: a bound for each
    return circ, err, res.converged, res.subintervals


# ------------------------------------------------------------------- flux and d(flux)/dt


@dataclass
class FluxAt:
    unit: Arr  # (K,) Φ per column (sources at 1 A, then static)
    error: Arr
    converged: bool
    cells: int
    patches_rule: Cells | None  # frozen rule (cells) for re-evaluation
    rings: list[float] | None


def flux_columns(p: Posed, fm: FieldModel, rtol: float) -> FluxAt:
    geo = p.geo
    rings = radial_edges(geo, fm.cs) if geo.circle_r is not None else None
    patches = _patches(geo, fm.cs, rings)
    normal = geo.normal
    k = len(fm.ids) + 1

    def f(points: Arr) -> Arr:
        out: Arr = np.einsum("nkj,j->nk", fm.unit_b(points), normal)
        return out

    si = surface_integrate(f, patches, k, rtol, keep_rule=True)
    return FluxAt(si.value, si.error, si.converged, si.cells, si.rule, rings)


@dataclass
class Derivative:
    value: float
    error: float
    converged: bool
    method: Literal["central", "forward", "backward"]
    step: float
    levels: int


def richardson(flux: Callable[[float], float], t: float, h0: float,
               method: Literal["central", "forward", "backward"], tol: float,
               levels: int = DERIVATIVE_LEVELS) -> Derivative:
    """dΦ/dt from flux values: second-order differences D(h) (central, or the one-sided
    three-point formulas), Richardson-extrapolated R = (4 D(h/2) − D(h)) / 3, steps halved until
    two successive extrapolations agree within ``tol`` (the error estimate is their
    difference). Non-finite flux values never converge."""
    cache: dict[float, float] = {}

    def F(x: float) -> float:
        if x not in cache:
            cache[x] = flux(x)
        return cache[x]

    d_prev: float | None = None
    r_prev: float | None = None
    best = (math.nan, math.inf)
    h = h0
    for k in range(levels):
        h = h0 / 2.0**k
        if method == "central":
            d = (F(t + h) - F(t - h)) / (2 * h)
        elif method == "forward":
            d = (-3 * F(t) + 4 * F(t + h) - F(t + 2 * h)) / (2 * h)
        else:
            d = (3 * F(t) - 4 * F(t - h) + F(t - 2 * h)) / (2 * h)
        if not math.isfinite(d):
            return Derivative(math.nan, math.inf, False, method, h, k + 1)
        if d_prev is not None:
            r = (4 * d - d_prev) / 3
            if r_prev is not None:
                err = abs(r - r_prev)
                if err < best[1]:
                    best = (r, err)
                if err <= tol:
                    return Derivative(r, err, True, method, h, k + 1)
            r_prev = r
        d_prev = d
    return Derivative(best[0], best[1], False, method, h, levels)


# ---------------------------------------------------------------------------- the result


def _vec(a: Arr) -> list[float]:
    return [float(x) for x in a]


def _samples(p: Posed, fm: FieldModel, t: float, side: Side | None) -> list[MotionalSample]:
    out: list[MotionalSample] = []
    pieces = range(len(p.geo.pieces()))
    w = fm.weights(t)
    for piece in pieces:
        moving = piece in p.moving_pieces
        if p.rod is not None and not moving:
            continue
        n = SAMPLES_ROD if p.rod is not None else max(2, SAMPLES_RIGID // len(p.geo.pieces()))
        ts = (np.arange(n) + 0.5) / n
        pt, _ = p.geo.param(piece, ts)
        b = np.einsum("nkj,k->nj", fm.unit_b(pt), w)
        u = p.velocity(pt, piece, side) if side is not None else np.zeros_like(pt)
        uxb = np.cross(u, b)
        for i in range(n):
            ok = bool(np.all(np.isfinite(b[i])))
            out.append(MotionalSample(point_m=_vec(pt[i]), u_m_per_s=_vec(u[i]),
                                      B_T=_vec(b[i]) if ok else None,
                                      u_cross_B_V_per_m=_vec(uxb[i]) if ok and side else None,
                                      moving=moving))
    return out


def _state(surface: FluxSurface, p: Posed, side: Side | None, samples: list[MotionalSample]
           ) -> MotionState:
    speed = max((float(np.linalg.norm(s.u_m_per_s)) for s in samples), default=0.0)
    if p.pose is not None:
        pz = p.pose
        return MotionState(
            kind="rigid", center_m=_vec(pz.center), rotation=[_vec(r) for r in pz.rotation],
            side=side, unique=pz.unique,
            velocity_m_per_s=_vec(pz.velocity(side)) if side else None,
            angular_velocity_rad_per_s=_vec(pz.omega(side)) if side else None,
            velocity_left_m_per_s=_vec(pz.velocity_left),
            velocity_right_m_per_s=_vec(pz.velocity_right),
            angular_velocity_left_rad_per_s=_vec(pz.omega_left),
            angular_velocity_right_rad_per_s=_vec(pz.omega_right), max_speed_m_per_s=speed)
    assert p.rod is not None and p.rod_axis is not None
    shape = surface.shape
    assert isinstance(shape, SlidingRodShape)
    c0, r0 = _reference_frame(surface)
    h = shape.rail_separation_m / 2

    def w(x: float, y: float) -> list[float]:
        return _vec(c0 + r0 @ np.array([x, y, 0.0]))

    x, vl, vr = p.rod
    v = (vl if side == "left" else vr) if side else None
    return MotionState(
        kind="sliding_rod", center_m=_vec(c0), rotation=[_vec(r) for r in r0], side=side,
        unique=vl == vr, velocity_m_per_s=_vec(v * p.rod_axis) if v is not None else None,
        angular_velocity_rad_per_s=[0.0, 0.0, 0.0] if side else None,
        velocity_left_m_per_s=_vec(vl * p.rod_axis), velocity_right_m_per_s=_vec(vr * p.rod_axis),
        angular_velocity_left_rad_per_s=[0.0, 0.0, 0.0],
        angular_velocity_right_rad_per_s=[0.0, 0.0, 0.0], max_speed_m_per_s=speed,
        rod_position_m=x, rod_velocity_m_per_s=v, rod_length_m=shape.rail_separation_m,
        rails_m=[[w(0, -h), w(shape.rail_length_m, -h)], [w(0, h), w(shape.rail_length_m, h)],
                 [w(0, -h), w(0, h)]],
        rod_m=[w(x, -h), w(x, h)])


def _reference(surface: FluxSurface, p: Posed, fm: FieldModel, t: float, side: Side,
               varying: bool) -> UniformReference | None:
    """Uniform-field generator references (approximations, labelled as such)."""
    if varying:
        return None  # the references are for static fields only
    if p.rod is not None:
        assert isinstance(surface.shape, SlidingRodShape)
        x, vl, vr = p.rod
        c0, r0 = _reference_frame(surface)
        mid = c0 + r0 @ np.array([x, 0.0, 0.0])
        b = fm.b(mid[None, :], t)[0]
        if not np.all(np.isfinite(b)):
            return None
        bn = float(b @ p.geo.normal)
        length = surface.shape.rail_separation_m
        v = vl if side == "left" else vr
        return UniformReference(
            kind="sliding_rod_BLv", B_T=_vec(b), point_m=_vec(mid), flux_Wb=bn * length * x,
            emf_V=-bn * length * v, note=L(
                "Uniform-field approximation: B taken everywhere equal to its value at the rod's "
                "midpoint, so |EMF| = |B·n| L |v|. Valid only where the field is uniform over "
                "the circuit; the result above integrates the actual field.",
                "Homogén tér közelítés: B mindenütt a rúd felezőpontjabeli értékével egyenlő, "
                "így |EMF| = |B·n| L |v|. Csak ott érvényes, ahol a tér az áramkörön homogén; "
                "a fenti eredmény a tényleges teret integrálja."))
    pz = p.pose
    if pz is None or np.any(pz.velocity(side) != 0.0) or not np.any(pz.omega(side) != 0.0):
        return None
    b = fm.b(pz.center[None, :], t)[0]
    if not np.all(np.isfinite(b)):
        return None
    n = p.geo.normal
    area = p.geo.area()
    return UniformReference(
        kind="rotating_coil", B_T=_vec(b), point_m=_vec(pz.center), flux_Wb=area * float(b @ n),
        emf_V=-area * float(b @ np.cross(pz.omega(side), n)), note=L(
            "Uniform-field approximation: B taken everywhere equal to its value at the coil's "
            "centre, so Φ = A B·n(t) = BA cos(ωt + φ) and EMF = −A B·(ω × n). Valid only where "
            "the field is uniform over the coil; the result above integrates the actual field.",
            "Homogén tér közelítés: B mindenütt a tekercs középpontjabeli értékével egyenlő, "
            "így Φ = A B·n(t) = BA cos(ωt + φ) és EMF = −A B·(ω × n). Csak ott érvényes, ahol "
            "a tér a tekercsen homogén; a fenti eredmény a tényleges teret integrálja."))


def _geometry_dict(geo: _Geo) -> dict[str, object]:
    return {"valid": True, "normal": _vec(geo.normal), "center_m": _vec(geo.c),
            "area_m2": geo.area(), "perimeter_m": geo.perimeter(),
            "polyline_m": [_vec(q) for q in geo.polyline()]}


def evaluate_moving(surface: FluxSurface, fm: FieldModel, t: float,
                    convention: mo.VelocityConvention, tol_geo: float) -> SurfaceResult:
    """The moving-surface result for any field model (scene or analytical)."""
    p = posed(surface, t, tol_geo)
    base: dict[str, object] = {"surface_id": surface.id, "time_s": t, "moving": True}
    if p.invalid:
        return SurfaceResult(**base, valid=False, invalid_reasons=p.invalid, status="invalid")
    geo = p.geo
    # One-sided choice: the motion's (if its velocity jumps at t), else the currents'.
    motion_unique = p.unique
    side = mo.resolve_side(motion_unique, convention)
    current_unique = fm.rate_unique(t)
    if side is None:
        rate_side: Side = "right"
    elif motion_unique and not current_unique and convention != "undefined":
        rate_side = convention
    else:
        rate_side = side
    singular, dmin, approaches = (boundary_singularity(geo, fm.cs) if fm.cs is not None
                                  else (None, None, {}))
    samples = _samples(p, fm, t, side)
    state = _state(surface, p, side, samples)
    geom = _geometry_dict(geo)
    common: dict[str, object] = {**base, **geom, "motion": state, "motional_samples": samples,
                                 "min_distance_to_filament_m": dmin,
                                 "derivative_unique": current_unique and motion_unique}
    if singular is not None:
        return SurfaceResult(**common, status="singular", status_reason=singular)
    warnings: list[LocalizedText] = []
    speed = state.max_speed_m_per_s or 0.0
    if speed / mo.SPEED_OF_LIGHT > RELATIVISTIC_WARN:
        warnings.append(L(
            f"The conductor moves at {speed / mo.SPEED_OF_LIGHT:.2g} c: the nonrelativistic "
            "(Galilean) treatment of u × B is no longer accurate.",
            f"A vezető sebessége {speed / mo.SPEED_OF_LIGHT:.2g} c: az u × B nemrelativisztikus "
            "(galilei) kezelése már nem pontos."))
    rtol = 0.1 * surface.rtol

    # Flux through the instantaneous surface (per column) and the transformer EMF.
    fx = flux_columns(p, fm, rtol)
    w = fm.weights(t)
    rate = fm.rates(t, rate_side)
    flux = float(fx.unit @ w)
    flux_err = float(fx.error @ np.abs(w))
    circ, circ_err, line_ok, nsub = unit_circulations(p, fm, rtol, approaches)
    varying = rate != 0.0
    unsupported = [oid for oid, v, c in zip(fm.ids, varying, circ, strict=True)
                   if v and not np.isfinite(c)]
    emf_tr = emf_tr_err = None
    if not unsupported:
        emf_tr = float(-(rate[varying] @ circ[varying])) if varying.any() else 0.0
        emf_tr_err = float(np.abs(rate[varying]) @ circ_err[varying]) if varying.any() else 0.0
    sources = [SourceFlux(
        object_id=oid, kind="", current_A=float(w[j]), dI_dt_A_per_s=float(rate[j]),
        unit_flux_Wb_per_A=float(fx.unit[j]), unit_flux_error=float(fx.error[j]),
        unit_circulation_Wb_per_A=float(circ[j]) if np.isfinite(circ[j]) else None,
        unit_circulation_error=float(circ_err[j]) if np.isfinite(circ_err[j]) else None,
        flux_Wb=float(w[j] * fx.unit[j]),
        emf_V=float(-rate[j] * circ[j]) if np.isfinite(circ[j]) else None)
        for j, oid in enumerate(fm.ids)]
    common.update(flux_Wb=flux, flux_error_Wb=flux_err, emf_V=emf_tr, emf_error_V=emf_tr_err,
                  surface_converged=fx.converged, surface_cells=fx.cells,
                  static_flux_Wb=float(fx.unit[-1]), sources=sources, warnings=warnings)
    if side is None:
        common.update(emf_motional_V=None, line_converged=line_ok, line_subintervals=nsub)
        return SurfaceResult(**common, status="motion_undefined", status_reason=L(
            "The conductor's velocity jumps at this instant (left and right values differ), so "
            "the instantaneous motional EMF and dΦ/dt are not uniquely defined. Select a "
            "one-sided velocity convention to evaluate them.",
            "A vezető sebessége ebben a pillanatban ugrik (a bal és jobb oldali érték eltér), "
            "ezért a pillanatnyi mozgási EMF és dΦ/dt nem egyértelmű. Kiértékelésükhöz "
            "válasszon egyoldali sebesség-konvenciót."))

    # Motional EMF along the moving conductor.
    ub = ub_scale(p, fm, t, side)
    mot = motional_emf(p, fm, t, side, rtol, approaches, ub)
    emf_mot, emf_mot_err = float(mot.value[0]), mot.error
    line_conv = line_ok and mot.converged
    emf_tot = emf_tot_err = None
    if emf_tr is not None and emf_tr_err is not None:
        emf_tot, emf_tot_err = emf_tr + emf_mot, emf_tr_err + emf_mot_err
    terms = float(np.abs(rate) @ np.maximum(np.abs(fx.unit[:-1]), np.nan_to_num(np.abs(circ))))
    scale_terms = terms + max(ub, float(mot.abs_value[0]))

    # dΦ/dt from the flux values only (same frozen cells at every stencil time).
    length = max(geo.size(), 1e-300)
    if dmin is not None:
        length = min(length, max(dmin, 1e-6 * geo.size()))
    t_char = min(_motion_scale(surface, length), fm.time_scale)
    if not math.isfinite(t_char):
        t_char = 1.0
    corners = sorted(set(_motion_corners(surface)) | set(fm.corners))
    at = [c for c in corners if abs(t - c) <= CORNER_NEAR * t_char]
    method: Literal["central", "forward", "backward"] = "central"
    if at:
        # One-sided differences on the side whose velocity / dI/dt was used; just off a corner
        # (but within rounding of it) stay on t's own side.
        d_side: Side = (side if not motion_unique else rate_side if not current_unique
                        else "left" if t < at[0] else "right")
        method = "forward" if d_side == "right" else "backward"
    h0 = DERIVATIVE_START * t_char
    others = [c for c in corners if c not in at]
    if method == "central":
        near = min((abs(c - t) for c in others), default=math.inf)
        h0 = min(h0, near / 1.01)
    else:
        sgn = 1.0 if method == "forward" else -1.0
        ahead = min(((c - t) * sgn for c in others if (c - t) * sgn > 0), default=math.inf)
        h0 = min(h0, ahead / 2.02)
    cells = fx.patches_rule
    cols = len(fm.ids) + 1

    def flux_at(x: float) -> float:
        q = posed(surface, x, tol_geo)
        if q.invalid:
            return math.nan
        patches = _patches(q.geo, fm.cs, fx.rings)
        nrm = q.geo.normal

        def f(points: Arr) -> Arr:
            out: Arr = np.einsum("nkj,j->nk", fm.unit_b(points), nrm)
            return out

        assert cells is not None
        vals = fixed_integrate(f, patches, cells, cols)
        return float(vals @ fm.weights(x))

    tol = surface.rtol * max(abs(emf_tot if emf_tot is not None else emf_mot), scale_terms)
    der = richardson(flux_at, t, h0, method, DERIVATIVE_TOL_SHARE * tol)
    dphi = der.value
    steady = STEADY_FRACTION * (float(fm.rate_scale @ np.abs(fx.unit[:-1])) + ub)
    tol = surface.rtol * max(abs(dphi) if math.isfinite(dphi) else 0.0,
                             abs(emf_tot if emf_tot is not None else emf_mot), scale_terms)
    common.update(
        emf_motional_V=emf_mot, emf_motional_error_V=emf_mot_err, emf_total_V=emf_tot,
        emf_total_error_V=emf_tot_err, generalized_complete=not unsupported,
        dflux_dt_V=dphi if math.isfinite(dphi) else None,
        dflux_dt_error_V=der.error if math.isfinite(der.error) else None,
        derivative=DerivativeInfo(method=der.method, step_s=der.step, levels=der.levels,
                                  converged=der.converged,
                                  error_V=der.error if math.isfinite(der.error) else None),
        line_converged=line_conv, line_subintervals=nsub + mot.subintervals, tolerance_V=tol,
        no_change=not varying.any() and emf_mot == 0.0 and mot.abs_value[0] == 0.0,
        reference=_reference(surface, p, fm, t, side, bool(varying.any())),
        lenz=_lenz(dphi, emf_tot, steady) if math.isfinite(dphi) else Lenz(
            flux_trend="steady", emf_sign=0, circulation="none"))
    if unsupported:
        common["lenz"] = _lenz(dphi, emf_mot, steady) if math.isfinite(dphi) else None
        return SurfaceResult(**common, status="unsupported", status_reason=L(
            f"Motional-only result: {', '.join(unsupported)} changes at this time and has no "
            "vector potential in this model (infinite wire or ideal toroid), so the transformer "
            "EMF and the generalized EMF are not evaluated. The motional EMF ∮(u × B)·dl, the "
            "flux and dΦ/dt are shown.",
            f"Csak mozgási eredmény: {', '.join(unsupported)} ebben az időpontban változik, és "
            "ebben a modellben nincs vektorpotenciálja (végtelen vezető vagy ideális toroid), "
            "ezért a transzformátor-EMF és az általánosított EMF nincs kiértékelve. A mozgási "
            "EMF ∮(u × B)·dl, a fluxus és dΦ/dt látható."))
    assert emf_tot is not None and emf_tot_err is not None
    if math.isfinite(dphi):
        diff = emf_tot + dphi
        big = max(abs(emf_tot), abs(dphi))
        common.update(difference_V=diff, relative_error=abs(diff) / big if big > 0 else None)
    if not fx.converged:
        return SurfaceResult(**common, status="surface_not_converged")
    if not line_conv or emf_tot_err > tol:
        return SurfaceResult(**common, status="line_not_converged")
    if not der.converged or not math.isfinite(dphi) or der.error > tol:
        return SurfaceResult(**common, status="derivative_not_converged", status_reason=L(
            "The time derivative of the flux did not converge: successive Richardson "
            "extrapolations of the finite differences still differ by more than the tolerance "
            "(the flux may change too abruptly, or the stencil approaches a singular "
            "configuration).",
            "A fluxus időderiváltja nem konvergált: a véges differenciák egymást követő "
            "Richardson-extrapolációi még a tűrésnél jobban eltérnek (a fluxus túl hirtelen "
            "változhat, vagy a sablon szinguláris elrendezéshez közelít)."))
    diff = emf_tot + dphi
    return SurfaceResult(**common, status="verified" if abs(diff) <= tol else "failed")


def moving_surface_result(scene: Scene, cs: CurrentSources, surface: FluxSurface, t: float,
                          convention: mo.VelocityConvention) -> SurfaceResult:
    fm = scene_field_model(scene, cs)
    r = evaluate_moving(surface, fm, t, convention, ms.IN_PLANE_FACTOR * scene.domain.diagonal_m)
    kinds = {o.object_id: o.kind for o in cs.objects}
    return r.model_copy(update={"sources": [s.model_copy(update={"kind": kinds.get(s.object_id,
                                                                                 "")})
                                            for s in r.sources]})


def uniform_field_model(b0: Callable[[float], Arr], db0: Callable[[float], Arr] | None = None,
                        origin: Arr | None = None) -> FieldModel:
    """An analytical uniform field B(t) = b0(t), for tests and references: three columns
    (unit fields along x, y, z) with weights b0(t) and rates db0/dt, and the symmetric-gauge
    vector potential A = ½ B × (r − origin), so that E_ind = −½ dB/dt × (r − origin)."""
    o = np.zeros(3) if origin is None else np.asarray(origin, float)
    eye = np.eye(3)

    def unit_b(points: Arr) -> Arr:
        out: Arr = np.broadcast_to(eye[None, :, :], (points.shape[0], 3, 3)).copy()
        out = np.concatenate([out, np.zeros((points.shape[0], 1, 3))], axis=1)
        return out

    def a_col(k: int) -> Callable[[Arr], Arr]:
        def f(points: Arr) -> Arr:
            out: Arr = 0.5 * np.cross(eye[k][None, :], points - o[None, :])
            return out
        return f

    def rates(t: float, side: Side) -> Arr:
        if db0 is None:
            return np.zeros(3)
        return np.asarray(db0(t), float)

    return FieldModel(
        ids=["Bx", "By", "Bz"], unit_b=unit_b, unit_a=[a_col(0), a_col(1), a_col(2)],
        weights=lambda t: np.array([*np.asarray(b0(t), float), 1.0]), rates=rates,
        rate_scale=np.zeros(3), rate_unique=lambda t: True, corners=[], time_scale=math.inf,
        cs=None)

