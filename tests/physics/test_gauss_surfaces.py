"""Gaussian surface geometry: built-in meshes, orientation, transforms, validation, and
inside/outside/boundary classification (Phase 2B-2)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core.geometry import surfaces as geo

ROT = (0.4, -0.7, 1.1)
CENTRE = (0.3, -0.2, 0.5)


def surf(shape, **kw):
    return geo.GaussSurface.model_validate({"id": "S", "shape": shape, **kw})


SHAPES = {
    "sphere": {"type": "sphere", "radius_m": 0.8},
    "cube": {"type": "cube", "side_m": 1.1},
    "box": {"type": "box", "size_m": (1.4, 0.6, 0.9)},
    "cylinder": {"type": "cylinder", "radius_m": 0.5, "height_m": 1.3},
}
EXPECTED_TRIS = {
    ("sphere", "preview"): 2 * 24 * 11, ("sphere", "final"): 2 * 64 * 31,
    ("cylinder", "preview"): 2 * 32 * 2 + 2 * 32, ("cylinder", "final"): 2 * 96 * 8 + 2 * 96,
    ("cube", "preview"): 12, ("cube", "final"): 12, ("box", "preview"): 12, ("box", "final"): 12,
}


@pytest.mark.parametrize("name", list(SHAPES))
@pytest.mark.parametrize("quality", ["preview", "final"])
def test_built_in_surfaces_are_valid_closed_outward_meshes(name, quality):
    s = surf(SHAPES[name], center_m=CENTRE, rotation_euler_xyz_rad=ROT)
    m = geo.build_mesh(s, quality)
    assert m.valid and m.natural_orientation == "outward"
    assert len(m.triangles) == EXPECTED_TRIS[(name, quality)]
    assert geo.validate(m.vertices, m.triangles) == []
    vol = geo.signed_volume(m.vertices, m.triangles)
    assert vol > 0
    if name in ("cube", "box"):
        assert m.ideal.representation == "exact" and m.ideal.max_deviation_m == 0.0
        assert vol == pytest.approx(m.ideal.ideal_volume_m3, rel=1e-12)
        assert geo.areas(m.tri).sum() == pytest.approx(m.ideal.ideal_area_m2, rel=1e-12)
    else:
        # Inscribed polyhedron: smaller than the ideal shape, deviation reported.
        assert m.ideal.representation == "inscribed_polyhedron"
        assert 0 < m.ideal.max_deviation_m < 0.02
        assert vol < m.ideal.ideal_volume_m3 and geo.areas(m.tri).sum() < m.ideal.ideal_area_m2
    assert m.resolution_id.startswith(name)


def test_curved_mesh_geometry_converges_at_second_order():
    s = surf(SHAPES["sphere"])
    prev, fin = geo.build_mesh(s, "preview"), geo.build_mesh(s, "final")
    r = 0.8
    # Sagitta of the widest triangle ~ r (1 - cos(pi/n)): ratio ~ (64/24)^2 between levels.
    ratio = prev.ideal.max_deviation_m / fin.ideal.max_deviation_m
    assert ratio == pytest.approx((64 / 24) ** 2, rel=0.15)
    vol_err = [(4 / 3 * math.pi * r**3 - geo.signed_volume(m.vertices, m.triangles))
               for m in (prev, fin)]
    assert vol_err[0] / vol_err[1] == pytest.approx((64 / 24) ** 2, rel=0.15)
    cyl = surf(SHAPES["cylinder"])
    for q, n in (("preview", 32), ("final", 96)):
        assert geo.build_mesh(cyl, q).ideal.max_deviation_m == pytest.approx(
            0.5 * (1 - math.cos(math.pi / n)))


def test_vertices_follow_rotation_and_translation():
    s = surf(SHAPES["box"], center_m=CENTRE, rotation_euler_xyz_rad=ROT)
    m = geo.build_mesh(s, "final")
    assert np.allclose(m.vertices.mean(axis=0), CENTRE)
    rot = geo.rotation_matrix_xyz(ROT)
    local = (m.vertices - np.asarray(CENTRE)) @ rot
    assert np.allclose(np.sort(np.unique(np.round(np.abs(local), 12), axis=0).max(axis=0)),
                       np.sort([0.7, 0.3, 0.45]))


def test_reversed_orientation_reverses_every_triangle():
    out = geo.build_mesh(surf(SHAPES["sphere"]), "preview")
    inn = geo.build_mesh(surf(SHAPES["sphere"], orientation="inward"), "preview")
    assert np.array_equal(inn.triangles, out.triangles[:, [0, 2, 1]])
    assert geo.signed_volume(inn.vertices, inn.triangles) == pytest.approx(
        -geo.signed_volume(out.vertices, out.triangles), rel=1e-14)


TET_V = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)]
TET_T = [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]  # outward


def mesh_surface(v, t, **kw):
    return surf({"type": "mesh", "vertices_m": v, "triangles": t}, **kw)


def test_custom_closed_mesh_is_accepted_and_oriented_as_requested():
    good = geo.build_mesh(mesh_surface(TET_V, TET_T), "final")
    assert good.valid and good.natural_orientation == "outward"
    flipped = [(a, c, b) for a, b, c in TET_T]
    m = geo.build_mesh(mesh_surface(TET_V, flipped), "final")
    assert m.valid and m.natural_orientation == "inward"
    assert geo.signed_volume(m.vertices, m.triangles) > 0  # flipped to the requested outward


@pytest.mark.parametrize("v,t,needle", [
    # A square pyramid without its base: four triangles, open.
    ([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 1)],
     [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)], "not closed"),
    (TET_V, [TET_T[0], TET_T[1], TET_T[2], (1, 3, 2)], "not consistently oriented"),
    ([(0, 0, 0), (1, 0, 0), (2, 0, 0), (0, 0, 1)], TET_T, "zero area"),  # collinear face
    # Two tetrahedra sharing one vertex: a pinched (non-manifold) vertex.
    (TET_V + [(-1, 0, 0), (0, -1, 0), (0, 0, -1)],
     TET_T + [(0, 4, 5), (0, 6, 4), (0, 5, 6), (4, 6, 5)], "non-manifold vertex"),
    # Three triangles on one edge: a non-manifold edge.
    (TET_V + [(1, 1, 1)], TET_T + [(1, 2, 4), (1, 4, 2)], "more than two triangles"),
    # Two disjoint tetrahedra.
    (TET_V + [(5 + x, y, z) for x, y, z in TET_V],
     TET_T + [(a + 4, b + 4, c + 4) for a, b, c in TET_T], "separate pieces"),
])
def test_invalid_meshes_are_rejected_with_a_reason(v, t, needle):
    m = geo.build_mesh(mesh_surface(v, t), "final")
    assert not m.valid
    assert any(needle in e.en for e in m.errors), [e.en for e in m.errors]
    assert all(e.hu for e in m.errors)


@pytest.mark.parametrize("bad", [
    {"shape": {"type": "sphere", "radius_m": 0}},
    {"shape": {"type": "box", "size_m": (1, -1, 1)}},
    {"shape": {"type": "sphere", "radius_m": 1}, "subdivision": (2, 2, 2)},
    {"shape": {"type": "box"}, "subdivision": (9, 1, 1)},
    {"shape": {"type": "box"}, "subdivision": (8, 8, 9)},
    {"shape": {"type": "mesh", "vertices_m": TET_V, "triangles": [(0, 1, 7)] * 4}},
    {"shape": {"type": "cube"}, "orientation": "sideways"},
])
def test_invalid_surface_parameters_are_rejected(bad):
    with pytest.raises(ValidationError):
        geo.GaussSurface.model_validate({"id": "S", **bad})


def classify(surface, points, quality="final"):
    m = geo.build_mesh(surface, quality)
    pts = np.asarray(points, float)
    _, tau, near = geo.tolerances(m, pts)
    return geo.classify(m, pts, tau, near), tau, near, m


def test_inside_outside_for_rotated_and_translated_surfaces():
    s = surf(SHAPES["box"], center_m=CENTRE, rotation_euler_xyz_rad=ROT)
    rot = geo.rotation_matrix_xyz(ROT)
    local = np.array([[0.6, 0.25, 0.4], [0.75, 0, 0], [0, 0.35, 0], [-0.69, -0.29, -0.44],
                      [0, 0, 0.46]])
    world = local @ rot.T + np.asarray(CENTRE)
    cls, tau, *_ = classify(s, world)
    assert [c.state for c in cls] == ["inside", "outside", "outside", "inside", "outside"]
    assert cls[0].signed_distance_m == pytest.approx(-0.05) and cls[1].signed_distance_m == \
        pytest.approx(0.05)
    assert all(c.ray_agreement == 5 for c in cls)
    # A point inside the axis-aligned bounding box but outside the rotated box.
    corner = np.asarray(CENTRE) + np.array([0.55, 0.55, 0.0])
    assert classify(s, [corner])[0][0].state == "outside"


def test_tolerance_formula_and_boundary_classification():
    s = surf(SHAPES["cube"])  # faces at ±0.55
    cls, tau, near, m = classify(s, [(0.55, 0.1, 0.0), (0.55 + 3 * tau_guess(), 0, 0),
                                     (0.55 - 1e-9, 0, 0), (0.5, 0, 0)])
    assert tau == pytest.approx(max(1e-12 * 1.1, 64 * geo.EPS * 1.1))
    assert near == pytest.approx(max(0.011, 10 * tau))
    assert [c.state for c in cls] == ["boundary", "outside", "inside", "inside"]
    assert cls[0].signed_distance_m == 0.0
    # The last point is 0.05 m from a face: farther than the highlight distance (0.011 m).
    assert [c.near_boundary for c in cls] == [True, True, True, False]


def tau_guess():
    return max(1e-12 * 1.1, 64 * geo.EPS * 1.1)


def test_near_boundary_highlight_is_only_a_warning():
    s = surf(SHAPES["cube"])
    cls, tau, near, _ = classify(s, [(0.545, 0, 0), (0.555, 0, 0), (0.5, 0, 0)])
    assert [c.state for c in cls] == ["inside", "outside", "inside"]
    assert [c.near_boundary for c in cls] == [True, True, False]


def test_charges_near_mesh_vertices_and_edges_are_classified_by_their_true_position():
    s = surf(SHAPES["sphere"])
    m = geo.build_mesh(s, "final")
    v = m.vertices[5]  # a vertex on the ideal sphere
    e = 0.5 * (m.vertices[m.triangles[40, 0]] + m.vertices[m.triangles[40, 1]])  # an edge midpoint
    radial_v, radial_e = v / np.linalg.norm(v), e / np.linalg.norm(e)
    for d in (1e-3, 1e-6, 1e-9):
        cls, tau, *_ = classify(s, [v + d * radial_v, v - d * radial_v,
                                    e + d * radial_e, e - d * radial_e])
        assert [c.state for c in cls] == ["outside", "inside", "outside", "inside"]
        assert abs(cls[0].signed_distance_m - d) <= 1e-6 * d + 1e-15
    on, *_ = classify(s, [v, e])
    assert [c.state for c in on] == ["boundary", "boundary"]


def test_point_on_the_ideal_sphere_is_outside_its_inscribed_mesh():
    # The ideal sphere and the represented mesh differ: classification uses the mesh only.
    s = surf(SHAPES["sphere"])
    m = geo.build_mesh(s, "final")
    c = m.tri[100].mean(axis=0)
    p = 0.8 * c / np.linalg.norm(c)  # on the ideal sphere, above a face centre
    cls, *_ = classify(s, [p])
    assert cls[0].state == "outside" and cls[0].signed_distance_m > 0
