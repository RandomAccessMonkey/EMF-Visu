"""Ideal coaxial cable, TEM transmission-line model (closed form).

Geometry: inner conductor radius a, outer conductor inner radius b and outer radius c, length L;
the dielectric (ε = ε0 εr, μ = μ0 μr) fills a < r < b. Both conductors are perfect conductors, the
dielectric is homogeneous, linear, isotropic, non-dispersive and lossless, and only the TEM mode
propagates. Everything here is evaluated analytically; nothing is solved numerically except the
cross-check quadratures and finite differences that are reported next to the analytical values.

Conventions (documented in docs/architecture.md and shown in the UI):

* Cylindrical coordinates (r, φ, z) with z along the cable axis: z = 0 is the source end and
  z = L the load end. φ̂ = ẑ × r̂ (right-handed); in Cartesian terms the cross-section is the
  x-y plane at the chosen z.
* V(z, t) is the potential of the inner conductor relative to the outer one. I(z, t) > 0 means
  current in +z on the inner conductor (and the same current in −z on the outer conductor).
* Excitation f(t) is the forward wave the source launches into the line at z = 0:
  sinusoidal f(t) = A sin(2π f t) for t ≥ 0 and 0 before (switched on at t = 0), or Gaussian
  f(t) = A exp(−(t − t0)² / (2σ²)) with σ the width parameter.
* Load reflection Γ_L = (Z_L − Z0)/(Z_L + Z0): matched 0, open +1, short −1. Source-end
  reflection Γ_S for the waves returning to z = 0: matched 0 (default), short −1 (ideal voltage
  source, Z_S = 0), open +1 (ideal current source, Z_S → ∞).

With T = L/vp the closed-form multiple-reflection solution is

    V_f(z, t) = Σ_n (Γ_L Γ_S)^n f(t − 2nT − z/vp)
    V_b(z, t) = Γ_L Σ_n (Γ_L Γ_S)^n f(t − 2(n+1)T + z/vp)
    V = V_f + V_b,   I = (V_f − V_b)/Z0,

which satisfies the telegrapher equations, V_b(L) = Γ_L V_f(L) and V_f(0) − f = Γ_S V_b(0).
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .solvers.base import ModelContext
from .units import EPS0, MU0

C0 = 1.0 / math.sqrt(float(EPS0) * float(MU0))

# Bounds that keep every quantity finite and every array small (validation, not physics).
MAX_REFLECTION_TERMS = 20000
FIELD_LINES = 16  # number of E lines (radial) and of H lines (circles) in the cross-section
LINE_POINTS = 241  # samples of V(z), I(z) along the cable
GAUSS_TAIL_SIGMAS = 40.0  # a Gaussian is exactly 0 in double precision beyond ~38.6 σ


class CoaxGeometry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inner_radius_m: float = Field(gt=0, le=10.0, allow_inf_nan=False)  # a
    shield_inner_radius_m: float = Field(gt=0, le=10.0, allow_inf_nan=False)  # b
    shield_outer_radius_m: float = Field(gt=0, le=10.0, allow_inf_nan=False)  # c
    length_m: float = Field(gt=0, le=1e5, allow_inf_nan=False)  # L

    @model_validator(mode="after")
    def _order(self) -> CoaxGeometry:
        a, b, c = self.inner_radius_m, self.shield_inner_radius_m, self.shield_outer_radius_m
        if not a < b:
            raise ValueError("the radii must satisfy a < b (inner radius below the shield's "
                             "inner radius)")
        if not b < c:
            raise ValueError("the radii must satisfy b < c (the shield needs a positive "
                             "thickness)")
        if b / a < 1.0 + 1e-6:
            raise ValueError("b/a is too close to 1: ln(b/a) would be numerically meaningless")
        return self


class CoaxMaterial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relative_permittivity: float = Field(gt=0, le=1e4, allow_inf_nan=False)
    relative_permeability: float = Field(gt=0, le=1e4, allow_inf_nan=False)


class SinusoidalExcitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["sinusoidal"] = "sinusoidal"
    amplitude_V: float = Field(allow_inf_nan=False, ge=-1e9, le=1e9)
    frequency_Hz: float = Field(gt=0, le=1e15, allow_inf_nan=False)


class GaussianExcitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["gaussian"] = "gaussian"
    amplitude_V: float = Field(allow_inf_nan=False, ge=-1e9, le=1e9)
    center_s: float = Field(allow_inf_nan=False, ge=-1e3, le=1e3)
    width_s: float = Field(gt=0, le=1e3, allow_inf_nan=False)  # σ


Excitation = Annotated[SinusoidalExcitation | GaussianExcitation, Field(discriminator="type")]
Termination = Literal["matched", "open", "short"]
GAMMA: dict[str, float] = {"matched": 0.0, "open": 1.0, "short": -1.0}


class CoaxSpec(BaseModel):
    """The complete physical definition of the cable model."""

    model_config = ConfigDict(extra="forbid")
    geometry: CoaxGeometry
    material: CoaxMaterial
    excitation: Excitation
    load: Termination = "matched"
    source: Termination = "matched"


class TimeRange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_s: float = Field(allow_inf_nan=False)
    end_s: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def _order(self) -> TimeRange:
        if not self.end_s > self.start_s:
            raise ValueError("the simulation time range needs end > start")
        return self


class CoaxSnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: CoaxSpec
    t_s: float = Field(allow_inf_nan=False)
    z_m: float = Field(allow_inf_nan=False)  # cross-section position, 0 ≤ z ≤ L
    # Playback range: sets the fixed amplitude scale of the arrows (max |V|, |I| over it).
    range: TimeRange
    probe_m: tuple[float, float] | None = None  # (x, y) in the cross-section at z
    stations: int = Field(default=33, ge=3, le=129)  # cross-sections drawn in 3D

    @model_validator(mode="after")
    def _z(self) -> CoaxSnapshotRequest:
        if not 0.0 <= self.z_m <= self.spec.geometry.length_m:
            raise ValueError("the cross-section position must satisfy 0 ≤ z ≤ L")
        return self


class CoaxTraceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spec: CoaxSpec
    z_m: float = Field(allow_inf_nan=False)
    range: TimeRange
    count: int = Field(default=401, ge=2, le=4001)

    @model_validator(mode="after")
    def _z(self) -> CoaxTraceRequest:
        if not 0.0 <= self.z_m <= self.spec.geometry.length_m:
            raise ValueError("the observation position must satisfy 0 ≤ z ≤ L")
        return self


class CoaxError(ValueError):
    """A configuration that the closed-form model cannot evaluate (reported, never rendered)."""


# ------------------------------------------------------------------------- line parameters


class LineParameters(BaseModel):
    epsilon_F_per_m: float
    mu_H_per_m: float
    ln_b_over_a: float
    L_per_m_H: float
    C_per_m_F: float
    Z0_ohm: float
    vp_m_per_s: float
    vp_over_c: float
    delay_s: float
    gamma_load: float
    gamma_source: float
    # Cutoff of the lowest higher-order mode (TE11), approximation f_c ≈ vp / (π (a + b) / 2);
    # above it the TEM-only assumption no longer holds.
    te11_cutoff_Hz: float


def parameters(spec: CoaxSpec) -> LineParameters:
    g, m = spec.geometry, spec.material
    eps = float(EPS0) * m.relative_permittivity
    mu = float(MU0) * m.relative_permeability
    ln = math.log(g.shield_inner_radius_m / g.inner_radius_m)
    lp = mu / (2 * math.pi) * ln
    cp = 2 * math.pi * eps / ln
    vp = 1.0 / math.sqrt(lp * cp)
    return LineParameters(
        epsilon_F_per_m=eps, mu_H_per_m=mu, ln_b_over_a=ln, L_per_m_H=lp, C_per_m_F=cp,
        Z0_ohm=math.sqrt(lp / cp), vp_m_per_s=vp, vp_over_c=vp / C0,
        delay_s=g.length_m / vp, gamma_load=GAMMA[spec.load], gamma_source=GAMMA[spec.source],
        te11_cutoff_Hz=vp / (math.pi * (g.inner_radius_m + g.shield_inner_radius_m) / 2))


def reflection_coefficient(z_load_ohm: float, z0_ohm: float) -> float:
    """Γ = (Z_L − Z0)/(Z_L + Z0); Z_L = inf gives +1 (open)."""
    if math.isinf(z_load_ohm):
        return 1.0
    return (z_load_ohm - z0_ohm) / (z_load_ohm + z0_ohm)


# ----------------------------------------------------------------------------- excitation

Arr = NDArray[np.float64]


def signal(exc: SinusoidalExcitation | GaussianExcitation, t: Arr) -> tuple[Arr, Arr]:
    """f(t) and df/dt. The switched-on sinusoid has a kink at t = 0: there df/dt is the
    right-hand value (one-sided); see ``kink_times``."""
    t = np.asarray(t, dtype=float)
    if isinstance(exc, SinusoidalExcitation):
        w = 2 * math.pi * exc.frequency_Hz
        on = t >= 0
        f = np.where(on, exc.amplitude_V * np.sin(w * t), 0.0)
        df = np.where(on, exc.amplitude_V * w * np.cos(w * t), 0.0)
        return f, df
    s = exc.width_s
    u = (t - exc.center_s) / s
    f = exc.amplitude_V * np.exp(-0.5 * u * u)
    return f, -u / s * f


def _earliest(exc: SinusoidalExcitation | GaussianExcitation) -> float:
    """Argument below which f is exactly zero (switched sinusoid) or below double precision."""
    if isinstance(exc, SinusoidalExcitation):
        return 0.0
    return exc.center_s - GAUSS_TAIL_SIGMAS * exc.width_s


def time_scale(exc: SinusoidalExcitation | GaussianExcitation) -> float:
    """Characteristic time of the signal (period or σ), for finite-difference steps."""
    return 1.0 / exc.frequency_Hz if isinstance(exc, SinusoidalExcitation) else exc.width_s


def _terms(spec: CoaxSpec, p: LineParameters, t_max: float) -> int:
    """Number of round trips n that can contribute up to time t_max."""
    if p.gamma_load == 0.0 or p.gamma_source == 0.0:
        return 1
    n = int(math.floor((t_max - _earliest(spec.excitation)) / (2 * p.delay_s))) + 2
    n = max(n, 1)
    if n > MAX_REFLECTION_TERMS:
        raise CoaxError(
            f"the time range spans {n} round trips of the cable with reflections at both ends "
            f"(more than {MAX_REFLECTION_TERMS}); shorten the range or match one end")
    return n


class Waves(BaseModel):
    """Forward/backward voltage components and their derivatives on a (z, t) array."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    Vf: Arr
    Vb: Arr
    dVf_dt: Arr
    dVb_dt: Arr
    kink: NDArray[np.bool_]  # a switched-on sinusoid's front passes within the FD step


def waves(spec: CoaxSpec, p: LineParameters, z: Arr | float, t: Arr | float,
          kink_window_s: float = 0.0) -> Waves:
    z = np.asarray(z, dtype=float)
    t = np.asarray(t, dtype=float)
    z, t = np.broadcast_arrays(z, t)
    vp, T = p.vp_m_per_s, p.delay_s
    gl, gs = p.gamma_load, p.gamma_source
    n_terms = _terms(spec, p, float(np.max(t)) if t.size else 0.0)
    lo = _earliest(spec.excitation)
    Vf = np.zeros(z.shape)
    Vb = np.zeros(z.shape)
    dVf = np.zeros(z.shape)
    dVb = np.zeros(z.shape)
    kink = np.zeros(z.shape, dtype=bool)
    sin = isinstance(spec.excitation, SinusoidalExcitation)
    for n in range(n_terms):
        w = (gl * gs) ** n
        if w == 0.0 and n > 0:
            break
        tf = t - 2 * n * T - z / vp
        if np.all(tf < lo) and n > 0:
            break
        f, df = signal(spec.excitation, tf)
        Vf += w * f
        dVf += w * df
        if sin:
            kink |= np.abs(tf) <= kink_window_s
        if gl != 0.0:
            tb = t - 2 * (n + 1) * T + z / vp
            f, df = signal(spec.excitation, tb)
            Vb += gl * w * f
            dVb += gl * w * df
            if sin:
                kink |= np.abs(tb) <= kink_window_s
    return Waves(Vf=Vf, Vb=Vb, dVf_dt=dVf, dVb_dt=dVb, kink=kink)


def line_state(spec: CoaxSpec, p: LineParameters, z: Arr | float, t: Arr | float
               ) -> dict[str, Arr]:
    """V, I and their z and t derivatives (analytic, from the wave components)."""
    w = waves(spec, p, z, t)
    vp, z0 = p.vp_m_per_s, p.Z0_ohm
    V = w.Vf + w.Vb
    I = (w.Vf - w.Vb) / z0  # noqa: E741
    dV_dt = w.dVf_dt + w.dVb_dt
    dI_dt = (w.dVf_dt - w.dVb_dt) / z0
    # ∂/∂z of f(t ∓ z/vp) is ∓ f'/vp.
    dV_dz = (-w.dVf_dt + w.dVb_dt) / vp
    dI_dz = (-w.dVf_dt - w.dVb_dt) / (vp * z0)
    return {"Vf": w.Vf, "Vb": w.Vb, "V": V, "I": I, "If": w.Vf / z0, "Ib": -w.Vb / z0,
            "dV_dt": dV_dt, "dI_dt": dI_dt, "dV_dz": dV_dz, "dI_dz": dI_dz}


# --------------------------------------------------------------------------------- fields

Region = Literal["inner_conductor", "inner_surface", "dielectric", "shield_surface",
                 "shield", "outside"]


def region(g: CoaxGeometry, r: float) -> Region:
    """Region of radius r; a surface is the radius within 1e-9 b of r = a or r = b."""
    tol = 1e-9 * g.shield_inner_radius_m
    a, b, c = g.inner_radius_m, g.shield_inner_radius_m, g.shield_outer_radius_m
    if abs(r - a) <= tol:
        return "inner_surface"
    if abs(r - b) <= tol:
        return "shield_surface"
    if r < a:
        return "inner_conductor"
    if r < b:
        return "dielectric"
    if r <= c:
        return "shield"
    return "outside"


def radial_fields(p: LineParameters, r: Arr | float, V: Arr | float, I: Arr | float  # noqa: E741
                  ) -> dict[str, Arr]:
    """E_r, D_r, H_φ, B_φ, S_z in the dielectric (the caller masks the other regions)."""
    r = np.asarray(r, dtype=float)
    Er = np.asarray(V) / (r * p.ln_b_over_a)
    Hp = np.asarray(I) / (2 * math.pi * r)
    return {"E_r": Er, "D_r": p.epsilon_F_per_m * Er, "H_phi": Hp, "B_phi": p.mu_H_per_m * Hp,
            "S_z": Er * Hp}


def cartesian_fields(spec: CoaxSpec, p: LineParameters, x: Arr, y: Arr, z: Arr, t: Arr
                     ) -> dict[str, Arr]:
    """E, D, H, B, S (shape (..., 3)) at Cartesian points; zero outside the dielectric."""
    x, y, z, t = np.broadcast_arrays(*(np.asarray(v, dtype=float) for v in (x, y, z, t)))
    r = np.hypot(x, y)
    g = spec.geometry
    inside = (r > g.inner_radius_m) & (r < g.shield_inner_radius_m)
    s = line_state(spec, p, z, t)
    rs = np.where(inside, r, 1.0)
    f = radial_fields(p, rs, s["V"], s["I"])
    cx, cy = np.where(inside, x / rs, 0.0), np.where(inside, y / rs, 0.0)
    zero = np.zeros_like(r)

    def rad(v: Arr) -> Arr:
        v = np.where(inside, v, 0.0)
        return np.stack([v * cx, v * cy, zero], axis=-1)

    def azi(v: Arr) -> Arr:
        v = np.where(inside, v, 0.0)
        return np.stack([-v * cy, v * cx, zero], axis=-1)

    return {"E": rad(f["E_r"]), "D": rad(f["D_r"]), "H": azi(f["H_phi"]),
            "B": azi(f["B_phi"]),
            "S": np.stack([zero, zero, np.where(inside, f["S_z"], 0.0)], axis=-1)}


# ------------------------------------------------------------------------- Poynting power


def poynting_power(p: LineParameters, g: CoaxGeometry, V: float, I: float,  # noqa: E741
                   n_r: int = 48, n_phi: int = 64) -> float:
    """∫∫ S_z dA over the dielectric annulus by numerical quadrature: Gauss–Legendre in r
    (n_r nodes on [a, b]) and the midpoint rule in φ, on the Cartesian field values (S = E × H
    evaluated pointwise, not the closed-form integral)."""
    a, b = g.inner_radius_m, g.shield_inner_radius_m
    xg, wg = np.polynomial.legendre.leggauss(n_r)
    r = 0.5 * (b - a) * xg + 0.5 * (b + a)
    wr = 0.5 * (b - a) * wg
    phi = (np.arange(n_phi) + 0.5) * 2 * math.pi / n_phi
    R, PH = np.meshgrid(r, phi, indexing="ij")
    f = radial_fields(p, R, V, I)
    Er = f["E_r"]
    Hp = f["H_phi"]
    # Cartesian E and H, then the z-component of their cross product.
    Ex, Ey = Er * np.cos(PH), Er * np.sin(PH)
    Hx, Hy = -Hp * np.sin(PH), Hp * np.cos(PH)
    Sz = Ex * Hy - Ey * Hx
    return float(np.sum(Sz * R * wr[:, None]) * (2 * math.pi / n_phi))


# ------------------------------------------------------------------------------ responses


class ScalarCheck(BaseModel):
    """One side of a differential law: the analytic value (from the wave derivatives) and an
    independent central finite difference of the field itself."""

    analytic: float
    numerical: float


class LawCheck(BaseModel):
    id: str  # equation id in the registry
    component: str  # which cylindrical component is compared, e.g. "φ"
    unit: str
    lhs: ScalarCheck
    rhs: ScalarCheck
    residual: float  # |lhs_analytic − rhs_analytic| / scale
    fd_rel_error: float  # max relative difference analytic vs finite difference
    status: Literal["agree", "nonsmooth", "zero_field"]


class Calculus(BaseModel):
    point_m: tuple[float, float, float]
    r_m: float
    div_D: float  # = ρ_free = 0 in the dielectric (finite difference of D)
    div_B: float
    div_scale: float  # |D|/h-type scale for judging the finite-difference zero
    div_B_scale: float
    checks: list[LawCheck]
    telegrapher: list[LawCheck]


class Boundary(BaseModel):
    """Surface (distributional) quantities on the conductor/dielectric interfaces at z."""

    rho_s_inner_C_per_m2: float  # = D_r(a⁺)
    rho_s_shield_C_per_m2: float  # = −D_r(b⁻)
    K_z_inner_A_per_m: float  # = H_φ(a⁺)
    K_z_shield_A_per_m: float  # = −H_φ(b⁻)
    Q_per_m_C: float  # C' V: charge per unit length on the inner conductor
    I_A: float


class Probe(BaseModel):
    point_m: tuple[float, float, float]
    r_m: float
    phi_rad: float
    region: Region
    E: tuple[float, float, float]
    D: tuple[float, float, float]
    H: tuple[float, float, float]
    B: tuple[float, float, float]
    S: tuple[float, float, float]
    E_r: float
    H_phi: float
    S_z: float
    w_e_J_per_m3: float
    w_m_J_per_m3: float
    # On r = a or r = b the volume fields jump: the dielectric-side limit is given and the
    # surface charge / current density there (a distributional, not a volume, quantity).
    surface_charge_C_per_m2: float | None = None
    surface_current_A_per_m: float | None = None


class CrossSection(BaseModel):
    """Arrow samples in the cross-section at z (dielectric only), x-y Cartesian."""

    points_m: list[tuple[float, float]]
    E: list[tuple[float, float]]
    H: list[tuple[float, float]]
    S_z: list[float]
    e_line_angles_rad: list[float]  # radial E lines (equal flux between neighbours)
    h_line_radii_m: list[float]  # circular H lines, log-spaced: line density ∝ |H| ∝ 1/r
    e_sign: int  # +1: E points outward (V > 0), −1 inward, 0 none
    h_sign: int  # +1: H along +φ (I > 0), −1 along −φ, 0 none
    # Sample layout: points_m is ring-major (ring i, angle j at index i·n_angles + j); each ring
    # is the centre of one of len(rings_m) equal radial segments of length segment_m that keep a
    # margin from both conductor surfaces (see sample_rings).
    rings_m: list[float] = []
    n_angles: int = 0
    segment_m: float = 0.0


class Stations(BaseModel):
    """Cross-sections along the cable for the 3D view: per station V, I and sample vectors."""

    z_m: list[float]
    V: list[float]
    I: list[float]  # noqa: E741
    r_m: float  # radius of the arrow samples (geometric mean √(ab))
    E_r: list[float]  # at r_m, per station
    H_phi: list[float]
    S_z: list[float]
    # The same quantities at every sample ring (sample_rings), per station: [station][ring].
    rings_m: list[float] = []
    segment_m: float = 0.0
    E_r_rings: list[list[float]] = []
    H_phi_rings: list[list[float]] = []
    S_z_rings: list[list[float]] = []


class LineProfile(BaseModel):
    z_m: list[float]
    V: list[float]
    I: list[float]  # noqa: E741
    Vf: list[float]
    Vb: list[float]
    P_W: list[float]


class Power(BaseModel):
    P_poynting_W: float  # numerical ∫∫ S_z dA
    P_VI_W: float  # V(z, t) I(z, t)
    abs_error_W: float
    rel_error: float | None  # None when both are (numerically) zero
    nodes: tuple[int, int]


class CoaxSnapshot(BaseModel):
    params: LineParameters
    t_s: float
    z_m: float
    V: float
    I: float  # noqa: E741
    Vf: float
    Vb: float
    If: float
    Ib: float
    scale_V: float  # max |V| over the playback range (fixed arrow scale)
    scale_I: float
    warnings: list[str]
    line: LineProfile
    cross_section: CrossSection
    stations: Stations
    power: Power
    calculus: Calculus
    boundary: Boundary
    probe: Probe | None


class CoaxTrace(BaseModel):
    params: LineParameters
    z_m: float
    t_s: list[float]
    V: list[float]
    I: list[float]  # noqa: E741
    P_W: list[float]
    V_source: list[float]
    V_load: list[float]
    I_load: list[float]


# --------------------------------------------------------------------------- computation


def warnings(spec: CoaxSpec, p: LineParameters) -> list[str]:
    out: list[str] = []
    exc = spec.excitation
    if isinstance(exc, SinusoidalExcitation):
        if exc.frequency_Hz >= p.te11_cutoff_Hz:
            out.append("above_te11_cutoff")
    elif 1.0 / (2 * math.pi * exc.width_s) * 3 >= p.te11_cutoff_Hz:
        # Spectrum of the Gaussian: |F(f)| ∝ exp(−(2πfσ)²/2), 1 % at f ≈ 3/(2πσ).
        out.append("above_te11_cutoff")
    return out


SAMPLE_RINGS = 4
SAMPLE_MARGIN = 0.08  # fraction of b − a kept free next to each conductor surface
SECTION_ANGLES = 48


def sample_rings(g: CoaxGeometry, n: int = SAMPLE_RINGS, margin: float = SAMPLE_MARGIN
                 ) -> tuple[list[float], float]:
    """Display sample radii: [a + m, b − m] (m = margin·(b − a)) split into n equal segments;
    returns the segment centres and the segment length. An arrow centred on a ring and no longer
    than one segment never reaches a conductor surface, whatever its sign."""
    a, b = g.inner_radius_m, g.shield_inner_radius_m
    m = margin * (b - a)
    seg = (b - a - 2 * m) / n
    return [a + m + (i + 0.5) * seg for i in range(n)], seg


def _cross_section(p: LineParameters, g: CoaxGeometry, V: float, I: float  # noqa: E741
                   ) -> CrossSection:
    a, b = g.inner_radius_m, g.shield_inner_radius_m
    radii, seg = sample_rings(g)
    pts: list[tuple[float, float]] = []
    E: list[tuple[float, float]] = []
    H: list[tuple[float, float]] = []
    S: list[float] = []
    n = SECTION_ANGLES
    for r in radii:
        f = radial_fields(p, r, V, I)
        for j in range(n):
            ph = 2 * math.pi * j / n
            cx, cy = math.cos(ph), math.sin(ph)
            er, hp = float(f["E_r"]), float(f["H_phi"])
            pts.append((r * cx, r * cy))
            E.append((er * cx, er * cy))
            H.append((-hp * cy, hp * cx))
            S.append(er * hp)
    n_l = FIELD_LINES
    return CrossSection(
        points_m=pts, E=E, H=H, S_z=S,
        e_line_angles_rad=[2 * math.pi * k / n_l for k in range(n_l)],
        h_line_radii_m=[float(a * (b / a) ** ((k + 0.5) / 8)) for k in range(8)],
        e_sign=int(np.sign(V)), h_sign=int(np.sign(I)), rings_m=radii, n_angles=n,
        segment_m=seg)


def _check(id_: str, comp: str, unit: str, lhs: tuple[float, float],
           rhs: tuple[float, float], scale: float, nonsmooth: bool) -> LawCheck:
    la, ln_ = lhs
    ra, rn = rhs
    if scale <= 0 or not math.isfinite(scale):
        return LawCheck(id=id_, component=comp, unit=unit, lhs=ScalarCheck(analytic=la,
                        numerical=ln_), rhs=ScalarCheck(analytic=ra, numerical=rn),
                        residual=0.0, fd_rel_error=0.0, status="zero_field")
    res = abs(la - ra) / scale
    fd = max(abs(la - ln_), abs(ra - rn)) / scale
    return LawCheck(id=id_, component=comp, unit=unit, lhs=ScalarCheck(analytic=la, numerical=ln_),
                    rhs=ScalarCheck(analytic=ra, numerical=rn), residual=res, fd_rel_error=fd,
                    status="nonsmooth" if nonsmooth else "agree")


def calculus(spec: CoaxSpec, p: LineParameters, point: tuple[float, float, float], t: float
             ) -> Calculus:
    """Divergence and curl at a point of the dielectric. The analytic side uses the exact
    wave derivatives; the numerical side is a central finite difference of the Cartesian
    field functions (independent of the closed-form derivatives)."""
    x, y, z = point
    r = math.hypot(x, y)
    g = spec.geometry
    ts = time_scale(spec.excitation)
    ht = 1e-4 * min(ts, p.delay_s if p.delay_s > 0 else ts)
    hz = p.vp_m_per_s * ht
    hr = 1e-4 * (g.shield_inner_radius_m - g.inner_radius_m)
    cphi, sphi = (x / r, y / r) if r > 0 else (1.0, 0.0)

    def fld(dx: float = 0, dy: float = 0, dz: float = 0, dt: float = 0) -> dict[str, Arr]:
        return cartesian_fields(spec, p, np.array(x + dx), np.array(y + dy),
                                np.array(z + dz), np.array(t + dt))

    def d(name: str, axis: str, comp: int) -> float:
        h = {"x": hr, "y": hr, "z": hz, "t": ht}[axis]
        plus = fld(**{("d" + axis): h})[name][..., comp]
        minus = fld(**{("d" + axis): -h})[name][..., comp]
        return float((plus - minus) / (2 * h))

    div_D = d("D", "x", 0) + d("D", "y", 1) + d("D", "z", 2)
    div_B = d("B", "x", 0) + d("B", "y", 1) + d("B", "z", 2)
    # Curls (Cartesian finite differences), projected on φ̂ and r̂.
    curlE = np.array([d("E", "y", 2) - d("E", "z", 1), d("E", "z", 0) - d("E", "x", 2),
                      d("E", "x", 1) - d("E", "y", 0)])
    curlH = np.array([d("H", "y", 2) - d("H", "z", 1), d("H", "z", 0) - d("H", "x", 2),
                      d("H", "x", 1) - d("H", "y", 0)])
    dBdt = np.array([d("B", "t", k) for k in range(3)])
    dDdt = np.array([d("D", "t", k) for k in range(3)])
    rhat = np.array([cphi, sphi, 0.0])
    phat = np.array([-sphi, cphi, 0.0])
    zhat = np.array([0.0, 0.0, 1.0])

    w = waves(spec, p, z, t, kink_window_s=3 * ht)
    nonsmooth = bool(np.any(w.kink))
    s = line_state(spec, p, z, t)
    ln = p.ln_b_over_a
    curlE_phi = float(s["dV_dz"]) / (r * ln)
    mdBdt_phi = -p.mu_H_per_m * float(s["dI_dt"]) / (2 * math.pi * r)
    curlH_r = -float(s["dI_dz"]) / (2 * math.pi * r)
    dDdt_r = p.epsilon_F_per_m * float(s["dV_dt"]) / (r * ln)

    # Scales: the size of the terms (from |∂f/∂t| over the waves), so that the residual of a
    # law is relative to the magnitude of its own terms.
    vt = abs(float(w.dVf_dt)) + abs(float(w.dVb_dt))
    scale_faraday = p.mu_H_per_m * vt / p.Z0_ohm / (2 * math.pi * r)
    scale_ampere = p.epsilon_F_per_m * vt / (r * ln)
    checks = [
        _check("coax_faraday", "φ", "V/m^2", (curlE_phi, float(curlE @ phat)),
               (mdBdt_phi, float(-dBdt @ phat)), scale_faraday, nonsmooth),
        _check("coax_ampere_maxwell", "r", "A/m^2", (curlH_r, float(curlH @ rhat)),
               (dDdt_r, float(dDdt @ rhat)), scale_ampere, nonsmooth),
        # Components that vanish identically in the TEM field (reported, not assumed).
        _check("coax_faraday", "z", "V/m^2", (0.0, float(curlE @ zhat)),
               (0.0, float(-dBdt @ zhat)), scale_faraday, nonsmooth),
        _check("coax_ampere_maxwell", "z", "A/m^2", (0.0, float(curlH @ zhat)),
               (0.0, float(dDdt @ zhat)), scale_ampere, nonsmooth),
    ]
    lp, cp = p.L_per_m_H, p.C_per_m_F
    vt_scale = vt / p.vp_m_per_s

    def ls(name: str, dz: float = 0.0, dt: float = 0.0) -> float:
        return float(line_state(spec, p, z + dz, t + dt)[name])

    # Central differences of V(z, t) and I(z, t) themselves (z ± h may leave [0, L]: the
    # closed-form waves are defined there, so the difference is still the line's derivative).
    vz_n = (ls("V", dz=hz) - ls("V", dz=-hz)) / (2 * hz)
    iz_n = (ls("I", dz=hz) - ls("I", dz=-hz)) / (2 * hz)
    vt_n = (ls("V", dt=ht) - ls("V", dt=-ht)) / (2 * ht)
    it_n = (ls("I", dt=ht) - ls("I", dt=-ht)) / (2 * ht)
    tele = [
        _check("telegrapher_v", "", "V/m", (float(s["dV_dz"]), vz_n),
               (-lp * float(s["dI_dt"]), -lp * it_n), vt_scale, nonsmooth),
        _check("telegrapher_i", "", "A/m", (float(s["dI_dz"]), iz_n),
               (-cp * float(s["dV_dt"]), -cp * vt_n), vt_scale / p.Z0_ohm, nonsmooth),
    ]
    f = radial_fields(p, r, s["V"], s["I"])
    return Calculus(point_m=point, r_m=r, div_D=div_D, div_B=div_B,
                    div_scale=abs(float(f["D_r"])) / r, div_B_scale=abs(float(f["B_phi"])) / r,
                    checks=checks, telegrapher=tele)


def probe(spec: CoaxSpec, p: LineParameters, x: float, y: float, z: float, t: float) -> Probe:
    g = spec.geometry
    r = math.hypot(x, y)
    reg = region(g, r)
    s = line_state(spec, p, z, t)
    V, I = float(s["V"]), float(s["I"])  # noqa: E741
    cphi, sphi = (x / r, y / r) if r > 0 else (1.0, 0.0)
    sc: float | None = None
    sk: float | None = None
    if reg in ("dielectric", "inner_surface", "shield_surface"):
        f = radial_fields(p, r, V, I)
        er, dr, hp, bp = (float(f[k]) for k in ("E_r", "D_r", "H_phi", "B_phi"))
        if reg == "inner_surface":
            sc, sk = dr, hp
        elif reg == "shield_surface":
            sc, sk = -dr, -hp
    else:
        er = dr = hp = bp = 0.0

    def rv(v: float) -> tuple[float, float, float]:
        return (v * cphi, v * sphi, 0.0)

    def pv(v: float) -> tuple[float, float, float]:
        return (-v * sphi, v * cphi, 0.0)

    return Probe(point_m=(x, y, z), r_m=r, phi_rad=math.atan2(y, x), region=reg,
                 E=rv(er), D=rv(dr), H=pv(hp), B=pv(bp), S=(0.0, 0.0, er * hp),
                 E_r=er, H_phi=hp, S_z=er * hp, w_e_J_per_m3=0.5 * er * dr,
                 w_m_J_per_m3=0.5 * hp * bp, surface_charge_C_per_m2=sc,
                 surface_current_A_per_m=sk)


def _range_scale(spec: CoaxSpec, p: LineParameters, rng: TimeRange) -> tuple[float, float]:
    """max |V| and max |I| over a (z, t) grid of the playback range (arrow length scale)."""
    zs = np.linspace(0.0, spec.geometry.length_m, 97)
    # Make sure the grid resolves the signal: at least ~8 samples per period / σ.
    span = rng.end_s - rng.start_s
    n_t = int(min(4001, max(257, 8 * span / time_scale(spec.excitation))))
    ts = np.linspace(rng.start_s, rng.end_s, n_t)
    s = line_state(spec, p, zs[:, None], ts[None, :])
    return float(np.max(np.abs(s["V"]))), float(np.max(np.abs(s["I"])))


def snapshot(req: CoaxSnapshotRequest) -> CoaxSnapshot:
    spec = req.spec
    g = spec.geometry
    p = parameters(spec)
    t, z = req.t_s, req.z_m
    s = line_state(spec, p, z, t)
    V, I = float(s["V"]), float(s["I"])  # noqa: E741
    zl = np.linspace(0.0, g.length_m, LINE_POINTS)
    sl = line_state(spec, p, zl, t)
    zst = np.linspace(0.0, g.length_m, req.stations)
    sst = line_state(spec, p, zst, t)
    a, b = g.inner_radius_m, g.shield_inner_radius_m
    rm = math.sqrt(a * b)
    fst = radial_fields(p, rm, sst["V"], sst["I"])
    rings, seg = sample_rings(g)
    frg = radial_fields(p, np.array(rings)[None, :], sst["V"][:, None], sst["I"][:, None])
    sv, si = _range_scale(spec, p, req.range)
    sv, si = max(sv, abs(V)), max(si, abs(I))
    pw = poynting_power(p, g, V, I)
    vi = V * I
    err = abs(pw - vi)
    ref = max(abs(pw), abs(vi))
    calc_point = (rm, 0.0, z)
    pr = None
    if req.probe_m is not None:
        px, py = req.probe_m
        pr = probe(spec, p, px, py, z, t)
        if pr.region == "dielectric":
            calc_point = (px, py, z)
    return CoaxSnapshot(
        params=p, t_s=t, z_m=z, V=V, I=I, Vf=float(s["Vf"]), Vb=float(s["Vb"]),
        If=float(s["If"]), Ib=float(s["Ib"]), scale_V=sv, scale_I=si,
        warnings=warnings(spec, p),
        line=LineProfile(z_m=zl.tolist(), V=sl["V"].tolist(), I=sl["I"].tolist(),
                         Vf=sl["Vf"].tolist(), Vb=sl["Vb"].tolist(),
                         P_W=(sl["V"] * sl["I"]).tolist()),
        cross_section=_cross_section(p, g, V, I),
        stations=Stations(z_m=zst.tolist(), V=sst["V"].tolist(), I=sst["I"].tolist(),
                          r_m=rm, E_r=fst["E_r"].tolist(), H_phi=fst["H_phi"].tolist(),
                          S_z=fst["S_z"].tolist(), rings_m=rings, segment_m=seg,
                          E_r_rings=frg["E_r"].tolist(), H_phi_rings=frg["H_phi"].tolist(),
                          S_z_rings=frg["S_z"].tolist()),
        power=Power(P_poynting_W=pw, P_VI_W=vi, abs_error_W=err,
                    rel_error=err / ref if ref > 1e-300 else None, nodes=(48, 64)),
        calculus=calculus(spec, p, calc_point, t),
        boundary=Boundary(rho_s_inner_C_per_m2=p.C_per_m_F * V / (2 * math.pi * a),
                          rho_s_shield_C_per_m2=-p.C_per_m_F * V / (2 * math.pi * b),
                          K_z_inner_A_per_m=I / (2 * math.pi * a),
                          K_z_shield_A_per_m=-I / (2 * math.pi * b),
                          Q_per_m_C=p.C_per_m_F * V, I_A=I),
        probe=pr)


def trace(req: CoaxTraceRequest) -> CoaxTrace:
    spec = req.spec
    p = parameters(spec)
    ts = np.linspace(req.range.start_s, req.range.end_s, req.count)
    s = line_state(spec, p, req.z_m, ts)
    s0 = line_state(spec, p, 0.0, ts)
    sl = line_state(spec, p, spec.geometry.length_m, ts)
    return CoaxTrace(params=p, z_m=req.z_m, t_s=ts.tolist(), V=s["V"].tolist(),
                     I=s["I"].tolist(), P_W=(s["V"] * s["I"]).tolist(),
                     V_source=s0["V"].tolist(), V_load=sl["V"].tolist(),
                     I_load=sl["I"].tolist())


SOLVER_ID = "coax_tem_analytical"


def model_context(spec: CoaxSpec) -> ModelContext:
    """Model context of the standalone coaxial TEM model (for equation statuses)."""
    from .equations.coax import CHECKED, EVALUATED

    m = spec.material
    vacuum = m.relative_permittivity == 1.0 and m.relative_permeability == 1.0
    return ModelContext(
        regime="full_wave", dimensionality="3d",
        medium="vacuum" if vacuum else "homogeneous_linear", has_free_charge=True,
        has_free_current=True, has_conductors=True, time_varying=True,
        computes_magnetic_field=True, source_count=1, coax=True, solver_id=SOLVER_ID,
        evaluated_equation_ids=EVALUATED, checked_equation_ids=CHECKED)
