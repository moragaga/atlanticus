@echo off
setlocal EnableExtensions

for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
set "WEB=%ROOT%\web"

cd /d "%WEB%" || exit /b 1

echo [bootstrap] Synchronizing locked Atlanticus Web environment
uv sync --locked || exit /b 1
uv run --locked python "%ROOT%\scripts\web\check.py" %* || exit /b 1

exit /b 0
