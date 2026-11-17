"""Orchestrator: validates, selects the solver, runs fast solves in-process (with a result
cache) and dispatches long solves to the solver's queue."""

from __future__ import annotations

from collections import OrderedDict
from threading import Lock

import numpy as np

from emf_core import engine, wire
from emf_core.equations import EquationRegistry, EquationView, default_registry
from emf_core.geometry.surfaces import GaussSurface
from emf_core.i18n import LocalizedText
from emf_core.scene.models import Scene
from emf_core.solvers import (
    SolverCatalog,
    SolverDescriptor,
    SolveRequest,
    UnsupportedSceneError,
    default_catalog,
)
from emf_core.solvers.analytical import gauss
from emf_core.solvers.analytical.gauss import FluxRequest
from emf_core.solvers.base import ModelContext, Solver


class RequestTooLargeError(Exception):
    pass


class Orchestrator:
    def __init__(self, cache_entries: int, sync_point_limit: int,
                 catalog: SolverCatalog | None = None,
                 registry: EquationRegistry | None = None) -> None:
        self.catalog = catalog or default_catalog()
        self.registry = registry or default_registry()
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_entries = cache_entries
        self._sync_point_limit = sync_point_limit
        self._lock = Lock()

    def descriptors(self) -> list[SolverDescriptor]:
        return self.catalog.descriptors()

    def select(self, scene: Scene, request: SolveRequest) -> Solver:
        return self.catalog.select(scene, request)

    def solve_sync(self, scene: Scene, request: SolveRequest) -> tuple[bytes, bool]:
        """Return (EMF1 container, cache_hit)."""
        total = sum(int(np.prod(s.shape)) for s in request.samplings)
        if total > self._sync_point_limit:
            raise RequestTooLargeError(
                f"{total} sample points exceed the synchronous limit of "
                f"{self._sync_point_limit}; submit this request as a job"
            )
        key = engine.physics_fingerprint(scene, request)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit, True
        blob = engine.run(scene, request, catalog=self.catalog, registry=self.registry).to_bytes()
        with self._lock:
            self._cache[key] = blob
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return blob, False

    def solve_flux(self, scene: Scene, request: FluxRequest) -> tuple[bytes, bool]:
        """Closed-surface flux as an EMF1 container (cached separately from field solves)."""
        key = engine.flux_fingerprint(scene, request)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit, True
        header, arrays = engine.run_flux(scene, request, catalog=self.catalog)
        blob = wire.encode(header.model_dump(mode="json"), arrays)
        with self._lock:
            self._cache[key] = blob
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return blob, False

    def equations(self, scene: Scene, surfaces: list[GaussSurface] | None = None
                  ) -> tuple[list[EquationView], list[LocalizedText], list[str]]:
        """Equation views for the model(s) that would be used for this scene: the electric
        and/or magnetic sub-model, merged (see EquationRegistry.evaluate_merged). If a needed
        solver does not support the scene, return no equations plus the reasons."""
        contexts: list[ModelContext] = []
        solver_ids: list[str] = []
        for kind in engine.field_kinds(scene):
            sub = engine.field_subscene(scene, kind)
            probe = SolveRequest.model_validate({
                "samplings": [{"kind": "points", "id": "p", "points_m": [[0, 0, 0]]}],
                "quantities": ["phi"] if kind == "electric" else ["B"],
            })
            try:
                solver = self.catalog.select(sub, probe)
            except UnsupportedSceneError as exc:
                return [], exc.reasons, []
            ctx: ModelContext = solver.solve(sub, probe).header.model_context
            if kind == "electric" and surfaces:
                count, ambiguous, invalid = gauss.surface_context(sub, surfaces)
                ctx = ctx.model_copy(update={
                    "gauss_surfaces": count, "gauss_boundary_ambiguous": ambiguous,
                    "gauss_invalid": invalid,
                    "evaluated_equation_ids": [*ctx.evaluated_equation_ids, "electric_flux",
                                               "displacement_flux"],
                    "checked_equation_ids": ["gauss_integral_E", "gauss_integral_D",
                                             "divergence_theorem_E", "divergence_theorem_D"],
                })
            contexts.append(ctx)
            solver_ids.append(solver.id)
        return self.registry.evaluate_merged(contexts), [], solver_ids
