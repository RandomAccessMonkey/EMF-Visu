"""Exact electrostatic field of ideal point charges in unbounded vacuum.

Model (equation registry ids ``coulomb_field`` and ``coulomb_potential``):

    E(r)   = 1/(4 pi eps0) * sum_i q_i (r - r_i) / |r - r_i|^3      [V/m]
    phi(r) = 1/(4 pi eps0) * sum_i q_i / |r - r_i|                  [V], phi(infinity) = 0
    D(r)   = eps0 E(r)                                              [C/m^2] (vacuum)

The sums are evaluated directly in float64; nothing is discretized, so the result is exact up
to floating-point rounding. At a charge location the field is singular: sample points closer
than ``COINCIDENCE_FACTOR * domain diagonal`` to a charge are returned as NaN and counted.
"""

from __future__ import annotations

import time

import numpy as np
from numpy.typing import NDArray

from ...i18n import L, LocalizedText
from ...scene.models import MaterialModel, PointChargeSource, PointPrimitive, Role, Scene
from ...scene.transforms import world_position
from ...units import COULOMB_K, EPS0, QUANTITIES
from ..base import (
    ArrayEntry,
    ArrayStats,
    CancelCheck,
    ModelContext,
    ProgressCallback,
    ResultHeader,
    SimulationResult,
    SolverCancelledError,
    SolveRequest,
    SolverKind,
    Support,
)

COINCIDENCE_FACTOR = 1e-12
_CHUNK = 100_000


def point_charges(scene: Scene) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """World positions (n, 3) [m] and charges (n,) [C] of all enabled point-charge sources."""
    pos: list[NDArray[np.float64]] = []
    q: list[float] = []
    for o in scene.objects:
        if o.enabled and o.role is Role.CHARGE_SOURCE and isinstance(o.source, PointChargeSource):
            pos.append(world_position(scene, o))
            q.append(o.source.charge_C)
    return np.asarray(pos, np.float64).reshape(-1, 3), np.asarray(q, np.float64)


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


def _stats(a: NDArray[np.float64], vector: bool) -> ArrayStats:
    v = np.sqrt(np.einsum("...j,...j->...", a, a)) if vector else a
    finite = np.isfinite(v)
    bad = int(v.size - np.count_nonzero(finite))
    if not finite.any():
        return ArrayStats(min=None, max=None, non_finite_count=bad)
    return ArrayStats(min=float(v[finite].min()), max=float(v[finite].max()), non_finite_count=bad)


class PointChargeVacuumSolver:
    id = "analytical.electrostatics.point_charges"
    version = "1.0.0"
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

    def solve(
        self,
        scene: Scene,
        request: SolveRequest,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> SimulationResult:
        t0 = time.perf_counter()
        positions, charges = point_charges(scene)
        r_min = COINCIDENCE_FACTOR * scene.domain.diagonal_m
        total = sum(int(np.prod(s.shape)) for s in request.samplings)
        done = 0
        arrays: dict[str, NDArray[np.float64]] = {}
        entries: list[ArrayEntry] = []
        masked = 0
        for s in request.samplings:
            pts = s.points()
            e = np.empty_like(pts)
            phi = np.empty(pts.shape[0])
            for start in range(0, pts.shape[0], _CHUNK):
                if cancel is not None and cancel():
                    raise SolverCancelledError()
                sl = slice(start, start + _CHUNK)
                e[sl], phi[sl] = evaluate(pts[sl], positions, charges, r_min)
                done += pts[sl].shape[0]
                if progress is not None:
                    progress(done / total, s.id)
            masked += int(np.count_nonzero(np.isnan(phi)))
            for qty in request.quantities:
                data = {"E": e, "phi": phi, "D": EPS0 * e}[qty]
                info = QUANTITIES[qty]
                name = f"{s.id}.{qty}"
                shape = (*s.shape, 3) if info.rank == 1 else s.shape
                arrays[name] = data.reshape(shape)
                entries.append(ArrayEntry(
                    name=name, sampling_id=s.id, quantity=qty, symbol=info.symbol, unit=info.unit,
                    components=3 if info.rank == 1 else 1, stats=_stats(data, info.rank == 1),
                ))
        excluded = [o.id for o in scene.objects if o.enabled and o.role is Role.GEOMETRY_ONLY]
        assumptions = [
            L("Ideal point charges (zero size) at rest.", "Ideális (pontszerű), nyugvó töltések."),
            L("Unbounded vacuum: ε = ε₀ everywhere, no conductors, dielectrics or boundaries.",
              "Végtelen kiterjedésű vákuum: ε = ε₀ mindenütt, nincsenek vezetők, dielektrikumok "
              "vagy peremek."),
            L("Potential reference: φ → 0 at infinity.",
              "A potenciál vonatkoztatási pontja: φ → 0 a végtelenben."),
            L("Electrostatics: no time dependence, no currents, no magnetic field.",
              "Elektrosztatika: nincs időfüggés, nincs áram, nincs mágneses mező."),
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
                evaluated_equation_ids=["coulomb_field", "coulomb_potential",
                                        "constitutive_d_linear"],
            ),
            samplings=[s.model_dump(mode="json", exclude={"points_m"}) for s in request.samplings],
            quality=request.quality,
            compute_time_ms=(time.perf_counter() - t0) * 1e3,
            arrays=entries,
        )
        return SimulationResult(header=header, arrays=arrays)
