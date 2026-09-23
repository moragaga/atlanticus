ARG PYTHON_IMAGE=python:3.14.2-slim-bookworm
ARG DOCKER_CLI_IMAGE=docker:28.5.1-cli

FROM ${DOCKER_CLI_IMAGE} AS docker

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC
COPY --from=docker /usr/local/bin/docker /usr/local/bin/docker
RUN apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates cron tzdata; \
    ln -snf /usr/share/zoneinfo/UTC /etc/localtime; \
    printf 'UTC\n' > /etc/timezone; \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app/scheduler
COPY scheduler.py ./scheduler.py
ENTRYPOINT ["python", "/app/scheduler/scheduler.py", "serve"]
