#!/usr/bin/env bash
set -euo pipefail

# La ubicación del wrapper define la raíz del repositorio sin depender
# del directorio desde el cual el mantenedor ejecuta el comando.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WEB="$ROOT/web"

cd "$WEB"

# El lock existente es autoridad: el check no modifica dependencias.
echo '[bootstrap] Synchronizing locked Atlanticus Web environment'
uv sync --locked
# La lógica real vive en Python para compartir comportamiento con Windows.
uv run --locked python "$ROOT/scripts/web/check.py" "$@"
