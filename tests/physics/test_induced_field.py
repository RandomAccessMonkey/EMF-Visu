"""Phase 4A: Coulomb-gauge vector potential of circular loops, time-dependent B, dB/dt and the
induced electric field E_ind = -dA/dt.

Independent references: ``bs.loop_vector_potential_reference`` (direct numerical line integral
of A = mu0 I/(4 pi) ∮ dl'/|r - r'|, no elliptic integrals), the analytical axis limit
A_phi ≈ mu0 I a^2 rho / (4 (a^2 + z^2)^(3/2)), the dipole far field, and finite-difference
curls (with their own uncertainty estimates) of A and E_ind compared with the solver's B and
dB/dt, which use different formulas (Phase 3A loop field).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core import engine
from emf_core.postprocess.differential import estimate
from emf_core.scene.currents import CurrentSources, LoopSource, current_sources
from emf_core.scene.timedep import at_time, rates, time_state
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import magnetostatics as ms
from emf_core.units import MU0
from emf_core.verification import biot_savart as bs
from tests.conftest import loop, magnet, scene_of, solenoid, torus, wire

pytestmark = pytest.mark.filterwarnings("error::scipy.integrate.IntegrationWarning")


def a_local(rho, z, a=1.0, current=1.0):
    return float(ms.loop_vector_potential_local(np.array([rho]), np.array([z]), a, current)[0][0])


def with_profile(obj, profile, current0):
    obj["source"]["profile"] = profile
    obj["source"]["current_A"] = current0
    return obj


SINE = {"type": "sinusoidal", "dc_A": 0.0, "peak_A": 2.0, "frequency_Hz": 1.0, "phase_rad": 0.0}


def run(scene, points, t, quantities=("B", "dB_dt", "E_ind")):
    return engine.run(scene, SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": [list(map(float, p))
                                                                  for p in points]}],
        "quantities": list(quantities), "time_s": t}))


# ------------------------------------------------------------------------ vector potential


@pytest.mark.parametrize("rho", [0.01, 0.1, 0.3, 0.7, 0.95, 1.05, 1.5, 3.0, 10.0])
def test_loop_vector_potential_matches_independent_line_integral(rho):
    for z in (0.0, 1e-6, 0.05, 0.4, 2.0):
        ref = bs.loop_vector_potential_reference(rho - 1.0, rho, z, 1.0, 1.0)
        assert a_local(rho, z) == pytest.approx(ref, rel=1e-13), z


@pytest.mark.parametrize("k", range(1, 14))
def test_vector_potential_near_the_wire(k):
    d = 10.0 ** -k
    for th in np.linspace(0, 2 * math.pi, 8, endpoint=False) + 0.1:
        rho, z = 1.0 + d * math.cos(th), d * math.sin(th)
        ref = bs.loop_vector_potential_reference(rho - 1.0, rho, z, 1.0, 1.0)
        assert a_local(rho, z) == pytest.approx(ref, rel=1e-13)


def test_vector_potential_axis_limit_far_field_and_series_switch():
    assert a_local(0.0, 0.3) == 0.0  # A_phi vanishes on the axis
    for rho in (1e-12, 1e-8, 1e-4):
        for z in (0.0, 0.5):
            lim = MU0 * rho / (4 * (1 + z * z) ** 1.5)
            assert abs(a_local(rho, z) - lim) <= (0.5 * rho**2 + 1e-15) * lim
    r = math.hypot(50.0, 30.0)  # dipole: A = mu0 m x r / (4 pi r^3), m = I pi a^2
    assert a_local(50.0, 30.0, 0.4, 2.0) == pytest.approx(MU0 * 2.0 * 0.16 * 50.0 / (4 * r**3),
                                                            rel=2e-4)
    rho0 = 3 - 2 * math.sqrt(2)  # m = 0.5 on z = 0: series / closed-form switch
    lo, hi = a_local(rho0 * (1 - 1e-12), 0.0), a_local(rho0 * (1 + 1e-12), 0.0)
    assert abs(hi - lo) <= 1e-11 * abs(lo)


def test_vector_potential_linear_in_current_and_reversed():
    for rho, z in ((0.3, 0.1), (1.2, -0.4)):
        base = a_local(rho, z, 0.7, 1.0)
        assert a_local(rho, z, 0.7, -1.0) == -base
        assert a_local(rho, z, 0.7, 3.5) == pytest.approx(3.5 * base, rel=1e-15)
        assert base > 0  # along +phi, the positive current direction


def one_loop(c, n, a, current=1.0):
    n = np.asarray(n, float) / np.linalg.norm(n)
    u = np.cross(n, [1.0, 0, 0]) if abs(n[0]) < 0.9 else np.cross(n, [0, 1.0, 0])
    u /= np.linalg.norm(u)
    lp = LoopSource("l", current, np.asarray(c, float), n, a, u)
    return CurrentSources(wires=[], loops=[lp], problems=[]), lp


@pytest.mark.parametrize("c,n,a", [((0, 0, 0), (0, 0, 1), 0.05),
                                   ((0.3, -0.2, 0.7), (0.3, -0.6, 0.74), 0.08)])
def test_world_vector_potential_direction_and_transform(c, n, a):
    cs, lp = one_loop(c, n, a, 2.0)
    v = np.cross(lp.normal, lp.u)
    for rho, z, psi in ((0.3 * a, 0.2 * a, 0.0), (1.7 * a, -0.5 * a, 2.0), (a, 0.1 * a, 4.0)):
        radial = math.cos(psi) * lp.u + math.sin(psi) * v
        p = lp.center_m + rho * radial + z * lp.normal
        aw = ms.loops_vector_potential(cs.loops, p[None, :])[0][0]
        tangent = np.cross(lp.normal, radial)
        ref = bs.loop_vector_potential_reference(rho - a, rho, z, a, 2.0)
        assert np.allclose(aw, ref * tangent, rtol=1e-12, atol=1e-12 * abs(ref))


@pytest.mark.parametrize("objs", [[loop("l", 1.5, 0.3)],
                                  [loop("l", 1.5, 0.3, (0.1, -0.2, 0.05), (0.4, 0.3, 0))],
                                  [solenoid(turns=8, radius=0.04, length=0.1)]])
def test_curl_of_a_is_b(objs):
    cs = current_sources(scene_of(*objs))
    rng = np.random.default_rng(7)
    for p in rng.uniform(-0.25, 0.25, size=(6, 3)):
        d = ms.distance_to_sources(p[None, :], cs)[0]
        h = 1e-3 * min(d, 0.1)
        est = estimate(lambda q: ms.loops_vector_potential(cs.loops, q)[0], p, h)
        b = ms.evaluate(p[None, :], cs, 0.0)[0]
        assert np.all(np.abs(est.curl - b) <= est.curl_uncertainty + 1e-7 * np.linalg.norm(b))
        assert abs(est.div) <= est.div_uncertainty + 1e-7 * np.linalg.norm(b)  # Coulomb gauge


def test_vector_potential_singular_on_the_filament_finite_near_it():
    cs, _ = one_loop((0, 0, 0), (0, 0, 1), 0.2)
    a, sing, prec = ms.loops_vector_potential(cs.loops, np.array([[0.2, 0, 0],
                                                                   [0.2 + 1e-10, 0, 0]]))
    assert sing.tolist() == [True, False]
    assert np.all(np.isnan(a[0])) and np.all(np.isfinite(a[1])) and prec[1] > 0


# ----------------------------------------------------- time-dependent B, dB/dt and E_ind


def test_constant_scene_is_unchanged_by_time():
    s = scene_of(loop("l", 2.0, 0.3), wire("w", 1.0, (0.5, 0, 0)))
    pts = [(0.1, 0.2, 0.05), (0.7, -0.1, 0.2)]
    r0, r9 = run(s, pts, 0.0), run(s, pts, 9.0)
    assert np.array_equal(r0.arrays["p.B"], r9.arrays["p.B"])
    assert np.all(r0.arrays["p.dB_dt"] == 0.0) and np.all(r0.arrays["p.E_ind"] == 0.0)
    assert r0.header.induction is not None and not r0.header.induction.time_dependent
    assert r0.header.model_context.regime == "magnetostatic"


def test_b_and_db_dt_scale_with_the_profile():
    pts = [(0.02, 0.0, 0.01), (0.1, 0.05, -0.03)]
    unit = run(scene_of(loop("l", 1.0, 0.05)), pts, 0.0).arrays["p.B"]
    s = scene_of(with_profile(loop("l", 0.0, 0.05), {**SINE, "dc_A": 0.5}, 0.5))
    for t in (0.0, 0.1, 0.25, 0.6, 1.3):
        r = run(s, pts, t)
        i_t = 0.5 + 2.0 * math.sin(2 * math.pi * t)
        di = 4 * math.pi * math.cos(2 * math.pi * t)
        assert np.allclose(r.arrays["p.B"], i_t * unit, rtol=1e-12, atol=1e-20)
        assert np.allclose(r.arrays["p.dB_dt"], di * unit, rtol=1e-12, atol=1e-20)
        ts = {x.object_id: x for x in r.header.time_sources}["l"]
        assert ts.current_A == pytest.approx(i_t) and ts.dI_dt_A_per_s == pytest.approx(di)


def test_induced_field_is_minus_rate_times_unit_potential():
    pts = np.array([(0.02, 0.0, 0.01), (0.1, 0.05, -0.03), (-0.04, 0.03, 0.01)])
    cs = current_sources(scene_of(loop("l", 1.0, 0.05)))
    a_unit = ms.loops_vector_potential(cs.loops, pts)[0]
    s = scene_of(with_profile(loop("l", 0.0, 0.05), SINE, 0.0))
    for t, sign in ((0.0, 1), (0.25, 0), (0.5, -1), (0.1, 1), (0.8, 1)):
        di = 4 * math.pi * math.cos(2 * math.pi * t)
        e = run(s, pts, t).arrays["p.E_ind"]
        assert np.allclose(e, -di * a_unit, rtol=1e-12, atol=1e-18)
        if sign == 0:
            assert np.all(np.abs(e) <= 1e-12 * 4 * math.pi * np.abs(a_unit).max())


def test_lenz_direction_of_induced_field():
    """Current increasing counter-clockwise about +z: E_ind circulates clockwise (opposes the
    change), i.e. against the current direction at every point of the plane."""
    s = scene_of(with_profile(loop("l", 0.0, 0.05),
                              {"type": "ramp", "start_A": 0.0, "slope_A_per_s": 3.0,
                               "t_start_s": 0.0, "t_end_s": 2.0}, 0.0))
    th = np.linspace(0, 2 * np.pi, 9, endpoint=False)
    for r_ in (0.02, 0.08):
        pts = np.column_stack([r_ * np.cos(th), r_ * np.sin(th), np.zeros_like(th)])
        e = run(s, pts, 1.0).arrays["p.E_ind"]
        ccw = np.column_stack([-np.sin(th), np.cos(th), np.zeros_like(th)])
        assert np.all(np.einsum("ij,ij->i", e, ccw) < 0)


def test_curl_of_induced_field_is_minus_db_dt():
    s = scene_of(with_profile(loop("a", 0.0, 0.05, (0, 0, 0)), SINE, 0.0),
                 with_profile(solenoid("s", radius=0.03, length=0.06, turns=5, pos=(0.15, 0, 0),
                                       rot=(0.3, 0.2, 0.0)),
                              {"type": "ramp", "start_A": 1.0, "slope_A_per_s": -2.0,
                               "t_start_s": 0.0, "t_end_s": 3.0}, 1.0))
    cs0 = current_sources(s)
    ts = time_state(s, cs0, 0.3)
    cs_rate = rates(cs0, ts)
    rng = np.random.default_rng(3)
    for p in rng.uniform(-0.1, 0.25, size=(6, 3)):
        d = ms.distance_to_sources(p[None, :], cs0)[0]
        h = 1e-3 * min(d, 0.05)
        est = estimate(lambda q: -ms.loops_vector_potential(cs_rate.loops, q)[0], p, h)
        db = run(s, [p], 0.3).arrays["p.dB_dt"][0]
        assert np.all(np.abs(est.curl + db) <= est.curl_uncertainty + 1e-7 * np.linalg.norm(db))
    assert at_time(cs0, ts).loops[0].current_A == pytest.approx(2 * math.sin(0.6 * math.pi))


def test_superposition_of_two_time_dependent_sources():
    pts = [(0.05, 0.02, 0.03), (0.2, -0.1, 0.0)]
    a = with_profile(loop("a", 0.0, 0.05), SINE, 0.0)
    b = with_profile(loop("b", 1.0, 0.04, (0.1, 0, 0.05)),
                     {"type": "ramp", "start_A": 1.0, "slope_A_per_s": 4.0, "t_start_s": 0.0,
                      "t_end_s": 1.0}, 1.0)
    both = run(scene_of(a, b), pts, 0.4)
    one = run(scene_of(a), pts, 0.4)
    two = run(scene_of(b), pts, 0.4)
    for q in ("B", "dB_dt", "E_ind"):
        assert np.allclose(both.arrays[f"p.{q}"], one.arrays[f"p.{q}"] + two.arrays[f"p.{q}"],
                           rtol=1e-12, atol=1e-20)


def test_static_magnet_adds_b_but_no_db_dt_or_e_ind():
    pts = [(0.15, 0.0, 0.0), (0.0, 0.12, 0.05)]
    m = magnet(m=5e5, pos=(0.3, 0, 0))
    lp = with_profile(loop("l", 0.0, 0.05), SINE, 0.0)
    with_m, without = run(scene_of(lp, m), pts, 0.1), run(scene_of(lp), pts, 0.1)
    assert not np.allclose(with_m.arrays["p.B"], without.arrays["p.B"])
    assert np.array_equal(with_m.arrays["p.dB_dt"], without.arrays["p.dB_dt"])
    assert np.array_equal(with_m.arrays["p.E_ind"], without.arrays["p.E_ind"])
    only_m = run(scene_of(m), pts, 0.1)
    assert np.all(only_m.arrays["p.dB_dt"] == 0.0) and np.all(only_m.arrays["p.E_ind"] == 0.0)


def test_unsupported_time_varying_sources_give_no_partial_induced_field():
    pts = [(0.1, 0.1, 0.0)]
    w = with_profile(wire("w", 0.0, (0.5, 0, 0)), SINE, 0.0)
    r = run(scene_of(w, with_profile(loop("l", 0.0, 0.05), SINE, 0.0)), pts, 0.1)
    assert np.all(np.isnan(r.arrays["p.E_ind"]))
    assert r.header.induction.e_ind_available is False
    assert r.header.induction.unsupported_object_ids == ["w"]
    assert any("E_ind is not evaluated" in x.en for x in r.header.warnings)
    assert np.all(np.isfinite(r.arrays["p.B"])) and np.all(np.isfinite(r.arrays["p.dB_dt"]))
    # The same wire with a constant current does not prevent E_ind.
    ok = run(scene_of(wire("w", 3.0, (0.5, 0, 0)),
                      with_profile(loop("l", 0.0, 0.05), SINE, 0.0)), pts, 0.1)
    assert np.all(np.isfinite(ok.arrays["p.E_ind"]))
    ideal = with_profile(torus(model="toroid_ideal"), SINE, 0.0)
    assert run(scene_of(ideal), [(0.12, 0, 0)], 0.1).header.induction.e_ind_available is False


def test_toroid_turns_are_induction_sources():
    t = with_profile(torus(turns=12), SINE, 0.0)
    r = run(scene_of(t), [(0.12, 0.0, 0.0), (0.0, 0.0, 0.05)], 0.1)
    assert np.all(np.isfinite(r.arrays["p.E_ind"])) and r.header.induction.e_ind_available
    assert np.linalg.norm(r.arrays["p.dB_dt"][0]) > 0


def test_filament_points_singular_near_points_finite():
    s = scene_of(with_profile(loop("l", 0.0, 0.05), SINE, 0.0))
    r = run(s, [(0.05, 0.0, 0.0), (0.05 + 1e-9, 0.0, 0.0)], 0.1)
    for q in ("B", "dB_dt", "E_ind"):
        assert np.all(np.isnan(r.arrays[f"p.{q}"][0]))
        assert np.all(np.isfinite(r.arrays[f"p.{q}"][1]))


def test_corner_of_a_ramp_is_reported():
    s = scene_of(with_profile(loop("l", 0.0, 0.05),
                              {"type": "ramp", "start_A": 0.0, "slope_A_per_s": 5.0,
                               "t_start_s": 0.0, "t_end_s": 1.0}, 0.0))
    r = run(s, [(0.01, 0.0, 0.02)], 0.0)
    ts = r.header.time_sources[0]
    assert (ts.dI_dt_left_A_per_s, ts.dI_dt_A_per_s, ts.derivative_unique) == (0.0, 5.0, False)
    assert r.header.induction.derivative_unique is False
    assert any("dI/dt jumps" in x.en for x in r.header.warnings)
    inside = run(s, [(0.01, 0.0, 0.02)], 0.5)
    assert inside.header.induction.derivative_unique
    assert not any("dI/dt jumps" in x.en for x in inside.header.warnings)


def test_quasistatic_validity_is_checked():
    fast = with_profile(loop("l", 0.0, 0.05), {**SINE, "frequency_Hz": 1e6}, 0.0)
    big = scene_of(fast, domain={"min_m": [-2e3] * 3, "max_m": [2e3] * 3})
    r = run(big, [(0.1, 0, 0)], 0.0)
    assert r.header.induction.quasistatic_ratio > 1e-2
    assert any("quasistatic approximation is doubtful" in x.en for x in r.header.warnings)
    assert run(scene_of(with_profile(loop("l", 0.0, 0.05), SINE, 0.0)), [(0.1, 0, 0)],
               0.0).header.induction.quasistatic_ratio < 1e-6
