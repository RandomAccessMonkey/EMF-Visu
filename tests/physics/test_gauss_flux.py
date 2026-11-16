"""Closed-surface flux, Gauss's law and the Gauss–Ostrogradsky theorem (Phase 2B-2).

The surface integral (solid angles over the represented mesh) and the volume integral
(distributional source weights of the strictly enclosed charges) are produced by separate
functions; the tests compare them with each other and with Q_enc/eps0 and Q_enc."""

from __future__ import annotations

import math

import numpy as np
import pytest

from emf_core import engine
from emf_core.geometry import surfaces as geo
from emf_core.solvers.analytical import gauss
from emf_core.solvers.analytical.electrostatics import evaluate
from emf_core.solvers.analytical.gauss import FluxRequest
from emf_core.units import COULOMB_K, EPS0
from tests.conftest import charge, scene_of

Q = 1e-9
SHAPES = {
    "sphere": {"type": "sphere", "radius_m": 0.9},
    "cube": {"type": "cube", "side_m": 1.5},
    "box": {"type": "box", "size_m": (1.4, 1.0, 1.2)},
    "cylinder": {"type": "cylinder", "radius_m": 0.7, "height_m": 1.6},
}


def run(scene, *surfaces, quality="final"):
    req = FluxRequest.model_validate({"surfaces": [
        {"id": f"S{i}", **s} for i, s in enumerate(surfaces)], "quality": quality})
    header, arrays = engine.run_flux(scene, req)
    return header.surfaces, arrays


def one(scene, surface, **kw):
    res, arrays = run(scene, surface, **kw)
    return res[0], arrays


def gauss_holds(r, q_enc, sign=1):
    """Surface integral = sign * Q_enc/eps0 within its own reported uncertainty, and the
    volume integral (separate path) equals Q_enc/eps0."""
    assert r.status == "ok"
    tol_e = max(r.flux_E_uncertainty_V_m, 1e-12 * abs(q_enc) / EPS0)
    assert abs(r.flux_E_V_m - sign * q_enc / EPS0) <= tol_e + 1e-13
    assert abs(r.flux_D_C - sign * q_enc) <= r.flux_D_uncertainty_C + 1e-24
    assert r.volume_integral_E_V_m == pytest.approx(q_enc / EPS0, rel=1e-15, abs=1e-30)
    assert r.volume_integral_D_C == pytest.approx(q_enc, rel=1e-15, abs=1e-36)
    assert abs(r.difference_E_V_m) <= tol_e + 1e-13


@pytest.mark.parametrize("name", list(SHAPES))
@pytest.mark.parametrize("q", [Q, -Q])
def test_single_charge_inside_each_shape(name, q):
    scene = scene_of(charge("a", q, (0.12, -0.07, 0.05)))
    r, _ = one(scene, {"shape": SHAPES[name], "rotation_euler_xyz_rad": (0.3, 0.2, -0.4)})
    gauss_holds(r, q)
    assert r.enclosed.positive_count == (q > 0) and r.enclosed.negative_count == (q < 0)
    assert np.sign(r.flux_E_V_m) == np.sign(q)  # outward surface: + charge -> + flux


def test_multiple_and_cancelling_charges_inside():
    scene = scene_of(charge("a", 2 * Q, (0.2, 0, 0)), charge("b", -0.5 * Q, (-0.3, 0.2, 0)),
                     charge("c", 1.5 * Q, (0, -0.3, 0.1)))
    r, _ = one(scene, {"shape": SHAPES["sphere"]})
    gauss_holds(r, 3 * Q)
    assert (r.enclosed.positive_count, r.enclosed.negative_count) == (2, 1)
    assert r.enclosed.positive_C == pytest.approx(3.5 * Q) and r.enclosed.negative_C == \
        pytest.approx(-0.5 * Q)
    zero = scene_of(charge("p", Q, (-0.4, 0, 0)), charge("n", -Q, (0.4, 0, 0)))
    r0, arrays = one(zero, {"shape": SHAPES["sphere"]})
    gauss_holds(r0, 0.0)
    flux_tri = arrays["surf0.flux_E"]
    # Nonzero local contributions of both signs (each of 3968 triangles carries a small share).
    assert flux_tri.max() > 1e-4 * Q / EPS0 and flux_tri.min() < -1e-4 * Q / EPS0
    assert arrays["surf0.En"].max() > 0 and arrays["surf0.En"].min() < 0


def test_external_charges_have_zero_net_but_nonzero_local_flux():
    scene = scene_of(charge("x1", 2 * Q, (1.4, 0.5, 0)), charge("x2", -Q, (-1.3, -0.8, 0.3)),
                     charge("x3", Q, (0, 1.5, -0.5)))
    for name in SHAPES:
        r, arrays = one(scene, {"shape": SHAPES[name]})
        gauss_holds(r, 0.0)
        assert r.enclosed.external_count == 3
        for c in r.charges:
            assert c.state == "outside" and abs(c.flux_E_V_m) <= 1e-12 * abs(c.charge_C) / EPS0
            assert c.volume_weight_E_V_m == 0.0
        en = arrays["surf0.En"]
        assert en.max() > 0 and en.min() < 0  # field enters and leaves
        per_charge = arrays["surf0.charge_flux_E"]
        # Each external charge, on its own, sends flux in through some triangles and out
        # through others.
        assert np.all(per_charge.max(axis=1) > 1e-6 * Q / EPS0)
        assert np.all(per_charge.min(axis=1) < -1e-6 * Q / EPS0)


def test_enclosed_and_external_charges_together():
    scene = scene_of(charge("in", Q, (0, 0, 0)), charge("x1", 2 * Q, (1.4, 0.5, 0)),
                     charge("x2", -Q, (-1.3, -0.8, 0.3)))
    r, _ = one(scene, {"shape": {"type": "box", "size_m": (1.2, 1.2, 1.2)}})
    gauss_holds(r, Q)
    by = {c.object_id: c for c in r.charges}
    assert by["in"].flux_E_V_m == pytest.approx(Q / EPS0, rel=1e-12)
    assert abs(by["x1"].flux_E_V_m) < 1e-12 * Q / EPS0
    assert sum(c.flux_E_V_m for c in r.charges) == pytest.approx(r.flux_E_V_m, rel=1e-14)


def test_same_enclosed_charge_any_shape_or_size():
    scene = scene_of(charge("a", Q, (0.1, 0, 0)), charge("b", -0.5 * Q, (-0.2, 0.2, 0.1)),
                     charge("x", 2 * Q, (1.6, 0, 0)))
    shapes = [SHAPES["sphere"], {"type": "sphere", "radius_m": 1.3}, SHAPES["box"],
              {"type": "box", "size_m": (0.7, 0.8, 0.9)}, SHAPES["cylinder"],
              {"type": "cylinder", "radius_m": 0.5, "height_m": 3.0}, SHAPES["cube"]]
    res, arrays = run(scene, *[{"shape": s} for s in shapes])
    fluxes = [r.flux_E_V_m for r in res]
    assert all(r.status == "ok" for r in res)
    assert max(fluxes) - min(fluxes) < 1e-12 * 0.5 * Q / EPS0
    for r in res:
        gauss_holds(r, 0.5 * Q)
    # ... while the local distribution differs from shape to shape.
    spreads = [float(np.ptp(arrays[f"surf{k}.En"])) for k in range(len(shapes))]
    assert max(spreads) / min(spreads) > 2


def test_reversed_orientation_flips_the_sign():
    scene = scene_of(charge("a", Q, (0.1, 0.1, 0)))
    for name in SHAPES:
        res, arrays = run(scene, {"shape": SHAPES[name]},
                          {"shape": SHAPES[name], "orientation": "inward"})
        out, inn = res
        assert inn.orientation_sign == -1
        gauss_holds(inn, Q, sign=-1)
        assert inn.flux_E_V_m == pytest.approx(-out.flux_E_V_m, rel=1e-14)
        assert np.array_equal(arrays["surf1.flux_E"], -arrays["surf0.flux_E"])  # bitwise
        assert np.allclose(arrays["surf1.normals"], -arrays["surf0.normals"])


def test_displacement_flux_is_eps0_times_electric_flux():
    scene = scene_of(charge("a", 3 * Q, (0.1, 0.1, 0)), charge("x", -Q, (1.5, 0, 0)))
    r, arrays = one(scene, {"shape": SHAPES["cylinder"]})
    assert r.flux_D_C == pytest.approx(EPS0 * r.flux_E_V_m, rel=1e-13)
    assert np.allclose(arrays["surf0.flux_D"], EPS0 * arrays["surf0.flux_E"], rtol=1e-12, atol=0)
    assert np.allclose(arrays["surf0.Dn"], EPS0 * arrays["surf0.En"], rtol=1e-15, atol=0)


def test_solid_angle_flux_matches_direct_quadrature_on_triangles():
    """Independent check of the solid-angle formula: Gauss–Legendre quadrature of E·n over
    individual triangles (Duffy-free, charge well away from the triangles)."""
    pos = np.array([[0.13, -0.21, 0.07]])
    qs = np.array([Q])
    s = geo.GaussSurface.model_validate({"id": "S", "shape": SHAPES["box"]})
    tri = geo.build_mesh(s, "final").tri
    omega = gauss.solid_angles(pos, tri)[0]
    x, w = np.polynomial.legendre.leggauss(40)
    u = (x + 1) / 2
    for t in range(len(tri)):
        a, b, c = tri[t]
        n = np.cross(b - a, c - a)
        uu, vv = np.meshgrid(u, u, indexing="ij")
        ww = np.outer(w, w) / 4
        # Map the unit square onto the triangle: p = a + s (b - a) + s t (c - b), J = s.
        p = a + uu[..., None] * (b - a) + (uu * vv)[..., None] * (c - b)
        e = evaluate(p.reshape(-1, 3), pos, qs, 0.0)[0].reshape(40, 40, 3)
        integral = float(np.sum(ww * uu * (e @ n)))
        assert integral == pytest.approx(COULOMB_K * Q * omega[t], rel=1e-8, abs=1e-10)


def test_preview_and_final_use_one_mesh_each_for_rendering_classification_and_flux():
    # A charge between the preview mesh and the final mesh (both inscribed in the sphere):
    # the preview mesh does not contain it, the final mesh does. Each result is consistent
    # with its own mesh: classification and flux agree, and the transported triangles are
    # exactly that mesh.
    s = {"shape": {"type": "sphere", "radius_m": 1.0}}
    surface = geo.GaussSurface.model_validate({"id": "S0", **s})
    prev, fin = geo.build_mesh(surface, "preview"), geo.build_mesh(surface, "final")
    c = prev.tri[60].mean(axis=0)
    direction = c / np.linalg.norm(c)
    d_prev = geo.point_mesh_distance(np.zeros((1, 3)), prev.tri[60:61])[0]
    p = direction * (d_prev + 0.5 * (1.0 - fin.ideal.max_deviation_m - d_prev))
    scene = scene_of(charge("a", Q, tuple(p)))
    rp, ap = one(scene, s, quality="preview")
    rf, af = one(scene, s, quality="final")
    assert rp.mesh.resolution_id == "sphere/lon24-lat12" and rf.mesh.resolution_id == \
        "sphere/lon64-lat32"
    assert np.array_equal(ap["surf0.triangles"], prev.tri)
    assert np.array_equal(af["surf0.triangles"], fin.tri)
    assert rp.charges[0].state == "outside" and abs(rp.flux_E_V_m) < 1e-10
    assert rf.charges[0].state == "inside" and rf.flux_E_V_m == pytest.approx(Q / EPS0,
                                                                                 rel=1e-12)
    # The ideal sphere would contain it: reported as a geometric-approximation diagnostic.
    assert rp.ideal_shape_disagreement_ids == ["a"] and rf.ideal_shape_disagreement_ids == []


def test_geometric_error_and_integration_error_are_reported_separately():
    scene = scene_of(charge("a", Q, (0.1, 0, 0)))
    for q in ("preview", "final"):
        r, _ = one(scene, {"shape": SHAPES["sphere"]}, quality=q)
        gauss_holds(r, Q)  # exact for the represented mesh at both resolutions
        assert r.flux_E_uncertainty_V_m < 1e-9 * Q / EPS0  # floating-point evaluation
        assert r.mesh.max_deviation_m > 1e-4  # geometry of the inscribed polyhedron
        assert r.value_classes["flux"] == "exact_for_represented_mesh"
        assert r.value_classes["mesh_geometry"] == "numerical_approximation"


def test_refinement_does_not_change_the_flux():
    scene = scene_of(charge("a", Q, (0.3, -0.2, 0.1)), charge("x", -Q, (1.2, 0.4, 0.3)))
    fl = [one(scene, {"shape": SHAPES["sphere"]}, quality=q)[0].flux_E_V_m
          for q in ("preview", "final")]
    assert fl[0] == pytest.approx(fl[1], rel=1e-13) == pytest.approx(Q / EPS0, rel=1e-13)


@pytest.mark.parametrize("d", [1e-2, 1e-5, 1e-8, 1e-10])
def test_charge_near_but_not_on_the_surface(d):
    for side, q_enc in ((-1, Q), (1, 0.0)):
        scene = scene_of(charge("a", Q, (0.75 + side * d, 0.1, -0.2)))
        r, arrays = one(scene, {"shape": SHAPES["cube"]})
        assert r.charges[0].state == ("inside" if side < 0 else "outside")
        gauss_holds(r, q_enc)
        assert np.all(np.isfinite(arrays["surf0.flux_E"]))
        assert r.charges[0].near_boundary


def test_charge_on_the_surface_makes_the_flux_undefined():
    scene = scene_of(charge("on", Q, (0.75, 0.1, -0.2)), charge("in", Q, (0, 0, 0)))
    r, _ = one(scene, {"shape": SHAPES["cube"]})
    assert r.status == "boundary_ambiguous"
    assert r.flux_E_V_m is None and r.flux_D_C is None and r.volume_integral_E_V_m is None
    by = {c.object_id: c for c in r.charges}
    assert by["on"].state == "boundary" and by["on"].flux_E_V_m is None
    assert by["in"].state == "inside" and r.enclosed.boundary_count == 1
    assert r.value_classes["flux"] == "undefined"


def test_zero_enclosed_charge_and_empty_scene():
    r, _ = one(scene_of(), {"shape": SHAPES["sphere"]})
    assert r.flux_E_V_m == 0.0 and r.volume_integral_E_V_m == 0.0 and r.charges == []


def test_invalid_surface_gets_no_flux():
    scene = scene_of(charge("a", Q, (0, 0, 0)))
    v = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0.5, 0.5, 1)]
    t = [(0, 1, 4), (1, 2, 4), (2, 3, 4), (3, 0, 4)]
    r, arrays = one(scene, {"shape": {"type": "mesh", "vertices_m": v, "triangles": t}})
    assert r.status == "invalid" and r.flux_E_V_m is None and r.errors
    assert not any(k.startswith("surf0.") for k in arrays)


# ------------------------------------------------------------------------- subdivision


def sub(scene, n=(4, 4, 4), size=(1.2, 1.0, 0.8), rot=(0.2, -0.3, 0.5)):
    res, arrays = run(scene, {"shape": {"type": "box", "size_m": size}, "subdivision": n,
                              "rotation_euler_xyz_rad": rot, "center_m": (0.05, 0.02, -0.03)})
    return res[0], arrays


def test_shared_internal_faces_cancel_exactly_on_the_actual_face_data():
    scene = scene_of(charge("a", Q, (0.31, 0.12, 0.07)), charge("b", -2 * Q, (-0.2, -0.3, 0.1)),
                     charge("x", Q, (1.5, 0.2, 0.0)))
    r, arrays = sub(scene, n=(3, 4, 2))
    d = r.subdivision
    face = arrays["surf0.cells.face_flux_E"]
    nb = arrays["surf0.cells.face_neighbor"].astype(int)
    pairs = 0
    for ci in range(face.shape[0]):
        for f in range(6):
            cj = nb[ci, f]
            if cj >= 0:
                opposite = f + 1 if f % 2 == 0 else f - 1
                assert nb[cj, opposite] == ci
                assert face[ci, f] + face[cj, opposite] == 0.0  # bitwise cancellation
                pairs += 1
    assert pairs == 2 * d.shared_faces and d.shared_face_max_abs_sum_E_V_m == 0.0
    # Cell corners in grid order m = dx + 2dy + 4dz: corner 7 of a cell is corner 0 of its
    # diagonal neighbour, and neighbouring cells share their common corners.
    corners = arrays["surf0.cells.corners"]
    assert np.array_equal(corners[0, 1], corners[(1 * 4 + 0) * 2 + 0, 0])  # (0,0,0) +x neighbour
    assert np.array_equal(corners[0, 7], corners[(1 * 4 + 1) * 2 + 1, 0])
    assert d.shared_faces == (2 * 4 * 2) + (3 * 3 * 2) + (3 * 4 * 1)
    # The shared faces are made of the same triangles with opposite winding.
    verts, cells, faces = geo.grid_box_cells((1.2, 1.0, 0.8), (3, 4, 2))
    a = [t for t, f in zip(cells[0], faces[0], strict=True) if f == 1]  # +x face of cell (0,0,0)
    b_cell = (1 * 4 + 0) * 2 + 0  # cell (1,0,0)
    b = [t for t, f in zip(cells[b_cell], faces[b_cell], strict=True) if f == 0]
    assert sorted(a) == sorted((p, r_, q) for p, q, r_ in b)


@pytest.mark.parametrize("n", [(1, 1, 1), (2, 3, 1), (4, 4, 4), (8, 8, 8)])
def test_cell_fluxes_sum_to_the_outer_flux_and_cell_volume_integrals_to_the_parent(n):
    scene = scene_of(charge("a", Q, (0.31, 0.12, 0.07)), charge("b", -2 * Q, (-0.21, -0.3, 0.1)),
                     charge("c", 0.5 * Q, (0.013, -0.017, 0.029)), charge("x", Q, (1.5, 0.2, 0)))
    r, arrays = sub(scene, n=n)
    d = r.subdivision
    assert d.status == "ok" and len(d.cells) == math.prod(n)
    assert abs(d.sum_cell_flux_E_V_m - r.flux_E_V_m) <= 1e-12 * 3.5 * Q / EPS0
    assert d.cell_flux_difference_E_V_m == pytest.approx(d.sum_cell_flux_E_V_m - r.flux_E_V_m)
    assert d.sum_cell_volume_integral_E_V_m == pytest.approx(r.volume_integral_E_V_m,
                                                              rel=1e-14)
    assert d.parent_volume_integral_E_V_m == r.volume_integral_E_V_m
    assert sum(c.enclosed_C for c in d.cells) == pytest.approx(-0.5 * Q, rel=1e-14)
    assert sum(1 for c in d.cells if c.enclosed_C) <= 3
    for c in d.cells:  # each cell obeys Gauss's law on its own
        assert c.flux_E_V_m == pytest.approx(c.volume_integral_E_V_m, abs=1e-12 * 3.5 * Q / EPS0)


def test_charge_on_an_internal_cell_boundary_is_ambiguous_but_the_parent_is_not():
    # (2,2,2) cells of a centred box: the centre lies on internal faces of all eight cells.
    scene = scene_of(charge("mid", Q, (0.0, 0.0, 0.0)), charge("a", Q, (0.3, 0.2, 0.1)))
    res, _ = run(scene, {"shape": {"type": "box", "size_m": (1.2, 1.0, 0.8)},
                         "subdivision": (2, 2, 2)})
    r = res[0]
    d = r.subdivision
    gauss_holds(r, 2 * Q)  # the parent volume is unaffected
    assert d.status == "ambiguous" and d.ambiguous_object_ids == ["mid"]
    assert d.sum_cell_volume_integral_E_V_m is None
    assert d.parent_volume_integral_E_V_m == pytest.approx(2 * Q / EPS0)
    touching = [c for c in d.cells if "mid" in c.ambiguous_object_ids]
    assert len(touching) == 8 and all(c.enclosed_C is None for c in touching)
