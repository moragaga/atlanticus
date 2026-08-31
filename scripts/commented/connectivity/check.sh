#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONNECTIVITY="$ROOT/connectivity"
DISTRIBUTIONS=(
  atlanticus-kernel
  atlanticus-observability
  atlanticus-http
  atlanticus-key-vault
  atlanticus-cosmos
  atlanticus-service-bus
  atlanticus-sql
  atlanticus-storage
  atlanticus-redis
)

# --clean conserva el modo fuerte para troubleshooting; no es el camino ordinario.
CLEAN=0
RUN_COMMAND=(python "$ROOT/scripts/connectivity/check.py")
for argument in "$@"; do
  if [[ "$argument" == "--clean" ]]; then
    CLEAN=1
  else
    RUN_COMMAND+=("$argument")
  fi
done

cd "$CONNECTIVITY"

if [[ ! -f "uv.lock" ]]; then
  echo "connectivity/uv.lock is missing. Run uv lock from connectivity first." >&2
  exit 1
fi

PYTHON_BIN="$(uv python find 3.14.2 --no-python-downloads)"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)'

if [[ "$CLEAN" -eq 1 ]]; then
  rm -rf .venv dist
  for project in http-client key-vault cosmos service-bus sql storage redis; do
    rm -rf "$project/build" "$project/.pytest_cache" "$project/.ruff_cache"
    find "$project" -maxdepth 2 -type d -name '*.egg-info' -prune -exec rm -rf {} + 2>/dev/null || true
  done
fi

# Reinstalamos también Kernel y Observability porque durante preproducción permanecen en 1.0.0.
REINSTALL_ARGS=()
for distribution in "${DISTRIBUTIONS[@]}"; do
  REINSTALL_ARGS+=(--reinstall-package "$distribution")
done

# La instalación no-editable evita colisiones entre distribuciones que comparten el namespace atlanticus.
echo '[bootstrap] Synchronizing locked Atlanticus Connectivity environment'
uv sync \
  --python "$PYTHON_BIN" \
  --no-python-downloads \
  --locked \
  --all-packages \
  --group dev \
  --no-editable \
  "${REINSTALL_ARGS[@]}"

uv run \
  --python "$PYTHON_BIN" \
  --no-python-downloads \
  --no-sync \
  "${RUN_COMMAND[@]}"
