#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
APP="$ROOT/scopes/ada/web/application/ada-generic-application"

cd "$APP"

echo '[bootstrap] Synchronizing locked ADA Generic Application environment'
uv sync --locked
uv run --locked python "$ROOT/scripts/scopes/ada/check.py" "$@"
