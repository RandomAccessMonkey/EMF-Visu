from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from emf_worker.client import JobClient

from .. import __version__
from ..db import Database
from ..deps import get_database, get_jobs, get_orchestrator
from ..orchestrator import Orchestrator
from ..schemas import ComponentHealth, Health, SolverStatus

router = APIRouter(tags=["system"])


def _redis_health(jobs: JobClient) -> ComponentHealth:
    try:
        jobs.ping()
        return ComponentHealth(ok=True)
    except Exception as exc:  # noqa: BLE001 - any failure means "unreachable"
        return ComponentHealth(ok=False, detail=f"{type(exc).__name__}: {exc}")


@router.get("/health")
def health(db: Annotated[Database, Depends(get_database)],
           jobs: Annotated[JobClient, Depends(get_jobs)]) -> Health:
    problem = db.check()
    database = ComponentHealth(ok=problem is None, detail=problem)
    redis = _redis_health(jobs)
    return Health(status="ok" if database.ok and redis.ok else "degraded", version=__version__,
                  database=database, redis=redis)


@router.get("/solvers")
def solvers(orch: Annotated[Orchestrator, Depends(get_orchestrator)],
            jobs: Annotated[JobClient, Depends(get_jobs)]) -> list[SolverStatus]:
    """Real availability: a solver is only 'available' if its code is loaded; its queue worker
    is only 'online' if a live worker answers right now."""
    try:
        online = jobs.online_queues()
    except Exception:  # noqa: BLE001 - broker down => no worker is reachable
        online = set()
    return [SolverStatus(descriptor=d, in_process=d.available,
                         queue_worker_online=d.available and d.queue in online)
            for d in orch.descriptors()]
