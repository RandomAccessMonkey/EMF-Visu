"""Client side of the job protocol, used by the API orchestrator."""

from __future__ import annotations

import time
import uuid
from typing import Any, Literal

import redis
from pydantic import BaseModel

from emf_core.scene.models import Scene
from emf_core.solvers import ResultHeader, SolveRequest

from . import JOB_PROTOCOL_VERSION
from .app import make_app
from .config import RESULT_TTL_S, cancel_key, job_key, result_key

_LIVENESS_TTL_S = 2.0  # how long a worker liveness answer is reused

JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobStatus(BaseModel):
    job_id: str
    state: JobState
    progress: float = 0.0  # 0..1
    message: str = ""
    failure_reason: str | None = None
    result_header: ResultHeader | None = None


class JobNotFoundError(Exception):
    pass


class JobClient:
    def __init__(self, redis_url: str) -> None:
        self._celery = make_app(redis_url)
        self._store = redis.Redis.from_url(redis_url, socket_connect_timeout=1.0,
                                           socket_timeout=5.0)
        self._online: tuple[float, set[str]] | None = None

    def ping(self) -> None:
        """Raise if the broker is unreachable."""
        self._store.ping()

    def online_queues(self, timeout_s: float = 0.5) -> set[str]:
        """Queues that currently have a live worker consuming them."""
        self.ping()
        now = time.monotonic()
        if self._online is not None and now - self._online[0] < _LIVENESS_TTL_S:
            return self._online[1]
        queues: set[str] = set()
        for _ in range(2):  # a broadcast reply can be missed once; ask twice before saying "no"
            replies = self._celery.control.inspect(timeout=timeout_s).active_queues() or {}
            queues = {q["name"] for qs in replies.values() for q in qs}
            if queues:
                break
        self._online = (now, queues)
        return queues

    def submit(self, scene: Scene, request: SolveRequest, queue: str) -> str:
        job_id = uuid.uuid4().hex
        self._store.set(job_key(job_id), queue, ex=RESULT_TTL_S)
        payload = {"protocol_version": JOB_PROTOCOL_VERSION,
                   "scene": scene.model_dump(mode="json"),
                   "request": request.model_dump(mode="json")}
        self._celery.send_task("emf.solve", args=[payload], queue=queue, task_id=job_id)
        return job_id

    def status(self, job_id: str) -> JobStatus:
        if not self._store.exists(job_key(job_id)):
            raise JobNotFoundError(job_id)
        res = self._celery.AsyncResult(job_id)
        state, info = res.state, res.info
        if state == "SUCCESS" and isinstance(info, dict):
            outcome: dict[str, Any] = info
            if outcome["status"] == "ok":
                return JobStatus(job_id=job_id, state="succeeded", progress=1.0,
                                 result_header=ResultHeader.model_validate(outcome["header"]))
            if outcome["status"] == "cancelled":
                return JobStatus(job_id=job_id, state="cancelled")
            return JobStatus(job_id=job_id, state="failed",
                             failure_reason=outcome.get("failure_reason", "unknown failure"))
        if state == "FAILURE":
            return JobStatus(job_id=job_id, state="failed", failure_reason=f"worker error: {info}")
        if state == "REVOKED" or (state == "PENDING" and self._store.exists(cancel_key(job_id))):
            return JobStatus(job_id=job_id, state="cancelled")
        if state == "PROGRESS" and isinstance(info, dict):
            return JobStatus(job_id=job_id, state="running",
                             progress=float(info.get("fraction", 0)),
                             message=str(info.get("message", "")))
        if state == "STARTED":
            return JobStatus(job_id=job_id, state="running")
        return JobStatus(job_id=job_id, state="queued")

    def cancel(self, job_id: str) -> None:
        """Cooperative cancellation: the worker checks the flag between chunks; a job that has
        not started yet is revoked."""
        if not self._store.exists(job_key(job_id)):
            raise JobNotFoundError(job_id)
        self._store.set(cancel_key(job_id), b"1", ex=RESULT_TTL_S)
        self._celery.control.revoke(job_id)

    def result_bytes(self, job_id: str) -> bytes | None:
        data = self._store.get(result_key(job_id))
        return data if isinstance(data, bytes) else None
