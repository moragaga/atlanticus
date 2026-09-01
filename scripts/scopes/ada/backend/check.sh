#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

cd "$REPO_ROOT"
uv run \
  --python 3.14.2 \
  --project scopes/ada/backend \
  --frozen \
  python scripts/scopes/ada/backend/check.py "$@"
