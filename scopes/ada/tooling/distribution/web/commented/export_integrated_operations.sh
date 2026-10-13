#!/usr/bin/env bash
# La ejecución falla de forma inmediata ante errores del exportador.
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd -- "$SCRIPT_DIR/../../../../.." && pwd)"
PROJECT="$REPOSITORY_ROOT/scopes/ada/web/application/ada-integrated-operations-application"
exec uv run --project "$PROJECT" --locked python "$SCRIPT_DIR/export_integrated_operations.py" "$@"
