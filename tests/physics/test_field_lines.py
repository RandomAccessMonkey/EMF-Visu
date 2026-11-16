"""Field lines: direction, termination bookkeeping, behaviour near singularities and zeros of
the field, domain boundaries, and accuracy against an independent analytical invariant."""

from __future__ import annotations

import numpy as np
import pytest

from emf_core import engine
from emf_core.postprocess import field_lines as fl
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical.electrostatics import evaluate
from emf_core.units import COULOMB_K
from tests.conftest import charge, scene_of

NUMERICAL_ENDS = {"max_length", "integration_failure"}


def request(seeding="planar", quality="normal", n=97, **fl_kwargs) -> SolveRequest:
    return SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "heat", "u_extent_m": 4, "v_extent_m": 4,
                       "nu": n, "nv": n}],
        "quantities": ["E", "phi"], "quality": quality,
        "field_lines": {"seeding": seeding, "sampling_id": "heat", **fl_kwargs},
    })


def lines_of(result):
    pts = result.arrays["field_lines.points"]
    return [(info, pts[info.start:info.start + info.count])
            for info in result.header.field_lines.lines]


def tangent_alignment(scene, pts, skip=1):
    """cos of the angle between each polyline segment and the exact field at its midpoint."""
    pos = np.array([o.transform.position_m for o in scene.objects if o.source])
    q = np.array([o.source.charge_C for o in scene.objects if o.source])
    seg = pts[skip + 1:len(pts) - skip] - pts[skip:len(pts) - skip - 1]
    mid = 0.5 * (pts[skip + 1:len(pts) - skip] + pts[skip:len(pts) - skip - 1])
    e = evaluate(mid, pos, q, 0.0)[0]
    return np.einsum("ij,ij->i", seg, e) / (np.linalg.norm(seg, axis=1) * np.linalg.norm(e, axis=1))


@pytest.mark.parametrize("seeding", ["planar", "spherical"])
def test_positive_charge_lines_start_on_it_and_leave_through_the_boundary(seeding):
    scene = scene_of(charge("a", 2e-9, (0.3, -0.2, 0.0)))
    r = engine.run(scene, request(seeding))
    lines = lines_of(r)
    assert len(lines) > 0
    for info, pts in lines:
        assert (info.start_reason, info.end_reason) == ("positive_charge", "domain_boundary")
        assert info.start_object_id == "a" and info.end_object_id is None
        assert np.array_equal(pts[0], [0.3, -0.2, 0.0])  # drawn from the charge itself
        assert np.isclose(np.abs(pts[-1]).max(), 2.0, atol=1e-12)  # ends on the domain boundary
        assert np.all(np.abs(pts) <= 2.0 + 1e-12)
        # A single charge has straight radial lines.
        d = pts[1:] - pts[0]
        d /= np.linalg.norm(d, axis=1)[:, None]
        assert np.allclose(d, d[0], atol=1e-9)
        assert np.all(tangent_alignment(scene, pts, skip=0) > 1 - 1e-9)


def test_negative_charge_lines_come_from_the_boundary_and_end_on_it():
    scene = scene_of(charge("n", -1e-9, (0.0, 0.0, 0.0)))
    r = engine.run(scene, request())
    for info, pts in lines_of(r):
        assert (info.start_reason, info.end_reason) == ("domain_boundary", "negative_charge")
        assert info.end_object_id == "n" and np.array_equal(pts[-1], [0, 0, 0])
        assert np.isclose(np.abs(pts[0]).max(), 2.0, atol=1e-12)
        # Stored along +E: towards the negative charge (positive test-charge convention).
        assert np.all(tangent_alignment(scene, pts, skip=0) > 1 - 1e-9)
        assert np.linalg.norm(pts[0]) > np.linalg.norm(pts[-2])


def test_dipole_lines_run_from_plus_to_minus_and_follow_the_analytic_line_equation():
    q, d = 1e-9, 1.0
    scene = scene_of(charge("p", q, (-d / 2, 0, 0)), charge("n", -q, (d / 2, 0, 0)))
    r = engine.run(scene, request())
    fls = r.header.field_lines
    assert fls.lines_stay_in_plane is True and not NUMERICAL_ENDS & set(fls.end_reason_counts)
    connected = 0
    for info, pts in lines_of(r):
        assert info.start_reason in ("positive_charge", "domain_boundary")
        assert info.end_reason in ("negative_charge", "domain_boundary")
        assert np.all(pts[:, 2] == 0.0)  # all charges in the plane: lines stay in it exactly
        assert np.all(tangent_alignment(scene, pts) > 0.999)
        connected += info.start_reason == "positive_charge" and info.end_reason == "negative_charge"
        # Independent reference: along a field line of two collinear charges,
        # q1 cos(theta1) + q2 cos(theta2) is constant (theta_i measured from the axis at charge i).
        inner = pts[2:-2]
        if len(inner) < 3:
            continue
        c = sum(qi * (inner[:, 0] - xi) / np.hypot(inner[:, 0] - xi, inner[:, 1])
                for qi, xi in ((q, -d / 2), (-q, d / 2)))
        assert np.ptp(c) < 2e-4 * q
    assert connected > 0
    # Mirror symmetry of the configuration: as many lines enter the − charge as leave the + one.
    assert fls.end_reason_counts["positive_charge"] == fls.end_reason_counts["negative_charge"]


@pytest.mark.parametrize("q_pos,q_neg,expect", [(2e-9, -1e-9, "net_positive"),
                                                (1e-9, -2e-9, "net_negative")])
def test_net_charge_decides_where_the_excess_lines_go(q_pos, q_neg, expect):
    # Charges close together compared with the domain, so no connecting line leaves the domain.
    scene = scene_of(charge("p", q_pos, (-0.1, 0, 0)), charge("n", q_neg, (0.1, 0, 0)))
    r = engine.run(scene, request("spherical", base_lines=16, levels=3))
    level = [info for info in r.header.field_lines.lines if info.level == 2]
    from_pos = [i for i in level if i.start_reason == "positive_charge"]
    into_neg = [i for i in level if i.end_reason == "negative_charge"]
    assert not NUMERICAL_ENDS & set(r.header.field_lines.end_reason_counts)
    if expect == "net_positive":
        # Every line into the − charge comes from the + charge; half of the + charge's flux
        # (|q−|/q+ = 1/2, Gauss's law) ends there and the rest leaves through the boundary.
        assert all(i.start_reason == "positive_charge" for i in into_neg)
        frac = sum(i.end_reason == "negative_charge" for i in from_pos) / len(from_pos)
        assert frac == pytest.approx(0.5, abs=0.06)
        assert any(i.end_reason == "domain_boundary" for i in from_pos)
    else:
        # All lines of the + charge end on the − charge; the excess arrives from the boundary.
        assert all(i.end_reason == "negative_charge" for i in from_pos)
        frac = sum(i.start_reason == "domain_boundary" for i in into_neg) / len(into_neg)
        assert frac == pytest.approx(0.5, abs=0.06)


def _settings(diag=1.0, **kw):
    base = dict(atol=1e-6 * diag, h_max=diag / 48, h_min=1e-12 * diag, max_length=6 * diag,
                max_steps=2000, guard_radius=0.01, stagnation_E=1e-9)
    return fl.TraceSettings(**{**base, **kw})


def _two_equal(q=1e-9):
    pos = np.array([[-0.5, 0, 0], [0.5, 0, 0]])
    ch = np.array([q, q])
    return (lambda p: evaluate(p, pos, ch, 0.0)[0]), fl.PointSources(pos, ch, COULOMB_K)


def test_line_aimed_at_a_zero_of_the_field_ends_as_a_stagnation_point():
    field, src = _two_equal()
    lo, hi = np.full(3, -2.0), np.full(3, 2.0)
    tr = fl.trace(field, np.array([[-0.49, 0.0, 0.0], [-0.49, 0.02, 0.0]]), 1.0, src, lo, hi,
                  _settings(stagnation_E=1e-9 * COULOMB_K * 2e-9))
    assert tr[0].reason == "stagnation_point"
    assert np.linalg.norm(tr[0].points[-1]) < 1e-4  # the field is zero at the midpoint
    assert tr[1].reason == "domain_boundary"  # a neighbouring line is deflected and escapes
    assert abs(tr[1].points[-1][1]) > 1.0


def test_numerical_endings_are_reported_as_numerical():
    field, src = _two_equal()
    lo, hi = np.full(3, -2.0), np.full(3, 2.0)
    seed = np.array([[-0.5, 0.01, 0.0]])
    assert fl.trace(field, seed, 1.0, src, lo, hi, _settings(max_length=0.05))[0].reason == \
        "max_length"
    assert fl.trace(field, seed, 1.0, src, lo, hi, _settings(max_steps=3))[0].reason == \
        "max_length"
    # A tolerance no step can meet: the step size underflows -> failure, not a physical ending.
    assert fl.trace(field, seed, 1.0, src, lo, hi, _settings(atol=1e-30, h_min=1e-6)
                    )[0].reason == "integration_failure"
    # A field that is not finite at the seed.
    bad = fl.trace(lambda p: np.full_like(p, np.nan), seed, 1.0, src, lo, hi, _settings())
    assert bad[0].reason == "integration_failure"


def test_weak_sink_near_a_strong_source_does_not_swallow_passing_lines():
    # A tiny negative charge inside a strong field: only lines its own field dominates end on it.
    pos = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    ch = np.array([1e-6, -1e-12])
    src = fl.PointSources(pos, ch, COULOMB_K)
    field = lambda p: evaluate(p, pos, ch, 0.0)[0]  # noqa: E731
    seeds = np.array([[0.01, 0.0, 0.0], [0.01 * np.cos(0.004), 0.01 * np.sin(0.004), 0.0]])
    tr = fl.trace(field, seeds, 1.0, src, np.full(3, -2.0), np.full(3, 2.0),
                  _settings(guard_radius=0.02))
    assert tr[0].reason == "negative_charge"  # aimed straight at it
    assert tr[1].reason == "domain_boundary"  # passes within the guard radius, is not captured


def test_end_point_converges_as_the_tolerance_is_tightened():
    scene = scene_of(charge("p", 1e-9, (-0.5, 0, 0)), charge("n", -1e-9, (0.5, 0, 0)))
    pos = np.array([[-0.5, 0, 0], [0.5, 0, 0]])
    ch = np.array([1e-9, -1e-9])
    field = lambda p: evaluate(p, pos, ch, 0.0)[0]  # noqa: E731
    src = fl.PointSources(pos, ch, COULOMB_K)
    # A line leaving the + charge away from the − charge: it curves and exits through the
    # boundary, so its exit point is sensitive to the accumulated integration error.
    seed = pos[0] + 0.01 * np.array([[np.cos(2.6), np.sin(2.6), 0.0]])
    traces = [fl.trace(field, seed, 1.0, src, np.full(3, -2.0), np.full(3, 2.0),
                       _settings(atol=tol, h_max=0.2))[0] for tol in (1e-4, 1e-6, 1e-8, 1e-10)]
    assert all(t.reason == "domain_boundary" for t in traces)
    ends = [t.points[-1] for t in traces]
    errs = [np.linalg.norm(e - ends[-1]) for e in ends[:-1]]
    assert errs[0] > errs[1] > errs[2]
    # Global error stays within a modest multiple of the per-step tolerance.
    for tol, err in zip((1e-4, 1e-6, 1e-8), errs, strict=True):
        assert err < 300 * tol
    assert scene.domain.diagonal_m > 0


def test_guard_radius_follows_the_sampling_resolution_and_never_changes_the_field():
    scene = scene_of(charge("p", 1e-9, (-0.5, 0, 0)), charge("n", -1e-9, (0.5, 0, 0)))
    coarse, fine = engine.run(scene, request(n=33)), engine.run(scene, request(n=129))
    assert coarse.header.field_lines.guard_radius_m == pytest.approx(0.5 * 4 / 32)
    assert fine.header.field_lines.guard_radius_m == pytest.approx(0.5 * 4 / 128)
    without = SolveRequest.model_validate({**request(n=129).model_dump(), "field_lines": None})
    plain = engine.run(scene, without)
    assert np.array_equal(plain.arrays["heat.E"], fine.arrays["heat.E"], equal_nan=True)
    assert np.array_equal(plain.arrays["heat.phi"], fine.arrays["heat.phi"], equal_nan=True)
    # Inside the guard radius the line is the straight segment from the charge to the seed point.
    for info, pts in lines_of(fine):
        if info.start_reason == "positive_charge":
            assert np.linalg.norm(pts[1] - pts[0]) <= fine.header.field_lines.guard_radius_m + 1e-12


def test_planar_seeding_reports_charges_outside_the_plane():
    scene = scene_of(charge("in", 1e-9, (0, 0, 0)), charge("off", -1e-9, (0.5, 0, 0.7)))
    fls = engine.run(scene, request()).header.field_lines
    assert fls.unseeded_object_ids == ["off"] and fls.lines_stay_in_plane is False
    assert all(i.start_object_id == "in" for i in fls.lines)


def test_lines_are_clipped_to_a_non_cubic_domain_and_levels_are_complete_sets():
    scene = scene_of(charge("a", 1e-9, (0.5, 0, 0)),
                     domain={"min_m": (-1, -0.5, -2), "max_m": (3, 0.5, 2)})
    r = engine.run(scene, SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "heat", "center_m": (1, 0, 0),
                       "u_extent_m": 4, "v_extent_m": 1, "nu": 97, "nv": 25}],
        "quantities": ["phi"], "field_lines": {"seeding": "planar", "sampling_id": "heat"}}))
    lo, hi = np.array([-1, -0.5, -2.0]), np.array([3, 0.5, 2.0])
    per_level = {}
    for info, pts in lines_of(r):
        assert np.all(pts >= lo - 1e-12) and np.all(pts <= hi + 1e-12)
        end = pts[-1]
        assert np.any(np.isclose(end, lo, atol=1e-12) | np.isclose(end, hi, atol=1e-12))
        per_level[info.level] = per_level.get(info.level, 0) + 1
    assert per_level == {0: 8, 1: 16, 2: 32}


def test_scene_without_charges_has_no_lines():
    r = engine.run(scene_of(), request())
    assert r.header.field_lines.lines == [] and r.arrays["field_lines.points"].shape == (0, 3)
