#!/usr/bin/env bash
# Script local de consumo del repositorio exportado.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
uv venv --python 3.14.2 .venv
uv pip install --python .venv/bin/python --only-binary :all: --require-hashes \
  -r requirements/project-runtime.txt -r requirements/host-runtime.txt
uv pip install --python .venv/bin/python --no-index --no-deps \
  --find-links wheelhouse wheelhouse/*.whl
uv pip install --python .venv/bin/python --no-deps -e .
uv pip check --python .venv/bin/python
.venv/bin/python docker/verify_delivery.py .
