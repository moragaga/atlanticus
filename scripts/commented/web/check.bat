@echo off
setlocal EnableExtensions

rem Resolver la raíz desde scripts\web para no depender del directorio actual.
for %%I in ("%~dp0..\..") do set "ROOT=%%~fI"
set "WEB=%ROOT%\web"

cd /d "%WEB%" || exit /b 1

rem Sincronizar estrictamente con el lock ya versionado.
echo [bootstrap] Synchronizing locked Atlanticus Web environment
uv sync --locked || exit /b 1
rem Delegar la lógica compartida al mismo checker Python usado en Unix.
uv run --locked python "%ROOT%\scripts\web\check.py" %* || exit /b 1

exit /b 0
