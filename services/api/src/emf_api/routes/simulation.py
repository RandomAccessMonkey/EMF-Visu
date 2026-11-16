from __future__ import annotations

from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Response

from emf_core.postprocess import differential
from emf_core.presets import PRESETS, Preset
from emf_core.solvers import SolveRequest, SolverError, UnsupportedSceneError
from emf_core.solvers.analytical import electrostatics as es
from emf_core.units import EPS0, QUANTITIES

from ..deps import api_error, get_orchestrator
from ..orchestrator import Orchestrator, RequestTooLargeError
from ..schemas import (
    EquationsBody,
    EquationsResponse,
    ErrorBody,
    ProbeBody,
    ProbeContribution,
    ProbeDiagnostic,
    ProbeDistributional,
    ProbeResponse,
    ProbeValue,
    SimulationBody,
)

router = APIRouter(tags=["simulation"])
Orch = Annotated[Orchestrator, Depends(get_orchestrator)]
RESULT_MEDIA_TYPE = "application/vnd.emf.result"
_ERRORS: dict[int | str, dict[str, object]] = {
    413: {"model": ErrorBody}, 422: {"model": ErrorBody}, 500: {"model": ErrorBody},
}


@router.post(
    "/simulations",
    response_class=Response,
    responses={200: {"content": {RESULT_MEDIA_TYPE: {}},
                     "description": "EMF1 binary container (see docs/architecture.md)"}, **_ERRORS},
)
def simulate(body: SimulationBody, orch: Orch) -> Response:
    """Solve synchronously (fast analytical requests). Unsupported configurations are refused
    with reasons; they are never approximated by a simpler model."""
    try:
        blob, hit = orch.solve_sync(body.scene, body.request)
    except UnsupportedSceneError as exc:
        raise api_error(422, "unsupported", "no available solver supports this configuration",
                        exc.reasons) from exc
    except RequestTooLargeError as exc:
        raise api_error(413, "too_large", str(exc)) from exc
    except SolverError as exc:
        raise api_error(500, "solver_failed", str(exc)) from exc
    return Response(blob, media_type=RESULT_MEDIA_TYPE,
                    headers={"X-EMF-Cache": "hit" if hit else "miss"})


@router.post("/probe", responses=_ERRORS)
def probe(body: ProbeBody, orch: Orch) -> ProbeResponse:
    """Evaluate the fields at one point. Values are returned as float64 JSON numbers, not
    interpolated from a sampled grid."""
    request = SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "probe", "points_m": [body.point_m]}],
        "quantities": ["E", "phi", "D", "div_E", "curl_E", "div_D", "curl_D"],
    })
    try:
        solver = orch.select(body.scene, request)
        result = solver.solve(body.scene, request)
    except UnsupportedSceneError as exc:
        raise api_error(422, "unsupported", "no available solver supports this configuration",
                        exc.reasons) from exc
    except SolverError as exc:
        raise api_error(500, "solver_failed", str(exc)) from exc
    values: list[ProbeValue] = []
    defined = True
    for entry in result.header.arrays:
        a = result.arrays[entry.name][0]
        kind = "vector" if entry.components == 3 else "scalar"
        if not np.all(np.isfinite(a)):
            defined = False
            status = "not_evaluated" if entry.quantity.startswith(("div_", "curl_")) else "singular"
            values.append(ProbeValue(quantity=entry.quantity, symbol=entry.symbol,
                                     unit=entry.unit, value=None, kind=kind, status=status))
        elif entry.components == 3:
            values.append(ProbeValue(quantity=entry.quantity, symbol=entry.symbol, unit=entry.unit,
                                     value=[float(x) for x in a],
                                     magnitude=float(np.linalg.norm(a)), kind=kind))
        else:
            values.append(ProbeValue(quantity=entry.quantity, symbol=entry.symbol,
                                     unit=entry.unit, value=float(a), kind=kind))
    # Individual terms of the superposition, from the same solver module.
    ids, positions, charges = es.point_charge_table(body.scene)
    r_min = es.COINCIDENCE_FACTOR * body.scene.domain.diagonal_m
    point = np.asarray([body.point_m], dtype=np.float64)
    e_i, phi_i = es.contributions(point, positions, charges, r_min)
    names = {o.id: o.name or o.id for o in body.scene.objects}
    contributions: list[ProbeContribution] = []
    singular_id: str | None = None
    for k, oid in enumerate(ids):
        ok = bool(np.isfinite(phi_i[k, 0]))
        if not ok:
            singular_id = oid
        contributions.append(ProbeContribution(
            object_id=oid, name=names[oid], charge_C=float(charges[k]),
            distance_m=float(np.linalg.norm(point[0] - positions[k])),
            E_V_per_m=[float(x) for x in e_i[k, 0]] if ok else None,
            E_magnitude_V_per_m=float(np.linalg.norm(e_i[k, 0])) if ok else None,
            phi_V=float(phi_i[k, 0]) if ok else None,
        ))
    distributional: ProbeDistributional | None = None
    if singular_id is not None:
        src = next(c for c in contributions if c.object_id == singular_id)
        distributional = ProbeDistributional(
            object_id=src.object_id, name=src.name, charge_C=src.charge_C,
            div_E_weight_V_m=src.charge_C / EPS0, div_D_weight_C=src.charge_C,
            curl_E_distributional=[0.0, 0.0, 0.0], curl_D_distributional=[0.0, 0.0, 0.0],
        )
    diagnostics: list[ProbeDiagnostic] = []
    if defined:
        diagnostics = _diagnostics(point[0], positions, charges, r_min,
                                   body.scene.domain.diagonal_m, values)
    return ProbeResponse(point_m=body.point_m, solver_id=solver.id, solver_version=solver.version,
                         classification=result.header.classification, defined=defined,
                         singular_tolerance_m=r_min, singular_object_id=singular_id,
                         values=values, contributions=contributions,
                         distributional=distributional, diagnostics=diagnostics,
                         diagnostics_method="central differences of the exact field with steps h "
                                            "and h/2, Richardson-extrapolated; uncertainty = "
                                            "truncation estimate + round-off bound")


def _diagnostics(point: np.ndarray, positions: np.ndarray, charges: np.ndarray, r_min: float,
                 diag: float, values: list[ProbeValue]) -> list[ProbeDiagnostic]:
    """Numerical cross-check of the exact div/curl at an ordinary point (never a result)."""
    nearest = float(np.linalg.norm(positions - point, axis=1).min()) if len(charges) else diag
    h = differential.RELATIVE_STEP * min(nearest, diag)
    exact = {v.quantity: v.value for v in values}
    out: list[ProbeDiagnostic] = []
    for field, scale in (("E", 1.0), ("D", EPS0)):
        def fn(p: np.ndarray, scale: float = scale) -> np.ndarray:
            return scale * es.evaluate(p, positions, charges, r_min)[0]

        est = differential.estimate(fn, point, h)
        div_q, curl_q = f"div_{field}", f"curl_{field}"
        div_exact = exact[div_q]
        curl_exact = exact[curl_q]
        assert isinstance(div_exact, float) and isinstance(curl_exact, list)
        out.append(ProbeDiagnostic(
            quantity=div_q, symbol=QUANTITIES[div_q].symbol, unit=QUANTITIES[div_q].unit,
            exact=div_exact, estimate=est.div, uncertainty=est.div_uncertainty,
            consistent_with_exact=abs(est.div - div_exact) <= est.div_uncertainty, step_m=h))
        out.append(ProbeDiagnostic(
            quantity=curl_q, symbol=QUANTITIES[curl_q].symbol, unit=QUANTITIES[curl_q].unit,
            exact=curl_exact, estimate=[float(x) for x in est.curl],
            uncertainty=[float(x) for x in est.curl_uncertainty],
            consistent_with_exact=bool(np.all(np.abs(est.curl - np.asarray(curl_exact))
                                              <= est.curl_uncertainty)),
            step_m=h))
    return out


@router.post("/equations/evaluate")
def evaluate_equations(body: EquationsBody, orch: Orch) -> EquationsResponse:
    """Equations with their applicability status for the model that this scene resolves to."""
    views, reasons, solver_id = orch.equations(body.scene)
    return EquationsResponse(supported=solver_id is not None, solver_id=solver_id,
                             unsupported_reasons=reasons, equations=views)


@router.get("/presets")
def presets() -> list[Preset]:
    return PRESETS


