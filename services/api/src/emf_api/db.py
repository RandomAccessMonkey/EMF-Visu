"""Persistence. Single-user for now; every row has an ``owner_id`` column (constant "local")
so that authentication can be added later without a schema redesign."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Engine, String, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    owner_id: Mapped[str] = mapped_column(String(64), default="local", index=True)
    name: Mapped[str] = mapped_column(String(200))
    scene: Mapped[dict[str, Any]] = mapped_column(JSON)
    view: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now,
                                                 onupdate=_now)


class Database:
    def __init__(self, url: str) -> None:
        kwargs: dict[str, Any] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            from sqlalchemy.pool import StaticPool

            kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
        self.engine: Engine = create_engine(url, **kwargs)
        self._session = sessionmaker(self.engine, expire_on_commit=False)
        self.error: str | None = None

    def init(self) -> None:
        """Create tables. On failure the API keeps running; project endpoints report 503."""
        try:
            Base.metadata.create_all(self.engine)
            self.error = None
        except Exception as exc:  # noqa: BLE001 - any driver error means "unavailable"
            self.error = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"

    def check(self) -> str | None:
        if self.error is not None:
            self.init()
        if self.error is None:
            try:
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
            except Exception as exc:  # noqa: BLE001
                return f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        return self.error

    def session(self) -> Iterator[Session]:
        with self._session() as s:
            yield s
