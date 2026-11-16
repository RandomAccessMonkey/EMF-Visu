"""Divergence and curl of the point-charge field (Phase 2B-1).

References are independent of the solver: the analytical Jacobian of the Coulomb field written
out in the test, finite differences with error control, surface quadrature of the flux, and
loop quadrature of the circulation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core import engine
from emf_core.postprocess import differential as fd
from emf_core.scene.models import Scene
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import electrostatics as es
from emf_core.units import COULOMB_K, EPS0
from emf_core.verification import references as ref
from tests.conftest import charge, scene_of

CALCULUS = ["E", "D", "div_E", "curl_E", "div_D", "curl_D"]


def points_req(points, quantities=CALCULUS):
    return SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": [tuple(p) for p in points]}],
        "quantities": quantities})


def analytic_jacobian(positions, charges, p):
    """Independent reference: d E_i / d x_j = sum K q (delta_ij - 3 n_i n_j) / r^3."""
    jac = np.zeros((3, 3))
    for pos, q in zip(positions, charges, strict=True):
        d = p - pos
        r = np.linalg.norm(d)
        n = d / r
        jac += COULOMB_K * q * (np.eye(3) - 3 * np.outer(n, n)) / r**3
    return jac


SCENES = {
    "positive": [(2e-9, (0.1, -0.2, 0.05))],
    "negative": [(-3e-9, (-0.4, 0.3, 0.0))],
    "dipole": [(1e-9, (-0.5, 0, 0)), (-1e-9, (0.5, 0, 0))],
    "four": [(2e-9, (-0.8, -0.6, 0)), (-1e-9, (0.8, -0.6, 0)), (1e-9, (0, 0.8, 0.2)),
             (-2e-9, (0.9, 0.9, -0.3))],
}


def build(spec):
    return scene_of(*[charge(f"q{i}", q, pos) for i, (q, pos) in enumerate(spec)])


@pytest.mark.parametrize("name", list(SCENES))
def test_div_and_curl_are_exactly_zero_away_from_the_charges_while_E_is_not(name):
    spec = SCENES[name]
    rng = np.random.default_rng(3)
    pts = rng.uniform(-2, 2, (300, 3))
    r = engine.run(build(spec), points_req(pts))
    e = r.arrays["p.E"]
    assert np.all(np.linalg.norm(e, axis=1) > 0)  # the field is nonzero everywhere sampled
    for q in ("div_E", "div_D"):
        assert np.all(r.arrays[f"p.{q}"] == 0.0)  # exact zero, not round-off
    for q in ("curl_E", "curl_D"):
        assert r.arrays[f"p.{q}"].shape == (300, 3) and np.all(r.arrays[f"p.{q}"] == 0.0)
    units = {a.quantity: a.unit for a in r.header.arrays}
    assert units == {"E": "V/m", "D": "C/m^2", "div_E": "V/m^2", "curl_E": "V/m^2",
                     "div_D": "C/m^3", "curl_D": "C/m^3"}
    # Independent check that the exact zeros are right: the analytical Jacobian is traceless
    # and symmetric to round-off at every point.
    pos = np.array([p for _, p in spec])
    qs = np.array([q for q, _ in spec])
    for p in pts[:50]:
        jac = analytic_jacobian(pos, qs, p)
        scale = np.abs(jac).max()
        assert abs(np.trace(jac)) <= 1e-13 * scale
        assert np.abs(jac - jac.T).max() <= 1e-13 * scale


@pytest.mark.parametrize("name", list(SCENES))
def test_finite_difference_diagnostic_agrees_with_the_exact_zeros(name):
    spec = SCENES[name]
    pos = np.array([p for _, p in spec])
    qs = np.array([q for q, _ in spec])

    def field(p):
        return es.evaluate(p, pos, qs, 0.0)[0]

    rng = np.random.default_rng(5)
    for p in rng.uniform(-2, 2, (20, 3)):
        d = np.linalg.norm(pos - p, axis=1).min()
        est = fd.estimate(field, p, fd.RELATIVE_STEP * d)
        assert est.div_consistent_with_zero and est.curl_consistent_with_zero
        # Scale of the field's derivatives: sum of the individual Coulomb terms' K|q|/r^3 (the
        # terms can cancel in E itself, e.g. for a dipole).
        r = np.linalg.norm(pos - p, axis=1)
        jac_scale = float(np.sum(COULOMB_K * np.abs(qs) / r**3))
        assert est.div_uncertainty < 1e-5 * jac_scale  # the check is sharp, not vacuous
        assert np.all(est.curl_uncertainty < 1e-5 * jac_scale)


def test_finite_difference_method_recovers_known_nonzero_divergence_and_curl():
    # Validates the diagnostic itself on fields whose operators are not zero.
    def source(p):  # F = (x, y, z) + a quadratic term: div = 3 + 2x, curl = 0
        return np.stack([p[:, 0] + p[:, 0] ** 2, p[:, 1], p[:, 2]], axis=1)

    def vortex(p):  # F = (-y, x, 0) * (1 + z^2): div = 0, curl = (-2xz, -2yz, 2(1 + z^2))
        s = 1 + p[:, 2] ** 2
        return np.stack([-p[:, 1] * s, p[:, 0] * s, np.zeros(len(p))], axis=1)

    p = np.array([0.3, -0.7, 0.4])
    errs = []
    for h in (1e-1, 5e-2, 2.5e-2):
        a = fd.estimate(source, p, h)
        b = fd.estimate(vortex, p, h)
        assert abs(a.div - (3 + 2 * 0.3)) <= a.div_uncertainty + 1e-12
        exact_curl = np.array([-2 * 0.3 * 0.4, 2 * 0.7 * 0.4, 2 * (1 + 0.16)])
        assert np.all(np.abs(b.curl - exact_curl) <= b.curl_uncertainty + 1e-12)
        assert abs(b.div) <= b.div_uncertainty
        assert not b.curl_consistent_with_zero  # a real curl is not reported as zero
        errs.append(abs(a.div - 3.6))
    # Polynomial of degree 2: central differences are exact up to round-off.
    assert max(errs) < 1e-12

    def wavy(p):  # div = cos(x) + cos(y) + cos(z), exercises the truncation estimate
        return np.sin(p)

    true = np.cos(p).sum()
    e1 = abs(fd.estimate(wavy, p, 0.2).div - true)
    e2 = abs(fd.estimate(wavy, p, 0.1).div - true)
    assert e1 / e2 == pytest.approx(16, rel=0.2)  # Richardson: fourth order
    assert e2 <= fd.estimate(wavy, p, 0.1).div_uncertainty


def test_behaviour_near_but_not_at_a_charge():
    scene = scene_of(charge("a", 1e-9, (0.0, 0.0, 0.0)))
    for r_ in (1e-3, 1e-6, 1e-9, 1e-10):
        res = engine.run(scene, points_req([(0, r_, 0)]))
        assert res.arrays["p.E"][0, 1] == pytest.approx(COULOMB_K * 1e-9 / r_**2, rel=1e-12)
        assert res.arrays["p.div_E"][0] == 0.0 and np.all(res.arrays["p.curl_E"][0] == 0.0)
        assert res.arrays["p.div_D"][0] == 0.0 and np.all(res.arrays["p.curl_D"][0] == 0.0)


def test_behaviour_at_a_charge_is_not_evaluated_and_counted():
    scene = scene_of(charge("a", 1e-9, (0.2, 0.1, 0.0)), charge("b", -1e-9, (1, 0, 0)))
    res = engine.run(scene, points_req([(0.2, 0.1, 0.0), (0.5, 0.5, 0.5)]))
    for q in CALCULUS:
        a = res.arrays[f"p.{q}"]
        assert np.all(np.isnan(a[0])) and np.all(np.isfinite(a[1]))
    stats = {e.quantity: e.stats for e in res.header.arrays}
    assert stats["div_E"].non_finite_count == 1 and stats["div_E"].min == stats["div_E"].max == 0


def test_point_sources_carry_exact_delta_weights_and_slice_positions():
    objs = [charge("p", 2e-9, (0.3, 0.0, 0.0)), charge("n", -1e-9, (-0.4, 0.2, 0.7)),
            charge("zero", 0.0, (1, 1, 1)), charge("off", 5e-9, (0, 0, 0), enabled=False)]
    scene = scene_of(*objs)
    req = SolveRequest.model_validate({
        "samplings": [
            {"kind": "plane_grid", "id": "xy", "center_m": (0, 0, 0.0), "u_extent_m": 4,
             "v_extent_m": 4, "nu": 5, "nv": 5},
            {"kind": "plane_grid", "id": "xz", "center_m": (0, 0.2, 0), "u_dir": (1, 0, 0),
             "v_dir": (0, 0, 1), "u_extent_m": 4, "v_extent_m": 4, "nu": 5, "nv": 5}],
        "quantities": ["phi"]})
    h = engine.run(scene, req).header
    by = {s.object_id: s for s in h.point_sources}
    assert set(by) == {"p", "n"}  # zero and disabled charges are no sources
    assert by["p"].div_E_weight_V_m == 2e-9 / EPS0 and by["p"].div_D_weight_C == 2e-9
    assert by["n"].div_E_weight_V_m == -1e-9 / EPS0 and by["n"].div_D_weight_C == -1e-9
    assert by["n"].position_m == [-0.4, 0.2, 0.7]
    # Signed distances along u x v: xy -> +z, xz -> x × z = -y.
    assert by["p"].plane_distance_m["xy"] == 0.0 and by["p"].in_plane["xy"] is True
    assert by["n"].plane_distance_m["xy"] == pytest.approx(0.7) and by["n"].in_plane["xy"] is False
    assert by["p"].plane_distance_m["xz"] == pytest.approx(0.2) and by["p"].in_plane["xz"] is False
    assert abs(by["n"].plane_distance_m["xz"]) < 1e-15 and by["n"].in_plane["xz"] is True
    assert h.in_plane_tolerance_m == pytest.approx(1e-9 * math.sqrt(48))
    assert not hasattr(by["p"], "curl_weight")  # a point charge has no rotational weight


def _box_flux(field, lo, hi, n=40):
    """Outward flux through the faces of an axis-aligned box by Gauss–Legendre quadrature."""
    x, w = np.polynomial.legendre.leggauss(n)
    total = 0.0
    for axis in range(3):
        a, b = [k for k in range(3) if k != axis]
        ua = lo[a] + (x + 1) / 2 * (hi[a] - lo[a])
        ub = lo[b] + (x + 1) / 2 * (hi[b] - lo[b])
        wa, wb = np.meshgrid(w * (hi[a] - lo[a]) / 2, w * (hi[b] - lo[b]) / 2, indexing="ij")
        ga, gb = np.meshgrid(ua, ub, indexing="ij")
        for side, sign in ((hi[axis], 1.0), (lo[axis], -1.0)):
            pts = np.zeros((n * n, 3))
            pts[:, a], pts[:, b], pts[:, axis] = ga.ravel(), gb.ravel(), side
            total += sign * float(np.sum(field(pts)[:, axis] * (wa * wb).ravel()))
    return total


@pytest.mark.parametrize("lo,hi,inside", [
    ((-1.0, -1.0, -1.0), (1.0, 1.0, 1.0), {"p", "n", "m"}),
    ((0.1, -1.0, -1.0), (1.5, 1.0, 1.0), {"p"}),
    ((-1.5, -0.5, -0.5), (-0.1, 0.5, 0.5), {"n"}),
    ((1.2, 1.2, 1.2), (1.9, 1.9, 1.9), set()),
])
def test_volume_integral_of_divergence_is_the_enclosed_weight(lo, hi, inside):
    spec = {"p": (3e-9, (0.4, 0.1, 0.0)), "n": (-1e-9, (-0.6, 0.0, 0.2)),
            "m": (-0.5e-9, (0.0, 0.0, -0.6))}
    scene = scene_of(*[charge(k, q, pos) for k, (q, pos) in spec.items()])
    h = engine.run(scene, points_req([(1.95, 1.95, 1.95)], ["phi"])).header
    lo_a, hi_a = np.array(lo), np.array(hi)

    def contains(p):
        return bool(np.all(p > lo_a) and np.all(p < hi_a))

    q_enc = sum(spec[k][0] for k in inside)
    weight_e = es.enclosed_source_weight(h.point_sources, contains, "E")
    weight_d = es.enclosed_source_weight(h.point_sources, contains, "D")
    # Exactly the enclosed charges, with their exact weights.
    assert weight_e == pytest.approx(q_enc / EPS0, rel=1e-15, abs=1e-30)
    assert weight_d == pytest.approx(q_enc, rel=1e-15, abs=1e-30)
    # Independent: the outward flux of the exact field through the box surface.
    pos = np.array([v[1] for v in spec.values()])
    qs = np.array([v[0] for v in spec.values()])

    def e_field(p):
        return es.evaluate(p, pos, qs, 0.0)[0]

    scale = sum(abs(q) for q in qs) / EPS0
    flux_e = _box_flux(e_field, lo_a, hi_a)
    assert flux_e == pytest.approx(weight_e, abs=1e-4 * scale)
    flux_d = _box_flux(lambda p: EPS0 * e_field(p), lo_a, hi_a)
    assert flux_d == pytest.approx(weight_d, abs=1e-4 * scale * EPS0)


def _circulation(field, centre, u, v, radius, n=256):
    t = 2 * np.pi * np.arange(n) / n
    pts = centre + radius * (np.cos(t)[:, None] * u + np.sin(t)[:, None] * v)
    tangent = radius * (-np.sin(t)[:, None] * u + np.cos(t)[:, None] * v)
    return float(np.sum(np.einsum("ij,ij->i", field(pts), tangent)) * 2 * np.pi / n)


def test_distributional_curl_is_zero_on_loops_around_and_through_charge_positions():
    spec = SCENES["four"]
    pos = np.array([p for _, p in spec])
    qs = np.array([q for q, _ in spec])

    def field(p):
        return es.evaluate(p, pos, qs, 0.0)[0]

    rng = np.random.default_rng(11)
    for c in pos:
        for radius in (1e-3, 0.05, 0.3):
            for _ in range(4):
                u = rng.normal(size=3)
                u /= np.linalg.norm(u)
                v = np.cross(u, rng.normal(size=3))
                v /= np.linalg.norm(v)
                # Loops centred on the charge (in a plane through it) and loops displaced so
                # that the charge sits just off the loop's plane.
                for shift in (0.0, 0.3 * radius):
                    centre = c + shift * np.cross(u, v)
                    circ = _circulation(field, centre, u, v, radius)
                    e_scale = np.abs(field((centre + radius * u)[None])).max() * 2 * np.pi * radius
                    assert abs(circ) <= 1e-9 * e_scale


def test_2d_slice_shows_the_full_3d_operators_not_in_plane_derivatives():
    q = 1e-9
    scene = scene_of(charge("a", q, (0.0, 0.0, 0.0)))
    n = 161
    req = SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "s", "u_extent_m": 2, "v_extent_m": 2,
                       "nu": n, "nv": n, "quantities": CALCULUS}],
        "quantities": ["phi"]})
    res = engine.run(scene, req)
    div = res.arrays["s.div_E"]
    defined = np.isfinite(div)
    assert defined.sum() == n * n - 1  # only the sample on the charge is not evaluated
    assert np.all(div[defined] == 0.0)
    assert res.arrays["s.curl_E"].shape == (n, n, 3)
    # What a 2D-only operator would show instead: dEx/dx + dEy/dy from the same samples is
    # far from zero, and equals the analytical in-plane value -K q / r^3 (the missing term
    # dEz/dz = +K q / r^3 restores zero in 3D).
    e = res.arrays["s.E"].astype(np.float64)
    hgrid = 2 / (n - 1)
    div2d = (np.gradient(e[..., 0], hgrid, axis=1) + np.gradient(e[..., 1], hgrid, axis=0))
    pts = engine.run(scene, req).header.samplings[0]
    xs = np.linspace(-1, 1, n)
    xx, yy = np.meshgrid(xs, xs, indexing="xy")
    rr = np.hypot(xx, yy)
    ring = (rr > 0.5) & (rr < 0.9)
    expected = -COULOMB_K * q / rr[ring] ** 3
    # Second-order differences on a 0.0125 m grid: relative error ~ 4 h^2 / r^2 <= 2.5e-3.
    assert np.allclose(div2d[ring], expected, rtol=5e-3)
    assert np.all(np.abs(div2d[ring]) > 5.0)
    assert pts["id"] == "s"


def test_dipole_reference_values_are_unchanged():
    # Phase 2A references still hold with the new quantities requested alongside.
    q, d = 1e-9, 0.4
    scene = scene_of(charge("p", q, (-d / 2, 0, 0)), charge("n", -q, (d / 2, 0, 0)))
    res = engine.run(scene, points_req([(1.3, 0, 0), (0, 0.9, 0)]))
    assert res.arrays["p.E"][0, 0] == pytest.approx(ref.dipole_e_on_axis(q, d, 1.3), rel=1e-12)
    assert res.arrays["p.E"][1, 0] == pytest.approx(ref.dipole_e_on_bisector(q, d, 0.9),
                                                    rel=1e-12)


def test_scene_round_trip_keeps_differential_quantities_optional():
    scene = Scene.model_validate({"objects": [charge("a", 1e-9, (0, 0, 0))]})
    res = engine.run(scene, points_req([(1, 0, 0)], ["E", "phi"]))
    assert sorted(res.arrays) == ["p.E", "p.phi"]
