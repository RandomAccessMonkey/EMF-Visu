"""Coaxial-cable TEM model: validation, analytical fields, line parameters, wave signs,
reflections, excitation signals, Poynting power and interface behaviour. Reference values are
closed-form expressions evaluated independently in the tests."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core import coax
from emf_core.presets import PRESETS
from emf_core.units import EPS0, MU0

A, B, C, LEN = 0.5e-3, 1.67e-3, 2.0e-3, 2.0
EPS_R, MU_R = 2.1, 1.0


def spec(load: str = "matched", source: str = "matched", exc: dict | None = None,
         **geo: float) -> coax.CoaxSpec:
    g = {"inner_radius_m": A, "shield_inner_radius_m": B, "shield_outer_radius_m": C,
         "length_m": LEN, **geo}
    return coax.CoaxSpec.model_validate({
        "geometry": g, "material": {"relative_permittivity": EPS_R,
                                    "relative_permeability": MU_R},
        "excitation": exc or {"type": "gaussian", "amplitude_V": 1.0, "center_s": 2e-9,
                              "width_s": 0.5e-9},
        "load": load, "source": source})


def gauss(t: float, amp: float = 1.0, t0: float = 2e-9, s: float = 0.5e-9) -> float:
    return amp * math.exp(-0.5 * ((t - t0) / s) ** 2)


# ------------------------------------------------------------------ geometry and validation


@pytest.mark.parametrize("geo", [
    {"inner_radius_m": 2e-3},  # a > b
    {"inner_radius_m": B},  # a = b
    {"shield_outer_radius_m": B},  # b = c
    {"shield_outer_radius_m": 1e-3},  # c < b
    {"inner_radius_m": 0.0},
    {"inner_radius_m": -1e-3},
    {"length_m": 0.0},
    {"length_m": -1.0},
    {"length_m": float("inf")},
    {"inner_radius_m": float("nan")},
])
def test_invalid_geometry_is_rejected(geo):
    with pytest.raises(ValidationError):
        spec(**geo)


@pytest.mark.parametrize("mat", [{"relative_permittivity": 0.0}, {"relative_permittivity": -2},
                                 {"relative_permeability": 0.0}, {"relative_permittivity": "nan"}])
def test_invalid_material_is_rejected(mat):
    m = {"relative_permittivity": EPS_R, "relative_permeability": MU_R, **mat}
    with pytest.raises(ValidationError):
        coax.CoaxMaterial.model_validate(m)


@pytest.mark.parametrize("exc", [
    {"type": "sinusoidal", "amplitude_V": 1.0, "frequency_Hz": 0.0},
    {"type": "sinusoidal", "amplitude_V": 1.0, "frequency_Hz": -1e6},
    {"type": "gaussian", "amplitude_V": 1.0, "center_s": 1e-9, "width_s": 0.0},
    {"type": "gaussian", "amplitude_V": 1.0, "center_s": 1e-9, "width_s": -1e-9},
    {"type": "gaussian", "amplitude_V": float("inf"), "center_s": 1e-9, "width_s": 1e-9},
    {"type": "square", "amplitude_V": 1.0},
])
def test_invalid_excitation_is_rejected(exc):
    with pytest.raises(ValidationError):
        spec(exc=exc)


def test_invalid_requests_are_rejected():
    s = spec()
    with pytest.raises(ValidationError):  # z outside the cable
        coax.CoaxSnapshotRequest(spec=s, t_s=0.0, z_m=LEN * 1.01,
                                 range=coax.TimeRange(start_s=0, end_s=1e-9))
    with pytest.raises(ValidationError):  # empty time range
        coax.TimeRange(start_s=1e-9, end_s=1e-9)
    with pytest.raises(ValidationError):
        coax.CoaxSpec.model_validate({**s.model_dump(), "load": "resistive"})


def test_too_many_round_trips_are_refused():
    s = spec(load="short", source="short")
    p = coax.parameters(s)
    with pytest.raises(coax.CoaxError):
        coax.line_state(s, p, 0.0, 1.0)  # 1 s ≈ 5e7 round trips


# ----------------------------------------------------------------------- line parameters


def test_line_parameters_match_closed_form():
    p = coax.parameters(spec())
    eps, mu = float(EPS0) * EPS_R, float(MU0) * MU_R
    ln = math.log(B / A)
    assert p.L_per_m_H == pytest.approx(mu / (2 * math.pi) * ln, rel=1e-14)
    assert p.C_per_m_F == pytest.approx(2 * math.pi * eps / ln, rel=1e-14)
    assert p.Z0_ohm == pytest.approx(math.sqrt(mu / eps) * ln / (2 * math.pi), rel=1e-13)
    assert p.vp_m_per_s == pytest.approx(1 / math.sqrt(mu * eps), rel=1e-13)
    assert p.delay_s == pytest.approx(LEN * math.sqrt(mu * eps), rel=1e-13)
    # Preset-A reference: the classic 50 Ω PTFE cable.
    assert p.Z0_ohm == pytest.approx(49.897, abs=1e-3)
    assert p.vp_over_c == pytest.approx(1 / math.sqrt(2.1), rel=1e-6)
    assert p.delay_s == pytest.approx(9.6676e-9, rel=1e-4)
    # L'C' = με for every TEM line.
    assert p.L_per_m_H * p.C_per_m_F == pytest.approx(mu * eps, rel=1e-13)


def test_parameters_follow_geometry_and_material():
    base = coax.parameters(spec())
    wide = coax.parameters(spec(shield_inner_radius_m=1.9e-3))
    assert wide.Z0_ohm > base.Z0_ohm and wide.C_per_m_F < base.C_per_m_F
    assert wide.vp_m_per_s == pytest.approx(base.vp_m_per_s, rel=1e-13)  # independent of radii
    s = spec()
    s.material.relative_permittivity = 4.0
    q = coax.parameters(s)
    assert q.vp_m_per_s == pytest.approx(base.vp_m_per_s * math.sqrt(2.1 / 4.0), rel=1e-13)
    # c does not enter any TEM parameter.
    assert coax.parameters(spec(shield_outer_radius_m=5e-3)) == base


def test_reflection_coefficients():
    z0 = 50.0
    assert coax.reflection_coefficient(50.0, z0) == 0.0
    assert coax.reflection_coefficient(math.inf, z0) == 1.0
    assert coax.reflection_coefficient(0.0, z0) == -1.0
    assert coax.reflection_coefficient(150.0, z0) == pytest.approx(0.5)
    assert [coax.parameters(spec(load=k)).gamma_load for k in ("matched", "open", "short")] == \
        [0.0, 1.0, -1.0]
    assert [coax.parameters(spec(source=k)).gamma_source for k in ("matched", "open", "short")] \
        == [0.0, 1.0, -1.0]


# --------------------------------------------------------------------------- excitation


def test_sinusoid_is_switched_on_at_zero():
    exc = coax.SinusoidalExcitation(amplitude_V=2.0, frequency_Hz=1e8)
    t = np.array([-1e-9, 0.0, 2.5e-9, 1.25e-9, 3.3e-9])
    f, df = coax.signal(exc, t)
    w = 2 * math.pi * 1e8
    assert f[0] == 0.0 and df[0] == 0.0
    np.testing.assert_allclose(f[1:], 2.0 * np.sin(w * t[1:]), atol=1e-15)
    np.testing.assert_allclose(df[1:], 2.0 * w * np.cos(w * t[1:]), rtol=1e-12)
    assert f[2] == pytest.approx(2.0)  # quarter period → peak


def test_gaussian_signal_and_width_convention():
    exc = coax.GaussianExcitation(amplitude_V=1.5, center_s=2e-9, width_s=0.5e-9)
    f, df = coax.signal(exc, np.array([2e-9, 2.5e-9, 1.0e-9]))
    assert f[0] == pytest.approx(1.5)
    # σ is the standard deviation: one σ from the centre the value is A·e^(−1/2).
    assert f[1] == pytest.approx(1.5 * math.exp(-0.5), rel=1e-13)
    assert df[0] == 0.0
    # u = (t − t0)/σ = −2: df/dt = −u/σ · f = 4e9 s⁻¹ · 1.5 e^(−2).
    assert df[2] == pytest.approx(1.5 * 4e9 * math.exp(-2), rel=1e-12)


# ---------------------------------------------------------------- waves and wave signs


def test_forward_wave_only_with_matched_load():
    s = spec()
    p = coax.parameters(s)
    z, t = 1.2, 8e-9
    st = coax.line_state(s, p, z, t)
    expect = gauss(t - z / p.vp_m_per_s)
    assert float(st["V"]) == pytest.approx(expect, rel=1e-13)
    assert float(st["Vb"]) == 0.0
    # Forward wave: I = V/Z0 (same sign as V, power toward +z).
    assert float(st["I"]) == pytest.approx(expect / p.Z0_ohm, rel=1e-13)


@pytest.mark.parametrize("load,gamma", [("open", 1.0), ("short", -1.0)])
def test_backward_wave_signs(load, gamma):
    s = spec(load=load)
    p = coax.parameters(s)
    T = p.delay_s
    z = 0.5
    # After the reflection the pulse travels back: centre at z when t = 2 ns + (2L − z)/vp.
    t = 2e-9 + (2 * LEN - z) / p.vp_m_per_s
    st = coax.line_state(s, p, z, t)
    assert float(st["Vf"]) == pytest.approx(gauss(t - z / p.vp_m_per_s), abs=1e-15)
    assert float(st["Vf"]) < 1e-30  # the incident pulse has long passed
    assert float(st["Vb"]) == pytest.approx(gamma * 1.0, rel=1e-12)
    # Backward wave: I = −V⁻/Z0, i.e. current opposite to the voltage sign times Γ.
    assert float(st["I"]) == pytest.approx(-gamma / p.Z0_ohm, rel=1e-12)
    assert float(st["Ib"]) == pytest.approx(-gamma / p.Z0_ohm, rel=1e-12)
    # S = E × H points along −z for every backward wave (V·I < 0), whatever Γ is.
    assert float(st["V"] * st["I"]) < 0
    assert T > 0


def test_load_boundary_conditions():
    t = np.linspace(0, 25e-9, 501)
    for load in ("open", "short", "matched"):
        s = spec(load=load)
        p = coax.parameters(s)
        st = coax.line_state(s, p, LEN, t)
        peak = coax.line_state(s, p, LEN, 2e-9 + p.delay_s)  # pulse centre at the load
        if load == "open":
            np.testing.assert_allclose(st["I"], 0.0, atol=1e-18)
            assert float(peak["V"]) == pytest.approx(2.0, rel=1e-12)  # doubling at the open end
        elif load == "short":
            np.testing.assert_allclose(st["V"], 0.0, atol=1e-15)
            assert float(peak["I"]) * p.Z0_ohm == pytest.approx(2.0, rel=1e-12)
        else:
            np.testing.assert_allclose(st["V"], p.Z0_ohm * st["I"], rtol=1e-12, atol=1e-18)


def test_source_re_reflection():
    # Short at both ends: the pulse returns to z = 0 inverted and is inverted again, so after
    # one round trip the forward wave is the original pulse delayed by 2T.
    s = spec(load="short", source="short")
    p = coax.parameters(s)
    z = 0.3
    t = 2e-9 + 2 * p.delay_s + z / p.vp_m_per_s
    st = coax.line_state(s, p, z, t)
    assert float(st["Vf"]) == pytest.approx(1.0, rel=1e-12)  # (Γ_L Γ_S)^1 = +1
    # At z = 0 the source condition V_f − f = Γ_S V_b holds at every time.
    ts = np.linspace(0, 60e-9, 601)
    s0 = coax.line_state(s, p, 0.0, ts)
    f, _ = coax.signal(s.excitation, ts)
    np.testing.assert_allclose(s0["Vf"] - f, -s0["Vb"], atol=1e-14)
    # Matched source: no re-reflection.
    m = spec(load="short", source="matched")
    pm = coax.parameters(m)
    sm = coax.line_state(m, pm, z, t)
    assert abs(float(sm["Vf"])) < 1e-30


def test_telegrapher_equations_hold_analytically():
    for load, src in (("open", "short"), ("matched", "matched"), ("short", "open")):
        s = spec(load=load, source=src)
        p = coax.parameters(s)
        z = np.linspace(0, LEN, 41)[:, None]
        t = np.linspace(0, 40e-9, 81)[None, :]
        st = coax.line_state(s, p, z, t)
        sc = np.max(np.abs(st["dV_dt"])) / p.vp_m_per_s
        np.testing.assert_allclose(st["dV_dz"], -p.L_per_m_H * st["dI_dt"], atol=1e-12 * sc)
        np.testing.assert_allclose(st["dI_dz"], -p.C_per_m_F * st["dV_dt"],
                                   atol=1e-12 * sc / p.Z0_ohm)


def test_matched_sinusoid_steady_state_is_in_phase():
    s = spec(exc={"type": "sinusoidal", "amplitude_V": 1.0, "frequency_Hz": 1e8})
    p = coax.parameters(s)
    z = np.linspace(0, LEN, 21)
    t = 30e-9  # well after the front reached the load
    st = coax.line_state(s, p, z, t)
    w = 2 * math.pi * 1e8
    np.testing.assert_allclose(st["V"], np.sin(w * (t - z / p.vp_m_per_s)), atol=1e-14)
    np.testing.assert_allclose(st["I"] * p.Z0_ohm, st["V"], atol=1e-14)
    # Ahead of the front nothing has arrived yet.
    early = coax.line_state(s, p, 1.5, 0.5 * 1.5 / p.vp_m_per_s)
    assert float(early["V"]) == 0.0 and float(early["I"]) == 0.0


# ------------------------------------------------------------------ fields and regions


def test_fields_in_the_dielectric():
    s = spec(load="open")
    p = coax.parameters(s)
    z, t = 0.8, 6e-9
    st = coax.line_state(s, p, z, t)
    V, I = float(st["V"]), float(st["I"])  # noqa: E741
    eps, mu = float(EPS0) * EPS_R, float(MU0) * MU_R
    for r in (0.6e-3, 1.0e-3, 1.6e-3):
        ph = 0.7
        x, y = r * math.cos(ph), r * math.sin(ph)
        f = coax.cartesian_fields(s, p, np.array(x), np.array(y), np.array(z), np.array(t))
        er = V / (r * math.log(B / A))
        hp = I / (2 * math.pi * r)
        np.testing.assert_allclose(f["E"], [er * math.cos(ph), er * math.sin(ph), 0], rtol=1e-13)
        np.testing.assert_allclose(f["D"], eps * f["E"], rtol=1e-13)
        np.testing.assert_allclose(f["H"], [-hp * math.sin(ph), hp * math.cos(ph), 0],
                                   rtol=1e-13)
        np.testing.assert_allclose(f["B"], mu * f["H"], rtol=1e-13)
        # E radial, H azimuthal, both transverse; S = E × H axial.
        assert abs(float(np.dot(f["E"], [-math.sin(ph), math.cos(ph), 0]))) < 1e-14 * abs(er)
        assert abs(float(np.dot(f["H"], [math.cos(ph), math.sin(ph), 0]))) < 1e-14 * abs(hp)
        np.testing.assert_allclose(f["S"], np.cross(f["E"], f["H"]), rtol=1e-12, atol=1e-30)
    # The line integral of E from a to b is V.
    ln = math.log(B / A)
    rs = np.linspace(A, B, 20001)
    assert np.trapezoid(V / (rs * ln), rs) == pytest.approx(V, rel=1e-6)


def test_fields_vanish_outside_the_dielectric():
    s = spec(load="open")
    p = coax.parameters(s)
    for r in (0.0, 0.25e-3, 1.8e-3, 1.99e-3, 2.5e-3, 1.0):
        f = coax.cartesian_fields(s, p, np.array(r), np.array(0.0), np.array(0.5),
                                  np.array(4e-9))
        for k in ("E", "D", "H", "B", "S"):
            assert np.all(f[k] == 0.0), (r, k)


def test_regions_and_interfaces():
    g = spec().geometry
    assert coax.region(g, 0.2e-3) == "inner_conductor"
    assert coax.region(g, A) == "inner_surface"
    assert coax.region(g, 1e-3) == "dielectric"
    assert coax.region(g, B) == "shield_surface"
    assert coax.region(g, 1.8e-3) == "shield"
    assert coax.region(g, C) == "shield"
    assert coax.region(g, 3e-3) == "outside"


def test_interface_jumps_equal_surface_charge_and_current():
    s = spec(load="short")
    p = coax.parameters(s)
    z, t = 1.0, 6.8e-9
    st = coax.line_state(s, p, z, t)
    V, I = float(st["V"]), float(st["I"])  # noqa: E741
    pa = coax.probe(s, p, A, 0.0, z, t)
    pb = coax.probe(s, p, 0.0, B, z, t)
    inner = coax.probe(s, p, 0.4e-3, 0.0, z, t)
    # D_r jumps from 0 (conductor) to ρ_s at r = a; H_φ jumps from 0 to K_z.
    assert inner.D == (0.0, 0.0, 0.0) and inner.H == (0.0, 0.0, 0.0)
    assert pa.surface_charge_C_per_m2 == pytest.approx(p.C_per_m_F * V / (2 * math.pi * A),
                                                       rel=1e-12)
    assert pa.surface_current_A_per_m == pytest.approx(I / (2 * math.pi * A), rel=1e-12)
    assert pb.surface_charge_C_per_m2 == pytest.approx(-p.C_per_m_F * V / (2 * math.pi * B),
                                                       rel=1e-12)
    assert pb.surface_current_A_per_m == pytest.approx(-I / (2 * math.pi * B), rel=1e-12)
    # Charge per unit length is equal and opposite on the two conductors (net zero), and the
    # same for the currents: no field outside.
    assert 2 * math.pi * A * pa.surface_charge_C_per_m2 == pytest.approx(
        -2 * math.pi * B * pb.surface_charge_C_per_m2, rel=1e-12)
    assert 2 * math.pi * A * pa.surface_current_A_per_m == pytest.approx(
        -2 * math.pi * B * pb.surface_current_A_per_m, rel=1e-12)
    snap = coax.snapshot(coax.CoaxSnapshotRequest(spec=s, t_s=t, z_m=z,
                                                  range=coax.TimeRange(start_s=0, end_s=2e-8)))
    assert snap.boundary.Q_per_m_C == pytest.approx(p.C_per_m_F * V, rel=1e-12)
    assert snap.boundary.K_z_inner_A_per_m == pytest.approx(pa.surface_current_A_per_m)


# ---------------------------------------------------------------------- Poynting power


@pytest.mark.parametrize("load", ["matched", "open", "short"])
def test_poynting_integral_equals_vi(load):
    s = spec(load=load)
    p = coax.parameters(s)
    for t in (3e-9, 9e-9, 12e-9, 18e-9):
        for z in (0.1, 1.0, 1.9):
            st = coax.line_state(s, p, z, t)
            V, I = float(st["V"]), float(st["I"])  # noqa: E741
            pw = coax.poynting_power(p, s.geometry, V, I)
            assert pw == pytest.approx(V * I, rel=1e-10, abs=1e-30)


def test_poynting_direction_follows_the_waves():
    s = spec(load="open")
    p = coax.parameters(s)
    z = 1.0
    t_in = 2e-9 + z / p.vp_m_per_s  # incident pulse centred at z
    t_back = 2e-9 + (2 * LEN - z) / p.vp_m_per_s  # reflected pulse centred at z
    for t, sign in ((t_in, 1), (t_back, -1)):
        pr = coax.probe(s, p, 1e-3, 0.0, z, t)
        assert np.sign(pr.S[2]) == sign
        assert pr.S[0] == 0.0 and pr.S[1] == 0.0


def test_energy_densities_are_equal_in_a_single_wave():
    s = spec()
    p = coax.parameters(s)
    pr = coax.probe(s, p, 0.0, 1.2e-3, 1.0, 2e-9 + 1.0 / p.vp_m_per_s)
    assert pr.w_e_J_per_m3 == pytest.approx(pr.w_m_J_per_m3, rel=1e-12)
    # S = (w_e + w_m) vp for a single travelling wave.
    assert pr.S_z == pytest.approx((pr.w_e_J_per_m3 + pr.w_m_J_per_m3) * p.vp_m_per_s, rel=1e-12)


# -------------------------------------------------------------- differential-law checks


def test_divergence_and_curl_checks():
    s = spec(load="open")
    p = coax.parameters(s)
    snap = coax.snapshot(coax.CoaxSnapshotRequest(
        spec=s, t_s=5e-9, z_m=0.4, range=coax.TimeRange(start_s=0, end_s=25e-9),
        probe_m=(0.9e-3, 0.3e-3)))
    c = snap.calculus
    assert c.point_m == (0.9e-3, 0.3e-3, 0.4)
    assert abs(c.div_D) < 1e-6 * c.div_scale and abs(c.div_B) < 1e-6 * c.div_B_scale
    faraday = next(k for k in c.checks if k.id == "coax_faraday" and k.component == "φ")
    ampere = next(k for k in c.checks if k.id == "coax_ampere_maxwell" and k.component == "r")
    # Nonzero curls (a TEM wave is not curl-free), both laws hold.
    assert abs(faraday.lhs.analytic) > 0 and abs(ampere.lhs.analytic) > 0
    for k in (faraday, ampere, *c.telegrapher):
        assert k.status == "agree" and k.residual < 1e-12 and k.fd_rel_error < 1e-6
    for k in c.checks:
        assert k.fd_rel_error < 1e-5
    # The analytic curl matches the closed form ∂E_r/∂z = (∂V/∂z)/(r ln(b/a)).
    st = coax.line_state(s, p, 0.4, 5e-9)
    r = math.hypot(0.9e-3, 0.3e-3)
    assert faraday.lhs.analytic == pytest.approx(float(st["dV_dz"]) / (r * p.ln_b_over_a))


def test_switched_sinusoid_front_is_reported_as_nonsmooth():
    s = spec(exc={"type": "sinusoidal", "amplitude_V": 1.0, "frequency_Hz": 1e8})
    p = coax.parameters(s)
    z = 1.0
    c = coax.calculus(s, p, (1e-3, 0.0, z), z / p.vp_m_per_s)  # exactly on the wave front
    assert all(k.status == "nonsmooth" for k in c.checks)
    c2 = coax.calculus(s, p, (1e-3, 0.0, z), z / p.vp_m_per_s + 3e-9)
    assert all(k.status == "agree" for k in c2.checks)


def test_te11_warning():
    assert coax.warnings(spec(), coax.parameters(spec())) == []
    hf = spec(exc={"type": "sinusoidal", "amplitude_V": 1.0, "frequency_Hz": 7e10})
    assert coax.warnings(hf, coax.parameters(hf)) == ["above_te11_cutoff"]


# ---------------------------------------------------------------- snapshot and presets


def test_snapshot_and_trace_are_consistent():
    s = spec(load="open")
    rng = coax.TimeRange(start_s=0.0, end_s=25e-9)
    snap = coax.snapshot(coax.CoaxSnapshotRequest(spec=s, t_s=11e-9, z_m=LEN, range=rng))
    tr = coax.trace(coax.CoaxTraceRequest(spec=s, z_m=LEN, range=rng, count=251))
    k = tr.t_s.index(min(tr.t_s, key=lambda x: abs(x - 11e-9)))
    assert tr.V[k] == pytest.approx(snap.V, rel=1e-9)
    assert snap.line.V[-1] == pytest.approx(snap.V, rel=1e-12)
    assert snap.scale_V == pytest.approx(2.0, rel=1e-2)  # open-end doubling within the range
    # Open end: I = 0, so no power crosses z = L (both sides exactly zero).
    assert snap.power.P_VI_W == 0.0 and snap.power.P_poynting_W == 0.0
    mid = coax.snapshot(coax.CoaxSnapshotRequest(spec=s, t_s=11e-9, z_m=1.0, range=rng))
    assert mid.power.rel_error is not None and mid.power.rel_error < 1e-10
    cs = snap.cross_section
    assert len(cs.points_m) == len(cs.E) == len(cs.H) == len(cs.S_z)
    assert all(A < math.hypot(*q) < B for q in cs.points_m)
    assert cs.h_line_radii_m == sorted(cs.h_line_radii_m)
    assert cs.h_line_radii_m[0] > A and cs.h_line_radii_m[-1] < B


def test_coax_presets():
    by = {p.number: p for p in PRESETS}
    a, b = by[30], by[31]
    for p in (a, b):
        assert p.available and p.coax is not None and p.time is not None
        g = p.coax.geometry
        assert (g.inner_radius_m, g.shield_inner_radius_m, g.shield_outer_radius_m,
                g.length_m) == (0.5e-3, 1.67e-3, 2.0e-3, 2.0)
        assert p.coax.material.relative_permittivity == 2.1
        assert p.coax.material.relative_permeability == 1.0
    assert a.coax.load == "matched" and a.coax.excitation.type == "sinusoidal"
    assert a.coax.excitation.amplitude_V == 1.0 and a.coax.excitation.frequency_Hz == 100e6
    assert (a.time.start_s, a.time.end_s) == (0.0, 20e-9)
    assert b.coax.load == "open" and b.coax.excitation.type == "gaussian"
    assert (b.coax.excitation.center_s, b.coax.excitation.width_s) == (2e-9, 0.5e-9)
    assert (b.time.start_s, b.time.end_s) == (0.0, 25e-9)
    # Earlier preset numbers are unchanged.
    assert by[29].id == "coupled_passive_circuits" and by[26].id == "shorted_loop_induction"


# ------------------------------------------------------------------ display sampling


def test_sample_rings_keep_a_margin_and_carry_analytical_values():
    s = spec(load="open")
    p = coax.parameters(s)
    rings, seg = coax.sample_rings(s.geometry)
    m = coax.SAMPLE_MARGIN * (B - A)
    assert len(rings) == 4 and seg == pytest.approx((B - A - 2 * m) / 4)
    # An arrow centred on a ring and at most one segment long stays clear of both conductors.
    assert rings[0] - seg / 2 == pytest.approx(A + m)
    assert rings[-1] + seg / 2 == pytest.approx(B - m)
    snap = coax.snapshot(coax.CoaxSnapshotRequest(
        spec=s, t_s=13e-9, z_m=1.0, range=coax.TimeRange(start_s=0, end_s=25e-9), stations=9))
    st = snap.stations
    assert st.rings_m == rings and len(st.E_r_rings) == 9
    for j, z in enumerate(st.z_m):
        ls = coax.line_state(s, p, z, 13e-9)
        V, I = float(ls["V"]), float(ls["I"])  # noqa: E741
        for i, r in enumerate(rings):
            e_ref, h_ref = V / (r * math.log(B / A)), I / (2 * math.pi * r)
            assert st.E_r_rings[j][i] == pytest.approx(e_ref, rel=1e-12, abs=1e-30)
            assert st.H_phi_rings[j][i] == pytest.approx(h_ref, rel=1e-12, abs=1e-30)
            assert st.S_z_rings[j][i] == pytest.approx(
                st.E_r_rings[j][i] * st.H_phi_rings[j][i], rel=1e-12, abs=1e-40)
    cs = snap.cross_section
    assert cs.rings_m == rings and cs.n_angles == coax.SECTION_ANGLES
    assert len(cs.points_m) == len(rings) * cs.n_angles
    for i, (x, y) in enumerate(cs.points_m):
        r = math.hypot(x, y)
        assert r == pytest.approx(rings[i // cs.n_angles], rel=1e-12)
        ex, ey = cs.E[i]
        assert ex * y - ey * x == pytest.approx(0.0, abs=1e-9 * (abs(ex) + abs(ey) + 1e-30))
