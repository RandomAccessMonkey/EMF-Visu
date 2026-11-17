"""Phase 3B.1: numerical stability near ideal current filaments.

An ideal filament's field is singular on the filament and finite (large) everywhere else. These
tests check that the circular-loop solution and every consumer keep that distinction: values
arbitrarily close to a filament are the true field (compared with an independent Biot–Savart
reference that uses no elliptic integrals), never capped; only points that float64 cannot tell
apart from the filament are singular; the float64 accuracy limit near a filament is reported,
not hidden.

Reference accuracy: ``bs.loop_local_reference`` integrates each graded sub-interval with QUADPACK
to 2e-14 relative, so comparisons in local coordinates use 3e-14. In world coordinates the input
point is a float64 vector; the solver is backward stable (its result is the exact field at a
point within ~ε·S), so its error there is bounded by the reported precision 8 ε S / d.
"""

from __future__ import annotations

import math
from decimal import Decimal, getcontext

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import ampere, engine
from emf_core.postprocess import magnetic_lines as ml
from emf_core.scene.currents import CurrentSources, LoopSource, current_sources
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import magnetostatics as ms
from emf_core.units import MU0
from emf_core.verification import biot_savart as bs
from tests.conftest import loop, magnet, scene_of, solenoid, torus, wire

# The reference must certify its own accuracy: a QUADPACK roundoff warning fails the test.
pytestmark = pytest.mark.filterwarnings("error::scipy.integrate.IntegrationWarning")

V1 = "/api/v1"
EPS = float(np.finfo(np.float64).eps)
DISTANCES = [10.0 ** -k for k in range(1, 14)]  # d / a, above the singular tolerance
ANGLES = np.linspace(0.0, 2 * math.pi, 12, endpoint=False) + 0.1


def local(rho: float, z: float, a: float = 1.0, current: float = 1.0) -> tuple[float, float]:
    br, bz, _ = ms.loop_local(np.array([rho]), np.array([z]), a, current)
    return float(br[0]), float(bz[0])


def one_loop(c, n, a, current=1.0) -> tuple[CurrentSources, LoopSource]:
    n = np.asarray(n, float) / np.linalg.norm(n)
    u = np.cross(n, [1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.cross(n, [0.0, 1.0, 0.0])
    u /= np.linalg.norm(u)
    lp = LoopSource("l", current, np.asarray(c, float), n, a, u)
    return CurrentSources(wires=[], loops=[lp], problems=[]), lp


def exact_local(p, lp: LoopSource) -> tuple[float, float, float, np.ndarray, np.ndarray]:
    """Local coordinates of a float64 point, computed exactly (60 digits): (rho - a, rho, z,
    radial unit vector, axis unit vector)."""
    getcontext().prec = 60
    P = [Decimal(float(x)) for x in p]
    C = [Decimal(float(x)) for x in lp.center_m]
    N = [Decimal(float(x)) for x in lp.normal]
    nn = sum(x * x for x in N).sqrt()
    N = [x / nn for x in N]
    d = [pi - ci for pi, ci in zip(P, C, strict=True)]
    z = sum(x * y for x, y in zip(d, N, strict=True))
    r = [x - z * y for x, y in zip(d, N, strict=True)]
    rho = sum(x * x for x in r).sqrt()
    return (float(rho - Decimal(lp.radius_m)), float(rho), float(z),
            np.array([float(x / rho) for x in r]), np.array([float(x) for x in N]))


# ----------------------------------------------------------- 1, 2: filament and its vicinity


def test_exactly_on_the_filament_is_singular_not_a_value():
    for a in (1.0, 0.04, 2.5):
        cs, _ = one_loop((0, 0, 0), (0, 0, 1), a)
        ev = ms.evaluate_bh(np.array([[a, 0.0, 0.0], [0.0, -a, 0.0]]), cs, 0.0)
        assert np.all(ev.status == ms.ST_SINGULAR)
        assert np.all(np.isnan(ev.b)) and np.all(np.isnan(ev.h))
        assert np.all(ev.precision == 0.0)  # no bogus accuracy claim on a singular point


@pytest.mark.parametrize("dist", DISTANCES)
def test_near_filament_local_formula_matches_independent_biot_savart(dist):
    """Exact local inputs: the elliptic-integral formulas stay at rounding level (≤ 3e-14)
    however close to the wire, down to 1e-13 a."""
    a = 1.0
    for th in ANGLES:
        u, z = dist * math.cos(th), dist * math.sin(th)
        rho = a + u
        br, bz = local(rho, z, a)
        rr, rz = bs.loop_local_reference(rho - a, rho, z, a, 1.0)
        assert math.hypot(br - rr, bz - rz) <= 3e-14 * math.hypot(rr, rz), (dist, th)


def test_field_grows_without_plateau_and_approaches_the_straight_wire_limit():
    """|B| increases toward the wire, with d|B| -> mu0 I / (2 pi) (the local straight-wire
    field) as d -> 0; deviation of order (d/a) ln(8a/d). No magnitude cap anywhere."""
    a, current = 0.3, 2.0
    mags = []
    for nominal in [a * 10.0 ** -k for k in range(1, 14)]:
        rho = a + nominal
        dist = rho - a  # the offset float64 actually represents (exact, Sterbenz)
        br, bz = local(rho, 0.0, a, current)
        mag = math.hypot(br, bz)
        mags.append(mag)
        ratio = mag * dist / (MU0 * current / (2 * math.pi))
        assert abs(ratio - 1) <= 2 * (dist / a) * math.log(8 * a / dist) + 1e-14
    assert all(m2 > 9.99 * m1 for m1, m2 in zip(mags, mags[1:], strict=False))
    assert mags[-1] == pytest.approx(MU0 * current / (2 * math.pi * 3e-14), rel=1e-3)  # no cap


def test_right_hand_rule_and_reversal_near_the_wire():
    """Positive current runs counter-clockwise about +z; at (a, 0, 0) it flows along +y. Next to
    it the field circles the wire: -z on the outside, +rho above it."""
    a, dist = 1.0, 1e-9
    br, bz = local(a + dist, 0.0, a)
    assert bz < 0 and abs(br) <= 1e-12 * abs(bz)
    br, bz = local(a, dist, a)
    # Above a curved wire B_z is of order (d/a) ln(8a/d) relative (curvature), not zero.
    assert br > 0 and abs(bz) <= 2 * dist / a * math.log(8 * a / dist) * br
    for rho, z in ((a + dist, 0.0), (a, dist), (a - 0.7 * dist, -0.7 * dist)):
        f, r = local(rho, z, a, 1.5), local(rho, z, a, -1.5)
        assert f == (-r[0], -r[1])  # exact sign flip


def test_clamp_is_inactive_away_from_the_wire_and_harmless_at_it():
    """m = 4 a rho / D+^2 is clamped to <= 1 (ellipe is NaN above 1). For d / a >= 1e-7 the
    clamp never changes m; closer, it replaces E(1 - q) by E(1) = 1 with q < 1e-15, and the
    result still matches the reference at rounding level (test above)."""
    a = 1.0
    for dist in (1e-1, 1e-4, 1e-7):
        for th in ANGLES:
            rho, z = a + dist * math.cos(th), dist * math.sin(th)
            assert 4 * a * rho / ((a + rho) ** 2 + z * z) < 1.0
    rho = a * (1 + 2 * EPS)
    assert np.isfinite(local(rho, 0.0, a)).all()


# ----------------------------------------------------------------- 3, 4: axis and near axis


def test_axis_exact_and_near_axis_continuous():
    a, current = 0.4, 3.0
    for z in (0.0, 0.1, -0.7, 5.0):
        br, bz = local(0.0, z, a, current)
        assert br == 0.0
        assert bz == pytest.approx(bs.loop_axis_bz(current, a, z), rel=1e-15)
    for k in range(1, 13):
        rho = a * 10.0 ** -k
        for z in (0.0, 0.13, -0.5):
            br, bz = local(rho, z, a, current)
            rr, rz = bs.loop_local_reference(rho - a, rho, z, a, current)
            assert math.hypot(br - rr, bz - rz) <= 3e-14 * math.hypot(rr, rz), (k, z)


# ------------------------------------------------------- 6: rotation and translation (world)


@pytest.mark.parametrize("c,n,a", [((0, 0, 0), (0, 0, 1), 0.04),
                                   ((3.1, -2.7, 5.3), (0.3, -0.6, 0.74), 0.04),
                                   ((0.2, 0.1, 0.0), (1.0, 1.0, 0.2), 2.5)])
def test_world_coordinates_error_within_reported_precision(c, n, a):
    cs, lp = one_loop(c, n, a)
    v = np.cross(lp.normal, lp.u)
    for dist in [a * 10.0 ** -k for k in range(1, 14)]:
        for th in ANGLES[::3]:
            for psi in (0.0, 1.7):
                radial = math.cos(psi) * lp.u + math.sin(psi) * v
                p = (lp.center_m + (a + dist * math.cos(th)) * radial
                     + dist * math.sin(th) * lp.normal)
                u, rho, z, rhat, nhat = exact_local(p, lp)
                rr, rz = bs.loop_local_reference(u, rho, z, a, 1.0)
                ref = rr * rhat + rz * nhat
                ev = ms.evaluate_bh(p[None, :], cs, 0.0)
                assert ev.status[0] == ms.ST_OK, dist
                err = np.linalg.norm(ev.b[0] - ref) / np.linalg.norm(ref)
                assert err <= ev.precision[0], (dist, err, ev.precision[0])
                assert ev.precision[0] <= 8 * EPS * 3 * a / dist  # bound itself is ~ eps a/d


def test_singular_detection_after_rotation_and_translation():
    """Points computed on the wire of a rotated, translated loop (rounding ~eps) are singular;
    points 1e-12 a away are not."""
    cs, lp = one_loop((3.1, -2.7, 5.3), (0.3, -0.6, 0.74), 0.04)
    v = np.cross(lp.normal, lp.u)
    th = np.linspace(0, 2 * np.pi, 50)
    on = lp.center_m + 0.04 * (np.cos(th)[:, None] * lp.u + np.sin(th)[:, None] * v)
    assert np.all(ms.evaluate_bh(on, cs, 0.0).status == ms.ST_SINGULAR)
    off = on + 0.04e-12 * lp.normal
    ev = ms.evaluate_bh(off, cs, 0.0)
    assert np.all(ev.status == ms.ST_OK) and np.all(np.isfinite(ev.b))
    # ~ mu0 I / (2 pi d) with d = 4e-14 m: about 5e6 T, the true (unclipped) value. These points
    # are ~6.7 m from the origin, so float64 places them only to ~eps|p| = 1.5e-15 m, i.e. 4 % of
    # the intended 4e-14 m offset: that input quantization, not the solver, sets the tolerance.
    assert np.allclose(np.linalg.norm(ev.b, axis=1), MU0 / (2 * math.pi * 0.04e-12), rtol=0.05)


def test_tolerance_is_scaled_by_the_source_not_the_domain():
    """Same loop in a 0.01 m and a 1000 m domain: identical singular set and values."""
    pts = np.array([[0.04 * (1 + 1e-12), 0, 0], [0.04 * (1 + 1e-15), 0, 0], [0.04, 0, 0]])
    res = []
    for half in (0.005, 500.0):
        s = scene_of(loop("l", 1.0, 0.04), domain={"min_m": [-half] * 3, "max_m": [half] * 3})
        r = engine.run(s, SolveRequest.model_validate({
            "samplings": [{"kind": "points", "id": "p", "points_m": pts.tolist()}],
            "quantities": ["B"]}))
        res.append(r.arrays["p.B"])
    assert np.array_equal(res[0], res[1], equal_nan=True)
    assert np.all(np.isfinite(res[0][0])) and np.all(np.isnan(res[0][1:]))


# --------------------------------------------------------------------- 7: superposition


def test_one_singular_turn_does_not_poison_other_points_or_sources():
    s = scene_of(loop("a", 1.0, 0.3), loop("b", 2.0, 0.2, (0, 0, 0.5)))
    cs = current_sources(s)
    pts = np.array([[0.3, 0.0, 0.0], [0.1, 0.1, 0.1], [0.3 + 1e-11, 0.0, 0.0]])
    ev = ms.evaluate_bh(pts, cs, 0.0)
    assert ev.status.tolist() == [ms.ST_SINGULAR, ms.ST_OK, ms.ST_OK]
    assert np.all(np.isnan(ev.b[0])) and np.all(np.isfinite(ev.b[1:]))
    per = ms.source_fields(pts, cs, 0.0)
    assert np.all(np.isnan(per[0][0])) and np.all(np.isfinite(per[1][0]))  # b's own field kept
    total = per[0][1:] + per[1][1:]
    assert np.allclose(ev.b[1:], total, rtol=1e-14, atol=0)


# ---------------------------------------------------------- 8, 9, 11: probe through the API


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def probe(client, scene, point):
    r = client.post(f"{V1}/probe", json={"scene": scene, "point_m": point})
    assert r.status_code == 200, r.text
    return r.json()["magnetic"]


@pytest.mark.parametrize("obj,on,kind", [
    (solenoid(turns=20, radius=0.04, length=0.2), [0.04, 0.0, -0.1], "solenoid"),
    (torus(turns=24, major=0.12, b_w=0.03), [0.15, 0.0, 0.0], "toroid_finite"),
    (loop("l", 1.0, 0.3), [0.3, 0.0, 0.0], "circular_loop"),
])
def test_probe_on_and_near_a_winding(client, obj, on, kind):
    scene = {"objects": [obj]}
    m = probe(client, scene, on)
    assert m["status"] == "singular" and not m["defined"]
    assert m["singular_object_id"] == obj["id"] and m["singular_kind"] == kind
    assert m["singular_tolerance_m"] < 1e-13  # float64-scale, not a broad geometric band
    by = {v["quantity"]: v for v in m["values"]}
    assert by["B"]["value"] is None and by["B"]["status"] == "singular"
    for dist, warn in ((1e-6, False), (1e-11, True)):
        near = list(on)
        near[0] += dist  # radially outward from that turn
        mm = probe(client, scene, near)
        assert mm["status"] == "defined" and mm["singular_object_id"] is None
        b = {v["quantity"]: v for v in mm["values"]}["B"]
        # Dominated by the nearby turn: ~ mu0 I / (2 pi d), I = 1 A per turn.
        assert b["magnitude"] == pytest.approx(MU0 / (2 * math.pi * dist), rel=0.05)
        bound = mm["relative_precision_bound"]
        assert bound is not None and (bound > ms.PRECISION_WARN) == warn


# -------------------------------------------------------------- 10: magnet near its sheet


def test_magnet_quadrature_converges_and_the_jump_tends_to_mu0_m_linearly():
    m, a = 5e5, 0.04
    cs = current_sources(scene_of(magnet(m=m, radius=a)))
    errs = []
    for k in range(1, 7):
        dl = a * 10.0 ** -k
        pts = np.array([[a - dl, 0.0, 0.01], [a + dl, 0.0, 0.01]])
        ev = ms.evaluate_bh(pts, cs, ms.COINCIDENCE_FACTOR * 6.93, ms.MAGNET_RTOL["probe"])
        assert ev.unconverged == 0 and np.all(ev.status == ms.ST_OK)
        jump = ev.b[0] - ev.b[1]
        errs.append(abs(jump[2] / (MU0 * m) - 1))
        assert abs(jump[0]) <= 0.02 * (dl / a) * MU0 * m  # normal B continuous to O(delta)
    assert all(e <= 5 * 10.0 ** -k for k, e in enumerate(errs, start=1))
    assert all(9 < e1 / e2 < 11 for e1, e2 in zip(errs, errs[1:], strict=False))  # first order


# --------------------------------------------------------------------- 11: Ampère paths


def _ampere(objs, path):
    req = ampere.AmpereRequest.model_validate({"paths": [path]})
    return ampere.compute(scene_of(*objs), req, "t", "0").paths[0]


@pytest.mark.parametrize("k", range(2, 13))
def test_ampere_path_approaching_a_wire_stays_evaluable(k):
    d = 10.0 ** -k
    r = _ampere([wire("w", 1.0, (0.1 - d, 0, 0))],
                {"id": "c", "shape": {"type": "circle", "radius_m": 0.1}})
    assert r.status == "verified", (k, r.status)
    assert abs(r.circulation_H_A - 1.0) <= r.tolerance_A
    assert r.min_distance_to_filament_m == pytest.approx(d, rel=1e-3)
    assert r.precision_floor_A is not None and r.precision_floor_A <= r.tolerance_A


def test_ampere_path_too_close_is_reported_honestly_and_on_the_filament_rejected():
    circle = {"id": "c", "shape": {"type": "circle", "radius_m": 0.1}}
    for d in (1e-13, 1e-14):  # float64 floor above the tolerance: never claimed verified
        r = _ampere([wire("w", 1.0, (0.1 - d, 0, 0))], circle)
        assert r.status == "not_converged" and r.circulation_H_A is not None
        assert r.precision_floor_A > r.tolerance_A or not r.converged
    for d in (0.0, 1e-16):
        r = _ampere([wire("w", 1.0, (0.1 - d, 0, 0))], circle)
        assert r.status == "intersects_source" and r.circulation_H_A is None


def test_ampere_path_near_a_loop_wire():
    def path(d):
        return {"id": "r", "shape": {"type": "rectangle", "width_m": 0.2 - d, "height_m": 0.1},
                "center_m": (0.2 + d / 2, 0, 0), "rotation_euler_xyz_rad": (math.pi / 2, 0, 0)}
    for k in range(2, 9):
        r = _ampere([loop("l", 1.0, 0.1)], path(10.0 ** -k))
        assert r.status == "verified" and abs(r.circulation_H_A) <= r.tolerance_A, k
    for k in range(9, 15):  # float64 floor exceeds the 1e-8 A tolerance: not verified
        assert _ampere([loop("l", 1.0, 0.1)], path(10.0 ** -k)).status == "not_converged"
    assert _ampere([loop("l", 1.0, 0.1)], path(0.0)).status == "intersects_source"


# ------------------------------------------------------------------ 12: field lines


def test_field_line_terminates_at_a_filament_without_crossing_it():
    """A synthetic field flowing straight into a filament point (the worst case for the
    integrator): the line ends as source_singularity inside the guard radius, after a bounded
    number of steps, and no vertex reaches the filament."""
    target = np.array([0.3, -0.2, 0.1])

    def field(p):
        return target - p

    def dist(p):
        return np.linalg.norm(p - target, axis=1)

    s = ml.Settings(atol=1e-6, h_max=0.05, h_min=1e-12, max_length=50.0, max_steps=4000,
                    guard_radius=1e-4, stagnation_B=1e-30)
    (tr,) = ml.trace(field, dist, np.array([[1.0, 0.5, 0.4]]), 1.0, np.full(3, -2.0),
                     np.full(3, 2.0), s, False)
    assert tr.reason == "source_singularity"
    dd = dist(tr.points)
    assert dd[-1] <= s.guard_radius and np.all(dd > 0)
    assert tr.steps < 200  # step <= d/2: geometric approach, no runaway refinement


def test_line_seeded_inside_the_guard_of_a_real_loop_ends_immediately():
    cs = current_sources(scene_of(loop("l", 1.0, 0.3)))
    s = ml.Settings(atol=1e-6, h_max=0.05, h_min=1e-12, max_length=50.0, max_steps=4000,
                    guard_radius=1e-4, stagnation_B=1e-30)
    (tr,) = ml.trace(lambda p: ms.evaluate(p, cs, 0.0), lambda p: ms.distance_to_sources(p, cs),
                     np.array([[0.3 + 5e-5, 0.0, 0.0]]), 1.0, np.full(3, -2.0), np.full(3, 2.0),
                     s, True)
    assert tr.reason == "source_singularity" and tr.steps == 0


# ------------------------------------------------- solve-level reporting of the float64 limit


def test_solve_reports_near_filament_precision_only_when_it_matters():
    s = scene_of(loop("l", 1.0, 0.3))

    def warnings_for(points):
        r = engine.run(s, SolveRequest.model_validate({
            "samplings": [{"kind": "points", "id": "p", "points_m": points}],
            "quantities": ["B"]}))
        assert np.all(np.isfinite(r.arrays["p.B"]))
        return [w.en for w in r.header.warnings if "float64" in w.en]

    assert warnings_for([[0.3 + 1e-3, 0, 0], [0.1, 0.2, 0.3]]) == []
    msgs = warnings_for([[0.3 + 1e-11, 0, 0]])
    assert len(msgs) == 1 and "not capped" in msgs[0]
