from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from emf_worker.client import JobClient

from . import __version__
from .db import Database
from .orchestrator import Orchestrator
from .routes import jobs, projects, simulation, system
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.database.init()
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
    return app


app = create_app()
