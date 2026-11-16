from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from emf_core.i18n import LocalizedText
from emf_worker.client import JobClient

from .db import Database
from .orchestrator import Orchestrator
from .schemas import ErrorBody


def get_orchestrator(request: Request) -> Orchestrator:
    orch: Orchestrator = request.app.state.orchestrator
    return orch


def get_jobs(request: Request) -> JobClient:
    jobs: JobClient = request.app.state.jobs
    return jobs


def get_database(request: Request) -> Database:
    db: Database = request.app.state.database
    return db


def get_session(request: Request) -> Iterator[Session]:
    db = get_database(request)
    problem = db.check()
    if problem is not None:
        raise api_error(503, "unavailable", f"database unavailable: {problem}")
    yield from db.session()


def api_error(status: int, code: Any, message: str,
              reasons: list[LocalizedText] | None = None) -> HTTPException:
    body = ErrorBody(code=code, message=message, reasons=reasons or [])
    return HTTPException(status_code=status, detail=body.model_dump())
