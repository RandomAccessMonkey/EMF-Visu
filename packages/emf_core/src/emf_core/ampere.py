"""Ampère's law investigation (Phase 3B): closed planar paths, the numerical circulation of H
(and of B), and the enclosed free current determined independently from the source geometry.

Paths. A path lives in the local xy plane of its own transform (centre, Euler XYZ rotation):

* ``circle``: exact parametrisation r(t) = c + R (cos t u + sin t v), t ∈ [0, 2π);
* ``rectangle``: width × height, four straight edges;
* ``polygon``: vertices given in local coordinates (x, y, z); they must lie in the local plane
  (|z| within tolerance), form a simple, non-degenerate, closed polygon.

Traversal is counter-clockwise about the path's positive normal; the normal follows the
right-hand rule. For a polygon the vertex order decides the traversal (counter-clockwise about
local +z gives normal +z). ``reversed`` flips traversal and normal together.

Left-hand side: Γ_H = ∮ H·dl by vectorised adaptive Gauss–Kronrod (``numerics.quadrature``)
over the exact parametrisation, H from the magnetostatic solver (``evaluate_bh``). Γ_B = ∮ B·dl
is computed in the same pass. Convergence: total error estimate ≤ max(rtol·|Γ_H|, 1e-8 A,
1e-8·I_scale).

Right-hand side: the signed free current through the planar region bounded by the path, from
the source geometry only (never from Γ):

* infinite wire: plane crossing, inside test, sign of d·n;
* circular loops, solenoid turns, finite-toroid turns: circle–plane intersections (0, tangent,
  2), inside test, sign of the current's tangent along n;
* ideal toroid: coaxial circular paths only (NI or 0); anything else is "unsupported";
* permanent magnets: bound current, never free current (0).

A crossing within the tolerance of the path means the path meets a filament: the circulation
is undefined. A tangency inside the region or a filament lying in the surface is ambiguous.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field

from .i18n import L, LocalizedText
from .numerics.quadrature import adaptive_gk
from .scene.currents import CurrentSources, current_sources
from .scene.models import PositiveFloat, Scene, StrictModel, Vec3
from .scene.transforms import rotation_matrix_xyz
from .solvers.analytical import magnetostatics as ms
from .units import MU0

Arr = NDArray[np.float64]
ATOL_A = 1e-8  # absolute tolerance of the circulation, amperes
SCALE_RTOL = 1e-8  # relative to I_scale, for cancellation cases
REFERENCE_SCALE_A = 1.0  # I_scale used when the scene has no free current at all
# Path points carry rounding <= eps S_path (S_path = |centre| + size); within distance d of a
# filament that perturbs H by <= eps S_path / d relatively, over a stretch contributing at most
# about I_scale / 2 to the circulation. With a factor 2 of safety the float64 floor of Γ_H is
# eps S_path / d_min I_scale (measured errors are 10-100x below it).
AMPERE_FLOOR_FACTOR = 1.0
NEAR_FACTOR = 0.02  # a filament closer than this × path size triggers a "near-singular" warning
CIRCLE_ARCS = 8


class CirclePath(StrictModel):
    type: Literal["circle"] = "circle"
    radius_m: PositiveFloat = 0.1


class RectanglePath(StrictModel):
    type: Literal["rectangle"] = "rectangle"
    width_m: PositiveFloat = 0.2
    height_m: PositiveFloat = 0.1


class PolygonPath(StrictModel):
    type: Literal["polygon"] = "polygon"
    vertices_m: list[Vec3] = Field(min_length=1, max_length=64)  # local coordinates
    closed: bool = True


PathShape = Annotated[CirclePath | RectanglePath | PolygonPath, Field(discriminator="type")]


class PathDisplay(StrictModel):
    """Visualization only: never part of a cache key."""

    visible: bool = True
    show_normal: bool = True
    show_crossings: bool = True
    show_surface: bool = False


class AmperePath(StrictModel):
    id: str = Field(min_length=1, max_length=40)
    name: str = ""
    shape: PathShape
    center_m: Vec3 = (0.0, 0.0, 0.0)
    rotation_euler_xyz_rad: Vec3 = (0.0, 0.0, 0.0)
    reversed: bool = False
    rtol: Annotated[float, Field(ge=1e-10, le=1e-2)] = 1e-4
    display: PathDisplay | None = None

    def physics_dump(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"name", "display"})


class AmpereRequest(StrictModel):
    paths: list[AmperePath] = Field(min_length=1, max_length=16)


class Crossing(BaseModel):
    object_id: str
    kind: str
    point_m: list[float]
    sign: int  # +1 along the surface normal, -1 against, 0 ambiguous / on the path
    current_A: float  # the source's signed current (per turn)
    contribution_A: float  # sign × current (0 for ambiguous)
    state: Literal["inside", "on_path", "ambiguous"]


class Enclosure(BaseModel):
    available: bool  # False: unsupported or ambiguous; the value is then not a result
    status: Literal["ok", "ambiguous", "on_path", "unsupported"]
    value_A: float | None
    crossings: list[Crossing]
    notes: list[LocalizedText] = []


class PathResult(BaseModel):
    path_id: str
    valid: bool
    invalid_reasons: list[LocalizedText] = []
    status: Literal["verified", "not_converged", "ambiguous", "intersects_source", "unsupported",
                    "failed", "invalid"]
    normal: list[float] | None = None  # positive surface normal (world)
    center_m: list[float] | None = None
    perimeter_m: float | None = None
    area_m2: float | None = None
    polyline_m: list[list[float]] = []  # for drawing, along the traversal direction
    circulation_H_A: float | None = None
    circulation_error_A: float | None = None
    circulation_B_T_m: float | None = None
    converged: bool | None = None
    subintervals: int | None = None
    evaluations: int | None = None
    min_distance_to_filament_m: float | None = None
    near_singular: bool = False
    crosses_material: bool = False  # passes through a magnet or the ideal core
    enclosure: Enclosure | None = None
    difference_A: float | None = None
    relative_error: float | None = None
    tolerance_A: float | None = None
    bound_current_from_B_A: float | None = None  # Γ_B/μ0 − I_free (explanatory, magnets)
    # Phase 3B.1: float64 floor of Γ_H from path points rounded near a filament,
    # ε S_path / d_min · I_scale. If it exceeds tolerance_A the path is not verified.
    precision_floor_A: float | None = None


class AmpereHeader(BaseModel):
    solver_id: str
    solver_version: str
    current_scale_A: float
    method: LocalizedText
    paths: list[PathResult]


# ----------------------------------------------------------------------------- geometry


class _Geo:
    """A validated path: frame, 2D outline in the local plane, traversal."""

    def __init__(self, path: AmperePath, tol: float) -> None:
        self.path = path
        rot = rotation_matrix_xyz(path.rotation_euler_xyz_rad)
        self.c = np.asarray(path.center_m, float)
        self.ex, self.ey, self.ez = rot[:, 0], rot[:, 1], rot[:, 2]
        self.reasons: list[LocalizedText] = []
        self.tol = tol
        shape = path.shape
        self.circle_r: float | None = None
        self.poly: Arr | None = None  # (n, 2) counter-clockwise about +ez·sense
        sense = 1.0
        if isinstance(shape, CirclePath):
            self.circle_r = shape.radius_m
        elif isinstance(shape, RectanglePath):
            w, h = shape.width_m / 2, shape.height_m / 2
            self.poly = np.array([[-w, -h], [w, -h], [w, h], [-w, h]])
        else:
            v = np.asarray(shape.vertices_m, float)
            self._validate_polygon(v, shape.closed)
            if self.reasons:
                self.normal = self.ez
                return
            self.poly = v[:, :2].copy()
            area2 = _signed_area(self.poly)
            if area2 < 0:  # clockwise about +z: the right-hand normal is -z
                sense = -1.0
        if path.reversed:
            sense = -sense
        self.sense = sense
        self.normal = sense * self.ez

    def _validate_polygon(self, v: Arr, closed: bool) -> None:
        size = float(np.ptp(v[:, :2], axis=0).max()) if len(v) else 0.0
        if not closed:
            self.reasons.append(L("The path is open. Ampère's law needs a closed path.",
                                  "Az út nyitott. Az Ampère-törvényhez zárt út kell."))
            return
        if len(v) < 3:
            self.reasons.append(L("A polygon needs at least three vertices.",
                                  "Egy sokszöghöz legalább három csúcs kell."))
            return
        if np.max(np.abs(v[:, 2])) > max(self.tol, 1e-9 * size):
            self.reasons.append(L(
                "The vertices do not lie in one plane (the path's local xy plane). Non-planar "
                "paths have no supported spanning surface in this milestone.",
                "A csúcsok nem egy síkban (az út helyi xy síkjában) vannak. Nem sík utakhoz ebben "
                "a mérföldkőben nincs támogatott kifeszített felület."))
            return
        p = v[:, :2]
        edges = np.roll(p, -1, axis=0) - p
        if np.any(np.linalg.norm(edges, axis=1) <= self.tol):
            self.reasons.append(L("Two consecutive vertices coincide (a zero-length edge).",
                                  "Két egymást követő csúcs egybeesik (nulla hosszúságú él)."))
            return
        n = len(p)
        for i in range(n):
            for j in range(i + 1, n):
                if j == i + 1 or (i == 0 and j == n - 1):
                    continue
                if _segments_intersect(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n], self.tol):
                    self.reasons.append(L("The polygon intersects itself; only simple paths "
                                          "have a well-defined enclosed current.",
                                          "A sokszög önmagát metszi; csak egyszerű utakhoz "
                                          "tartozik jól definiált bezárt áram."))
                    return
        if abs(_signed_area(p)) <= self.tol * max(size, self.tol):
            self.reasons.append(L("The polygon is degenerate: its vertices are collinear.",
                                  "A sokszög elfajult: csúcsai egy egyenesre esnek."))
            return

    # world <-> local
    def to_world(self, xy: Arr) -> Arr:
        out: Arr = self.c + xy[:, :1] * self.ex + xy[:, 1:2] * self.ey
        return out

    def to_local(self, p: Arr) -> Arr:
        d = np.atleast_2d(p) - self.c
        out: Arr = np.stack([d @ self.ex, d @ self.ey, d @ self.ez], axis=1)
        return out

    def size(self) -> float:
        if self.circle_r is not None:
            return 2 * self.circle_r
        assert self.poly is not None
        return float(np.ptp(self.poly, axis=0).max())

    def boundary_distance(self, xy: Arr) -> Arr:
        """Distance from local 2D points to the path curve."""
        if self.circle_r is not None:
            out: Arr = np.abs(np.linalg.norm(xy, axis=1) - self.circle_r)
            return out
        assert self.poly is not None
        a = self.poly
        b = np.roll(a, -1, axis=0)
        ab = b - a
        ap = xy[:, None, :] - a[None, :, :]
        t = np.clip(np.einsum("kij,ij->ki", ap, ab) / np.einsum("ij,ij->i", ab, ab), 0.0, 1.0)
        proj = a[None] + t[:, :, None] * ab[None]
        out = np.linalg.norm(xy[:, None, :] - proj, axis=2).min(axis=1)
        return out

    def inside(self, xy: Arr) -> NDArray[np.bool_]:
        if self.circle_r is not None:
            out: NDArray[np.bool_] = np.linalg.norm(xy, axis=1) < self.circle_r
            return out
        assert self.poly is not None
        return _point_in_polygon(xy, self.poly)

    def perimeter(self) -> float:
        if self.circle_r is not None:
            return 2 * math.pi * self.circle_r
        assert self.poly is not None
        return float(np.linalg.norm(np.roll(self.poly, -1, axis=0) - self.poly, axis=1).sum())

    def area(self) -> float:
        if self.circle_r is not None:
            return math.pi * self.circle_r**2
        assert self.poly is not None
        return abs(_signed_area(self.poly))

    def pieces(self) -> list[tuple[str, int]]:
        """Integration pieces: circle arcs or polygon edges, in traversal order."""
        if self.circle_r is not None:
            return [("arc", k) for k in range(CIRCLE_ARCS)]
        assert self.poly is not None
        return [("edge", k) for k in range(len(self.poly))]

    def param(self, piece: int, t: Arr) -> tuple[Arr, Arr]:
        """Point and derivative dr/dt for t ∈ [0, 1] on a piece, along the positive traversal
        (counter-clockwise about +normal)."""
        if self.circle_r is not None:
            r = self.circle_r
            th0 = 2 * math.pi * piece / CIRCLE_ARCS
            dth = 2 * math.pi / CIRCLE_ARCS
            th = th0 + dth * t
            s = self.sense
            # Counter-clockwise about +ez for sense +1, clockwise for -1.
            pt = self.c + r * (np.cos(th)[:, None] * self.ex + s * np.sin(th)[:, None] * self.ey)
            dp = r * dth * (-np.sin(th)[:, None] * self.ex + s * np.cos(th)[:, None] * self.ey)
            return pt, dp
        assert self.poly is not None
        poly = self.poly if self.sense * np.sign(_signed_area(self.poly)) > 0 else self.poly[::-1]
        a = poly[piece]
        b = poly[(piece + 1) % len(poly)]
        xy = a[None, :] + t[:, None] * (b - a)[None, :]
        pt = self.to_world(xy)
        dp = np.broadcast_to((b - a)[0] * self.ex + (b - a)[1] * self.ey, pt.shape)
        return pt, np.asarray(dp)

    def polyline(self, n_circle: int = 128) -> Arr:
        if self.circle_r is not None:
            t = np.linspace(0, 1, n_circle // CIRCLE_ARCS + 1)
            pts = [self.param(k, t[:-1] if k < CIRCLE_ARCS - 1 else t)[0]
                   for k in range(CIRCLE_ARCS)]
            out: Arr = np.vstack(pts)
            return out
        pts = [self.param(k, np.array([0.0]))[0] for k, _ in enumerate(self.pieces())]
        pts.append(pts[0])
        out = np.vstack(pts)
        return out


def _signed_area(p: Arr) -> float:
    x, y = p[:, 0], p[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _cross2(a: Arr, b: Arr) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def _segments_intersect(p1: Arr, p2: Arr, q1: Arr, q2: Arr, tol: float) -> bool:
    d1, d2 = p2 - p1, q2 - q1
    denom = _cross2(d1, d2)
    if abs(denom) <= tol * tol:
        # parallel: overlapping collinear segments count as intersecting
        if abs(_cross2(q1 - p1, d1)) > tol * float(np.linalg.norm(d1)):
            return False
        t0 = float((q1 - p1) @ d1) / float(d1 @ d1)
        t1 = float((q2 - p1) @ d1) / float(d1 @ d1)
        return max(t0, t1) >= 0 and min(t0, t1) <= 1
    t = _cross2(q1 - p1, d2) / denom
    u = _cross2(q1 - p1, d1) / denom
    return -1e-12 <= t <= 1 + 1e-12 and -1e-12 <= u <= 1 + 1e-12


def _point_in_polygon(xy: Arr, poly: Arr) -> NDArray[np.bool_]:
    """Even-odd ray casting (the polygon is simple, so this equals the winding test)."""
    x, y = xy[:, 0][:, None], xy[:, 1][:, None]
    a = poly[None, :, :]
    b = np.roll(poly, -1, axis=0)[None, :, :]
    cond = (a[..., 1] > y) != (b[..., 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xin = a[..., 0] + (y - a[..., 1]) * (b[..., 0] - a[..., 0]) / (b[..., 1] - a[..., 1])
    out: NDArray[np.bool_] = (np.count_nonzero(cond & (x < xin), axis=1) % 2) == 1
    return out


# ------------------------------------------------------------------- enclosed free current


def enclosed_current(geo: _Geo, cs: CurrentSources) -> Enclosure:
    tol = geo.tol
    n = geo.normal
    crossings: list[Crossing] = []
    notes: list[LocalizedText] = []
    status: Literal["ok", "ambiguous", "on_path", "unsupported"] = "ok"

    def classify(oid: str, kind: str, point: Arr, tangent: Arr, current: float) -> None:
        nonlocal status
        xy = geo.to_local(point)[:, :2]
        # A filament crossing is "on the path" only when float64 cannot tell it apart from the
        # path: the source-scaled filament tolerance (Phase 3B.1), not the domain tolerance.
        scale = float(np.linalg.norm(point - geo.c)) + geo.size()
        on_path = float(geo.boundary_distance(xy)[0]) <= float(
            ms.filament_tolerance(np.asarray(scale)))
        if on_path:
            crossings.append(Crossing(object_id=oid, kind=kind, point_m=list(map(float, point)),
                                      sign=0, current_A=current, contribution_A=0.0,
                                      state="on_path"))
            status = "on_path"
            return
        if not bool(geo.inside(xy)[0]):
            return
        tn = float(tangent @ n)
        if abs(tn) <= 1e-12:
            crossings.append(Crossing(object_id=oid, kind=kind, point_m=list(map(float, point)),
                                      sign=0, current_A=current, contribution_A=0.0,
                                      state="ambiguous"))
            if status == "ok":
                status = "ambiguous"
            return
        sgn = 1 if tn > 0 else -1
        crossings.append(Crossing(object_id=oid, kind=kind, point_m=list(map(float, point)),
                                  sign=sgn, current_A=current, contribution_A=sgn * current,
                                  state="inside"))

    for w in cs.wires:
        dn = float(w.direction @ n)
        dist0 = float((w.point_m - geo.c) @ n)
        if abs(dn) <= 1e-12:
            if abs(dist0) > tol:
                continue  # parallel to the surface, off it: never crosses
            # The wire lies in the surface plane: it crosses the path if it meets it.
            pts = geo.to_local(w.point_m + np.linspace(-1, 1, 4001)[:, None] * 4 * geo.size()
                               * w.direction)[:, :2]
            if np.any(geo.boundary_distance(pts) <= max(tol, 1e-3 * geo.size())) or \
                    np.any(geo.inside(pts)):
                status = "ambiguous"
                notes.append(L(f"Wire '{w.object_id}' lies in the spanning surface; its "
                               "contribution cannot be established.",
                               f"A(z) '{w.object_id}' vezeték a kifeszített felületben fekszik; "
                               "járuléka nem határozható meg."))
            continue
        tw = (float((geo.c - w.point_m) @ n)) / dn
        classify(w.object_id, "infinite_wire", w.point_m + tw * w.direction, w.direction,
                 w.current_A)

    for lp in cs.loops:
        u = lp.u
        v = np.cross(lp.normal, u)
        a = lp.radius_m
        # points c + a(cos θ u + sin θ v); signed height above the path plane:
        h0 = float((lp.center_m - geo.c) @ n)
        hu, hv = a * float(u @ n), a * float(v @ n)
        amp = math.hypot(hu, hv)
        if amp <= tol:
            # Loop parallel to the surface plane.
            if abs(h0) > tol:
                continue
            # Coplanar: unlinked unless it touches the path.
            ths = np.linspace(0, 2 * np.pi, 2048, endpoint=False)
            ring = lp.center_m + a * (np.cos(ths)[:, None] * u + np.sin(ths)[:, None] * v)
            if np.any(geo.boundary_distance(geo.to_local(ring)[:, :2]) <= tol):
                status = "on_path"
                crossings.append(Crossing(object_id=lp.object_id, kind=lp.kind,
                                          point_m=list(map(float, lp.center_m)), sign=0,
                                          current_A=lp.current_A, contribution_A=0.0,
                                          state="on_path"))
            else:
                notes.append(L("A current loop lies in the plane of the path without touching "
                               "it: two disjoint closed curves in one plane are not linked, so "
                               "it contributes 0.",
                               "Egy áramhurok az út síkjában fekszik, de nem érinti: egy síkban "
                               "fekvő két diszjunkt zárt görbe nincs összekapcsolva, így járuléka "
                               "0."))
            continue
        # h0 + hu cos θ + hv sin θ = 0  →  cos(θ - φ) = -h0/amp
        ratio = -h0 / amp
        if abs(ratio) > 1 + 1e-12:
            continue
        phi = math.atan2(hv, hu)
        if abs(abs(ratio) - 1) <= 1e-9:
            th = phi + (0.0 if ratio > 0 else math.pi)
            pt = lp.center_m + a * (math.cos(th) * u + math.sin(th) * v)
            xy = geo.to_local(pt)[:, :2]
            if float(geo.boundary_distance(xy)[0]) <= tol:
                status = "on_path"
            elif bool(geo.inside(xy)[0]):
                if status == "ok":
                    status = "ambiguous"
                crossings.append(Crossing(object_id=lp.object_id, kind=lp.kind,
                                          point_m=list(map(float, pt)), sign=0,
                                          current_A=lp.current_A, contribution_A=0.0,
                                          state="ambiguous"))
            continue
        dth = math.acos(max(-1.0, min(1.0, ratio)))
        for th in (phi + dth, phi - dth):
            pt = lp.center_m + a * (math.cos(th) * u + math.sin(th) * v)
            tangent = -math.sin(th) * u + math.cos(th) * v  # positive current direction
            classify(lp.object_id, lp.kind, pt, tangent, lp.current_A)

    for tor in cs.ideal_toroids:
        coaxial = (geo.circle_r is not None and abs(abs(float(n @ tor.axis)) - 1) <= 1e-12
                   and float(np.linalg.norm(np.cross(geo.c - tor.center_m, tor.axis))) <= tol)
        if not coaxial:
            status = "unsupported"
            notes.append(L(
                "Ideal toroid: the enclosed current of the continuous winding is implemented for "
                "circular paths coaxial with the toroid only. Use such a path, or the finite-turn "
                "model, whose turns are counted individually.",
                "Ideális toroid: a folytonos tekercselés bezárt árama csak a toroiddal koaxiális "
                "kör alakú utakra van megvalósítva. Használjon ilyen utat, vagy a véges "
                "menetszámú modellt, amelynek meneteit egyenként számoljuk."))
            continue
        assert geo.circle_r is not None
        z = float((geo.c - tor.center_m) @ tor.axis)
        r_core = math.hypot(geo.circle_r - tor.major_radius_m, z)
        if abs(r_core - tor.core_radius_m) <= tol:
            status = "on_path"
            notes.append(L("The path lies on the ideal core surface (one-sided field).",
                           "Az út az ideális mag felületén fut (egyoldali tér)."))
            continue
        if r_core < tor.core_radius_m:
            sgn = 1 if float(n @ tor.axis) > 0 else -1
            crossings.append(Crossing(object_id=tor.object_id, kind="toroid_ideal",
                                      point_m=list(map(float, geo.c)), sign=sgn,
                                      current_A=tor.current_A * tor.turns,
                                      contribution_A=sgn * tor.current_A * tor.turns,
                                      state="inside"))
    if cs.magnets:
        notes.append(L("Permanent magnets carry bound (magnetization) current, which is not free "
                       "current: they contribute nothing to I_free,enclosed.",
                       "Az állandó mágnesek kötött (mágnesezési) áramot hordoznak, amely nem "
                       "szabad áram: az I_szabad,bezárt értékéhez nem járulnak hozzá."))
    available = status == "ok"
    value = float(sum(c.contribution_A for c in crossings)) if available else None
    return Enclosure(available=available, status=status, value_A=value, crossings=crossings,
                     notes=notes)


# --------------------------------------------------------------------------- circulation


def _breakpoints(geo: _Geo, piece: int, cs: CurrentSources) -> list[float]:
    """Parameters in (0, 1) where the piece crosses a magnet surface or the ideal core surface.
    H jumps there (its normal component by M, or the ideal field to 0), so the integration is
    split at these points: each sub-interval then has a smooth integrand. Located by dense
    sampling and 60 bisection steps (to about 1e-18 of the piece)."""
    if not cs.magnets and not cs.ideal_toroids:
        return []
    t = np.linspace(0.0, 1.0, 2049)
    code = ms.region_code(geo.param(piece, t)[0], cs)
    out: list[float] = []
    for i in np.flatnonzero(code[1:] != code[:-1]):
        lo, hi = float(t[i]), float(t[i + 1])
        c_lo = code[i]
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            if ms.region_code(geo.param(piece, np.array([mid]))[0], cs)[0] == c_lo:
                lo = mid
            else:
                hi = mid
        out.append(0.5 * (lo + hi))
    return out


FILAMENT_SAMPLES = 2049  # samples per piece to locate closest approaches to filaments
FILAMENT_NEAR = 0.05  # closest approaches nearer than this × path size are pre-split


def _filament_approaches(geo: _Geo, piece: int, cs: CurrentSources
                         ) -> list[tuple[float, float, float]]:
    """Closest approaches of a piece to the filaments: (t*, distance, coordinate scale) for every
    local minimum of the distance nearer than FILAMENT_NEAR × path size, refined by 80
    golden-section steps (to about 1e-17 of the piece)."""
    if not cs.wires and not cs.loops:
        return []
    t = np.linspace(0.0, 1.0, FILAMENT_SAMPLES)
    d, _ = ms.nearest_filament(geo.param(piece, t)[0], cs)
    near = FILAMENT_NEAR * geo.size()
    out: list[tuple[float, float, float]] = []

    def dist(x: float) -> tuple[float, float]:
        dd, sc = ms.nearest_filament(geo.param(piece, np.array([x]))[0], cs)
        return float(dd[0]), float(sc[0])

    g = (math.sqrt(5.0) - 1.0) / 2.0
    for i in range(len(t)):
        left = d[i - 1] if i > 0 else np.inf
        right = d[i + 1] if i + 1 < len(t) else np.inf
        if not (d[i] <= left and d[i] <= right and d[i] < near):
            continue
        lo, hi = float(t[max(i - 1, 0)]), float(t[min(i + 1, len(t) - 1)])
        x1, x2 = hi - g * (hi - lo), lo + g * (hi - lo)
        f1, f2 = dist(x1)[0], dist(x2)[0]
        for _ in range(80):
            if f1 <= f2:
                hi, x2, f2 = x2, x1, f1
                x1 = hi - g * (hi - lo)
                f1 = dist(x1)[0]
            else:
                lo, x1, f1 = x1, x2, f2
                x2 = lo + g * (hi - lo)
                f2 = dist(x2)[0]
        cands = [(float(t[i]), *dist(float(t[i]))), (0.5 * (lo + hi), *dist(0.5 * (lo + hi)))]
        out.append(min(cands, key=lambda c: c[1]))
    return out


def _graded(t_star: float, d: float, speed: float, lo: float, hi: float) -> list[float]:
    """Breakpoints t* ± (d/speed)·4^j inside (lo, hi): the integrand near a filament at distance
    d varies on the scale d, so every sub-interval is smooth on its own length."""
    out = [t_star] if lo < t_star < hi else []
    step = d / max(speed, 1e-300)
    while step < (hi - lo):
        out += [x for x in (t_star - step, t_star + step) if lo < x < hi]
        step *= 4.0
    return out


def _circulation(geo: _Geo, cs: CurrentSources, r_min: float, i_scale: float,
                 approaches: dict[int, list[tuple[float, float, float]]] | None = None
                 ) -> tuple[float, float, float, bool, int, int, bool]:
    """(Γ_H, error, Γ_B, converged, subintervals, evaluations, crosses material)."""
    item_piece: list[int] = []
    lo: list[float] = []
    hi: list[float] = []
    material = False
    for piece, _ in enumerate(geo.pieces()):
        bps = _breakpoints(geo, piece, cs)
        # Through material: crossing a boundary, or lying wholly inside a magnet or the core.
        material |= bool(bps) or bool(
            np.any(ms.region_code(geo.param(piece, np.array([0.5]))[0], cs)))
        fil: list[float] = []
        found = (approaches[piece] if approaches is not None
                 else _filament_approaches(geo, piece, cs))
        for t_star, d, _ in found:
            speed = float(np.linalg.norm(geo.param(piece, np.array([t_star]))[1][0]))
            fil += _graded(t_star, d, speed, 0.0, 1.0)
        edges = sorted({0.0, *bps, *fil, 1.0})
        for a, b in zip(edges[:-1], edges[1:], strict=True):
            item_piece.append(piece)
            lo.append(a)
            hi.append(b)
    pieces_of = np.asarray(item_piece)

    def f(items: NDArray[np.int64], t: Arr) -> Arr:
        out = np.empty((t.size, 2))
        piece_ids = pieces_of[items]
        for k in np.unique(piece_ids):
            sel = piece_ids == k
            pt, dp = geo.param(int(k), t[sel])
            ev = ms.evaluate_bh(pt, cs, r_min, ms.MAGNET_RTOL["ampere"])
            out[sel, 0] = np.einsum("ij,ij->i", ev.h, dp)
            out[sel, 1] = np.einsum("ij,ij->i", ev.b, dp)
        return out

    rtol = geo.path.rtol
    n = len(lo)
    floor = max(ATOL_A, SCALE_RTOL * i_scale)
    # Pass 1: each piece to rtol/10. If the pieces cancel (|Γ| much smaller than the pieces),
    # their errors can exceed the global tolerance; pass 2 then refines every piece to 1e-10
    # relative (smooth pieces converge exponentially). The global criterion is never relaxed.
    evaluations = 0
    for piece_rtol in (0.1 * rtol, 1e-10):
        res = adaptive_gk(f, np.asarray(lo), np.asarray(hi), 2, piece_rtol, atol=floor / n,
                          max_levels=30)
        evaluations += res.evaluations
        gamma_h = float(res.value[:, 0].sum())
        gamma_b = float(res.value[:, 1].sum())
        err = float(res.error.sum())
        tol = max(rtol * abs(gamma_h), floor)
        finite = math.isfinite(gamma_h) and math.isfinite(err)
        converged = bool(finite and np.all(res.converged) and err <= tol)
        if converged:
            break
    return (gamma_h, err, gamma_b, converged, int(res.intervals.sum()), evaluations, material)


def compute(scene: Scene, request: AmpereRequest, solver_id: str, solver_version: str
            ) -> AmpereHeader:
    cs = current_sources(scene)
    diag = scene.domain.diagonal_m
    r_min = ms.COINCIDENCE_FACTOR * diag
    tol = ms.IN_PLANE_FACTOR * diag
    # Scale for cancellation cases: free ampere-turns plus each magnet's bound sheet current
    # |M| L (the size of the H circulation's pieces near a magnet); 1 A if there is neither.
    i_scale = (cs.free_current_scale_A
               + sum(abs(mg.magnetization_A_per_m) * mg.length_m for mg in cs.magnets)
               ) or REFERENCE_SCALE_A
    results: list[PathResult] = []
    for path in request.paths:
        geo = _Geo(path, tol)
        if geo.reasons:
            results.append(PathResult(path_id=path.id, valid=False, invalid_reasons=geo.reasons,
                                      status="invalid"))
            continue
        poly = geo.polyline()
        size = geo.size()
        dense = geo.polyline(4096) if geo.circle_r is not None else np.vstack([
            geo.param(k, np.linspace(0, 1, 513))[0] for k, _ in enumerate(geo.pieces())])
        dmin = float(ms.distance_to_sources(dense, cs).min()) if cs.loops or cs.wires else None
        # Closest approaches to filaments, refined beyond the sampling (Phase 3B.1); the path
        # intersects a filament only if one is closer than float64 can resolve there.
        approaches = {k: _filament_approaches(geo, k, cs) for k, _ in enumerate(geo.pieces())}
        touches = False
        for found in approaches.values():
            for _, d_star, scale in found:
                dmin = d_star if dmin is None else min(dmin, d_star)
                touches |= d_star <= float(ms.filament_tolerance(np.asarray(scale)))
        enc = enclosed_current(geo, cs)
        base = {"path_id": path.id, "valid": True, "normal": list(map(float, geo.normal)),
                "center_m": list(map(float, geo.c)), "perimeter_m": geo.perimeter(),
                "area_m2": geo.area(), "polyline_m": [list(map(float, p)) for p in poly],
                "min_distance_to_filament_m": dmin, "enclosure": enc}
        base["min_distance_to_filament_m"] = dmin
        if enc.status == "on_path" or touches:
            results.append(PathResult(**base, status="intersects_source"))
            continue
        gh, err, gb, conv, nint, nev, mat = _circulation(geo, cs, r_min, i_scale, approaches)
        near = dmin is not None and dmin < NEAR_FACTOR * size
        tol_a = max(path.rtol * max(abs(gh), abs(enc.value_A or 0.0)), ATOL_A,
                    SCALE_RTOL * i_scale)
        diff = None if enc.value_A is None else gh - enc.value_A
        rel = (abs(diff) / abs(enc.value_A) if diff is not None and enc.value_A
               else None)
        floor_a = (AMPERE_FLOOR_FACTOR * ms.EPS
                   * (float(np.linalg.norm(geo.c)) + geo.size()) / dmin * i_scale
                   if dmin is not None and dmin > 0 else None)
        if not conv or (floor_a is not None and floor_a > tol_a):
            status = "not_converged"
        elif enc.status == "unsupported":
            status = "unsupported"
        elif enc.status == "ambiguous":
            status = "ambiguous"
        elif diff is not None and abs(diff) <= tol_a:
            status = "verified"
        else:
            status = "failed"
        bound = gb / MU0 - (enc.value_A or 0.0) if cs.magnets and enc.value_A is not None \
            else None
        results.append(PathResult(
            **base, status=status, circulation_H_A=gh, circulation_error_A=err,
            circulation_B_T_m=gb, converged=conv, subintervals=nint, evaluations=nev,
            near_singular=near, crosses_material=mat, difference_A=diff, relative_error=rel,
            tolerance_A=tol_a, bound_current_from_B_A=bound, precision_floor_A=floor_a))
    return AmpereHeader(
        solver_id=solver_id, solver_version=solver_version, current_scale_A=i_scale,
        method=L("Γ_H = ∮H·dl by adaptive Gauss–Kronrod (G7/K15) quadrature of H from the "
                 "magnetostatic solver along the exact path; I_free,enclosed from the signed "
                 "crossings of the free-current filaments with the planar spanning surface "
                 "(independent of Γ_H).",
                 "Γ_H = ∮H·dl adaptív Gauss–Kronrod (G7/K15) kvadratúrával, a magnetosztatikus "
                 "megoldó H terével, a pontos út mentén; I_szabad,bezárt a szabad áramszálak és a "
                 "sík kifeszített felület előjeles metszéspontjaiból (Γ_H-tól független)."),
        paths=results)


def fingerprint(scene: Scene, request: AmpereRequest) -> str:
    s = scene.model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
    for m in s["materials"]:
        m.pop("name", None)
    payload = json.dumps({"scene": s, "paths": [p.physics_dump() for p in request.paths]},
                         sort_keys=True, separators=(",", ":"))
    return "ampere:" + hashlib.sha256(payload.encode()).hexdigest()

