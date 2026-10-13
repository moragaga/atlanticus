#!/usr/bin/env bash
# Script local de consumo del repositorio exportado.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f .env ]]; then
  echo 'Create .env from .env.detail and configure the environment' >&2
  exit 2
fi
exec uv run --no-sync --env-file .env ada-integrated-operations-application "$@"
