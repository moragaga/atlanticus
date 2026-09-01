#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "$ROOT/scopes/ada/backend"
exec uv run --python 3.14.2 --no-python-downloads python "$ROOT/scripts/scopes/ada/backend/check.py" "$@"
