"""Prescribed rigid-body motion of measurement conductors (Phase 4B).

A conductor has a reference geometry in its local frame and a time-dependent pose in world
coordinates:

    r_world(t) = R(t) r_local + c(t),   R(t) = R_rot(t) R0,   c(t) = c0 + d(t)

where c0 and R0 are the stored (reference) centre and orientation, d(t) is the translation
profile and R_rot(t) the rotation profile, a rotation about an axis through the moving centre
c(t). The local material velocity of a conductor point is

    u(r, t) = V(t) + omega(t) × (r − c(t)),   V = dc/dt,   omega: angular velocity (world)

with the right-hand rule for omega. Every velocity is analytical (never a difference of
rendered frames) and the independent variable is the simulation time.

Translation profiles (world vectors):

* stationary:            d = 0.
* constant_velocity:     d = V0 (t − t0).
* constant_acceleration: d = V0 (t − t0) + a (t − t0)^2 / 2.
* sinusoidal:            d = A sin(2 pi f t + phi) e_axis   (c0 is the centre of oscillation).

Rotation profiles: none, or constant_angular_velocity: theta = omega (t − t0) about the unit
axis (signed omega, right-hand rule), so that R_rot(t0) = 1.

Every moving profile may be restricted to an active window [t_start, t_end] (either end
optional). Outside the window the pose is held (the profile is evaluated at the clamped time)
and the velocity is zero. Where the velocity jumps (window ends) the left and right limits
differ and the instantaneous velocity is not uniquely defined; both are returned.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import Field, model_validator

from ._base import FiniteFloat, PositiveFloat, StrictModel

Arr = NDArray[np.float64]
Vec = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
MAX_MOTION_FREQUENCY_HZ = 1e6
SPEED_OF_LIGHT = 299_792_458.0  # m/s


class _Window(StrictModel):
    t_start_s: FiniteFloat | None = Field(default=None, exclude_if=lambda v: v is None)
    t_end_s: FiniteFloat | None = Field(default=None, exclude_if=lambda v: v is None)

    @model_validator(mode="after")
    def _window(self) -> _Window:
        if self.t_start_s is not None and self.t_end_s is not None \
                and not self.t_end_s > self.t_start_s:
            raise ValueError("motion window: t_end_s must be later than t_start_s")
        return self

    def lo(self) -> float:
        return -math.inf if self.t_start_s is None else float(self.t_start_s)

    def hi(self) -> float:
        return math.inf if self.t_end_s is None else float(self.t_end_s)

    def clamp(self, t: float) -> float:
        return min(max(t, self.lo()), self.hi())

    def active(self, t: float, side: Literal["left", "right"]) -> bool:
        """Whether the motion is running just before (left) or just after (right) t."""
        if side == "right":
            return self.lo() <= t < self.hi()
        return self.lo() < t <= self.hi()

    def corners(self) -> list[float]:
        return [x for x in (self.t_start_s, self.t_end_s) if x is not None]


def _nonzero(v: Vec, what: str) -> None:
    if not math.isfinite(math.hypot(*v)) or math.hypot(*v) == 0.0:
        raise ValueError(f"{what} must be a non-zero finite vector")


class StationaryTranslation(StrictModel):
    type: Literal["stationary"] = "stationary"


class ConstantVelocity(_Window):
    type: Literal["constant_velocity"] = "constant_velocity"
    velocity_m_per_s: Vec = (0.0, 0.0, 0.0)
    t0_s: FiniteFloat = 0.0


class ConstantAcceleration(_Window):
    type: Literal["constant_acceleration"] = "constant_acceleration"
    velocity_m_per_s: Vec = (0.0, 0.0, 0.0)  # V0 at t0
    acceleration_m_per_s2: Vec = (0.0, 0.0, 0.0)
    t0_s: FiniteFloat = 0.0


class SinusoidalTranslation(_Window):
    type: Literal["sinusoidal"] = "sinusoidal"
    amplitude_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.01
    axis: Vec = (1.0, 0.0, 0.0)
    frequency_Hz: Annotated[PositiveFloat, Field(le=MAX_MOTION_FREQUENCY_HZ)] = 1.0
    phase_rad: FiniteFloat = 0.0

    @model_validator(mode="after")
    def _axis(self) -> SinusoidalTranslation:
        _nonzero(self.axis, "sinusoidal translation: axis")
        return self


Translation = Annotated[StationaryTranslation | ConstantVelocity | ConstantAcceleration
                       | SinusoidalTranslation, Field(discriminator="type")]
TranslationModel = (StationaryTranslation | ConstantVelocity | ConstantAcceleration
                    | SinusoidalTranslation)


class NoRotation(StrictModel):
    type: Literal["none"] = "none"


class ConstantAngularVelocity(_Window):
    type: Literal["constant_angular_velocity"] = "constant_angular_velocity"
    axis: Vec = (0.0, 0.0, 1.0)  # world direction, normalized internally
    omega_rad_per_s: FiniteFloat = 1.0  # signed, right-hand rule about the axis
    t0_s: FiniteFloat = 0.0

    @model_validator(mode="after")
    def _axis(self) -> ConstantAngularVelocity:
        _nonzero(self.axis, "rotation axis")
        if abs(self.omega_rad_per_s) / (2 * math.pi) > MAX_MOTION_FREQUENCY_HZ:
            raise ValueError("rotation: |omega| / 2 pi exceeds the supported frequency")
        return self


Rotation = Annotated[NoRotation | ConstantAngularVelocity, Field(discriminator="type")]
RotationModel = NoRotation | ConstantAngularVelocity


class MotionProfile(StrictModel):
    """Rigid motion of a measurement conductor relative to its reference pose."""

    translation: Translation = Field(default_factory=StationaryTranslation)
    rotation: Rotation = Field(default_factory=NoRotation)


VelocityConvention = Literal["undefined", "left", "right"]


def _unit(v: Vec) -> Arr:
    a = np.asarray(v, np.float64)
    out: Arr = a / np.linalg.norm(a)
    return out


def displacement(tr: TranslationModel, t: float) -> Arr:
    """d(t) of a translation profile (world, metres)."""
    if isinstance(tr, StationaryTranslation):
        return np.zeros(3)
    tc = tr.clamp(t)
    if isinstance(tr, ConstantVelocity):
        out: Arr = np.asarray(tr.velocity_m_per_s, float) * (tc - tr.t0_s)
        return out
    if isinstance(tr, ConstantAcceleration):
        dt = tc - tr.t0_s
        out = (np.asarray(tr.velocity_m_per_s, float) * dt
               + 0.5 * np.asarray(tr.acceleration_m_per_s2, float) * dt * dt)
        return out
    out = tr.amplitude_m * math.sin(2 * math.pi * tr.frequency_Hz * tc + tr.phase_rad) \
        * _unit(tr.axis)
    return out


def velocity(tr: TranslationModel, t: float, side: Literal["left", "right"]) -> Arr:
    """V = dd/dt from the left or the right (analytical)."""
    if isinstance(tr, StationaryTranslation) or not tr.active(t, side):
        return np.zeros(3)
    if isinstance(tr, ConstantVelocity):
        return np.asarray(tr.velocity_m_per_s, float)
    if isinstance(tr, ConstantAcceleration):
        out: Arr = (np.asarray(tr.velocity_m_per_s, float)
                    + np.asarray(tr.acceleration_m_per_s2, float) * (t - tr.t0_s))
        return out
    w = 2 * math.pi * tr.frequency_Hz
    out = tr.amplitude_m * w * math.cos(w * t + tr.phase_rad) * _unit(tr.axis)
    return out


def rodrigues(axis: Arr, theta: float) -> Arr:
    """Rotation matrix about a unit axis by theta (right-hand rule)."""
    k = np.array([[0.0, -axis[2], axis[1]], [axis[2], 0.0, -axis[0]],
                  [-axis[1], axis[0], 0.0]])
    out: Arr = np.eye(3) + math.sin(theta) * k + (1.0 - math.cos(theta)) * (k @ k)
    return out


def rotation(rot: RotationModel, t: float) -> Arr:
    if isinstance(rot, NoRotation):
        return np.eye(3)
    return rodrigues(_unit(rot.axis), rot.omega_rad_per_s * (rot.clamp(t) - rot.t0_s))


def angular_velocity(rot: RotationModel, t: float, side: Literal["left", "right"]) -> Arr:
    if isinstance(rot, NoRotation) or not rot.active(t, side):
        return np.zeros(3)
    out: Arr = rot.omega_rad_per_s * _unit(rot.axis)
    return out


def corners(m: MotionProfile) -> list[float]:
    """Times at which the velocity may jump."""
    out: list[float] = []
    for part in (m.translation, m.rotation):
        if isinstance(part, _Window):
            out += part.corners()
    return sorted(set(out))


def time_scale(m: MotionProfile, length_m: float) -> float:
    """Characteristic time over which the pose changes appreciably (s; inf if never), used to
    choose finite-difference steps in time (never a physical result)."""
    out = math.inf
    tr, rot = m.translation, m.rotation
    if isinstance(rot, ConstantAngularVelocity) and rot.omega_rad_per_s != 0.0:
        out = min(out, 1.0 / abs(rot.omega_rad_per_s))
    if isinstance(tr, SinusoidalTranslation) and tr.amplitude_m > 0:
        out = min(out, 1.0 / (2 * math.pi * tr.frequency_Hz),
                  length_m / (2 * math.pi * tr.frequency_Hz * tr.amplitude_m))
    if isinstance(tr, ConstantVelocity | ConstantAcceleration):
        v = float(np.linalg.norm(tr.velocity_m_per_s))
        if v > 0:
            out = min(out, length_m / v)
    if isinstance(tr, ConstantAcceleration):
        a = float(np.linalg.norm(tr.acceleration_m_per_s2))
        if a > 0:
            out = min(out, math.sqrt(length_m / a))
    return out


@dataclass(frozen=True)
class Pose:
    """Instantaneous pose and velocity of a rigid conductor."""

    t_s: float
    center: Arr  # c(t)
    rotation: Arr  # R(t) = R_rot(t) R0, columns: local axes in world coordinates
    velocity_left: Arr
    velocity_right: Arr
    omega_left: Arr
    omega_right: Arr

    @property
    def unique(self) -> bool:
        return bool(np.array_equal(self.velocity_left, self.velocity_right)
                    and np.array_equal(self.omega_left, self.omega_right))

    def velocity(self, side: Literal["left", "right"]) -> Arr:
        return self.velocity_left if side == "left" else self.velocity_right

    def omega(self, side: Literal["left", "right"]) -> Arr:
        return self.omega_left if side == "left" else self.omega_right

    def material_velocity(self, points: Arr, side: Literal["left", "right"]) -> Arr:
        """u(r) = V + omega × (r − c) at world points (N, 3)."""
        out: Arr = self.velocity(side)[None, :] + np.cross(self.omega(side)[None, :],
                                                           points - self.center[None, :])
        return out


def pose(m: MotionProfile, c0: Arr, r0: Arr, t: float) -> Pose:
    c = np.asarray(c0, float) + displacement(m.translation, t)
    rot = rotation(m.rotation, t) @ np.asarray(r0, float)
    return Pose(float(t), c, rot,
                velocity(m.translation, t, "left"), velocity(m.translation, t, "right"),
                angular_velocity(m.rotation, t, "left"), angular_velocity(m.rotation, t, "right"))


def resolve_side(unique: bool, convention: VelocityConvention
                 ) -> Literal["left", "right"] | None:
    """The one-sided velocity to use: either side where the velocity is unique; the selected
    convention at a jump; None (undefined) at a jump without a convention."""
    if unique:
        return "right"
    if convention == "undefined":
        return None
    return convention
