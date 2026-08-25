#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$ROOT/web"

cd "$WEB"

echo '[bootstrap] Synchronizing locked Atlanticus Web environment'
uv sync --locked
uv run --locked python "$ROOT/scripts/web/check.py" "$@"
