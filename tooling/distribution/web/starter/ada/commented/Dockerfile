FROM python:3.14.2-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /bin/uv

ENV UV_LINK_MODE=copy UV_NO_PROGRESS=1
WORKDIR /build

COPY pyproject.toml manifest.json ./
COPY src/ ./src/
COPY docker/verify_delivery.py ./verify_delivery.py
COPY wheelhouse/ ./wheelhouse/
COPY requirements/ ./requirements/

RUN python verify_delivery.py . \
    && uv venv /opt/venv --python /usr/local/bin/python \
    && uv venv /opt/buildvenv --python /usr/local/bin/python \
    && uv pip install --python /opt/buildvenv/bin/python --only-binary :all: --require-hashes \
       -r requirements/starter-build.txt \
    && uv build --wheel --no-build-isolation --python /opt/buildvenv/bin/python \
       --out-dir /build/starter-wheels /build \
    && uv pip install --python /opt/venv/bin/python --only-binary :all: --require-hashes \
       -r requirements/project-runtime.txt -r requirements/host-runtime.txt \
    && uv pip install --python /opt/venv/bin/python --no-index --no-deps \
       --find-links /build/wheelhouse /build/wheelhouse/*.whl \
    && uv pip install --python /opt/venv/bin/python --no-index --no-deps \
       /build/starter-wheels/*.whl \
    && uv pip check --python /opt/venv/bin/python

FROM python:3.14.2-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    ATLANTICUS_ENVIRONMENT=local \
    APPLICATION_PUBLICATIONS_ROOT=/var/lib/atlanticus/publications

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /var/lib/atlanticus app \
    && mkdir -p /var/lib/atlanticus/publications /var/lib/atlanticus/tool /etc/atlanticus \
    && chown -R app:app /var/lib/atlanticus

COPY --from=builder /opt/venv /opt/venv
COPY gunicorn.conf.py /etc/atlanticus/gunicorn.conf.py

WORKDIR /var/lib/atlanticus
USER app
EXPOSE 8000

ENTRYPOINT ["gunicorn", "--config", "/etc/atlanticus/gunicorn.conf.py", "application.wsgi:application"]

# Instalación reproducible desde el lock derivado; producción permanece sin uv.
