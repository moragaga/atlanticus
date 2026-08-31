#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INTEGRATIONS="$ROOT/integrations"
DISTRIBUTIONS=(
  atlanticus-kernel
  atlanticus-observability
  atlanticus-http
  atlanticus-pi-contracts
  atlanticus-pi-web-api
)

CLEAN=0
RUN_COMMAND=(python "$ROOT/scripts/integrations/check.py")
for argument in "$@"; do
  if [[ "$argument" == "--clean" ]]; then
    CLEAN=1
  else
    RUN_COMMAND+=("$argument")
  fi
done

cd "$INTEGRATIONS"

if [[ ! -f "uv.lock" ]]; then
  echo "integrations/uv.lock is missing. Run uv lock from integrations first." >&2
  exit 1
fi

PYTHON_BIN="$(uv python find 3.14.2 --no-python-downloads)"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)'

if [[ "$CLEAN" -eq 1 ]]; then
  rm -rf .venv dist
  for project in pi/contracts pi/web-api; do
    rm -rf "$project/build" "$project/.pytest_cache" "$project/.ruff_cache"
    find "$project" -type d -name '*.egg-info' -prune -exec rm -rf {} + 2>/dev/null || true
  done
fi

REINSTALL_ARGS=()
for distribution in "${DISTRIBUTIONS[@]}"; do
  REINSTALL_ARGS+=(--reinstall-package "$distribution")
done

echo '[bootstrap] Synchronizing locked Atlanticus Integrations environment'
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
