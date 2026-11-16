"""Engine entry point shared by the API (in-process) and by every worker service.

select solver -> solve -> attach computed equation statuses. Nothing here knows about HTTP,
queues or rendering."""

from __future__ import annotations

import hashlib
import json

from .equations import EquationRegistry, default_registry
from .scene.models import Scene
from .solvers import SimulationResult, SolverCatalog, SolveRequest, default_catalog
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
