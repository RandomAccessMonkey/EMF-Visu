"""Celery application and the single generic task ``emf.solve``.

Start a worker for one solver kind with, e.g.:

    celery -A emf_worker.app worker -Q solver.analytical --concurrency 2
"""

from __future__ import annotations

from typing import Any

import redis
from celery import Celery

from emf_core import engine
from emf_core.scene.models import Scene
from emf_core.solvers import SolverCancelledError, SolveRequest, SolverError, UnsupportedSceneError

from . import JOB_PROTOCOL_VERSION
from .config import REDIS_URL, RESULT_TTL_S, cancel_key, result_key


def make_app(redis_url: str) -> Celery:
    """Celery app bound to one broker. The worker uses the module-level ``app``; the API
    creates its own client-side app (tasks are addressed by name, so no import is needed)."""
    celery = Celery("emf", broker=redis_url, backend=redis_url)
    celery.conf.update(
        task_track_started=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        result_expires=RESULT_TTL_S,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        broker_connection_timeout=1.0,
        broker_transport_options={"socket_connect_timeout": 1.0, "socket_timeout": 5.0},
        task_default_queue="solver.analytical",
    )
    return celery


app = make_app(REDIS_URL)


@app.task(name="emf.solve", bind=True)  # type: ignore[untyped-decorator]
def solve(self: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Run one job. Always returns a status dict; the binary result goes to Redis."""
    job_id: str = self.request.id
    store = redis.Redis.from_url(REDIS_URL)

    def cancelled() -> bool:
        return bool(store.exists(cancel_key(job_id)))

    def progress(fraction: float, message: str) -> None:
        self.update_state(state="PROGRESS", meta={"fraction": fraction, "message": message})

    if payload.get("protocol_version") != JOB_PROTOCOL_VERSION:
        return {"status": "failed", "failure_reason": "unsupported job protocol version"}
    if cancelled():
        return {"status": "cancelled"}
    try:
        scene = Scene.model_validate(payload["scene"])
        request = SolveRequest.model_validate(payload["request"])
        result = engine.run(scene, request, progress, cancelled)
    except SolverCancelledError:
        return {"status": "cancelled"}
    except UnsupportedSceneError as exc:
        return {"status": "failed", "failure_reason": f"unsupported configuration: {exc}",
                "reasons": [r.model_dump() for r in exc.reasons]}
    except SolverError as exc:
        return {"status": "failed", "failure_reason": str(exc)}
    store.set(result_key(job_id), result.to_bytes(), ex=RESULT_TTL_S)
    return {"status": "ok", "header": result.header.model_dump(mode="json")}
