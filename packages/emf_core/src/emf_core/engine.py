"""Engine entry point shared by the API (in-process) and by every worker service.

select solver -> solve -> attach computed equation statuses. Nothing here knows about HTTP,
queues or rendering."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from numpy.typing import NDArray

from .equations import EquationRegistry, default_registry
from .i18n import L
from .scene.models import Scene
from .solvers import (
    SimulationResult,
    SolverCatalog,
    SolveRequest,
    UnsupportedSceneError,
    default_catalog,
)
from .solvers.analytical import PointChargeVacuumSolver, gauss
from .solvers.analytical.gauss import FluxHeader, FluxRequest
from .solvers.base import CancelCheck, ProgressCallback

_CATALOG = default_catalog()
_REGISTRY = default_registry()


def run(
    scene: Scene,
    request: SolveRequest,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
    catalog: SolverCatalog | None = None,
    registry: EquationRegistry | None = None,
) -> SimulationResult:
    """Raises UnsupportedSceneError, SolverError or SolverCancelledError."""
    solver = (catalog or _CATALOG).select(scene, request)
    result = solver.solve(scene, request, progress, cancel)
    result.header.equation_status = (registry or _REGISTRY).statuses(result.header.model_context)
    return result


def physics_fingerprint(scene: Scene, request: SolveRequest) -> str:
    """Hash of everything that can change a physical result. Display-only attributes (object
    and material names) are excluded, so renaming never invalidates cached results."""
    s = scene.model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
    for m in s["materials"]:
        m.pop("name", None)
    payload = json.dumps({"scene": s, "request": request.model_dump(mode="json")},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def run_flux(scene: Scene, request: FluxRequest,
             catalog: SolverCatalog | None = None) -> tuple[FluxHeader, dict[str, NDArray[Any]]]:
    """Closed-surface flux through the analytical point-charge model. Raises
    UnsupportedSceneError when the scene is outside that model."""
    probe = SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": [[0, 0, 0]]}],
        "quantities": ["phi"]})
    solver = (catalog or _CATALOG).select(scene, probe)
    if solver.id != PointChargeVacuumSolver.id:
        raise UnsupportedSceneError([L("Flux through closed surfaces is implemented for the "
                                       "analytical point-charge model only.",
                                       "A zárt felületen átmenő fluxus csak az analitikus "
                                       "ponttöltés-modellre van megvalósítva.")])
    return gauss.compute(scene, request, solver.id, solver.version)


def flux_fingerprint(scene: Scene, request: FluxRequest) -> str:
    """Cache key of a flux result: physical scene, surface geometry and orientation, quality
    (which fixes the mesh resolution). Surface names and display metadata are excluded."""
    s = scene.model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
    for m in s["materials"]:
        m.pop("name", None)
    payload = json.dumps({"scene": s, "surfaces": [x.physics_dump() for x in request.surfaces],
                          "quality": request.quality, "details": request.patch_details},
                         sort_keys=True, separators=(",", ":"))
    return "flux:" + hashlib.sha256(payload.encode()).hexdigest()
