"""Orchestrator: validates, selects the solver, runs fast solves in-process (with a result
cache) and dispatches long solves to the solver's queue."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from threading import Lock

import numpy as np

from emf_core import ampere, circuits, engine, induction, lorentz, wire
from emf_core.ampere import AmperePath, AmpereRequest
from emf_core.equations import EquationRegistry, EquationView, default_registry
from emf_core.geometry.surfaces import GaussSurface
from emf_core.i18n import LocalizedText
from emf_core.induction import FluxSurface, InductionRequest
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


# Interactive budget for magnetic solves: loop-field evaluations per synchronous request.
SYNC_LOOP_EVALUATIONS = 4e7
MAGNET_COST = 60  # typical loop evaluations per point for a magnet's adaptive quadrature


def magnetic_cost_per_point(scene: Scene) -> int:
    from emf_core.scene.currents import current_sources

    cs = current_sources(scene)
    return max(1, len(cs.wires) + len(cs.loops) + MAGNET_COST * len(cs.magnets)
               + len(cs.ideal_toroids))


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
        if request.field_kind == "magnetic":
            cost = total * magnetic_cost_per_point(engine.field_subscene(scene, "magnetic"))
            if cost > SYNC_LOOP_EVALUATIONS:
                raise RequestTooLargeError(
                    f"about {cost:.3g} loop-field evaluations (sample points × filaments, plus "
                    f"~{MAGNET_COST} per magnet) exceed the interactive limit of "
                    f"{SYNC_LOOP_EVALUATIONS:.0e}; reduce the number of turns or submit a "
                    "high-resolution job. Nothing was reduced or approximated.")
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

    def solve_ampere(self, scene: Scene, request: AmpereRequest) -> tuple[bytes, bool]:
        """Ampère circulation results (JSON bytes), cached separately (magnetic subscene +
        path physics)."""
        sub = engine.field_subscene(scene, "magnetic")
        key = ampere.fingerprint(sub, request)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit, True
        probe = SolveRequest.model_validate({
            "samplings": [{"kind": "points", "id": "p", "points_m": [[0, 0, 0]]}],
            "quantities": ["B"]})
        solver = self.catalog.select(sub, probe)
        blob = ampere.compute(sub, request, solver.id, solver.version).model_dump_json().encode()
        with self._lock:
            self._cache[key] = blob
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return blob, False

    def solve_induction(self, scene: Scene, request: InductionRequest) -> tuple[bytes, bool]:
        """Flux, Faraday and mutual-induction results at one time (JSON bytes; Phase 4A),
        cached by magnetic subscene + time + surfaces. The geometry-only unit quantities are
        cached inside ``induction`` independently of time, so moving the time is cheap."""
        sub = engine.field_subscene(scene, "magnetic")
        key = induction.fingerprint(sub, request)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit, True
        probe = SolveRequest.model_validate({
            "samplings": [{"kind": "points", "id": "p", "points_m": [[0, 0, 0]]}],
            "quantities": ["B"]})
        solver = self.catalog.select(sub, probe)
        blob = induction.compute(sub, request, solver.id,
                                 solver.version).model_dump_json().encode()
        with self._lock:
            self._cache[key] = blob
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return blob, False

    def solve_circuits(self, scene: Scene, request: circuits.CircuitRequest
                       ) -> tuple[bytes, bool]:
        """Passive-circuit solution over the whole time range (JSON bytes; Phase 4C), cached by
        the magnetic subscene and the circuits' physics."""
        sub = engine.field_subscene(scene, "magnetic")
        key = circuits.fingerprint(sub, request)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit, True
        blob = circuits.compute(sub, request).model_dump_json().encode()
        with self._lock:
            self._cache[key] = blob
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return blob, False

    def solve_particle(self, scene: Scene, request: lorentz.ParticleRequest
                       ) -> tuple[bytes, bool]:
        """Test-particle trajectory (JSON bytes; Phase 4B), cached by scene and request."""
        s = scene.model_dump(mode="json")
        for o in s["objects"]:
            o.pop("name", None)
        key = "particle:" + hashlib.sha256(json.dumps(
            {"scene": s, "particle": request.model_dump(mode="json")}, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit, True
        blob = lorentz.trajectory(scene, request).model_dump_json().encode()
        with self._lock:
            self._cache[key] = blob
            while len(self._cache) > self._cache_entries:
                self._cache.popitem(last=False)
        return blob, False

    def equations(self, scene: Scene, surfaces: list[GaussSurface] | None = None,
                  paths: list[AmperePath] | None = None,
                  flux_surfaces: list[FluxSurface] | None = None,
                  test_charge: lorentz.TestCharge | None = None,
                  passive: list[circuits.PassiveCircuit] | None = None,
                  disks: list[circuits.EddyDisk] | None = None
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
            if kind == "magnetic" and paths:
                ctx = ctx.model_copy(update={
                    "ampere_paths": len(paths),
                    "checked_equation_ids": [*ctx.checked_equation_ids, "ampere_integral"],
                })
            if kind == "magnetic" and flux_surfaces:
                ctx = ctx.model_copy(update={
                    "flux_surfaces": len(flux_surfaces),
                    "evaluated_equation_ids": [*ctx.evaluated_equation_ids, "magnetic_flux",
                                               "flux_derivative", "mutual_inductance"],
                    "checked_equation_ids": [*ctx.checked_equation_ids, "faraday_integral",
                                             "mutual_reciprocity"],
                })
            moving = [f for f in flux_surfaces or [] if f.moving]
            if kind == "magnetic" and moving:
                rods = sum(isinstance(f.shape, induction.SlidingRodShape) for f in moving)
                rot = sum(f.motion is not None and f.motion.rotation.type != "none"
                          for f in moving)
                ctx = ctx.model_copy(update={
                    "moving_surfaces": len(moving), "sliding_rods": rods, "rotating_surfaces": rot,
                    "evaluated_equation_ids": [*ctx.evaluated_equation_ids, "rigid_body_pose",
                                               "material_velocity", "motional_field",
                                               "motional_emf", "moving_surface_flux"],
                    "checked_equation_ids": [*ctx.checked_equation_ids,
                                             "generalized_faraday"],
                })
            if kind == "magnetic" and flux_surfaces:
                ctx = ctx.model_copy(update={"multi_turn_surfaces": sum(
                    f.turns > 1 for f in flux_surfaces)})
            if kind == "magnetic" and (passive or disks):
                pc = passive or []
                ctx = ctx.model_copy(update={
                    "passive_circuits": len(pc) + sum(d.bands for d in disks or []),
                    "moving_circuits": sum(c.path.moving for c in pc),
                    "dynamic_circuits": sum(c.mechanics is not None
                                            and c.mechanics.mode == "dynamic" for c in pc),
                    "eddy_disks": len(disks or []),
                    "user_inductance": any(c.electrical.self_inductance.mode == "user"
                                           for c in pc),
                    "evaluated_equation_ids": [*ctx.evaluated_equation_ids, "resistance_sigma",
                                               "passive_loop_equation", "flux_linkage",
                                               "joule_heating", "coupled_magnetic_energy",
                                               "magnetic_force_filament"],
                })
            if test_charge is not None and test_charge.enabled:
                ctx = ctx.model_copy(update={
                    "test_charge": True, "trajectory": test_charge.trajectory.enabled,
                    "evaluated_equation_ids": [*ctx.evaluated_equation_ids, "lorentz_force",
                                               "electric_force", "magnetic_force"],
                })
            contexts.append(ctx)
            solver_ids.append(solver.id)
        return self.registry.evaluate_merged(contexts), [], solver_ids
