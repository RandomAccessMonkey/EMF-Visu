"""Equipotential contours (2D) and isosurfaces (3D): every vertex must lie on the exact level
set, the geometry must converge under grid refinement, and singular samples must be harmless."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core import engine
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical.electrostatics import auto_levels, evaluate
from emf_core.units import COULOMB_K
from tests.conftest import charge, scene_of


def contour_request(n=129, levels=None, **extra) -> SolveRequest:
    return SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "heat", "u_extent_m": 4, "v_extent_m": 4,
                       "nu": n, "nv": n}],
        "quantities": ["phi"], "equipotentials": {"sampling_id": "heat", "levels_V": levels},
        **extra,
    })


def iso_request(n=33, levels=None) -> SolveRequest:
    return SolveRequest.model_validate({
        "samplings": [{"kind": "points", "id": "p", "points_m": [(1, 1, 1)]}],
        "quantities": ["phi"],
        "isosurfaces": {"lattice": {"kind": "lattice", "id": "iso", "min_m": (-2, -2, -2),
                                    "max_m": (2, 2, 2), "nx": n, "ny": n, "nz": n},
                        "levels_V": levels},
    })


def exact_phi(scene, pts):
    pos = np.array([o.transform.position_m for o in scene.objects if o.source])
    q = np.array([o.source.charge_C for o in scene.objects if o.source])
    return evaluate(np.asarray(pts, float).reshape(-1, 3), pos, q, 0.0)


def by_level(result, key="equipotentials"):
    product = getattr(result.header, key)
    data = result.arrays[product.array]
    return [(lv.value_V, data[lv.start:lv.start + lv.count]) for lv in product.levels]


def test_single_charge_contours_are_circles_of_the_analytic_radius():
    q = 1e-9
    scene = scene_of(charge("a", q, (0.2, -0.1, 0.0)))
    levels = [6.0, 12.0, 30.0]
    r = engine.run(scene, contour_request(levels=levels))
    for value, seg in by_level(r):
        radius = COULOMB_K * q / value
        assert len(seg) > 16
        d = np.linalg.norm(seg.reshape(-1, 3) - [0.2, -0.1, 0.0], axis=1)
        assert np.allclose(d, radius, rtol=1e-7, atol=0)  # vertices sit on the exact circle
        assert np.all(seg[..., 2] == 0.0)
        # Segments form a closed loop: every vertex is shared by exactly two segments.
        keys, counts = np.unique(np.round(seg.reshape(-1, 3), 9), axis=0, return_counts=True)
        assert np.all(counts == 2)
        # Total length approaches the circumference from below (inscribed polygon).
        length = np.linalg.norm(seg[:, 1] - seg[:, 0], axis=1).sum()
        assert 0.995 < length / (2 * math.pi * radius) <= 1.0


def test_contour_vertices_match_the_level_and_segments_are_perpendicular_to_E():
    scene = scene_of(charge("a", 2e-9, (-0.8, -0.6, 0)), charge("b", -1e-9, (0.8, -0.6, 0)),
                     charge("c", 1e-9, (0.0, 0.8, 0)), charge("d", -2e-9, (0.9, 0.9, 0)))
    r = engine.run(scene, contour_request(n=193))
    values = [v for v, _ in by_level(r)]
    assert 0.0 in values and min(values) < 0 < max(values)
    scale = COULOMB_K * 6e-9 / scene.domain.diagonal_m
    worst_angle = 0.0
    for value, seg in by_level(r):
        if len(seg) == 0:
            continue
        _, phi = exact_phi(scene, seg)
        assert np.all(np.abs(phi - value) <= 1e-7 * max(abs(value), 1e-3 * scale))
        e, _ = exact_phi(scene, seg.mean(axis=1))
        t = seg[:, 1] - seg[:, 0]
        long_enough = np.linalg.norm(t, axis=1) > 1e-3
        cos = np.abs(np.einsum("ij,ij->i", t, e)) / (
            np.linalg.norm(t, axis=1) * np.linalg.norm(e, axis=1))
        worst_angle = max(worst_angle, float(cos[long_enough].max(initial=0.0)))
    assert worst_angle < 0.15  # chords of a curved equipotential; E is normal to the true curve


def test_dipole_zero_equipotential_is_the_symmetry_plane():
    scene = scene_of(charge("p", 1e-9, (-0.5, 0, 0)), charge("n", -1e-9, (0.5, 0, 0)))
    # 130 samples: no grid line lies on x = 0, so the level is found by interpolation.
    r = engine.run(scene, contour_request(n=130, levels=[0.0]))
    (value, seg), = by_level(r)
    assert value == 0.0 and len(seg) > 100
    assert np.all(np.abs(seg[..., 0]) < 1e-9)
    assert seg[..., 1].min() < -1.9 and seg[..., 1].max() > 1.9


def test_contour_midpoint_error_converges_at_second_order():
    q = 1e-9
    scene = scene_of(charge("a", q, (0.013, 0.007, 0.0)))
    value = 9.0
    errs = []
    for n in (33, 65, 129):
        (_, seg), = by_level(engine.run(scene, contour_request(n=n, levels=[value])))
        _, phi_mid = exact_phi(scene, seg.mean(axis=1))
        errs.append(float(np.abs(phi_mid - value).max() / value))
    assert errs[0] / errs[1] == pytest.approx(4.0, rel=0.35)
    assert errs[1] / errs[2] == pytest.approx(4.0, rel=0.35)
    # Theory: a chord of length c on a circle of radius r misses it by c^2 / (8 r); the longest
    # chord in a square cell of size h is the diagonal, c = sqrt(2) h.
    radius = COULOMB_K * q / value
    for n, err in zip((33, 65, 129), errs, strict=True):
        h = 4 / (n - 1)
        assert err <= 1.05 * (2 * h * h) / (8 * radius * radius)


def test_singular_samples_and_tiny_loops_are_handled_safely():
    # The charge sits exactly on a grid node: that sample is undefined (NaN).
    scene = scene_of(charge("a", 1e-9, (0.0, 0.0, 0.0)))
    r = engine.run(scene, contour_request(n=65, levels=[5.0, 1e6]))
    assert np.isnan(r.arrays["heat.phi"]).sum() == 1
    segments = r.arrays["equipotentials.segments"]
    assert np.all(np.isfinite(segments))
    (_, big), (_, tiny) = by_level(r)
    assert len(big) > 0
    # Loops inside the cells around the undefined sample are traced correctly, because the
    # potential's divergence to +infinity at the charge is known: 4 exact vertices each.
    assert len(tiny) == 4  # r = 9 µm
    assert np.allclose(np.linalg.norm(tiny.reshape(-1, 3), axis=1), COULOMB_K * 1e-9 / 1e6,
                       rtol=1e-7)
    # With the charge inside a cell (not on a node) a loop smaller than the cell crosses no
    # grid edge: it is missed (documented limitation), never invented.
    off_node = scene_of(charge("a", 1e-9, (0.03, 0.03, 0.0)))
    (_, missed), = by_level(engine.run(off_node, contour_request(n=65, levels=[1e3])))
    assert len(missed) == 0


def test_automatic_levels_are_a_signed_geometric_ladder():
    assert auto_levels(np.array([]), 1.0, (0, 1)) == []
    pos_only = auto_levels(np.array([1e-9]), 2.0, (0, 1, 2))
    v_ref = COULOMB_K * 1e-9 / 2.0
    assert pos_only == pytest.approx([v_ref, 2 * v_ref, 4 * v_ref])
    mixed = auto_levels(np.array([1e-9, -3e-9]), 2.0, (0, 1))
    assert mixed == sorted(mixed) and 0.0 in mixed and len(mixed) == 5
    assert auto_levels(np.array([-1e-9]), 2.0, (0,))[0] < 0


def test_single_charge_isosurface_is_the_analytic_sphere():
    q = 1e-9
    centre = np.array([0.1, -0.05, 0.2])
    scene = scene_of(charge("a", q, tuple(centre)))
    value = 9.0
    radius = COULOMB_K * q / value
    areas = []
    for n in (17, 33):
        r = engine.run(scene, iso_request(n=n, levels=[value]))
        tri = r.arrays["isosurfaces.triangles"]
        normals = r.arrays["isosurfaces.normals"]
        assert tri.shape[0] > 100 and normals.shape == tri.shape
        d = tri.reshape(-1, 3) - centre
        assert np.allclose(np.linalg.norm(d, axis=1), radius, rtol=1e-7, atol=0)
        # Normals are E/|E|: radially outward for a positive charge, unit length.
        radial = d / np.linalg.norm(d, axis=1)[:, None]
        assert np.allclose(normals.reshape(-1, 3), radial, atol=1e-7)
        areas.append(0.5 * np.linalg.norm(
            np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1).sum())
    exact = 4 * math.pi * radius**2
    err = [abs(a - exact) / exact for a in areas]
    assert areas[0] < exact and areas[1] < exact  # inscribed polyhedron
    assert err[1] < 0.01 and err[0] / err[1] > 2.5  # converges under refinement


def test_isosurface_vertices_match_levels_for_several_charges_and_are_watertight():
    scene = scene_of(charge("p", 1e-9, (-0.5, 0, 0)), charge("n", -1e-9, (0.5, 0, 0)))
    r = engine.run(scene, iso_request(n=25))
    levels = by_level(r, "isosurfaces")
    assert [v for v, _ in levels] == sorted(v for v, _ in levels)
    assert any(v == 0.0 for v, _ in levels)
    scale = COULOMB_K * 2e-9 / scene.domain.diagonal_m
    for value, tri in levels:
        assert len(tri) > 0
        _, phi = exact_phi(scene, tri)
        assert np.all(np.abs(phi - value) <= 1e-7 * max(abs(value), 1e-3 * scale))
        if value == 0.0:
            assert np.all(np.abs(tri[..., 0]) < 1e-9)  # the symmetry plane x = 0
        else:
            # A closed surface inside the lattice: every edge belongs to exactly two triangles.
            # Shared vertices are bitwise identical, so they can be matched exactly.
            _, vid = np.unique(tri.reshape(-1, 3), axis=0, return_inverse=True)
            vid = vid.reshape(-1, 3)
            assert np.all((vid[:, 0] != vid[:, 1]) & (vid[:, 1] != vid[:, 2])
                          & (vid[:, 0] != vid[:, 2]))
            edges = np.sort(np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]]),
                            axis=1)
            _, counts = np.unique(edges, axis=0, return_counts=True)
            assert np.all(counts == 2)


def test_lattice_node_on_a_charge_is_skipped_safely():
    scene = scene_of(charge("a", 1e-9, (0.0, 0.0, 0.0)))  # node (8, 8, 8) of a 17^3 lattice
    r = engine.run(scene, iso_request(n=17, levels=[20.0]))
    tri = r.arrays["isosurfaces.triangles"]
    assert np.all(np.isfinite(tri)) and np.all(np.isfinite(r.arrays["isosurfaces.normals"]))
    # r = 0.449 m spans the cells around the undefined node; the surface is still complete.
    assert np.allclose(np.linalg.norm(tri.reshape(-1, 3), axis=1), COULOMB_K * 1e-9 / 20.0,
                       rtol=1e-7)
    _, vid = np.unique(tri.reshape(-1, 3), axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    edges = np.sort(np.concatenate([vid[:, [0, 1]], vid[:, [1, 2]], vid[:, [2, 0]]]), axis=1)
    assert np.all(np.unique(edges, axis=0, return_counts=True)[1] == 2)
