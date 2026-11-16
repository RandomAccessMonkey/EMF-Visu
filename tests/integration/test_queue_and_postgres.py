"""Integration tests against real services: Redis + a real Celery worker process, and
PostgreSQL. Auto-skipped when the service is unreachable (see README for how to start them)."""

from __future__ import annotations

import os
import subprocess
import sys
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from emf_core import wire
from tests.conftest import charge

pytestmark = pytest.mark.integration
V1 = "/api/v1"
REDIS_URL = os.environ.get("EMF_REDIS_URL", "redis://localhost:6379/0")
PG_URL = os.environ.get("EMF_TEST_DATABASE_URL",
                        "postgresql+psycopg://emf:emf@localhost:5432/emf_test")
SCENE = {"objects": [charge("a", 1e-9, (0.3, 0, 0)), charge("b", -2e-9, (-0.3, 0, 0))]}
BIG = {"samplings": [{"kind": "lattice", "id": "vol", "min_m": (-2, -2, -2), "max_m": (2, 2, 2),
                      "nx": 100, "ny": 100, "nz": 100}], "quantities": ["E", "phi"],
       "quality": "high"}


def _redis_ok() -> bool:
    import redis
    try:
        redis.Redis.from_url(REDIS_URL, socket_connect_timeout=0.5).ping()
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="module")
def worker():
    if not _redis_ok():
        pytest.skip("Redis is not reachable")
    from emf_worker.client import JobClient
    jobs = JobClient(REDIS_URL)
    proc = subprocess.Popen(
        [sys.executable, "-m", "celery", "-A", "emf_worker.app", "worker", "-Q",
         "solver.analytical", "--pool", "solo", "--loglevel", "WARNING", "-n", "pytest@%h"],
        env={**os.environ, "EMF_REDIS_URL": REDIS_URL},
    )
    try:
        deadline = time.time() + 30
        while "solver.analytical" not in jobs.online_queues(1.0):
            if proc.poll() is not None or time.time() > deadline:
                pytest.fail("Celery worker did not come online")
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=20)


@pytest.fixture
def client():
    from emf_api.main import create_app
    from emf_api.settings import Settings
    with TestClient(create_app(Settings(database_url="sqlite://", redis_url=REDIS_URL))) as c:
        yield c


def _wait(client, job_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = client.get(f"{V1}/jobs/{job_id}").json()
        if st["state"] in ("succeeded", "failed", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_job_runs_on_worker_and_matches_in_process_result(worker, client):
    solvers = {s["descriptor"]["id"]: s for s in client.get(f"{V1}/solvers").json()}
    assert solvers["analytical.electrostatics.point_charges"]["queue_worker_online"] is True
    assert solvers["fem.dolfinx"]["queue_worker_online"] is False
    assert client.get(f"{V1}/health").json()["redis"]["ok"] is True

    small = {"samplings": [{"kind": "plane_grid", "id": "s", "u_extent_m": 4, "v_extent_m": 4,
                            "nu": 16, "nv": 16}], "quantities": ["E", "phi"]}
    job = client.post(f"{V1}/jobs", json={"scene": SCENE, "request": small})
    assert job.status_code == 202 and job.json()["queue"] == "solver.analytical"
    job_id = job.json()["job_id"]
    st = _wait(client, job_id)
    assert st["state"] == "succeeded" and st["result_header"]["solver_kind"] == "analytical"
    blob = client.get(f"{V1}/jobs/{job_id}/result").content
    sync = client.post(f"{V1}/simulations", json={"scene": SCENE, "request": small}).content
    _, a = wire.decode(blob)
    _, b = wire.decode(sync)
    assert np.array_equal(a["s.E"], b["s.E"]) and np.array_equal(a["s.phi"], b["s.phi"])


def test_websocket_streams_progress_until_done(worker, client):
    job_id = client.post(f"{V1}/jobs", json={"scene": SCENE, "request": BIG}).json()["job_id"]
    states, fractions = [], []
    with client.websocket_connect(f"{V1}/ws/jobs/{job_id}") as ws:
        while True:
            msg = ws.receive_json()
            states.append(msg["state"])
            fractions.append(msg["progress"])
            if msg["state"] in ("succeeded", "failed", "cancelled"):
                break
    assert states[-1] == "succeeded" and fractions[-1] == 1.0
    assert fractions == sorted(fractions)
    header, arrays = wire.decode(client.get(f"{V1}/jobs/{job_id}/result").content)
    assert arrays["vol.E"].shape == (100, 100, 100, 3) and header["quality"] == "high"


def test_job_can_be_cancelled(worker, client):
    huge = {**BIG, "samplings": [{**BIG["samplings"][0], "nx": 125, "ny": 125, "nz": 125}]}
    job_id = client.post(f"{V1}/jobs", json={"scene": SCENE, "request": huge}).json()["job_id"]
    assert client.delete(f"{V1}/jobs/{job_id}").status_code == 202
    assert _wait(client, job_id)["state"] == "cancelled"
    assert client.get(f"{V1}/jobs/{job_id}/result").status_code == 409


def test_unsupported_job_and_unknown_job(worker, client):
    scene = {"objects": [{"id": "s", "primitive": {"type": "sphere"}, "role": "conductor"}]}
    assert client.post(f"{V1}/jobs", json={"scene": scene, "request": BIG}).status_code == 422
    assert client.get(f"{V1}/jobs/doesnotexist").status_code == 404


def test_projects_persist_in_postgresql():
    from sqlalchemy import create_engine, text

    from emf_api.main import create_app
    from emf_api.settings import Settings
    try:
        with create_engine(PG_URL).connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        pytest.skip("PostgreSQL is not reachable")
    settings = Settings(database_url=PG_URL, redis_url=REDIS_URL)
    with TestClient(create_app(settings)) as c:
        pid = c.post(f"{V1}/projects", json={"name": "pg", "scene": SCENE,
                                             "view": {"slice": "xy"}}).json()["id"]
    with TestClient(create_app(settings)) as c2:  # a fresh app instance sees the stored project
        got = c2.get(f"{V1}/projects/{pid}").json()
        assert got["scene"]["objects"][1]["source"]["charge_C"] == -2e-9
        assert got["view"] == {"slice": "xy"}
        assert c2.delete(f"{V1}/projects/{pid}").status_code == 204
