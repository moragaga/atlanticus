#!/usr/bin/env bash
# Espejo pedagógico: resuelve la raíz del repositorio y delega toda la validación al gate Python.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT/scopes/ada-kpi-engine"
exec uv run --python 3.14.2 --no-python-downloads python "$ROOT/scripts/scopes/ada-kpi-engine/check.py" "$@"
