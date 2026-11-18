"""API tests for Phase 4C: /circuits (passive circuits, braking, eddy disk), the field and the
probe with induced currents, equation statuses, presets 26-29 and persistence."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire as wire_format
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


def circuits(client, p):
    body = {"scene": p["scene"], "circuits": {
        "circuits": p["circuits"], "disks": p["eddy_disks"], "start_s": p["time"]["start_s"],
        "end_s": p["time"]["end_s"], "step_s": p["time"]["step_s"]}}
    r = client.post(f"{V1}/circuits", json=body)
    assert r.status_code == 200, r.text
    return r.json(), r.headers["X-EMF-Cache"], body


def test_presets_26_to_29_solve_and_are_cached(client, presets):
    for n in (26, 28, 29):
        p = presets[n]
        assert p["available"] and p["description"]["hu"] and p["time"]
        res, cache, body = circuits(client, p)
        assert res["status"] == "solved" and cache == "miss"
        assert client.post(f"{V1}/circuits", json=body).headers["X-EMF-Cache"] == "hit"
        s = res["series"]
        assert len(s["t_s"]) == len(s["current_A"][0])
        assert max(abs(x) for x in s["energy_residual_J"]) < 1e-6 * max(s["joule_heat_J"][-1],
                                                                         1e-30)
    assert presets[21]["id"] == "toroid_mutual_induction" and presets[25]["number"] == 25
    disk = circuits(client, presets[28])[0]
    assert len(disk["elements"]) == 20 and disk["elements"][0]["kind"] == "band"
    assert disk["series"]["current_density_A_per_m2"][5] is not None
    pair = circuits(client, presets[29])[0]
    m = pair["matrix"]["values_H"]
    assert m[0][1] == m[1][0] and pair["matrix"]["positive_definite"]


def test_braking_preset_27(client, presets):
    res, _, _ = circuits(client, presets[27])
    assert res["status"] == "stopped"
    s = res["series"]
    assert s["rod_velocity_m_per_s"][-1] < s["rod_velocity_m_per_s"][0]
    assert all(f[0] < 0 for f in s["force_N"][0][1:])


def test_invalid_and_unsupported_requests(client, presets):
    p = presets[26]
    bad = {**p["circuits"][0], "path": {**p["circuits"][0]["path"],
                                         "shape": {"type": "rectangle", "width_m": 0.04,
                                                   "height_m": 0.02}}}
    r = client.post(f"{V1}/circuits", json={"scene": p["scene"], "circuits": {
        "circuits": [bad], "start_s": 0, "end_s": 0.1, "step_s": 0.01}}).json()
    assert r["status"] == "invalid" and r["problems"]
    assert client.post(f"{V1}/circuits", json={"scene": p["scene"], "circuits": {
        "circuits": [], "start_s": 0, "end_s": 0.1, "step_s": 0.01}}).status_code == 422


def test_field_and_probe_include_induced_currents(client, presets):
    p = presets[26]
    res, _, _ = circuits(client, p)
    k = 50
    fil = {**res["series"]["filaments"][0][0], "current_A": res["series"]["current_A"][0][k],
           "rate_A_per_s": res["series"]["dI_dt_A_per_s"][0][k]}
    t = res["series"]["t_s"][k]
    r = client.post(f"{V1}/simulations", json={"scene": p["scene"], "request": {
        "samplings": [{"kind": "points", "id": "p", "points_m": [[0.0, 0.0, 0.02]]}],
        "quantities": ["B", "B_prescribed", "B_passive", "E_ind"], "time_s": t,
        "passive": [fil]}})
    assert r.status_code == 200, r.text
    header, arrays = wire_format.decode(r.content)
    b, bp, bq = arrays["p.B"], arrays["p.B_prescribed"], arrays["p.B_passive"]
    assert np.allclose(b, bp + bq, rtol=1e-6) and bq[0, 2] * bp[0, 2] < 0  # Lenz
    assert header["induction"]["passive_ids"] == ["P1"]
    probe = client.post(f"{V1}/probe", json={"scene": p["scene"], "point_m": [0.0, 0.0, 0.02],
                                             "time_s": t, "passive": [fil]}).json()
    pm = probe["magnetic"]["passive"]
    assert pm["contributions"][0]["circuit_id"] == "P1"
    total = np.add(pm["B_prescribed_T"], pm["B_passive_T"])
    assert np.allclose(total, pm["B_total_T"]) and np.allclose(
        probe["magnetic"]["values"][0]["value"], total, rtol=1e-12)


def test_equation_statuses_for_circuits(client, presets):
    p = presets[28]
    r = client.post(f"{V1}/equations/evaluate", json={"scene": p["scene"]}).json()
    st = {e["id"]: e["status"] for e in r["equations"]}
    assert st["coupled_band_dynamics"] == "not_evaluated"
    r = client.post(f"{V1}/equations/evaluate", json={
        "scene": p["scene"], "eddy_disks": p["eddy_disks"]}).json()
    st = {e["id"]: e for e in r["equations"]}
    assert st["coupled_band_dynamics"]["status"] == "applicable_under_assumptions"
    assert st["rotational_dynamics"]["status"] == "not_evaluated"
    assert st["coupled_band_dynamics"]["category"] == "circuits"


def test_projects_persist_circuits_and_disks(client, presets):
    p27, p28 = presets[27], presets[28]
    created = client.post(f"{V1}/projects", json={
        "name": "4c", "scene": p27["scene"], "circuits": p27["circuits"],
        "eddy_disks": p28["eddy_disks"]})
    assert created.status_code == 201, created.text
    back = client.get(f"{V1}/projects/{created.json()['id']}").json()
    assert back["circuits"] == p27["circuits"] and back["eddy_disks"] == p28["eddy_disks"]
    assert back["circuits"][0]["mechanics"]["mode"] == "dynamic"
    old = client.post(f"{V1}/projects", json={"name": "old", "scene": {
        "objects": [loop("l", 1.0, 0.05)]}}).json()
    again = client.get(f"{V1}/projects/{old['id']}").json()
    assert again["circuits"] == [] and again["eddy_disks"] == [] and again["view"] == {}
