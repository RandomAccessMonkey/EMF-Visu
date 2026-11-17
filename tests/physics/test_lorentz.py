"""Phase 4B: Lorentz force on a test charge and nonrelativistic test-particle trajectories."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core.lorentz import (
    FieldSample,
    LorentzRequest,
    ParticleRequest,
    boris,
    lorentz_probe,
    trajectory,
)
from emf_core.presets import PRESETS
from emf_core.scene.models import (
    CircularLoopSource,
    Domain,
    InfiniteWireSource,
    LinePrimitive,
    PointChargeSource,
    PointPrimitive,
    RingPrimitive,
    Role,
    Scene,
    SceneObject,
    Transform,
)

Q, M = 1.602176634e-19, 1.67262192369e-27
PRESET = {p.id: p for p in PRESETS}


def uniform(e=(0.0, 0.0, 0.0), b=(0.0, 0.0, 0.0)):
    e_, b_ = np.asarray(e, float), np.asarray(b, float)

    def f(x: np.ndarray, t: float) -> FieldSample:
        return FieldSample(e_.copy(), e_.copy(), np.zeros(3), b_.copy(), False, math.inf)
    return f


def wire_scene(current: float = 10.0, profile: dict | None = None) -> Scene:
    src = {"current_A": current, **({"profile": profile} if profile else {})}
    return Scene(objects=[SceneObject(id="w", name="w", role=Role.CURRENT_SOURCE,
                                      primitive=LinePrimitive(length_m=1.0),
                                      source=InfiniteWireSource.model_validate(src))],
                 domain=Domain(min_m=(-0.2,) * 3, max_m=(0.2,) * 3))


# ------------------------------------------------------------------------ Lorentz force


def test_lorentz_force_decomposition_and_magnetic_orthogonality():
    scene = wire_scene()
    req = LorentzRequest(charge_C=Q, velocity_m_per_s=(1e4, 2e3, -5e3), point_m=(0.05, 0, 0))
    r = lorentz_probe(scene, req)
    assert r.status == "complete" and r.E_V_per_m == [0.0, 0.0, 0.0]
    v, b = np.array(r.velocity_m_per_s), np.array(r.B_T)
    assert np.allclose(r.F_B_N, Q * np.cross(v, b), rtol=1e-15, atol=0)
    assert np.allclose(r.F_total_N, np.add(r.F_E_N, r.F_B_N))
    assert abs(r.power_B_W) <= r.power_B_bound_W  # (v × B)·v = 0 within rounding
    # Wire along +z, B along +y at +x (right-hand rule): v_x e_x × B_y e_y is along +z.
    assert b[1] > 0 and abs(b[0]) < 1e-20
    assert r.F_total_magnitude_N == pytest.approx(np.linalg.norm(r.F_total_N))


@pytest.mark.parametrize("q", [Q, -Q, 0.0])
def test_charge_sign_reverses_every_force_and_zero_charge_feels_none(q: float):
    scene = Scene(objects=[
        SceneObject(id="c", name="c", role=Role.CHARGE_SOURCE, primitive=PointPrimitive(),
                    source=PointChargeSource(charge_C=1e-9),
                    transform=Transform(position_m=(0.1, 0, 0))),
        *wire_scene().objects], domain=Domain(min_m=(-0.2,) * 3, max_m=(0.2,) * 3))
    r = lorentz_probe(scene, LorentzRequest(charge_C=q, velocity_m_per_s=(0, 3e4, 1e4),
                                            point_m=(0.03, 0.01, 0)))
    pos = lorentz_probe(scene, LorentzRequest(charge_C=Q, velocity_m_per_s=(0, 3e4, 1e4),
                                              point_m=(0.03, 0.01, 0)))
    s = q / Q
    for name in ("F_E_N", "F_B_N", "F_total_N"):
        assert np.allclose(getattr(r, name), s * np.asarray(getattr(pos, name)), rtol=1e-14,
                           atol=0)
    assert r.power_E_W == pytest.approx(s * pos.power_E_W, abs=1e-40)
    assert pos.power_E_W == pytest.approx(Q * np.dot(pos.E_V_per_m, pos.velocity_m_per_s))


def test_current_and_field_reversal_reverse_the_magnetic_force():
    a = lorentz_probe(wire_scene(10.0), LorentzRequest(charge_C=Q, velocity_m_per_s=(1e4, 0, 0),
                                                       point_m=(0.05, 0, 0)))
    b = lorentz_probe(wire_scene(-10.0), LorentzRequest(charge_C=Q, velocity_m_per_s=(1e4, 0, 0),
                                                        point_m=(0.05, 0, 0)))
    assert np.allclose(b.F_B_N, -np.asarray(a.F_B_N), rtol=1e-14, atol=0)


def test_force_at_a_filament_is_singular_and_unsupported_e_ind_is_partial():
    r = lorentz_probe(wire_scene(), LorentzRequest(charge_C=Q, velocity_m_per_s=(1, 0, 0),
                                                   point_m=(0, 0, 0.01)))
    assert r.status == "singular" and r.F_total_N is None
    varying = wire_scene(0.0, {"type": "sinusoidal", "peak_A": 2.0, "frequency_Hz": 1.0})
    p = lorentz_probe(varying, LorentzRequest(charge_C=Q, velocity_m_per_s=(1e3, 0, 0),
                                              point_m=(0.05, 0, 0), time_s=0.0))
    assert p.status == "partial" and p.F_B_N is not None
    assert p.F_E_N is None and p.F_total_N is None and not p.e_ind_supported


def test_induced_field_contributes_to_the_electric_force():
    loop = SceneObject(id="l", name="l", role=Role.CURRENT_SOURCE,
                       primitive=RingPrimitive(radius_m=0.05),
                       source=CircularLoopSource.model_validate({"current_A": 0.0, "profile": {
                           "type": "sinusoidal", "peak_A": 2.0, "frequency_Hz": 50.0}}))
    scene = Scene(objects=[loop], domain=Domain(min_m=(-0.1,) * 3, max_m=(0.1,) * 3))
    r = lorentz_probe(scene, LorentzRequest(charge_C=Q, velocity_m_per_s=(0, 0, 0),
                                            point_m=(0.03, 0, 0), time_s=0.0))
    assert r.status == "complete" and r.E_static_V_per_m == [0.0, 0.0, 0.0]
    # dI/dt > 0 at t = 0: E_ind circulates against the current (−e_phi = −y at +x).
    assert r.E_ind_V_per_m[1] < 0 and r.F_E_N[1] < 0 and r.F_B_N == [0.0, 0.0, 0.0]


# ---------------------------------------------------------------------------- trajectory


def test_uniform_b_perpendicular_velocity_gives_the_cyclotron_circle():
    b, v = 1e-3, 1e5
    wc = Q * b / M
    period = 2 * math.pi / wc
    out = boris(uniform(b=(0, 0, b)), Q, M, np.zeros(3), np.array([v, 0, 0]), 0, period, 0.01,
                100_000)
    x = np.array(out.x)
    rc = v / wc
    # Centre of the circle: for q > 0 and B along +z the gyration is clockwise, centre at −y.
    centre = np.array([0.0, -rc, 0.0])
    radii = np.linalg.norm(x - centre, axis=1)
    assert out.status == "completed"
    assert np.max(np.abs(radii - rc)) < 1e-4 * rc
    assert np.linalg.norm(x[-1]) < 2e-3 * rc  # back to the start after one period
    speeds = np.linalg.norm(out.v, axis=1)
    assert np.max(np.abs(speeds - v)) < 1e-9 * v  # magnetic-only: |v| conserved


def test_helix_has_constant_parallel_velocity_and_the_right_pitch():
    b = 1e-3
    wc = Q * b / M
    period = 2 * math.pi / wc
    out = boris(uniform(b=(0, 0, b)), Q, M, np.zeros(3), np.array([1e5, 0, 3e4]), 0,
                2 * period, 0.01, 100_000)
    vz = np.array(out.v)[:, 2]
    assert np.allclose(vz, 3e4, rtol=1e-12)
    assert out.x[-1][2] == pytest.approx(3e4 * 2 * period, rel=1e-9)


def test_uniform_electric_field_gives_constant_acceleration():
    e = 1e3
    out = boris(uniform(e=(e, 0, 0)), Q, M, np.zeros(3), np.zeros(3), 0, 1e-6, 0.02, 10_000)
    a = Q * e / M
    t = out.t[-1]
    assert out.x[-1][0] == pytest.approx(0.5 * a * t * t, rel=1e-12)
    assert out.v[-1][0] == pytest.approx(a * t, rel=1e-12)
    assert not out.magnetic_only


def test_zero_field_gives_a_straight_line():
    out = boris(uniform(), Q, M, np.array([1.0, 2, 3]), np.array([5.0, -1, 2]), 0, 2.0, 0.02,
                1000)
    assert np.allclose(out.x[-1], [11, 0, 7], rtol=1e-14)


def test_step_refinement_converges_to_the_exact_gyration_phase():
    b, v = 1e-3, 1e5
    wc = Q * b / M
    t1 = 0.75 * 2 * math.pi / wc
    exact = np.array([v / wc * math.sin(wc * t1), v / wc * (math.cos(wc * t1) - 1), 0])
    errs = []
    for eta in (0.02, 0.01, 0.005):  # below the default span/200 limit
        out = boris(uniform(b=(0, 0, b)), Q, M, np.zeros(3), np.array([v, 0, 0]), 0, t1, eta,
                    100_000)
        errs.append(np.linalg.norm(out.x[-1] - exact))
    assert errs[1] < errs[0] / 3 and errs[2] < errs[1] / 3  # second order


def test_particle_never_jumps_over_a_filament():
    scene = wire_scene()
    req = ParticleRequest(charge_C=0.0, mass_kg=M, position_m=(-0.05, 0, 0),
                          velocity_m_per_s=(1e3, 0, 0), start_s=0, end_s=1e-4, max_steps=5000)
    r = trajectory(scene, req)
    assert r.status in ("singular", "max_steps")
    assert all(s.position_m[0] < 0 for s in r.samples)  # never crossed the wire at x = 0


def test_time_dependent_fields_are_sampled_at_the_simulation_time():
    scene = wire_scene(0.0, {"type": "sinusoidal", "peak_A": 2.0, "frequency_Hz": 1.0})
    req = ParticleRequest(charge_C=Q, mass_kg=M, position_m=(0.05, 0, 0),
                          velocity_m_per_s=(0, 0, 1e3), start_s=0, end_s=1e-3)
    r = trajectory(scene, req)
    assert r.status == "unsupported"  # E_ind of a changing infinite wire is not available


def test_helmholtz_preset_trajectory_matches_the_ideal_helix():
    p = PRESET["charged_particle_magnetic"]
    tc = p.test_charge
    r = trajectory(p.scene, ParticleRequest(
        charge_C=tc.charge_C, mass_kg=tc.mass_kg, position_m=tc.position_m,
        velocity_m_per_s=tc.velocity_m_per_s, start_s=0.0, end_s=tc.trajectory.end_s))
    assert r.status == "completed" and r.magnetic_only
    assert abs(r.energy_relative_change) < 1e-12
    b = r.gyrofrequency_rad_per_s * M / Q
    assert b == pytest.approx(5.98e-4, rel=1e-2)
    assert r.gyroradius_m == pytest.approx(M * 1000 / (Q * b), rel=1e-12)
    xs = np.array([s.position_m for s in r.samples])
    # Gyration radius about the field: the transverse extent is ~ 2 r_c.
    assert np.ptp(xs[:, 0]) == pytest.approx(2 * r.gyroradius_m, rel=0.02)
    assert all(s.F_B_N is not None and abs(np.dot(s.F_B_N, s.velocity_m_per_s)) < 1e-25
               for s in r.samples[:50])
