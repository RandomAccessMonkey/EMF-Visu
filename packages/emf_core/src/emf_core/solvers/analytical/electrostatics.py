"""Exact electrostatic field of ideal point charges in unbounded vacuum.

Model (equation registry ids ``coulomb_field`` and ``coulomb_potential``):

    E(r)   = 1/(4 pi eps0) * sum_i q_i (r - r_i) / |r - r_i|^3      [V/m]
    phi(r) = 1/(4 pi eps0) * sum_i q_i / |r - r_i|                  [V], phi(infinity) = 0
    D(r)   = eps0 E(r)                                              [C/m^2] (vacuum)

The sums are evaluated directly in float64; nothing is discretized, so the result is exact up
to floating-point rounding.

Singularity versus safeguards
-----------------------------
* Mathematical singularity: E and phi are undefined *at* a charge position. A sample point is
  treated as coinciding with a charge only within the floating-point position tolerance
  ``COINCIDENCE_FACTOR * domain diagonal`` (1e-12 of the domain size, i.e. a few ulps of the
  coordinates). Such samples are returned as NaN and counted. Any other point, however close,
  gets its true (possibly very large) analytical value.
* Divergence and curl (Phase 2B-1). Every Coulomb term K q_i (r - r_i)/|r - r_i|^3 has a
  symmetric, traceless Jacobian K q_i (I - 3 n n^T)/|r - r_i|^3 at every r != r_i, so its
  pointwise divergence and curl are exactly zero there (an analytical identity, not a rounded
  computation). The solver therefore returns exact 0 for div/curl of E and D wherever E is
  defined, and "not evaluated" (NaN) exactly where E is undefined. The charges themselves enter
  only as distributional sources: div E = sum_i (q_i/eps0) delta3(r - r_i), reported with their
  exact weights in ``ResultHeader.point_sources``; the distributional curl is zero everywhere.
* Numerical / drawing safeguards (guard radius for field-line seeding and capture, masked
  contour cells) are derived from the sampling resolution in ``postprocess`` and never change a
  field value.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from ...i18n import L, LocalizedText
from ...postprocess import field_lines as fl
from ...postprocess import isolines as iso
from ...sampling import PlaneGridSampling
from ...scene.models import (
    GroupPrimitive,
    MaterialModel,
    PointChargeSource,
    PointPrimitive,
    Role,
    Scene,
)
from ...scene.transforms import world_position
from ...units import COULOMB_K, EPS0, QUANTITIES
from ..base import (
    ArrayEntry,
    ArrayStats,
    CancelCheck,
    EquipotentialSet,
    FieldLineInfo,
    FieldLineSet,
    IsosurfaceSet,
    LevelRange,
    MethodInfo,
    ModelContext,
    PointSourceInfo,
    ProgressCallback,
    ResultHeader,
    SimulationResult,
    SolverCancelledError,
    SolveRequest,
    SolverKind,
    Support,
    quantities_for,
)

COINCIDENCE_FACTOR = 1e-12
# A charge counts as lying in a sampling plane if |distance| <= IN_PLANE_FACTOR * domain diagonal.
IN_PLANE_FACTOR = 1e-9
_CHUNK = 100_000


def _enabled(scene: Scene, object_id: str) -> bool:
    """An object contributes only if it and all of its ancestors are enabled."""
    by_id = {o.id: o for o in scene.objects}
    cur = by_id[object_id]
    while True:
        if not cur.enabled:
            return False
        if cur.parent_id is None:
            return True
        cur = by_id[cur.parent_id]


def point_charge_table(scene: Scene) -> tuple[list[str], NDArray[np.float64], NDArray[np.float64]]:
    """Ids, world positions (n, 3) [m] and charges (n,) [C] of all enabled point charges."""
    ids: list[str] = []
    pos: list[NDArray[np.float64]] = []
    q: list[float] = []
    for o in scene.objects:
        if (o.role is Role.CHARGE_SOURCE and isinstance(o.source, PointChargeSource)
                and _enabled(scene, o.id)):
            ids.append(o.id)
            pos.append(world_position(scene, o))
            q.append(o.source.charge_C)
    return ids, np.asarray(pos, np.float64).reshape(-1, 3), np.asarray(q, np.float64)


def point_charges(scene: Scene) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """World positions (n, 3) [m] and charges (n,) [C] of all enabled point-charge sources."""
    _, pos, q = point_charge_table(scene)
    return pos, q


def contributions(
    points: NDArray[np.float64],
    positions: NDArray[np.float64],
    charges: NDArray[np.float64],
    r_min: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Individual Coulomb contributions: E_i with shape (n, N, 3) and phi_i with shape (n, N).

    The total field is their sum (superposition); ``evaluate`` computes the same sum directly."""
    d = points[None, :, :] - positions[:, None, :]
    r = np.sqrt(np.einsum("nij,nij->ni", d, d))
    near = r <= r_min
    r_safe = np.where(near, 1.0, r)
    phi = COULOMB_K * charges[:, None] / r_safe
    e = (COULOMB_K * charges[:, None] / r_safe**3)[:, :, None] * d
    phi[near] = np.nan
    e[near] = np.nan
    return e, phi


def evaluate(
    points: NDArray[np.float64],
    positions: NDArray[np.float64],
    charges: NDArray[np.float64],
    r_min: float,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return (E [V/m] shape (N, 3), phi [V] shape (N,)). Singular points become NaN."""
    e = np.zeros_like(points)
    phi = np.zeros(points.shape[0])
    singular = np.zeros(points.shape[0], dtype=bool)
    for ri, qi in zip(positions, charges, strict=True):
        d = points - ri
        r = np.sqrt(np.einsum("ij,ij->i", d, d))
        near = r <= r_min
        singular |= near
        r_safe = np.where(near, 1.0, r)
        phi += qi / r_safe
        e += (qi / r_safe**3)[:, None] * d
    e *= COULOMB_K
    phi *= COULOMB_K
    e[singular] = np.nan
    phi[singular] = np.nan
    return e, phi


def exact_div_curl(e: NDArray[np.float64]) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Pointwise divergence (N,) and curl (N, 3) of a superposition of Coulomb fields, given the
    field values (N, 3) returned by ``evaluate``.

    Exact analytical result: zero wherever the field is defined (see the module docstring); not
    evaluated (NaN) at samples that coincide with a charge, where E itself is undefined. Units are
    those of the field per metre. The same identities hold for D = eps0 E in vacuum."""
    defined = np.all(np.isfinite(e), axis=1)
    div = np.where(defined, 0.0, np.nan)
    curl = np.where(defined[:, None], 0.0, np.nan) * np.ones((1, 3))
    return div, curl


def point_source_table(scene: Scene, planes: list[PlaneGridSampling]) -> list[PointSourceInfo]:
    """The distributional sources of div E and div D, with their positions relative to every
    sampling plane."""
    ids, positions, charges = point_charge_table(scene)
    tol = IN_PLANE_FACTOR * scene.domain.diagonal_m
    out: list[PointSourceInfo] = []
    for oid, pos, q in zip(ids, positions, charges, strict=True):
        if q == 0.0:
            continue  # a zero charge is no source
        dist: dict[str, float] = {}
        inside: dict[str, bool] = {}
        for g in planes:
            n = np.cross(np.asarray(g.u_dir, float), np.asarray(g.v_dir, float))
            d = float((pos - np.asarray(g.center_m, float)) @ n)
            dist[g.id] = d
            inside[g.id] = abs(d) <= tol
        out.append(PointSourceInfo(
            object_id=oid, position_m=[float(x) for x in pos], charge_C=float(q),
            div_E_weight_V_m=float(q / EPS0), div_D_weight_C=float(q),
            plane_distance_m=dist, in_plane=inside,
        ))
    return out


def enclosed_source_weight(sources: list[PointSourceInfo],
                           contains: Callable[[NDArray[np.float64]], bool],
                           quantity: Literal["E", "D"] = "E") -> float:
    """Integral of div E (or div D) over a volume: the sum of the delta weights of the sources
    inside it, i.e. Q_enclosed / eps0 (or Q_enclosed). ``contains`` decides membership; a charge
    exactly on the boundary is a matter of convention and must be avoided by the caller."""
    total = 0.0
    for src in sources:
        if contains(np.asarray(src.position_m, float)):
            total += src.div_E_weight_V_m if quantity == "E" else src.div_D_weight_C
    return total


def _stats(a: NDArray[np.float64], vector: bool) -> ArrayStats:
    v = np.sqrt(np.einsum("...j,...j->...", a, a)) if vector else a
    finite = np.isfinite(v)
    bad = int(v.size - np.count_nonzero(finite))
    if not finite.any():
        return ArrayStats(min=None, max=None, non_finite_count=bad)
    return ArrayStats(min=float(v[finite].min()), max=float(v[finite].max()), non_finite_count=bad)


def _singular_sign(points: NDArray[np.float64], phi: NDArray[np.float64],
                   positions: NDArray[np.float64],
                   charges: NDArray[np.float64]) -> NDArray[np.float64]:
    """+1 / −1 at samples that coincide with a positive / negative charge (phi -> ±infinity
    there), 0 elsewhere. Used so that level sets are traced correctly around such a sample."""
    sign = np.zeros(phi.shape)
    bad = np.flatnonzero(~np.isfinite(phi))
    for k in bad:
        d = np.linalg.norm(positions - points[k], axis=1)
        sign[k] = np.sign(charges[int(d.argmin())])
    return sign


def _geometry_entry(name: str, group: str, data: NDArray[np.float64], unit: str = "m",
                    quantity: str = "position") -> ArrayEntry:
    return ArrayEntry(name=name, sampling_id=group, quantity=quantity, symbol="r", unit=unit,
                      components=3, kind="geometry", stats=_stats(data, True))


def auto_levels(charges: NDArray[np.float64], length: float,
                exponents: tuple[int, ...]) -> list[float]:
    """Geometric ladder of potential levels: V_ref * 2**j with V_ref = K * sum|q| / length, for
    each sign of charge present, plus 0 V when both signs are present. Sorted ascending.

    Choosing levels is a display decision; it does not affect any field value."""
    total = float(np.abs(charges).sum())
    if total == 0.0 or length <= 0.0:
        return []
    v_ref = COULOMB_K * total / length
    levels: list[float] = []
    if np.any(charges < 0):
        levels += [-v_ref * 2.0**j for j in exponents]
    if np.any(charges > 0) and np.any(charges < 0):
        levels.append(0.0)
    if np.any(charges > 0):
        levels += [v_ref * 2.0**j for j in exponents]
    return sorted(levels)


# Field-line integration settings per quality level (lengths relative to the domain diagonal).
_FL_SETTINGS = {
    "preview": {"atol": 1e-4, "h_max": 1 / 24, "max_steps": 400},
    "normal": {"atol": 1e-5, "h_max": 1 / 48, "max_steps": 1200},
    "high": {"atol": 1e-6, "h_max": 1 / 96, "max_steps": 4000},
}
CONTOUR_EXPONENTS = tuple(range(-3, 8))
ISOSURFACE_EXPONENTS = (2, 3, 4)
_MAX_LINES = 1500


class PointChargeVacuumSolver:
    id = "analytical.electrostatics.point_charges"
    version = "1.1.0"
    kind: SolverKind = "analytical"

    def supports(self, scene: Scene, request: SolveRequest) -> Support:
        reasons: list[LocalizedText] = []
        if scene.dimensionality != "3d":
            reasons.append(L(
                f"Dimensionality '{scene.dimensionality}' is not implemented; only the full 3D "
                "model is available.",
                f"A(z) '{scene.dimensionality}' dimenziójú modell nincs megvalósítva; csak a "
                "teljes 3D modell érhető el.",
            ))
        bg = scene.material(scene.domain.background_material_id)
        if bg.model is not MaterialModel.VACUUM:
            reasons.append(L(
                "The background medium must be vacuum for this analytical model.",
                "Ennél az analitikus modellnél a háttérközegnek vákuumnak kell lennie.",
            ))
        if scene.boundaries:
            reasons.append(L(
                "Boundary conditions (grounding, fixed potentials, conductors) require a "
                "boundary-value solver, which is not available yet.",
                "A peremfeltételek (földelés, rögzített potenciál, vezetők) peremérték-megoldót "
                "igényelnek, amely még nem érhető el.",
            ))
        for o in scene.objects:
            if not o.enabled or o.role is Role.GEOMETRY_ONLY:
                continue
            label = o.name or o.id
            if o.role is not Role.CHARGE_SOURCE:
                reasons.append(L(
                    f"Object '{label}' has role '{o.role.value}', which no available solver "
                    "supports yet. It is not approximated by a simpler model.",
                    f"A(z) '{label}' objektum szerepe '{o.role.value}', amelyet még egyetlen "
                    "elérhető megoldó sem támogat. Egyszerűbb modellel nem helyettesítjük.",
                ))
            elif not isinstance(o.primitive, PointPrimitive) or o.source is None:
                reasons.append(L(
                    f"Object '{label}' is a charge source that is not an ideal point charge; "
                    "extended charge distributions are not supported yet.",
                    f"A(z) '{label}' objektum töltésforrás, de nem ideális ponttöltés; a "
                    "kiterjedt töltéseloszlások még nem támogatottak.",
                ))
        return Support(supported=not reasons, reasons=reasons)

    # ------------------------------------------------------------------ derived products

    def _field_lines(self, scene: Scene, request: SolveRequest, ids: list[str],
                     positions: NDArray[np.float64], charges: NDArray[np.float64], r_min: float,
                     arrays: dict[str, NDArray[np.float64]],
                     entries: list[ArrayEntry]) -> FieldLineSet:
        req = request.field_lines
        assert req is not None
        ref = next(s for s in request.samplings if s.id == req.sampling_id)
        assert ref.kind != "points"
        diag = scene.domain.diagonal_m
        guard = req.guard_cells * ref.cell_m
        cfg = _FL_SETTINGS[request.quality]
        total_q = float(np.abs(charges).sum())
        settings = fl.TraceSettings(
            atol=cfg["atol"] * diag, h_max=cfg["h_max"] * diag, h_min=1e-12 * diag,
            max_length=6.0 * diag, max_steps=int(cfg["max_steps"]), guard_radius=guard,
            stagnation_E=1e-9 * COULOMB_K * total_q / diag**2,
        )
        sources = fl.PointSources(positions=positions, strengths=charges,
                                  coulomb_constant=COULOMB_K)

        def field_fn(p: NDArray[np.float64]) -> NDArray[np.float64]:
            return evaluate(p, positions, charges, r_min)[0]

        dmin, dmax = np.asarray(scene.domain.min_m), np.asarray(scene.domain.max_m)
        active = np.flatnonzero(charges != 0.0)
        inside = np.array([bool(np.all(positions[i] >= dmin) and np.all(positions[i] <= dmax))
                           for i in range(len(ids))], dtype=bool)
        seedable = np.zeros(len(ids), bool)
        seedable[active] = inside[active]
        stay_in_plane: bool | None = None
        u = v = None
        if req.seeding == "planar":
            assert isinstance(ref, PlaneGridSampling)
            u, v = np.asarray(ref.u_dir, float), np.asarray(ref.v_dir, float)
            normal = np.cross(u, v)
            off = np.abs((positions - np.asarray(ref.center_m)) @ normal)
            in_plane = off <= IN_PLANE_FACTOR * diag
            stay_in_plane = bool(np.all(in_plane[active])) if active.size else True
            seedable &= in_plane
        radii = fl.seed_radii(field_fn, sources, guard)
        q_max = float(np.abs(charges[seedable]).max()) if seedable.any() else 0.0
        base = req.base_lines if req.seeding == "planar" else int(round(req.base_lines * 1.5))
        # Keep the total line count bounded for scenes with many charges.
        est = sum(max(1, round(base * abs(charges[i]) / q_max)) for i in np.flatnonzero(seedable)
                  ) * (2**req.levels - 1) if q_max > 0 else 0
        if est > _MAX_LINES:
            base = max(1, int(base * _MAX_LINES / est))

        infos: list[FieldLineInfo] = []
        chunks: list[NDArray[np.float64]] = []
        cursor = 0
        for level in range(req.levels):
            seeds: dict[float, list[NDArray[np.float64]]] = {1.0: [], -1.0: []}
            owner: dict[float, list[int]] = {1.0: [], -1.0: []}
            for i in np.flatnonzero(seedable):
                n = max(1, round(base * 2**level * abs(charges[i]) / q_max))
                dirs = fl.circle(n, u, v) if u is not None and v is not None else \
                    fl.fibonacci_sphere(n)
                sign = 1.0 if charges[i] > 0 else -1.0
                seeds[sign].append(positions[i] + radii[i] * dirs)
                owner[sign] += [int(i)] * n
            for sign in (1.0, -1.0):
                if not seeds[sign]:
                    continue
                traces = fl.trace(field_fn, np.concatenate(seeds[sign]), sign, sources, dmin,
                                  dmax, settings)
                for tr, own in zip(traces, owner[sign], strict=True):
                    if sign < 0 and tr.reason == "positive_charge":
                        continue  # the same line is already traced forward from that charge
                    # Prepend the source itself: the radial limit inside the seed radius.
                    pts = np.vstack([positions[own], tr.points])
                    end_id = ids[tr.source_index] if tr.source_index is not None else None
                    if sign > 0:
                        info = FieldLineInfo(start=cursor, count=len(pts), level=level,
                                             start_reason="positive_charge", end_reason=tr.reason,
                                             start_object_id=ids[own], end_object_id=end_id,
                                             steps=tr.steps)
                    else:  # traced against E from a negative charge: store it along +E
                        pts = pts[::-1]
                        info = FieldLineInfo(start=cursor, count=len(pts), level=level,
                                             start_reason=tr.reason, end_reason="negative_charge",
                                             start_object_id=end_id, end_object_id=ids[own],
                                             steps=tr.steps)
                    infos.append(info)
                    chunks.append(pts)
                    cursor += len(pts)
        points = np.concatenate(chunks) if chunks else np.empty((0, 3))
        name = "field_lines.points"
        arrays[name] = points
        entries.append(_geometry_entry(name, "field_lines", points))
        counts: dict[str, int] = {}
        for info in infos:
            for reason in (info.start_reason, info.end_reason):
                counts[reason] = counts.get(reason, 0) + 1
        return FieldLineSet(
            array=name, seeding=req.seeding, levels=req.levels, guard_radius_m=guard,
            lines_stay_in_plane=stay_in_plane,
            unseeded_object_ids=[ids[i] for i in active if not seedable[i]],
            lines=infos, end_reason_counts=counts, field_classification="exact_analytical",
            method=MethodInfo(
                kind="numerical_integration",
                name=L("Adaptive Dormand–Prince RK5(4) integration of dr/ds = E/|E|",
                       "A dr/ds = E/|E| egyenlet adaptív Dormand–Prince RK5(4) integrálása"),
                description=L(
                    "Field lines are numerical integral curves of the exact analytical field. "
                    "The field itself stays exact; only the path of each line carries an "
                    "integration error bounded per step by the tolerance below.",
                    "Az erővonalak az egzakt analitikus mező numerikusan integrált görbéi. Maga a "
                    "mező egzakt marad; csak az egyes vonalak pályája hordoz integrálási hibát, "
                    "amelyet lépésenként az alábbi tolerancia korlátoz."),
                parameters={
                    "local_error_tolerance_m": settings.atol, "max_step_m": settings.h_max,
                    "min_step_m": settings.h_min, "max_length_m": settings.max_length,
                    "max_steps": settings.max_steps, "guard_radius_m": guard,
                    "min_seed_radius_m": float(radii[seedable].min()) if seedable.any() else guard,
                    "stagnation_threshold_V_per_m": settings.stagnation_E,
                    "lines_of_strongest_charge_level_0": base,
                },
                limitations=[
                    L("Line density indicates field strength only for spherical (3D) seeding, "
                      "and only approximately: line counts are rounded and seeds are uniform on "
                      "a small sphere around each charge. In a planar cross-section, line "
                      "density does not represent |E|.",
                      "A vonalsűrűség csak gömbi (3D) indítás esetén, és ott is csak közelítőleg "
                      "jelzi a térerősséget: a vonalszámok kerekítettek, az indítópontok pedig "
                      "egyenletesen helyezkednek el a töltés körüli kis gömbön. Síkmetszetben a "
                      "vonalsűrűség nem jellemzi |E| nagyságát."),
                    L("Inside the guard radius around a charge a line is drawn as a straight "
                      "radial segment. This is a drawing safeguard; it does not change the field.",
                      "A töltés körüli védősugáron belül a vonal egyenes, sugárirányú szakaszként "
                      "jelenik meg. Ez rajzolási óvintézkedés; a mezőt nem változtatja meg."),
                    L("Lines that reach the edge of the region of interest end there, although "
                      "the physical line continues (to infinity, or back into the region).",
                      "A vizsgált tartomány szélét elérő vonalak ott véget érnek, noha a fizikai "
                      "erővonal folytatódik (a végtelenbe, vagy vissza a tartományba)."),
                    L("Lines ending with 'maximum length' or 'integration failure' are numerical "
                      "outcomes, not physical endings.",
                      "A „maximális hossz” vagy „integrálási hiba” miatt véget érő vonalak "
                      "numerikus eredmények, nem fizikai végpontok."),
                ],
            ),
        )

    def _equipotentials(self, scene: Scene, request: SolveRequest,
                        positions: NDArray[np.float64], charges: NDArray[np.float64], r_min: float,
                        phi_by_sampling: dict[str, NDArray[np.float64]],
                        arrays: dict[str, NDArray[np.float64]],
                        entries: list[ArrayEntry]) -> EquipotentialSet:
        req = request.equipotentials
        assert req is not None
        grid = next(s for s in request.samplings if s.id == req.sampling_id)
        assert isinstance(grid, PlaneGridSampling)
        pts = grid.points().reshape(grid.nv, grid.nu, 3)
        phi = phi_by_sampling[grid.id].reshape(grid.nv, grid.nu)
        sing = _singular_sign(pts.reshape(-1, 3), phi.ravel(), positions, charges
                              ).reshape(phi.shape)
        diag = scene.domain.diagonal_m
        levels = sorted(req.levels_V) if req.levels_V is not None else \
            auto_levels(charges, diag, CONTOUR_EXPONENTS)
        scale = COULOMB_K * float(np.abs(charges).sum()) / diag if charges.size else 1.0

        def phi_fn(p: NDArray[np.float64]) -> NDArray[np.float64]:
            return evaluate(p, positions, charges, r_min)[1]

        ranges: list[LevelRange] = []
        chunks: list[NDArray[np.float64]] = []
        cursor = 0
        for lv in levels:
            seg = iso.contour_segments(phi, pts, lv, phi_fn, max(abs(lv), scale * 1e-3),
                                       singular_sign=sing)
            seg = seg[np.all(np.isfinite(seg), axis=(1, 2))]
            ranges.append(LevelRange(value_V=lv, start=cursor, count=len(seg)))
            chunks.append(seg)
            cursor += len(seg)
        segments = np.concatenate(chunks) if chunks else np.empty((0, 2, 3))
        name = "equipotentials.segments"
        arrays[name] = segments
        entries.append(_geometry_entry(name, "equipotentials", segments.reshape(-1, 3)))
        return EquipotentialSet(
            array=name, sampling_id=grid.id, levels=ranges,
            field_classification="exact_analytical",
            method=MethodInfo(
                kind="numerical_extraction",
                name=L("Marching squares with exact vertex refinement",
                       "Marching squares eljárás egzakt csúcspont-finomítással"),
                description=L(
                    "Contour lines are extracted from potential samples of the exact analytical "
                    "solution. Every contour vertex is refined on its grid edge until the exact "
                    "potential matches the level; between vertices the curve is replaced by "
                    "straight segments.",
                    "A szintvonalak az egzakt analitikus megoldás potenciálmintáiból készülnek. "
                    "Minden csúcspont a rácsélen addig finomodik, amíg az egzakt potenciál meg "
                    "nem egyezik a szinttel; a csúcsok között a görbét egyenes szakaszok "
                    "helyettesítik."),
                parameters={"grid_nu": grid.nu, "grid_nv": grid.nv, "cell_m": grid.cell_m,
                            "vertex_relative_tolerance": iso.VERTEX_RTOL,
                            "levels": len(levels)},
                limitations=[
                    L("Segment chords deviate from the true curve by about cell² × curvature / 8.",
                      "A szakaszok húrjai kb. cella² × görbület / 8 mértékben térnek el a valódi "
                      "görbétől."),
                    L("Contour loops smaller than a grid cell are not drawn.",
                      "A rácscellánál kisebb szintvonalhurkok nem jelennek meg."),
                    L("The levels shown are a display choice (a geometric ladder); equal spacing "
                      "in potential is not implied.",
                      "A megjelenített szintek megjelenítési választás eredményei (mértani "
                      "sorozat); nem jelentenek egyenlő potenciálközöket."),
                ],
            ),
        )

    def _isosurfaces(self, scene: Scene, request: SolveRequest,
                     positions: NDArray[np.float64], charges: NDArray[np.float64], r_min: float,
                     arrays: dict[str, NDArray[np.float64]],
                     entries: list[ArrayEntry]) -> IsosurfaceSet:
        req = request.isosurfaces
        assert req is not None
        lat = req.lattice
        pts = lat.points()
        phi = evaluate(pts, positions, charges, r_min)[1].reshape(lat.shape)
        grid_pts = pts.reshape(*lat.shape, 3)
        sing = _singular_sign(pts, phi.ravel(), positions, charges).reshape(phi.shape)
        diag = scene.domain.diagonal_m
        levels = sorted(req.levels_V) if req.levels_V is not None else \
            auto_levels(charges, diag, ISOSURFACE_EXPONENTS)
        scale = COULOMB_K * float(np.abs(charges).sum()) / diag if charges.size else 1.0

        def phi_fn(p: NDArray[np.float64]) -> NDArray[np.float64]:
            return evaluate(p, positions, charges, r_min)[1]

        ranges: list[LevelRange] = []
        chunks: list[NDArray[np.float64]] = []
        cursor = 0
        for lv in levels:
            tri = iso.isosurface_triangles(phi, grid_pts, lv, phi_fn,
                                           max(abs(lv), scale * 1e-3), singular_sign=sing)
            tri = tri[np.all(np.isfinite(tri), axis=(1, 2))]
            ranges.append(LevelRange(value_V=lv, start=cursor, count=len(tri)))
            chunks.append(tri)
            cursor += len(tri)
        triangles = np.concatenate(chunks) if chunks else np.empty((0, 3, 3))
        e = evaluate(triangles.reshape(-1, 3), positions, charges, r_min)[0]
        mag = np.sqrt(np.einsum("ij,ij->i", e, e))
        with np.errstate(invalid="ignore", divide="ignore"):
            normals = np.where(mag[:, None] > 0, e / mag[:, None], 0.0).reshape(-1, 3, 3)
        normals = np.nan_to_num(normals)
        name, nname = "isosurfaces.triangles", "isosurfaces.normals"
        arrays[name], arrays[nname] = triangles, normals
        entries.append(_geometry_entry(name, "isosurfaces", triangles.reshape(-1, 3)))
        entries.append(_geometry_entry(nname, "isosurfaces", normals.reshape(-1, 3), unit="1",
                                       quantity="direction"))
        return IsosurfaceSet(
            array=name, normals_array=nname,
            lattice=lat.model_dump(mode="json"), levels=ranges,
            field_classification="exact_analytical",
            method=MethodInfo(
                kind="numerical_extraction",
                name=L("Marching tetrahedra with exact vertex refinement",
                       "Marching tetrahedra eljárás egzakt csúcspont-finomítással"),
                description=L(
                    "Equipotential surfaces are extracted from potential samples of the exact "
                    "analytical solution on a lattice. Every vertex is refined on its lattice "
                    "edge until the exact potential matches the level; the surface between "
                    "vertices is made of flat triangles. Shading normals are the exact field "
                    "direction E/|E|.",
                    "Az ekvipotenciális felületek az egzakt analitikus megoldás rácson vett "
                    "potenciálmintáiból készülnek. Minden csúcspont a rácsélen addig finomodik, "
                    "amíg az egzakt potenciál meg nem egyezik a szinttel; a csúcsok közötti "
                    "felület sík háromszögekből áll. Az árnyalási normálisok az egzakt E/|E| "
                    "térirányt követik."),
                parameters={"lattice_nx": lat.nx, "lattice_ny": lat.ny, "lattice_nz": lat.nz,
                            "cell_m": lat.cell_m, "vertex_relative_tolerance": iso.VERTEX_RTOL,
                            "levels": len(levels)},
                limitations=[
                    L("Flat triangles deviate from the true surface by about cell² × curvature / "
                      "8; closed surfaces smaller than a lattice cell are missed.",
                      "A sík háromszögek kb. cella² × görbület / 8 mértékben térnek el a valódi "
                      "felülettől; a rácscellánál kisebb zárt felületek kimaradnak."),
                    L("Surfaces are cut off at the edge of the region of interest.",
                      "A felületek a vizsgált tartomány szélén le vannak vágva."),
                    L("Only a few levels are shown; they are a display choice.",
                      "Csak néhány szint jelenik meg; ezek megjelenítési választás eredményei."),
                ],
            ),
        )

    # ------------------------------------------------------------------------------ solve

    def solve(
        self,
        scene: Scene,
        request: SolveRequest,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> SimulationResult:
        t0 = time.perf_counter()
        ids, positions, charges = point_charge_table(scene)
        r_min = COINCIDENCE_FACTOR * scene.domain.diagonal_m
        extras = sum(x is not None for x in
                     (request.field_lines, request.equipotentials, request.isosurfaces))
        total = sum(int(np.prod(s.shape)) for s in request.samplings)
        sampling_share = 1.0 if extras == 0 else 0.6

        def check_cancel() -> None:
            if cancel is not None and cancel():
                raise SolverCancelledError()

        done = 0
        arrays: dict[str, NDArray[np.float64]] = {}
        entries: list[ArrayEntry] = []
        phi_by_sampling: dict[str, NDArray[np.float64]] = {}
        masked = 0
        for s in request.samplings:
            pts = s.points()
            e = np.empty_like(pts)
            phi = np.empty(pts.shape[0])
            for start in range(0, pts.shape[0], _CHUNK):
                check_cancel()
                sl = slice(start, start + _CHUNK)
                e[sl], phi[sl] = evaluate(pts[sl], positions, charges, r_min)
                done += pts[sl].shape[0]
                if progress is not None:
                    progress(sampling_share * done / total, s.id)
            masked += int(np.count_nonzero(np.isnan(phi)))
            phi_by_sampling[s.id] = phi
            wanted = quantities_for(request, s)
            div = curl = None
            if any(q in wanted for q in ("div_E", "curl_E", "div_D", "curl_D")):
                div, curl = exact_div_curl(e)
            for qty in wanted:
                if qty in ("E", "phi", "D"):
                    data = {"E": e, "phi": phi, "D": EPS0 * e}[qty]
                else:
                    assert div is not None and curl is not None
                    # D = eps0 E in vacuum: the same exact zeros, in C/m^3 instead of V/m^2.
                    data = {"div_E": div, "curl_E": curl, "div_D": EPS0 * div,
                            "curl_D": EPS0 * curl}[qty]
                info = QUANTITIES[qty]
                name = f"{s.id}.{qty}"
                shape = (*s.shape, 3) if info.rank == 1 else s.shape
                arrays[name] = data.reshape(shape)
                entries.append(ArrayEntry(
                    name=name, sampling_id=s.id, quantity=qty, symbol=info.symbol, unit=info.unit,
                    components=3 if info.rank == 1 else 1, stats=_stats(data, info.rank == 1),
                ))

        field_lines = equipotentials = isosurfaces = None
        step = 0

        def stage(label: str) -> None:
            nonlocal step
            check_cancel()
            if progress is not None:
                progress(sampling_share + (1 - sampling_share) * step / max(extras, 1), label)
            step += 1

        if request.equipotentials is not None:
            stage("equipotentials")
            equipotentials = self._equipotentials(scene, request, positions, charges, r_min,
                                                  phi_by_sampling, arrays, entries)
        if request.field_lines is not None:
            stage("field_lines")
            field_lines = self._field_lines(scene, request, ids, positions, charges, r_min,
                                            arrays, entries)
        if request.isosurfaces is not None:
            stage("isosurfaces")
            isosurfaces = self._isosurfaces(scene, request, positions, charges, r_min, arrays,
                                            entries)
        if progress is not None:
            progress(1.0, "done")

        excluded = [o.id for o in scene.objects
                    if o.enabled and o.role is Role.GEOMETRY_ONLY
                    and not isinstance(o.primitive, GroupPrimitive)]
        assumptions = [
            L("Ideal point charges (zero size) at rest.", "Ideális (pontszerű), nyugvó töltések."),
            L("Unbounded vacuum: ε = ε₀ everywhere, no conductors, dielectrics or boundaries.",
              "Végtelen kiterjedésű vákuum: ε = ε₀ mindenütt, nincsenek vezetők, dielektrikumok "
              "vagy peremek."),
            L("Potential reference: φ → 0 at infinity.",
              "A potenciál vonatkoztatási pontja: φ → 0 a végtelenben."),
            L("Electrostatics: no time dependence, no currents, no magnetic field.",
              "Elektrosztatika: nincs időfüggés, nincs áram, nincs mágneses mező."),
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
                "modellnek.",
            ))
        if masked:
            warnings.append(L(
                f"{masked} sample point(s) coincide with a point charge, where the field is "
                "singular; they are reported as undefined.",
                f"{masked} mintavételi pont egybeesik egy ponttöltéssel, ahol a mező szinguláris; "
                "ezek értéke nem értelmezett.",
            ))
        if field_lines is not None:
            bad = sum(field_lines.end_reason_counts.get(k, 0)
                      for k in ("max_length", "integration_failure"))
            if bad:
                warnings.append(L(
                    f"{bad} field-line end(s) are numerical (maximum length or integration "
                    "failure), not physical endings.",
                    f"{bad} erővonalvég numerikus eredetű (maximális hossz vagy integrálási "
                    "hiba), nem fizikai végpont.",
                ))
            if field_lines.unseeded_object_ids:
                warnings.append(L(
                    f"{len(field_lines.unseeded_object_ids)} charge(s) lie outside the slice "
                    "plane or the region of interest and start no field lines in this view.",
                    f"{len(field_lines.unseeded_object_ids)} töltés a metszősíkon vagy a vizsgált "
                    "tartományon kívül esik, ezért ebben a nézetben nem indít erővonalat.",
                ))
        header = ResultHeader(
            solver_id=self.id, solver_version=self.version, solver_kind=self.kind,
            classification="exact_analytical",
            classification_note=L(
                "Exact analytical solution (Coulomb superposition) of an idealized point-charge "
                "model, evaluated in 64-bit floating point and transported as 32-bit.",
                "Idealizált ponttöltés-modell egzakt analitikus megoldása (Coulomb-szuperpozíció), "
                "64 bites lebegőpontos számítással, 32 bites átvitellel.",
            ),
            assumptions=assumptions, warnings=warnings, excluded_object_ids=excluded,
            model_context=ModelContext(
                regime="electrostatic", dimensionality="3d", medium="vacuum",
                has_free_charge=bool(np.any(charges != 0.0)), solver_id=self.id,
                source_count=int(np.count_nonzero(charges)),
                evaluated_equation_ids=["coulomb_field", "coulomb_potential", "superposition",
                                        "constitutive_d_linear", "div_E_point_charges",
                                        "div_D_point_charges", "curl_E_electrostatic",
                                        "curl_D_vacuum"],
            ),
            samplings=[s.model_dump(mode="json", exclude={"points_m"}) for s in request.samplings],
            quality=request.quality,
            compute_time_ms=(time.perf_counter() - t0) * 1e3,
            point_sources=point_source_table(
                scene, [g for g in request.samplings if isinstance(g, PlaneGridSampling)]),
            in_plane_tolerance_m=IN_PLANE_FACTOR * scene.domain.diagonal_m,
            field_lines=field_lines, equipotentials=equipotentials, isosurfaces=isosurfaces,
            arrays=entries,
        )
        return SimulationResult(header=header, arrays=arrays)
