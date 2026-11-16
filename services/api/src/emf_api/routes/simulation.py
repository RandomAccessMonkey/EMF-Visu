from __future__ import annotations

from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, Response

from emf_core.presets import PRESETS, Preset
from emf_core.solvers import SolveRequest, SolverError, UnsupportedSceneError

from ..deps import api_error, get_orchestrator
from ..orchestrator import Orchestrator, RequestTooLargeError
from ..schemas import (
    EquationsBody,
    EquationsResponse,
    ErrorBody,
    ProbeBody,
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
        "quantities": ["E", "phi", "D"],
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
        if not np.all(np.isfinite(a)):
            defined = False
            values.append(ProbeValue(quantity=entry.quantity, symbol=entry.symbol,
                                     unit=entry.unit, value=None))
        elif entry.components == 3:
            values.append(ProbeValue(quantity=entry.quantity, symbol=entry.symbol, unit=entry.unit,
                                     value=[float(x) for x in a],
                                     magnitude=float(np.linalg.norm(a))))
        else:
            values.append(ProbeValue(quantity=entry.quantity, symbol=entry.symbol,
                                     unit=entry.unit, value=float(a)))
    return ProbeResponse(point_m=body.point_m, solver_id=solver.id, solver_version=solver.version,
                         classification=result.header.classification, defined=defined,
                         values=values)


@router.post("/equations/evaluate")
def evaluate_equations(body: EquationsBody, orch: Orch) -> EquationsResponse:
    """Equations with their applicability status for the model that this scene resolves to."""
    views, reasons, solver_id = orch.equations(body.scene)
    return EquationsResponse(supported=solver_id is not None, solver_id=solver_id,
                             unsupported_reasons=reasons, equations=views)


@router.get("/presets")
def presets() -> list[Preset]:
    return PRESETS


