"""Validation of the analytical magnetostatic solver (Phase 3A) against independent references:
closed forms, a numerical Biot–Savart integral written separately from the solver, symmetry,
linearity, the right-hand rule and the divergence identity."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core import engine
from emf_core.postprocess.differential import estimate
from emf_core.scene.currents import current_sources
from emf_core.solvers.analytical import FilamentMagnetostaticSolver
from emf_core.solvers.analytical import magnetostatics as ms
from emf_core.units import MU0
from emf_core.verification import biot_savart as bs
from tests.conftest import charge, loop, points_request, scene_of, wire

SOLVER = FilamentMagnetostaticSolver()
RTOL = 1e-12


def field(scene, pts, *q):
    r = SOLVER.solve(scene, points_request([tuple(p) for p in pts], *(q or ("B", "H"))))
    return r


def b_at(scene, pts):
    return field(scene, pts, "B").arrays["p.B"]


def unit(v):
    v = np.asarray(v, float)
    return v / np.linalg.norm(v)


def rot_for(d):
    """Euler XYZ angles whose rotation maps local +z to the unit vector d (as in the UI)."""
    d = unit(d)
    return (math.atan2(-d[1], d[2]), math.asin(d[0]), 0.0)


# --- 1-4: infinite wire --------------------------------------------------------------------


@pytest.mark.parametrize("current", [10.0, -3.5, 2e3])
@pytest.mark.parametrize("r", [1e-4, 0.37, 1.0, 25.0])
def test_wire_magnitude_matches_closed_form(current, r):
    b = b_at(scene_of(wire("w", current)), [(r, 0.0, 0.3)])
    assert np.linalg.norm(b[0]) == pytest.approx(bs.wire_magnitude(current, r), rel=RTOL)


def test_wire_direction_right_hand_rule():
    # Current along +z: B circles counter-clockwise seen from +z, i.e. B = phi_hat.
    pts = [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0), (0.6, 0.8, 5.0)]
    b = b_at(scene_of(wire("w", 10.0)), pts)
    for p, bi in zip(pts, b, strict=True):
        phi_hat = unit(np.cross([0, 0, 1], [p[0], p[1], 0]))
        assert np.allclose(unit(bi), phi_hat, atol=1e-15)
        assert abs(bi[2]) == 0.0 and abs(np.dot(bi, [p[0], p[1], 0])) < 1e-20  # azimuthal only


@pytest.mark.parametrize("d", [(1, 0, 0), (0.3, -0.5, 0.81), (-1, 2, 2), (0, 1, 0)])
def test_arbitrary_wire_orientation(d):
    d = unit(d)
    p0 = np.array([0.2, -0.4, 0.1])
    scene = scene_of(wire("w", 7.0, tuple(p0), rot_for(d)))
    rng = np.random.default_rng(1)
    pts = p0 + rng.normal(size=(20, 3))
    b = b_at(scene, pts)
    for p, bi in zip(pts, b, strict=True):
        r = p - p0
        rp = r - (r @ d) * d
        rho = np.linalg.norm(rp)
        expected = bs.wire_magnitude(7.0, rho) * np.cross(d, rp / rho)
        assert np.allclose(bi, expected, rtol=1e-12, atol=1e-12 * np.linalg.norm(expected))
    # Independent check: numerical Biot–Savart over a long segment plus its analytical tail.
    ref = bs.wire_segment(pts[0], p0, d, 7.0, half_length=3.0)
    assert np.linalg.norm(b[0] - ref) / np.linalg.norm(ref) < 1e-10


def test_current_reversal_and_scaling():
    pts = [(0.3, 0.7, -0.2), (1.5, -0.4, 0.9)]
    for make in (lambda i: wire("w", i, (0.1, 0, 0), rot_for((1, 1, 0))),
                 lambda i: loop("l", i, 0.5, (0, 0.1, 0), rot_for((0.2, 0.3, 1)))):
        r1 = field(scene_of(make(4.0)), pts)
        r2 = field(scene_of(make(-4.0)), pts)
        r3 = field(scene_of(make(8.0)), pts)
        for q in ("B", "H"):
            assert np.array_equal(r2.arrays[f"p.{q}"], -r1.arrays[f"p.{q}"])
            assert np.allclose(r3.arrays[f"p.{q}"], 2 * r1.arrays[f"p.{q}"], rtol=1e-15, atol=0)


# --- 5-7: parallel wires and superposition --------------------------------------------------


def test_two_parallel_wires_same_direction():
    s = scene_of(wire("a", 10.0, (-0.5, 0, 0)), wire("b", 10.0, (0.5, 0, 0)))
    b = b_at(s, [(0, 0, 0), (0, 1, 0), (2, 0, 0)])
    assert np.linalg.norm(b[0]) == 0.0  # exact cancellation midway (mirror symmetry)
    # On the perpendicular bisector the y-components cancel and the x-components add.
    r = math.hypot(0.5, 1.0)
    assert b[1][0] == pytest.approx(-2 * bs.wire_magnitude(10, r) * (1.0 / r), rel=1e-13)
    assert abs(b[1][1]) < 1e-20
    # Outside, the fields add: 10 A at 2.5 m and 10 A at 1.5 m, both along +y.
    assert b[2][1] == pytest.approx(bs.wire_magnitude(10, 2.5) + bs.wire_magnitude(10, 1.5),
                                    rel=1e-13)


def test_two_parallel_wires_opposite_directions():
    s = scene_of(wire("a", 10.0, (-0.5, 0, 0)), wire("b", -10.0, (0.5, 0, 0)))
    b = b_at(s, [(0, 0, 0), (2, 0, 0)])
    # Between the wires the contributions reinforce: 2 × mu0 I/(2 pi 0.5), along +y.
    assert b[0][1] == pytest.approx(2 * bs.wire_magnitude(10, 0.5), rel=1e-13)
    assert b[1][1] == pytest.approx(bs.wire_magnitude(10, 2.5) - bs.wire_magnitude(10, 1.5),
                                    rel=1e-13)


def test_unequal_currents_zero_moves_towards_weaker_wire():
    s = scene_of(wire("a", 10.0, (-0.5, 0, 0)), wire("b", 4.0, (0.5, 0, 0)))
    x0 = 3 / 14  # 10/(x0 + 0.5) = 4/(0.5 - x0)
    b = b_at(s, [(x0, 0, 0), (x0 - 0.01, 0, 0), (x0 + 0.01, 0, 0)])
    scale = bs.wire_magnitude(10, 1.0)
    assert np.linalg.norm(b[0]) < 1e-14 * scale
    assert b[1][1] * b[2][1] < 0  # B_y changes sign across the zero


def test_superposition_is_exactly_the_sum_of_sources():
    objs = [wire("a", 3.0, (0.4, 0, 0), rot_for((0, 1, 1))), wire("b", -7.0, (-0.2, 0.3, 0)),
            loop("c", 5.0, 0.6, (0, 0, 0.3), rot_for((1, 0, 1)))]
    rng = np.random.default_rng(7)
    pts = rng.uniform(-1.5, 1.5, size=(40, 3))
    total = b_at(scene_of(*objs), pts)
    singles = sum(b_at(scene_of(o), pts) for o in objs)
    assert np.allclose(total, singles, rtol=1e-14, atol=1e-25)
    cs = current_sources(scene_of(*objs))
    parts = ms.source_fields(pts, cs, 1e-12)
    assert np.allclose(total, sum(parts), rtol=1e-15, atol=0)


# --- 8-12: circular loop -------------------------------------------------------------------


@pytest.mark.parametrize("z", [0.0, 0.1, -0.37, 2.0, 30.0])
def test_loop_on_axis_matches_closed_form(z):
    a, i = 0.5, 10.0
    b = b_at(scene_of(loop("l", i, a)), [(0, 0, z)])[0]
    assert b[2] == pytest.approx(bs.loop_axis_bz(i, a, z), rel=1e-14)
    assert b[0] == 0.0 and b[1] == 0.0  # B_rho = 0 by symmetry, exactly


def _loop_case(seed=3):
    rng = np.random.default_rng(seed)
    normal = unit(rng.normal(size=3))
    center = rng.uniform(-0.3, 0.3, size=3)
    return center, normal


def _local_point(center, normal, u, a, rho, z, phi=0.7):
    v = np.cross(normal, u)
    return center + z * normal + rho * (math.cos(phi) * u + math.sin(phi) * v)


@pytest.mark.parametrize("rho_over_a,z_over_a", [
    (0.3, 0.4), (0.9, -0.2), (1.5, 0.8), (3.0, -2.0), (0.05, 0.2), (1.0, 0.5), (0.5, 0.0),
    (1.0 + 0.02, 0.0), (1.0, 0.011), (1.3, 0.0),
])
def test_loop_off_axis_against_numerical_biot_savart(rho_over_a, z_over_a):
    """Normal region (distance from the wire >= 0.01 a): relative vector error <= 1e-8."""
    a, i = 0.5, 10.0
    center, normal = _loop_case()
    scene = scene_of(loop("l", i, a, tuple(center), rot_for(normal)))
    lp = current_sources(scene).loops[0]
    p = _local_point(center, normal, lp.u, a, rho_over_a * a, z_over_a * a)
    assert math.hypot(rho_over_a - 1, z_over_a) >= 0.01
    ref = bs.loop_converged(p, lp.center_m, lp.normal, lp.u, lp.radius_m, i)
    b = b_at(scene, [p])[0]
    err = np.linalg.norm(ref.value - b) / np.linalg.norm(b)
    assert err <= 1e-8, (err, ref.nodes)


@pytest.mark.parametrize("d_over_a,angle",
                         [(0.001, 0.3), (0.002, 2.0), (0.005, -1.2), (0.0099, 4.0)])
def test_loop_near_wire_against_numerical_biot_savart(d_over_a, angle):
    """Near-wire region (0.001 a <= distance < 0.01 a): relative vector error <= 1e-6."""
    a, i = 0.5, 10.0
    center, normal = _loop_case(5)
    scene = scene_of(loop("l", i, a, tuple(center), rot_for(normal)))
    lp = current_sources(scene).loops[0]
    rho = a + d_over_a * a * math.cos(angle)
    z = d_over_a * a * math.sin(angle)
    p = _local_point(center, normal, lp.u, a, rho, z)
    ref = bs.loop_converged(p, lp.center_m, lp.normal, lp.u, lp.radius_m, i, rtol=1e-12)
    b = b_at(scene, [p])[0]
    assert np.linalg.norm(ref.value - b) / np.linalg.norm(b) <= 1e-6


def test_numerical_biot_savart_converges_with_resolution():
    """The independent reference converges as its node count grows (exponentially for the
    periodic trapezoidal rule), towards the analytical solution."""
    a, i = 0.5, 10.0
    scene = scene_of(loop("l", i, a))
    lp = current_sources(scene).loops[0]
    p = np.array([0.52, 0.0, 0.01])  # about 0.045 a from the wire
    exact = b_at(scene, [p])[0]
    errors = [np.linalg.norm(bs.loop_trapezoid(p, lp.center_m, lp.normal, lp.u, a, i, n) - exact)
              / np.linalg.norm(exact) for n in (64, 128, 256, 512, 1024, 2048)]
    assert all(e2 < e1 for e1, e2 in zip(errors, errors[1:], strict=False) if e1 > 1e-13)
    assert errors[0] > 1e-2 and errors[-1] < 1e-12


def test_loop_orientation_rotates_the_field_rigidly():
    a, i = 0.4, 6.0
    ref_scene = scene_of(loop("l", i, a))
    for d in [(1, 0, 0), (0.3, -0.5, 0.81), (0, -1, 0)]:
        d = unit(d)
        rot = rot_for(d)
        scene = scene_of(loop("l", i, a, (0.1, -0.2, 0.3), rot))
        lp = current_sources(scene).loops[0]
        assert np.allclose(lp.normal, d, atol=1e-15)
        # Same local point in both frames: the field is the rotated reference field.
        rmat = np.column_stack([lp.u, np.cross(lp.normal, lp.u), lp.normal])
        local = np.array([0.31, -0.12, 0.27])
        b_ref = b_at(ref_scene, [local])[0]
        b = b_at(scene, [lp.center_m + rmat @ local])[0]
        assert np.allclose(b, rmat @ b_ref, rtol=1e-12, atol=1e-12 * np.linalg.norm(b_ref))


def test_loop_axial_symmetry_and_mirror_symmetry():
    a, i = 0.5, 10.0
    scene = scene_of(loop("l", i, a))
    phis = np.linspace(0, 2 * np.pi, 13)[:-1]
    pts = [(0.8 * math.cos(p), 0.8 * math.sin(p), 0.3) for p in phis]
    b = b_at(scene, pts)
    # |B|, B_z and B_rho are the same at every azimuth; there is no azimuthal component.
    bz = b[:, 2]
    brho = np.array([bi[:2] @ unit(p[:2]) for bi, p in zip(b, pts, strict=True)])
    bphi = np.array([bi[:2] @ unit((-p[1], p[0])) for bi, p in zip(b, pts, strict=True)])
    assert np.ptp(bz) <= 1e-14 * abs(bz[0]) and np.ptp(brho) <= 1e-14 * abs(brho[0])
    assert np.max(np.abs(bphi)) <= 1e-14 * np.linalg.norm(b[0])
    # Mirror in the loop plane: B_z even, B_rho odd in z.
    up, down = b_at(scene, [(0.7, 0, 0.25), (0.7, 0, -0.25)])
    assert up[2] == pytest.approx(down[2], rel=1e-14)
    assert up[0] == pytest.approx(-down[0], rel=1e-14)


def test_loop_right_hand_rule():
    # Counter-clockwise current about +z (positive I): B along +z inside, near the centre.
    b = b_at(scene_of(loop("l", 10.0, 0.5)), [(0, 0, 0), (0.1, 0.05, 0.02)])
    assert b[0][2] > 0 and b[1][2] > 0
    # Around the wire at (a, 0, 0), where the current flows along +y: B circles +y.
    for ang in np.linspace(0, 2 * np.pi, 9)[:-1]:
        p = np.array([0.5 + 0.01 * math.cos(ang), 0.0, 0.01 * math.sin(ang)])
        bi = b_at(scene_of(loop("l", 10.0, 0.5)), [p])[0]
        radial = p - np.array([0.5, 0, 0])
        assert np.dot(np.cross([0, 1, 0], radial), bi) > 0


# --- near-axis formulation -----------------------------------------------------------------


def test_series_coefficients_and_truncation():
    f = ms.F_SERIES
    assert f[0] == 0 and f[1] == 0 and f[2] == 0.375 and np.all(f[2:] > 0)
    assert np.all(np.diff(f[2:]) < 0)  # decreasing: the tail bound used below is valid
    assert ms.series_remainder_bound(ms.NEAR_AXIS_M) < 1e-20


def test_near_axis_continuity_axial_and_radial_components():
    """Exact axis, near-axis series and general elliptic formula agree, for both components,
    as the distance from the axis shrinks, including across the transition m = 0.5."""
    a, i, z = 0.5, 10.0, 0.2
    rho = np.array([0.0, 1e-12, 1e-9, 1e-6, 1e-4, 1e-2, 0.05])
    br, bz, _ = ms.loop_local(rho, np.full(rho.size, z), a, i)
    assert br[0] == 0.0 and bz[0] == pytest.approx(bs.loop_axis_bz(i, a, z), rel=1e-15)
    # Leading-order behaviour near the axis: B_rho = (3 mu0 I a^2 z / (4 (a^2+z^2)^(5/2))) rho.
    slope = 3 * MU0 * i * a * a * z / (4 * (a * a + z * z) ** 2.5)
    assert np.allclose(br[1:5] / rho[1:5], slope, rtol=1e-6)
    assert np.all(br[1:] > 0)  # nonzero radial component is kept, however small
    assert np.allclose(bz[:5], bz[0], rtol=1e-6)
    # Across the transition between the series and the closed form: no jump.
    from scipy.optimize import brentq

    r0 = brentq(lambda r: 4 * a * r / ((a + r) ** 2 + z * z) - ms.NEAR_AXIS_M, 1e-6, a)
    x = np.array([r0 * (1 - 1e-12), r0 * (1 + 1e-12)])
    brx, bzx, _ = ms.loop_local(x, np.full(2, z), a, i)
    assert brx[0] == pytest.approx(brx[1], rel=1e-11)
    assert bzx[0] == pytest.approx(bzx[1], rel=1e-11)
    # Both formulations at the same m below the threshold: the series is the accurate one, and
    # the cancelling closed form approaches it as m grows.
    for r in (0.05, 0.1, 0.2):
        m = 4 * a * r / ((a + r) ** 2 + z * z)
        series = ms.loop_local(np.array([r]), np.array([z]), a, i)[0][0]
        p = np.array([r, 0, z])
        ref = bs.loop_converged(p, np.zeros(3), np.array([0, 0, 1.0]), np.array([1.0, 0, 0]),
                                a, i).value
        assert series == pytest.approx(ref[0], rel=1e-10), m


# --- 13-14, 18: B = mu0 H, singularities, divergence -------------------------------------


def test_b_equals_mu0_h_and_units():
    r = field(scene_of(wire("w", 3.0), loop("l", -2.0, 0.4, (0.2, 0, 0))), [(0.3, 0.6, 0.1)])
    assert np.allclose(r.arrays["p.B"], MU0 * r.arrays["p.H"], rtol=1e-15, atol=0)
    units = {e.quantity: e.unit for e in r.header.arrays}
    assert units == {"B": "T", "H": "A/m"}


def test_singularities_on_filaments_are_explicit():
    s = scene_of(wire("w", 3.0, (0.5, 0, 0)), loop("l", 2.0, 0.4))
    tol = ms.COINCIDENCE_FACTOR * s.domain.diagonal_m
    r = field(s, [(0.5, 0, 1.7), (0, 0.4, 0), (0.5 + 2 * tol, 0, 0), (0.3, 0.3, 0.3)],
              "B", "H", "div_B", "div_H")
    b, divb = r.arrays["p.B"], r.arrays["p.div_B"]
    assert np.all(np.isnan(b[0])) and np.all(np.isnan(b[1]))  # on the wire, on the loop
    assert np.isnan(divb[0]) and np.isnan(divb[1])  # not evaluated where B is undefined
    # Just outside the tolerance: the true (huge) analytical value, dominated by the wire.
    assert np.all(np.isfinite(b[2]))
    actual = (0.5 + 2 * tol) - 0.5  # the distance that float64 actually represents (exact)
    assert np.linalg.norm(b[2]) == pytest.approx(bs.wire_magnitude(3.0, actual), rel=1e-6)
    assert divb[3] == 0.0 and r.arrays["p.div_H"][3] == 0.0
    assert any("singular" in w.en for w in r.header.warnings)


def test_divergence_of_b_is_zero_numerically_and_reported_exactly():
    s = scene_of(wire("a", 10.0, (-0.5, 0, 0), rot_for((0.1, 0.2, 1))),
                 loop("l", 7.0, 0.5, (0.2, 0.1, 0.0), rot_for((1, 1, 1))))
    cs = current_sources(s)

    def fn(p):
        return ms.evaluate(p, cs, 1e-12)

    rng = np.random.default_rng(11)
    for p in rng.uniform(-1.2, 1.2, size=(8, 3)):
        d = ms.distance_to_sources(p[None, :], cs)[0]
        est = estimate(fn, p, 1e-3 * d)
        assert abs(est.div) <= est.div_uncertainty + 1e-9 * np.linalg.norm(fn(p[None, :])) / d
    r = field(s, list(rng.uniform(-1.2, 1.2, size=(50, 3))), "div_B")
    assert np.all(r.arrays["p.div_B"] == 0.0)


def test_scene_charges_do_not_change_b_and_wires_do_not_change_e():
    w = wire("w", 10.0, (0.3, 0, 0))
    q = charge("q", 2e-9, (-0.4, 0.2, 0))
    pts = [(0.1, 0.5, 0.2), (1.0, -0.3, 0.4)]
    mreq = points_request(pts, "B")
    ereq = points_request(pts, "E", "phi")
    assert np.array_equal(engine.run(scene_of(w, q), mreq).arrays["p.B"],
                          engine.run(scene_of(w), mreq).arrays["p.B"])
    assert np.array_equal(engine.run(scene_of(w, q), ereq).arrays["p.E"],
                          engine.run(scene_of(q), ereq).arrays["p.E"])
    assert engine.physics_fingerprint(scene_of(w, q), mreq) == engine.physics_fingerprint(
        scene_of(w), mreq)
    assert engine.physics_fingerprint(scene_of(w, q), ereq) == engine.physics_fingerprint(
        scene_of(q), ereq)
