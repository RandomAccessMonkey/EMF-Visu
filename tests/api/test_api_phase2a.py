"""API tests for Phase 2A: probe behaviour at and near singularities, superposition terms,
derived products through the binary container, and cache behaviour."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire
from emf_core.units import COULOMB_K, EPS0
from tests.conftest import charge

V1 = "/api/v1"
Q = 1e-9
SCENE = {"objects": [charge("a", Q, (0, 0, 0), name="q1"), charge("b", -2 * Q, (1, 0, 0))]}


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def probe(client, point, scene=SCENE):
    r = client.post(f"{V1}/probe", json={"scene": scene, "point_m": point})
    assert r.status_code == 200
    return r.json()


def test_probe_at_the_charge_position_is_undefined_not_a_number(client):
    single = {"objects": [charge("a", Q, (0.3, -0.2, 0.1))]}
    at = probe(client, [0.3, -0.2, 0.1], single)
    assert at["defined"] is False and at["singular_object_id"] == "a"
    assert all(v["value"] is None for v in at["values"])
    assert at["contributions"][0]["E_V_per_m"] is None and at["contributions"][0]["phi_V"] is None
    # The tolerance is a floating-point position tolerance, not a neighbourhood of the charge.
    assert at["singular_tolerance_m"] == pytest.approx(1e-12 * np.sqrt(48.0))
    assert at["singular_tolerance_m"] < 1e-10


@pytest.mark.parametrize("r", [1e-3, 1e-6, 1e-9, 1e-10])
def test_probe_near_a_charge_returns_the_true_large_value(client, r):
    single = {"objects": [charge("a", Q, (0, 0, 0))]}
    near = probe(client, [0, r, 0], single)
    assert near["defined"] is True and near["singular_object_id"] is None
    by = {v["quantity"]: v for v in near["values"]}
    assert by["E"]["magnitude"] == pytest.approx(COULOMB_K * Q / r**2, rel=1e-12)
    assert by["E"]["value"][1] > 0 and by["E"]["value"][0] == 0
    assert by["phi"]["value"] == pytest.approx(COULOMB_K * Q / r, rel=1e-12)
    assert by["D"]["magnitude"] == pytest.approx(EPS0 * COULOMB_K * Q / r**2, rel=1e-12)
    assert by["D"]["unit"] == "C/m^2"


def test_probe_lists_each_charges_contribution_and_they_sum_to_the_total(client):
    p = probe(client, [0.4, 0.3, 0.0])
    by = {v["quantity"]: v for v in p["values"]}
    terms = p["contributions"]
    assert [t["object_id"] for t in terms] == ["a", "b"] and terms[0]["name"] == "q1"
    assert terms[0]["charge_C"] == Q and terms[1]["charge_C"] == -2 * Q
    assert terms[0]["distance_m"] == pytest.approx(0.5)
    assert terms[0]["phi_V"] == pytest.approx(COULOMB_K * Q / 0.5, rel=1e-12)
    assert terms[0]["E_magnitude_V_per_m"] == pytest.approx(COULOMB_K * Q / 0.25, rel=1e-12)
    total_e = np.sum([t["E_V_per_m"] for t in terms], axis=0)
    assert np.allclose(total_e, by["E"]["value"], rtol=1e-12, atol=0)
    assert sum(t["phi_V"] for t in terms) == pytest.approx(by["phi"]["value"], rel=1e-12)
    # Magnitudes do not add: the total |E| differs from the sum of the |E_i|.
    assert by["E"]["magnitude"] != pytest.approx(sum(t["E_magnitude_V_per_m"] for t in terms))


def test_simulation_returns_derived_products_and_caches_them(client):
    request = {
        "samplings": [
            {"kind": "plane_grid", "id": "heat", "u_extent_m": 4, "v_extent_m": 4, "nu": 49,
             "nv": 49, "quantities": ["E", "phi"]},
            {"kind": "plane_grid", "id": "arrows", "u_extent_m": 3.9, "v_extent_m": 3.9, "nu": 13,
             "nv": 13, "quantities": ["E", "D"]},
        ],
        "quantities": ["E", "phi"],
        "field_lines": {"seeding": "planar", "sampling_id": "heat"},
        "equipotentials": {"sampling_id": "heat"},
    }
    r = client.post(f"{V1}/simulations", json={"scene": SCENE, "request": request})
    assert r.status_code == 200 and r.headers["x-emf-cache"] == "miss"
    header, arrays = wire.decode(r.content)
    assert header["solver_version"] == "1.1.0" and header["classification"] == "exact_analytical"
    assert set(arrays) == {"heat.E", "heat.phi", "arrows.E", "arrows.D", "field_lines.points",
                           "equipotentials.segments"}
    assert np.isnan(arrays["arrows.E"]).any()  # the centre sample sits on charge "a"
    assert np.allclose(arrays["arrows.D"], EPS0 * arrays["arrows.E"].astype(np.float64),
                       rtol=1e-6, atol=0, equal_nan=True)
    fl = header["field_lines"]
    assert fl["lines_stay_in_plane"] is True and len(fl["lines"]) > 0
    assert {ln["start_reason"] for ln in fl["lines"]} <= {"positive_charge", "domain_boundary"}
    assert header["equipotentials"]["levels"][0]["value_V"] < 0
    assert header["model_context"]["source_count"] == 2
    statuses = {e["equation_id"]: e["status"] for e in header["equation_status"]}
    assert statuses["superposition"] == "applicable"
    again = client.post(f"{V1}/simulations", json={"scene": SCENE, "request": request})
    assert again.headers["x-emf-cache"] == "hit" and again.content == r.content
    # A physical change (polarity) misses the cache; so does a different charge count.
    flipped = {"objects": [charge("a", -Q, (0, 0, 0), name="q1"), charge("b", -2 * Q, (1, 0, 0))]}
    assert client.post(f"{V1}/simulations", json={"scene": flipped, "request": request}
                       ).headers["x-emf-cache"] == "miss"
    fewer = {"objects": SCENE["objects"][:1]}
    assert client.post(f"{V1}/simulations", json={"scene": fewer, "request": request}
                       ).headers["x-emf-cache"] == "miss"


def test_equations_endpoint_reports_usage(client):
    eq = client.post(f"{V1}/equations/evaluate", json={"scene": SCENE}).json()
    by = {e["id"]: e for e in eq["equations"]}
    assert by["superposition"]["usage"] == "evaluated"
    assert by["poisson_homogeneous"]["usage"] == "satisfied"
    assert by["poisson_homogeneous"]["usage_note"]["hu"]
    assert by["biot_savart"]["usage"] == "not_used"


def test_dipole_preset_is_solvable_through_the_api(client):
    presets = {p["id"]: p for p in client.get(f"{V1}/presets").json()}
    scene = presets["electric_dipole"]["scene"]
    assert scene["objects"][0]["primitive"] == {"type": "group", "kind": "dipole"}
    mid = probe(client, [0.0, 0.7, 0.0], scene)
    by = {v["quantity"]: v for v in mid["values"]}
    assert by["phi"]["value"] == 0.0  # symmetry plane of the dipole
    assert by["E"]["value"][0] > 0 and abs(by["E"]["value"][1]) < 1e-12 * by["E"]["value"][0]
