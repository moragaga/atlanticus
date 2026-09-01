@echo off
REM Espejo comentado: bootstrap non-editable del scope Operational Data.
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0\..\..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "SCOPE=%ROOT%\scopes\operational-data"
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
cd /d "%SCOPE%"

if not exist "uv.lock" (
    echo scopes/operational-data/uv.lock is missing. Run uv lock from scopes/operational-data first. 1>&2
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
    for %%P in (core planner calendar sources producers\core producers\sql producers\pi producers\notpii producers\fabrica producers\remanentes processes\pi processes\notpii processes\dispatch processes\blockgrade processes\fabrica processes\remanentes) do (
        if exist "%%P\build" rmdir /s /q "%%P\build"
        if exist "%%P\.pytest_cache" rmdir /s /q "%%P\.pytest_cache"
        if exist "%%P\.ruff_cache" rmdir /s /q "%%P\.ruff_cache"
    )
)

echo [bootstrap] Synchronizing locked Atlanticus Operational Data environment
uv sync --python "%PYTHON_BIN%" --no-python-downloads --locked --all-packages --group dev --no-editable ^
 --reinstall-package atlanticus-configuration ^
 --reinstall-package atlanticus-kernel ^
 --reinstall-package atlanticus-observability ^
 --reinstall-package atlanticus-observability-azure ^
 --reinstall-package atlanticus-datasets ^
 --reinstall-package atlanticus-datasets-parquet ^
 --reinstall-package atlanticus-datasets-runtime ^
 --reinstall-package atlanticus-job-runtime ^
 --reinstall-package atlanticus-state ^
 --reinstall-package atlanticus-http ^
 --reinstall-package atlanticus-key-vault ^
 --reinstall-package atlanticus-service-bus ^
 --reinstall-package atlanticus-sql ^
 --reinstall-package atlanticus-storage ^
 --reinstall-package atlanticus-pi-contracts ^
 --reinstall-package atlanticus-pi-web-api ^
 --reinstall-package atlanticus-operational-data-core ^
 --reinstall-package atlanticus-operational-data-planner ^
 --reinstall-package atlanticus-operational-data-calendar ^
 --reinstall-package atlanticus-operational-data-sources ^
 --reinstall-package atlanticus-data-producers-core ^
 --reinstall-package atlanticus-data-producers-sql ^
 --reinstall-package atlanticus-data-producers-pi ^
 --reinstall-package atlanticus-data-producers-notpii ^
 --reinstall-package atlanticus-data-producers-fabrica ^
 --reinstall-package atlanticus-data-producers-remanentes ^
 --reinstall-package atlanticus-operational-data-pi-process ^
 --reinstall-package atlanticus-operational-data-notpii-process ^
 --reinstall-package atlanticus-operational-data-dispatch-process ^
 --reinstall-package atlanticus-operational-data-blockgrade-process ^
 --reinstall-package atlanticus-operational-data-fabrica-process ^
 --reinstall-package atlanticus-operational-data-remanentes-process
if errorlevel 1 exit /b 1

uv run --python "%PYTHON_BIN%" --no-python-downloads --no-sync python "%ROOT%\scripts\scopes\operational-data\check.py" %FORWARD_ARGS%
exit /b %errorlevel%
