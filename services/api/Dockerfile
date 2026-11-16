# syntax=docker/dockerfile:1.7
# EMF-Visu API (FastAPI orchestrator + in-process analytical solver).
# Build context: repository root.
# Base image is overridable so a registry mirror can be used (see README).
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services/api ./services/api
# The optional "extra_ca" build secret lets the build work behind a TLS-inspecting proxy.
RUN --mount=type=secret,id=extra_ca,target=/run/extra-ca.pem,required=false \
    --mount=type=cache,target=/root/.cache/uv \
    if [ -s /run/extra-ca.pem ]; then export SSL_CERT_FILE=/run/extra-ca.pem PIP_CERT=/run/extra-ca.pem; fi && \
    pip install --no-cache-dir --root-user-action=ignore uv==0.11.32 && \
    uv sync --frozen --no-dev --package emf-api --no-editable
RUN useradd --system --uid 10001 emf
USER emf
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=6 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"
CMD ["uvicorn", "emf_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
