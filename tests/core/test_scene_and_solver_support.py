from __future__ import annotations

import math

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core import engine
from emf_core.presets import PRESETS
from emf_core.scene.models import Scene
from emf_core.scene.transforms import rotation_matrix_xyz, world_position
from emf_core.solvers import UnsupportedSceneError, default_catalog
from tests.conftest import charge, points_request, scene_of

REQ = points_request([(1.0, 0.0, 0.0)])


def test_rotation_convention_matches_threejs_xyz():
    # Three.js Euler('XYZ'): rotating +x by +90 deg about z gives +y; R = Rx Ry Rz.
    assert np.allclose(rotation_matrix_xyz((0, 0, math.pi / 2)) @ [1, 0, 0], [0, 1, 0])
    r = rotation_matrix_xyz((math.pi / 2, 0, math.pi / 2))
    assert np.allclose(r @ [1, 0, 0], [0, 0, 1])  # Rz first (-> +y), then Rx (+y -> +z)


def test_parent_transform_moves_child_charge():
    parent = {"id": "g", "primitive": {"type": "box"},
              "transform": {"position_m": (1, 0, 0), "rotation_euler_xyz_rad": (0, 0, math.pi / 2),
                            "scale": (2, 2, 2)}}
    s = scene_of(parent, charge("c", 1e-9, (0.5, 0, 0), parent_id="g"))
    assert np.allclose(world_position(s, s.objects[1]), [1.0, 1.0, 0.0])
    e = engine.run(s, points_request([(1.0, 3.0, 0.0)])).arrays["p.E"][0]
    assert e[1] > 0 and abs(e[0]) < 1e-9 * e[1]


@pytest.mark.parametrize("bad", [
    {"objects": [charge("a", 1e-9, (0, 0, 0)), charge("a", 1e-9, (1, 0, 0))]},
    {"objects": [charge("a", 1e-9, (0, 0, 0), parent_id="missing")]},
    {"objects": [charge("a", 1e-9, (0, 0, 0), parent_id="b"),
                 charge("b", 1e-9, (0, 0, 0), parent_id="a")]},
    {"objects": [charge("a", float("nan"), (0, 0, 0))]},
    {"objects": [charge("a", 1e-9, (0, 0, 0), material_id="nope")]},
    {"domain": {"min_m": (0, 0, 0), "max_m": (0, 1, 1)}},
    {"materials": [{"id": "vacuum", "model": "vacuum", "relative_permittivity": 2.0}]},
    {"unknown_field": 1},
])
def test_invalid_scenes_are_rejected(bad):
    with pytest.raises(ValidationError):
        Scene.model_validate(bad)


def test_inert_geometry_is_excluded_and_reported():
    s = scene_of(charge("a", 1e-9, (0, 0, 0)), {"id": "box", "primitive": {"type": "box"}})
    with_box = engine.run(s, REQ)
    without = engine.run(scene_of(charge("a", 1e-9, (0, 0, 0))), REQ)
    assert np.array_equal(with_box.arrays["p.E"], without.arrays["p.E"])
    assert with_box.header.excluded_object_ids == ["box"]


def test_disabled_charge_does_not_contribute():
    s = scene_of(charge("a", 1e-9, (0, 0, 0)), charge("b", 5e-9, (0.5, 0, 0), enabled=False))
    ref = engine.run(scene_of(charge("a", 1e-9, (0, 0, 0))), REQ)
    assert np.array_equal(engine.run(s, REQ).arrays["p.E"], ref.arrays["p.E"])


@pytest.mark.parametrize("scene_kwargs,needle", [
    ({"objects": [{"id": "s", "primitive": {"type": "sphere"}, "role": "conductor"}]}, "conductor"),
    ({"objects": [{"id": "s", "primitive": {"type": "sphere"}, "role": "dielectric"}]},
     "dielectric"),
    ({"objects": [{"id": "s", "primitive": {"type": "sphere"}, "role": "charge_source",
                   "source": {"type": "point_charge", "charge_C": 1e-9}}]}, "not an ideal point"),
    ({"objects": [{"id": "w", "primitive": {"type": "line"}, "role": "current_source"}]},
     "current_source"),
    ({"dimensionality": "2d_planar"}, "2d_planar"),
    ({"boundaries": [{"id": "b", "type": "ground"}]}, "Boundary conditions"),
    ({"materials": [{"id": "vacuum"}, {"id": "glass", "model": "linear_dielectric",
                                       "relative_permittivity": 4.0}],
      "domain": {"background_material_id": "glass"}}, "vacuum"),
])
def test_unsupported_configurations_are_refused_never_approximated(scene_kwargs, needle):
    with pytest.raises(UnsupportedSceneError) as exc:
        engine.run(Scene.model_validate(scene_kwargs), REQ)
    assert any(needle in r.en for r in exc.value.reasons)
    assert all(r.hu for r in exc.value.reasons)


def test_catalog_reports_planned_solvers_as_unavailable():
    by_id = {d.id: d for d in default_catalog().descriptors()}
    assert by_id["analytical.electrostatics.point_charges"].available
    for sid in ("fem.dolfinx", "fdtd.meep", "circuit.mna"):
        assert not by_id[sid].available and by_id[sid].unavailable_reason is not None


def test_presets_catalog():
    # Phase 4A added preset 21 (toroid and mutual induction) after the planned 1-20; Phase 4B
    # added 22-25 (moving conductors and a test particle), Phase 4C 26-29 (passive circuits).
    assert [p.number for p in PRESETS] == list(range(1, 30))
    for p in PRESETS:
        if p.available:
            assert p.scene is not None and engine.run(p.scene, REQ).header.status == "ok"
        else:
            assert p.scene is None  # never ship a scene nobody can solve


def test_fingerprint_ignores_display_names_only():
    a = scene_of(charge("a", 1e-9, (0, 0, 0), name="one"))
    b = scene_of(charge("a", 1e-9, (0, 0, 0), name="renamed"))
    c = scene_of(charge("a", 2e-9, (0, 0, 0), name="one"))
    assert engine.physics_fingerprint(a, REQ) == engine.physics_fingerprint(b, REQ)
    assert engine.physics_fingerprint(a, REQ) != engine.physics_fingerprint(c, REQ)
