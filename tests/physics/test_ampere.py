"""Phase 3B: Ampère's circuital law, ∮H·dl = I_free,enclosed, with Γ_H from adaptive quadrature
of the solver's H field and I_free,enclosed from independent signed crossings. A: path
geometry; B: wires; C: loops and solenoids; D: toroids; E: magnets; F: sources on or near the
path; G: numerics, invariance and fingerprints."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core import ampere
from emf_core.scene.models import Scene
from emf_core.units import MU0
from tests.conftest import charge, loop, magnet, scene_of, solenoid, torus, wire

HALF_PI = math.pi / 2


def run(objs, *paths, **scene_extra) -> list[ampere.PathResult]:
    scene = objs if isinstance(objs, Scene) else scene_of(*objs, **scene_extra)
    req = ampere.AmpereRequest.model_validate({"paths": list(paths)})
    return ampere.compute(scene, req, "test", "0").paths


def circle(pid="c", r=0.1, center=(0, 0, 0), rot=(0, 0, 0), reversed_=False, rtol=1e-4):
    return {"id": pid, "shape": {"type": "circle", "radius_m": r}, "center_m": center,
            "rotation_euler_xyz_rad": rot, "reversed": reversed_, "rtol": rtol}


def rect(pid="r", w=0.2, h=0.1, center=(0, 0, 0), rot=(0, 0, 0), reversed_=False):
    return {"id": pid, "shape": {"type": "rectangle", "width_m": w, "height_m": h},
            "center_m": center, "rotation_euler_xyz_rad": rot, "reversed": reversed_}


def poly(pid="p", verts=(), closed=True, center=(0, 0, 0), rot=(0, 0, 0)):
    return {"id": pid, "shape": {"type": "polygon", "vertices_m": list(verts), "closed": closed},
            "center_m": center, "rotation_euler_xyz_rad": rot}


def assert_verified(r: ampere.PathResult, expected: float) -> None:
    assert r.status == "verified", (r.status, r.circulation_H_A, r.enclosure)
    assert r.enclosure is not None and r.enclosure.value_A == pytest.approx(expected, abs=1e-12)
    assert r.circulation_H_A == pytest.approx(expected, rel=1e-4, abs=1e-8)
    assert r.converged


# ------------------------------------------------------------------- A: path geometry


def test_circle_geometry_normal_and_orientation():
    (r,) = run([wire("w", 1.0, (5, 5, 0))], circle(r=0.2, center=(0.1, 0, 0)))
    assert r.valid and np.allclose(r.normal, [0, 0, 1])
    assert r.perimeter_m == pytest.approx(2 * math.pi * 0.2, rel=1e-12)
    assert r.area_m2 == pytest.approx(math.pi * 0.04, rel=1e-12)
    pl = np.asarray(r.polyline_m)
    # Counter-clockwise about +z (right-hand rule with the normal).
    d = pl[1] - pl[0]
    assert np.cross(pl[0] - [0.1, 0, 0], d)[2] > 0
    (rv,) = run([wire("w", 1.0, (5, 5, 0))], circle(r=0.2, reversed_=True))
    assert np.allclose(rv.normal, [0, 0, -1])


def test_rectangle_and_polygon_area_perimeter():
    (r,) = run([wire("w", 1.0, (5, 5, 0))], rect(w=0.3, h=0.1))
    assert r.perimeter_m == pytest.approx(0.8) and r.area_m2 == pytest.approx(0.03)
    tri = [(0, 0, 0), (0.3, 0, 0), (0, 0.4, 0)]
    (p,) = run([wire("w", 1.0, (5, 5, 0))], poly(verts=tri))
    assert p.perimeter_m == pytest.approx(1.2) and p.area_m2 == pytest.approx(0.06)
    # Clockwise vertex order flips the normal (right-hand rule follows the traversal).
    (pc,) = run([wire("w", 1.0, (5, 5, 0))], poly(verts=tri[::-1]))
    assert np.allclose(pc.normal, [0, 0, -1])


@pytest.mark.parametrize("verts,closed,word", [
    ([(0, 0, 0), (0.1, 0, 0), (0.1, 0.1, 0)], False, "closed"),
    ([(0, 0, 0), (0.1, 0, 0)], True, "three"),
    ([(0, 0, 0), (0.1, 0, 0), (0.2, 0, 0)], True, "collinear"),
    ([(0, 0, 0), (0.1, 0.1, 0), (0.1, 0, 0), (0, 0.1, 0)], True, "intersect"),
    ([(0, 0, 0), (0.1, 0, 0), (0.1, 0.1, 0.05), (0, 0.1, 0)], True, "planar"),
    ([(0, 0, 0), (0, 0, 0), (0.1, 0, 0), (0, 0.1, 0)], True, "zero-length"),
])
def test_invalid_paths_are_rejected_with_a_reason(verts, closed, word):
    (r,) = run([wire("w", 1.0, (5, 5, 0))], poly(verts=verts, closed=closed))
    assert not r.valid and r.status == "invalid" and r.circulation_H_A is None
    assert any(word in reason.en for reason in r.invalid_reasons), r.invalid_reasons


def test_bad_parameters_are_schema_errors():
    for bad in (circle(r=0.0), circle(rtol=0.5), rect(w=-1)):
        with pytest.raises(ValidationError):
            ampere.AmpereRequest.model_validate({"paths": [bad]})
    with pytest.raises(ValidationError):
        ampere.AmpereRequest.model_validate({"paths": []})


# --------------------------------------------------------------------------- B: wires


def test_wire_enclosed_outside_and_reversed():
    w = [wire("w", 10.0)]
    assert_verified(run(w, circle(r=0.1))[0], 10.0)
    assert_verified(run(w, circle(r=0.1, center=(0.03, 0.02, 0)))[0], 10.0)  # off-centre
    assert_verified(run(w, circle(r=0.1, reversed_=True))[0], -10.0)
    assert_verified(run(w, circle(r=0.05, center=(0.2, 0, 0)))[0], 0.0)  # not enclosed
    assert_verified(run(w, rect(w=0.3, h=0.05))[0], 10.0)
    assert_verified(run(w, poly(verts=[(-0.1, -0.1, 0), (0.2, -0.05, 0), (0.0, 0.15, 0)]))[0],
                    10.0)


def test_several_wires_signed_sum():
    objs = [wire("a", 10.0, (0.02, 0, 0)), wire("b", -4.0, (-0.03, 0.01, 0)),
            wire("c", 7.0, (0.4, 0, 0))]
    (r,) = run(objs, circle(r=0.1))
    assert_verified(r, 6.0)
    ids = {c.object_id: c.sign for c in r.enclosure.crossings}
    assert ids == {"a": 1, "b": 1}  # both cross along +n; the sign of I is in the value


def test_tilted_wire_and_tilted_path():
    tilt = (0.4, -0.3, 0.0)
    assert_verified(run([wire("w", 5.0, rot=tilt)], circle(r=0.1))[0], 5.0)
    assert_verified(run([wire("w", 5.0)], circle(r=0.1, rot=(0.5, 0.2, 0)))[0], 5.0)
    # Wire parallel to the path plane never crosses its surface.
    assert_verified(run([wire("w", 5.0, (0, 0, 0.05), rot=(HALF_PI, 0, 0))],
                        circle(r=0.1))[0], 0.0)


def test_circulation_independent_of_shape():
    w = [wire("w", 3.0, (0.01, 0.02, 0))]
    vals = [run(w, p)[0].circulation_H_A for p in (
        circle(r=0.1), rect(w=0.25, h=0.12), poly(verts=[(-0.1, -0.1, 0), (0.2, -0.1, 0),
                                                         (0.05, 0.0, 0), (0.2, 0.1, 0),
                                                         (-0.1, 0.1, 0)]))]
    assert np.allclose(vals, 3.0, rtol=1e-4)


# --------------------------------------------------------------- C: loops and solenoids


def test_loop_linked_and_unlinked():
    lp = [loop("l", 2.0, 0.1)]
    # A rectangle in the xz plane threading the wire at x = 0.1: linked once.
    linked = rect(w=0.08, h=0.1, center=(0.1, 0, 0), rot=(HALF_PI, 0, 0))
    (r,) = run(lp, linked)
    assert abs(r.enclosure.value_A) == 2.0
    assert_verified(r, r.enclosure.value_A)
    # Same rectangle wholly inside the loop (does not cross the wire): zero.
    assert_verified(run(lp, rect(w=0.06, h=0.1, center=(0.0, 0, 0), rot=(HALF_PI, 0, 0)))[0],
                    0.0)
    # Path coaxial with the loop in its own plane, radius larger: zero linkage.
    assert_verified(run(lp, circle(r=0.2))[0], 0.0)


def test_solenoid_paths():
    s = [solenoid(turns=20, current=1.0, length=0.2, radius=0.04)]
    # Rectangle spanning the whole winding on one side: N I.
    whole = rect(w=0.06, h=0.3, center=(0.04, 0, 0), rot=(-HALF_PI, 0, 0))
    (r,) = run(s, whole)
    assert abs(r.enclosure.value_A) == 20.0
    assert_verified(r, r.enclosure.value_A)
    # Sub-path enclosing a part of the winding: counts its turns exactly.
    part = rect(w=0.06, h=0.12, center=(0.04, 0, 0), rot=(-HALF_PI, 0, 0))
    (p,) = run(s, part)
    zs = np.linspace(-0.1, 0.1, 20)
    assert abs(p.enclosure.value_A) == float(np.count_nonzero(np.abs(zs) < 0.06))
    assert_verified(p, p.enclosure.value_A)
    # Reversal of the current flips the result, not the geometry.
    (rv,) = run([solenoid(turns=20, current=-1.0, length=0.2, radius=0.04)], whole)
    assert rv.enclosure.value_A == -r.enclosure.value_A


def test_path_through_solenoid_bore_links_nothing():
    assert_verified(run([solenoid()], circle(r=0.02, center=(0, 0, 0.003)))[0], 0.0)


# ------------------------------------------------------------------------------ D: toroids


def test_finite_toroid_paths():
    t = [torus(turns=24, current=1.0)]
    assert_verified(run(t, circle(r=0.12))[0], 24.0)  # coaxial through the winding
    assert_verified(run(t, circle(r=0.05))[0], 0.0)  # hole
    assert_verified(run(t, circle(r=0.2))[0], 0.0)  # around the whole toroid: net zero
    # Small loop around one leg of the winding cross-section: links nothing net either.
    assert_verified(run(t, rect(w=0.1, h=0.1, center=(0.12, 0, 0), rot=(HALF_PI, 0, 0)))[0],
                    0.0)


def test_ideal_toroid_coaxial_and_unsupported():
    t = [torus(model="toroid_ideal", turns=24, current=1.0, mu_r=500.0)]
    assert_verified(run(t, circle(r=0.12))[0], 24.0)
    assert_verified(run(t, circle(r=0.13, center=(0, 0, 0.01)))[0], 24.0)
    assert_verified(run(t, circle(r=0.05))[0], 0.0)
    assert_verified(run(t, circle(r=0.3))[0], 0.0)
    (r,) = run(t, rect(w=0.1, h=0.1, center=(0.12, 0, 0), rot=(HALF_PI, 0, 0)))
    assert r.status == "unsupported" and not r.enclosure.available


def test_ideal_toroid_circulation_of_b_shows_mu_r():
    mu_r = 300.0
    (r,) = run([torus(model="toroid_ideal", turns=24, current=1.0, mu_r=mu_r)], circle(r=0.12))
    assert r.circulation_B_T_m == pytest.approx(MU0 * mu_r * 24.0, rel=1e-4)
    assert r.crosses_material


# ------------------------------------------------------------------------------ E: magnets


def test_magnet_has_no_free_current_but_bound_current():
    m, length = 5e5, 0.08
    # Rectangle crossing the side wall, spanning the magnet's length.
    path = rect(w=0.05, h=0.12, center=(0.045, 0, 0), rot=(-HALF_PI, 0, 0))
    (r,) = run([magnet(m=m, length=length)], path)
    assert r.status == "verified" and r.enclosure.value_A == 0.0
    assert abs(r.circulation_H_A) <= r.tolerance_A
    assert r.crosses_material
    assert abs(r.bound_current_from_B_A) == pytest.approx(m * length, rel=1e-4)


def test_magnet_with_free_current():
    (r,) = run([magnet(), wire("w", 3.0, (0.2, 0, 0), rot=(0, 0, 0))],
               circle(r=0.05, center=(0.2, 0, 0)))
    assert_verified(r, 3.0)
    (o,) = run([magnet(), wire("w", 3.0, (0.2, 0, 0))], circle(r=0.15, center=(0.0, 0, 0.1)))
    assert_verified(o, 0.0)  # around the magnet, outside its body


# ------------------------------------------------------------- F: sources on or near the path


def test_path_through_a_wire_is_reported_not_integrated():
    (r,) = run([wire("w", 1.0, (0.1, 0, 0))], circle(r=0.1))
    assert r.status == "intersects_source" and r.circulation_H_A is None


def test_path_through_a_loop_wire_is_reported():
    (r,) = run([loop("l", 1.0, 0.1)], rect(w=0.2, h=0.1, center=(0.0, 0, 0),
                                           rot=(HALF_PI, 0, 0)))
    assert r.status == "intersects_source"


def test_path_close_to_a_wire_still_converges_and_is_flagged():
    (r,) = run([wire("w", 1.0, (0.0999, 0, 0))], circle(r=0.1))
    assert r.near_singular and r.min_distance_to_filament_m == pytest.approx(1e-4, rel=1e-3)
    assert_verified(r, 1.0)


def test_charges_do_not_affect_ampere():
    a = run([wire("w", 2.0)], circle(r=0.1))[0]
    b = run([wire("w", 2.0), charge("q", 1e-6, (0.05, 0, 0))], circle(r=0.1))[0]
    assert a.circulation_H_A == b.circulation_H_A


def test_no_sources_gives_zero():
    (r,) = run([charge("q", 1e-9, (0.5, 0, 0))], circle(r=0.1))
    assert_verified(r, 0.0)


# ----------------------------------------------------------- G: numerics and invariance


def test_tolerance_controls_accuracy():
    w = [wire("w", 1.0, (0.08, 0.0, 0))]  # near the path: peaked integrand
    errs = []
    for rtol in (1e-3, 1e-6, 1e-9):
        (r,) = run(w, circle(r=0.1, rtol=rtol))
        assert r.converged and r.status == "verified"
        errs.append(abs(r.circulation_H_A - 1.0))
        assert errs[-1] <= max(rtol, 1e-8)


def test_rigid_motion_of_the_whole_scene_leaves_results_unchanged():
    # Path in the xz plane from x = 0.03 to 0.13: links the loop wire at x = 0.05 and the
    # wire running along y through (0.08, 0, 0).
    objs = [wire("a", 2.0, (0.08, 0, 0), rot=(HALF_PI, 0, 0)), loop("l", 1.5, 0.05)]
    path = rect(w=0.1, h=0.1, center=(0.08, 0, 0), rot=(HALF_PI, 0, 0))
    (r0,) = run(objs, path)
    # The two currents cross the surface in opposite senses: |2 - 1.5|.
    assert r0.status == "verified" and abs(r0.enclosure.value_A) == pytest.approx(0.5)
    shift = np.array([0.3, -0.1, 0.2])
    moved = [wire("a", 2.0, tuple(np.array([0.08, 0, 0]) + shift), rot=(HALF_PI, 0, 0)),
             loop("l", 1.5, 0.05, tuple(shift))]
    path2 = dict(path, center_m=tuple(np.array([0.08, 0, 0]) + shift))
    (r1,) = run(moved, path2)
    assert r1.status == "verified"
    assert r1.enclosure.value_A == r0.enclosure.value_A
    assert r1.circulation_H_A == pytest.approx(r0.circulation_H_A, rel=1e-9, abs=1e-10)


def test_fingerprint_tracks_physics_not_names():
    scene = scene_of(wire("w", 1.0))
    req = ampere.AmpereRequest.model_validate({"paths": [circle()]})
    named = scene_of(wire("w", 1.0, name="renamed"))
    assert ampere.fingerprint(scene, req) == ampere.fingerprint(named, req)
    other = ampere.AmpereRequest.model_validate({"paths": [circle(r=0.11)]})
    assert ampere.fingerprint(scene, req) != ampere.fingerprint(scene, other)
    assert ampere.fingerprint(scene, req) != ampere.fingerprint(scene_of(wire("w", 1.1)), req)
