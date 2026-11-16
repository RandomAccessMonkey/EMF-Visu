# syntax=docker/dockerfile:1.7
# EMF-Visu analytical solver worker: emf_core + emf_worker only (no web stack, no FEM/FDTD
# native dependencies). Consumes the "solver.analytical" queue. Build context: repository root.
# Base image is overridable so a registry mirror can be used (see README).
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services/api/pyproject.toml ./services/api/pyproject.toml
RUN --mount=type=secret,id=extra_ca,target=/run/extra-ca.pem,required=false \
    --mount=type=cache,target=/root/.cache/uv \
    if [ -s /run/extra-ca.pem ]; then export SSL_CERT_FILE=/run/extra-ca.pem PIP_CERT=/run/extra-ca.pem; fi && \
    pip install --no-cache-dir --root-user-action=ignore uv==0.11.32 && \
    uv sync --frozen --no-dev --package emf-worker --no-editable
RUN useradd --system --uid 10001 emf
USER emf
ENV EMF_WORKER_QUEUE=solver.analytical EMF_WORKER_CONCURRENCY=2
CMD ["sh", "-c", "exec celery -A emf_worker.app worker -Q \"$EMF_WORKER_QUEUE\" --concurrency \"$EMF_WORKER_CONCURRENCY\" --loglevel INFO"]
