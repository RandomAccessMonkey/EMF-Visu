"""API tests for Phase 2B-1: probe divergence/curl values, units, statuses, distributional
information at a charge, finite-difference diagnostics, and the source table in results."""

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
SCENE = {"objects": [charge("a", 1e-9, (0, 0, 0), name="q1"), charge("b", -2e-9, (1, 0, 0.3))]}
UNITS = {"E": "V/m", "phi": "V", "D": "C/m^2", "div_E": "V/m^2", "curl_E": "V/m^2",
         "div_D": "C/m^3", "curl_D": "C/m^3"}


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def probe(client, point, scene=SCENE):
    r = client.post(f"{V1}/probe", json={"scene": scene, "point_m": point})
    assert r.status_code == 200
    return r.json()


def test_ordinary_point_reports_exact_zero_divergence_and_curl_with_units(client):
    p = probe(client, [0.4, 0.3, 0.1])
    by = {v["quantity"]: v for v in p["values"]}
    assert list(by) == ["E", "phi", "D", "div_E", "curl_E", "div_D", "curl_D"]
    assert {k: v["unit"] for k, v in by.items()} == UNITS
    assert {k: v["kind"] for k, v in by.items()} == {
        "E": "vector", "phi": "scalar", "D": "vector", "div_E": "scalar", "curl_E": "vector",
        "div_D": "scalar", "curl_D": "vector"}
    assert all(v["status"] == "defined" for v in by.values())
    assert by["E"]["magnitude"] > 1.0  # the field is clearly nonzero ...
    assert by["div_E"]["value"] == 0.0 and by["div_D"]["value"] == 0.0  # ... its divergence is 0
    assert by["curl_E"]["value"] == [0.0, 0.0, 0.0] and by["curl_E"]["magnitude"] == 0.0
    assert by["curl_D"]["value"] == [0.0, 0.0, 0.0] and by["curl_D"]["magnitude"] == 0.0
    assert by["D"]["magnitude"] == pytest.approx(EPS0 * by["E"]["magnitude"], rel=1e-15)
    assert p["distributional"] is None


def test_diagnostics_are_numerical_estimates_consistent_with_the_exact_zeros(client):
    p = probe(client, [0.4, 0.3, 0.1])
    diags = {d["quantity"]: d for d in p["diagnostics"]}
    assert set(diags) == {"div_E", "curl_E", "div_D", "curl_D"}
    for q, d in diags.items():
        assert d["unit"] == UNITS[q] and d["consistent_with_exact"] is True
        assert d["exact"] in (0.0, [0.0, 0.0, 0.0])
        assert d["step_m"] == pytest.approx(1e-3 * 0.5099019513592785)  # 1e-3 * nearest distance
        est = np.atleast_1d(d["estimate"])
        unc = np.atleast_1d(d["uncertainty"])
        assert np.all(np.abs(est) <= unc) and np.all(unc > 0)
    # The estimate is rarely exactly zero: round-off is reported with its uncertainty, and the
    # uncertainty is small compared with the derivative scale K|q|/r^3 of the field.
    assert diags["div_E"]["uncertainty"] < 1e-5 * COULOMB_K * 1e-9 / 0.5**3
    assert "Richardson" in p["diagnostics_method"]


def test_probe_at_a_charge_reports_singular_values_and_the_distributional_statement(client):
    p = probe(client, [0, 0, 0])
    by = {v["quantity"]: v for v in p["values"]}
    for q in ("E", "phi", "D"):
        assert by[q]["status"] == "singular" and by[q]["value"] is None
    for q in ("div_E", "curl_E", "div_D", "curl_D"):
        assert by[q]["status"] == "not_evaluated" and by[q]["value"] is None
    dist = p["distributional"]
    assert dist["object_id"] == "a" and dist["name"] == "q1" and dist["charge_C"] == 1e-9
    assert dist["div_E_weight_V_m"] == 1e-9 / EPS0 and dist["div_D_weight_C"] == 1e-9
    assert dist["curl_E_distributional"] == [0.0, 0.0, 0.0]
    assert dist["curl_D_distributional"] == [0.0, 0.0, 0.0]
    assert p["diagnostics"] == []  # no finite differences across a singularity


def test_probe_near_a_charge_is_an_ordinary_point(client):
    p = probe(client, [0, 1e-10, 0])
    by = {v["quantity"]: v for v in p["values"]}
    assert all(v["status"] == "defined" for v in by.values())
    assert by["div_E"]["value"] == 0.0 and by["curl_E"]["value"] == [0.0, 0.0, 0.0]
    assert by["E"]["magnitude"] == pytest.approx(COULOMB_K * 1e-9 / 1e-20, rel=1e-6)
    assert p["distributional"] is None
    assert all(d["consistent_with_exact"] for d in p["diagnostics"])


def test_simulation_transports_differential_arrays_and_the_source_table(client):
    request = {
        "samplings": [{"kind": "plane_grid", "id": "arrows", "u_extent_m": 4, "v_extent_m": 4,
                       "nu": 9, "nv": 9, "quantities": ["E", "div_E", "curl_E", "div_D",
                                                         "curl_D"]}],
        "quantities": ["phi"]}
    r = client.post(f"{V1}/simulations", json={"scene": SCENE, "request": request})
    header, arrays = wire.decode(r.content)
    assert arrays["arrows.curl_E"].shape == (9, 9, 3) and arrays["arrows.div_D"].shape == (9, 9)
    centre = np.isnan(arrays["arrows.div_E"])
    assert centre.sum() == 1 and centre[4, 4]  # the sample on charge "a" is not evaluated
    assert np.all(arrays["arrows.div_E"][~centre] == 0)
    assert np.all(np.linalg.norm(arrays["arrows.E"][~centre], axis=1) > 0)
    srcs = {s["object_id"]: s for s in header["point_sources"]}
    assert srcs["a"]["in_plane"] == {"arrows": True}
    assert srcs["b"]["plane_distance_m"]["arrows"] == pytest.approx(0.3)
    assert srcs["b"]["div_D_weight_C"] == -2e-9
    eq = {e["equation_id"]: e["status"] for e in header["equation_status"]}
    assert eq["div_E_point_charges"] == eq["curl_E_electrostatic"] == "applicable"
