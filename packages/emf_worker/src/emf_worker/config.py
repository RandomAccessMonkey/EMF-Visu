from __future__ import annotations

import os

REDIS_URL = os.environ.get("EMF_REDIS_URL", "redis://localhost:6379/0")
RESULT_TTL_S = int(os.environ.get("EMF_RESULT_TTL_S", "3600"))


def result_key(job_id: str) -> str:
    return f"emf:result:{job_id}"


def cancel_key(job_id: str) -> str:
    return f"emf:cancel:{job_id}"


def job_key(job_id: str) -> str:
    return f"emf:job:{job_id}"
