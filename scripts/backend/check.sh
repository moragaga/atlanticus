#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
DISTRIBUTIONS=(
  atlanticus-kernel
  atlanticus-json
  atlanticus-configuration
  atlanticus-datasets
  atlanticus-datasets-parquet
  atlanticus-datasets-runtime
  atlanticus-observability
  atlanticus-observability-azure
  atlanticus-state
  atlanticus-job-runtime
)

cd "$BACKEND"

if [[ ! -f "uv.lock" ]]; then
  echo "backend/uv.lock is missing. Run uv lock from backend first." >&2
  exit 1
fi

PYTHON_BIN="$(uv python find 3.14.2 --no-python-downloads)"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)'

REINSTALL_ARGS=()
for distribution in "${DISTRIBUTIONS[@]}"; do
  REINSTALL_ARGS+=(--reinstall-package "$distribution")
done

echo '[bootstrap] Synchronizing locked Atlanticus Backend environment'
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
  python "$ROOT/scripts/backend/check.py" "$@"
