"""Phase 4C: passive circuits with induced currents: resistance and inductance, the coupled RL
solver, moving and dynamically moving circuits, magnetic braking, the annular-band eddy-current
approximation, energy accounting and the field of the induced currents."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError
from scipy.linalg import expm

from emf_core import engine
from emf_core.circuits import (
    MATERIALS,
    CircuitRequest,
    EddyDisk,
    Electrical,
    PassiveCircuit,
    coaxial_mutual,
    compute,
    thin_loop_inductance,
)
from emf_core.presets import PRESETS
from emf_core.scene.models import (
    CircularLoopSource,
    Domain,
    RingPrimitive,
    Role,
    Scene,
    SceneObject,
    Transform,
)
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import magnetostatics as ms

PRESET = {p.id: p for p in PRESETS}
DOM = Domain(min_m=(-0.3,) * 3, max_m=(0.3,) * 3)


def src_loop(radius=0.05, z=0.0, current=0.0, profile=None, oid="src", x=0.0):
    s = {"current_A": current, **({"profile": profile} if profile else {})}
    return SceneObject(id=oid, name=oid, role=Role.CURRENT_SOURCE,
                       primitive=RingPrimitive(radius_m=radius),
                       source=CircularLoopSource.model_validate(s),
                       transform=Transform(position_m=(x, 0.0, z)))


def ramp(slope=50.0, t_end=0.1):
    return {"type": "ramp", "start_A": 0.0, "slope_A_per_s": slope, "t_start_s": 0.0,
            "t_end_s": t_end}


def loop_circuit(cid="P1", radius=0.04, z=0.04, L_user=None, i0=0.0, reversed_=False,
                 rot=(0.0, 0.0, 0.0), center=None, motion=None, **el):
    elec = {"material": "copper", "wire_radius_m": 0.001, **el}
    if L_user is not None:
        elec["self_inductance"] = {"mode": "user", "value_H": L_user}
    path = {"id": cid, "shape": {"type": "circle", "radius_m": radius},
            "center_m": center or (0.0, 0.0, z), "reversed": reversed_,
            "rotation_euler_xyz_rad": rot}
    if motion is not None:
        path["motion"] = motion
    return {"id": cid, "path": path, "electrical": elec, "initial_current_A": i0}


def solve(objs, circuits=(), disks=(), end=0.5, step=0.005, rtol=1e-8):
    req = CircuitRequest.model_validate({"circuits": list(circuits), "disks": list(disks),
                                         "start_s": 0.0, "end_s": end, "step_s": step,
                                         "rtol": rtol})
    return compute(Scene(objects=list(objs), domain=DOM), req)


# ---------------------------------------------------------------- resistance, inductance


def test_resistance_from_conductivity_and_resistivity():
    a, rw = 0.04, 0.001
    r = solve([src_loop()], [loop_circuit(radius=a)], end=0.01)
    expect = 2 * math.pi * a / (MATERIALS["copper"] * math.pi * rw * rw)
    assert r.elements[0].resistance_ohm == pytest.approx(expect, rel=1e-12)
    rho = 1 / 3.5e7
    r2 = solve([src_loop()], [loop_circuit(radius=a, material="custom", resistivity_ohm_m=rho)],
               end=0.01)
    assert r2.elements[0].resistance_ohm == pytest.approx(
        rho * 2 * math.pi * a / (math.pi * rw * rw), rel=1e-12)
    r3 = solve([src_loop()], [loop_circuit(radius=a, material="aluminium")], end=0.01)
    assert r3.elements[0].resistance_ohm == pytest.approx(r2.elements[0].resistance_ohm, rel=1e-12)
    # N turns in series: N times the length.
    c = loop_circuit(radius=a)
    c["path"]["turns"] = 3
    r4 = solve([src_loop()], [c], end=0.01)
    assert r4.elements[0].resistance_ohm == pytest.approx(3 * expect, rel=1e-12)
    assert r4.elements[0].self_inductance_H == pytest.approx(
        9 * thin_loop_inductance(a, rw), rel=1e-12)


def test_thin_loop_inductance_against_an_independent_reference():
    # The thin-loop external self-inductance equals the mutual inductance of two coaxial
    # filaments of radius a one wire radius apart (Maxwell's elliptic-integral formula, an
    # independent closed form); the difference is O((r_w/a)²). The flux through the disk inside
    # the wire (radius a − r_w) agrees to O(r_w/a).
    errs = []
    for ratio in (0.1, 0.01, 0.001):
        a = 0.05
        rw = ratio * a
        rel = abs(thin_loop_inductance(a, rw) / coaxial_mutual(a, a, rw) - 1)
        assert rel < 0.4 * ratio ** 2
        errs.append(rel)
        assert thin_loop_inductance(a, rw) == pytest.approx(coaxial_mutual(a, a - rw, 0.0),
                                                            rel=0.8 * ratio)
    assert errs[2] < errs[1] / 50 < errs[0] / 2500


def test_maxwell_mutual_inductance_against_surface_quadrature():
    from emf_core.ampere import AmperePath, _Geo
    from emf_core.circuits import _unit_flux_through
    from emf_core.scene.passive import PassiveFilament

    geo = _Geo(AmperePath.model_validate({"id": "a", "shape": {"type": "circle",
                                                                "radius_m": 0.04}}), 1e-12)
    for b, d in ((0.06, 0.03), (0.02, 0.0), (0.05, 0.1)):
        f = PassiveFilament(id="b", kind="circle", center_m=(0.0, 0.0, d), radius_m=b)
        if b < 0.04 and d == 0.0:
            continue  # pierces the disk
        assert _unit_flux_through(geo, f) == pytest.approx(coaxial_mutual(0.04, b, d), rel=1e-8)


@pytest.mark.parametrize("bad", [
    {"material": "custom", "conductivity_S_per_m": 1e7, "resistivity_ohm_m": 1e-7},
    {"material": "copper", "conductivity_S_per_m": 1e7},
    {"material": "custom"},
    {"wire_radius_m": 0.001, "cross_section_m2": 1e-6},
    {"conductivity_S_per_m": -1.0, "material": "custom"},
    {"self_inductance": {"mode": "user"}},
])
def test_invalid_conductor_inputs_are_rejected(bad):
    with pytest.raises(ValidationError):
        Electrical.model_validate(bad)


def test_unsupported_automatic_inductance_requires_user_input():
    rect = {"id": "R", "path": {"id": "R", "shape": {"type": "rectangle", "width_m": 0.05,
                                                     "height_m": 0.03}, "center_m": (0, 0, 0.04)},
            "electrical": {"material": "copper", "wire_radius_m": 0.001}}
    r = solve([src_loop(profile=ramp())], [rect], end=0.01)
    assert r.status == "invalid" and "circular loops only" in r.problems[0].en
    thick = loop_circuit(radius=0.004)  # r_w/a = 0.25
    assert solve([src_loop(profile=ramp())], [thick], end=0.01).status == "invalid"
    filament = loop_circuit(wire_radius_m=None, cross_section_m2=None, resistance_ohm=1e-3)
    r = solve([src_loop(profile=ramp())], [filament], end=0.01)
    assert r.status == "invalid" and "ideal filament" in r.problems[0].en


# -------------------------------------------------------------------- single fixed loop


def test_single_loop_rl_transient_and_decay_match_the_closed_form():
    lu = 1e-4  # user inductance, so τ = ℒ/R is visible on the output grid
    r = solve([src_loop(profile=ramp(50.0, 0.1))], [loop_circuit(L_user=lu)], end=0.4,
              step=0.002, rtol=1e-9)
    assert r.status == "solved"
    e = r.elements[0]
    s = r.series
    tau = lu / e.resistance_ohm
    dphi = 50.0 * coaxial_mutual(0.04, 0.05, 0.04)  # analytical dΦ/dt during the ramp
    t = np.array(s.t_s)
    i = np.array(s.current_A[0])
    during = t <= 0.1
    expect = -(dphi / e.resistance_ohm) * (1 - np.exp(-t[during] / tau))
    assert np.max(np.abs(i[during] - expect)) <= 1e-6 * np.max(np.abs(expect))
    after = t > 0.1
    i1 = -(dphi / e.resistance_ohm) * (1 - math.exp(-0.1 / tau))
    expect2 = i1 * np.exp(-(t[after] - 0.1) / tau)
    assert np.max(np.abs(i[after] - expect2)) <= 1e-6 * abs(i1)
    # Lenz: the induced current opposes the growing source flux (negative about +z).
    assert np.all(i[1:] < 0)
    # Flux linkage and EMF bookkeeping: λ = Φ_ext + ℒI, R I + dλ/dt = 0.
    lam = np.array(s.flux_linkage_Wb[0])
    dlam = np.gradient(lam, t)
    k = (t > 0.02) & (t < 0.09)
    assert np.allclose(dlam[k], -e.resistance_ohm * i[k], rtol=1e-3)


def test_no_flux_change_and_no_initial_current_give_no_current():
    r = solve([src_loop(current=5.0)], [loop_circuit()], end=0.05)
    assert r.status == "solved" and max(abs(x) for x in r.series.current_A[0]) == 0.0


def test_initial_current_decays_with_the_time_constant():
    lu = 1e-4
    r = solve([src_loop(current=0.0)], [loop_circuit(L_user=lu, i0=2.0)], end=0.2, step=0.002,
              rtol=1e-9)
    tau = r.elements[0].time_constant_s
    t = np.array(r.series.t_s)
    assert np.allclose(r.series.current_A[0], 2.0 * np.exp(-t / tau), rtol=1e-6, atol=1e-12)
    # All the initial magnetic energy ends as heat.
    s = r.series
    assert s.joule_heat_J[-1] == pytest.approx(s.magnetic_energy_J[0] - s.magnetic_energy_J[-1],
                                               rel=1e-6)


def test_source_reversal_and_orientation_reversal_flip_the_current():
    base = solve([src_loop(profile=ramp(50.0))], [loop_circuit()], end=0.05)
    neg = solve([src_loop(profile=ramp(-50.0))], [loop_circuit()], end=0.05)
    rev = solve([src_loop(profile=ramp(50.0))], [loop_circuit(reversed_=True)], end=0.05)
    k = 5
    assert neg.series.current_A[0][k] == pytest.approx(-base.series.current_A[0][k], rel=1e-9)
    # Reversed traversal: the current is counted the other way round (same physical current).
    assert rev.series.current_A[0][k] == pytest.approx(-base.series.current_A[0][k], rel=1e-9)


# ------------------------------------------------------------------- coupled passive loops


def _two_loops(rtol=1e-9, **kw):
    # User self-inductances close to the thin-loop values (≈ 0.19 and 0.31 µH): M/ℒ ≈ 6 %,
    # time constants ≈ 0.14 and 0.15 ms, resolved by a 20 µs output grid.
    return solve([src_loop(profile=ramp(50.0, 0.1))],
                 [loop_circuit("P1", 0.04, 0.03, L_user=2e-7), loop_circuit("P2", 0.06, -0.03,
                                                                              L_user=3e-7)],
                 end=0.002, step=2e-5, rtol=rtol, **kw)


def test_coupled_matrix_is_symmetric_positive_definite_and_closed_form():
    r = _two_loops()
    m = np.array(r.matrix.values_H)
    assert r.matrix.positive_definite and m[0, 1] == m[1, 0]
    assert m[0, 1] == pytest.approx(coaxial_mutual(0.04, 0.06, 0.06), rel=1e-12)
    assert r.matrix.method[0][1] == "closed_form"


def test_coupled_response_matches_the_matrix_exponential_and_differs_without_coupling():
    r = _two_loops()
    e = r.elements
    m = np.array(r.matrix.values_H)
    rr = np.diag([x.resistance_ohm for x in e])
    dphi = 50.0 * np.array([coaxial_mutual(0.04, 0.05, 0.03), coaxial_mutual(0.06, 0.05, 0.03)])
    a = -np.linalg.solve(m, rr)
    b = -np.linalg.solve(m, dphi)
    t = np.array(r.series.t_s)
    cur = np.array(r.series.current_A)
    for k in (3, 10, 40, 100):
        ref = np.linalg.solve(a, (expm(a * t[k]) - np.eye(2)) @ b)
        assert np.allclose(cur[:, k], ref, rtol=1e-6)
    # Ignoring the mutual inductance gives a detectably different transient.
    m0 = np.diag(np.diag(m))
    a0, b0 = -np.linalg.solve(m0, rr), -np.linalg.solve(m0, dphi)
    ref0 = np.linalg.solve(a0, (expm(a0 * t[3]) - np.eye(2)) @ b0)
    assert np.max(np.abs(ref0 - cur[:, 3])) > 0.01 * np.max(np.abs(cur[:, 3]))


def test_numerical_mutual_inductance_is_reciprocal_for_tilted_loops():
    r = solve([src_loop(profile=ramp())],
              [loop_circuit("P1", 0.04, 0.03, L_user=1e-4),
               loop_circuit("P2", 0.03, -0.03, L_user=1e-4, rot=(0.4, 0.2, 0.0),
                            center=(0.02, 0.01, -0.03))], end=0.01)
    assert r.status == "solved" and r.matrix.method[0][1] == "numerical"
    assert r.matrix.reciprocity_max_relative < 1e-7


def test_linked_or_touching_circuits_are_reported():
    linked = solve([src_loop(radius=0.2, profile=ramp())],
                   [loop_circuit("P1", 0.04, 0.0, L_user=1e-4),
                    loop_circuit("P2", 0.04, 0.0, L_user=1e-4, rot=(math.pi / 2, 0, 0),
                                 center=(0.04, 0.0, 0.0))], end=0.01)
    assert linked.status == "singular" and "linked" in linked.status_reason.en


def test_nonphysical_inductance_matrix_is_rejected():
    # Two nearly coincident coaxial loops with tiny user self-inductances: M > √(L1 L2).
    r = solve([src_loop(profile=ramp())],
              [loop_circuit("P1", 0.04, 0.03, L_user=1e-9),
               loop_circuit("P2", 0.04, 0.035, L_user=1e-9)], end=0.01)
    assert r.status == "nonphysical" and not r.matrix.positive_definite


# ------------------------------------------------------------------- moving circuits


def _rod(mode="dynamic", v0=0.5, x0=0.1, R=0.002, L=5e-6, z=0.02, motion=None, m=0.02,
         force=0.0, damping=0.0):
    rm = motion or {"type": "stationary"}
    c = {"id": "R1", "path": {"id": "R1", "center_m": (-0.15, 0.0, z),
                              "shape": {"type": "sliding_rod", "rail_separation_m": 0.1,
                                        "rail_length_m": 0.3, "rod_position_m": x0,
                                        "rod_motion": rm}},
         "electrical": {"resistance_ohm": R, "self_inductance": {"mode": "user", "value_H": L}}}
    if mode == "dynamic":
        c["mechanics"] = {"mode": "dynamic", "mass_kg": m, "initial_velocity_m_per_s": v0,
                          "external_force_N": force, "damping_N_s_per_m": damping}
    return c


BIG = 2000.0  # A in a large loop (radius 0.4 m) below the rails: a strong, smooth field


def _braking(**kw):
    return solve([src_loop(radius=0.4, z=0.0, current=kw.pop("I", BIG))], [_rod(**kw)],
                 end=kw.pop("end", 0.2) if "end" in kw else 0.2, step=0.002, rtol=1e-8)


def test_magnetic_braking_force_opposes_motion_and_kinetic_energy_falls():
    r = _braking()
    s = r.series
    assert r.status in ("solved", "stopped")
    v = np.array(s.rod_velocity_m_per_s)
    fx = np.array([f[0] for f in s.force_N[0]])
    assert np.all(fx[1:] * v[1:] < 0)  # braking: computed force opposes the motion
    assert np.all(np.diff(s.kinetic_energy_J) < 0)
    assert np.all(np.array(s.mechanical_power_W[0][1:]) < 0)
    # Lenz: the current makes a field against the growing flux of the circuit.
    d_phi = s.flux_external_Wb[0][-1] - s.flux_external_Wb[0][0]
    assert np.sign(s.current_A[0][-1]) == -np.sign(d_phi)
    # Energy: kinetic energy → Joule heat + magnetic energy (residual ≪ the heat).
    assert abs(s.energy_residual_J[-1]) < 1e-6 * s.joule_heat_J[-1]
    lost = s.kinetic_energy_J[0] - s.kinetic_energy_J[-1]
    assert lost == pytest.approx(s.joule_heat_J[-1] + s.magnetic_energy_J[-1], rel=1e-6)


def test_braking_sign_symmetries():
    a = _braking()
    rev_field = _braking(I=-BIG)
    rev_motion = _braking(v0=-0.5, x0=0.25)
    k = 20
    assert rev_field.series.current_A[0][k] == pytest.approx(-a.series.current_A[0][k], rel=1e-7)
    assert rev_field.series.force_N[0][k][0] == pytest.approx(a.series.force_N[0][k][0], rel=1e-7)
    assert rev_motion.series.force_N[0][k][0] > 0  # still opposes the (now negative) motion
    still = _braking(v0=0.0)
    assert max(abs(x) for x in still.series.current_A[0]) == 0.0


def test_resistance_and_inductance_shape_the_braking_current():
    a = _braking()
    hi_r = _braking(R=0.02)
    hi_l = _braking(L=5e-4)
    k = 50
    assert abs(hi_r.series.current_A[0][k]) < abs(a.series.current_A[0][k])
    # Early on, a larger inductance delays the current.
    assert abs(hi_l.series.current_A[0][2]) < abs(a.series.current_A[0][2])


def test_prescribed_motion_counts_the_motional_emf_once():
    r = solve([src_loop(radius=0.4, current=BIG)],
              [_rod(mode="prescribed", motion={"type": "constant_velocity",
                                               "velocity_m_per_s": (0.5, 0.0, 0.0)})],
              end=0.2, step=0.002, rtol=1e-9)
    s = r.series
    t = np.array(s.t_s)
    x = np.array([0.1 + 0.5 * tt for tt in t])
    assert s.rod_position_m is None  # prescribed: the motion is not changed
    lam = np.array(s.flux_linkage_Wb[0])
    i = np.array(s.current_A[0])
    dlam = np.gradient(lam, t)
    k = t > 0.02  # after the RL transient (τ = 2.5 ms), where central differences resolve λ
    # R I + dλ/dt = 0 with λ = Φ_ext + ℒI: the motional EMF enters exactly once (twice would
    # make dλ/dt = −2RI).
    assert np.allclose(dlam[k], -0.002 * i[k], rtol=1e-3)
    # The motional EMF is the Phase 4B line integral at the rod.
    assert np.all(np.diff(x) > 0) and s.emf_motional_V[0][10] != 0.0
    # Electrical power balance with the independently integrated force (F·u from ∮ I dl × B).
    assert max(abs(p) for p in s.power_residual_W if p is not None) < 1e-9 * max(
        s.joule_power_W[0])


def test_moving_loop_relative_to_another_uses_dL_dt():
    moving = loop_circuit("P2", 0.03, -0.03, L_user=1e-5, motion={
        "translation": {"type": "constant_velocity", "velocity_m_per_s": (0.0, 0.0, 0.2)}})
    r = solve([src_loop(radius=0.08, current=0.0)],
              [loop_circuit("P1", 0.04, 0.05, L_user=1e-5, i0=1.0), moving],
              end=0.02, step=2e-4, rtol=1e-9)
    assert r.status == "solved" and r.matrix.time_dependent
    s = r.series
    t = np.array(s.t_s)
    for i, e in enumerate(r.elements):
        lam = np.array(s.flux_linkage_Wb[i])
        dlam = np.gradient(lam, t)
        k = slice(5, -5)
        assert np.allclose(dlam[k], -e.resistance_ohm * np.array(s.current_A[i])[k],
                           rtol=2e-3, atol=1e-6 * np.max(np.abs(dlam)))


def test_dynamic_rod_preset_27():
    p = PRESET["magnetic_braking_rod"]
    req = CircuitRequest(circuits=p.circuits, start_s=0.0, end_s=p.time.end_s,
                         step_s=p.time.step_s)
    r = compute(p.scene, req)
    s = r.series
    assert r.status == "stopped" and "left the rails" in r.status_reason.en
    assert r.end_time_s == pytest.approx(0.4006, abs=1e-3)
    assert s.rod_velocity_m_per_s[-1] < s.rod_velocity_m_per_s[0]
    assert all(f[0] < 0 for f in s.force_N[0][1:])
    assert max(abs(x) for x in s.energy_residual_J) < 1e-6 * s.joule_heat_J[-1]
    # BLv with the local field as a comparison: the motional EMF has its order of magnitude.
    blv = 0.1 * 0.5 * 0.009
    assert 0.1 * blv < max(abs(x) for x in s.emf_motional_V[0]) < 10 * blv


# ---------------------------------------------------------------------------- eddy disk


def disk(bands=20, **kw):
    return {"id": "D1", "outer_radius_m": 0.1, "thickness_m": 0.005, "bands": bands, **kw}


SINE10 = {"type": "sinusoidal", "peak_A": 10.0, "frequency_Hz": 10.0}


def test_annular_band_resistance_and_current_density():
    r = solve([src_loop(0.07, 0.02, profile=SINE10)], disks=[disk(10)], end=0.05, step=0.001)
    e = r.elements[3]
    sigma = MATERIALS["copper"]
    assert e.radius_m == pytest.approx(0.035) and e.width_m == pytest.approx(0.01)
    assert e.resistance_ohm == pytest.approx(2 * math.pi * 0.035 / (sigma * 0.005 * 0.01))
    k = 10
    assert r.series.current_density_A_per_m2[3][k] == pytest.approx(
        r.series.current_A[3][k] / (0.005 * 0.01))
    assert r.matrix.positive_definite


def test_eddy_currents_oppose_the_change_and_converge_under_refinement():
    out = {}
    for n in (10, 20, 40):
        r = solve([src_loop(0.07, 0.02, profile=SINE10)], disks=[disk(n)], end=0.03, step=0.001)
        assert r.status == "solved"
        rad = [e.radius_m for e in r.elements]
        jj = [r.series.current_density_A_per_m2[i][10] for i in range(n)]
        out[n] = np.interp([0.03, 0.05, 0.07], rad, jj)
        # dI/dt > 0 near t = 0: the induced azimuthal current is negative (against the source).
        assert all(r.series.current_A[i][5] < 0 for i in range(n))
    assert np.max(np.abs(out[20] - out[10]) / np.abs(out[20])) < 0.02
    assert np.max(np.abs(out[40] - out[20]) / np.abs(out[40])) < 0.01
    assert np.max(np.abs(out[40] - out[20])) < np.max(np.abs(out[20] - out[10]))


def test_eddy_disk_validity_checks():
    off_axis = solve([src_loop(0.07, 0.02, profile=SINE10, x=0.01)], disks=[disk(10)], end=0.01)
    assert off_axis.status == "unsupported" and "axisymmetric" in off_axis.status_reason.en
    narrow = solve([src_loop(0.07, 0.02, profile=SINE10)], disks=[disk(60)], end=0.01)
    assert narrow.status == "invalid" and "narrower than half" in narrow.problems[0].en
    pierced = solve([src_loop(0.07, 0.0, profile=SINE10)], disks=[disk(10)], end=0.01)
    assert pierced.status == "singular"
    with pytest.raises(ValidationError):
        EddyDisk.model_validate({"id": "d", "outer_radius_m": 0.05, "inner_radius_m": 0.06})


# ---------------------------------------------------------------------------- energy


def test_energy_accounting_and_refinement():
    coarse = _two_loops(rtol=1e-5)
    fine = _two_loops(rtol=1e-9)
    for r in (coarse, fine):
        s = r.series
        e = r.elements
        t = np.array(s.t_s)
        cur = np.array(s.current_A)
        pr = np.array(s.joule_power_W)
        assert np.allclose(pr, np.array([[x.resistance_ohm] for x in e]) * cur ** 2)
        m = np.array(r.matrix.values_H)
        assert np.allclose(s.magnetic_energy_J, [0.5 * c @ m @ c for c in cur.T], rtol=1e-12)
        q_trap = np.concatenate([[0], np.cumsum(0.5 * (pr.sum(0)[1:] + pr.sum(0)[:-1])
                                                 * np.diff(t))])
        assert np.allclose(s.joule_heat_J, q_trap, rtol=2e-3, atol=1e-3 * q_trap[-1])
    res_c = max(abs(x) for x in coarse.series.energy_residual_J)
    res_f = max(abs(x) for x in fine.series.energy_residual_J)
    assert res_f < res_c and res_f < 1e-9 * fine.series.source_work_J[-1]


def test_source_work_balances_heat_and_magnetic_energy():
    r = _two_loops()
    s = r.series
    assert s.source_work_J[-1] == pytest.approx(s.joule_heat_J[-1] + s.magnetic_energy_J[-1]
                                                - s.magnetic_energy_J[0], rel=1e-6)


# ------------------------------------------------------------- field of induced currents


def test_passive_field_is_added_to_the_total_field():
    r = solve([src_loop(profile=ramp())], [loop_circuit(L_user=1e-4)], end=0.05)
    k = 5
    fil = r.series.filaments[0][0].model_copy(update={
        "current_A": r.series.current_A[0][k], "rate_A_per_s": r.series.dI_dt_A_per_s[0][k]})
    pts = [[0.01, 0.0, 0.02], [0.0, 0.0, 0.04]]
    req = SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": pts}],
        "quantities": ["B", "B_prescribed", "B_passive", "dB_dt", "E_ind"],
        "time_s": r.series.t_s[k], "passive": [fil.model_dump()]})
    res = engine.run(Scene(objects=[src_loop(profile=ramp())], domain=DOM), req)
    b, bp, bq = (res.arrays[f"p.{q}"] for q in ("B", "B_prescribed", "B_passive"))
    assert np.allclose(b, bp + bq, rtol=1e-14, atol=0)
    lp = ms._passive_loop(fil, fil.current_A)
    ref = ms.loops_field([lp], np.asarray(pts, float))[0]
    assert np.allclose(bq, ref, rtol=1e-12)
    # On the axis above the source the induced field opposes the source's growing field.
    assert bq[1, 2] * bp[1, 2] < 0
    # The filament itself is singular (no finite value is invented there).
    on = SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": [[0.04, 0.0, 0.04]]}],
        "quantities": ["B"], "passive": [fil.model_dump()]})
    assert not np.all(np.isfinite(engine.run(Scene(objects=[src_loop(profile=ramp())],
                                                   domain=DOM), on).arrays["p.B"]))


def test_polygon_vector_potential_curl_is_the_segment_field():
    from emf_core.segments import segment_field, segment_vector_potential

    verts = np.array([[0, 0, 0], [0.1, 0, 0], [0.1, 0.05, 0], [0, 0.07, 0.01]], float)
    p = np.array([[0.03, 0.02, 0.04], [-0.2, 0.0, 0.0001]])
    h = 1e-6
    for q in p:
        jac = np.array([(segment_vector_potential((q + h * e)[None], verts)
                         - segment_vector_potential((q - h * e)[None], verts))[0] / (2 * h)
                        for e in np.eye(3)])
        curl = np.array([jac[1, 2] - jac[2, 1], jac[2, 0] - jac[0, 2], jac[0, 1] - jac[1, 0]])
        assert np.allclose(curl, segment_field(q[None], verts)[0], rtol=1e-5, atol=1e-14)


def test_circuit_request_validation():
    with pytest.raises(ValidationError):
        CircuitRequest.model_validate({"circuits": [], "disks": []})
    with pytest.raises(ValidationError):
        PassiveCircuit.model_validate({"id": "c", "path": {"id": "c", "shape": {
            "type": "circle", "radius_m": 0.04}}, "mechanics": {"mode": "dynamic"}})
    with pytest.raises(ValidationError):
        CircuitRequest.model_validate({"circuits": [loop_circuit()], "start_s": 0, "end_s": 1,
                                       "step_s": 1e-5})
