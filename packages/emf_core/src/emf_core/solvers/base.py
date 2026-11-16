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
from ..sampling import (
    MAX_POINTS_PER_REQUEST,
    LatticeSampling,
    PlaneGridSampling,
    Quantity,
    Sampling,
)
from ..scene.models import Scene, StrictModel

SOLVER_INTERFACE_VERSION = 1
RESULT_FORMAT_VERSION: Literal[1] = 1

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


class FieldLineRequest(StrictModel):
    """Ask for field lines. All density levels are computed at once so that changing the
    displayed density is a visual-only operation.

    ``planar``: seeds on a circle in the plane of the referenced plane-grid sampling, around
    every source lying in that plane. ``spherical``: seeds on a sphere around every source."""

    seeding: Literal["planar", "spherical"]
    sampling_id: str  # its grid spacing sets the default guard radius around sources
    base_lines: int = Field(default=8, ge=1, le=64)  # strongest source, density level 0
    levels: int = Field(default=3, ge=1, le=4)  # level k has base_lines * 2**k lines
    guard_cells: float = Field(default=0.5, gt=0, le=4)  # guard radius in grid cells


class EquipotentialRequest(StrictModel):
    """Equipotential contour lines on a plane-grid sampling."""

    sampling_id: str
    levels_V: list[float] | None = Field(default=None, max_length=64)  # None = automatic


class IsosurfaceRequest(StrictModel):
    """Equipotential surfaces extracted on a lattice (the lattice samples are not transported)."""

    lattice: LatticeSampling
    levels_V: list[float] | None = Field(default=None, max_length=16)  # None = automatic


class SolveRequest(StrictModel):
    samplings: list[Sampling] = Field(min_length=1, max_length=8)
    quantities: list[Quantity] = Field(min_length=1)
    quality: Quality = "normal"
    # Derived geometric products (Phase 2A, additive: omitted = not computed).
    field_lines: FieldLineRequest | None = None
    equipotentials: EquipotentialRequest | None = None
    isosurfaces: IsosurfaceRequest | None = None

    @model_validator(mode="after")
    def _check(self) -> SolveRequest:
        ids = [s.id for s in self.samplings]
        if len(set(ids)) != len(ids):
            raise ValueError("sampling ids must be unique")
        if len(set(self.quantities)) != len(self.quantities):
            raise ValueError("quantities must be unique")
        by_id = {s.id: s for s in self.samplings}
        for s in self.samplings:
            if s.quantities is not None and len(set(s.quantities)) != len(s.quantities):
                raise ValueError("per-sampling quantities must be unique")
        if self.field_lines is not None:
            ref = by_id.get(self.field_lines.sampling_id)
            if ref is None or ref.kind == "points":
                raise ValueError("field_lines.sampling_id must reference a grid or lattice")
            if self.field_lines.seeding == "planar" and not isinstance(ref, PlaneGridSampling):
                raise ValueError("planar seeding needs a plane_grid sampling")
        if self.equipotentials is not None:
            ref = by_id.get(self.equipotentials.sampling_id)
            if not isinstance(ref, PlaneGridSampling):
                raise ValueError("equipotentials.sampling_id must reference a plane_grid")
        total = sum(int(np.prod(s.shape)) for s in self.samplings)
        if self.isosurfaces is not None:
            total += int(np.prod(self.isosurfaces.lattice.shape))
        if total > MAX_POINTS_PER_REQUEST:
            raise ValueError(
                f"request samples {total} points; the limit is {MAX_POINTS_PER_REQUEST}"
            )
        return self


def quantities_for(request: SolveRequest, sampling: Sampling) -> list[Quantity]:
    return sampling.quantities if sampling.quantities is not None else request.quantities


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
    source_count: int = 0  # number of non-zero point sources in the model
    # Gaussian surfaces in the request (Phase 2B-2): how many, and whether any of them has a
    # charge on its boundary (flux undefined) or failed validation.
    gauss_surfaces: int = 0
    gauss_boundary_ambiguous: bool = False
    gauss_invalid: bool = False
    # Equations whose two sides the application computes independently and compares.
    checked_equation_ids: list[str] = []
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
    # "field": a physical quantity sampled from the solver. "geometry": vertex positions or
    # directions of a derived product (field lines, contours, isosurfaces).
    kind: Literal["field", "geometry"] = "field"
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


class MethodInfo(BaseModel):
    """How a derived product was obtained. Kept separate from the physical classification of the
    field it was derived from: a numerically integrated line of an exact field is still a line
    of an exact field."""

    kind: Literal["numerical_integration", "numerical_extraction"]
    name: LocalizedText
    description: LocalizedText
    parameters: dict[str, float | int | str]
    limitations: list[LocalizedText]


FieldLineEnd = Literal["positive_charge", "negative_charge", "domain_boundary",
                       "stagnation_point", "max_length", "integration_failure"]


class FieldLineInfo(BaseModel):
    start: int  # index of the first point in the points array
    count: int  # number of points; the polyline runs along +E
    level: int  # density level this line belongs to (each level is a complete set)
    start_reason: FieldLineEnd
    end_reason: FieldLineEnd
    start_object_id: str | None = None
    end_object_id: str | None = None
    steps: int


class FieldLineSet(BaseModel):
    array: str
    seeding: Literal["planar", "spherical"]
    levels: int
    guard_radius_m: float
    # planar seeding only: True if every source lies in the seeding plane, so the lines stay in
    # that plane exactly; False means they are 3D curves that leave it.
    lines_stay_in_plane: bool | None = None
    unseeded_object_ids: list[str] = []
    lines: list[FieldLineInfo]
    end_reason_counts: dict[str, int]
    field_classification: Classification
    method: MethodInfo


class LevelRange(BaseModel):
    value_V: float
    start: int  # first segment / triangle of this level
    count: int


class EquipotentialSet(BaseModel):
    array: str  # (S, 2, 3) segment end points
    sampling_id: str
    levels: list[LevelRange]
    field_classification: Classification
    method: MethodInfo


class IsosurfaceSet(BaseModel):
    array: str  # (T, 3, 3) triangle vertices
    normals_array: str  # (T, 3, 3) unit vectors along E (towards decreasing potential)
    lattice: dict[str, Any]
    levels: list[LevelRange]
    field_classification: Classification
    method: MethodInfo


class PointSourceInfo(BaseModel):
    """One ideal point charge as a distributional source (Phase 2B-1).

    rho = sum_i q_i delta3(r - r_i), so div E = sum_i (q_i/eps0) delta3(r - r_i) and
    div D = sum_i q_i delta3(r - r_i). The weights are exact; a delta source has no finite
    pointwise value. Its distributional curl contribution is zero (there is no weight for it)."""

    object_id: str
    position_m: list[float]  # world position, metres
    charge_C: float
    div_E_weight_V_m: float  # q / eps0, the weight of delta3 in div E  [V*m]
    div_D_weight_C: float  # q, the weight of delta3 in div D  [C]
    # For every plane-grid sampling: signed distance of the charge from that plane along the
    # plane normal u x v [m], and whether it lies in the plane (|distance| <= tolerance).
    plane_distance_m: dict[str, float] = {}
    in_plane: dict[str, bool] = {}


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
    point_sources: list[PointSourceInfo] = []
    in_plane_tolerance_m: float | None = None
    field_lines: FieldLineSet | None = None
    equipotentials: EquipotentialSet | None = None
    isosurfaces: IsosurfaceSet | None = None
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
