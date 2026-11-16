from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from emf_core.equations import EquationView
from emf_core.i18n import LocalizedText
from emf_core.scene.models import Scene, Vec3
from emf_core.solvers import SolverDescriptor, SolveRequest
from emf_core.solvers.base import Classification


class SimulationBody(BaseModel):
    scene: Scene
    request: SolveRequest


class ErrorBody(BaseModel):
    code: Literal["unsupported", "solver_failed", "too_large", "unavailable", "not_found",
                  "not_ready"]
    message: str
    reasons: list[LocalizedText] = []


class ProbeBody(BaseModel):
    scene: Scene
    point_m: Vec3


class ProbeValue(BaseModel):
    quantity: str
    symbol: str
    unit: str
    value: list[float] | float | None  # None where the quantity is undefined (singularity)
    magnitude: float | None = None


class ProbeContribution(BaseModel):
    """Field of one source at the probe point (one term of the superposition sums)."""

    object_id: str
    name: str
    charge_C: float
    distance_m: float
    E_V_per_m: list[float] | None
    E_magnitude_V_per_m: float | None
    phi_V: float | None


class ProbeResponse(BaseModel):
    point_m: Vec3
    solver_id: str
    solver_version: str
    classification: Classification
    defined: bool
    # Position tolerance below which the probe is considered to sit *on* a point charge.
    singular_tolerance_m: float
    singular_object_id: str | None = None
    values: list[ProbeValue]
    contributions: list[ProbeContribution]


class EquationsBody(BaseModel):
    scene: Scene


class EquationsResponse(BaseModel):
    supported: bool
    solver_id: str | None
    unsupported_reasons: list[LocalizedText]
    equations: list[EquationView]


class SolverStatus(BaseModel):
    descriptor: SolverDescriptor
    in_process: bool  # runs inside the API for interactive requests
    queue_worker_online: bool  # a live worker is consuming this solver's queue


class ComponentHealth(BaseModel):
    ok: bool
    detail: str | None = None


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: ComponentHealth
    redis: ComponentHealth


class JobCreated(BaseModel):
    job_id: str
    queue: str


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scene: Scene
    view: dict[str, Any] = {}


class ProjectSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class ProjectOut(ProjectSummary):
    scene: Scene
    view: dict[str, Any]
