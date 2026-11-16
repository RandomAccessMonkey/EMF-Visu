from __future__ import annotations

import json
import struct

import numpy as np
import pytest
from pydantic import ValidationError

from emf_core import engine, wire
from emf_core.equations import default_registry
from emf_core.equations.data import EQUATIONS
from emf_core.sampling import LatticeSampling, PlaneGridSampling
from emf_core.solvers import SolveRequest
from emf_core.solvers.base import ModelContext
from tests.conftest import charge, scene_of


def test_plane_grid_layout_is_row_major_v_then_u():
    s = PlaneGridSampling(id="g", center_m=(1, 2, 3), u_dir=(1, 0, 0), v_dir=(0, 0, 1),
                          u_extent_m=2, v_extent_m=4, nu=3, nv=5)
    pts = s.points().reshape(5, 3, 3)
    assert np.allclose(pts[0, 0], [0, 2, 1]) and np.allclose(pts[0, 2], [2, 2, 1])
    assert np.allclose(pts[4, 0], [0, 2, 5]) and np.allclose(pts[2, 1], [1, 2, 3])


def test_lattice_layout_is_z_y_x():
    s = LatticeSampling(id="l", min_m=(0, 0, 0), max_m=(1, 2, 3), nx=2, ny=3, nz=4)
    pts = s.points().reshape(4, 3, 2, 3)
    assert np.allclose(pts[3, 2, 1], [1, 2, 3]) and np.allclose(pts[0, 0, 1], [1, 0, 0])


def test_non_orthonormal_plane_is_rejected():
    with pytest.raises(ValidationError):
        PlaneGridSampling(id="g", u_dir=(1, 0, 0), v_dir=(1, 1, 0), u_extent_m=1, v_extent_m=1,
                          nu=2, nv=2)


def test_point_budget_is_enforced():
    big = {"kind": "plane_grid", "id": "a", "u_extent_m": 1, "v_extent_m": 1, "nu": 1024,
           "nv": 1024}
    with pytest.raises(ValidationError):
        SolveRequest.model_validate({"samplings": [big, {**big, "id": "b"}], "quantities": ["E"]})


def test_container_round_trip_and_alignment():
    scene = scene_of(charge("a", 1e-9, (0, 0, 0)))
    req = SolveRequest.model_validate({
        "samplings": [
            {"kind": "plane_grid", "id": "slice", "u_extent_m": 2, "v_extent_m": 2, "nu": 5,
             "nv": 3},
            {"kind": "lattice", "id": "vol", "min_m": (-1, -1, -1), "max_m": (1, 1, 1), "nx": 3,
             "ny": 3, "nz": 3},
        ],
        "quantities": ["phi", "E"],
    })
    result = engine.run(scene, req)
    blob = result.to_bytes()
    assert blob[:4] == b"EMF1"
    (hlen,) = struct.unpack("<I", blob[4:8])
    header_json = blob[8:8 + hlen].decode()
    assert "NaN" not in header_json and json.loads(header_json)["format_version"] == 1
    header, arrays = wire.decode(blob)
    assert wire.read_header(blob) == header
    assert arrays["slice.phi"].shape == (3, 5) and arrays["slice.E"].shape == (3, 5, 3)
    assert arrays["vol.E"].shape == (3, 3, 3, 3)
    for e in header["arrays"]:
        assert e["offset"] % 8 == 0 and e["dtype"] == "<f4" and e["unit"] in ("V", "V/m")
        expected = result.arrays[e["name"]].astype("<f4")
        assert np.array_equal(arrays[e["name"]], expected, equal_nan=True)
    # The lattice centre coincides with the charge: masked in the payload, counted in the header.
    assert np.isnan(arrays["vol.phi"][1, 1, 1])
    stats = next(e for e in header["arrays"] if e["name"] == "vol.phi")["stats"]
    assert stats["non_finite_count"] == 1
    assert header["solver_id"] and header["classification"] == "exact_analytical"
    assert len(header["equation_status"]) == len(EQUATIONS)


def _ctx(**kw):
    base = dict(regime="electrostatic", dimensionality="3d", medium="vacuum",
                has_free_charge=True, solver_id="analytical.electrostatics.point_charges",
                evaluated_equation_ids=["coulomb_field"])
    return ModelContext(**{**base, **kw})


def test_registry_covers_required_equations_with_complete_metadata():
    reg = default_registry()
    required = {"gauss_electric", "gauss_electric_vacuum", "gauss_magnetic", "faraday",
                "ampere_maxwell", "e_from_potential", "poisson_general", "poisson_homogeneous",
                "laplace", "ampere_static", "biot_savart", "continuity", "lorentz_force",
                "ohm_local", "poynting", "energy_density", "constitutive_d_general",
                "constitutive_d_linear", "constitutive_b_general", "constitutive_b_linear"}
    assert required <= set(reg.ids)
    for v in reg.evaluate(_ctx()):
        assert v.latex and v.name.en and v.name.hu and v.meaning.hu and v.intuition.hu
        assert v.symbols and all(s.meaning.hu for s in v.symbols)
        assert (v.status == "applicable") == (v.status_reason is None)


def test_statuses_follow_the_model_context():
    reg = default_registry()
    st = {v.id: v for v in reg.evaluate(_ctx())}
    assert st["coulomb_field"].status == "applicable" and st["coulomb_field"].evaluated_by_solver
    assert st["gauss_electric_vacuum"].status == "applicable"
    assert st["faraday"].status == "applicable_under_assumptions"
    assert st["laplace"].status == "applicable_under_assumptions"
    assert st["gauss_magnetic"].status == "not_evaluated"
    assert st["biot_savart"].status == "not_applicable"
    assert st["ohm_local"].status == "not_applicable"
    # The same rules give different answers for a different model: computed, not hard-coded.
    assert {v.id: v for v in reg.evaluate(_ctx(has_free_charge=False))}["laplace"].status == \
        "applicable"
    inhom = {v.id: v.status for v in reg.evaluate(_ctx(medium="inhomogeneous_linear"))}
    assert inhom["poisson_general"] == "applicable"
    assert inhom["poisson_homogeneous"] == "not_applicable"
    assert inhom["gauss_electric_vacuum"] == "not_applicable"
    wave = {v.id: v.status for v in reg.evaluate(_ctx(
        regime="full_wave", time_varying=True, computes_magnetic_field=True))}
    assert wave["faraday"] == "applicable" and wave["ampere_maxwell"] == "applicable"
    assert wave["e_from_potential"] == "not_applicable"
