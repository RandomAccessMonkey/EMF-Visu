"""API tests for the coaxial-cable TEM module: /coax/snapshot, /coax/trace, validation errors,
equation statuses, presets 30-31 and project persistence."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from tests.conftest import loop

V1 = "/api/v1"


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def presets(client):
    return {p["number"]: p for p in client.get(f"{V1}/presets").json()}


def snap(client, spec, t, z, **extra):
    return client.post(f"{V1}/coax/snapshot", json={
        "spec": spec, "t_s": t, "z_m": z, "range": {"start_s": 0.0, "end_s": 25e-9}, **extra})


def test_presets_30_31_snapshot(client, presets):
    a, b = presets[30], presets[31]
    assert a["coax"]["excitation"]["type"] == "sinusoidal" and b["coax"]["load"] == "open"
    assert a["scene"]["objects"] == [] and a["view_hint"]["mode"] == "3d"
    r = snap(client, b["coax"], 7e-9, 1.0, probe_m=[1e-3, 0.0])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["params"]["Z0_ohm"] == pytest.approx(49.897, abs=1e-3)
    assert d["params"]["gamma_load"] == 1.0 and d["params"]["gamma_source"] == 0.0
    assert d["probe"]["region"] == "dielectric"
    assert d["power"]["rel_error"] < 1e-10
    assert len(d["line"]["z_m"]) == 241 and d["line"]["z_m"][-1] == 2.0
    assert {c["status"] for c in d["calculus"]["checks"]} == {"agree"}
    tr = client.post(f"{V1}/coax/trace", json={
        "spec": b["coax"], "z_m": 2.0, "range": {"start_s": 0.0, "end_s": 25e-9}, "count": 101})
    assert tr.status_code == 200, tr.text
    t = tr.json()
    assert len(t["t_s"]) == 101 and max(abs(i) for i in t["I_load"]) < 1e-15
    assert max(t["V_load"]) == pytest.approx(2.0, rel=2e-2)


def test_boundary_probe_reports_surface_quantities(client, presets):
    d = snap(client, presets[31]["coax"], 5e-9, 0.2, probe_m=[0.5e-3, 0.0]).json()
    p = d["probe"]
    assert p["region"] == "inner_surface"
    assert p["surface_charge_C_per_m2"] == pytest.approx(d["boundary"]["rho_s_inner_C_per_m2"])
    assert p["surface_current_A_per_m"] == pytest.approx(d["boundary"]["K_z_inner_A_per_m"])
    # A probe inside a conductor: zero fields; the calculus point stays in the dielectric.
    d = snap(client, presets[31]["coax"], 5e-9, 0.2, probe_m=[0.1e-3, 0.0]).json()
    assert d["probe"]["region"] == "inner_conductor" and d["probe"]["E"] == [0.0, 0.0, 0.0]
    assert 0.5e-3 < d["calculus"]["r_m"] < 1.67e-3


@pytest.mark.parametrize("mutate", [
    lambda s: s["geometry"].update(inner_radius_m=2e-3),
    lambda s: s["geometry"].update(shield_outer_radius_m=1.0e-3),
    lambda s: s["geometry"].update(length_m=0.0),
    lambda s: s["material"].update(relative_permittivity=0.0),
    lambda s: s["material"].update(relative_permeability=-1.0),
    lambda s: s["excitation"].update(width_s=0.0),
])
def test_invalid_specs_are_422(client, presets, mutate):
    spec = presets[31]["coax"]
    mutate(spec)
    assert snap(client, spec, 1e-9, 0.5).status_code == 422


def test_out_of_range_and_round_trip_limits(client, presets):
    spec = presets[31]["coax"]
    assert snap(client, spec, 1e-9, 2.5).status_code == 422  # z > L
    spec = {**spec, "load": "short", "source": "short"}
    r = client.post(f"{V1}/coax/snapshot", json={
        "spec": spec, "t_s": 1.0, "z_m": 0.5, "range": {"start_s": 0.0, "end_s": 1.0}})
    assert r.status_code == 422 and "round trips" in r.json()["detail"]["message"]


def test_equations_for_the_coax_model(client, presets):
    r = client.post(f"{V1}/equations/evaluate", json={"scene": presets[31]["scene"],
                                                      "coax": presets[31]["coax"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["solver_ids"] == ["coax_tem_analytical"]
    eq = {e["id"]: e for e in body["equations"]}
    assert eq["coax_faraday"]["usage"] == "checked" and eq["coax_power"]["usage"] == "checked"
    assert eq["coax_e_field"]["usage"] == "evaluated" and eq["faraday"]["status"] == "applicable"
    assert eq["coulomb_field"]["status"] == "not_applicable"
    assert eq["coax_surface_charge"]["status_reason"]["en"].startswith("Interface")
    for e in body["equations"]:
        if e["category"] == "coax":
            assert e["name"]["en"] and e["name"]["hu"]
    # Without the coax model nothing changes for an ordinary scene.
    plain = client.post(f"{V1}/equations/evaluate", json={
        "scene": {"objects": [loop("l", 1.0, 0.05)]}}).json()
    peq = {e["id"]: e for e in plain["equations"]}
    assert peq["coax_e_field"]["status"] == "not_evaluated"
    assert peq["faraday"]["status"] != "not_applicable"


def test_projects_persist_the_coax_model(client, presets):
    spec = presets[30]["coax"]
    created = client.post(f"{V1}/projects", json={"name": "coax", "scene": presets[30]["scene"],
                                                  "coax": spec})
    assert created.status_code == 201, created.text
    back = client.get(f"{V1}/projects/{created.json()['id']}").json()
    assert back["coax"] == spec and back["view"] == {}
    old = client.post(f"{V1}/projects", json={"name": "old", "scene": {
        "objects": [loop("l", 1.0, 0.05)]}}).json()
    assert client.get(f"{V1}/projects/{old['id']}").json()["coax"] is None
    assert math.isfinite(spec["geometry"]["length_m"])
