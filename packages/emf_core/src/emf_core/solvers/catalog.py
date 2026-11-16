"""Solver catalog: what exists, what is actually available, and solver selection.

A solver is only reported as available when its implementation is importable in this process
(or, for queue workers, when a live worker answers — that check is done by the API). Planned
solvers are listed with ``available = False`` and a reason, never as working."""

from __future__ import annotations

from pydantic import BaseModel

from ..i18n import L, LocalizedText
from ..scene.models import Scene
from .analytical import PointChargeVacuumSolver
from .base import Solver, SolveRequest, SolverKind


class SolverDescriptor(BaseModel):
    id: str
    kind: SolverKind
    version: str | None
    name: LocalizedText
    available: bool
    unavailable_reason: LocalizedText | None = None
    planned_phase: int | None = None
    queue: str  # task queue served by this solver's worker service


class UnsupportedSceneError(Exception):
    def __init__(self, reasons: list[LocalizedText]) -> None:
        super().__init__("; ".join(r.en for r in reasons))
        self.reasons = reasons


_PLANNED: list[SolverDescriptor] = [
    SolverDescriptor(
        id="fem.dolfinx", kind="fem", version=None,
        name=L("Finite element solver (DOLFINx + Gmsh)", "Végeselemes megoldó (DOLFINx + Gmsh)"),
        available=False, planned_phase=5, queue="solver.fem",
        unavailable_reason=L("The FEM worker service is not implemented or deployed (Phase 5).",
                             "A végeselemes worker szolgáltatás nincs megvalósítva, illetve "
                             "telepítve (5. fázis)."),
    ),
    SolverDescriptor(
        id="fdtd.meep", kind="fdtd", version=None,
        name=L("FDTD full-wave solver (Meep)", "FDTD teljes hullámú megoldó (Meep)"),
        available=False, planned_phase=5, queue="solver.fdtd",
        unavailable_reason=L("The FDTD worker service is not implemented or deployed (Phase 5).",
                             "Az FDTD worker szolgáltatás nincs megvalósítva, illetve telepítve "
                             "(5. fázis)."),
    ),
    SolverDescriptor(
        id="circuit.mna", kind="circuit", version=None,
        name=L("Lumped circuit solver (MNA)", "Koncentrált paraméterű áramköri megoldó (MNA)"),
        available=False, planned_phase=None, queue="solver.circuit",
        unavailable_reason=L("The circuit subsystem is not implemented yet.",
                             "Az áramköri alrendszer még nincs megvalósítva."),
    ),
]


class SolverCatalog:
    def __init__(self, solvers: list[Solver]) -> None:
        self._solvers = {s.id: s for s in solvers}

    def get(self, solver_id: str) -> Solver:
        return self._solvers[solver_id]

    def descriptors(self) -> list[SolverDescriptor]:
        live = [
            SolverDescriptor(
                id=s.id, kind=s.kind, version=s.version, available=True, queue=f"solver.{s.kind}",
                name=L("Analytical electrostatics: point charges in vacuum",
                       "Analitikus elektrosztatika: ponttöltések vákuumban"),
            )
            for s in self._solvers.values()
        ]
        return live + _PLANNED

    def select(self, scene: Scene, request: SolveRequest) -> Solver:
        """Pick the first available solver that supports the scene (analytical solvers are
        registered first, so they win whenever they apply). Never falls back to a simpler
        model: if nothing supports the scene, raise with every solver's reasons."""
        reasons: list[LocalizedText] = []
        for s in self._solvers.values():
            sup = s.supports(scene, request)
            if sup.supported:
                return s
            reasons.extend(sup.reasons)
        raise UnsupportedSceneError(reasons)


def default_catalog() -> SolverCatalog:
    return SolverCatalog([PointChargeVacuumSolver()])
