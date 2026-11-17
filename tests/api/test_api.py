"""API contract tests (in-process, SQLite for persistence; no Redis required)."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_api.main import create_app
from emf_api.settings import Settings
from emf_core import wire
from emf_core.units import COULOMB_K
from tests.conftest import charge

V1 = "/api/v1"
SCENE = {"objects": [charge("a", 1e-9, (0, 0, 0))]}
REQUEST = {"samplings": [{"kind": "plane_grid", "id": "slice", "u_extent_m": 4, "v_extent_m": 4,
                          "nu": 8, "nv": 8}], "quantities": ["E", "phi"]}


@pytest.fixture
def client():
    settings = Settings(database_url="sqlite://", redis_url="redis://127.0.0.1:1/0",
                        sync_point_limit=10_000)
    with TestClient(create_app(settings)) as c:
        yield c


def test_simulation_returns_binary_container_and_uses_cache(client):
    r = client.post(f"{V1}/simulations", json={"scene": SCENE, "request": REQUEST})
    assert r.status_code == 200 and r.headers["content-type"] == "application/vnd.emf.result"
    assert r.headers["x-emf-cache"] == "miss"
    header, arrays = wire.decode(r.content)
    assert header["status"] == "ok" and arrays["slice.E"].shape == (8, 8, 3)
    corner = COULOMB_K * 1e-9 / np.hypot(2, 2)
    assert arrays["slice.phi"][0, 0] == pytest.approx(corner, rel=1e-6)
    # Renaming an object is display-only: served from cache without re-solving.
    renamed = {"objects": [charge("a", 1e-9, (0, 0, 0), name="renamed")]}
    r2 = client.post(f"{V1}/simulations", json={"scene": renamed, "request": REQUEST})
    assert r2.headers["x-emf-cache"] == "hit" and r2.content == r.content
    moved = {"objects": [charge("a", 1e-9, (0.1, 0, 0))]}
    assert client.post(f"{V1}/simulations", json={"scene": moved, "request": REQUEST}
                       ).headers["x-emf-cache"] == "miss"


def test_unsupported_scene_is_refused_with_localized_reasons(client):
    scene = {"objects": [{"id": "s", "primitive": {"type": "sphere"}, "role": "conductor"}]}
    for path, body in ((f"{V1}/simulations", {"scene": scene, "request": REQUEST}),
                       (f"{V1}/probe", {"scene": scene, "point_m": [1, 0, 0]})):
        r = client.post(path, json=body)
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert detail["code"] == "unsupported" and detail["reasons"][0]["hu"]
    eq = client.post(f"{V1}/equations/evaluate", json={"scene": scene}).json()
    assert eq["supported"] is False and eq["equations"] == [] and eq["unsupported_reasons"]


def test_invalid_scene_is_a_validation_error(client):
    r = client.post(f"{V1}/simulations", json={"scene": {"objects": [{"id": "x"}]},
                                               "request": REQUEST})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


def test_oversized_sync_request_is_rejected(client):
    big = {"samplings": [{**REQUEST["samplings"][0], "nu": 200, "nv": 200}], "quantities": ["E"]}
    r = client.post(f"{V1}/simulations", json={"scene": SCENE, "request": big})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"


def test_probe_returns_float64_values_with_units(client):
    r = client.post(f"{V1}/probe", json={"scene": SCENE, "point_m": [0, 2, 0]}).json()
    by = {v["quantity"]: v for v in r["values"]}
    assert r["classification"] == "exact_analytical" and r["defined"]
    assert by["E"]["unit"] == "V/m" and by["phi"]["unit"] == "V" and by["D"]["unit"] == "C/m^2"
    assert by["E"]["value"][1] == COULOMB_K * 1e-9 / 4  # exact float64, not interpolated
    assert by["phi"]["value"] == COULOMB_K * 1e-9 / 2
    at_charge = client.post(f"{V1}/probe", json={"scene": SCENE, "point_m": [0, 0, 0]}).json()
    assert at_charge["defined"] is False and at_charge["values"][0]["value"] is None


def test_equations_endpoint(client):
    r = client.post(f"{V1}/equations/evaluate", json={"scene": SCENE}).json()
    assert r["supported"] and r["solver_id"] == "analytical.electrostatics.point_charges"
    by = {e["id"]: e for e in r["equations"]}
    assert by["coulomb_field"]["status"] == "applicable" and by["coulomb_field"]["latex"]
    assert by["gauss_magnetic"]["status_reason"]["hu"]
    empty = client.post(f"{V1}/equations/evaluate", json={"scene": {}}).json()
    assert {e["id"]: e for e in empty["equations"]}["laplace"]["status"] == "applicable"


def test_solvers_and_presets_do_not_overclaim(client):
    solvers = {s["descriptor"]["id"]: s for s in client.get(f"{V1}/solvers").json()}
    assert solvers["analytical.electrostatics.point_charges"]["in_process"] is True
    for sid in ("fem.dolfinx", "fdtd.meep", "circuit.mna"):
        assert solvers[sid]["descriptor"]["available"] is False
        assert solvers[sid]["queue_worker_online"] is False
    # Redis is unreachable in this fixture: the worker must not be reported as online.
    assert solvers["analytical.electrostatics.point_charges"]["queue_worker_online"] is False
    presets = client.get(f"{V1}/presets").json()
    # Phase 3A made presets 9-11 (magnetostatics) available, Phase 3B 12-14, in addition to 1-4.
    assert len(presets) == 20 and sum(p["available"] for p in presets) == 10


def test_health_reports_unreachable_redis_as_degraded(client):
    h = client.get(f"{V1}/health").json()
    assert h["database"]["ok"] is True and h["redis"]["ok"] is False and h["status"] == "degraded"


def test_jobs_report_unavailable_queue(client):
    r = client.post(f"{V1}/jobs", json={"scene": SCENE, "request": REQUEST})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "unavailable"


def test_project_crud_round_trip(client):
    body = {"name": "My dipole", "scene": SCENE, "view": {"mode": "2d"}}
    created = client.post(f"{V1}/projects", json=body)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert [p["id"] for p in client.get(f"{V1}/projects").json()] == [pid]
    got = client.get(f"{V1}/projects/{pid}").json()
    assert got["scene"]["objects"][0]["source"]["charge_C"] == 1e-9
    assert got["view"] == {"mode": "2d"}
    body["name"] = "Renamed"
    assert client.put(f"{V1}/projects/{pid}", json=body).json()["name"] == "Renamed"
    assert client.post(f"{V1}/projects", json={"name": "bad", "scene": {"objects": [{}]}}
                       ).status_code == 422
    assert client.delete(f"{V1}/projects/{pid}").status_code == 204
    assert client.get(f"{V1}/projects/{pid}").status_code == 404


def test_database_outage_is_reported_not_hidden():
    settings = Settings(database_url="postgresql+psycopg://x:x@127.0.0.1:1/x",
                        redis_url="redis://127.0.0.1:1/0")
    with TestClient(create_app(settings)) as c:
        assert c.get(f"{V1}/projects").status_code == 503
        assert c.get(f"{V1}/health").json()["database"]["ok"] is False
        # Physics does not depend on persistence.
        assert c.post(f"{V1}/simulations", json={"scene": SCENE, "request": REQUEST}
                      ).status_code == 200
