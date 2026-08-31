@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Resolver la raíz desde el wrapper evita depender del directorio actual del usuario.
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
set "BACKEND=%ROOT%\backend"

cd /d "%BACKEND%" || exit /b 1

rem El gate exige un lock generado por UV y no lo modifica silenciosamente.
if not exist "uv.lock" (
    echo backend/uv.lock is missing. Run uv lock from backend first. 1>&2
    exit /b 1
)

rem Se resuelve exactamente Python 3.14.2 sin permitir descargas automáticas.
set "PYTHON_BIN="
for /f "usebackq delims=" %%P in (`uv python find 3.14.2 --no-python-downloads`) do set "PYTHON_BIN=%%P"
if not defined PYTHON_BIN exit /b 1

"%PYTHON_BIN%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)" || exit /b 1

rem Los packages del workspace se reinstalan como distribuciones normales para retirar residuos editables.
echo [bootstrap] Synchronizing locked Atlanticus Backend environment
uv sync --python "%PYTHON_BIN%" --no-python-downloads --locked --all-packages --group dev --no-editable ^
    --reinstall-package atlanticus-kernel ^
    --reinstall-package atlanticus-json ^
    --reinstall-package atlanticus-configuration ^
    --reinstall-package atlanticus-datasets ^
    --reinstall-package atlanticus-datasets-parquet ^
    --reinstall-package atlanticus-datasets-runtime ^
    --reinstall-package atlanticus-observability ^
    --reinstall-package atlanticus-observability-azure ^
    --reinstall-package atlanticus-state ^
    --reinstall-package atlanticus-job-runtime || exit /b 1

rem --no-sync conserva esa instalación no-editable cuando se ejecuta el gate común en Python.
uv run --python "%PYTHON_BIN%" --no-python-downloads --no-sync python "%ROOT%\scripts\backend\check.py" %* || exit /b 1

exit /b 0
