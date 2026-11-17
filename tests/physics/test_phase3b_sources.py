"""Phase 3B physics validation: finite solenoids, finite-turn and ideal toroids, uniformly
magnetized cylinders. References are independent of the solver: closed-form axis fields, the
numerical Biot–Savart line integral per turn, and a direct surface integral of the magnet's
bound current (no circular-loop formula)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core import engine
from emf_core.postprocess.differential import estimate
from emf_core.scene.currents import current_sources, solenoid_turn_positions
from emf_core.scene.models import Scene
from emf_core.solvers import SolveRequest, UnsupportedSceneError
from emf_core.solvers.analytical import magnetostatics as ms
from emf_core.units import MU0
from emf_core.verification import biot_savart as bs
from tests.conftest import charge, loop, magnet, points_request, scene_of, solenoid, torus, wire

R_MIN = 1e-12


def bh(objs, pts, rtol=ms.MAGNET_RTOL["probe"]):
    cs = current_sources(scene_of(*objs))
    assert not cs.problems, [p.en for p in cs.problems]
    return ms.evaluate_bh(np.asarray(pts, float), cs, R_MIN, rtol)


def rot_for(d):
    d = np.asarray(d, float) / np.linalg.norm(d)
    return (math.atan2(-d[1], d[2]), math.asin(d[0]), 0.0)


# ------------------------------------------------------------------------------- solenoid


def test_single_turn_solenoid_is_exactly_a_single_loop():
    pts = np.array([[0.01, 0.02, 0.03], [0.2, -0.1, 0.05], [0, 0, 0.3]])
    b1 = bh([solenoid(turns=1, length=0.7, radius=0.05, current=3.0)], pts).b
    b2 = bh([loop("l", 3.0, 0.05)], pts).b
    assert np.array_equal(b1, b2)


def test_turn_positions_and_spacing():
    z = solenoid_turn_positions(20, 0.2)
    assert z[0] == -0.1 and z[-1] == pytest.approx(0.1, rel=1e-15)
    assert np.allclose(np.diff(z), 0.2 / 19, rtol=1e-14)
    assert solenoid_turn_positions(1, 0.5).tolist() == [0.0]
    cs = current_sources(scene_of(solenoid()))
    assert len(cs.loops) == 20 and all(lp.kind == "solenoid" for lp in cs.loops)
    table = ms.current_source_table(cs, [])
    assert table[0].turn_spacing_m == pytest.approx(0.2 / 19, rel=1e-14)
    assert table[0].ideal_long_solenoid.turns_per_m == pytest.approx(100.0)


@pytest.mark.parametrize("z", [0.0, 0.05, 0.1, 0.13, 0.4])
def test_axis_field_equals_sum_of_exact_loop_axis_fields(z):
    a, length, n, i = 0.04, 0.2, 20, 1.0
    b = bh([solenoid(current=i, radius=a, length=length, turns=n)], [[0, 0, z]]).b[0]
    ref = sum(bs.loop_axis_bz(i, a, z - zk) for zk in solenoid_turn_positions(n, length))
    assert b[2] == pytest.approx(ref, rel=1e-13) and b[0] == 0 and b[1] == 0


def test_off_axis_against_numerical_biot_savart_per_turn():
    a, length, n = 0.04, 0.2, 7
    scene = scene_of(solenoid(radius=a, length=length, turns=n, current=2.0, pos=(0.01, 0, 0),
                              rot=rot_for((0.3, -0.2, 1))))
    cs = current_sources(scene)
    p = np.array([0.03, 0.02, 0.05])
    ref = sum(bs.loop_converged(p, lp.center_m, lp.normal, lp.u, lp.radius_m, lp.current_A).value
              for lp in cs.loops)
    b = ms.evaluate(p[None, :], cs, R_MIN)[0]
    assert np.linalg.norm(b - ref) / np.linalg.norm(b) < 1e-10


def test_high_turn_solenoid_approaches_continuous_sheet_axis_formula():
    a, length, i = 0.04, 0.2, 1.0
    for n, tol in ((64, 2e-3), (256, 2e-4)):
        nI = n * i / length  # turns per metre of the continuous-sheet model, as N/L
        for z in (0.0, 0.05, 0.12, 0.3):
            b = bh([solenoid(current=i, radius=a, length=length, turns=n)], [[0, 0, z]]).b[0][2]
            # The discrete model spreads N turns over L (centres), the sheet over L(1 + 1/(N-1)):
            ref = bs.finite_sheet_axis_bz(nI * (n - 1) / n, a, length * n / (n - 1), z)
            assert b == pytest.approx(ref, rel=tol), (n, z)


def test_ideal_long_solenoid_approached_only_at_the_centre_of_long_coils():
    a, i = 0.01, 1.0
    centre = []
    for length, n in ((0.04, 20), (0.2, 100), (1.0, 500)):
        b = bh([solenoid(current=i, radius=a, length=length, turns=n)],
               [[0, 0, 0], [0, 0, length / 2]]).b
        ideal = MU0 * (n / length) * i
        centre.append(abs(b[0][2] - ideal) / ideal)
        # At an end the field drops to about half the central value (never the ideal value).
        # The discrete coil acts like a sheet extending half a turn spacing past the end turns.
        eff = length * n / (n - 1)
        ratio = bs.finite_sheet_axis_bz(1.0, a, eff, length / 2) / bs.finite_sheet_axis_bz(
            1.0, a, eff, 0.0)
        assert b[1][2] / b[0][2] == pytest.approx(ratio, rel=0.02)
        assert b[1][2] < 0.7 * ideal
    # n = N/L, while the turns cover L (1 + 1/(N-1)): the remaining offset is about 1/(N-1).
    assert centre[0] > centre[1] > centre[2]
    assert centre[2] == pytest.approx(1 / 499, rel=0.15)


def test_end_effects_and_weak_field_outside():
    b = bh([solenoid()], [[0, 0, 0], [0, 0, 0.1], [0, 0, 0.2], [0.08, 0, 0]]).b
    assert b[1][2] < 0.65 * b[0][2]  # end
    assert b[2][2] < 0.2 * b[0][2]  # beyond the end: fringe field
    assert abs(b[3][2]) < 0.1 * b[0][2] and b[3][2] < 0  # outside, return direction


def test_reversal_scaling_and_parameter_dependence():
    pts = [[0.01, 0.02, 0.03], [0.1, 0, 0.12]]
    base = bh([solenoid(current=1.0)], pts).b
    assert np.array_equal(bh([solenoid(current=-1.0)], pts).b, -base)
    assert np.allclose(bh([solenoid(current=2.5)], pts).b, 2.5 * base, rtol=1e-14)
    for kw in ({"turns": 21}, {"length": 0.21}, {"radius": 0.041}):
        assert not np.allclose(bh([solenoid(**kw)], pts).b, base, rtol=1e-6)


def test_translation_and_rotation_covariance():
    local = np.array([0.02, -0.01, 0.07])
    ref = bh([solenoid()], [local]).b[0]
    d = np.array([1.0, 2.0, -0.5]) / np.linalg.norm([1.0, 2.0, -0.5])
    rot = rot_for(d)
    pos = np.array([0.3, -0.2, 0.1])
    cs = current_sources(scene_of(solenoid(pos=tuple(pos), rot=rot)))
    rmat = np.column_stack([cs.loops[0].u, np.cross(cs.loops[0].normal, cs.loops[0].u),
                            cs.loops[0].normal])
    b = ms.evaluate((pos + rmat @ local)[None, :], cs, R_MIN)[0]
    assert np.allclose(b, rmat @ ref, rtol=1e-12, atol=1e-12 * np.linalg.norm(ref))


@pytest.mark.parametrize("bad", [
    {"turns": 0}, {"turns": 5, "length": 0.0}, {"radius": 0.0}, {"radius": float("nan")}])
def test_invalid_solenoids_are_rejected(bad):
    with pytest.raises(ValidationError):
        scene_of(solenoid(**bad))


def test_scaled_coil_is_refused():
    obj = solenoid()
    obj["transform"]["scale"] = (1.0, 1.0, 2.0)
    with pytest.raises(UnsupportedSceneError) as exc:
        engine.run(scene_of(obj), points_request([(0.1, 0, 0)], "B"))
    assert "scaled" in exc.value.reasons[0].en


# --------------------------------------------------------------------------- finite toroid


def test_toroid_turn_geometry_and_orientation():
    cs = current_sources(scene_of(torus(turns=8)))
    assert len(cs.loops) == 8
    for k, lp in enumerate(cs.loops):
        phi = 2 * math.pi * k / 8
        e_rho = np.array([math.cos(phi), math.sin(phi), 0])
        e_phi = np.array([-math.sin(phi), math.cos(phi), 0])
        assert np.allclose(lp.center_m, 0.12 * e_rho, atol=1e-16)
        assert np.allclose(lp.normal, e_phi, atol=1e-16)  # same circulation sense for every turn
        assert lp.radius_m == 0.03 and lp.current_A == 1.0


def test_finite_toroid_against_numerical_biot_savart():
    scene = scene_of(torus(turns=12))
    cs = current_sources(scene)
    for p in ([0.12, 0.0, 0.01], [0.05, 0.08, 0.02], [0.3, 0.1, -0.05]):
        p = np.asarray(p, float)
        ref = sum(bs.loop_converged(p, lp.center_m, lp.normal, lp.u, lp.radius_m,
                                    lp.current_A).value for lp in cs.loops)
        b = ms.evaluate(p[None, :], cs, R_MIN)[0]
        assert np.linalg.norm(b - ref) <= 1e-10 * np.linalg.norm(b) + 1e-22


def test_toroid_rotational_covariance_reversal_and_outside_field():
    n = 16
    p = np.array([0.13, 0.01, 0.005])
    ang = 2 * math.pi / n
    rz = np.array([[math.cos(ang), -math.sin(ang), 0], [math.sin(ang), math.cos(ang), 0],
                   [0, 0, 1]])
    b = bh([torus(turns=n)], [p, rz @ p, [0.3, 0.0, 0.0], [0, 0, 0.2]]).b
    assert np.allclose(b[1], rz @ b[0], rtol=1e-12, atol=1e-20)
    assert np.array_equal(bh([torus(turns=n, current=-1.0)], [p]).b[0], -b[0])
    # Outside: computed by superposition, small but not forced to zero.
    assert 0 < np.linalg.norm(b[2]) < 1e-3 * np.linalg.norm(b[0])
    assert np.linalg.norm(b[3]) > 0


def test_whole_toroid_translation_and_rotation():
    local = np.array([0.1, 0.02, 0.01])
    ref = bh([torus()], [local]).b[0]
    rot = rot_for((0.4, 0.5, 0.7))
    pos = np.array([0.05, -0.02, 0.1])
    cs = current_sources(scene_of(torus(pos=tuple(pos), rot=rot)))
    from emf_core.scene.transforms import rotation_matrix_xyz

    rmat = rotation_matrix_xyz(rot)
    b = ms.evaluate((pos + rmat @ local)[None, :], cs, R_MIN)[0]
    assert np.allclose(b, rmat @ ref, rtol=1e-12, atol=1e-12 * np.linalg.norm(ref))


def test_more_turns_approach_the_continuous_winding():
    # Midway between turns on the centreline, the finite field approaches mu0 N I / (2 pi R).
    errs = []
    for n in (8, 24, 96):
        phi = math.pi / n
        p = [0.12 * math.cos(phi), 0.12 * math.sin(phi), 0]
        b = np.linalg.norm(bh([torus(turns=n, current=24 / n)], [p]).b[0])
        errs.append(abs(b - MU0 * 24 / (2 * math.pi * 0.12)) / (MU0 * 24 / (2 * math.pi * 0.12)))
    assert errs[0] > errs[1] > errs[2]


@pytest.mark.parametrize("bad", [{"major": 0.03, "b_w": 0.03}, {"b_w": 0.2}, {"turns": 0},
                                 {"b_c": 0.13}])
def test_invalid_toroids_are_rejected(bad):
    with pytest.raises(ValidationError):
        scene_of(torus(**bad))


def test_toroid_turn_separation_is_checked():
    close = current_sources(scene_of(torus(turns=4000, major=0.12, b_w=0.11)))
    assert not close.problems and close.warnings  # close but valid: warned
    with pytest.raises(UnsupportedSceneError):
        engine.run(scene_of(torus(turns=10**10, major=0.12, b_w=0.11)),
                   points_request([(0.5, 0, 0)], "B"))


# ---------------------------------------------------------------------------- ideal toroid


def test_ideal_toroid_core_field_and_outside_zero():
    n, i, mu_r, major, b_c = 24, 1.5, 200.0, 0.12, 0.03
    obj = torus(model="toroid_ideal", current=i, turns=n, mu_r=mu_r, major=major, b_c=b_c)
    pts = [[0.12, 0, 0], [0, 0.1, 0.01], [0.149, 0, 0], [0.151, 0, 0], [0.12, 0, 0.031],
           [0.0, 0.0, 0.0]]
    ev = bh([obj], pts)
    for p, b, h in zip(pts[:3], ev.b[:3], ev.h[:3], strict=True):
        rho = math.hypot(p[0], p[1])
        e_phi = np.array([-p[1], p[0], 0]) / rho
        assert np.allclose(h, n * i / (2 * math.pi * rho) * e_phi, rtol=1e-14)
        assert np.allclose(b, MU0 * mu_r * h, rtol=1e-14)
    for b, h in zip(ev.b[3:], ev.h[3:], strict=True):
        assert np.all(b == 0) and np.all(h == 0)
    rev = bh([torus(model="toroid_ideal", current=-i, turns=n, mu_r=mu_r)], pts[:1])
    assert np.array_equal(rev.h[0], -ev.h[0])
    assert np.all(ev.material[:3] == 2) and np.all(ev.material[3:] == 0)


def test_ideal_toroid_boundary_is_one_sided_and_explicit():
    ev = bh([torus(model="toroid_ideal")], [[0.15, 0, 0]])
    assert ev.status[0] == ms.ST_CORE_BOUNDARY and np.all(np.isnan(ev.b[0]))


def test_models_do_not_contaminate_each_other():
    p = [[0.12, 0.0, 0.01]]
    finite = bh([torus(b_c=0.02)], p).b
    assert np.array_equal(finite, bh([torus(b_c=0.025)], p).b)  # b_core unused by finite
    ideal = bh([torus(model="toroid_ideal", b_w=0.02)], p).b
    assert np.array_equal(ideal, bh([torus(model="toroid_ideal", b_w=0.025)], p).b)


def test_ideal_toroid_with_other_sources_or_bad_mu_is_refused():
    with pytest.raises(UnsupportedSceneError) as exc:
        engine.run(scene_of(torus(model="toroid_ideal"), wire("w", 1.0, (0.5, 0, 0))),
                   points_request([(0.3, 0.3, 0)], "B"))
    assert "cannot be combined" in exc.value.reasons[0].en
    with pytest.raises(ValidationError):
        scene_of(torus(model="toroid_ideal", mu_r=0.0))


# -------------------------------------------------------------------------- permanent magnet


@pytest.mark.parametrize("z", [0.0, 0.02, 0.039, 0.041, 0.06, 0.2, -0.05])
def test_magnet_axis_field_against_closed_form(z):
    a, length, m = 0.04, 0.08, 5e5
    ev = bh([magnet()], [[0, 0, z]])
    ref = bs.finite_sheet_axis_bz(m, a, length, z)
    assert ev.b[0][2] == pytest.approx(ref, rel=1e-11)
    inside = abs(z) < length / 2
    assert ev.h[0][2] == pytest.approx(ref / MU0 - (m if inside else 0.0), rel=1e-10)


def test_magnet_off_axis_against_direct_surface_integral():
    scene = scene_of(magnet(m=3e5, pos=(0.01, 0, 0), rot=rot_for((0.2, 0.3, 1.0))))
    mg = current_sources(scene).magnets[0]
    for local in ([0.02, 0.01, 0.01], [0.07, 0.0, 0.0], [0.05, 0.02, 0.06], [0.2, 0.1, 0.3]):
        lv = np.asarray(local, float)
        p = mg.center_m + lv[0] * mg.u + lv[1] * np.cross(mg.axis, mg.u) + lv[2] * mg.axis
        ref = bs.magnet_sheet(p, mg.center_m, mg.axis, mg.u, mg.radius_m, mg.length_m,
                              mg.magnetization_A_per_m)
        b = ms.evaluate(p[None, :], current_sources(scene), R_MIN, 1e-11)[0]
        assert np.linalg.norm(b - ref) / np.linalg.norm(ref) < 1e-8, local


def test_magnet_quadrature_converges_with_tolerance():
    cs = current_sources(scene_of(magnet()))
    p = np.array([[0.0405, 0.0, 0.01], [0.03, 0.0, 0.035]])  # near the wall and the rim
    vals = [ms.evaluate(p, cs, R_MIN, rtol) for rtol in (1e-5, 1e-8, 1e-11, 1e-13)]
    errs = [np.linalg.norm(v - vals[-1]) / np.linalg.norm(vals[-1]) for v in vals[:-1]]
    assert errs[0] < 1e-4 and errs[1] < 1e-7 and errs[2] < 1e-10


def test_bound_surface_current_from_one_sided_limits():
    """K_b = M × n: across the side wall the tangential B jumps by μ0 K_b = μ0 M (along the
    axis, inside larger for M > 0); the normal component is continuous. Across an end face
    there is no surface current: B is continuous, H_z jumps by M."""
    m, delta = 5e5, 1e-7
    ev = bh([magnet(m=m)], [[0.04 - delta, 0, 0.01], [0.04 + delta, 0, 0.01],
                            [0.01, 0, 0.04 - delta], [0.01, 0, 0.04 + delta]])
    jump = ev.b[0] - ev.b[1]
    assert jump[2] == pytest.approx(MU0 * m, rel=1e-4)  # tangential, sign of M × n_outward
    assert abs(jump[0]) < 1e-4 * MU0 * m  # normal B continuous
    assert np.allclose(ev.b[2], ev.b[3], rtol=1e-4, atol=1e-6)  # end face: no sheet
    assert ev.h[2][2] - ev.h[3][2] == pytest.approx(-m, rel=1e-4)
    rev = bh([magnet(m=-m)], [[0.04 - delta, 0, 0.01]])
    assert np.array_equal(rev.b[0], -ev.b[0])


def test_magnet_b_and_h_inside_outside_and_moment():
    m = 4e5
    pts = [[0.01, 0.0, 0.0], [0.0, 0.0, 0.3], [0.1, 0.05, 0.02]]
    ev = bh([magnet(m=m)], pts)
    assert np.allclose(ev.h[0], ev.b[0] / MU0 - np.array([0, 0, m]), rtol=1e-14)
    assert np.allclose(ev.h[1:], ev.b[1:] / MU0, rtol=1e-14)
    assert ev.h[0][2] < 0 < ev.b[0][2]  # inside a bar magnet H opposes B
    assert np.all(ev.m[1:] == 0) and ev.m[0][2] == m
    mg = current_sources(scene_of(magnet(m=m))).magnets[0]
    assert np.allclose(mg.moment_A_m2, [0, 0, m * math.pi * 0.04**2 * 0.08], rtol=1e-15)


def test_uniform_magnetization_has_no_bound_volume_current():
    """J_b = ∇×M = 0 inside: numerically ∇×H = 0 and ∇×B = 0 inside the magnet (finite
    differences of the solver's fields), ∇·B = 0 inside and outside."""
    cs = current_sources(scene_of(magnet()))

    def b_fn(p):
        return ms.evaluate(p, cs, R_MIN, 1e-12)

    for p in ([0.01, 0.005, 0.01], [0.0, 0.02, -0.02], [0.07, 0.01, 0.05]):
        est = estimate(b_fn, np.asarray(p, float), 1e-4)
        scale = np.linalg.norm(b_fn(np.asarray([p], float))[0]) / 0.04
        assert np.all(np.abs(est.curl) <= est.curl_uncertainty + 1e-6 * scale)
        assert abs(est.div) <= est.div_uncertainty + 1e-6 * scale


def test_magnet_far_field_approaches_a_dipole():
    m = 5e5
    mom = np.array([0, 0, m * math.pi * 0.04**2 * 0.08])
    errs = []
    for r in (0.4, 1.0, 3.0):
        p = np.array([r * 0.6, 0.0, r * 0.8])
        b = bh([magnet(m=m)], [p]).b[0]
        rh = p / r
        dip = MU0 / (4 * math.pi * r**3) * (3 * (mom @ rh) * rh - mom)
        errs.append(np.linalg.norm(b - dip) / np.linalg.norm(dip))
    assert errs[0] > errs[1] > errs[2] and errs[2] < 1e-3


def test_point_on_the_current_sheet_is_a_boundary_not_a_value():
    ev = bh([magnet()], [[0.04, 0.0, 0.01], [0.0, 0.04, -0.04], [0.02, 0.0, 0.04]])
    assert ev.status[0] == ms.ST_SHEET and np.all(np.isnan(ev.b[0]))
    assert ev.status[1] == ms.ST_SHEET  # rim
    assert ev.status[2] == ms.ST_END_FACE and np.all(np.isfinite(ev.b[2]))
    assert np.all(np.isnan(ev.h[2]))


def test_overlapping_magnets_are_refused_touching_ones_accepted():
    with pytest.raises(UnsupportedSceneError) as exc:
        engine.run(scene_of(magnet("a"), magnet("b", pos=(0.03, 0, 0))),
                   points_request([(0.5, 0, 0)], "B"))
    assert "overlap" in exc.value.reasons[0].en
    r = engine.run(scene_of(magnet("a"), magnet("b", pos=(0, 0, 0.08))),
                   points_request([(0.5, 0, 0)], "B"))
    assert r.header.status == "ok"


# ------------------------------------------------------------------------- global checks


def test_superposition_and_div_b_for_new_sources():
    objs = [solenoid(turns=5), torus(turns=6, pos=(0.5, 0, 0)),
            magnet(pos=(0, 0.4, 0), rot=rot_for((1, 0, 0)))]
    rng = np.random.default_rng(3)
    pts = rng.uniform(-0.3, 0.3, size=(12, 3)) + np.array([0.2, 0.2, 0.0])
    total = bh(objs, pts).b
    parts = sum(bh([o], pts).b for o in objs)
    assert np.allclose(total, parts, rtol=1e-12, atol=1e-18)
    cs = current_sources(scene_of(*objs))
    for p in pts[:4]:
        d = min(ms.distance_to_sources(p[None, :], cs)[0],
                ms.distance_to_boundaries(p[None, :], cs)[0])
        est = estimate(lambda q: ms.evaluate(q, cs, R_MIN, 1e-12), p, 1e-3 * d)
        scale = np.linalg.norm(ms.evaluate(p[None, :], cs, R_MIN)[0]) / d
        assert abs(est.div) <= est.div_uncertainty + 1e-7 * scale


def test_magnetic_cache_keys_and_electric_independence():
    req_b = points_request([(0.3, 0.1, 0.0)], "B")
    req_e = points_request([(0.3, 0.1, 0.0)], "E")
    base = [solenoid(), charge("q", 1e-9, (0.5, 0.5, 0))]
    keys = {engine.physics_fingerprint(scene_of(*base), req_b)}
    for change in ({"turns": 21}, {"length": 0.3}, {"current": 2.0}, {"pos": (0.01, 0, 0)}):
        keys.add(engine.physics_fingerprint(scene_of(solenoid(**change), base[1]), req_b))
        assert engine.physics_fingerprint(scene_of(solenoid(**change), base[1]), req_e) == \
            engine.physics_fingerprint(scene_of(*base), req_e)
    assert len(keys) == 5
    e1 = engine.run(scene_of(*base), req_e).arrays["p.E"]
    e2 = engine.run(scene_of(charge("q", 1e-9, (0.5, 0.5, 0))), req_e).arrays["p.E"]
    assert np.array_equal(e1, e2)


def test_old_scenes_load_and_solve_unchanged():
    old = Scene.model_validate({"objects": [wire("w", 3.0), loop("l", 2.0, 0.4)]})
    r = engine.run(old, SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": [[0.3, 0.2, 0.1]]}],
        "quantities": ["B", "H"]}))
    assert r.header.classification == "exact_analytical"
    assert np.allclose(r.arrays["p.B"], MU0 * r.arrays["p.H"], rtol=1e-15)
