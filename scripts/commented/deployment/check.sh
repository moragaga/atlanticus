#!/usr/bin/env bash
# Wrapper fino: UV entrega Python/Ruff/Pytest exactos y check.py conserva la lógica del gate.
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON_VERSION="3.14.2"
RUFF_VERSION="0.15.22"
PYTEST_VERSION="9.1.1"

exec uv run \
    --python "${PYTHON_VERSION}" \
    --no-python-downloads \
    --no-project \
    --with "ruff==${RUFF_VERSION}" \
    --with "pytest==${PYTEST_VERSION}" \
    python "${ROOT}/scripts/commented/deployment/check.py" "$@"
