"""Where a field is evaluated. A sampling yields an (N, 3) float64 point array plus a shape."""

from __future__ import annotations

from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from .scene.models import StrictModel, Vec3

MAX_POINTS_PER_REQUEST = 2_000_000
SamplingId = Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_]+$")]


class PlaneGridSampling(StrictModel):
    """Regular grid on a planar cross-section through the 3D configuration.

    Point (i, j) = center + (u_i) * u_dir + (v_j) * v_dir with u_i, v_j spanning
    [-extent/2, +extent/2] inclusive. Arrays are stored row-major with shape (nv, nu[, 3])."""

    kind: Literal["plane_grid"] = "plane_grid"
    id: SamplingId
    center_m: Vec3 = (0.0, 0.0, 0.0)
    u_dir: Vec3 = (1.0, 0.0, 0.0)
    v_dir: Vec3 = (0.0, 1.0, 0.0)
    u_extent_m: float = Field(gt=0)
    v_extent_m: float = Field(gt=0)
    nu: int = Field(ge=2, le=1024)
    nv: int = Field(ge=2, le=1024)

    @model_validator(mode="after")
    def _orthonormal(self) -> PlaneGridSampling:
        u, v = np.asarray(self.u_dir), np.asarray(self.v_dir)
        if abs(np.linalg.norm(u) - 1) > 1e-9 or abs(np.linalg.norm(v) - 1) > 1e-9:
            raise ValueError("u_dir and v_dir must be unit vectors")
        if abs(float(u @ v)) > 1e-9:
            raise ValueError("u_dir and v_dir must be orthogonal")
        return self

    @property
    def shape(self) -> tuple[int, ...]:
        return (self.nv, self.nu)

    def points(self) -> NDArray[np.float64]:
        us = np.linspace(-self.u_extent_m / 2, self.u_extent_m / 2, self.nu)
        vs = np.linspace(-self.v_extent_m / 2, self.v_extent_m / 2, self.nv)
        uu, vv = np.meshgrid(us, vs, indexing="xy")  # shape (nv, nu)
        pts = (
            np.asarray(self.center_m, np.float64)
            + uu[..., None] * np.asarray(self.u_dir, np.float64)
            + vv[..., None] * np.asarray(self.v_dir, np.float64)
        )
        return pts.reshape(-1, 3)


class LatticeSampling(StrictModel):
    """Regular axis-aligned 3D lattice, inclusive of both ends. Shape (nz, ny, nx[, 3])."""

    kind: Literal["lattice"] = "lattice"
    id: SamplingId
    min_m: Vec3
    max_m: Vec3
    nx: int = Field(ge=2, le=256)
    ny: int = Field(ge=2, le=256)
    nz: int = Field(ge=2, le=256)

    @model_validator(mode="after")
    def _ordered(self) -> LatticeSampling:
        if any(hi <= lo for lo, hi in zip(self.min_m, self.max_m, strict=True)):
            raise ValueError("lattice max must be greater than min on every axis")
        return self

    @property
    def shape(self) -> tuple[int, ...]:
        return (self.nz, self.ny, self.nx)

    def points(self) -> NDArray[np.float64]:
        xs = np.linspace(self.min_m[0], self.max_m[0], self.nx)
        ys = np.linspace(self.min_m[1], self.max_m[1], self.ny)
        zs = np.linspace(self.min_m[2], self.max_m[2], self.nz)
        zz, yy, xx = np.meshgrid(zs, ys, xs, indexing="ij")
        return np.stack([xx, yy, zz], axis=-1).reshape(-1, 3)


class PointsSampling(StrictModel):
    kind: Literal["points"] = "points"
    id: SamplingId
    points_m: list[Vec3] = Field(min_length=1, max_length=100_000)

    @property
    def shape(self) -> tuple[int, ...]:
        return (len(self.points_m),)

    def points(self) -> NDArray[np.float64]:
        return np.asarray(self.points_m, dtype=np.float64).reshape(-1, 3)


Sampling = Annotated[
    PlaneGridSampling | LatticeSampling | PointsSampling, Field(discriminator="kind")
]
