"""Validation of the analytical point-charge solver against independent closed forms and
against the integral/differential laws it must satisfy."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core.solvers.analytical import PointChargeVacuumSolver
from emf_core.solvers.analytical.electrostatics import evaluate
from emf_core.units import C0, EPS0, MU0
from emf_core.verification import references as ref
from tests.conftest import charge, points_request, scene_of

SOLVER = PointChargeVacuumSolver()
RTOL = 1e-12


def fields(scene, pts):
    r = SOLVER.solve(scene, points_request(pts, "E", "phi", "D"))
    return r.arrays["p.E"], r.arrays["p.phi"], r.arrays["p.D"]


def test_constants_are_consistent():
    assert 1.0 / math.sqrt(EPS0 * MU0) == pytest.approx(C0, rel=1e-9)


@pytest.mark.parametrize("q", [1e-9, -3.5e-6])
@pytest.mark.parametrize("r", [1e-3, 0.37, 12.0])
def test_single_charge_matches_closed_form(q, r):
    direction = np.array([1.0, -2.0, 0.5])
    direction /= np.linalg.norm(direction)
    origin = np.array([0.3, -0.1, 0.7])
    e, phi, _ = fields(scene_of(charge("a", q, tuple(origin))), [tuple(origin + r * direction)])
    assert np.linalg.norm(e[0]) == pytest.approx(ref.point_charge_e_magnitude(q, r), rel=RTOL)
    assert phi[0] == pytest.approx(ref.point_charge_phi(q, r), rel=RTOL)
    # Positive test-charge convention: E points away from a positive charge.
    assert np.dot(e[0], direction) * q > 0
    assert np.allclose(np.cross(e[0], direction), 0, atol=1e-9 * np.linalg.norm(e[0]))


def test_dipole_axis_and_bisector():
    q, d = 2e-9, 0.4
    s = scene_of(charge("p", q, (-d / 2, 0, 0)), charge("n", -q, (d / 2, 0, 0)))
    e, phi, _ = fields(s, [(1.3, 0, 0), (0, 0.9, 0), (0, 0, -2.0)])
    assert e[0, 0] == pytest.approx(ref.dipole_e_on_axis(q, d, 1.3), rel=RTOL)
    assert e[1, 0] == pytest.approx(ref.dipole_e_on_bisector(q, d, 0.9), rel=RTOL)
    assert e[2, 0] == pytest.approx(ref.dipole_e_on_bisector(q, d, 2.0), rel=RTOL)
    assert abs(e[1, 1]) < 1e-12 * abs(e[1, 0]) and abs(e[0, 1]) == 0.0
    assert phi[1] == 0.0 and phi[2] == 0.0  # symmetry plane is the zero equipotential


def test_dipole_far_field_falls_as_inverse_cube():
    q, d = 1e-9, 0.01
    s = scene_of(charge("p", q, (-d / 2, 0, 0)), charge("n", -q, (d / 2, 0, 0)))
    e, _, _ = fields(s, [(0, 10.0, 0), (0, 20.0, 0)])
    assert e[0, 0] / e[1, 0] == pytest.approx(8.0, rel=1e-5)


def test_superposition_is_linear():
    rng = np.random.default_rng(1)
    pts = [tuple(p) for p in rng.uniform(-2, 2, (50, 3))]
    a, b = charge("a", 1e-9, (0.2, 0.1, -0.3)), charge("b", -4e-9, (-0.7, 0.5, 0.2))
    ea, pa, _ = fields(scene_of(a), pts)
    eb, pb, _ = fields(scene_of(b), pts)
    eab, pab, _ = fields(scene_of(a, b), pts)
    assert np.allclose(eab, ea + eb, rtol=1e-13, atol=0)
    assert np.allclose(pab, pa + pb, rtol=1e-13, atol=0)


def test_constitutive_relation_in_vacuum():
    e, _, d = fields(scene_of(charge("a", 1e-9, (0, 0, 0))), [(0.3, 0.4, 0.5)])
    assert np.array_equal(d, EPS0 * e)


@pytest.mark.parametrize("centre,expected_enclosed", [
    ((0.0, 0.0, 0.0), 3e-9 - 1e-9),   # both charges inside
    ((0.9, 0.0, 0.0), -1e-9),         # only the negative charge inside
    ((0.0, 3.0, 0.0), 0.0),           # no charge inside: zero net flux, non-zero field
])
def test_gauss_law_flux_through_sphere(centre, expected_enclosed):
    s = scene_of(charge("a", 3e-9, (-0.2, 0.1, 0.0)), charge("b", -1e-9, (0.6, 0.0, 0.1)))
    radius = 0.75 if centre != (0.9, 0.0, 0.0) else 0.5
    nodes, w = ref.sphere_quadrature(48, 96)
    pts = np.asarray(centre) + radius * nodes
    e, _, _ = fields(s, [tuple(p) for p in pts])
    flux = float(np.sum(np.einsum("ij,ij->i", e, nodes) * w) * radius**2)
    scale = 3e-9 / EPS0
    assert flux == pytest.approx(expected_enclosed / EPS0, abs=1e-6 * scale)
    assert np.linalg.norm(e, axis=1).min() > 0  # the field itself is non-zero everywhere


def _phi(pos, q, pts):
    return evaluate(np.asarray(pts, float), pos, q, 0.0)[1]


def test_e_is_minus_grad_phi_with_second_order_convergence():
    pos = np.array([[0.1, -0.2, 0.3], [-0.5, 0.4, 0.0]])
    q = np.array([2e-9, -1e-9])
    p = np.array([0.8, 0.7, -0.6])
    e = evaluate(p[None], pos, q, 0.0)[0][0]
    errs = []
    for h in (1e-2, 5e-3, 2.5e-3):
        grad = np.array([(_phi(pos, q, [p + h * ax])[0] - _phi(pos, q, [p - h * ax])[0]) / (2 * h)
                         for ax in np.eye(3)])
        errs.append(np.linalg.norm(e + grad) / np.linalg.norm(e))
    assert errs[-1] < 1e-4
    # Central differences are O(h^2): halving h must divide the error by ~4.
    assert errs[0] / errs[1] == pytest.approx(4.0, rel=0.05)
    assert errs[1] / errs[2] == pytest.approx(4.0, rel=0.05)


def test_field_is_curl_free_and_divergence_free_away_from_charges():
    pos, q = np.array([[0.0, 0.0, 0.0], [0.5, 0.2, -0.1]]), np.array([1e-9, 2e-9])
    p, h = np.array([1.1, -0.9, 0.8]), 1e-3

    def e_at(x):
        return evaluate(np.asarray(x)[None], pos, q, 0.0)[0][0]

    jac = np.array([(e_at(p + h * ax) - e_at(p - h * ax)) / (2 * h) for ax in np.eye(3)]).T
    scale = np.linalg.norm(e_at(p)) / np.linalg.norm(p)
    curl = np.array([jac[2, 1] - jac[1, 2], jac[0, 2] - jac[2, 0], jac[1, 0] - jac[0, 1]])
    assert np.linalg.norm(curl) < 1e-5 * scale
    assert abs(np.trace(jac)) < 1e-5 * scale


def test_singular_points_are_masked_and_reported():
    s = scene_of(charge("a", 1e-9, (0.5, 0, 0)))
    r = SOLVER.solve(s, points_request([(0.5, 0, 0), (0, 0, 0)]))
    assert np.all(np.isnan(r.arrays["p.E"][0])) and np.isnan(r.arrays["p.phi"][0])
    assert np.all(np.isfinite(r.arrays["p.E"][1]))
    entry = next(a for a in r.header.arrays if a.name == "p.E")
    assert entry.stats.non_finite_count == 1
    assert any("singular" in w.en for w in r.header.warnings)


def test_empty_scene_gives_zero_field():
    r = SOLVER.solve(scene_of(), points_request([(0.1, 0.2, 0.3)]))
    assert np.all(r.arrays["p.E"] == 0) and np.all(r.arrays["p.phi"] == 0)
    assert r.header.model_context.has_free_charge is False
