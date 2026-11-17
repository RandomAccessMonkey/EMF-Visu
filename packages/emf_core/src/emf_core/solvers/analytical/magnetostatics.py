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
B is undefined. B is undefined (singular) within the position tolerance
COINCIDENCE_FACTOR × domain diagonal of a filament; any other point gets its analytical value.
"""

from __future__ import annotations

import time
from fractions import Fraction

import numpy as np
from numpy.typing import NDArray
from scipy.special import ellipe, ellipkm1

from ...i18n import L, LocalizedText
from ...postprocess import magnetic_lines as ml
from ...sampling import PlaneGridSampling
from ...scene.currents import CurrentSources, LoopSource, WireSource, current_sources
from ...scene.models import GroupPrimitive, MaterialModel, Role, Scene
from ...units import MU0, QUANTITIES
from ..base import (
    ArrayEntry,
    ArrayStats,
    CancelCheck,
    CurrentSourceInfo,
    FieldLineInfo,
    FieldLineSet,
    MethodInfo,
    ModelContext,
    ProgressCallback,
    ResultHeader,
    SimulationResult,
    SolverCancelledError,
    SolveRequest,
    SolverKind,
    Support,
    quantities_for,
)

Arr = NDArray[np.float64]
COINCIDENCE_FACTOR = 1e-12
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


def wire_field(points: Arr, w: WireSource, r_min: float) -> Arr:
    r = points - w.point_m
    rp = r - (r @ w.direction)[:, None] * w.direction
    s2 = np.einsum("ij,ij->i", rp, rp)
    near = np.sqrt(s2) <= r_min
    s2 = np.where(near, 1.0, s2)
    b = (MU0 * w.current_A / (2.0 * np.pi) / s2)[:, None] * np.cross(w.direction, rp)
    b[near] = np.nan
    return b


def loop_local(rho: Arr, z: Arr, a: float, current: float) -> tuple[Arr, Arr, Arr]:
    """(B_rho, B_z, distance to the wire) in local cylindrical coordinates."""
    c = MU0 * current / (2.0 * np.pi)
    dp = (a + rho) ** 2 + z**2
    dm = (a - rho) ** 2 + z**2
    m = 4.0 * a * rho / dp
    p1 = dm / dp  # 1 - m, formed without cancellation
    with np.errstate(divide="ignore", invalid="ignore"):
        k = ellipkm1(p1)
        e = ellipe(m)
        sq = np.sqrt(dp)
        bz = c / sq * (k + (a * a - rho * rho - z * z) / dm * e)
        general = c * z / (rho * sq) * (-k + (a * a + rho * rho + z * z) / dm * e)
        near = c * z / sq * (4.0 * a / dp) * (np.pi / 2.0) * _f_over_m(m) / (2.0 * p1)
    b_rho = np.where(m <= NEAR_AXIS_M, near, general)
    return b_rho, bz, np.sqrt(dm)


def loop_field(points: Arr, lp: LoopSource, r_min: float) -> Arr:
    d = points - lp.center_m
    z = d @ lp.normal
    rvec = d - z[:, None] * lp.normal
    rho = np.linalg.norm(rvec, axis=1)
    b_rho, b_z, dist = loop_local(rho, z, lp.radius_m, lp.current_A)
    with np.errstate(divide="ignore", invalid="ignore"):
        rhat = np.where(rho[:, None] > 0, rvec / rho[:, None], 0.0)
    b = b_rho[:, None] * rhat + b_z[:, None] * lp.normal
    b[dist <= r_min] = np.nan
    return b


def source_fields(points: Arr, cs: CurrentSources, r_min: float) -> list[Arr]:
    """Each source's own B (N, 3), in the order of ``cs.ids``."""
    return ([wire_field(points, w, r_min) for w in cs.wires]
            + [loop_field(points, lp, r_min) for lp in cs.loops])


def evaluate(points: Arr, cs: CurrentSources, r_min: float) -> Arr:
    """Total B [T] (N, 3) by superposition; NaN where any filament makes it singular."""
    b = np.zeros_like(points)
    for bi in source_fields(points, cs, r_min):
        b += bi
    return b


def distance_to_sources(points: Arr, cs: CurrentSources) -> Arr:
    """Distance to the nearest filament (wire axis or loop wire), inf if there is none."""
    out = np.full(points.shape[0], np.inf)
    for w in cs.wires:
        r = points - w.point_m
        rp = r - (r @ w.direction)[:, None] * w.direction
        out = np.minimum(out, np.linalg.norm(rp, axis=1))
    for lp in cs.loops:
        d = points - lp.center_m
        z = d @ lp.normal
        rho = np.linalg.norm(d - z[:, None] * lp.normal, axis=1)
        out = np.minimum(out, np.sqrt((lp.radius_m - rho) ** 2 + z**2))
    return out


def _stats(a: Arr, vector: bool) -> ArrayStats:
    v = np.sqrt(np.einsum("...j,...j->...", a, a)) if vector else a
    finite = np.isfinite(v)
    bad = int(v.size - np.count_nonzero(finite))
    if not finite.any():
        return ArrayStats(min=None, max=None, non_finite_count=bad)
    return ArrayStats(min=float(v[finite].min()), max=float(v[finite].max()), non_finite_count=bad)


def current_source_table(cs: CurrentSources, planes: list[PlaneGridSampling]
                         ) -> list[CurrentSourceInfo]:
    out: list[CurrentSourceInfo] = []
    for w in cs.wires:
        cross: dict[str, list[float] | None] = {}
        sign: dict[str, int] = {}
        for g in planes:
            n = np.cross(np.asarray(g.u_dir, float), np.asarray(g.v_dir, float))
            dn = float(w.direction @ n)
            if abs(dn) <= 1e-9:
                cross[g.id], sign[g.id] = None, 0
            else:
                t = float((np.asarray(g.center_m, float) - w.point_m) @ n) / dn
                cross[g.id] = [float(x) for x in w.point_m + t * w.direction]
                sign[g.id] = 1 if dn * w.current_A > 0 else (-1 if dn * w.current_A < 0 else 0)
        out.append(CurrentSourceInfo(
            object_id=w.object_id, kind="infinite_wire", current_A=w.current_A,
            point_m=[float(x) for x in w.point_m], direction=[float(x) for x in w.direction],
            plane_crossing_m=cross, plane_crossing_sign=sign))
    for lp in cs.loops:
        dist = {g.id: float((lp.center_m - np.asarray(g.center_m, float))
                            @ np.cross(np.asarray(g.u_dir, float), np.asarray(g.v_dir, float)))
                for g in planes}
        out.append(CurrentSourceInfo(
            object_id=lp.object_id, kind="circular_loop", current_A=lp.current_A,
            point_m=[float(x) for x in lp.center_m], direction=[float(x) for x in lp.normal],
            radius_m=lp.radius_m, plane_distance_m=dist))
    return out


_FL_SETTINGS = {
    "preview": {"atol": 1e-4, "h_max": 1 / 24, "max_steps": 500},
    "normal": {"atol": 1e-5, "h_max": 1 / 48, "max_steps": 1500},
    "high": {"atol": 1e-6, "h_max": 1 / 96, "max_steps": 5000},
}
_MAX_LINES = 900


def _perp(d: Arr) -> Arr:
    """A unit vector perpendicular to d."""
    a = np.array([1.0, 0.0, 0.0]) if abs(d[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    v = np.cross(d, a)
    return v / np.linalg.norm(v)


class FilamentMagnetostaticSolver:
    id = "analytical.magnetostatics.filaments"
    version = "1.0.0"
    kind: SolverKind = "analytical"
    field_kinds: tuple[str, ...] = ("magnetic",)
    name = L("Analytical magnetostatics: ideal current filaments in vacuum",
             "Analitikus magnetosztatika: ideális áramszálak vákuumban")

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
                                           Role.CHARGE_SOURCE):
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
        currents = [abs(w.current_A) for w in cs.wires] + [abs(lp.current_A) for lp in cs.loops]
        i_max = max(currents) if currents else 0.0
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
        sources: list[WireSource | LoopSource] = [*cs.wires, *cs.loops]
        for k, (src, cur) in enumerate(zip(sources, currents, strict=True)):
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
                                unseeded.append(src.object_id)
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
                                    unseeded.append(src.object_id)
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
                                    unseeded.append(src.object_id)
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
                                    unseeded.append(src.object_id)
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
                        per_level[level].append((p, cs.ids[k]))
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
        i_sum = sum(abs(w.current_A) for w in cs.wires) + sum(abs(lp.current_A) for lp in cs.loops)
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

        def field_fn(p: Arr) -> Arr:
            return evaluate(p, cs, r_min)

        def dist_fn(p: Arr) -> Arr:
            return distance_to_sources(p, cs)

        infos: list[FieldLineInfo] = []
        chunks: list[Arr] = []
        cursor = 0
        # Seeds closer than this to an already drawn line are skipped (display choice).
        dedupe = 2.0 * ml.CLOSURE_ATOL_FACTOR * settings.atol + 0.25 * guard
        for level, (sd, own) in enumerate(zip(seeds, owners, strict=True)):
            if len(sd) == 0:
                continue
            lines = ml.trace_lines(field_fn, dist_fn, sd, dmin, dmax, settings)
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
        cs = current_sources(scene)
        r_min = COINCIDENCE_FACTOR * scene.domain.diagonal_m
        total = sum(int(np.prod(s.shape)) for s in request.samplings)
        share = 1.0 if request.field_lines is None else 0.5

        def check_cancel() -> None:
            if cancel is not None and cancel():
                raise SolverCancelledError()

        arrays: dict[str, Arr] = {}
        entries: list[ArrayEntry] = []
        masked = 0
        done = 0
        contrib_ok = cs.count <= MAX_CONTRIBUTION_SOURCES
        for s in request.samplings:
            pts = s.points()
            b = np.empty_like(pts)
            for start in range(0, pts.shape[0], _CHUNK):
                check_cancel()
                sl = slice(start, start + _CHUNK)
                b[sl] = evaluate(pts[sl], cs, r_min)
                done += pts[sl].shape[0]
                if progress is not None:
                    progress(share * done / max(total, 1), s.id)
            defined = np.all(np.isfinite(b), axis=1)
            masked += int(np.count_nonzero(~defined))
            div = np.where(defined, 0.0, np.nan)
            data_by_q = {"B": b, "H": b / MU0, "div_B": div, "div_H": div / MU0}
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
                for oid, bi in zip(cs.ids, source_fields(pts, cs, r_min), strict=True):
                    for qty, data in (("B", bi), ("H", bi / MU0)):
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
              "wires and thin circular loops.",
              "Stacionárius (egyen-) áramok nulla vastagságú ideális áramszálakban: végtelen "
              "hosszú egyenes vezetők és vékony körvezetők."),
            L("Unbounded vacuum: B = μ₀H everywhere; no magnetic materials, conductors or "
              "boundaries.",
              "Végtelen kiterjedésű vákuum: mindenütt B = μ₀H; nincsenek mágneses anyagok, "
              "vezetők vagy peremek."),
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
        warnings: list[LocalizedText] = []
        if excluded:
            warnings.append(L(
                f"{len(excluded)} inert geometry object(s) are drawn but are not part of the "
                "physical model.",
                f"{len(excluded)} inert geometriai objektum látható, de nem része a fizikai "
                "modellnek."))
        if masked:
            warnings.append(L(
                f"{masked} sample point(s) lie on an ideal current filament, where B and H are "
                "singular; they are reported as undefined.",
                f"{masked} mintavételi pont ideális áramszálra esik, ahol B és H szinguláris; "
                "ezek értéke nem értelmezett."))
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
        kinds = (["circular_loop"] if cs.loops else []) + (["infinite_wire"] if cs.wires else [])
        currents = [w.current_A for w in cs.wires] + [lp.current_A for lp in cs.loops]
        evaluated = ["superposition_magnetic", "b_mu0_h", "h_from_b", "div_B_filaments"]
        if cs.wires:
            evaluated.append("infinite_wire_field")
        if cs.loops:
            evaluated += ["loop_field_elliptic", "loop_axis_field"]
        header = ResultHeader(
            solver_id=self.id, solver_version=self.version, solver_kind=self.kind,
            classification="exact_analytical",
            classification_note=L(
                "Exact analytical solution (closed-form Biot–Savart solutions: straight wire, "
                "and circular loop with complete elliptic integrals) of an idealized filament "
                "model, evaluated in 64-bit floating point and transported as 32-bit.",
                "Idealizált áramszál-modell egzakt analitikus megoldása (a Biot–Savart-törvény "
                "zárt alakú megoldásai: egyenes vezető, valamint körvezető teljes elliptikus "
                "integrálokkal), 64 bites lebegőpontos számítással, 32 bites átvitellel."),
            assumptions=assumptions, warnings=warnings, excluded_object_ids=excluded,
            model_context=ModelContext(
                regime="magnetostatic", dimensionality="3d", medium="vacuum",
                has_free_current=any(c != 0.0 for c in currents),
                computes_magnetic_field=True, solver_id=self.id,
                source_count=sum(c != 0.0 for c in currents), current_source_kinds=kinds,
                evaluated_equation_ids=evaluated),
            samplings=[s.model_dump(mode="json", exclude={"points_m"}) for s in request.samplings],
            quality=request.quality, compute_time_ms=(time.perf_counter() - t0) * 1e3,
            current_sources=current_source_table(
                cs, [g for g in request.samplings if isinstance(g, PlaneGridSampling)]),
            in_plane_tolerance_m=IN_PLANE_FACTOR * scene.domain.diagonal_m,
            field_lines=field_lines, arrays=entries)
        return SimulationResult(header=header, arrays=arrays)

