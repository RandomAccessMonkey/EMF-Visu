"""Passive conducting circuits with induced currents (Phase 4C).

A passive circuit is a closed conductor with resistance R_i and a finite self-inductance ℒ_i,
without any applied voltage. Its total flux linkage is

    λ_i = Φ_i,ext(t) + Σ_j L_ij I_j,     L_ii = ℒ_i,  L_ij = M_ij (i ≠ j)

with Φ_i,ext the (N_i-turn) flux of the prescribed sources through the circuit, and the circuit
equation R_i I_i + dλ_i/dt = 0 gives the coupled system solved here:

    L(t) dI/dt = EMF_ext(t) − R I − (dL/dt) I,
    EMF_ext,i = −dΦ_i,ext/dt = EMF_tr,i + EMF_mot,i

The transformer part EMF_tr,i = −Σ_s dI_s/dt Φ_is (prescribed currents, analytical dI_s/dt) and
the motional part EMF_mot,i = N_i ∮(u × B_prescribed)·dl (Phase 4B line integral) are each
counted once; the motion relative to other passive circuits enters only through dL_ij/dt.
A circuit's own (singular) filament field is never integrated: its self-flux is ℒ_i I_i.

Sources of the numbers (one implementation each):
- B and A of prescribed sources: the magnetostatic solver (unit-current columns, Phase 4A/4B);
- B and A of passive circuits: the same loop field (circles) and exact straight-segment
  Biot–Savart (polygons), ``segments.py``;
- Φ_is, M_ij: Maxwell's closed form for coaxial circles, otherwise adaptive surface
  quadrature (Phase 4A) through a surface that the other filament does not pierce;
- R = ℓ/(σA); ℒ: thin-loop formula μ₀a[ln(8a/r_w) − 2] (circles, r_w/a ≤ 0.1) or user input.

Eddy-current disk (reduced-order, axisymmetric approximation): N_r concentric annular bands,
each a circular loop at its mid-radius with R_k = 2πr_k/(σ t Δr_k) and ℒ_k from an
equivalent round wire r_eq = √(tΔr_k/π) (thin-loop formula where r_eq/r_k ≤ 0.1) or else the
geometric-mean-distance (GMD) method; mutual inductances from Maxwell's formula.

Integration: SciPy's Radau (implicit, L-stable: suited to stiff RL systems), adaptive, split at
every corner of the source and motion profiles, with an event that stops a sliding rod leaving
its rails. Energies (Joule heat, source work, motional work, kinetic energy, ...) are integrated
as extra states of the same system.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, Field, model_validator
from scipy.integrate import solve_ivp
from scipy.special import ellipe, ellipkm1

from . import motional as mt
from .ampere import _Geo
from .i18n import L, LocalizedText
from .induction import (
    FluxSurface,
    SlidingRodShape,
    _patches,
    boundary_singularity,
    surface_integrate,
)
from .scene import motion as mo
from .scene._base import FiniteFloat, PositiveFloat, StrictModel
from .scene.currents import CurrentSources, LoopSource, current_sources
from .scene.models import Scene
from .scene.passive import PassiveFilament
from .scene.transforms import rotation_matrix_xyz
from .solvers.analytical import magnetostatics as ms
from .units import MU0

Arr = NDArray[np.float64]
Vec = tuple[FiniteFloat, FiniteFloat, FiniteFloat]

MATERIALS: dict[str, float] = {"copper": 5.8e7, "aluminium": 3.5e7, "silver": 6.3e7}  # S/m
THIN_LOOP_MAX_RATIO = 0.1  # r_w / a for the thin-loop self-inductance
RECIPROCITY_RTOL = 1e-6  # |M_ij − M_ji| / max(|M|) above this: matrix rejected
PD_RTOL = 1e-12  # smallest eigenvalue of L must exceed this × the largest
FLUX_RTOL = 1e-10  # surface quadrature of unit fluxes and mutual inductances
MAX_SAMPLES = 2001
MAX_BANDS = 200
GMD_RECT = 0.2235  # geometric mean distance of a rectangle ≈ 0.2235 (a + b) (Maxwell)


# ----------------------------------------------------------------------------- models


class SelfInductance(StrictModel):
    """'thin_loop': μ₀a[ln(8a/r_w) − 2] for a circular loop of round wire (r_w/a ≤ 0.1), times
    N² for N coincident turns; 'user': the given value."""

    mode: Literal["thin_loop", "user"] = "thin_loop"
    value_H: PositiveFloat | None = None

    @model_validator(mode="after")
    def _value(self) -> SelfInductance:
        if self.mode == "user" and self.value_H is None:
            raise ValueError("self-inductance: a user value in H is required")
        return self


class Electrical(StrictModel):
    """Conductor of a passive circuit. Exactly one of conductivity / resistivity for a custom
    material; exactly one of wire radius / cross-section; an explicit lumped resistance, if
    given, is authoritative (then σ and the cross-section only matter for ℒ)."""

    material: Literal["copper", "aluminium", "silver", "custom"] = "copper"
    conductivity_S_per_m: PositiveFloat | None = None
    resistivity_ohm_m: PositiveFloat | None = None
    wire_radius_m: PositiveFloat | None = 0.001
    cross_section_m2: PositiveFloat | None = None
    resistance_ohm: PositiveFloat | None = None
    self_inductance: SelfInductance = Field(default_factory=SelfInductance)

    @model_validator(mode="after")
    def _consistent(self) -> Electrical:
        if self.conductivity_S_per_m is not None and self.resistivity_ohm_m is not None:
            raise ValueError("give either the conductivity or the resistivity, not both")
        if self.material != "custom" and (self.conductivity_S_per_m is not None
                                          or self.resistivity_ohm_m is not None):
            raise ValueError("a preset material fixes the conductivity; choose 'custom'")
        if self.material == "custom" and self.resistance_ohm is None and \
                self.conductivity_S_per_m is None and self.resistivity_ohm_m is None:
            raise ValueError("a custom material needs a conductivity or a resistivity")
        if self.wire_radius_m is not None and self.cross_section_m2 is not None:
            raise ValueError("give either the wire radius or the cross-section, not both")
        return self

    def conductivity(self) -> float | None:
        if self.material != "custom":
            return MATERIALS[self.material]
        if self.conductivity_S_per_m is not None:
            return float(self.conductivity_S_per_m)
        if self.resistivity_ohm_m is not None:
            return 1.0 / float(self.resistivity_ohm_m)
        return None

    def area(self) -> float | None:
        if self.cross_section_m2 is not None:
            return float(self.cross_section_m2)
        if self.wire_radius_m is not None:
            return math.pi * float(self.wire_radius_m) ** 2
        return None

    def equivalent_radius(self) -> float | None:
        a = self.area()
        return float(self.wire_radius_m) if self.wire_radius_m is not None else (
            math.sqrt(a / math.pi) if a is not None else None)


class Mechanics(StrictModel):
    """Sliding rod only. 'prescribed': the rod follows its motion profile; 'dynamic': its
    position obeys m d²x/dt² = F_ext + F_em − b dx/dt (x along the rails)."""

    mode: Literal["prescribed", "dynamic"] = "prescribed"
    mass_kg: PositiveFloat = 0.02
    initial_velocity_m_per_s: FiniteFloat = 0.5
    external_force_N: FiniteFloat = 0.0
    damping_N_s_per_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0


class CircuitDisplay(StrictModel):
    visible: bool = True
    show_current: bool = True


class PassiveCircuit(StrictModel):
    """A closed passive conductor: the geometry of a measurement surface's boundary (circle,
    rectangle, polygon, sliding rod; optional Phase 4B motion and N series turns) with
    electrical properties. Measurement surfaces stay measurement surfaces; a circuit is only
    created explicitly."""

    id: str = Field(min_length=1, max_length=40)
    name: str = ""
    path: FluxSurface
    electrical: Electrical = Field(default_factory=Electrical)
    initial_current_A: FiniteFloat = 0.0
    mechanics: Mechanics | None = None
    display: CircuitDisplay | None = None

    @model_validator(mode="after")
    def _mechanics(self) -> PassiveCircuit:
        if self.mechanics is not None and not isinstance(self.path.shape, SlidingRodShape):
            raise ValueError("mechanics (dynamic motion) is supported for the sliding rod only")
        return self

    def physics_dump(self) -> dict[str, object]:
        d = self.model_dump(mode="json", exclude={"name", "display"})
        d["path"] = self.path.physics_dump()
        return d


class EddyDisk(StrictModel):
    """Thin conducting disk in its local xy plane (normal +z), discretized into N_r concentric
    annular bands (reduced-order axisymmetric eddy-current approximation)."""

    id: str = Field(min_length=1, max_length=40)
    name: str = ""
    center_m: Vec = (0.0, 0.0, 0.0)
    rotation_euler_xyz_rad: Vec = (0.0, 0.0, 0.0)
    outer_radius_m: PositiveFloat = 0.1
    inner_radius_m: Annotated[float, Field(ge=0, allow_inf_nan=False)] = 0.0
    thickness_m: PositiveFloat = 0.005
    material: Literal["copper", "aluminium", "silver", "custom"] = "copper"
    conductivity_S_per_m: PositiveFloat | None = None
    bands: Annotated[int, Field(ge=2, le=MAX_BANDS)] = 20
    display: CircuitDisplay | None = None

    @model_validator(mode="after")
    def _radii(self) -> EddyDisk:
        if not self.outer_radius_m > self.inner_radius_m:
            raise ValueError("eddy disk: the outer radius must exceed the inner radius")
        if self.material == "custom" and self.conductivity_S_per_m is None:
            raise ValueError("eddy disk: a custom material needs a conductivity")
        if self.material != "custom" and self.conductivity_S_per_m is not None:
            raise ValueError("eddy disk: a preset material fixes the conductivity")
        return self

    def conductivity(self) -> float:
        return float(self.conductivity_S_per_m or 0.0) if self.material == "custom" else \
            MATERIALS[self.material]

    def physics_dump(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"name", "display"})


class CircuitRequest(StrictModel):
    circuits: list[PassiveCircuit] = Field(default=[], max_length=8)
    disks: list[EddyDisk] = Field(default=[], max_length=2)
    start_s: FiniteFloat = 0.0
    end_s: FiniteFloat = 1.0
    step_s: PositiveFloat = 0.01  # output grid t_k = start + k step (the playback grid)
    rtol: Annotated[float, Field(ge=1e-10, le=1e-3)] = 1e-7

    @model_validator(mode="after")
    def _grid(self) -> CircuitRequest:
        if not self.end_s > self.start_s:
            raise ValueError("circuits: end_s must be later than start_s")
        if (self.end_s - self.start_s) / self.step_s > MAX_SAMPLES - 1 + 1e-9:
            raise ValueError(f"circuits: at most {MAX_SAMPLES} output samples")
        if not self.circuits and not self.disks:
            raise ValueError("circuits: nothing to solve")
        ids = [c.id for c in self.circuits] + [d.id for d in self.disks]
        if len(set(ids)) != len(ids):
            raise ValueError("circuits: ids must be unique")
        if sum(1 for c in self.circuits if c.mechanics and c.mechanics.mode == "dynamic") > 1:
            raise ValueError("circuits: at most one dynamically moving rod")
        return self


# ------------------------------------------------------------------------------ results


class ElementInfo(BaseModel):
    """One electrical branch: a passive circuit, or one band of an eddy-current disk."""

    id: str
    owner_id: str  # circuit or disk id
    kind: Literal["circuit", "band"]
    name: str
    band_index: int | None = None
    radius_m: float | None = None  # band mid-radius
    width_m: float | None = None  # band radial width
    thickness_m: float | None = None
    turns: int = 1
    resistance_ohm: float
    resistance_method: LocalizedText
    length_m: float | None = None
    cross_section_m2: float | None = None
    self_inductance_H: float
    self_inductance_method: LocalizedText
    self_inductance_approximate: bool
    moving: bool = False
    dynamic: bool = False
    time_constant_s: float  # ℒ/R (uncoupled)


class MatrixInfo(BaseModel):
    ids: list[str]
    values_H: list[list[float]]  # at the start time
    method: list[list[str]]  # "self", "closed_form", "numerical", "numerical_one_way"
    reciprocity_max_relative: float | None
    positive_definite: bool
    min_eigenvalue_H: float
    max_eigenvalue_H: float
    time_dependent: bool  # some circuit moves relative to another


class CircuitSeries(BaseModel):
    """Columnar time series on the output grid; per-element lists are indexed [element][k]."""

    t_s: list[float]
    current_A: list[list[float]]  # induced current per turn
    dI_dt_A_per_s: list[list[float]]
    flux_external_Wb: list[list[float]]  # N Φ_ext from the prescribed sources
    flux_linkage_Wb: list[list[float]]  # λ = Φ_ext + Σ L_ij I_j
    emf_transformer_V: list[list[float]]
    emf_motional_V: list[list[float]]
    resistive_drop_V: list[list[float]]  # R I
    joule_power_W: list[list[float]]  # R I²
    current_density_A_per_m2: list[list[float] | None]  # bands: I/(tΔr); circuits: None
    force_N: list[list[list[float]] | None]  # circuits: I∮dl × B_ext on movable parts
    torque_N_m: list[list[list[float]] | None]  # about the circuit's centre
    mechanical_power_W: list[list[float] | None]  # F_em·u (+ τ·ω)
    magnetic_energy_J: list[float]  # ½ IᵀLI (passive circuits only)
    joule_heat_J: list[float]  # ∫ Σ R I² dt
    source_work_J: list[float]  # ∫ I·EMF_tr dt: energy delivered by changing prescribed flux
    motional_work_J: list[float]  # ∫ I·EMF_mot dt
    geometric_work_J: list[float]  # ∫ ½ IᵀL̇I dt
    kinetic_energy_J: list[float] | None = None
    damping_heat_J: list[float] | None = None
    external_work_J: list[float] | None = None
    rod_position_m: list[float] | None = None  # along the rails (local x)
    rod_velocity_m_per_s: list[float] | None = None
    energy_residual_J: list[float]
    power_residual_W: list[float | None]
    filaments: list[list[PassiveFilament]]  # per element: one entry (fixed) or one per sample


class CircuitResult(BaseModel):
    status: Literal["solved", "stopped", "invalid", "singular", "unsupported", "nonphysical",
                    "failed"]
    status_reason: LocalizedText | None = None
    problems: list[LocalizedText] = []
    warnings: list[LocalizedText] = []
    method: LocalizedText
    elements: list[ElementInfo] = []
    matrix: MatrixInfo | None = None
    series: CircuitSeries | None = None
    solver_steps: int = 0
    rhs_evaluations: int = 0
    end_time_s: float | None = None  # last solved time


# ---------------------------------------------------------------------------- physics


def thin_loop_inductance(a: float, r_w: float) -> float:
    """ℒ ≈ μ₀a[ln(8a/r_w) − 2] for a thin circular loop (current on the wire surface)."""
    return MU0 * a * (math.log(8.0 * a / r_w) - 2.0)


def coaxial_mutual(a: float, b: float, d: float) -> float:
    """Maxwell's mutual inductance of two coaxial circles (radii a, b, axial distance d):
    M = μ₀√(ab)[(2/k − k)K(k) − (2/k)E(k)], k² = 4ab/((a + b)² + d²); a series for small k."""
    den = (a + b) ** 2 + d * d
    m = 4 * a * b / den
    if m < 1e-3:
        k3 = m ** 1.5
        return float(MU0 * math.sqrt(a * b) * math.pi / 16 * k3
                     * (1 + 0.75 * m + 75 / 128 * m * m))
    p = ((a - b) ** 2 + d * d) / den  # 1 − m
    k = math.sqrt(m)
    return MU0 * math.sqrt(a * b) * ((2 / k - k) * float(ellipkm1(p)) - (2 / k) * float(
        ellipe(m)))


def _coaxial_mutual_arr(a: Arr, b: Arr, d: Arr) -> Arr:
    den = (a + b) ** 2 + d * d
    m = 4 * a * b / den
    p = ((a - b) ** 2 + d * d) / den
    k = np.sqrt(m)
    out: Arr = MU0 * np.sqrt(a * b) * ((2 / k - k) * ellipkm1(p) - (2 / k) * ellipe(m))
    return out


_GX, _GW = np.polynomial.legendre.leggauss(6)


def band_mutual(r1: float, r2: float, w: float, t: float) -> float:
    """Mutual inductance of two coplanar coaxial annular bands (width w, thickness t, uniform
    current density), averaged over both cross-sections with 6×6 Gauss–Legendre points per
    band (Maxwell's formula between the points). Used for bands closer than 3t + w, where the
    filament formula at the band centres overestimates the coupling."""
    a = (r1 + 0.5 * w * _GX)[:, None, None, None]
    b = (r2 + 0.5 * w * _GX)[None, :, None, None]
    z1 = (0.5 * t * _GX)[None, None, :, None]
    z2 = (0.5 * t * _GX)[None, None, None, :]
    wt = (_GW[:, None, None, None] * _GW[None, :, None, None] * _GW[None, None, :, None]
          * _GW[None, None, None, :])
    return float((wt * _coaxial_mutual_arr(a, b, np.abs(z1 - z2))).sum() / 16.0)


def gmd_inductance(a: float, t: float, w: float) -> float:
    """Self-inductance of a ring of rectangular cross-section t × w by the geometric-mean-
    distance method: the mutual inductance of two coaxial circles of radius a separated by the
    GMD ≈ 0.2235 (t + w) (an approximation that stays finite and positive for thick rings)."""
    return coaxial_mutual(a, a, GMD_RECT * (t + w))


@dataclass
class Element:
    info: ElementInfo
    surface: FluxSurface
    R: float
    L_self: float
    turns: int
    wire_radius: float
    moving: bool
    dynamic: bool
    mech: Mechanics | None = None
    circuit: PassiveCircuit | None = None
    disk: EddyDisk | None = None


def _resistance(c: PassiveCircuit, perimeter: float) -> tuple[float | None, LocalizedText,
                                                                  list[LocalizedText]]:
    e = c.electrical
    if e.resistance_ohm is not None:
        return float(e.resistance_ohm), L("given lumped resistance", "megadott ellenállás"), []
    if isinstance(c.path.shape, SlidingRodShape):
        return None, L("", ""), [L(f"{c.name or c.id}: the sliding-rod circuit needs an explicit "
                                   "total resistance (its length changes as the rod moves).",
                                   f"{c.name or c.id}: a csúszó rudas áramkörhöz megadott teljes "
                                   "ellenállás kell (hossza a rúd mozgásával változik).")]
    sigma, area = e.conductivity(), e.area()
    if sigma is None or area is None:
        return None, L("", ""), [L(f"{c.name or c.id}: conductivity and cross-section are needed "
                                   "for the resistance.",
                                   f"{c.name or c.id}: az ellenálláshoz vezetőképesség és "
                                   "keresztmetszet kell.")]
    length = perimeter * c.path.turns
    return length / (sigma * area), L(f"R = ℓ/(σA), ℓ = {length:.6g} m, σ = {sigma:.4g} S/m, "
                                      f"A = {area:.4g} m²",
                                      f"R = ℓ/(σA), ℓ = {length:.6g} m, σ = {sigma:.4g} S/m, "
                                      f"A = {area:.4g} m²"), []


def _self_inductance(c: PassiveCircuit) -> tuple[float | None, LocalizedText, bool,
                                                list[LocalizedText]]:
    si = c.electrical.self_inductance
    name = c.name or c.id
    if si.mode == "user":
        assert si.value_H is not None
        return float(si.value_H), L("user-specified", "felhasználó által megadott"), False, []
    sh = c.path.shape
    if sh.type != "circle":
        return None, L("", ""), False, [L(
            f"{name}: the thin-loop self-inductance applies to circular loops only; give a "
            "self-inductance for this geometry.",
            f"{name}: a vékony hurok önindukciója csak kör alakú hurokra érvényes; ehhez a "
            "geometriához adjon meg önindukciót.")]
    r_w = c.electrical.equivalent_radius()
    if r_w is None:
        return None, L("", ""), False, [L(f"{name}: a finite wire radius is needed (an ideal "
                                          "filament has no finite self-inductance).",
                                          f"{name}: véges huzalsugár kell (ideális áramszálnak "
                                          "nincs véges önindukciója).")]
    a = float(sh.radius_m)
    if r_w / a > THIN_LOOP_MAX_RATIO:
        return None, L("", ""), False, [L(
            f"{name}: r_w/a = {r_w / a:.3g} exceeds {THIN_LOOP_MAX_RATIO}: the thin-loop formula "
            "does not apply; give a self-inductance.",
            f"{name}: r_w/a = {r_w / a:.3g} nagyobb, mint {THIN_LOOP_MAX_RATIO}: a vékony hurok "
            "képlete nem alkalmazható; adjon meg önindukciót.")]
    n = c.path.turns
    val = n * n * thin_loop_inductance(a, r_w)
    eq = "" if c.electrical.wire_radius_m is not None else " (equivalent round wire √(A/π))"
    eqh = "" if c.electrical.wire_radius_m is not None else " (egyenértékű kör huzal √(A/π))"
    return val, L(f"thin-loop approximation μ₀a[ln(8a/r_w) − 2]{' × N²' if n > 1 else ''}, "
                  f"r_w/a = {r_w / a:.3g}{eq}",
                  f"vékony hurok közelítés μ₀a[ln(8a/r_w) − 2]{' × N²' if n > 1 else ''}, "
                  f"r_w/a = {r_w / a:.3g}{eqh}"), True, []


def _disk_frame(d: EddyDisk) -> tuple[Arr, Arr]:
    return np.asarray(d.center_m, float), rotation_matrix_xyz(d.rotation_euler_xyz_rad)


def posed_any(surface: FluxSurface, t: float, tol: float,
              rod_state: tuple[float, float] | None = None) -> mt.Posed:
    """The Phase 4B posed geometry, for stationary surfaces too (reference pose)."""
    if not surface.moving:
        surface = surface.model_copy(update={"motion": mo.MotionProfile()})
    return mt.posed(surface, t, tol, rod_state)


def build_elements(req: CircuitRequest, tol: float) -> tuple[list[Element], list[LocalizedText]]:
    out: list[Element] = []
    problems: list[LocalizedText] = []
    for c in req.circuits:
        p0 = posed_any(c.path, req.start_s, tol)
        problems += p0.invalid
        if p0.invalid:
            continue
        perimeter = p0.geo.perimeter()
        r, r_how, pr = _resistance(c, perimeter)
        ls, l_how, approx, pl = _self_inductance(c)
        problems += pr + pl
        if r is None or ls is None:
            continue
        dyn = c.mechanics is not None and c.mechanics.mode == "dynamic"
        moving = c.path.moving
        info = ElementInfo(
            id=c.id, owner_id=c.id, kind="circuit", name=c.name or c.id, turns=c.path.turns,
            resistance_ohm=r, resistance_method=r_how,
            length_m=None if isinstance(c.path.shape, SlidingRodShape)
            else perimeter * c.path.turns,
            cross_section_m2=c.electrical.area(), self_inductance_H=ls,
            self_inductance_method=l_how, self_inductance_approximate=approx, moving=moving,
            dynamic=dyn, time_constant_s=ls / r)
        out.append(Element(info, c.path, r, ls, c.path.turns,
                           c.electrical.equivalent_radius() or 0.0, moving, dyn, c.mechanics, c))
    for d in req.disks:
        sigma = d.conductivity()
        width = (d.outer_radius_m - d.inner_radius_m) / d.bands
        if width < 0.5 * d.thickness_m:
            problems.append(L(
                f"{d.name or d.id}: bands of width {width:.3g} m are narrower than half the "
                f"thickness ({d.thickness_m:.3g} m): outside the validity range of the "
                "annular-band approximation (the inductance matrix becomes unreliable). Use at "
                f"most {int((d.outer_radius_m - d.inner_radius_m) / (0.5 * d.thickness_m))} "
                "bands.",
                f"{d.name or d.id}: a {width:.3g} m széles sávok keskenyebbek a vastagság "
                f"({d.thickness_m:.3g} m) felénél: ez kívül esik a körgyűrű-sávos közelítés "
                "érvényességi tartományán (az induktivitásmátrix megbízhatatlanná válik). "
                f"Legfeljebb {int((d.outer_radius_m - d.inner_radius_m) / (0.5 * d.thickness_m))}"
                " sávot használjon."))
            continue
        edges = np.linspace(d.inner_radius_m, d.outer_radius_m, d.bands + 1)
        for k in range(d.bands):
            r0, r1 = float(edges[k]), float(edges[k + 1])
            rk, w = 0.5 * (r0 + r1), r1 - r0
            area = d.thickness_m * w
            res = 2 * math.pi * rk / (sigma * area)
            r_eq = math.sqrt(area / math.pi)
            if r_eq / rk <= THIN_LOOP_MAX_RATIO:
                ls = thin_loop_inductance(rk, r_eq)
                how = L(f"equivalent-wire approximation: thin loop with r_eq = √(tΔr/π) = "
                        f"{r_eq:.3g} m (r_eq/r = {r_eq / rk:.3g})",
                        f"egyenértékű huzal közelítés: vékony hurok, r_eq = √(tΔr/π) = "
                        f"{r_eq:.3g} m (r_eq/r = {r_eq / rk:.3g})")
            else:
                ls = gmd_inductance(rk, d.thickness_m, w)
                how = L(f"geometric-mean-distance approximation for a thick band (r_eq/r = "
                        f"{r_eq / rk:.3g} > {THIN_LOOP_MAX_RATIO}): M(r, r, 0.2235(t + Δr))",
                        f"geometriai középtávolság közelítés vastag sávra (r_eq/r = "
                        f"{r_eq / rk:.3g} > {THIN_LOOP_MAX_RATIO}): M(r, r, 0.2235(t + Δr))")
            surf = FluxSurface.model_validate({
                "id": f"{d.id}#{k}", "shape": {"type": "circle", "radius_m": rk},
                "center_m": d.center_m, "rotation_euler_xyz_rad": d.rotation_euler_xyz_rad})
            info = ElementInfo(
                id=f"{d.id}#{k}", owner_id=d.id, kind="band", name=f"{d.name or d.id} [{k + 1}]",
                band_index=k, radius_m=rk, width_m=w, thickness_m=d.thickness_m,
                resistance_ohm=res, resistance_method=L(
                    f"annular band R = 2πr/(σ t Δr), σ = {sigma:.4g} S/m",
                    f"körgyűrű sáv R = 2πr/(σ t Δr), σ = {sigma:.4g} S/m"),
                length_m=2 * math.pi * rk, cross_section_m2=area, self_inductance_H=ls,
                self_inductance_method=how, self_inductance_approximate=True,
                time_constant_s=ls / res)
            out.append(Element(info, surf, res, ls, 1, r_eq, False, False, disk=d))
    return out, problems


def filament_of(e: Element, p: mt.Posed, current: float = 0.0, rate: float = 0.0
                ) -> PassiveFilament:
    g = p.geo
    if g.circle_r is not None:
        return PassiveFilament(id=e.info.id, kind="circle", center_m=tuple(map(float, g.c)),
                               normal=tuple(map(float, g.normal)), u=tuple(map(float, g.ex)),
                               radius_m=g.circle_r, turns=e.turns, current_A=current,
                               rate_A_per_s=rate, moving=e.moving, wire_radius_m=e.wire_radius
                               or None)
    verts = [tuple(map(float, g.param(k, np.array([0.0]))[0][0]))
             for k, _ in enumerate(g.pieces())]
    return PassiveFilament(id=e.info.id, kind="polygon", center_m=tuple(map(float, g.c)),
                           normal=tuple(map(float, g.normal)), vertices_m=verts, turns=e.turns,
                           current_A=current, rate_A_per_s=rate, moving=e.moving,
                           wire_radius_m=e.wire_radius or None)


def _dense(g: _Geo, n: int = 256) -> Arr:
    if g.circle_r is not None:
        return g.polyline(n)
    return np.vstack([g.param(k, np.linspace(0, 1, 33)[:-1])[0] for k, _ in enumerate(g.pieces())])


def _pierces(g: _Geo, pts: Arr) -> bool:
    """Whether the closed polyline passes through (or lies in) the surface spanned by g."""
    loc = g.to_local(pts)
    h = loc[:, 2]
    inplane = np.abs(h) <= g.tol
    if np.any(inplane & g.inside(loc[:, :2])):
        return True
    nxt = np.roll(loc, -1, axis=0)
    hn = nxt[:, 2]
    for i in np.flatnonzero(h * hn < 0):
        w = h[i] / (h[i] - hn[i])
        q = loc[i] + w * (nxt[i] - loc[i])
        if bool(g.inside(q[None, :2])[0]):
            return True
    return False


def _coaxial(gi: _Geo, gj: _Geo) -> float | None:
    """Signed axial distance if both are coaxial circles, else None."""
    if gi.circle_r is None or gj.circle_r is None:
        return None
    if np.linalg.norm(np.cross(gi.normal, gj.normal)) > 1e-12:
        return None
    d = gj.c - gi.c
    z = float(d @ gi.normal)
    if np.linalg.norm(d - z * gi.normal) > 1e-12 * (1 + np.linalg.norm(gi.c)
                                                       + np.linalg.norm(gj.c)):
        return None
    return z


def _unit_flux_through(gi: _Geo, fj: PassiveFilament) -> float:
    """Flux through the surface of gi of filament j at 1 A per turn (× its turns)."""
    cs = None
    if fj.kind == "circle":
        cs = CurrentSources(wires=[], loops=[ms._passive_loop(fj, 1.0)], problems=[])
    n = gi.normal

    def f(points: Arr) -> Arr:
        out: Arr = (ms.passive_unit(points, fj, "B")[0] @ n)[:, None]
        return out

    res = surface_integrate(f, _patches(gi, cs), 1, FLUX_RTOL)
    return float(res.value[0])


def mutual(ei: Element, gi: _Geo, ej: Element, gj: _Geo
           ) -> tuple[float, str, float | None, LocalizedText | None]:
    """(M_ij, method, reciprocity relative difference, problem)."""
    z = _coaxial(gi, gj)
    if (z is not None and ei.disk is not None and ei.disk is ej.disk
            and abs(float(ei.info.radius_m or 0) - float(ej.info.radius_m or 0))
            <= 3 * float(ei.info.thickness_m or 0) + float(ei.info.width_m or 0)):
        return band_mutual(float(ei.info.radius_m or 0), float(ej.info.radius_m or 0),
                           float(ei.info.width_m or 0), float(ei.info.thickness_m or 0)), \
            "band_average", None, None
    if z is not None:
        a, b = float(gi.circle_r or 0), float(gj.circle_r or 0)
        if a == b and abs(z) <= (ei.wire_radius + ej.wire_radius):
            return 0.0, "", None, L(f"{ei.info.name} and {ej.info.name} coincide.",
                                    f"{ei.info.name} és {ej.info.name} egybeesik.")
        sign = float(np.sign(gi.normal @ gj.normal))
        return sign * ei.turns * ej.turns * coaxial_mutual(a, b, abs(z)), "closed_form", None, \
            None
    pi_, pj_ = _dense(gi), _dense(gj)
    fi, fj = _filament_geo(ei, gi), _filament_geo(ej, gj)
    gap = float(np.min(ms.passive_distance(pi_, [fj])))
    if gap <= ei.wire_radius + ej.wire_radius:
        return 0.0, "", None, L(f"{ei.info.name} and {ej.info.name} touch or overlap (gap "
                                f"{gap:.3g} m): their mutual inductance is degenerate.",
                                f"{ei.info.name} és {ej.info.name} érintkezik vagy átfed "
                                f"(rés {gap:.3g} m): kölcsönös induktivitásuk elfajult.")
    through_i = not _pierces(gi, pj_)
    through_j = not _pierces(gj, pi_)
    if not through_i and not through_j:
        return 0.0, "", None, L(f"{ei.info.name} and {ej.info.name} are linked (each passes "
                                "through the other): not supported.",
                                f"{ei.info.name} és {ej.info.name} egymásba fűzött: nem "
                                "támogatott.")
    vals = []
    if through_i:
        vals.append(_unit_flux_through(gi, fj) * ei.turns)
    if through_j:
        vals.append(_unit_flux_through(gj, fi) * ej.turns)
    if len(vals) == 2:
        rel = abs(vals[0] - vals[1]) / max(abs(vals[0]), abs(vals[1]), 1e-300)
        return 0.5 * (vals[0] + vals[1]), "numerical", rel, None
    return vals[0], "numerical_one_way", None, None


def _filament_geo(e: Element, g: _Geo) -> PassiveFilament:
    return filament_of(e, mt.Posed(g, None, None, None, [], []))


# --------------------------------------------------------------------- axisymmetry check


def _axisymmetric(d: EddyDisk, cs: CurrentSources, others: list[tuple[Element, _Geo]]
                  ) -> LocalizedText | None:
    c, r = _disk_frame(d)
    n = r[:, 2]

    def on_axis(p: Arr, direction: Arr) -> bool:
        q = np.asarray(p, float) - c
        return bool(np.linalg.norm(np.cross(direction, n)) <= 1e-9 and
                    np.linalg.norm(q - (q @ n) * n) <= 1e-9 * (1 + np.linalg.norm(c)))

    bad: list[str] = []
    for lp in cs.loops:
        if lp.kind == "toroid_finite" or not on_axis(lp.center_m, lp.normal):
            bad.append(lp.object_id)
    for mg in cs.magnets:
        if not on_axis(mg.center_m, mg.axis):
            bad.append(mg.object_id)
    for t in cs.ideal_toroids:
        if not on_axis(t.center_m, t.axis):
            bad.append(t.object_id)
    for w in cs.wires:
        if not on_axis(w.point_m, w.direction):
            bad.append(w.object_id)
    for e, g in others:
        if e.disk is d:
            continue
        if g.circle_r is None or e.moving or not on_axis(g.c, g.normal):
            bad.append(e.info.owner_id)
    if bad:
        names = ", ".join(sorted(set(bad)))
        return L(f"The eddy-current disk model is axisymmetric only: {names} is not coaxial with "
                 "the disk (or not rotationally symmetric), so the azimuthal-band approximation "
                 "does not apply.",
                 f"Az örvényáramú korong modellje csak tengelyszimmetrikus: {names} nem "
                 "koaxiális a "
                 "koronggal (vagy nem forgásszimmetrikus), így az azimutális sávos közelítés nem "
                 "alkalmazható.")
    return None


# ----------------------------------------------------------------------------- system


@dataclass
class _System:
    scene: Scene
    req: CircuitRequest
    els: list[Element]
    fm: mt.FieldModel
    cs: CurrentSources
    tol: float
    R: Arr = field(init=False)
    n: int = field(init=False)
    dyn: int | None = field(init=False)
    moving_idx: list[int] = field(init=False)
    unit_flux: dict[int, Arr] = field(default_factory=dict)  # stationary: Φ per source column
    L0: Arr | None = None
    methods: list[list[str]] = field(default_factory=list)
    recip: float | None = None
    _lcache: dict[tuple[float, float], Arr] = field(default_factory=dict)
    evals: int = 0
    rod_tab: RodTable | None = None
    _ftab: dict[int, tuple[Arr, Arr]] = field(default_factory=dict)
    rod_tab_note: LocalizedText | None = None

    def __post_init__(self) -> None:
        self.n = len(self.els)
        self.R = np.array([e.R for e in self.els])
        self.dyn = next((i for i, e in enumerate(self.els) if e.dynamic), None)
        self.moving_idx = [i for i, e in enumerate(self.els) if e.moving]

    # geometry -------------------------------------------------------------------------
    def posed(self, i: int, t: float, x: float | None = None, v: float = 0.0) -> mt.Posed:
        e = self.els[i]
        rod = (x, v) if (i == self.dyn and x is not None) else None
        return posed_any(e.surface, t, self.tol, rod)

    def x0(self) -> tuple[float, float]:
        assert self.dyn is not None
        e = self.els[self.dyn]
        sh = e.surface.shape
        assert isinstance(sh, SlidingRodShape) and e.mech is not None
        return float(sh.rod_position_m), float(e.mech.initial_velocity_m_per_s)

    def build_rod_table(self) -> None:
        """Chebyshev tables in x of the dynamic rod's static-field integrals (see RodTable)."""
        if self.dyn is None:
            return
        i = self.dyn
        e = self.els[i]
        sh = e.surface.shape
        assert isinstance(sh, SlidingRodShape)
        k_cols = len(self.fm.ids) + 1
        t0 = self.req.start_s

        def values(x: float) -> Arr:
            p = self.posed(i, t0, x, 1.0)
            nrm = p.geo.normal

            def fn(piece: int, pt: Arr, dp: Arr) -> Arr:
                ub = self.fm.unit_b(pt)  # (N, K, 3)
                cr = np.cross(dp[:, None, :], ub)
                bn = np.einsum("nkj,j->nk", ub, nrm) * np.linalg.norm(dp, axis=1)[:, None]
                out: Arr = np.concatenate([cr.reshape(len(pt), -1), bn], axis=1)
                return out

            res = mt.line_integral(p.geo, p.moving_pieces, fn, 4 * k_cols, 1e-12, None)
            v = res.value
            return np.concatenate([v[:3 * k_cols].reshape(k_cols, 3), v[3 * k_cols:, None]],
                                  axis=1)  # (K, 4)

        a = max(10 * self.tol, 1e-9 * sh.rail_length_m)
        b = float(sh.rail_length_m)
        x0 = float(sh.rod_position_m)
        try:
            self.rod_tab = RodTable.build(values, a, b, x0, self.flux_cols(i, t0, x0) / e.turns)
            self.rod_tab_note = L(
                f"Dynamic rod: the static-field line integrals along the rod are tabulated as "
                f"Chebyshev series in x ({self.rod_tab.pieces} pieces of degree "
                f"{self.rod_tab.degree}, verified against direct "
                f"quadrature to {self.rod_tab.error:.1g} relative).",
                f"Dinamikus rúd: a rúd menti sztatikus térvonal-integrálok x szerinti Csebisev-"
                f"sorként tabulálva ({self.rod_tab.pieces} darab, fokszám {self.rod_tab.degree}, "
                f"közvetlen kvadratúrával "
                f"{self.rod_tab.error:.1g} relatív pontosságig ellenőrizve).")
        except ValueError:
            self.rod_tab = None  # not smooth enough: direct quadrature at every evaluation

    def _unit_force(self, i: int, t: float) -> tuple[Arr, Arr]:
        p = self.posed(i, t)
        c = p.geo.c
        k_cols = len(self.fm.ids) + 1
        fils = [filament_of(self.els[j], self.posed(j, t), 1.0) for j in range(self.n)]

        def fn(piece: int, pt: Arr, dp: Arr) -> Arr:
            cols = [self.fm.unit_b(pt)[:, k, :] for k in range(k_cols)]
            cols += [ms.passive_unit(pt, fils[j], "B")[0] if j != i else np.zeros_like(pt)
                     for j in range(self.n)]
            out = []
            for b in cols:
                f = np.cross(dp, b)
                out += [f, np.cross(pt - c, f)]
            res: Arr = np.concatenate(out, axis=1)
            return res

        res = mt.line_integral(p.geo, list(range(len(p.geo.pieces()))), fn,
                               6 * (k_cols + self.n), 1e-9, None)
        v = res.value.reshape(k_cols + self.n, 6)
        return v[:k_cols], v[k_cols:]

    # inductance -----------------------------------------------------------------------
    def L(self, t: float, x: float | None = None) -> tuple[Arr, list[LocalizedText]]:
        presc_moving = any(i != self.dyn for i in self.moving_idx)
        key = (t if presc_moving else 0.0, x if x is not None else 0.0)
        if self.L0 is not None and not self.moving_idx:
            return self.L0, []
        if key in self._lcache:
            return self._lcache[key], []
        geos = [self.posed(i, t, x).geo for i in range(self.n)]
        mat = np.diag([e.L_self for e in self.els]).astype(float)
        methods = [["self" if i == j else "" for j in range(self.n)] for i in range(self.n)]
        probs: list[LocalizedText] = []
        recip = 0.0
        have = False
        for i in range(self.n):
            for j in range(i + 1, self.n):
                m, how, rel, prob = mutual(self.els[i], geos[i], self.els[j], geos[j])
                if prob is not None:
                    probs.append(prob)
                mat[i, j] = mat[j, i] = m
                methods[i][j] = methods[j][i] = how
                if rel is not None:
                    recip, have = max(recip, rel), True
        self.methods, self.recip = methods, recip if have else None
        if not self.moving_idx:
            self.L0 = mat
        else:
            if len(self._lcache) > 4096:
                self._lcache.clear()
            self._lcache[key] = mat
        return mat, probs

    def Ldot(self, t: float, x: float | None, v: float) -> Arr:
        if not self.moving_idx or self.n == 1:
            return np.zeros((self.n, self.n))
        if self.dyn is not None:
            assert x is not None
            sh = self.els[self.dyn].surface.shape
            assert isinstance(sh, SlidingRodShape)
            hx = 1e-5 * sh.rail_length_m
            return (self.L(t, x + hx)[0] - self.L(t, x - hx)[0]) / (2 * hx) * v
        h = 1e-5 * self.time_scale()
        return (self.L(t + h)[0] - self.L(t - h)[0]) / (2 * h)

    def time_scale(self) -> float:
        ts = math.inf
        for i in self.moving_idx:
            g = self.posed(i, self.req.start_s).geo
            ts = min(ts, mt._motion_scale(self.els[i].surface, g.size()))
        return ts if math.isfinite(ts) else 1.0

    # external flux and EMF ------------------------------------------------------------
    def flux_cols(self, i: int, t: float, x: float | None = None) -> Arr:
        """Φ per source column (1 A per source; static last) through element i, × turns."""
        e = self.els[i]
        if not e.moving and i in self.unit_flux:
            return self.unit_flux[i]
        p = self.posed(i, t, x)
        vals = _coaxial_source_flux(p.geo, self.cs, self.fm)
        if vals is None:
            vals = mt.flux_columns(p, self.fm, FLUX_RTOL).unit
        vals = vals * e.turns
        if not e.moving:
            self.unit_flux[i] = vals
        return vals

    def ext(self, t: float, x: float | None, v: float) -> tuple[Arr, Arr]:
        rates = self.fm.rates(t, "right")
        tr = np.zeros(self.n)
        mot = np.zeros(self.n)
        any_rate = bool(np.any(rates != 0.0))
        for i, e in enumerate(self.els):
            if i == self.dyn and self.rod_tab is not None and x is not None:
                g, phi = self.rod_tab.at(x)
                p = self.posed(i, t, x, v)
                assert p.rod_axis is not None
                w = self.fm.weights(t)
                tr[i] = -float(phi[:-1] @ rates) * e.turns
                mot[i] = -float((v * p.rod_axis) @ (w @ g)) * e.turns
                continue
            if any_rate:
                tr[i] = -float(self.flux_cols(i, t, x)[:-1] @ rates)
            if e.moving and np.any(self.fm.weights(t) != 0.0):  # no field: no motional EMF
                p = self.posed(i, t, x, v)
                res = mt.motional_emf(p, self.fm, t, "right", 1e-10, None)
                mot[i] = float(res.value[0]) * e.turns
        return tr, mot

    def force(self, i: int, t: float, currents: Arr, x: float | None = None, v: float = 0.0
              ) -> tuple[Arr, Arr]:
        """(F, τ about the centre) on the movable conductor of element i:
        I N ∮ dl × B_ext, B_ext = prescribed + the other passive circuits (own field
        excluded)."""
        e = self.els[i]
        w = self.fm.weights(t)
        if not self.moving_idx:
            # Fixed geometry: the integrals are linear in every current; per unit current of
            # each source column (Gs: (K, 6)) and of each other passive circuit (Gp: (n, 6)).
            if i not in self._ftab:
                self._ftab[i] = self._unit_force(i, t)
            gs, gp = self._ftab[i]
            others_i = np.array([0.0 if j == i else float(currents[j]) for j in range(self.n)])
            val = (w @ gs + others_i @ gp) * float(currents[i]) * e.turns
            return val[:3], val[3:]
        p = self.posed(i, t, x, v)
        others = [filament_of(self.els[j], self.posed(j, t, x, v), float(currents[j]))
                  for j in range(self.n) if j != i and currents[j] != 0.0]
        if i == self.dyn and self.rod_tab is not None and x is not None and not others:
            g, _ = self.rod_tab.at(x)
            f = (w @ g) * float(currents[i]) * e.turns
            return f, np.cross(np.zeros(3), f)
        pieces = p.moving_pieces if p.rod is not None else list(range(len(p.geo.pieces())))
        c = p.geo.c

        def fn(piece: int, pt: Arr, dp: Arr) -> Arr:
            b = np.einsum("nkj,k->nj", self.fm.unit_b(pt), w)
            if others:
                b = b + ms.passive_fields(pt, others)[0]
            f = np.cross(dp, b)
            out: Arr = np.concatenate([f, np.cross(pt - c, f)], axis=1)
            return out

        res = mt.line_integral(p.geo, pieces, fn, 6, 1e-9, None)
        scale = float(currents[i]) * e.turns
        return res.value[:3] * scale, res.value[3:] * scale


@dataclass
class RodTable:
    """Per source column k (1 A; static last): G_k(x) = ∫_rod dl × B_k (3 components) and
    dΦ_k/dx = ∫_rod B_k·n |dl|, as piecewise Chebyshev series on [a, b] (pieces halved until
    each interpolant agrees with direct quadrature between its nodes to 1e-9 of the largest
    value), and Φ_k(x) = Φ_k(x0) + ∫_{x0}^{x} dΦ_k/dx' dx' integrated exactly from the series.
    Valid because the source geometry is static (the rod moves, the field shape does not)."""

    edges: Arr  # (M + 1,)
    coefs: list[Arr]  # per piece (deg + 1, K * 4)
    icoefs: list[Arr]  # per piece ∫_{piece start}^{x} dΦ/dx: (deg + 2, K)
    offsets: Arr  # (M, K) ∫_a^{piece start}
    phi0: Arr  # (K,) flux at x0
    f0: Arr  # (K,) ∫_a^{x0}
    k_cols: int
    degree: int
    pieces: int
    error: float

    def _f(self, x: float) -> tuple[Arr, Arr]:
        x = min(max(x, float(self.edges[0])), float(self.edges[-1]))
        m = min(int(np.searchsorted(self.edges, x, side="right")) - 1, len(self.coefs) - 1)
        a, b = float(self.edges[m]), float(self.edges[m + 1])
        u = (2 * x - (a + b)) / (b - a)
        v = np.polynomial.chebyshev.chebval(u, self.coefs[m])
        f = self.offsets[m] + np.polynomial.chebyshev.chebval(u, self.icoefs[m])
        return np.asarray(v, np.float64), np.asarray(f, np.float64)

    def at(self, x: float) -> tuple[Arr, Arr]:
        v, f = self._f(x)
        return v.reshape(self.k_cols, 4)[:, :3], self.phi0 + f - self.f0

    @staticmethod
    def build(values: Callable[[float], Arr], a: float, b: float, x0: float, phi0: Arr,
              deg: int = 16) -> RodTable:
        u = np.cos(np.pi * (np.arange(deg + 1) + 0.5) / (deg + 1))
        chk = np.array([-0.5, 0.37])
        for m in (8, 16, 32, 64):
            edges = np.linspace(a, b, m + 1)
            coefs: list[Arr] = []
            err, scale = 0.0, 0.0
            vals_all = []
            for k in range(m):
                lo, hi = float(edges[k]), float(edges[k + 1])
                vals = np.stack([values(0.5 * (lo + hi) + 0.5 * (hi - lo) * float(x)).ravel()
                                 for x in u])
                vals_all.append(vals)
                coefs.append(np.asarray(np.polynomial.chebyshev.chebfit(u, vals, deg), np.float64))
            scale = max(float(np.max(np.abs(v))) for v in vals_all) or 1.0
            for k in range(m):
                lo, hi = float(edges[k]), float(edges[k + 1])
                for cu in chk:
                    direct = values(0.5 * (lo + hi) + 0.5 * (hi - lo) * float(cu)).ravel()
                    approx = np.polynomial.chebyshev.chebval(cu, coefs[k])
                    err = max(err, float(np.max(np.abs(direct - approx))) / scale)
            if err <= 1e-9:
                k_cols = coefs[0].shape[1] // 4
                icoefs: list[Arr] = []
                offs: list[Arr] = []
                acc = np.zeros(k_cols)
                for k in range(m):
                    h = float(edges[k + 1] - edges[k])
                    dphi = coefs[k].reshape(deg + 1, k_cols, 4)[:, :, 3]
                    ic = np.polynomial.chebyshev.chebint(dphi, m=1, lbnd=-1.0, scl=0.5 * h)
                    icoefs.append(np.asarray(ic, np.float64))
                    offs.append(acc.copy())
                    acc = acc + np.polynomial.chebyshev.chebval(1.0, ic)
                tab = RodTable(edges, coefs, icoefs, np.array(offs), phi0, np.zeros(k_cols),
                               k_cols, deg, m, err)
                tab.f0 = tab._f(x0)[1]
                return tab
        raise ValueError("rod table did not converge")


def _coaxial_source_flux(g: _Geo, cs: CurrentSources, fm: mt.FieldModel) -> Arr | None:
    """Closed-form unit fluxes when the element is a circle coaxial with every prescribed
    source and all sources are circular filaments (loops, solenoid turns)."""
    if g.circle_r is None or cs.wires or cs.magnets or cs.ideal_toroids:
        return None
    out = np.zeros(len(fm.ids) + 1)
    for k, oid in enumerate(fm.ids):
        for lp in cs.loops:
            if lp.object_id != oid:
                continue
            if lp.kind == "toroid_finite":
                return None
            d = lp.center_m - g.c
            z = float(d @ g.normal)
            if np.linalg.norm(np.cross(lp.normal, g.normal)) > 1e-12 or np.linalg.norm(
                    d - z * g.normal) > 1e-12 * (1 + np.linalg.norm(g.c)):
                return None
            if lp.radius_m == g.circle_r and abs(z) <= 0.0:
                return None
            out[k] += float(np.sign(lp.normal @ g.normal)) * coaxial_mutual(
                float(g.circle_r), lp.radius_m, abs(z))
    return out


# ------------------------------------------------------------------------------- solve


METHOD = L("Coupled passive RL circuits: L(t) dI/dt = EMF_ext − RI − (dL/dt)I with EMF_ext = "
           "−dΦ_ext/dt (transformer: analytical dI_s/dt × unit fluxes; motional: ∮(u × B)·dl), "
           "integrated with the implicit Radau IIA method (adaptive, split at profile corners). "
           "Mutual inductances by Maxwell's closed form (coaxial circles) or adaptive surface "
           "quadrature; energies integrated with the currents.",
           "Csatolt passzív RL áramkörök: L(t) dI/dt = EMF_ext − RI − (dL/dt)I, ahol EMF_ext = "
           "−dΦ_ext/dt (transzformátor: analitikus dI_s/dt × egységfluxusok; mozgási: "
           "∮(u × B)·dl), "
           "implicit Radau IIA módszerrel integrálva (adaptív, a profilok töréspontjainál "
           "szakaszolva). Kölcsönös induktivitások Maxwell zárt képletével (koaxiális körök) vagy "
           "adaptív felületi kvadratúrával; az energiák az áramokkal együtt integrálva.")


def compute(scene: Scene, req: CircuitRequest) -> CircuitResult:
    tol = ms.IN_PLANE_FACTOR * scene.domain.diagonal_m
    els, problems = build_elements(req, tol)
    if problems:
        return CircuitResult(status="invalid", problems=problems, method=METHOD)
    cs = current_sources(scene)
    fm = mt.scene_field_model(scene, cs)
    sysm = _System(scene, req, els, fm, cs, tol)
    t0 = req.start_s
    x_init = sysm.x0() if sysm.dyn is not None else (None, 0.0)
    # Singularities: a prescribed filament piercing or touching a circuit.
    for i, e in enumerate(els):
        # A disk is checked through its outermost band's surface (the whole disk).
        if e.info.kind == "band" and i + 1 < len(els) and els[i + 1].disk is e.disk:
            continue
        g = sysm.posed(i, t0, x_init[0]).geo
        sing, _, _ = boundary_singularity(g, cs)
        if sing is not None:
            return CircuitResult(status="singular", status_reason=L(
                f"{e.info.name}: {sing.en}", f"{e.info.name}: {sing.hu}"), method=METHOD)
    for d in req.disks:
        bad = _axisymmetric(d, cs, [(e, sysm.posed(i, t0).geo) for i, e in enumerate(els)])
        if bad is not None:
            return CircuitResult(status="unsupported", status_reason=bad, method=METHOD,
                                 elements=[e.info for e in els])
    sysm.build_rod_table()
    mat, probs = sysm.L(t0, x_init[0])
    if probs:
        return CircuitResult(status="singular", status_reason=probs[0], problems=probs,
                             method=METHOD, elements=[e.info for e in els])
    minfo = _matrix_info(sysm, mat)
    if not minfo.positive_definite or (minfo.reciprocity_max_relative or 0.0) > RECIPROCITY_RTOL:
        why = (L("The inductance matrix is not positive definite: the magnetic energy ½IᵀLI "
                 "could be negative, which is nonphysical (circuits too close, or a "
                 "self-inductance too small for the coupling).",
                 "Az induktivitásmátrix nem pozitív definit: a ½IᵀLI mágneses energia negatív "
                 "lehetne, ami nem fizikai (túl közeli áramkörök, vagy a csatoláshoz túl kicsi "
                 "önindukció).") if not minfo.positive_definite else
               L(f"Reciprocity M_ij = M_ji fails (relative difference "
                 f"{minfo.reciprocity_max_relative:.2g}): the mutual inductances are not reliable.",
                 f"A reciprocitás M_ij = M_ji nem teljesül (relatív eltérés "
                 f"{minfo.reciprocity_max_relative:.2g}): a kölcsönös induktivitások nem "
                 "megbízhatóak."))
        return CircuitResult(status="nonphysical", status_reason=why, method=METHOD,
                             elements=[e.info for e in els], matrix=minfo)
    return _integrate(sysm, minfo)


def _matrix_info(sysm: _System, mat: Arr) -> MatrixInfo:
    ev = np.linalg.eigvalsh(0.5 * (mat + mat.T))
    return MatrixInfo(
        ids=[e.info.id for e in sysm.els], values_H=[[float(v) for v in row] for row in mat],
        method=sysm.methods, reciprocity_max_relative=sysm.recip,
        positive_definite=bool(ev.min() > PD_RTOL * ev.max()),
        min_eigenvalue_H=float(ev.min()), max_eigenvalue_H=float(ev.max()),
        time_dependent=bool(sysm.moving_idx) and sysm.n > 1)


def _corners(sysm: _System) -> list[float]:
    req = sysm.req
    out = set(sysm.fm.corners)
    for i in sysm.moving_idx:
        if i != sysm.dyn:
            out.update(mt._motion_corners(sysm.els[i].surface))
    return sorted(c for c in out if req.start_s < c < req.end_s)


def _integrate(sysm: _System, minfo: MatrixInfo) -> CircuitResult:
    req = sysm.req
    n = sysm.n
    dyn = sysm.dyn
    mov = sysm.moving_idx
    i0 = np.array([e.circuit.initial_current_A if e.circuit else 0.0 for e in sysm.els])
    x0, v0 = sysm.x0() if dyn is not None else (0.0, 0.0)
    nm = 2 if dyn is not None else 0
    # State: I (n) | x, v | Φ_ext of moving elements | Q_R, W_src, W_mot, W_geom, W_damp, W_ext
    o_mech = n
    o_phi = n + nm
    o_en = o_phi + len(mov)
    y0 = np.zeros(o_en + 6)
    y0[:n] = i0
    if dyn is not None:
        y0[o_mech:o_mech + 2] = (x0, v0)
    for k, i in enumerate(mov):
        y0[o_phi + k] = float(sysm.flux_cols(i, req.start_s, x0 if i == dyn else None)
                              @ sysm.fm.weights(req.start_s))
    mech = sysm.els[dyn].mech if dyn is not None else None

    def parts(t: float, y: Arr) -> dict[str, object]:
        sysm.evals += 1
        cur = y[:n]
        x = float(y[o_mech]) if dyn is not None else None
        v = float(y[o_mech + 1]) if dyn is not None else 0.0
        lm, _ = sysm.L(t, x)
        ld = sysm.Ldot(t, x, v)
        tr, mot = sysm.ext(t, x, v)
        di = np.linalg.solve(lm, tr + mot - sysm.R * cur - ld @ cur)
        out: dict[str, object] = {"L": lm, "Ld": ld, "tr": tr, "mot": mot, "dI": di}
        if dyn is not None and mech is not None:
            f, _ = sysm.force(dyn, t, cur, x, v)
            p = sysm.posed(dyn, t, x, v)
            assert p.rod_axis is not None
            out["F"] = float(f @ p.rod_axis)
        return out

    def rhs(t: float, y: Arr) -> Arr:
        pr = parts(t, y)
        cur = y[:n]
        dy = np.zeros_like(y)
        di = pr["dI"]
        assert isinstance(di, np.ndarray)
        dy[:n] = di
        tr, mot, ld = pr["tr"], pr["mot"], pr["Ld"]
        assert isinstance(tr, np.ndarray) and isinstance(mot, np.ndarray)
        assert isinstance(ld, np.ndarray)
        v = 0.0
        if dyn is not None and mech is not None:
            v = float(y[o_mech + 1])
            dy[o_mech] = v
            dy[o_mech + 1] = (mech.external_force_N + float(pr["F"])  # type: ignore[arg-type]
                              - mech.damping_N_s_per_m * v) / mech.mass_kg
        for k, i in enumerate(mov):
            dy[o_phi + k] = -(tr[i] + mot[i])
        dy[o_en] = float(sysm.R @ (cur * cur))
        dy[o_en + 1] = float(cur @ tr)
        dy[o_en + 2] = float(cur @ mot)
        dy[o_en + 3] = 0.5 * float(cur @ (ld @ cur))
        if mech is not None:
            dy[o_en + 4] = mech.damping_N_s_per_m * v * v
            dy[o_en + 5] = mech.external_force_N * v
        return dy

    jac: Callable[[float, Arr], Arr] | None = None
    if not mov:
        lm, _ = sysm.L(req.start_s)
        a_mat = -np.linalg.solve(lm, np.diag(sysm.R))

        def jac_fn(t: float, y: Arr) -> Arr:
            j = np.zeros((len(y), len(y)))
            j[:n, :n] = a_mat
            tr, _ = sysm.ext(t, None, 0.0)
            j[o_en, :n] = 2 * sysm.R * y[:n]
            j[o_en + 1, :n] = tr
            return j
        jac = jac_fn

    events: list[Callable[[float, Arr], float]] = []
    for i in mov:  # a sliding rod leaving its rails (or reaching the fixed end) opens the circuit
        sh = sysm.els[i].surface.shape
        if not isinstance(sh, SlidingRodShape):
            continue

        def rod_x(t: float, y: Arr, i: int = i, sh: SlidingRodShape = sh) -> float:
            if i == dyn:
                return float(y[o_mech])
            return float(sh.rod_position_m + mo.displacement(sh.rod_motion, t)[0])

        def off_end(t: float, y: Arr, f: Callable[[float, Arr], float] = rod_x,
                    sh: SlidingRodShape = sh) -> float:
            return float(sh.rail_length_m - f(t, y))

        def at_start(t: float, y: Arr, f: Callable[[float, Arr], float] = rod_x) -> float:
            return f(t, y) - sysm.tol

        off_end.terminal = True  # type: ignore[attr-defined]
        at_start.terminal = True  # type: ignore[attr-defined]
        events += [off_end, at_start]

    # Characteristic scales for the absolute tolerances.
    i_scale = max(1e-12, float(np.max(np.abs(i0))) if n else 0.0)
    try:
        tr0, mot0 = sysm.ext(req.start_s, x0 if dyn is not None else None, v0)
        i_scale = max(i_scale, float(np.max(np.abs((tr0 + mot0) / sysm.R))))
        for c in sysm.fm.corners + [req.start_s + 0.5 * (req.end_s - req.start_s)]:
            if req.start_s <= c <= req.end_s:
                tr1, _ = sysm.ext(c, x0 if dyn is not None else None, v0)
                i_scale = max(i_scale, float(np.max(np.abs(tr1 / sysm.R))))
    except Exception:  # noqa: BLE001 - scale estimate only; the solve reports failures
        pass
    atol = np.full(len(y0), 1e-12)
    atol[:n] = req.rtol * 1e-3 * i_scale
    if dyn is not None:
        atol[o_mech:o_mech + 2] = req.rtol * 1e-3 * np.array([
            max(1e-9, abs(x0)), max(1e-9, abs(v0))])
    e_scale = max(1e-30, float(np.max(sysm.R)) * i_scale * i_scale * (req.end_s - req.start_s))
    atol[o_en:] = req.rtol * 1e-3 * e_scale
    if mov:
        atol[o_phi:o_en] = req.rtol * 1e-3 * max(1e-30, float(np.max(np.abs(y0[o_phi:o_en]))
                                                              if len(mov) else 0.0) + 1e-30)

    grid = req.start_s + req.step_s * np.arange(int(math.floor(
        (req.end_s - req.start_s) / req.step_s + 1e-9)) + 1)
    grid = np.minimum(grid, req.end_s)
    breaks = [req.start_s, *_corners(sysm), req.end_s]
    sols = []
    status: Literal["solved", "stopped", "failed"] = "solved"
    reason: LocalizedText | None = None
    y = y0
    t_end = req.start_s
    steps = 0
    for a, b in zip(breaks[:-1], breaks[1:], strict=True):
        try:
            sol = solve_ivp(rhs, (a, b), y, method="Radau", rtol=req.rtol, atol=atol,
                            dense_output=True, jac=jac, events=events or None)
        except (np.linalg.LinAlgError, ValueError, FloatingPointError) as exc:
            status, reason = "failed", L(f"The integration failed: {exc}",
                                         f"Az integrálás sikertelen: {exc}")
            break
        steps += int(sol.t.size)
        if sol.status == -1:
            status, reason = "failed", L(f"The integration failed: {sol.message}",
                                         f"Az integrálás sikertelen: {sol.message}")
            break
        sols.append((a, float(sol.t[-1]), sol.sol))
        y = sol.y[:, -1]
        t_end = float(sol.t[-1])
        if sol.status == 1:
            status = "stopped"
            hit_end = sol.t_events and len(sol.t_events[0]) > 0
            reason = (L(f"The rod left the rails at t = {t_end:.6g} s: the circuit opened; the "
                        "simulation stops there.",
                        f"A rúd t = {t_end:.6g} s-kor lecsúszott a sínekről: az áramkör "
                        "megszakadt; a szimuláció itt leáll.") if hit_end else
                      L(f"The rod reached the connecting segment at t = {t_end:.6g} s (no "
                        "enclosed area); the simulation stops there.",
                        f"A rúd t = {t_end:.6g} s-kor elérte az összekötő szakaszt (nincs "
                        "közrezárt terület); a szimuláció itt leáll."))
            break
    if not sols:
        return CircuitResult(status="failed", status_reason=reason, method=METHOD,
                             elements=[e.info for e in sysm.els], matrix=minfo)

    def state_at(t: float) -> Arr:
        for a, b, f in reversed(sols):
            if a <= t <= b:
                out: Arr = f(t)
                return out
        raise ValueError(t)

    ts = [float(t) for t in grid if t <= t_end + 1e-12 * max(1.0, abs(t_end))]
    series = _series(sysm, ts, state_at, o_mech, o_phi, o_en, parts)
    return CircuitResult(status=status, status_reason=reason, method=METHOD,
                         elements=[e.info for e in sysm.els], matrix=minfo, series=series,
                         solver_steps=steps, rhs_evaluations=sysm.evals, end_time_s=t_end,
                         warnings=_warnings(sysm) + ([sysm.rod_tab_note] if sysm.rod_tab_note
                                                     else []))


def _warnings(sysm: _System) -> list[LocalizedText]:
    out: list[LocalizedText] = []
    if sysm.req.disks:
        out.append(L("Eddy-current disk: reduced-order axisymmetric approximation by "
                     "concentric annular bands (no skin effect, no radial current, no thermal "
                     "or temperature effects); its accuracy is limited by the band "
                     "discretization.",
                     "Örvényáramú korong: redukált rendű, tengelyszimmetrikus közelítés "
                     "koncentrikus körgyűrű-sávokkal (nincs szkinhatás, radiális áram, hő- "
                     "vagy hőmérséklethatás); pontosságát a sávfelosztás korlátozza."))
    return out


def _series(sysm: _System, ts: list[float], state_at: Callable[[float], Arr], o_mech: int,
            o_phi: int, o_en: int, parts: Callable[[float, Arr], dict[str, object]]
            ) -> CircuitSeries:
    n = sysm.n
    dyn = sysm.dyn
    mov = sysm.moving_idx
    cols: dict[str, list[list[float]]] = {k: [[] for _ in range(n)] for k in (
        "I", "dI", "phi", "lam", "tr", "mot", "ri", "pr")}
    forces: list[list[list[float]] | None] = [[] if e.info.kind == "circuit" else None
                                              for e in sysm.els]
    torques: list[list[list[float]] | None] = [[] if e.info.kind == "circuit" else None
                                               for e in sysm.els]
    pmech: list[list[float] | None] = [[] if e.info.kind == "circuit" else None
                                       for e in sysm.els]
    fils: list[list[PassiveFilament]] = [[] for _ in range(n)]
    wm, q, wsrc, wmot, wgeo, res, pres = [], [], [], [], [], [], []
    ke: list[float] = []
    wd: list[float] = []
    wx: list[float] = []
    xs: list[float] = []
    vs: list[float] = []
    w0: float | None = None
    k0 = 0.0
    for t in ts:
        y = state_at(t)
        cur = y[:n]
        x = float(y[o_mech]) if dyn is not None else None
        v = float(y[o_mech + 1]) if dyn is not None else 0.0
        pr = parts(t, y)
        lm, di, tr, mot, ld = pr["L"], pr["dI"], pr["tr"], pr["mot"], pr["Ld"]
        assert isinstance(lm, np.ndarray) and isinstance(di, np.ndarray)
        assert isinstance(tr, np.ndarray) and isinstance(mot, np.ndarray)
        assert isinstance(ld, np.ndarray)
        weights = sysm.fm.weights(t)
        p_mech_total = 0.0
        for i, e in enumerate(sysm.els):
            if e.moving:
                phi = float(y[o_phi + mov.index(i)])
            else:
                phi = float(sysm.flux_cols(i, t) @ weights)
            cols["I"][i].append(float(cur[i]))
            cols["dI"][i].append(float(di[i]))
            cols["phi"][i].append(phi)
            cols["lam"][i].append(phi + float(lm[i] @ cur))
            cols["tr"][i].append(float(tr[i]))
            cols["mot"][i].append(float(mot[i]))
            cols["ri"][i].append(float(e.R * cur[i]))
            cols["pr"][i].append(float(e.R * cur[i] ** 2))
            p = sysm.posed(i, t, x if i == dyn else None, v)
            if e.moving or not fils[i]:
                fils[i].append(filament_of(e, p))
            if e.info.kind == "circuit":
                f, tau = sysm.force(i, t, cur, x if i == dyn else None, v)
                fl, tl, pl = forces[i], torques[i], pmech[i]
                assert fl is not None and tl is not None and pl is not None
                fl.append([float(c) for c in f])
                tl.append([float(c) for c in tau])
                pm = 0.0
                if e.moving:
                    if p.rod is not None:
                        assert p.rod_axis is not None
                        pm = float(f @ (p.rod_axis * (v if i == dyn else p.rod[2])))
                    elif p.pose is not None:
                        pm = float(f @ p.pose.velocity("right") + tau @ p.pose.omega("right"))
                pl.append(pm)
                p_mech_total += pm
        w = 0.5 * float(cur @ (lm @ cur))
        if w0 is None:
            w0 = w
        wm.append(w)
        q.append(float(y[o_en]))
        wsrc.append(float(y[o_en + 1]))
        wmot.append(float(y[o_en + 2]))
        wgeo.append(float(y[o_en + 3]))
        p_r = float(sysm.R @ (cur * cur))
        dw = float(cur @ (lm @ di)) + 0.5 * float(cur @ (ld @ cur))
        p_src = float(cur @ tr)
        # Instantaneous balance: the EM forces' mechanical power (from ∮ I dl × B_ext, an
        # independent integral) + P_R + dW_m/dt − P_source = 0. Only defined where every moving
        # conductor's force is computed (circuits; bands do not move).
        pres.append(p_mech_total + p_r + dw - p_src)
        if dyn is not None:
            mech = sysm.els[dyn].mech
            assert mech is not None
            k = 0.5 * mech.mass_kg * v * v
            if not ke:
                k0 = k
            ke.append(k)
            wd.append(float(y[o_en + 4]))
            wx.append(float(y[o_en + 5]))
            xs.append(float(x if x is not None else 0.0))
            vs.append(v)
            res.append((k - k0) + wd[-1] - wx[-1] + (w - w0) + q[-1] - wsrc[-1])
        else:
            # Without mechanical dynamics: ΔW_m + Q_R + W_geom − W_src − W_mot (the circuit
            # energy equation; W_mot = −mechanical work of the EM forces on moving conductors).
            res.append((w - w0) + q[-1] + wgeo[-1] - wsrc[-1] - wmot[-1])
    dens: list[list[float] | None] = []
    for i, e in enumerate(sysm.els):
        if e.info.kind == "band":
            a = float(e.info.thickness_m or 0) * float(e.info.width_m or 0)
            dens.append([c / a for c in cols["I"][i]])
        else:
            dens.append(None)
    return CircuitSeries(
        t_s=ts, current_A=cols["I"], dI_dt_A_per_s=cols["dI"], flux_external_Wb=cols["phi"],
        flux_linkage_Wb=cols["lam"], emf_transformer_V=cols["tr"], emf_motional_V=cols["mot"],
        resistive_drop_V=cols["ri"], joule_power_W=cols["pr"], current_density_A_per_m2=dens,
        force_N=forces, torque_N_m=torques, mechanical_power_W=pmech, magnetic_energy_J=wm,
        joule_heat_J=q, source_work_J=wsrc, motional_work_J=wmot, geometric_work_J=wgeo,
        kinetic_energy_J=ke or None, damping_heat_J=wd or None, external_work_J=wx or None,
        rod_position_m=xs or None, rod_velocity_m_per_s=vs or None, energy_residual_J=res,
        power_residual_W=list(pres), filaments=fils)


def fingerprint(scene: Scene, req: CircuitRequest) -> str:
    s = scene.model_dump(mode="json")
    for o in s["objects"]:
        o.pop("name", None)
    payload = json.dumps({"scene": s, "circuits": [c.physics_dump() for c in req.circuits],
                          "disks": [d.physics_dump() for d in req.disks],
                          "grid": [req.start_s, req.end_s, req.step_s, req.rtol]},
                         sort_keys=True, separators=(",", ":"))
    return "circuits:" + hashlib.sha256(payload.encode()).hexdigest()


__all__ = ["CircuitRequest", "CircuitResult", "EddyDisk", "PassiveCircuit", "compute",
           "coaxial_mutual", "thin_loop_inductance", "LoopSource"]
