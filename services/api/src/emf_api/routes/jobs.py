from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from emf_core.solvers import UnsupportedSceneError
from emf_worker.client import JobClient, JobNotFoundError, JobStatus

from ..deps import api_error, get_jobs, get_orchestrator
from ..orchestrator import Orchestrator
from ..schemas import ErrorBody, JobCreated, SimulationBody
from .simulation import RESULT_MEDIA_TYPE

router = APIRouter(tags=["jobs"])
Jobs = Annotated[JobClient, Depends(get_jobs)]
_TERMINAL = {"succeeded", "failed", "cancelled"}
_ERR: dict[int | str, dict[str, object]] = {404: {"model": ErrorBody}, 503: {"model": ErrorBody}}


@router.post("/jobs", status_code=202, responses={422: {"model": ErrorBody}, **_ERR})
def create_job(body: SimulationBody, jobs: Jobs,
               orch: Annotated[Orchestrator, Depends(get_orchestrator)]) -> JobCreated:
    """Queue a long-running simulation on the worker service of the selected solver."""
    try:
        solver = orch.select(body.scene, body.request)
    except UnsupportedSceneError as exc:
        raise api_error(422, "unsupported", "no available solver supports this configuration",
                        exc.reasons) from exc
    queue = f"solver.{solver.kind}"
    try:
        online = jobs.online_queues()
    except Exception as exc:  # noqa: BLE001 - any broker failure means "unavailable"
        raise api_error(503, "unavailable", f"job queue unreachable: {exc}") from exc
    if queue not in online:
        raise api_error(503, "unavailable", f"no worker is online for queue '{queue}'")
    job_id = jobs.submit(body.scene, body.request, queue)
    return JobCreated(job_id=job_id, queue=queue)


@router.get("/jobs/{job_id}", responses=_ERR)
def job_status(job_id: str, jobs: Jobs) -> JobStatus:
    try:
        return jobs.status(job_id)
    except JobNotFoundError as exc:
        raise api_error(404, "not_found", "unknown job") from exc


@router.delete("/jobs/{job_id}", status_code=202, responses=_ERR)
def cancel_job(job_id: str, jobs: Jobs) -> JobStatus:
    try:
        jobs.cancel(job_id)
        return jobs.status(job_id)
    except JobNotFoundError as exc:
        raise api_error(404, "not_found", "unknown job") from exc


@router.get("/jobs/{job_id}/result", response_class=Response,
            responses={200: {"content": {RESULT_MEDIA_TYPE: {}}}, 409: {"model": ErrorBody},
                       **_ERR})
def job_result(job_id: str, jobs: Jobs) -> Response:
    try:
        st = jobs.status(job_id)
    except JobNotFoundError as exc:
        raise api_error(404, "not_found", "unknown job") from exc
    blob = jobs.result_bytes(job_id) if st.state == "succeeded" else None
    if blob is None:
        raise api_error(409, "not_ready", f"job is {st.state}; no result available")
    return Response(blob, media_type=RESULT_MEDIA_TYPE)


@router.websocket("/ws/jobs/{job_id}")
async def job_progress(ws: WebSocket, job_id: str) -> None:
    """Push JobStatus JSON whenever it changes, until the job reaches a terminal state."""
    await ws.accept()
    jobs: JobClient = ws.app.state.jobs
    last: str | None = None
    try:
        while True:
            try:
                st = await run_in_threadpool(jobs.status, job_id)
            except JobNotFoundError:
                await ws.send_json({"error": "unknown job"})
                break
            payload = st.model_dump_json()
            if payload != last:
                await ws.send_text(payload)
                last = payload
            if st.state in _TERMINAL:
                break
            await asyncio.sleep(0.1)
        await ws.close()
    except WebSocketDisconnect:
        return
