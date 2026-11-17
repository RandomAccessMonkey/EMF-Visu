"""Magnetic field lines (Phase 3A): direction, closure detection, truncation and numerical
failures. A traced line must follow B, a closed line must really return to its start, and a
line cut by the region, or one that failed numerically, must never be reported as closed."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core import engine
from emf_core.postprocess import magnetic_lines as ml
from emf_core.scene.currents import current_sources
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import magnetostatics as ms
from tests.conftest import loop, scene_of, wire


def request(plane="xy", seeding="planar", quality="normal", extent=4.0):
    u, v = {"xy": ((1, 0, 0), (0, 1, 0)), "xz": ((1, 0, 0), (0, 0, 1))}[plane]
    return SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "heat", "u_dir": u, "v_dir": v,
                       "u_extent_m": extent, "v_extent_m": extent, "nu": 129, "nv": 129}],
        "quantities": ["B"], "quality": quality,
        "field_lines": {"seeding": seeding, "sampling_id": "heat", "base_lines": 8, "levels": 2},
    })


def lines_of(result):
    fl = result.header.field_lines
    pts = result.arrays[fl.array]
    return fl, [(info, pts[info.start: info.start + info.count]) for info in fl.lines]


def assert_follows_b(scene, pts, min_cos=0.999):
    cs = current_sources(scene)
    seg = np.diff(pts, axis=0)
    keep = np.linalg.norm(seg, axis=1) > 0
    mid = 0.5 * (pts[1:] + pts[:-1])[keep]
    b = ms.evaluate(mid, cs, 1e-12)
    t = seg[keep] / np.linalg.norm(seg[keep], axis=1)[:, None]
    cosang = np.einsum("ij,ij->i", t, b / np.linalg.norm(b, axis=1)[:, None])
    assert np.min(cosang) > min_cos


def test_wire_lines_are_closed_circles_following_the_right_hand_rule():
    scene = scene_of(wire("w", 10.0))
    fl, lines = lines_of(engine.run(scene, request()))
    assert fl.field == "B" and fl.lines_stay_in_plane is True and lines
    atol = fl.method.parameters["local_error_tolerance_m"]
    for info, pts in lines:
        assert info.start_reason == info.end_reason == "closed_loop"
        r = np.linalg.norm(pts[:, :2], axis=1)
        # A circle about the wire, within the documented integration tolerance (the last vertex
        # is the closing point on the step's cubic interpolant).
        assert np.ptp(r) <= atol
        assert np.max(np.abs(pts[:, 2])) == 0.0  # stays in the slice exactly
        # Counter-clockwise (positive signed area) seen from +z for current along +z.
        area = 0.5 * np.sum(pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1])
        assert area > 0
        assert info.closure_gap_m is not None and info.closure_gap_m <= 1e-3
        assert_follows_b(scene, pts)


def test_reversed_current_reverses_the_lines():
    fl, lines = lines_of(engine.run(scene_of(wire("w", -10.0)), request()))
    for _, pts in lines:
        area = 0.5 * np.sum(pts[:-1, 0] * pts[1:, 1] - pts[1:, 0] * pts[:-1, 1])
        assert area < 0


def test_lines_cut_by_the_region_are_truncated_not_closed():
    # A flat region (|y| <= 0.1 m) beside the wire: circles wider than 0.1 m leave it.
    lo, hi = np.array([-0.3, -0.1, -1.0]), np.array([0.3, 0.1, 1.0])
    scene = scene_of(wire("w", 10.0, (-0.2, 0.0, 0.0)),
                     domain={"min_m": tuple(lo), "max_m": tuple(hi)})
    req = SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "heat", "u_extent_m": 0.6, "v_extent_m": 0.2,
                       "nu": 121, "nv": 41}],
        "quantities": ["B"],
        "field_lines": {"seeding": "planar", "sampling_id": "heat", "base_lines": 8, "levels": 1}})
    fl, lines = lines_of(engine.run(scene, req))
    reasons = {(i.start_reason, i.end_reason) for i, _ in lines}
    assert ("domain_boundary", "domain_boundary") in reasons
    assert ("closed_loop", "closed_loop") in reasons
    for info, pts in lines:
        if info.end_reason == "domain_boundary":
            assert info.start_reason == "domain_boundary" and info.closure_gap_m is None
            for end in (pts[0], pts[-1]):  # both ends lie on the boundary of the region
                on_face = np.isclose(end, lo, atol=1e-12) | np.isclose(end, hi, atol=1e-12)
                assert on_face[:2].any()
        else:
            assert info.end_reason == "closed_loop"
            assert np.all(pts >= lo) and np.all(pts <= hi)


def test_two_wire_lines_follow_the_superposed_field():
    for i2 in (10.0, -10.0, 4.0):
        scene = scene_of(wire("a", 10.0, (-0.5, 0, 0)), wire("b", i2, (0.5, 0, 0)))
        fl, lines = lines_of(engine.run(scene, request()))
        assert lines
        for info, pts in lines:
            assert info.end_reason in ("closed_loop", "domain_boundary")
            assert_follows_b(scene, pts)


def test_loop_lines_close_around_the_wire_or_are_truncated():
    scene = scene_of(loop("l", 10.0, 0.5))
    fl, lines = lines_of(engine.run(scene, request("xz")))
    assert fl.lines_stay_in_plane is True
    closed = [p for i, p in lines if i.end_reason == "closed_loop"]
    assert closed and all(i.end_reason in ("closed_loop", "domain_boundary") for i, _ in lines)
    for pts in closed:
        # A closed line links the current: it encircles one of the two wire crossings (±a, 0).
        rel = pts[:, [0, 2]] - np.array([0.5 if pts[:, 0].mean() > 0 else -0.5, 0.0])
        winding = np.sum(np.diff(np.unwrap(np.arctan2(rel[:, 1], rel[:, 0])))) / (2 * math.pi)
        assert abs(abs(winding) - 1.0) < 0.01
    for _, pts in lines:
        assert np.max(np.abs(pts[:, 1])) <= 1e-12  # in the meridian plane
        assert_follows_b(scene, pts)
    # On the axis, B points along +z for positive current: lines through the centre go up.
    for _, pts in lines:
        k = np.argmin(np.hypot(pts[:, 0], pts[:, 2]))
        if np.hypot(pts[k, 0], pts[k, 2]) < 0.05 and 0 < k < len(pts) - 1:
            assert pts[k + 1, 2] > pts[k - 1, 2]


def test_3d_lines_of_wire_and_loop():
    for scene in (scene_of(wire("w", 10.0)), scene_of(loop("l", 10.0, 0.5))):
        fl, lines = lines_of(engine.run(scene, request(seeding="spherical")))
        assert lines and fl.seeding == "spherical"
        for info, pts in lines:
            assert info.end_reason in ("closed_loop", "domain_boundary")
            assert_follows_b(scene, pts)


# --- the closure criterion itself, on synthetic fields --------------------------------------


def _settings(max_steps=4000, atol=1e-6):
    return ml.Settings(atol=atol, h_max=0.05, h_min=1e-12, max_length=200.0, max_steps=max_steps,
                       guard_radius=1e-4, stagnation_B=1e-14)


def test_helix_passing_near_its_start_is_not_closed():
    """B = φ̂/ρ + c ẑ: helical lines. After one turn the line passes the start point displaced
    by the pitch along z. With a pitch above the closure tolerance it must not be closed."""
    for c in (2e-3, 5e-4):
        def field(p, c=c):
            rho2 = p[:, 0] ** 2 + p[:, 1] ** 2
            return np.stack([-p[:, 1] / rho2, p[:, 0] / rho2, np.full(len(p), c)], axis=1)

        def dist(p):
            return np.hypot(p[:, 0], p[:, 1])

        seed = np.array([[0.5, 0.0, 0.0]])
        pitch = 2 * math.pi * 0.5 * 0.5 * c / 1.0  # z advance per turn: 2πρ · c / |φ̂/ρ|
        s = _settings()
        (line,) = ml.trace_lines(field, dist, seed, np.array([-1, -1, -1.0]),
                                 np.array([1, 1, 1.0]), s)
        delta = max(ml.CLOSURE_ATOL_FACTOR * s.atol, 0.0)
        assert pitch > delta
        assert line.end_reason != "closed_loop" and line.start_reason != "closed_loop"


def test_numerical_failure_or_step_budget_is_never_closed():
    scene = scene_of(wire("w", 10.0))
    cs = current_sources(scene)

    def field(p):
        return ms.evaluate(p, cs, 1e-12)

    def dist(p):
        return ms.distance_to_sources(p, cs)

    seeds = np.array([[0.5, 0.0, 0.0], [1.2, 0.0, 0.0]])
    lines = ml.trace_lines(field, dist, seeds, np.array([-2, -2, -2.0]), np.array([2, 2, 2.0]),
                           _settings(max_steps=5))
    for ln in lines:
        assert ln.end_reason == "max_length" and ln.closure_gap is None

    def broken(p):
        out = field(p)
        out[p[:, 1] > 0.3] = np.nan  # the field 'fails' in part of the domain
        return out

    lines = ml.trace_lines(broken, dist, seeds, np.array([-2, -2, -2.0]), np.array([2, 2, 2.0]),
                           _settings())
    for ln in lines:
        assert "closed_loop" not in (ln.start_reason, ln.end_reason)
        assert ln.end_reason == "integration_failure"


@pytest.mark.parametrize("quality", ["preview", "normal", "high"])
def test_closed_lines_meet_the_documented_criteria(quality):
    scene = scene_of(wire("a", 10.0, (-0.5, 0, 0)), wire("b", 6.0, (0.5, 0.2, 0)))
    res = engine.run(scene, request(quality=quality))
    fl, lines = lines_of(res)
    atol = fl.method.parameters["local_error_tolerance_m"]
    cs = current_sources(scene)
    for info, pts in lines:
        if info.end_reason != "closed_loop":
            continue
        assert info.closure_gap_m is not None
        assert info.closure_gap_m <= max(1e-3, 50 * atol)
        length = np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1))
        d0 = ms.distance_to_sources(pts[:1], cs)[0]
        assert length >= 2 * d0
        t0 = pts[1] - pts[0]
        t1 = pts[-1] - pts[-2]
        assert np.dot(t0, t1) / (np.linalg.norm(t0) * np.linalg.norm(t1)) > 0.9
