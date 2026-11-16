"""Scene data model: the single contract shared by frontend, API and every solver.

A scene describes *what exists* (geometry, roles, sources, materials, domain). It does not say
which solver can handle it: that is decided by ``Solver.supports`` so that an unsupported
configuration is refused with a reason instead of being silently approximated.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCENE_SCHEMA_VERSION: Literal[1] = 1

Vec3 = tuple[float, float, float]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Transform(StrictModel):
    """Local transform relative to the parent object (or to the world if there is no parent).

    ``rotation_euler_xyz_rad`` uses the rotation matrix R = Rx(a) @ Ry(b) @ Rz(c), which is the
    Three.js default Euler order ``'XYZ'``. Composition: M = T @ R @ S.
    """

    position_m: Vec3 = (0.0, 0.0, 0.0)
    rotation_euler_xyz_rad: Vec3 = (0.0, 0.0, 0.0)
    scale: Vec3 = (1.0, 1.0, 1.0)

    @model_validator(mode="after")
    def _nonzero_scale(self) -> Transform:
        if any(s == 0.0 for s in self.scale):
            raise ValueError("scale components must be non-zero")
        return self


# --- Primitives (discriminated union on "type"; add new primitives here) -------------------


class PointPrimitive(StrictModel):
    type: Literal["point"] = "point"


class SpherePrimitive(StrictModel):
    type: Literal["sphere"] = "sphere"
    radius_m: PositiveFloat = 0.25


class BoxPrimitive(StrictModel):
    type: Literal["box"] = "box"
    size_m: tuple[PositiveFloat, PositiveFloat, PositiveFloat] = (0.5, 0.5, 0.5)


class CylinderPrimitive(StrictModel):
    """Axis along local z."""

    type: Literal["cylinder"] = "cylinder"
    radius_m: PositiveFloat = 0.2
    height_m: PositiveFloat = 0.6


class RingPrimitive(StrictModel):
    """Circle in the local xy plane."""

    type: Literal["ring"] = "ring"
    radius_m: PositiveFloat = 0.3


class PlanePrimitive(StrictModel):
    """Finite rectangle in the local xy plane (normal along local z)."""

    type: Literal["plane"] = "plane"
    width_m: PositiveFloat = 1.0
    height_m: PositiveFloat = 1.0


class LinePrimitive(StrictModel):
    """Straight segment along local z, centred on the local origin."""

    type: Literal["line"] = "line"
    length_m: PositiveFloat = 1.0


class GroupPrimitive(StrictModel):
    """A container with no geometry of its own: its transform applies to its children.

    ``kind = "dipole"`` marks a pair of child point charges +q and −q (two real point charges at
    a finite separation, not an ideal point dipole). The kind is an editing aid for the UI; the
    physics always comes from the child charges themselves. Added in Phase 2A (additive: scenes
    without groups are unchanged, schema_version stays 1)."""

    type: Literal["group"] = "group"
    kind: Literal["generic", "dipole"] = "generic"


Primitive = Annotated[
    GroupPrimitive | PointPrimitive | SpherePrimitive | BoxPrimitive | CylinderPrimitive
    | RingPrimitive | PlanePrimitive | LinePrimitive,
    Field(discriminator="type"),
]


class Role(StrEnum):
    """Physical role of an object. ``geometry_only`` objects are inert: they are drawn but are
    explicitly excluded from the physical model (and reported as such in every result)."""

    GEOMETRY_ONLY = "geometry_only"
    CHARGE_SOURCE = "charge_source"
    CURRENT_SOURCE = "current_source"
    CONDUCTOR = "conductor"
    DIELECTRIC = "dielectric"
    MAGNETIC_MATERIAL = "magnetic_material"


# --- Sources (discriminated union on "type") ------------------------------------------------


class PointChargeSource(StrictModel):
    """Ideal point charge q located at the object's world position."""

    type: Literal["point_charge"] = "point_charge"
    charge_C: FiniteFloat = 1e-9


Source = Annotated[PointChargeSource, Field(discriminator="type")]


# --- Materials: constitutive models are first-class, never implied ----------------------------


class MaterialModel(StrEnum):
    VACUUM = "vacuum"  # D = eps0 E, B = mu0 H, sigma = 0
    LINEAR_DIELECTRIC = "linear_dielectric"  # D = eps0 eps_r E
    LINEAR_MAGNETIC = "linear_magnetic"  # B = mu0 mu_r H
    OHMIC_CONDUCTOR = "ohmic_conductor"  # J = sigma E
    PERFECT_CONDUCTOR = "perfect_conductor"


class Material(StrictModel):
    id: str = Field(min_length=1)
    name: str = ""
    model: MaterialModel = MaterialModel.VACUUM
    relative_permittivity: PositiveFloat = 1.0
    relative_permeability: PositiveFloat = 1.0
    conductivity_S_per_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0

    @model_validator(mode="after")
    def _vacuum_is_vacuum(self) -> Material:
        if self.model is MaterialModel.VACUUM and (
            self.relative_permittivity != 1.0
            or self.relative_permeability != 1.0
            or self.conductivity_S_per_m != 0.0
        ):
            raise ValueError("a vacuum material must have eps_r = 1, mu_r = 1, sigma = 0")
        return self


class BoundaryCondition(StrictModel):
    """Boundary condition attached to an object or to the domain boundary.

    No Phase 1 solver evaluates boundary conditions; a scene that contains one is refused."""

    id: str = Field(min_length=1)
    type: Literal["fixed_potential", "ground", "pec", "absorbing", "periodic"]
    target_object_id: str | None = None
    potential_V: FiniteFloat | None = None


class SceneObject(StrictModel):
    id: str = Field(min_length=1)
    name: str = ""
    primitive: Primitive
    transform: Transform = Transform()
    parent_id: str | None = None
    role: Role = Role.GEOMETRY_ONLY
    source: Source | None = None
    material_id: str | None = None
    enabled: bool = True


class Domain(StrictModel):
    """Axis-aligned region of interest. It bounds sampling and visualization; the Phase 1
    analytical model itself is unbounded (potential reference at infinity)."""

    min_m: Vec3 = (-2.0, -2.0, -2.0)
    max_m: Vec3 = (2.0, 2.0, 2.0)
    background_material_id: str = "vacuum"
    potential_reference: Literal["infinity"] = "infinity"

    @model_validator(mode="after")
    def _ordered(self) -> Domain:
        if any(hi <= lo for lo, hi in zip(self.min_m, self.max_m, strict=True)):
            raise ValueError("domain max must be strictly greater than min on every axis")
        return self

    @property
    def diagonal_m(self) -> float:
        return math.dist(self.min_m, self.max_m)


def _default_materials() -> list[Material]:
    return [Material(id="vacuum", name="Vacuum", model=MaterialModel.VACUUM)]


class Scene(StrictModel):
    schema_version: Literal[1] = SCENE_SCHEMA_VERSION
    # "3d" is a full 3D model. The 2D kinds are true two-dimensional mathematical models
    # (invariance along the omitted dimension); they are declared here so the distinction is
    # explicit in the contract, and are refused by solvers that do not implement them.
    dimensionality: Literal["3d", "2d_planar", "2d_axisymmetric"] = "3d"
    objects: list[SceneObject] = []
    materials: list[Material] = Field(default_factory=_default_materials)
    boundaries: list[BoundaryCondition] = []
    domain: Domain = Domain()

    @model_validator(mode="after")
    def _consistent(self) -> Scene:
        ids = [o.id for o in self.objects]
        if len(set(ids)) != len(ids):
            raise ValueError("object ids must be unique")
        mat_ids = [m.id for m in self.materials]
        if len(set(mat_ids)) != len(mat_ids):
            raise ValueError("material ids must be unique")
        if self.domain.background_material_id not in mat_ids:
            raise ValueError("domain.background_material_id does not reference a material")
        by_id = {o.id: o for o in self.objects}
        for o in self.objects:
            if o.material_id is not None and o.material_id not in mat_ids:
                raise ValueError(f"object '{o.id}' references unknown material '{o.material_id}'")
            seen = {o.id}
            cur = o
            while cur.parent_id is not None:
                if cur.parent_id not in by_id:
                    raise ValueError(f"object '{cur.id}' references unknown parent")
                if cur.parent_id in seen:
                    raise ValueError(f"object hierarchy contains a cycle at '{cur.parent_id}'")
                seen.add(cur.parent_id)
                cur = by_id[cur.parent_id]
        for b in self.boundaries:
            if b.target_object_id is not None and b.target_object_id not in by_id:
                raise ValueError(f"boundary '{b.id}' references unknown object")
        return self

    def material(self, material_id: str) -> Material:
        return next(m for m in self.materials if m.id == material_id)
