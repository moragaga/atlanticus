#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SCOPE="$ROOT/scopes/operational-data"
DISTRIBUTIONS=(
  atlanticus-configuration
  atlanticus-kernel
  atlanticus-observability
  atlanticus-observability-azure
  atlanticus-datasets
  atlanticus-datasets-parquet
  atlanticus-datasets-runtime
  atlanticus-job-runtime
  atlanticus-state
  atlanticus-http
  atlanticus-key-vault
  atlanticus-service-bus
  atlanticus-sql
  atlanticus-storage
  atlanticus-pi-contracts
  atlanticus-pi-web-api
  atlanticus-operational-data-core
  atlanticus-operational-data-planner
  atlanticus-operational-data-calendar
  atlanticus-operational-data-sources
  atlanticus-data-producers-core
  atlanticus-data-producers-sql
  atlanticus-data-producers-pi
  atlanticus-data-producers-notpii
  atlanticus-data-producers-fabrica
  atlanticus-data-producers-remanentes
  atlanticus-operational-data-pi-process
  atlanticus-operational-data-notpii-process
  atlanticus-operational-data-dispatch-process
  atlanticus-operational-data-blockgrade-process
  atlanticus-operational-data-fabrica-process
  atlanticus-operational-data-remanentes-process
)
PROJECTS=(
  core
  planner
  calendar
  sources
  producers/core
  producers/sql
  producers/pi
  producers/notpii
  producers/fabrica
  producers/remanentes
  processes/pi
  processes/notpii
  processes/dispatch
  processes/blockgrade
  processes/fabrica
  processes/remanentes
)

CLEAN=0
RUN_COMMAND=(python "$ROOT/scripts/scopes/operational-data/check.py")
for argument in "$@"; do
  if [[ "$argument" == "--clean" ]]; then
    CLEAN=1
  else
    RUN_COMMAND+=("$argument")
  fi
done

cd "$SCOPE"

if [[ ! -f "uv.lock" ]]; then
  echo "scopes/operational-data/uv.lock is missing. Run uv lock from scopes/operational-data first." >&2
  exit 1
fi

PYTHON_BIN="$(uv python find 3.14.2 --no-python-downloads)"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)'

if [[ "$CLEAN" -eq 1 ]]; then
  rm -rf .venv dist
  for project in "${PROJECTS[@]}"; do
    rm -rf "$project/build" "$project/.pytest_cache" "$project/.ruff_cache"
    find "$project" -type d -name '*.egg-info' -prune -exec rm -rf {} + 2>/dev/null || true
  done
fi

REINSTALL_ARGS=()
for distribution in "${DISTRIBUTIONS[@]}"; do
  REINSTALL_ARGS+=(--reinstall-package "$distribution")
done

echo '[bootstrap] Synchronizing locked Atlanticus Operational Data environment'
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
