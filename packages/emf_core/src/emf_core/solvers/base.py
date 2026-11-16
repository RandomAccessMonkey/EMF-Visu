"""Versioned, solver-agnostic solver interface (interface version 1).

Every solver — analytical, FEM, FDTD, circuit — implements ``Solver`` and returns a
``SimulationResult`` whose header states solver identity and version, the result classification,
the model assumptions, discretization and convergence information, units and status.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .. import wire
from ..i18n import LocalizedText
from ..sampling import MAX_POINTS_PER_REQUEST, Sampling
from ..scene.models import Scene, StrictModel

SOLVER_INTERFACE_VERSION = 1
RESULT_FORMAT_VERSION: Literal[1] = 1

Quantity = Literal["E", "phi", "D"]
Quality = Literal["preview", "normal", "high"]
SolverKind = Literal["analytical", "fem", "fdtd", "circuit"]
Classification = Literal[
    "exact_analytical", "numerical_approximation", "idealized_model", "visualization_aid"
]
ProgressCallback = Callable[[float, str], None]
CancelCheck = Callable[[], bool]


class SolverError(Exception):
    """The solver failed; the message is shown to the user in place of a result."""


class SolverCancelledError(Exception):
    pass


class SolveRequest(StrictModel):
    samplings: list[Sampling] = Field(min_length=1, max_length=8)
    quantities: list[Quantity] = Field(min_length=1)
    quality: Quality = "normal"

    @model_validator(mode="after")
    def _check(self) -> SolveRequest:
        ids = [s.id for s in self.samplings]
        if len(set(ids)) != len(ids):
            raise ValueError("sampling ids must be unique")
        if len(set(self.quantities)) != len(self.quantities):
            raise ValueError("quantities must be unique")
        total = sum(int(np.prod(s.shape)) for s in self.samplings)
        if total > MAX_POINTS_PER_REQUEST:
            raise ValueError(
                f"request samples {total} points; the limit is {MAX_POINTS_PER_REQUEST}"
            )
        return self


class Support(BaseModel):
    supported: bool
    reasons: list[LocalizedText] = []


class ModelContext(BaseModel):
    """What physical model produced a result. The equation registry derives every equation's
    applicability status from this, so statuses are computed rather than hard-coded."""

    model_config = ConfigDict(extra="forbid")
    regime: Literal["electrostatic", "magnetostatic", "quasi_static", "full_wave"]
    dimensionality: Literal["3d", "2d_planar", "2d_axisymmetric"]
    medium: Literal["vacuum", "homogeneous_linear", "inhomogeneous_linear"]
    has_free_charge: bool = False
    has_free_current: bool = False
    has_conductors: bool = False
    time_varying: bool = False
    computes_magnetic_field: bool = False
    solver_id: str
    evaluated_equation_ids: list[str] = []


class ArrayStats(BaseModel):
    """Statistics computed in float64 before the float32 transport cast. For vectors they
    describe the magnitude; for scalars the signed value."""

    min: float | None
    max: float | None
    non_finite_count: int


class ArrayEntry(BaseModel):
    name: str  # "<sampling_id>.<quantity>"
    sampling_id: str
    quantity: str
    symbol: str
    unit: str
    components: int  # 1 = scalar, 3 = vector (x, y, z)
    stats: ArrayStats
    dtype: str = "<f4"
    shape: list[int] = []
    offset: int = 0
    byte_length: int = 0


class EquationStatusEntry(BaseModel):
    equation_id: str
    status: Literal[
        "applicable", "applicable_under_assumptions", "not_applicable", "not_evaluated"
    ]
    reason: LocalizedText | None = None


class ResultHeader(BaseModel):
    format_version: Literal[1] = RESULT_FORMAT_VERSION
    status: Literal["ok", "failed", "cancelled"] = "ok"
    failure_reason: str | None = None
    solver_id: str
    solver_version: str
    solver_kind: SolverKind
    solver_interface_version: int = SOLVER_INTERFACE_VERSION
    classification: Classification
    classification_note: LocalizedText
    assumptions: list[LocalizedText]
    warnings: list[LocalizedText] = []
    excluded_object_ids: list[str] = []  # inert geometry that is not part of the model
    model_context: ModelContext
    discretization: dict[str, Any] | None = None  # mesh/grid details (numerical solvers)
    convergence: dict[str, Any] | None = None
    samplings: list[dict[str, Any]] = []
    quality: Quality = "normal"
    compute_time_ms: float = 0.0
    equation_status: list[EquationStatusEntry] = []
    arrays: list[ArrayEntry] = []


@dataclass
class SimulationResult:
    header: ResultHeader
    arrays: dict[str, NDArray[np.float64]]

    def to_bytes(self) -> bytes:
        head = self.header.model_dump(mode="json")
        blob = wire.encode(head, self.arrays)
        return blob


class Solver(Protocol):
    id: str
    version: str
    kind: SolverKind

    def supports(self, scene: Scene, request: SolveRequest) -> Support: ...

    def solve(
        self,
        scene: Scene,
        request: SolveRequest,
        progress: ProgressCallback | None = None,
        cancel: CancelCheck | None = None,
    ) -> SimulationResult: ...
