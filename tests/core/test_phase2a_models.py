"""Phase 2A model extensions: dipole groups, per-sampling quantities, superposition terms,
derived-product metadata, and the equation registry."""

from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core import engine, wire
from emf_core.equations import default_registry
from emf_core.presets import PRESETS, dipole_objects
from emf_core.scene.models import Scene
from emf_core.solvers import SolveRequest
from emf_core.solvers.analytical import electrostatics as es
from emf_core.solvers.base import ModelContext
from emf_core.units import COULOMB_K, EPS0
from emf_core.verification import references as ref
from tests.conftest import charge, points_request, scene_of


def test_dipole_group_equals_two_explicit_charges_and_follows_its_transform():
    q, d = 3e-9, 0.6
    objs = [o.model_dump() for o in dipole_objects("dip", "Dipole", q, d, (0.2, 0.1, 0.0))]
    objs[0]["transform"]["rotation_euler_xyz_rad"] = (0.0, 0.0, math.pi / 2)  # axis along +y
    grouped = Scene.model_validate({"objects": objs})
    flat = scene_of(charge("p", q, (0.2, 0.1 - d / 2, 0)), charge("n", -q, (0.2, 0.1 + d / 2, 0)))
    req = points_request([(1.0, 0.3, 0.4), (-0.7, 0.9, -0.2)])
    a, b = engine.run(grouped, req), engine.run(flat, req)
    assert np.allclose(a.arrays["p.E"], b.arrays["p.E"], rtol=1e-12, atol=0)
    assert np.allclose(a.arrays["p.phi"], b.arrays["p.phi"], rtol=1e-12, atol=0)
    assert a.header.excluded_object_ids == []  # the group itself is not "inert geometry"
    assert a.header.model_context.source_count == 2
    # On the dipole axis the field matches the independent closed form.
    on_axis = engine.run(grouped, points_request([(0.2, 0.1 + 1.3, 0.0)])).arrays["p.E"][0]
    assert on_axis[1] == pytest.approx(ref.dipole_e_on_axis(q, d, 1.3), rel=1e-12)


def test_disabling_a_group_disables_its_charges():
    objs = [o.model_dump() for o in dipole_objects("dip", "Dipole", 1e-9, 1.0)]
    objs[0]["enabled"] = False
    r = engine.run(Scene.model_validate({"objects": objs}), points_request([(1, 1, 1)]))
    assert np.all(r.arrays["p.E"] == 0) and r.header.model_context.source_count == 0


def test_dipole_preset_is_a_group_of_two_point_charges():
    preset = next(p for p in PRESETS if p.id == "electric_dipole")
    kinds = [(o.primitive.type, o.parent_id) for o in preset.scene.objects]
    assert kinds == [("group", None), ("point", "dipole"), ("point", "dipole")]
    assert preset.scene.objects[0].primitive.kind == "dipole"
    assert [o.source.charge_C for o in preset.scene.objects[1:]] == [1e-9, -1e-9]
    assert "superposition" in preset.equation_ids


def test_contributions_sum_to_the_total_field_and_potential():
    rng = np.random.default_rng(7)
    pos = rng.uniform(-1, 1, (5, 3))
    q = rng.uniform(-3e-9, 3e-9, 5)
    pts = rng.uniform(-2, 2, (40, 3))
    e_i, phi_i = es.contributions(pts, pos, q, 0.0)
    e, phi = es.evaluate(pts, pos, q, 0.0)
    assert e_i.shape == (5, 40, 3) and phi_i.shape == (5, 40)
    assert np.allclose(e_i.sum(axis=0), e, rtol=1e-12, atol=0)
    assert np.allclose(phi_i.sum(axis=0), phi, rtol=1e-12, atol=1e-25)
    # Each term is the single-charge closed form.
    r = np.linalg.norm(pts - pos[2], axis=1)
    assert np.allclose(np.linalg.norm(e_i[2], axis=1), COULOMB_K * abs(q[2]) / r**2, rtol=1e-12)
    assert np.allclose(phi_i[2], COULOMB_K * q[2] / r, rtol=1e-12)
    # |E| of the sum is not the sum of the magnitudes (vectors, not scalars, are added).
    sum_of_magnitudes = np.linalg.norm(e_i, axis=2).sum(axis=0)
    assert np.all(np.linalg.norm(e, axis=1) <= sum_of_magnitudes * (1 + 1e-12))
    assert np.any(np.linalg.norm(e, axis=1) < 0.9 * sum_of_magnitudes)


def test_per_sampling_quantities_override_the_request_default():
    scene = scene_of(charge("a", 1e-9, (0, 0, 0)))
    req = SolveRequest.model_validate({
        "samplings": [
            {"kind": "points", "id": "a", "points_m": [(1, 0, 0)]},
            {"kind": "points", "id": "b", "points_m": [(1, 0, 0)], "quantities": ["E", "D"]},
        ], "quantities": ["phi"]})
    r = engine.run(scene, req)
    assert sorted(r.arrays) == ["a.phi", "b.D", "b.E"]
    assert np.array_equal(r.arrays["b.D"], EPS0 * r.arrays["b.E"])
    units = {a.name: a.unit for a in r.header.arrays}
    assert units == {"a.phi": "V", "b.E": "V/m", "b.D": "C/m^2"}


@pytest.mark.parametrize("bad", [
    {"field_lines": {"seeding": "planar", "sampling_id": "missing"}},
    {"field_lines": {"seeding": "planar", "sampling_id": "vol"}},
    {"field_lines": {"seeding": "spherical", "sampling_id": "pts"}},
    {"equipotentials": {"sampling_id": "vol"}},
    {"field_lines": {"seeding": "spherical", "sampling_id": "heat", "levels": 9}},
])
def test_derived_product_requests_are_validated(bad):
    base = {"samplings": [
        {"kind": "plane_grid", "id": "heat", "u_extent_m": 1, "v_extent_m": 1, "nu": 4, "nv": 4},
        {"kind": "lattice", "id": "vol", "min_m": (0, 0, 0), "max_m": (1, 1, 1), "nx": 2,
         "ny": 2, "nz": 2},
        {"kind": "points", "id": "pts", "points_m": [(0, 0, 0)]}], "quantities": ["phi"]}
    with pytest.raises(ValidationError):
        SolveRequest.model_validate({**base, **bad})


def full_request() -> SolveRequest:
    return SolveRequest.model_validate({
        "samplings": [{"kind": "plane_grid", "id": "heat", "u_extent_m": 4, "v_extent_m": 4,
                       "nu": 49, "nv": 49}],
        "quantities": ["E", "phi"],
        "field_lines": {"seeding": "spherical", "sampling_id": "heat"},
        "equipotentials": {"sampling_id": "heat"},
        "isosurfaces": {"lattice": {"kind": "lattice", "id": "iso", "min_m": (-2, -2, -2),
                                    "max_m": (2, 2, 2), "nx": 17, "ny": 17, "nz": 17}},
    })


def test_physical_classification_and_method_metadata_are_kept_separate():
    scene = scene_of(charge("p", 1e-9, (-0.5, 0, 0)), charge("n", -1e-9, (0.5, 0, 0)))
    r = engine.run(scene, full_request())
    h = r.header
    assert h.classification == "exact_analytical"  # unchanged by numerical post-processing
    assert h.field_lines.method.kind == "numerical_integration"
    assert h.equipotentials.method.kind == h.isosurfaces.method.kind == "numerical_extraction"
    for product in (h.field_lines, h.equipotentials, h.isosurfaces):
        assert product.field_classification == "exact_analytical"
        m = product.method
        assert m.name.hu and m.description.hu and m.limitations and m.parameters
        assert all(lim.en and lim.hu for lim in m.limitations)
    kinds = {a.name: a.kind for a in h.arrays}
    assert kinds["heat.E"] == "field" and kinds["field_lines.points"] == "geometry"
    assert kinds["equipotentials.segments"] == kinds["isosurfaces.triangles"] == "geometry"
    # Everything survives the binary container, including the line table.
    header, arrays = wire.decode(r.to_bytes())
    assert arrays["isosurfaces.normals"].shape == arrays["isosurfaces.triangles"].shape
    assert arrays["equipotentials.segments"].shape[1:] == (2, 3)
    table = header["field_lines"]["lines"]
    assert sum(line["count"] for line in table) == arrays["field_lines.points"].shape[0]
    assert {line["end_reason"] for line in table} <= {"negative_charge", "domain_boundary"}
    assert header["field_lines"]["method"]["parameters"]["guard_radius_m"] == pytest.approx(
        0.5 * 4 / 48)


def test_requests_without_derived_products_are_unchanged_from_phase_1():
    scene = scene_of(charge("a", 1e-9, (0, 0, 0)))
    h = engine.run(scene, points_request([(1, 0, 0)])).header
    assert h.field_lines is None and h.equipotentials is None and h.isosurfaces is None
    assert Scene.model_validate({"objects": [charge("a", 1e-9, (0, 0, 0))]}).schema_version == 1


def _ctx(**kw) -> ModelContext:
    base = dict(regime="electrostatic", dimensionality="3d", medium="vacuum",
                solver_id="analytical.electrostatics.point_charges")
    return ModelContext(**{**base, **kw})


def test_registry_statuses_and_usage_are_computed_from_the_configuration():
    reg = default_registry()

    def views(scene):
        ctx = engine.run(scene, points_request([(1, 1, 1)])).header.model_context
        return {v.id: v for v in reg.evaluate(ctx)}

    none = views(scene_of())
    one = views(scene_of(charge("a", 1e-9, (0, 0, 0))))
    two = views(scene_of(charge("a", 1e-9, (0, 0, 0)), charge("b", -1e-9, (1, 0, 0))))
    zero_q = views(scene_of(charge("a", 0.0, (0, 0, 0))))

    assert two["superposition"].status == "applicable"
    assert one["superposition"].status == "applicable_under_assumptions"
    assert "single term" in one["superposition"].status_reason.en
    assert none["superposition"].status == zero_q["superposition"].status == \
        "applicable_under_assumptions"
    assert one["coulomb_field"].status == "applicable"
    assert none["coulomb_field"].status == "applicable_under_assumptions"
    assert none["laplace"].status == "applicable"
    assert one["laplace"].status == "applicable_under_assumptions"

    # Directly evaluated by the solver vs. laws the solution merely satisfies.
    for eq in ("coulomb_field", "coulomb_potential", "superposition", "constitutive_d_linear"):
        assert two[eq].usage == "evaluated" and two[eq].evaluated_by_solver
    for eq in ("gauss_electric_vacuum", "gauss_electric", "e_from_potential",
               "poisson_homogeneous", "poisson_general", "laplace"):
        assert two[eq].usage == "satisfied" and not two[eq].evaluated_by_solver
        assert "does not solve" in two[eq].usage_note.en and two[eq].usage_note.hu
    for eq in ("gauss_magnetic", "biot_savart", "ohm_local", "lorentz_force"):
        assert two[eq].usage == "not_used"
    assert two["gauss_electric_vacuum"].latex_integral  # integral form is available
    assert r"\sum_i" in two["superposition"].latex and r"\sum" not in two["coulomb_field"].latex
    for v in two.values():
        assert v.symbols and v.meaning.hu and v.intuition.hu
        assert (v.status == "applicable") == (v.status_reason is None)

    # The same rules give other answers for other models (not tied to presets).
    other = {v.id: v for v in reg.evaluate(_ctx(medium="inhomogeneous_linear", source_count=3,
                                                has_free_charge=True, has_conductors=True))}
    assert other["coulomb_field"].status == "not_applicable"
    assert other["coulomb_field"].usage == "not_used"
    assert other["superposition"].status == "applicable"
