@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT=%~dp0\..\.."
for %%I in ("%ROOT%") do set "ROOT=%%~fI"
set "CONNECTIVITY=%ROOT%\connectivity"
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
cd /d "%CONNECTIVITY%"

if not exist "uv.lock" (
    echo connectivity/uv.lock is missing. Run uv lock from connectivity first. 1>&2
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
    for %%P in (http-client key-vault cosmos service-bus sql storage redis) do (
        if exist "%%P\build" rmdir /s /q "%%P\build"
        if exist "%%P\.pytest_cache" rmdir /s /q "%%P\.pytest_cache"
        if exist "%%P\.ruff_cache" rmdir /s /q "%%P\.ruff_cache"
        for /d %%D in ("%%P\*.egg-info") do if exist "%%~fD" rmdir /s /q "%%~fD"
    )
)

echo [bootstrap] Synchronizing locked Atlanticus Connectivity environment
uv sync --python "%PYTHON_BIN%" --no-python-downloads --locked --all-packages --group dev --no-editable --reinstall-package atlanticus-kernel --reinstall-package atlanticus-observability --reinstall-package atlanticus-http --reinstall-package atlanticus-key-vault --reinstall-package atlanticus-cosmos --reinstall-package atlanticus-service-bus --reinstall-package atlanticus-sql --reinstall-package atlanticus-storage --reinstall-package atlanticus-redis
if errorlevel 1 exit /b 1

uv run --python "%PYTHON_BIN%" --no-python-downloads --no-sync python "%ROOT%\scripts\connectivity\check.py" %FORWARD_ARGS%
exit /b %errorlevel%
