from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMF_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://emf:emf@localhost:5432/emf"
    redis_url: str = "redis://localhost:6379/0"  # read by emf_worker.config as EMF_REDIS_URL
    cors_origins: str = "http://localhost:5173"
    cache_entries: int = 64
    sync_point_limit: int = 400_000  # larger requests must use the job queue


@lru_cache
def get_settings() -> Settings:
    return Settings()
