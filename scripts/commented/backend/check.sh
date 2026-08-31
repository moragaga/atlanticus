#!/usr/bin/env bash
set -euo pipefail

# Resolver la raíz desde la ubicación del wrapper mantiene el gate independiente del cwd.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
# Los diez wheels de la capa se reinstalan explícitamente para no reutilizar una instalación editable previa.
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

# El gate consume un lock generado por UV y nunca lo modifica silenciosamente.
if [[ ! -f "uv.lock" ]]; then
  echo "backend/uv.lock is missing. Run uv lock from backend first." >&2
  exit 1
fi

# Se exige exactamente el runtime autoritativo y se impiden descargas automáticas de Python.
PYTHON_BIN="$(uv python find 3.14.2 --no-python-downloads)"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)'

# --reinstall-package elimina residuos de instalaciones editables anteriores del mismo workspace.
REINSTALL_ARGS=()
for distribution in "${DISTRIBUTIONS[@]}"; do
  REINSTALL_ARGS+=(--reinstall-package "$distribution")
done

# --no-editable materializa los packages como distribuciones normales dentro del entorno compartido.
echo '[bootstrap] Synchronizing locked Atlanticus Backend environment'
uv sync \
  --python "$PYTHON_BIN" \
  --no-python-downloads \
  --locked \
  --all-packages \
  --group dev \
  --no-editable \
  "${REINSTALL_ARGS[@]}"

# --no-sync evita que uv run revierta la instalación no-editable antes de ejecutar el gate Python.
uv run \
  --python "$PYTHON_BIN" \
  --no-python-downloads \
  --no-sync \
  python "$ROOT/scripts/backend/check.py" "$@"
