FROM python:3.14.2-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_HTTP_TIMEOUT=120

WORKDIR /workspace

COPY backend/kernel /workspace/backend/kernel
COPY backend/observability /workspace/backend/observability
COPY connectivity/storage /workspace/connectivity/storage
COPY web /workspace/web

WORKDIR /workspace/web

RUN uv sync --frozen

ENTRYPOINT [".venv/bin/python", "-m", "pytest", "-q", "capabilities/source/blob/tests/integration/test_blob_source_azurite.py"]
