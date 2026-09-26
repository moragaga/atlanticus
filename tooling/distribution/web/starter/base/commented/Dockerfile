# El contenedor instala exclusivamente wheels ya publicados y verificados.
# La imagen se limita a qualification local; el host productivo requerirá contrato propio.
FROM python:3.14.2-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /bin/uv

ENV UV_OFFLINE=1 UV_LINK_MODE=copy UV_NO_PROGRESS=1

WORKDIR /build

COPY pyproject.toml manifest.json ./
COPY src/ ./src/
COPY docker/verify_wheelhouse.py ./verify_wheelhouse.py
COPY wheelhouse/ ./wheelhouse/

RUN python verify_wheelhouse.py . \
    && uv venv /opt/venv --python /usr/local/bin/python \
    && uv pip install --python /opt/venv/bin/python --no-index --find-links /build/wheelhouse /build

FROM python:3.14.2-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    ATLANTICUS_ENVIRONMENT=local \
    APPLICATION_PUBLICATIONS_ROOT=/var/lib/atlanticus/publications

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /var/lib/atlanticus app \
    && mkdir -p /var/lib/atlanticus/publications /var/lib/atlanticus/tool \
    && chown -R app:app /var/lib/atlanticus

COPY --from=builder /opt/venv /opt/venv

WORKDIR /var/lib/atlanticus
USER app
EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "from urllib.request import urlopen; assert urlopen('http://127.0.0.1:8050/health/live', timeout=3).status == 200"

ENTRYPOINT ["/bin/sh", "-c", "[ \"${ATLANTICUS_ENVIRONMENT:-local}\" = local ] || { echo 'Local Docker Starter cannot run in production' >&2; exit 2; }; exec python -m application"]
