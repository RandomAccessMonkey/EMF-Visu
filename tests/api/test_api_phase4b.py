"""API tests for Phase 4B: moving measurement conductors through /induction, the Lorentz-force
probe, test-particle trajectories, equation statuses, presets 22-25 and persistence."""

from __future__ import annotations

import math

import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from tests.conftest import loop

V1 = "/api/v1"
Q, M = 1.602176634e-19, 1.67262192369e-27


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.fixture
def presets(client):
    return {p["number"]: p for p in client.get(f"{V1}/presets").json()}


def induction(client, scene, surfaces, t, **extra):
    r = client.post(f"{V1}/induction", json={"scene": scene, "induction": {
        "surfaces": surfaces, "time_s": t, **extra}})
    assert r.status_code == 200, r.text
    return r.json(), r.headers["X-EMF-Cache"]


def test_presets_22_to_25_are_available_and_reproducible(client, presets):
    for n in (22, 23, 24, 25):
        p = presets[n]
        assert p["available"] and p["scene"] and p["description"]["hu"]
        assert p["equation_ids"] and p["view_hint"]
    # Existing preset ids and meanings are preserved.
    assert presets[15]["id"] == "changing_b_in_loop" and presets[16]["id"] == "faraday_induction"
    assert presets[21]["id"] == "toroid_mutual_induction"
    p = presets[22]
    a, _ = induction(client, p["scene"], p["flux_surfaces"], 0.1)
    b, hit = induction(client, p["scene"], p["flux_surfaces"], 0.1)
    assert hit == "hit" and a == b
    s = a["surfaces"][0]
    assert s["status"] == "verified" and s["moving"] and s["motion"]["kind"] == "sliding_rod"
    assert s["emf_motional_V"] < 0 and s["emf_V"] == 0.0
    assert s["reference"]["kind"] == "sliding_rod_BLv"
    assert s["derivative"]["method"] == "central" and s["derivative"]["converged"]


def test_velocity_convention_at_a_jump(client, presets):
    p = presets[22]
    undefined, _ = induction(client, p["scene"], p["flux_surfaces"], 0.3)
    assert undefined["surfaces"][0]["status"] == "motion_undefined"
    left, _ = induction(client, p["scene"], p["flux_surfaces"], 0.3,
                        velocity_convention="left")
    s = left["surfaces"][0]
    assert s["status"] == "verified" and s["motion"]["side"] == "left"
    assert s["derivative"]["method"] == "backward"


def test_rotating_coil_and_turns(client, presets):
    p = presets[23]
    one, _ = induction(client, p["scene"], p["flux_surfaces"], 0.125)
    surf = {**p["flux_surfaces"][0], "turns": 10}
    ten, _ = induction(client, p["scene"], [surf], 0.125)
    a, b = one["surfaces"][0], ten["surfaces"][0]
    assert a["status"] == b["status"] == "verified" and b["turns"] == 10
    assert b["emf_total_V"] == pytest.approx(10 * a["emf_total_V"], rel=1e-12)
    assert b["flux_Wb"] == pytest.approx(10 * a["flux_Wb"], rel=1e-12)
    assert a["reference"]["kind"] == "rotating_coil"
    assert len(a["motional_samples"]) > 8 and a["motion"]["angular_velocity_rad_per_s"][0] > 0


def test_lorentz_endpoint(client, presets):
    p = presets[24]
    tc = p["test_charge"]
    r = client.post(f"{V1}/lorentz", json={"scene": p["scene"], "lorentz": {
        "charge_C": tc["charge_C"], "velocity_m_per_s": tc["velocity_m_per_s"],
        "point_m": tc["position_m"], "time_s": 0.0}})
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["status"] == "complete" and f["F_E_magnitude_N"] == 0.0
    assert f["F_B_magnitude_N"] > 0 and abs(f["power_B_W"]) <= f["power_B_bound_W"]
    bad = client.post(f"{V1}/lorentz", json={"scene": p["scene"], "lorentz": {
        "charge_C": "x", "velocity_m_per_s": [0, 0, 0], "point_m": [0, 0, 0]}})
    assert bad.status_code == 422


def test_particle_endpoint_and_cache(client, presets):
    p = presets[24]
    tc = p["test_charge"]
    body = {"scene": p["scene"], "particle": {
        "charge_C": tc["charge_C"], "mass_kg": tc["mass_kg"], "position_m": tc["position_m"],
        "velocity_m_per_s": tc["velocity_m_per_s"], "start_s": 0.0, "end_s": 1.1e-4}}
    r = client.post(f"{V1}/particle", json=body)
    assert r.status_code == 200 and r.headers["X-EMF-Cache"] == "miss"
    tr = r.json()
    assert tr["status"] == "completed" and tr["magnetic_only"]
    assert abs(tr["energy_relative_change"]) < 1e-12
    assert tr["samples"][-1]["t_s"] == pytest.approx(1.1e-4)
    assert client.post(f"{V1}/particle", json=body).headers["X-EMF-Cache"] == "hit"
    fast = {**body["particle"], "velocity_m_per_s": [3.1e8, 0, 0]}
    assert client.post(f"{V1}/particle", json={**body, "particle": fast}).status_code == 422


def test_equation_statuses_for_moving_conductors_and_test_charges(client, presets):
    p = presets[23]

    def statuses(**extra):
        r = client.post(f"{V1}/equations/evaluate", json={"scene": p["scene"], **extra})
        assert r.status_code == 200
        return {e["id"]: e["status"] for e in r.json()["equations"]}

    none = statuses()
    assert none["motional_emf"] == "not_evaluated" and none["lorentz_force"] == "not_evaluated"
    assert none["sliding_rod_emf"] == "not_applicable"
    moving = statuses(flux_surfaces=p["flux_surfaces"])
    assert moving["motional_emf"] == "applicable_under_assumptions"
    assert moving["generalized_faraday"] == "applicable_under_assumptions"
    assert moving["rotating_coil_flux"] == "applicable_under_assumptions"
    charged = statuses(test_charge=presets[24]["test_charge"])
    assert charged["lorentz_force"] == "applicable_under_assumptions"
    assert charged["newton_lorentz"] == "applicable_under_assumptions"


def test_projects_persist_moving_surfaces_and_test_charge(client, presets):
    p22, p24 = presets[22], presets[24]
    surfaces = [*p22["flux_surfaces"], {
        "id": "F2", "shape": {"type": "circle", "radius_m": 0.02}, "turns": 3,
        "motion": {"translation": {"type": "sinusoidal", "amplitude_m": 0.01,
                                   "axis": [0, 0, 1], "frequency_Hz": 2.0}}}]
    created = client.post(f"{V1}/projects", json={
        "name": "4b", "scene": p22["scene"], "view": {"timeS": 0.1},
        "flux_surfaces": surfaces, "test_charge": p24["test_charge"]})
    assert created.status_code == 201, created.text
    back = client.get(f"{V1}/projects/{created.json()['id']}").json()
    assert back["flux_surfaces"][0]["shape"]["type"] == "sliding_rod"
    assert back["flux_surfaces"][1]["turns"] == 3
    assert back["flux_surfaces"][1]["motion"]["translation"]["frequency_Hz"] == 2.0
    assert back["test_charge"] == p24["test_charge"] and back["view"] == {"timeS": 0.1}
    # Projects saved before Phase 4B load unchanged: stationary surfaces, no test charge.
    old = client.post(f"{V1}/projects", json={
        "name": "old", "scene": {"objects": [loop("l", 1.0, 0.05)]},
        "flux_surfaces": [{"id": "F1", "shape": {"type": "circle", "radius_m": 0.03}}]}).json()
    again = client.get(f"{V1}/projects/{old['id']}").json()
    assert again["test_charge"] is None
    assert again["flux_surfaces"] == [{"id": "F1", "name": "", "shape": {
        "type": "circle", "radius_m": 0.03}, "center_m": [0.0, 0.0, 0.0],
        "rotation_euler_xyz_rad": [0.0, 0.0, 0.0], "reversed": False, "rtol": 1e-4,
        "display": None}]
    assert math.isfinite(again["flux_surfaces"][0]["rtol"])
