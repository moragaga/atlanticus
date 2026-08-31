REM Mirror comentado: bootstrap reproducible de Integrations.
@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0\..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "INTEGRATIONS=%ROOT%\integrations"
set "CLEAN=0"
set "FORWARD_ARGS="

:parse_args
if "%~1"=="" goto args_done
if /I "%~1"=="--clean" (
    set "CLEAN=1"
) else (
    set "FORWARD_ARGS=!FORWARD_ARGS! %~1"
)
shift
goto parse_args

:args_done
cd /d "%INTEGRATIONS%"

if not exist "uv.lock" (
    echo integrations/uv.lock is missing. Run uv lock from integrations first. 1>&2
    exit /b 1
)

set "PYTHON_BIN="
for /f "usebackq delims=" %%P in (`uv python find 3.14.2 --no-python-downloads`) do set "PYTHON_BIN=%%P"
if not defined PYTHON_BIN exit /b 1

"%PYTHON_BIN%" -c "import sys; raise SystemExit(0 if sys.version_info[:3] == (3, 14, 2) else 1)"
if errorlevel 1 exit /b 1

if "%CLEAN%"=="1" (
    if exist ".venv" rmdir /s /q ".venv"
    if exist "dist" rmdir /s /q "dist"
    for %%P in (pi\contracts pi\web-api) do (
        if exist "%%P\build" rmdir /s /q "%%P\build"
        if exist "%%P\.pytest_cache" rmdir /s /q "%%P\.pytest_cache"
        if exist "%%P\.ruff_cache" rmdir /s /q "%%P\.ruff_cache"
    )
)

echo [bootstrap] Synchronizing locked Atlanticus Integrations environment
uv sync --python "%PYTHON_BIN%" --no-python-downloads --locked --all-packages --group dev --no-editable --reinstall-package atlanticus-kernel --reinstall-package atlanticus-observability --reinstall-package atlanticus-http --reinstall-package atlanticus-pi-contracts --reinstall-package atlanticus-pi-web-api
if errorlevel 1 exit /b 1

uv run --python "%PYTHON_BIN%" --no-python-downloads --no-sync python "%ROOT%\scripts\integrations\check.py" %FORWARD_ARGS%
exit /b %errorlevel%
