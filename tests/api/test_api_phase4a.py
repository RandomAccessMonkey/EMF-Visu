"""API tests for Phase 4A: time-dependent magnetic requests, the probe at a simulation time,
/induction (flux, Faraday, Lenz, mutual inductance), equation statuses, presets 15, 16, 21,
persistence of profiles and measurement surfaces, and backward compatibility."""

from __future__ import annotations

import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire as wire_format
from tests.conftest import charge, loop, solenoid, wire

V1 = "/api/v1"
SINE = {"type": "sinusoidal", "dc_A": 0.0, "peak_A": 2.0, "frequency_Hz": 1.0, "phase_rad": 0.0}


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


def driven_loop(oid="l", radius=0.05, profile=SINE, i0=0.0):
    obj = loop(oid, i0, radius)
    obj["source"]["profile"] = profile
    return obj


def solve(client, scene, points, t, quantities=("B", "dB_dt", "E_ind")):
    r = client.post(f"{V1}/simulations", json={"scene": scene, "request": {
        "samplings": [{"kind": "points", "id": "p", "points_m": points}],
        "quantities": list(quantities), "time_s": t}})
    assert r.status_code == 200, r.text
    header, arrays = wire_format.decode(r.content)
    return header, arrays, r.headers["X-EMF-Cache"]


def test_time_dependent_solve_units_and_header(client):
    scene = {"objects": [driven_loop()]}
    header, arrays, _ = solve(client, scene, [[0.02, 0.0, 0.01]], 0.1)
    units = {a["quantity"]: a["unit"] for a in header["arrays"]}
    assert units == {"B": "T", "dB_dt": "T/s", "E_ind": "V/m"}
    ind = header["induction"]
    assert ind["time_dependent"] and ind["e_ind_available"]
    assert ind["regime"] == "magnetoquasistatic"
    ts = header["time_sources"][0]
    assert ts["current_A"] == pytest.approx(2 * math.sin(0.2 * math.pi))
    assert ts["dI_dt_A_per_s"] == pytest.approx(4 * math.pi * math.cos(0.2 * math.pi))
    assert header["model_context"]["regime"] == "quasi_static"
    # A different time is a different physics key; the same time is a cache hit.
    assert solve(client, scene, [[0.02, 0.0, 0.01]], 0.1)[2] == "hit"
    assert solve(client, scene, [[0.02, 0.0, 0.01]], 0.2)[2] == "miss"


def test_electric_requests_ignore_profiles_and_mixing_is_refused(client):
    q = charge("q", 1e-9, (0.5, 0.5, 0))
    pts = [{"kind": "points", "id": "p", "points_m": [[0, 0.3, 0]]}]
    r = client.post(f"{V1}/simulations", json={
        "scene": {"objects": [q, driven_loop()]},
        "request": {"samplings": pts, "quantities": ["E", "E_ind"]}})
    assert r.status_code == 422
    e1 = client.post(f"{V1}/simulations", json={
        "scene": {"objects": [q]}, "request": {"samplings": pts, "quantities": ["E"]}})
    e2 = client.post(f"{V1}/simulations", json={
        "scene": {"objects": [q, driven_loop()]},
        "request": {"samplings": pts, "quantities": ["E"]}})
    assert e2.headers["X-EMF-Cache"] == "hit"
    assert wire_format.decode(e1.content)[1]["p.E"].tolist() == \
        wire_format.decode(e2.content)[1]["p.E"].tolist()


def test_probe_at_a_time(client):
    scene = {"objects": [driven_loop()]}
    r = client.post(f"{V1}/probe", json={"scene": scene, "point_m": [0.02, 0.0, 0.01],
                                         "time_s": 0.0}).json()["magnetic"]
    assert r["time_s"] == 0.0 and r["time_dependent"] and r["e_ind_available"]
    vals = {v["quantity"]: v for v in r["time_values"]}
    assert vals["E_ind"]["unit"] == "V/m" and vals["E_ind"]["value"][1] < 0  # Lenz
    assert vals["dB_dt"]["value"][2] > 0
    b = {v["quantity"]: v for v in r["values"]}["B"]
    assert b["magnitude"] == 0.0  # I(0) = 0
    c = r["contributions"][0]
    assert c["dI_dt_A_per_s"] == pytest.approx(4 * math.pi)
    assert np.allclose(c["E_ind_V_per_m"], vals["E_ind"]["value"], rtol=1e-12)
    on = client.post(f"{V1}/probe", json={"scene": scene, "point_m": [0.05, 0.0, 0.0],
                                          "time_s": 0.1}).json()["magnetic"]
    tv = {v["quantity"]: v for v in on["time_values"]}
    assert tv["E_ind"]["status"] == "singular" and tv["E_ind"]["value"] is None
    w = wire("w", 0.0, (0.3, 0, 0))
    w["source"]["profile"] = SINE
    un = client.post(f"{V1}/probe", json={"scene": {"objects": [w]}, "point_m": [0.1, 0, 0],
                                          "time_s": 0.1}).json()["magnetic"]
    tv = {v["quantity"]: v for v in un["time_values"]}
    assert not un["e_ind_available"] and tv["E_ind"]["status"] == "not_evaluated"
    assert tv["dB_dt"]["status"] == "defined"


def induction(client, scene, surfaces, t, mutual=True):
    r = client.post(f"{V1}/induction", json={"scene": scene, "induction": {
        "surfaces": surfaces, "time_s": t, "mutual": mutual}})
    assert r.status_code == 200, r.text
    return r.json(), r.headers["X-EMF-Cache"]


def test_induction_endpoint_and_cache(client):
    scene = {"objects": [driven_loop()]}
    surf = [{"id": "F", "shape": {"type": "circle", "radius_m": 0.03}, "center_m": [0, 0, 0.02]}]
    body, cache = induction(client, scene, surf, 0.1)
    assert cache == "miss" and body["regime"] == "magnetoquasistatic" and body["method"]["hu"]
    (s,) = body["surfaces"]
    assert s["status"] == "verified"
    assert s["emf_V"] == pytest.approx(-s["dflux_dt_V"], rel=1e-8)
    assert s["lenz"] == {"flux_trend": "increasing", "emf_sign": -1, "circulation": "against_path"}
    assert s["mutual"][0]["reciprocity_ok"]
    assert induction(client, scene, surf, 0.1)[1] == "hit"
    later, _ = induction(client, scene, surf, 0.6)
    assert later["surfaces"][0]["lenz"]["circulation"] == "along_path"
    bad = [{"id": "B", "shape": {"type": "polygon", "closed": False,
                                 "vertices_m": [[0, 0, 0], [0.1, 0, 0], [0, 0.1, 0]]}}]
    assert induction(client, scene, bad, 0.0)[0]["surfaces"][0]["status"] == "invalid"


def test_equation_statuses_follow_time_dependence(client):
    def eqs(scene, flux=()):
        r = client.post(f"{V1}/equations/evaluate", json={"scene": scene,
                                                          "flux_surfaces": list(flux)})
        return {e["id"]: e for e in r.json()["equations"]}

    static = eqs({"objects": [loop("l", 1.0, 0.05)]})
    assert static["e_ind_from_a"]["status"] == "not_applicable"
    assert static["current_constant"]["status"] == "applicable"
    assert static["current_sinusoidal"]["status"] == "not_applicable"
    driven = eqs({"objects": [driven_loop()]},
                 [{"id": "F", "shape": {"type": "circle", "radius_m": 0.03},
                   "center_m": [0, 0, 0.02]}])
    assert driven["current_sinusoidal"]["usage"] == "evaluated"
    assert driven["e_ind_from_a"]["status"] == "applicable_under_assumptions"
    assert driven["e_ind_from_a"]["usage"] == "evaluated"
    assert driven["faraday_integral"]["usage"] == "checked"
    assert driven["mutual_reciprocity"]["usage"] == "checked"
    assert driven["ampere_integral"]["status"] != "not_applicable"
    assert driven["magnetoquasistatic"]["name"]["hu"]
    assert driven["e_decomposition"]["status"] == "applicable_under_assumptions"


def test_presets_15_16_21_reproducible(client):
    presets = {p["number"]: p for p in client.get(f"{V1}/presets").json()}
    for n in (15, 16, 21):
        p = presets[n]
        assert p["available"] and p["flux_surfaces"] and p["time"] is not None
        assert p["view_hint"]["probe_m"] is not None and p["name"]["hu"]
        t = p["time"]["initial_s"] or p["time"]["step_s"] * 7
        a, _ = induction(client, p["scene"], p["flux_surfaces"], t)
        b, _ = induction(client, p["scene"], p["flux_surfaces"], t)
        assert a == b and a["surfaces"][0]["status"] == "verified", n
    assert presets[15]["id"] == "changing_b_in_loop" and presets[16]["id"] == "faraday_induction"
    assert presets[17]["available"] is False  # still planned (electrostatic + induced)
    m = induction(client, presets[21]["scene"], presets[21]["flux_surfaces"],
                  0.003)[0]["surfaces"][0]["mutual"][0]
    assert m["M12_H"] > 0 and m["reciprocity_ok"]


def test_projects_persist_profiles_surfaces_and_time(client):
    scene = {"objects": [driven_loop(), solenoid("s", current=0.0)]}
    scene["objects"][1]["source"]["profile"] = {
        "type": "piecewise_linear", "keyframes": [{"t_s": 0, "current_A": 0},
                                                  {"t_s": 0.5, "current_A": 3},
                                                  {"t_s": 1.0, "current_A": -1}]}
    surf = {"id": "F", "name": "disk", "shape": {"type": "circle", "radius_m": 0.03},
            "center_m": [0, 0, 0.02], "reversed": True}
    view = {"timeS": 0.37, "timeStart": 0, "timeEnd": 2, "timeStep": 0.01}
    created = client.post(f"{V1}/projects", json={"name": "4a", "scene": scene, "view": view,
                                                  "flux_surfaces": [surf]}).json()
    back = client.get(f"{V1}/projects/{created['id']}").json()
    assert back["scene"]["objects"][0]["source"]["profile"] == SINE
    assert back["scene"]["objects"][1]["source"]["profile"]["keyframes"][1] == \
        {"t_s": 0.5, "current_A": 3.0}
    assert back["flux_surfaces"][0]["reversed"] is True and back["view"]["timeS"] == 0.37
    assert "flux_surfaces" not in back["view"]
    old = client.post(f"{V1}/projects", json={"name": "old", "scene": {
        "objects": [loop("l", 2.0, 0.3)]}, "view": {}}).json()
    again = client.get(f"{V1}/projects/{old['id']}").json()
    assert again["flux_surfaces"] == [] and "profile" not in again["scene"]["objects"][0]["source"]
