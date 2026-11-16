from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.openapi.utils import get_openapi

from emf_core.solvers.analytical.gauss import FluxHeader
from emf_worker.client import JobClient

from . import __version__
from .db import Database
from .orchestrator import Orchestrator
from .routes import jobs, projects, simulation, system
from .settings import Settings, get_settings

log = logging.getLogger("uvicorn.error")


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database.init()
        # Startup diagnostics. The API keeps running without the database or Redis (field
        # solving needs neither), but it says clearly what will not work.
        if app.state.database.error:
            log.warning("database unavailable: %s - saving and loading projects will fail until "
                        "it is reachable (EMF_DATABASE_URL)", app.state.database.error)
        else:
            log.info("database connected")
        try:
            app.state.jobs.ping()
            log.info("redis connected")
        except Exception as exc:  # noqa: BLE001 - any failure means "unreachable"
            log.warning("redis unavailable: %s - queued high-resolution solves will fail until "
                        "it is reachable (EMF_REDIS_URL)", exc)
        yield

    app = FastAPI(title="EMF-Visu API", version=__version__, lifespan=lifespan)
    app.state.orchestrator = Orchestrator(cfg.cache_entries, cfg.sync_point_limit)
    app.state.database = Database(cfg.database_url)
    app.state.jobs = JobClient(cfg.redis_url)
    app.add_middleware(GZipMiddleware, minimum_size=4096)
    app.add_middleware(
        CORSMiddleware, allow_origins=[o.strip() for o in cfg.cors_origins.split(",") if o.strip()],
        allow_methods=["*"], allow_headers=["*"], expose_headers=["X-EMF-Cache"],
    )
    for r in (system.router, simulation.router, jobs.router, projects.router):
        app.include_router(r, prefix="/api/v1")

    def openapi() -> dict[str, Any]:
        """Standard schema plus FluxHeader, which travels inside the binary /flux response and
        is therefore not referenced by any JSON route."""
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        extra = FluxHeader.model_json_schema(ref_template="#/components/schemas/{model}",
                                             mode="serialization")
        comps = schema.setdefault("components", {}).setdefault("schemas", {})
        for name, definition in extra.pop("$defs", {}).items():
            comps.setdefault(name, definition)
        comps["FluxHeader"] = extra
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
    return app


app = create_app()
