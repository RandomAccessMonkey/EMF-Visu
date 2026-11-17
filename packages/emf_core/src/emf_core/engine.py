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
from .sampling import FieldKind
from .scene.currents import current_sources, enabled
from .scene.models import GroupPrimitive, PointChargeSource, Role, Scene
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


def field_subscene(scene: Scene, kind: FieldKind) -> Scene:
    """The part of a scene that can affect a field of the given kind.

    Static charges produce no magnetic field, and steady currents in electrically neutral ideal
    filaments produce no electric field. The electric subscene therefore drops well-formed (or
    disabled) current sources, and the magnetic subscene drops charge sources and groups left
    without children (dipole groups). Malformed sources stay, so the solver still refuses them.
    An object that still has children is never dropped. Every cache key is computed from the
    subscene, so the electric and magnetic caches are independent."""
    if kind == "electric":
        well_formed = set(current_sources(scene).ids)
        # Free currents and magnetized material are the magnetic model's sources (Phase 3A/3B).
        drop = {o.id for o in scene.objects
                if o.role in (Role.CURRENT_SOURCE, Role.MAGNETIC_MATERIAL)
                and (o.id in well_formed or not enabled(scene, o))}
    else:
        drop = {o.id for o in scene.objects if o.role is Role.CHARGE_SOURCE
                and isinstance(o.source, PointChargeSource)}
    while True:
        kept = [o for o in scene.objects if o.id not in drop]
        parents = {o.parent_id for o in kept if o.parent_id is not None}
        drop -= parents  # never orphan a kept child
        empty_groups = {o.id for o in kept if isinstance(o.primitive, GroupPrimitive)
                        and o.id not in parents and kind == "magnetic"
                        and any(x.parent_id == o.id for x in scene.objects)}
        if not empty_groups - drop:
            break
        drop |= empty_groups
    return scene.model_copy(update={"objects": [o for o in scene.objects if o.id not in drop]})


def field_kinds(scene: Scene) -> list[FieldKind]:
    """Which field solves a scene needs: magnetic if it has current sources, electric if it has
    charges or has no current sources (so scenes without currents behave as before)."""
    live = [o for o in scene.objects if enabled(scene, o)]
    has_currents = any(o.role in (Role.CURRENT_SOURCE, Role.MAGNETIC_MATERIAL) for o in live)
    has_charges = any(o.role is Role.CHARGE_SOURCE for o in live)
    kinds: list[FieldKind] = []
    if has_charges or not has_currents:
        kinds.append("electric")
    if has_currents:
        kinds.append("magnetic")
    return kinds


def run(
    scene: Scene,
    request: SolveRequest,
    progress: ProgressCallback | None = None,
    cancel: CancelCheck | None = None,
    catalog: SolverCatalog | None = None,
    registry: EquationRegistry | None = None,
) -> SimulationResult:
    """Raises UnsupportedSceneError, SolverError or SolverCancelledError.

    The solver receives the subscene of the request's field kind, so the result depends on
    nothing outside its cache key."""
    scene = field_subscene(scene, request.field_kind)
    solver = (catalog or _CATALOG).select(scene, request)
    result = solver.solve(scene, request, progress, cancel)
    result.header.equation_status = (registry or _REGISTRY).statuses(result.header.model_context)
    return result


def physics_fingerprint(scene: Scene, request: SolveRequest) -> str:
    """Hash of everything that can change a physical result: the request and the subscene of
    its field kind. Display-only attributes (object and material names) are excluded, so
    renaming never invalidates cached results."""
    s = field_subscene(scene, request.field_kind).model_dump(mode="json")
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
    scene = field_subscene(scene, "electric")
    solver = (catalog or _CATALOG).select(scene, probe)
    if solver.id != PointChargeVacuumSolver.id:
        raise UnsupportedSceneError([L("Flux through closed surfaces is implemented for the "
                                       "analytical point-charge model only.",
                                       "A zárt felületen átmenő fluxus csak az analitikus "
                                       "ponttöltés-modellre van megvalósítva.")])
    return gauss.compute(scene, request, solver.id, solver.version)


def flux_fingerprint(scene: Scene, request: FluxRequest) -> str:
    """Cache key of a flux result: electric subscene, surface geometry and orientation, quality
    (which fixes the mesh resolution). Surface names and display metadata are excluded."""
    s = field_subscene(scene, "electric").model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
    for m in s["materials"]:
        m.pop("name", None)
    payload = json.dumps({"scene": s, "surfaces": [x.physics_dump() for x in request.surfaces],
                          "quality": request.quality, "details": request.patch_details},
                         sort_keys=True, separators=(",", ":"))
    return "flux:" + hashlib.sha256(payload.encode()).hexdigest()
