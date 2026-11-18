"""Lorentz force on a test charge and nonrelativistic test-particle trajectories (Phase 4B).

    F = q (E + v × B),   F_E = q E,   F_B = q v × B

v is the test particle's laboratory-frame velocity (never a conductor velocity u). E is the sum
of the electrostatic field of the point charges (Phase 2A solver) and, for time-varying
currents, the induced field E_ind = −∂A/∂t (Phase 4A); B is the magnetostatic solver's field
at the instantaneous currents. Where E_ind is not available for a time-varying source (infinite
wire, ideal toroid), the electric force and the total force are reported as partial.

The trajectory of a test particle (it does not change any field; no radiation reaction, no
self-field, no particle interactions, no relativistic corrections) obeys

    m dv/dt = q (E(r, t) + v × B(r, t)),   dr/dt = v

and is integrated with the Boris scheme in drift–kick–rotate–kick–drift form: the fields are
evaluated at the half-step position and the half-step time (time-centred), the electric field
gives two half kicks and the magnetic field an exact-norm rotation, so a magnetic-only field
keeps |v| (the kinetic energy) constant to rounding. The step is limited by the local
gyrofrequency (ω_c Δt ≤ η), by the distance to the nearest filament or point charge
(|v| Δt ≤ η d, so the particle never jumps over a singular region), by the electric
acceleration, by the current profiles' time scale and corner times, and by the time range.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, model_validator

from .i18n import L, LocalizedText
from .scene._base import FiniteFloat, PositiveFloat, StrictModel
from .scene.currents import CurrentSources, current_sources
from .scene.models import Scene
from .scene.motion import SPEED_OF_LIGHT
from .scene.profiles import corners as profile_corners
from .scene.timedep import at_time, rates, time_state
from .solvers.analytical import electrostatics as es
from .solvers.analytical import magnetostatics as ms

Arr = NDArray[np.float64]
Vec = tuple[FiniteFloat, FiniteFloat, FiniteFloat]
RELATIVISTIC_WARN = 0.01  # |v|/c above this: nonrelativistic accuracy degrades noticeably
RELATIVISTIC_BAD = 0.1
MAX_OUTPUT = 4000  # trajectory samples returned (every step is integrated)


class TrajectorySettings(StrictModel):
    """Trajectory controls of a test charge (persisted with a project)."""

    enabled: bool = False
    start_s: FiniteFloat = 0.0
    end_s: FiniteFloat = 1e-6
    tolerance: Annotated[float, Field(ge=1e-5, le=0.5)] = 0.02
    max_steps: Annotated[int, Field(ge=10, le=200_000)] = 20_000
    show_trail: bool = True  # display only
    show_forces: bool = True  # display only


class TestCharge(StrictModel):
    """A test charge (Phase 4B): the Lorentz-force probe (charge, laboratory-frame velocity,
    position) and the initial state and controls of its optional trajectory."""

    __test__ = False  # not a pytest class
    enabled: bool = True
    charge_C: FiniteFloat = 1.602176634e-19
    mass_kg: PositiveFloat = 1.67262192369e-27
    position_m: Vec = (0.0, 0.0, 0.0)
    velocity_m_per_s: Vec = (1.0e5, 0.0, 0.0)
    trajectory: TrajectorySettings = Field(default_factory=TrajectorySettings)


class LorentzRequest(StrictModel):
    charge_C: FiniteFloat
    velocity_m_per_s: Vec
    point_m: Vec
    time_s: FiniteFloat = 0.0


class LorentzResult(BaseModel):
    status: Literal["complete", "partial", "singular"]
    status_reason: LocalizedText | None = None
    time_s: float
    point_m: list[float]
    charge_C: float
    velocity_m_per_s: list[float]
    speed_m_per_s: float
    E_static_V_per_m: list[float] | None
    E_ind_V_per_m: list[float] | None  # None: not evaluated (unsupported or singular)
    e_ind_supported: bool
    E_V_per_m: list[float] | None  # E_static + E_ind (None if any part is undefined)
    B_T: list[float] | None
    F_E_N: list[float] | None
    F_B_N: list[float] | None
    F_total_N: list[float] | None
    F_E_magnitude_N: float | None
    F_B_magnitude_N: float | None
    F_total_magnitude_N: float | None
    power_E_W: float | None  # q E · v
    power_B_W: float | None  # q (v × B) · v: zero within rounding
    power_total_W: float | None
    power_B_bound_W: float | None  # rounding bound of power_B
    warnings: list[LocalizedText] = []


# ----------------------------------------------------------------------------- fields


@dataclass
class FieldSample:
    e: Arr  # electrostatic + induced (NaN where undefined)
    e_static: Arr
    e_ind: Arr | None  # None: unsupported at this time
    b: Arr
    singular: bool
    distance: float  # to the nearest filament or point charge (inf if none)


class SceneFields:
    """E and B of a scene at points and times, from the existing solvers only."""

    def __init__(self, scene: Scene) -> None:
        self.scene = scene
        self.cs: CurrentSources = current_sources(scene)
        self.r_min = ms.COINCIDENCE_FACTOR * scene.domain.diagonal_m
        self.es_r_min = es.COINCIDENCE_FACTOR * scene.domain.diagonal_m
        _, self.q_pos, self.q_val = es.point_charge_table(scene)
        self._t: float | None = None
        self._static = False
        by_id = {o.id: o for o in scene.objects}
        corner_set: set[float] = set()
        scale = math.inf
        for oid in self.cs.ids:
            prof = getattr(by_id[oid].source, "profile", None) if oid in by_id else None
            if prof is None:
                continue
            corner_set.update(profile_corners(prof))
            if prof.type == "sinusoidal" and prof.peak_A > 0:
                scale = min(scale, 1.0 / (2 * math.pi * prof.frequency_Hz))
        self.corners = sorted(corner_set)
        self.time_scale = scale

    def _at(self, t: float) -> None:
        # Scenes without time-dependent currents: the source set is the same at every time.
        if self._t == t or (self._t is not None and self._static):
            return
        ts = time_state(self.scene, self.cs, t)
        self._static = not ts.time_dependent
        self._cs_t = at_time(self.cs, ts)
        self._cs_rate = rates(self.cs, ts)
        self._varying = any(s.varying for s in ts.sources)
        self._e_ind_ok = not ts.unsupported_ids
        self._unsupported = ts.unsupported_ids
        self._t = t

    def unsupported(self, t: float) -> list[str]:
        self._at(t)
        return list(self._unsupported)

    def sample(self, p: Arr, t: float) -> FieldSample:
        self._at(t)
        pts = p[None, :]
        ev = ms.evaluate_bh(pts, self._cs_t, self.r_min, ms.MAGNET_RTOL["probe"])
        b = ev.b[0]
        singular = bool(ev.status[0] == ms.ST_SINGULAR) or not np.all(np.isfinite(b))
        if len(self.q_val):
            e_s = es.evaluate(pts, self.q_pos, self.q_val, self.es_r_min)[0][0]
        else:
            e_s = np.zeros(3)
        singular |= not np.all(np.isfinite(e_s))
        e_ind: Arr | None
        if not self._varying:
            e_ind = np.zeros(3)
        elif self._e_ind_ok:
            e_ind = -ms.loops_vector_potential(self._cs_rate.loops, pts)[0][0]
        else:
            e_ind = None
        d = math.inf
        if self.cs.wires or self.cs.loops:
            d = float(ms.nearest_filament(pts, self.cs)[0][0])
        if len(self.q_val):
            d = min(d, float(np.linalg.norm(self.q_pos - p, axis=1).min()))
        e = e_s + (e_ind if e_ind is not None else np.full(3, np.nan))
        return FieldSample(e, e_s, e_ind, b, singular, d)


def _vec(a: Arr | None) -> list[float] | None:
    return None if a is None or not np.all(np.isfinite(a)) else [float(x) for x in a]


def _relativistic(speed: float) -> list[LocalizedText]:
    beta = speed / SPEED_OF_LIGHT
    if beta <= RELATIVISTIC_WARN:
        return []
    return [L(f"The speed is {beta:.3g} c: the nonrelativistic force law and Newton's equation "
              "lose accuracy" + (" substantially." if beta > RELATIVISTIC_BAD else "."),
              f"A sebesség {beta:.3g} c: a nemrelativisztikus erőtörvény és a Newton-egyenlet "
              "pontossága csökken" + (" jelentősen." if beta > RELATIVISTIC_BAD else "."))]


def lorentz_probe(scene: Scene, req: LorentzRequest) -> LorentzResult:
    f = SceneFields(scene)
    p = np.asarray(req.point_m, float)
    v = np.asarray(req.velocity_m_per_s, float)
    q = float(req.charge_C)
    s = f.sample(p, req.time_s)
    speed = float(np.linalg.norm(v))
    base = {"time_s": req.time_s, "point_m": [float(x) for x in p], "charge_C": q,
            "velocity_m_per_s": [float(x) for x in v], "speed_m_per_s": speed,
            "e_ind_supported": s.e_ind is not None, "warnings": _relativistic(speed)}
    if speed >= SPEED_OF_LIGHT:
        base["warnings"] = [L("The speed is not below c: the nonrelativistic force law does not "
                              "apply.", "A sebesség nem kisebb c-nél: a nemrelativisztikus "
                              "erőtörvény nem alkalmazható.")]
    if s.singular:
        return LorentzResult(**base, status="singular", status_reason=L(
            "The point lies on a current filament or a point charge: the field, and so the "
            "force, is undefined there.",
            "A pont áramszálon vagy ponttöltésen fekszik: ott a tér, így az erő sem "
            "értelmezett."),
            E_static_V_per_m=_vec(s.e_static), E_ind_V_per_m=None, E_V_per_m=None, B_T=None,
            F_E_N=None, F_B_N=None, F_total_N=None, F_E_magnitude_N=None,
            F_B_magnitude_N=None, F_total_magnitude_N=None, power_E_W=None, power_B_W=None,
            power_total_W=None, power_B_bound_W=None)
    f_b = q * np.cross(v, s.b)
    p_b = float(f_b @ v)
    bound = 8 * np.finfo(float).eps * abs(q) * speed**2 * float(np.linalg.norm(s.b))
    if s.e_ind is None:
        return LorentzResult(
            **base, status="partial", status_reason=L(
                "A source without a vector potential (infinite wire or ideal toroid) changes at "
                "this time: E_ind is not evaluated, so the electric and total forces are "
                "incomplete. The magnetic force is complete.",
                "Vektorpotenciál nélküli forrás (végtelen vezető vagy ideális toroid) változik "
                "ebben az időpontban: E_ind nincs kiértékelve, így az elektromos és a teljes erő "
                "hiányos. A mágneses erő teljes."),
            E_static_V_per_m=_vec(s.e_static), E_ind_V_per_m=None, E_V_per_m=None,
            B_T=_vec(s.b), F_E_N=None, F_B_N=_vec(f_b), F_total_N=None,
            F_E_magnitude_N=None, F_B_magnitude_N=float(np.linalg.norm(f_b)),
            F_total_magnitude_N=None, power_E_W=None,
            power_B_W=p_b, power_total_W=None, power_B_bound_W=bound)
    f_e = q * s.e
    f_t = f_e + f_b
    p_e = float(f_e @ v)
    return LorentzResult(
        **base, status="complete", E_static_V_per_m=_vec(s.e_static),
        E_ind_V_per_m=_vec(s.e_ind), E_V_per_m=_vec(s.e), B_T=_vec(s.b), F_E_N=_vec(f_e),
        F_B_N=_vec(f_b), F_total_N=_vec(f_t), F_E_magnitude_N=float(np.linalg.norm(f_e)),
        F_B_magnitude_N=float(np.linalg.norm(f_b)), F_total_magnitude_N=float(np.linalg.norm(f_t)),
        power_E_W=p_e, power_B_W=p_b, power_total_W=p_e + p_b, power_B_bound_W=bound)


# ------------------------------------------------------------------------- trajectory


class ParticleRequest(StrictModel):
    charge_C: FiniteFloat
    mass_kg: PositiveFloat
    position_m: Vec
    velocity_m_per_s: Vec
    start_s: FiniteFloat = 0.0
    end_s: FiniteFloat = 1e-6
    # Largest rotation angle ω_c Δt and fraction η of the distance to a singularity per step.
    tolerance: Annotated[float, Field(ge=1e-5, le=0.5)] = 0.02
    max_steps: Annotated[int, Field(ge=10, le=200_000)] = 20_000

    @model_validator(mode="after")
    def _order(self) -> ParticleRequest:
        if not self.end_s > self.start_s:
            raise ValueError("particle: end_s must be later than start_s")
        if math.hypot(*self.velocity_m_per_s) >= SPEED_OF_LIGHT:
            raise ValueError("particle: the initial speed must be below c")
        return self


TrajectoryStatus = Literal["completed", "max_steps", "singular", "unsupported", "invalid"]


class TrajectorySample(BaseModel):
    t_s: float
    position_m: list[float]
    velocity_m_per_s: list[float]
    speed_m_per_s: float
    kinetic_energy_J: float
    F_E_N: list[float] | None = None  # at the sample point and time
    F_B_N: list[float] | None = None
    F_total_N: list[float] | None = None


class TrajectoryResult(BaseModel):
    status: TrajectoryStatus
    status_reason: LocalizedText | None = None
    method: LocalizedText
    steps: int
    samples: list[TrajectorySample]
    min_step_s: float | None = None
    max_step_s: float | None = None
    end_time_s: float
    magnetic_only: bool  # E = 0 along the whole path: kinetic energy must stay constant
    energy_relative_change: float | None  # (K_end − K_start) / K_start
    gyrofrequency_rad_per_s: float | None  # |q| |B| / m at the start
    gyroradius_m: float | None  # m v_perp / (|q| |B|) at the start
    gyroperiod_s: float | None
    max_speed_fraction_c: float
    warnings: list[LocalizedText] = []


FieldFn = Callable[[Arr, float], FieldSample]


@dataclass
class PushOutput:
    t: list[float]
    x: list[Arr]
    v: list[Arr]
    status: TrajectoryStatus
    reason: LocalizedText | None
    dts: list[float]
    magnetic_only: bool


def boris(field: FieldFn, q: float, m: float, x0: Arr, v0: Arr, t0: float, t1: float, eta: float,
          max_steps: int, time_scale: float = math.inf, corners: list[float] | None = None,
          unsupported: Callable[[float], list[str]] | None = None) -> PushOutput:
    """Integrate the Newton–Lorentz equation with the Boris scheme (see the module docstring).
    Every step is recorded; the step size is chosen from the field at the current position."""
    qm = q / m
    x = np.asarray(x0, float).copy()
    v = np.asarray(v0, float).copy()
    t = float(t0)
    ts, xs, vs = [t], [x.copy()], [v.copy()]
    dts: list[float] = []
    corners = sorted(c for c in (corners or []) if t0 < c < t1)
    magnetic_only = True
    span = t1 - t0
    s = field(x, t)
    for _ in range(max_steps):
        if t >= t1:
            return PushOutput(ts, xs, vs, "completed", None, dts, magnetic_only)
        if s.singular or not np.all(np.isfinite(s.b)) or not np.all(np.isfinite(s.e_static)):
            return PushOutput(ts, xs, vs, "singular", L(
                "The particle reached a current filament or a point charge, where the field is "
                "singular; the integration stopped there.",
                "A részecske áramszálhoz vagy ponttöltéshez ért, ahol a tér szinguláris; az "
                "integrálás ott leállt."), dts, magnetic_only)
        if s.e_ind is None:
            bad = unsupported(t) if unsupported else []
            return PushOutput(ts, xs, vs, "unsupported", L(
                f"{', '.join(bad)} changes in time and has no induced field E_ind in this model "
                "(infinite wire or ideal toroid): the force is incomplete, so the integration "
                "stopped.",
                f"{', '.join(bad)} időben változik, és ebben a modellben nincs indukált tere "
                "(végtelen vezető vagy ideális toroid): az erő hiányos, ezért az integrálás "
                "leállt."), dts, magnetic_only)
        speed = float(np.linalg.norm(v))
        bmag = float(np.linalg.norm(s.b))
        emag = float(np.linalg.norm(s.e))
        if emag > 0:
            magnetic_only = False
        dt = span / 200.0
        if bmag > 0 and q != 0:
            dt = min(dt, eta / (abs(qm) * bmag))
        if speed > 0 and math.isfinite(s.distance):
            dt = min(dt, eta * s.distance / speed)
        if emag > 0 and q != 0 and math.isfinite(s.distance):
            dt = min(dt, math.sqrt(2 * eta * s.distance / (abs(qm) * emag)))
        if math.isfinite(time_scale):
            dt = min(dt, eta * time_scale)
        nxt = next((c for c in corners if c > t), t1)
        dt = min(dt, nxt - t, t1 - t)
        if not dt > 0:
            dt = t1 - t
        # Drift half a step, evaluate the fields there at the half-step time, kick–rotate–kick.
        xh = x + 0.5 * dt * v
        th = t + 0.5 * dt
        sh = field(xh, th)
        if sh.singular or sh.e_ind is None or not np.all(np.isfinite(sh.b)):
            s = sh
            x, t = xh, th
            continue  # reported by the checks at the top
        e, b = sh.e, sh.b
        if float(np.linalg.norm(e)) > 0:
            magnetic_only = False
        v_minus = v + 0.5 * dt * qm * e
        tv = 0.5 * dt * qm * b
        sv = 2.0 * tv / (1.0 + float(tv @ tv))
        v_prime = v_minus + np.cross(v_minus, tv)
        v_plus = v_minus + np.cross(v_prime, sv)
        v = v_plus + 0.5 * dt * qm * e
        x = xh + 0.5 * dt * v
        t = t1 if abs(t1 - (t + dt)) <= 1e-15 * max(abs(t1), span) else t + dt
        ts.append(t)
        xs.append(x.copy())
        vs.append(v.copy())
        dts.append(dt)
        if float(np.linalg.norm(v)) >= SPEED_OF_LIGHT:
            return PushOutput(ts, xs, vs, "invalid", L(
                "The particle has been accelerated to the speed of light: the nonrelativistic "
                "model is not valid; the integration stopped.",
                "A részecske fénysebességre gyorsult: a nemrelativisztikus modell nem érvényes; "
                "az integrálás leállt."), dts, magnetic_only)
        s = field(x, t)
    if t >= t1:
        return PushOutput(ts, xs, vs, "completed", None, dts, magnetic_only)
    return PushOutput(ts, xs, vs, "max_steps", L(
        "The maximum number of steps was reached before the end time (the step is limited by "
        "the gyrofrequency and by the distance to singular regions).",
        "A befejezési idő előtt elérte a maximális lépésszámot (a lépést a girofrekvencia és a "
        "szinguláris tartományoktól mért távolság korlátozza)."), dts, magnetic_only)


METHOD = L("Boris scheme (drift–kick–rotate–kick–drift, fields at the half-step position and "
           "time); step limited by ω_c Δt ≤ η, |v| Δt ≤ η d (d: distance to the nearest "
           "filament or point charge), the electric acceleration and the current time scale. "
           "Nonrelativistic test particle in prescribed fields.",
           "Boris-séma (sodródás–lökés–forgatás–lökés–sodródás, terek a féllépés helyén és "
           "időpontjában); lépéskorlát ω_c Δt ≤ η, |v| Δt ≤ η d (d: távolság a legközelebbi "
           "áramszáltól vagy ponttöltéstől), az elektromos gyorsulás és az áramok időskálája. "
           "Nemrelativisztikus próbarészecske előírt terekben.")


def trajectory(scene: Scene, req: ParticleRequest) -> TrajectoryResult:
    f = SceneFields(scene)
    q, m = float(req.charge_C), float(req.mass_kg)
    x0 = np.asarray(req.position_m, float)
    v0 = np.asarray(req.velocity_m_per_s, float)
    out = boris(f.sample, q, m, x0, v0, req.start_s, req.end_s, req.tolerance, req.max_steps,
                f.time_scale, f.corners, f.unsupported)
    return _result(out, f.sample, q, m, x0, v0, req.start_s)


def _result(out: PushOutput, field: FieldFn, q: float, m: float, x0: Arr, v0: Arr, t0: float
            ) -> TrajectoryResult:
    n = len(out.t)
    stride = max(1, math.ceil(n / MAX_OUTPUT))
    idx = list(range(0, n, stride))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    samples: list[TrajectorySample] = []
    for i in idx:
        v = out.v[i]
        sp = float(np.linalg.norm(v))
        fs = field(out.x[i], out.t[i])
        ok = not fs.singular and fs.e_ind is not None and np.all(np.isfinite(fs.b))
        samples.append(TrajectorySample(
            t_s=out.t[i], position_m=[float(x) for x in out.x[i]],
            velocity_m_per_s=[float(x) for x in v], speed_m_per_s=sp,
            kinetic_energy_J=0.5 * m * sp * sp,
            F_E_N=_vec(q * fs.e) if ok else None, F_B_N=_vec(q * np.cross(v, fs.b)) if ok
            else None, F_total_N=_vec(q * (fs.e + np.cross(v, fs.b))) if ok else None))
    s0 = field(x0, t0)
    b0 = float(np.linalg.norm(s0.b)) if np.all(np.isfinite(s0.b)) else 0.0
    gyro = abs(q) * b0 / m if b0 > 0 and q != 0 else None
    radius = period = None
    if gyro:
        bh = s0.b / b0
        v_perp = float(np.linalg.norm(v0 - (v0 @ bh) * bh))
        radius = v_perp / gyro
        period = 2 * math.pi / gyro
    k0 = 0.5 * m * float(v0 @ v0)
    k1 = 0.5 * m * float(out.v[-1] @ out.v[-1])
    vmax = max(float(np.linalg.norm(v)) for v in out.v)
    warnings = _relativistic(vmax)
    if gyro and out.dts and min(out.dts) * gyro > 0.5:
        warnings.append(L("The step is not small compared with the cyclotron period.",
                          "A lépés nem kicsi a ciklotronperiódushoz képest."))
    return TrajectoryResult(
        status=out.status, status_reason=out.reason, method=METHOD, steps=len(out.dts),
        samples=samples, min_step_s=min(out.dts) if out.dts else None,
        max_step_s=max(out.dts) if out.dts else None, end_time_s=out.t[-1],
        magnetic_only=out.magnetic_only,
        energy_relative_change=(k1 - k0) / k0 if k0 > 0 else None,
        gyrofrequency_rad_per_s=gyro, gyroradius_m=radius, gyroperiod_s=period,
        max_speed_fraction_c=vmax / SPEED_OF_LIGHT, warnings=warnings)
